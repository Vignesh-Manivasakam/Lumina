from qdrant_client import QdrantClient
from qdrant_client.http import models
from fastembed import SparseTextEmbedding
from typing import Optional

from app.config import settings
from app.ingestion.chunking import MultimodalChunk

import uuid

DENSE_DIM = getattr(settings, "EMBEDDING_DIM", 384)

_SPARSE_MODEL: Optional[SparseTextEmbedding] = None


def _get_sparse_model() -> Optional[SparseTextEmbedding]:
    """Process-wide singleton for FastEmbed BM25 sparse model."""
    global _SPARSE_MODEL
    if _SPARSE_MODEL is None:
        try:
            _SPARSE_MODEL = SparseTextEmbedding("Qdrant/bm25", threads=1)
        except Exception:
            try:
                _SPARSE_MODEL = SparseTextEmbedding("Qdrant/bm25")
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning("Failed to load SparseTextEmbedding: %s", exc)
                _SPARSE_MODEL = None
    return _SPARSE_MODEL


def _to_valid_point_id(raw_id: str) -> str:
    """Convert arbitrary chunk IDs to valid UUIDs required by Qdrant."""
    try:
        uuid.UUID(str(raw_id))
        return str(raw_id)
    except Exception:
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, str(raw_id)))


class QdrantStore:
    def __init__(self):
        self.client = QdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY,
            timeout=60.0,
        )
        self.collection_name = settings.QDRANT_COLLECTION
        self._ensure_collection()

    @property
    def sparse_model(self) -> Optional[SparseTextEmbedding]:
        return _get_sparse_model()

    @sparse_model.setter
    def sparse_model(self, model: Optional[SparseTextEmbedding]) -> None:
        global _SPARSE_MODEL
        _SPARSE_MODEL = model

    def _ensure_collection(self):
        try:
            if not self.client.collection_exists(self.collection_name):
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config={
                        "dense": models.VectorParams(
                            size=DENSE_DIM,
                            distance=models.Distance.COSINE,
                        )
                    },
                    sparse_vectors_config={
                        "bm25": models.SparseVectorParams(
                            modifier=models.Modifier.IDF
                        )
                    },
                )
            
            # Ensure indexes exist for fast metadata filtering + session isolation
            for field in [
                "doc_id",
                "modality",
                "dept",
                "file_type",
                "session_id",
                "parent_id",
            ]:
                try:
                    self.client.create_payload_index(
                        collection_name=self.collection_name,
                        field_name=field,
                        field_schema=models.PayloadSchemaType.KEYWORD,
                    )
                except Exception:
                    pass

            try:
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="is_parent",
                    field_schema=models.PayloadSchemaType.BOOL,
                )
            except Exception:
                pass
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "QdrantStore: could not connect to Qdrant at %s: %s",
                settings.QDRANT_URL,
                exc,
            )

    def upsert(
        self,
        chunks: list[MultimodalChunk],
        session_id: Optional[str] = None,
    ):
        """Upsert chunks to the collection.

        ``session_id`` is an explicit parameter (preferred) and wins over
        any ``session_id`` already present on the chunk object. When a
        ``session_id`` is provided it is stored in the payload so
        retrieval can be scoped per-tenant via ``hybrid_search``.

        Phase 3: also stores ``parent_id`` / ``is_parent`` / ``child_ids``
        so retrieval can resolve child hits to their parent context.
        """
        points = []
        for c in chunks:
            sparse_enc = self._bm25_encode(c.text_repr)
            effective_session = (
                session_id
                or getattr(c, "session_id", None)
                or c.metadata.get("session_id")
            )
            point_id = _to_valid_point_id(c.chunk_id)
            points.append(
                models.PointStruct(
                    id=point_id,
                    vector={
                        "dense": c.embedding,
                        "bm25": models.SparseVector(
                            indices=sparse_enc["indices"],
                            values=sparse_enc["values"]
                        ),
                    },
                    payload={
                        "chunk_id": c.chunk_id,
                        "text_repr": c.text_repr,
                        "modality": c.modality,
                        "doc_id": c.doc_id,
                        "page_num": c.page_num,
                        "base64": c.base64,
                        "session_id": effective_session,
                        "metadata": c.metadata,
                        # Phase 3: parent-child hierarchy
                        "parent_id": c.parent_id,
                        "is_parent": c.is_parent,
                        "child_ids": list(c.child_ids or []),
                        "contextual_header": getattr(c, "contextual_header", None),
                        "original_text": getattr(c, "original_text", None),
                    },
                )
            )
        BATCH_SIZE = 30
        for i in range(0, len(points), BATCH_SIZE):
            batch = points[i : i + BATCH_SIZE]
            self.client.upsert(collection_name=self.collection_name, points=batch)

    def hybrid_search(
        self,
        dense_vector: list[float],
        query_text: str,
        top_k: int = 20,
        filters: dict | None = None,
        session_id: Optional[str] = None,
        only_children: bool = True,
        bm25_weight: float = 0.5,
        dense_weight: float = 0.5,
    ) -> list[dict]:
        """BM25 sparse + dense semantic → weighted RRF fusion query.

        When ``session_id`` is provided, it is ALWAYS added to the
        payload filter so the requesting session cannot see another
        tenant's chunks. Pass ``session_id=None`` only for shared/
        cross-tenant search (admin tools).

        Phase 3: ``only_children=True`` (default) restricts search to
        child chunks so retrieval hits are precise; the caller is then
        responsible for resolving to parents via
        :meth:`get_parents_for_children`.
        """
        effective_filters = dict(filters or {})
        # Session Private Isolation:
        # If session_id is provided, restrict search strictly to chunks belonging to this session
        # (or chunks tagged as workspace/global)
        if session_id:
            effective_filters["session_id"] = session_id

        must_conditions = [
            models.FieldCondition(key=k, match=models.MatchValue(value=v))
            for k, v in effective_filters.items()
        ]
        must_not_conditions = []
        if only_children:
            must_not_conditions.append(
                models.FieldCondition(key="is_parent", match=models.MatchValue(value=True))
            )
        if not effective_filters.get("is_web_search"):
            must_not_conditions.append(
                models.FieldCondition(key="is_web_search", match=models.MatchValue(value=True))
            )
        qdrant_filter = (
            models.Filter(
                must=must_conditions if must_conditions else None,
                must_not=must_not_conditions if must_not_conditions else None,
            )
            if (must_conditions or must_not_conditions)
            else None
        )
        sparse_vec = self._bm25_encode(query_text)

        try:
            # When weights are balanced, use Qdrant's server-side RRF fusion
            if abs(bm25_weight - dense_weight) < 1e-4:
                results = self.client.query_points(
                    collection_name=self.collection_name,
                    prefetch=[
                        models.Prefetch(
                            query=models.SparseVector(
                                indices=sparse_vec["indices"],
                                values=sparse_vec["values"]
                            ),
                            using="bm25",
                            limit=top_k,
                            filter=qdrant_filter,
                        ),
                        models.Prefetch(
                            query=dense_vector,
                            using="dense",
                            limit=top_k,
                            filter=qdrant_filter,
                        ),
                    ],
                    query=models.FusionQuery(fusion=models.Fusion.RRF),
                    limit=top_k,
                    with_payload=True,
                )
                return [
                    {
                        "id": p.id,
                        "score": p.score,
                        **p.payload
                    }
                    for p in results.points
                ]

            # For asymmetric query types, perform weighted RRF over candidate sets
            candidate_limit = max(top_k * 2, 20)
            bm25_res = self.client.query_points(
                collection_name=self.collection_name,
                query=models.SparseVector(
                    indices=sparse_vec["indices"],
                    values=sparse_vec["values"]
                ),
                using="bm25",
                limit=candidate_limit,
                query_filter=qdrant_filter,
                with_payload=True,
            )
            dense_res = self.client.query_points(
                collection_name=self.collection_name,
                query=dense_vector,
                using="dense",
                limit=candidate_limit,
                query_filter=qdrant_filter,
                with_payload=True,
            )

            rrf_k = 60
            scores: dict[str, float] = {}
            payloads: dict[str, dict] = {}

            for rank, p in enumerate(bm25_res.points):
                scores[p.id] = scores.get(p.id, 0.0) + bm25_weight / (rrf_k + rank + 1)
                payloads[p.id] = p.payload or {}

            for rank, p in enumerate(dense_res.points):
                scores[p.id] = scores.get(p.id, 0.0) + dense_weight / (rrf_k + rank + 1)
                if p.id not in payloads:
                    payloads[p.id] = p.payload or {}

            sorted_ids = sorted(scores.keys(), key=lambda pid: scores[pid], reverse=True)[:top_k]
            return [
                {
                    "id": pid,
                    "score": scores[pid],
                    **payloads[pid]
                }
                for pid in sorted_ids
            ]
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("QdrantStore.hybrid_search failed: %s", exc)
            return []

    def get_by_ids(self, ids: list[str]) -> list[dict]:
        """Fetch full payloads for a set of chunk IDs."""
        if not ids:
            return []
        valid_ids = [_to_valid_point_id(i) for i in ids]
        points = self.client.retrieve(
            collection_name=self.collection_name,
            ids=valid_ids,
            with_payload=True,
            with_vectors=False,
        )
        return [
            {"id": p.id, **p.payload}
            for p in points
            if p.payload is not None
        ]

    def get_parents_for_children(
        self,
        child_hits: list[dict],
        session_id: Optional[str] = None,
        max_parents: int = 5,
    ) -> list[dict]:
        """Resolve child chunk hits to their parent chunks.

        Deduplicates parents (many children share one parent) and sorts
        by the best child's RRF score so the strongest context surfaces
        first. ``session_id`` is applied as a safety filter.
        """
        parent_scores: dict[str, float] = {}
        child_to_parent: dict[str, str] = {}
        for hit in child_hits:
            parent_id = hit.get("parent_id")
            if not parent_id:
                continue
            score = float(hit.get("score", 0.0) or 0.0)
            prev = parent_scores.get(parent_id)
            if prev is None or score > prev:
                parent_scores[parent_id] = score
            child_to_parent[hit.get("id", "")] = parent_id

        if not parent_scores:
            return []

        # Sort parents by best child's score, take top-N, then fetch
        ordered_ids = sorted(parent_scores.keys(), key=lambda k: parent_scores[k], reverse=True)[:max_parents]
        parents = self.get_by_ids(ordered_ids)

        # Re-apply ordering (retrieve() may not preserve order)
        index_map = {pid: i for i, pid in enumerate(ordered_ids)}
        parents.sort(key=lambda p: index_map.get(p.get("id"), 1_000_000))

        # Final session filter (defensive — child filter already enforced it)
        if session_id:
            parents = [p for p in parents if p.get("session_id") == session_id]

        return parents

    def delete_by_session(self, session_id: str) -> int:
        """Delete all chunks whose ``session_id`` payload matches.

        Returns the number of points deleted. Used by
        ``POST /api/sessions/{id}/cleanup`` so a session can wipe its
        own data without affecting the global document index.
        """
        if not session_id:
            return 0
        selector = models.FilterSelector(
            filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="session_id",
                        match=models.MatchValue(value=session_id),
                    )
                ]
            )
        )
        result = self.client.delete(
            collection_name=self.collection_name,
            points_selector=selector,
        )
        # qdrant-client returns either a DeleteResult or just status; be
        # defensive about attribute access
        return int(getattr(result, "deleted", 0) or 0)

    def delete_by_doc_id(self, doc_id: str) -> int:
        """Delete all chunks associated with a specific doc_id."""
        if not doc_id:
            return 0
        try:
            selector = models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="doc_id",
                            match=models.MatchValue(value=doc_id),
                        )
                    ]
                )
            )
            result = self.client.delete(
                collection_name=self.collection_name,
                points_selector=selector,
            )
            return int(getattr(result, "deleted", 0) or 0)
        except Exception as e:
            print(f"[QdrantStore] delete_by_doc_id error: {e}")
            return 0

    def _build_filter(self, filters: dict | None) -> models.Filter | None:
        if not filters:
            return None
        conditions = [
            models.FieldCondition(
                key=k, match=models.MatchValue(value=v)
            )
            for k, v in filters.items()
        ]
        return models.Filter(must=conditions)

    def _bm25_encode(self, text: str) -> dict:
        try:
            model = self.sparse_model
            if model is not None and text:
                result = list(model.embed([text]))[0]
                return {
                    "indices": result.indices.tolist(),
                    "values": result.values.tolist()
                }
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("BM25 encoding failed (%s); using dummy sparse vector", exc)
        return {"indices": [], "values": []}
