import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import uuid
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.middleware.session import SessionIsolationMiddleware

app = FastAPI()
app.add_middleware(SessionIsolationMiddleware)

@app.get("/test")
def ping_endpoint():
    return {"message": "ok"}

client = TestClient(app, raise_server_exceptions=False)

def test_session_middleware_generates_uuid_when_missing():
    response = client.get("/test")
    assert response.status_code == 200
    assert "X-Session-ID" in response.headers
    session_id = response.headers["X-Session-ID"]
    # Check valid UUID
    parsed = uuid.UUID(session_id, version=4)
    assert str(parsed) == session_id

def test_session_middleware_accepts_valid_uuid():
    test_uuid = str(uuid.uuid4())
    response = client.get("/test", headers={"X-Session-ID": test_uuid})
    assert response.status_code == 200
    assert response.headers["X-Session-ID"] == test_uuid

def test_session_middleware_rejects_invalid_uuid():
    response = client.get("/test", headers={"X-Session-ID": "invalid-uuid-string"})
    assert response.status_code == 401
