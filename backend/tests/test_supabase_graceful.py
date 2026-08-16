"""Tests for the graceful Supabase degradation."""
from __future__ import annotations

import pytest

from app.config import settings
from app.services.supabase_client import SupabaseService


@pytest.fixture
def supabase_off(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "SUPABASE_URL", "")
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_KEY", "")
    return SupabaseService()


@pytest.fixture
def supabase_on(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_KEY", "test-service-key")
    return SupabaseService()


class TestSupabaseOffline:
    """When SUPABASE_URL is empty, all methods return safe defaults."""

    def test_disabled_when_url_empty(self, supabase_off):
        assert supabase_off.enabled is False

    def test_create_document_returns_local_dict(self, supabase_off):
        result = supabase_off.create_document("file.pdf", "pdf", "HR")
        assert result["filename"] == "file.pdf"
        assert result["status"] == "pending"
        assert "id" in result

    def test_update_document_status_noop(self, supabase_off):
        result = supabase_off.update_document_status("doc-1", "ready", num_chunks=10)
        assert result["status"] == "ready"
        assert result["id"] == "doc-1"

    def test_get_document_status_returns_ready(self, supabase_off):
        # Without persistence, all docs are reported ready immediately.
        assert supabase_off.get_document_status("any-id") == "ready"

    def test_get_all_documents_returns_empty(self, supabase_off):
        assert supabase_off.get_all_documents() == []

    def test_insert_chunks_silent(self, supabase_off):
        # Must not raise.
        supabase_off.insert_chunks([{"chunk_id": "c1", "doc_id": "d1"}])

    def test_create_session_returns_local_id(self, supabase_off):
        result = supabase_off.create_session()
        assert result["id"] == "local"

    def test_list_sessions_returns_empty(self, supabase_off):
        assert supabase_off.list_sessions() == []

    def test_add_message_noop(self, supabase_off):
        result = supabase_off.add_message("s1", "user", "hello")
        assert result["role"] == "user"

    def test_get_session_history_returns_empty(self, supabase_off):
        assert supabase_off.get_session_history("s1") == []

    def test_cleanup_session_noop_with_mode_flag(self, supabase_off):
        result = supabase_off.cleanup_session("s1")
        assert result["deleted"] == 0
        assert result["mode"] == "local"

    def test_delete_session_noop(self, supabase_off):
        result = supabase_off.delete_session("s1")
        assert result["deleted_messages"] == 0
        assert result["mode"] == "local"

    def test_empty_session_id_safe(self, supabase_off):
        # Must not crash on empty session ID.
        assert supabase_off.cleanup_session("") == {"session_id": "", "deleted": 0}


class TestSupabaseOnline:
    """When SUPABASE_URL is set, the client initialises (uses stub)."""

    def test_enabled_when_url_set(self, supabase_on):
        assert supabase_on.enabled is True

    def test_create_session_real_path(self, supabase_on):
        # Hits the stub create_client which returns no data — should
        # still return an empty dict, not crash.
        result = supabase_on.create_session()
        # Stub returns no data, so this falls through to {}.
        assert isinstance(result, dict)

    def test_get_all_documents_returns_empty_from_stub(self, supabase_on):
        assert supabase_on.get_all_documents() == []
