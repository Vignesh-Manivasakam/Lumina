"""Render Cloud Deployment Manager and Verifier for Lumina.

Uses Render REST API (v1) to query services, deploys, logs, and verify
health endpoints for lumina-frontend and lumina-backend.
"""
from __future__ import annotations

import os
import sys
import json
import logging
from typing import Any, Dict, List, Optional
import httpx

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("render_manager")

RENDER_API_KEY = os.getenv("RENDER_API_KEY", "rnd_dsf3Wg1vpynzUzZJgJFbX7GdOPVZ")
RENDER_API_BASE = "https://api.render.com/v1"
FRONTEND_URL = "https://lumina-frontend-ma7n.onrender.com"


class RenderManager:
    def __init__(self, api_key: str = RENDER_API_KEY):
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def list_services(self, limit: int = 20) -> List[Dict[str, Any]]:
        """List all services associated with the Render account."""
        url = f"{RENDER_API_BASE}/services?limit={limit}"
        try:
            with httpx.Client(timeout=15.0) as client:
                res = client.get(url, headers=self.headers)
                if res.status_code == 200:
                    data = res.json()
                    # Render returns list of {"service": {...}} or list of objects
                    services = [item.get("service", item) for item in data] if isinstance(data, list) else []
                    return services
                else:
                    logger.error(f"Failed to list services: {res.status_code} - {res.text}")
                    return []
        except Exception as exc:
            logger.error(f"Render API request error: {exc}")
            return []

    def get_service(self, service_id: str) -> Optional[Dict[str, Any]]:
        """Get details for a specific service."""
        url = f"{RENDER_API_BASE}/services/{service_id}"
        try:
            with httpx.Client(timeout=15.0) as client:
                res = client.get(url, headers=self.headers)
                if res.status_code == 200:
                    return res.json()
                return None
        except Exception as exc:
            logger.error(f"Error fetching service {service_id}: {exc}")
            return None

    def get_latest_deploys(self, service_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Get recent deployments for a service."""
        url = f"{RENDER_API_BASE}/services/{service_id}/deploys?limit={limit}"
        try:
            with httpx.Client(timeout=15.0) as client:
                res = client.get(url, headers=self.headers)
                if res.status_code == 200:
                    data = res.json()
                    return [item.get("deploy", item) for item in data] if isinstance(data, list) else []
                return []
        except Exception as exc:
            logger.error(f"Error fetching deploys for {service_id}: {exc}")
            return []

    def verify_service_health(self, url: str) -> Dict[str, Any]:
        """Check the HTTP health status of a service URL."""
        health_url = url.rstrip("/") + "/health"
        root_url = url.rstrip("/") + "/"
        result = {"target_url": url, "healthy": False, "status_code": None, "response": None}
        
        try:
            with httpx.Client(timeout=15.0, follow_redirects=True) as client:
                # Try /health first
                try:
                    res = client.get(health_url)
                    if res.status_code in (200, 204):
                        result["healthy"] = True
                        result["status_code"] = res.status_code
                        result["response"] = res.text[:200]
                        return result
                except Exception:
                    pass

                # Fallback to root URL
                res = client.get(root_url)
                result["status_code"] = res.status_code
                result["healthy"] = res.status_code in (200, 301, 302, 307, 308)
                result["response"] = res.text[:200]
        except Exception as exc:
            result["error"] = str(exc)
            
        return result

    def inspect_cluster(self) -> Dict[str, Any]:
        """Perform full inspection of the Render cluster environment."""
        services = self.list_services()
        logger.info(f"Discovered {len(services)} services on Render.")

        report = {
            "services_count": len(services),
            "services": [],
            "frontend": None,
            "backend": None,
        }

        for svc in services:
            svc_id = svc.get("id")
            svc_name = svc.get("name")
            svc_type = svc.get("type")
            svc_url = svc.get("serviceDetails", {}).get("url") or svc.get("url")
            
            deploys = self.get_latest_deploys(svc_id, limit=1) if svc_id else []
            latest_status = deploys[0].get("status") if deploys else "unknown"

            svc_info = {
                "id": svc_id,
                "name": svc_name,
                "type": svc_type,
                "url": svc_url,
                "latest_deploy_status": latest_status,
            }
            report["services"].append(svc_info)
            logger.info(f"Service: {svc_name} ({svc_type}) -> URL: {svc_url} | Deploy: {latest_status}")

            if "frontend" in (svc_name or "").lower():
                report["frontend"] = svc_info
            elif "backend" in (svc_name or "").lower():
                report["backend"] = svc_info

        # Verify Frontend Health
        fe_url = (report["frontend"] and report["frontend"].get("url")) or FRONTEND_URL
        fe_health = self.verify_service_health(fe_url)
        report["frontend_health"] = fe_health
        logger.info(f"Frontend Health ({fe_url}): {fe_health}")

        # Verify Backend Health if discovered
        if report["backend"] and report["backend"].get("url"):
            be_url = report["backend"]["url"]
            be_health = self.verify_service_health(be_url)
            report["backend_health"] = be_health
            logger.info(f"Backend Health ({be_url}): {be_health}")

        return report


if __name__ == "__main__":
    manager = RenderManager()
    inspection = manager.inspect_cluster()
    print("\n--- Render Cluster Inspection Summary ---")
    print(json.dumps(inspection, indent=2))
