"""Integration tests for new FastAPI endpoints (Voice, MCP, Conversations, Chat SSE)."""
import json
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
import pytest

from app.main import app

client = TestClient(app)


def test_health_endpoint():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_voice_transcribe_endpoint():
    with patch("app.routers.voice.voice_service.transcribe") as mock_transcribe:
        mock_transcribe.return_value = "Transcribed speech text"

        file_content = b"fake audio wav data"
        resp = client.post(
            "/api/voice/transcribe",
            files={"file": ("test.wav", file_content, "audio/wav")},
        )
        assert resp.status_code == 200
        assert resp.json() == {"text": "Transcribed speech text"}


def test_voice_synthesize_endpoint():
    with patch("app.routers.voice.voice_service.synthesize") as mock_synth:
        mock_synth.return_value = b"WAVE_AUDIO_BYTES"

        resp = client.post(
            "/api/voice/synthesize",
            json={"text": "Synthesize this text", "voice": "en-US"},
        )
        assert resp.status_code == 200
        assert resp.content == b"WAVE_AUDIO_BYTES"
        assert resp.headers["content-type"] == "audio/wav"


def test_mcp_connections_crud_endpoints():
    with patch("app.routers.mcp.mcp_client_service.register_server_async") as mock_reg, \
         patch("app.routers.mcp.mcp_client_service.list_connections") as mock_list, \
         patch("app.routers.mcp.mcp_client_service.remove_connection") as mock_del:

        mock_reg.return_value = {
            "id": "mcp-test-1",
            "name": "test_mcp",
            "endpoint_url": "http://localhost:8000/mcp/sse",
            "transport": "sse",
            "scope": "workspace",
            "tools": [{"name": "tool1", "description": "desc"}],
        }
        mock_list.return_value = [
            {
                "id": "mcp-test-1",
                "name": "test_mcp",
                "endpoint_url": "http://localhost:8000/mcp/sse",
                "transport": "sse",
                "scope": "workspace",
                "tools": [{"name": "tool1", "description": "desc"}],
            }
        ]
        mock_del.return_value = True

        # POST /api/mcp/connections
        resp = client.post(
            "/api/mcp/connections",
            json={
                "name": "test_mcp",
                "endpoint_url": "http://localhost:8000/mcp/sse",
                "transport": "sse",
                "scope": "workspace",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "mcp-test-1"

        # GET /api/mcp/connections
        resp = client.get("/api/mcp/connections")
        assert resp.status_code == 200
        conns = resp.json()
        assert len(conns) == 1
        assert conns[0]["name"] == "test_mcp"

        # DELETE /api/mcp/connections/{id}
        resp = client.delete("/api/mcp/connections/mcp-test-1")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"


def test_conversations_crud_endpoints():
    with patch("app.routers.conversations.supabase_service.list_conversations") as mock_list, \
         patch("app.routers.conversations.supabase_service.create_conversation") as mock_create, \
         patch("app.routers.conversations.supabase_service.get_conversation") as mock_get, \
         patch("app.routers.conversations.supabase_service.update_conversation") as mock_update:

        mock_create.return_value = {
            "id": "conv-1",
            "title": "My Chat",
            "archived": False,
            "metadata": {},
        }
        mock_list.return_value = [
            {"id": "conv-1", "title": "My Chat", "archived": False}
        ]
        mock_get.return_value = {"id": "conv-1", "title": "My Chat", "archived": False}
        mock_update.return_value = {"id": "conv-1", "title": "Renamed Chat", "archived": True}

        # POST /api/conversations
        resp = client.post("/api/conversations", json={"title": "My Chat"})
        assert resp.status_code == 200
        assert resp.json()["id"] == "conv-1"

        # GET /api/conversations
        resp = client.get("/api/conversations")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

        # GET /api/conversations/{id}
        resp = client.get("/api/conversations/conv-1")
        assert resp.status_code == 200
        assert resp.json()["title"] == "My Chat"

        # PATCH /api/conversations/{id}
        resp = client.patch("/api/conversations/conv-1", json={"title": "Renamed Chat", "archived": True})
        assert resp.status_code == 200
        assert resp.json()["title"] == "Renamed Chat"
        assert resp.json()["archived"] is True


def test_chat_sse_image_result():
    with patch("app.main.crag_graph.invoke") as mock_invoke:
        mock_invoke.return_value = {
            "query": "Draw a sunset",
            "route": "image_gen",
            "image_result": {
                "image_b64": "fake_sunset_b64",
                "prompt": "Draw a sunset",
                "refined_prompt": "A beautiful golden sunset over the calm ocean",
            },
            "source_docs": [],
            "stream": None,
        }

        resp = client.post(
            "/api/chat",
            json={"query": "Draw a sunset"},
        )
        assert resp.status_code == 200
        content = resp.text
        assert "image_result" in content
        assert "fake_sunset_b64" in content
        assert "[DONE]" in content


def test_chat_sse_web_search_result():
    with patch("app.main.crag_graph.invoke") as mock_invoke:
        mock_invoke.return_value = {
            "query": "Search online for news",
            "route": "web_search",
            "web_results": [
                {
                    "title": "Breaking Tech News",
                    "url": "https://news.example.com",
                    "content": "AI systems update",
                    "score": 0.95,
                }
            ],
            "source_docs": [
                {
                    "chunk_id": "web-1",
                    "text_repr": "AI systems update",
                    "url": "https://news.example.com",
                    "score": 0.95,
                }
            ],
            "stream": [MagicMock(content="Here is the latest tech news.")],
        }

        resp = client.post(
            "/api/chat",
            json={"query": "Search online for news"},
        )
        assert resp.status_code == 200
        content = resp.text
        assert "web_results" in content
        assert "Breaking Tech News" in content
        assert "Here is the latest tech news." in content
        assert "[DONE]" in content

