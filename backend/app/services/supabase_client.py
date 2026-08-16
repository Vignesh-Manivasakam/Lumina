import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.config import settings


class SupabaseService:
    """Supabase wrapper with graceful degradation.

    When ``SUPABASE_URL`` and ``SUPABASE_SERVICE_KEY`` are set in the
    environment, all calls hit the real Supabase project. When they are
    unset (or empty), the service operates in offline/local mode using a
    local metadata registry (.local_documents.json) so documents, sessions,
    and chat history are preserved locally without requiring external DBs.
    """

    def __init__(self):
        self._enabled: bool = bool(
            settings.SUPABASE_URL.strip() and settings.SUPABASE_SERVICE_KEY.strip()
        )
        self._client = None
        self._local_docs_file = Path(__file__).resolve().parent.parent.parent / ".local_documents.json"
        self._local_documents: dict[str, dict] = self._load_local_docs()
        self._local_mcp_file = Path(__file__).resolve().parent.parent.parent / ".local_mcp.json"
        self._local_mcp_connections: dict[str, dict] = self._load_local_mcp()

        if self._enabled:
            try:
                from supabase import create_client
                self._client = create_client(
                    settings.SUPABASE_URL,
                    settings.SUPABASE_SERVICE_KEY,
                )
            except Exception as exc:  # pragma: no cover
                print(f"[SupabaseService] init failed ({exc}); running in offline mode.")
                self._enabled = False
                self._client = None

    def _load_local_docs(self) -> dict[str, dict]:
        """Load local documents from disk or seed from Qdrant if available."""
        docs = {}
        if self._local_docs_file.exists():
            try:
                with open(self._local_docs_file, "r", encoding="utf-8") as f:
                    docs = json.load(f)
            except Exception as e:
                print(f"[SupabaseService] Error reading local docs file: {e}")

        # Seed from Qdrant if local storage is empty
        if not docs:
            try:
                from app.retrieval.qdrant_store import QdrantStore
                qs = QdrantStore()
                scroll_res = qs.client.scroll(qs.collection_name, limit=100, with_payload=True)
                points = scroll_res[0] if scroll_res else []
                for p in points:
                    payload = getattr(p, "payload", {}) or {}
                    doc_id = payload.get("doc_id")
                    if doc_id and not payload.get("metadata", {}).get("is_web_search") and not doc_id.startswith("web_"):
                        meta = payload.get("metadata", {})
                        raw_title = meta.get("title") or payload.get("text_repr", "")[:30] or doc_id
                        clean_filename = raw_title.replace("0e581e5be70bac04_", "")
                        if doc_id not in docs:
                            docs[doc_id] = {
                                "id": doc_id,
                                "filename": clean_filename,
                                "file_type": meta.get("file_type") or "pdf",
                                "dept": meta.get("dept") or "General",
                                "status": "ready",
                                "created_at": datetime.now(timezone.utc).isoformat(),
                                "num_chunks": 1,
                            }
                if docs:
                    with open(self._local_docs_file, "w", encoding="utf-8") as f:
                        json.dump(docs, f, indent=2)
            except Exception:
                pass
        return docs

    def _save_local_docs(self):
        try:
            with open(self._local_docs_file, "w", encoding="utf-8") as f:
                json.dump(self._local_documents, f, indent=2)
        except Exception as e:
            print(f"[SupabaseService] Error saving local docs file: {e}")

    def _load_local_mcp(self) -> dict[str, dict]:
        """Load local MCP connections from disk."""
        connections = {}
        if self._local_mcp_file.exists():
            try:
                with open(self._local_mcp_file, "r", encoding="utf-8") as f:
                    connections = json.load(f)
            except Exception as e:
                print(f"[SupabaseService] Error reading local mcp file: {e}")
        return connections

    def _save_local_mcp(self):
        try:
            with open(self._local_mcp_file, "w", encoding="utf-8") as f:
                json.dump(self._local_mcp_connections, f, indent=2)
        except Exception as e:
            print(f"[SupabaseService] Error saving local mcp file: {e}")

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _noop(self, *_args, **_kwargs):
        """Default no-op return for disabled service."""
        return {}

    # --- Document Registry ---
    def create_document(self, filename: str, file_type: str, dept: str = "General", storage_path: Optional[str] = None) -> dict:
        doc_id = f"doc-{uuid.uuid4().hex[:10]}"
        clean_name = filename
        if len(filename) > 17 and filename[16] == "_":
            # Strip random hex prefix from displayed filename if present
            clean_name = filename[17:]

        local_doc = {
            "id": doc_id,
            "filename": clean_name,
            "file_type": file_type,
            "dept": dept,
            "status": "processing",
            "storage_path": storage_path,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "num_chunks": 0,
        }
        self._local_documents[doc_id] = local_doc
        self._save_local_docs()

        if not self._enabled or not self._client:
            return local_doc

        try:
            data = {
                "id": doc_id,
                "filename": clean_name,
                "file_type": file_type,
                "dept": dept,
                "status": "processing",
                "storage_path": storage_path,
            }
            res = self._client.table("documents").insert(data).execute()
            return res.data[0] if res.data else local_doc
        except Exception as e:
            print(f"[SupabaseService] create_document remote failed (using local): {e}")
            return local_doc

    def update_document_status(self, doc_id: str, status: str, num_chunks: Optional[int] = None) -> dict:
        if doc_id in self._local_documents:
            self._local_documents[doc_id]["status"] = status
            if num_chunks is not None:
                self._local_documents[doc_id]["num_chunks"] = num_chunks
            self._save_local_docs()
            local_doc = self._local_documents[doc_id]
        else:
            local_doc = {"id": doc_id, "status": status}

        if not self._enabled or not self._client:
            return local_doc

        try:
            data = {"status": status}
            if num_chunks is not None:
                data["num_chunks"] = num_chunks
            res = self._client.table("documents").update(data).eq("id", doc_id).execute()
            return res.data[0] if res.data else local_doc
        except Exception as e:
            print(f"[SupabaseService] update_document_status remote failed: {e}")
            return local_doc

    def get_document_status(self, doc_id: str) -> str:
        if doc_id in self._local_documents:
            return self._local_documents[doc_id].get("status", "ready")
        if not self._enabled or not self._client:
            return "ready"
        try:
            res = self._client.table("documents").select("status").eq("id", doc_id).execute()
            if res.data:
                return res.data[0]["status"]
        except Exception:
            pass
        return "ready"

    def get_all_documents(self) -> list:
        if self._enabled and self._client:
            try:
                res = self._client.table("documents").select("*").order("created_at", desc=True).execute()
                if res.data:
                    return res.data
            except Exception as e:
                print(f"[SupabaseService] get_all_documents remote failed: {e}")

        # Return local documents sorted by created_at desc
        return sorted(
            list(self._local_documents.values()),
            key=lambda d: d.get("created_at", ""),
            reverse=True,
        )

    def delete_document(self, doc_id: str) -> dict:
        """Permanently delete document record from local registry and Supabase."""
        deleted = False
        if doc_id in self._local_documents:
            del self._local_documents[doc_id]
            self._save_local_docs()
            deleted = True

        if self._enabled and self._client:
            try:
                self._client.table("chunks").delete().eq("doc_id", doc_id).execute()
                self._client.table("documents").delete().eq("id", doc_id).execute()
                deleted = True
            except Exception as e:
                print(f"[SupabaseService] delete_document remote failed: {e}")

        return {"status": "deleted" if deleted else "not_found", "doc_id": doc_id}

    # --- Chunks Metadata ---
    def insert_chunks(self, chunks: list):
        if not self._enabled or not chunks:
            return
        try:
            self._client.table("chunks").insert(chunks).execute()
        except Exception as exc:
            print(f"[SupabaseService] insert_chunks failed (non-fatal): {exc}")

    # --- Chat Sessions ---
    def ensure_session(self, session_id: str, user_id: Optional[str] = None) -> dict:
        """Ensure that a session record with id=session_id exists in Supabase.

        Uses upsert so it is safe to call concurrently and idempotently.
        """
        if not self._enabled or not self._client or not session_id:
            return {"id": session_id or "local"}
        try:
            data = {"id": session_id}
            if user_id:
                data["user_id"] = user_id
            res = self._client.table("sessions").upsert(data).execute()
            return res.data[0] if res.data else {"id": session_id}
        except Exception as exc:
            logger.warning(f"ensure_session failed for {session_id}: {exc}")
            return {"id": session_id}

    def create_session(self, user_id: Optional[str] = None, session_id: Optional[str] = None) -> dict:
        if not self._enabled or not self._client:
            # Local-only mode: caller will use a session UUID generated
            # by the SessionIsolationMiddleware. No persistence.
            return {"id": session_id or "local"}
        data: dict = {}
        if session_id:
            data["id"] = session_id
        if user_id:
            data["user_id"] = user_id
        try:
            res = self._client.table("sessions").upsert(data).execute()
            return res.data[0] if res.data else {"id": session_id or "local"}
        except Exception as exc:
            logger.warning(f"create_session failed: {exc}")
            return {"id": session_id or "local"}

    def get_session(self, session_id: str) -> Optional[dict]:
        if not self._enabled:
            return None
        res = self._client.table("sessions").select("*").eq("id", session_id).execute()
        return res.data[0] if res.data else None

    def list_sessions(self, limit: int = 50) -> list:
        if not self._enabled:
            return []
        res = (
            self._client.table("sessions")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return res.data or []

    # --- Messages ---
    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        image_b64: Optional[str] = None,
        source_chunks: Optional[list] = None,
    ) -> dict:
        if not self._enabled or not self._client or not session_id:
            return {"id": "local", "session_id": session_id, "role": role}
        try:
            self.ensure_session(session_id)
            data = {
                "session_id": session_id,
                "role": role,
                "content": content,
                "image_b64": image_b64,
                "source_chunks": source_chunks or [],
            }
            res = self._client.table("messages").insert(data).execute()
            return res.data[0] if res.data else {}
        except Exception as exc:
            logger.warning(f"add_message failed to insert message in Supabase: {exc}")
            return {"id": "local", "session_id": session_id, "role": role}

    def get_session_messages(self, session_id: str) -> list:
        if not self._enabled:
            return []
        res = (
            self._client.table("messages")
            .select("*")
            .eq("session_id", session_id)
            .order("created_at", asc=True)
            .execute()
        )
        return res.data or []

    def get_session_history(self, session_id: str) -> list[dict]:
        if not self._enabled:
            return []
        res = (
            self._client.table("messages")
            .select("*")
            .eq("session_id", session_id)
            .order("created_at")
            .execute()
        )
        return res.data or []

    # --- Phase 2: session lifecycle ---
    def cleanup_session(self, session_id: str) -> dict:
        """Delete all messages for a session. Documents remain (shared).

        Returns ``{"session_id": ..., "deleted": <int>}``. Idempotent —
        safe to call multiple times. No-op when Supabase is disabled.
        """
        if not session_id:
            return {"session_id": session_id, "deleted": 0}
        if not self._enabled:
            return {"session_id": session_id, "deleted": 0, "mode": "local"}
        msgs = (
            self._client.table("messages")
            .select("id")
            .eq("session_id", session_id)
            .execute()
        )
        count = len(msgs.data or [])
        if count:
            self._client.table("messages").delete().eq("session_id", session_id).execute()
        return {"session_id": session_id, "deleted": count}

    def delete_session(self, session_id: str) -> dict:
        """Permanently delete a session and all its messages."""
        cleanup = self.cleanup_session(session_id)
        if not self._enabled:
            return {
                "session_id": session_id,
                "deleted_messages": 0,
                "mode": "local",
            }
        try:
            self._client.table("sessions").delete().eq("id", session_id).execute()
        except Exception:
            pass
        return {
            "session_id": session_id,
            "deleted_messages": cleanup["deleted"],
        }

    # --- MCP Connections ---
    def create_mcp_connection(
        self,
        name: str,
        endpoint_url: str,
        transport: str = "sse",
        scope: str = "workspace",
        session_id: Optional[str] = None,
        tools: Optional[list] = None,
    ) -> dict:
        conn_id = f"mcp-{uuid.uuid4().hex[:10]}"
        data = {
            "id": conn_id,
            "name": name,
            "endpoint_url": endpoint_url,
            "transport": transport,
            "scope": scope,
            "session_id": session_id,
            "tools": tools or [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._local_mcp_connections[conn_id] = data
        self._save_local_mcp()

        if not self._enabled or not self._client:
            return data
        try:
            res = self._client.table("mcp_connections").insert(data).execute()
            return res.data[0] if res.data else data
        except Exception as exc:
            print(f"[SupabaseService] create_mcp_connection failed (using local): {exc}")
            return data

    def list_mcp_connections(
        self, scope: Optional[str] = None, session_id: Optional[str] = None
    ) -> list:
        if self._enabled and self._client:
            try:
                query = self._client.table("mcp_connections").select("*")
                if scope:
                    query = query.eq("scope", scope)
                if session_id:
                    query = query.eq("session_id", session_id)
                res = query.order("created_at", desc=True).execute()
                if res.data:
                    return res.data
            except Exception as exc:
                print(f"[SupabaseService] list_mcp_connections remote failed: {exc}")

        # Return local connections
        results = list(self._local_mcp_connections.values())
        if scope:
            results = [c for c in results if c.get("scope") == scope]
        if session_id:
            results = [
                c for c in results
                if c.get("session_id") == session_id or c.get("scope") == "workspace"
            ]
        return sorted(results, key=lambda c: c.get("created_at", ""), reverse=True)

    def get_mcp_connection(self, connection_id_or_name: str) -> Optional[dict]:
        if self._enabled and self._client:
            try:
                res = (
                    self._client.table("mcp_connections")
                    .select("*")
                    .or_(f"id.eq.{connection_id_or_name},name.eq.{connection_id_or_name}")
                    .execute()
                )
                if res.data:
                    return res.data[0]
            except Exception as exc:
                print(f"[SupabaseService] get_mcp_connection remote failed: {exc}")

        if connection_id_or_name in self._local_mcp_connections:
            return self._local_mcp_connections[connection_id_or_name]
        for conn in self._local_mcp_connections.values():
            if conn.get("name") == connection_id_or_name or conn.get("id") == connection_id_or_name:
                return conn
        return None

    def delete_mcp_connection(self, connection_id: str) -> bool:
        if connection_id in self._local_mcp_connections:
            del self._local_mcp_connections[connection_id]
            self._save_local_mcp()
        else:
            # Check by name
            for k, v in list(self._local_mcp_connections.items()):
                if v.get("name") == connection_id or v.get("id") == connection_id:
                    del self._local_mcp_connections[k]
                    self._save_local_mcp()

        if self._enabled and self._client:
            try:
                self._client.table("mcp_connections").delete().eq("id", connection_id).execute()
            except Exception as exc:
                print(f"[SupabaseService] delete_mcp_connection remote failed: {exc}")
        return True

    # --- Conversations ---
    def create_conversation(
        self,
        title: str = "New Conversation",
        session_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> dict:
        data = {
            "title": title,
            "session_id": session_id,
            "metadata": metadata or {},
            "archived": False,
        }
        if not self._enabled:
            data["id"] = f"conv-local-{session_id or 'anon'}"
            return data
        try:
            res = self._client.table("conversations").insert(data).execute()
            return res.data[0] if res.data else data
        except Exception as exc:
            print(f"[SupabaseService] create_conversation failed (falling back to local): {exc}")
            data["id"] = f"conv-local-{session_id or 'anon'}"
            return data

    def list_conversations(
        self, session_id: Optional[str] = None, limit: int = 50
    ) -> list:
        if not self._enabled:
            return []
        try:
            query = self._client.table("conversations").select("*")
            if session_id:
                query = query.eq("session_id", session_id)
            res = query.order("created_at", desc=True).limit(limit).execute()
            return res.data or []
        except Exception as exc:
            print(f"[SupabaseService] list_conversations failed: {exc}")
            return []

    def get_conversation(self, conversation_id: str) -> Optional[dict]:
        if not self._enabled:
            return None
        try:
            res = self._client.table("conversations").select("*").eq("id", conversation_id).execute()
            return res.data[0] if res.data else None
        except Exception as exc:
            print(f"[SupabaseService] get_conversation failed: {exc}")
            return None

    def update_conversation(
        self,
        conversation_id: str,
        title: Optional[str] = None,
        archived: Optional[bool] = None,
        metadata: Optional[dict] = None,
    ) -> dict:
        data: dict = {}
        if title is not None:
            data["title"] = title
        if archived is not None:
            data["archived"] = archived
        if metadata is not None:
            data["metadata"] = metadata

        if not self._enabled:
            data["id"] = conversation_id
            return data
        try:
            res = self._client.table("conversations").update(data).eq("id", conversation_id).execute()
            return res.data[0] if res.data else {"id": conversation_id, **data}
        except Exception as exc:
            print(f"[SupabaseService] update_conversation failed: {exc}")
            return {"id": conversation_id, **data}

