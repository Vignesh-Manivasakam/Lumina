"""Automated Fixture Ingestion Script for Lumina.

Uploads test fixtures (dense_table.csv, policy_document.pdf, system_architecture.png)
to /api/ingest and polls /api/ingest/{doc_id}/status until completion.
"""
from __future__ import annotations

import os
import sys
import time
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
import httpx

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("upload_fixtures")

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
DEFAULT_BASE_URL = os.getenv("LUMINA_API_BASE", "https://lumina-f779.onrender.com")

FIXTURE_CONFIGS = [
    {
        "filename": "dense_table.csv",
        "dept": "Finance",
        "mime_type": "text/csv",
    },
    {
        "filename": "policy_document.pdf",
        "dept": "Security",
        "mime_type": "application/pdf",
    },
    {
        "filename": "system_architecture.png",
        "dept": "Engineering",
        "mime_type": "image/png",
    },
]


class FixtureUploader:
    def __init__(self, base_url: str = DEFAULT_BASE_URL, session_id: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.session_id = session_id
        self.client = httpx.Client(timeout=120.0, follow_redirects=True)

    def upload_file(self, file_path: Path, dept: str, mime_type: str) -> Optional[str]:
        """Upload a file to /api/ingest and return the doc_id."""
        if not file_path.exists():
            logger.error(f"Fixture not found at: {file_path}")
            return None

        url = f"{self.base_url}/api/ingest"
        headers = {}
        if self.session_id:
            headers["X-Session-ID"] = self.session_id

        logger.info(f"Uploading {file_path.name} (dept={dept}) to {url}...")
        with open(file_path, "rb") as f:
            files = {"file": (file_path.name, f, mime_type)}
            data = {"dept": dept}
            try:
                res = self.client.post(url, files=files, data=data, headers=headers)
                if res.status_code == 200:
                    payload = res.json()
                    doc_id = payload.get("doc_id")
                    logger.info(f"Upload successful: doc_id={doc_id}, initial status={payload.get('status')}")
                    return doc_id
                else:
                    logger.error(f"Upload failed: HTTP {res.status_code} - {res.text}")
                    return None
            except Exception as exc:
                logger.error(f"Exception during upload of {file_path.name}: {exc}")
                return None

    def poll_status(self, doc_id: str, max_wait_sec: int = 120, poll_interval: float = 2.0) -> bool:
        """Poll /api/ingest/{doc_id}/status until 'completed' or timeout."""
        url = f"{self.base_url}/api/ingest/{doc_id}/status"
        headers = {}
        if self.session_id:
            headers["X-Session-ID"] = self.session_id

        start_time = time.monotonic()
        while time.monotonic() - start_time < max_wait_sec:
            try:
                res = self.client.get(url, headers=headers)
                if res.status_code == 200:
                    status_info = res.json()
                    status = status_info.get("status")
                    logger.info(f"Doc {doc_id} status: {status}")
                    if status in ("completed", "ready"):
                        return True
                    if status == "failed":
                        logger.error(f"Doc {doc_id} processing failed on server.")
                        return False
                else:
                    logger.warning(f"Poll returned status {res.status_code}: {res.text}")
            except Exception as exc:
                logger.warning(f"Polling error for doc {doc_id}: {exc}")

            time.sleep(poll_interval)

        logger.error(f"Timeout waiting for doc {doc_id} to complete ({max_wait_sec}s).")
        return False

    def ingest_all_fixtures(self) -> Dict[str, Any]:
        """Ingest all predefined fixtures and return results."""
        results = {}
        for cfg in FIXTURE_CONFIGS:
            file_path = FIXTURES_DIR / cfg["filename"]
            doc_id = self.upload_file(file_path, cfg["dept"], cfg["mime_type"])
            if not doc_id:
                results[cfg["filename"]] = {"success": False, "error": "upload_failed"}
                continue

            success = self.poll_status(doc_id)
            results[cfg["filename"]] = {
                "doc_id": doc_id,
                "dept": cfg["dept"],
                "success": success,
            }

        # Verify documents list
        try:
            docs_res = self.client.get(f"{self.base_url}/api/documents")
            if docs_res.status_code == 200:
                results["all_documents"] = docs_res.json()
        except Exception as exc:
            results["all_documents_error"] = str(exc)

        return results

    def close(self):
        self.client.close()


if __name__ == "__main__":
    base_url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE_URL
    uploader = FixtureUploader(base_url=base_url)
    try:
        report = uploader.ingest_all_fixtures()
        print("\n=== Ingestion Summary ===")
        print(json.dumps(report, indent=2))
    finally:
        uploader.close()
