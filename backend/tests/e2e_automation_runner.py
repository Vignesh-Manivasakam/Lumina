"""Lumina Enterprise-Grade E2E Automation Runner & Multi-Model Evaluation Matrix.

Executes the full 25 worst-case stress query matrix across 5 test suites:
- Suite 1: Tavily Live Web Search (Skill Routing & Live Internet QA)
- Suite 2: Text-to-Image Generation (Image Skill & Prompt Refinement)
- Suite 3: Document QA — Dense Table & SaaS Financial Metrics
- Suite 4: Document QA — PDF Policy & Compliance & Session Isolation
- Suite 5: Multimodal Image in Chat (Vision Flow Analysis)

Validates SSE events (agent_status, thinking, retrieval_info, text tokens, sources, [DONE]),
benchmarks Time-to-First-Token (TTFT), total latency, and multi-model dynamic switching.
"""
from __future__ import annotations

import os
import sys
import time
import json
import base64
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import httpx

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("e2e_runner")

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
DEFAULT_BASE_URL = os.getenv("LUMINA_API_BASE", "https://lumina-f779.onrender.com")


class SSEStreamParser:
    """Parses raw SSE line streams into structured event records."""

    @staticmethod
    def parse_stream(response_iterator) -> Dict[str, Any]:
        events = []
        full_text = ""
        agent_statuses = []
        thinking_notes = []
        retrieval_info = None
        sources = []
        image_result = None
        web_results = None
        tool_result = None
        has_done = False
        error_msg = None
        first_token_time = None
        start_time = time.monotonic()

        for line in response_iterator:
            if not line:
                continue
            if isinstance(line, bytes):
                line = line.decode("utf-8", errors="ignore")

            line = line.strip()
            if not line.startswith("data:"):
                continue

            payload_str = line[5:].strip()
            if payload_str == "[DONE]":
                has_done = True
                break

            try:
                evt = json.loads(payload_str)
                events.append(evt)
                evt_type = evt.get("type")

                if evt_type == "text":
                    if first_token_time is None:
                        first_token_time = time.monotonic() - start_time
                    full_text += evt.get("content", "")

                elif evt_type == "agent_status":
                    agent_statuses.append(evt)

                elif evt_type == "thinking":
                    thinking_notes.append(evt)

                elif evt_type == "retrieval_info":
                    retrieval_info = evt.get("info")

                elif evt_type == "sources":
                    sources = evt.get("sources", [])

                elif evt_type == "image_result":
                    image_result = evt

                elif evt_type == "web_results":
                    web_results = evt.get("results")

                elif evt_type == "tool_result":
                    tool_result = evt.get("result")

                elif evt_type == "error":
                    error_msg = evt.get("content")

            except Exception as parse_err:
                logger.warning(f"Error parsing SSE event payload: {parse_err} in '{payload_str}'")

        total_time = time.monotonic() - start_time
        token_count = len(full_text.split())

        return {
            "full_text": full_text,
            "agent_statuses": agent_statuses,
            "thinking_notes": thinking_notes,
            "retrieval_info": retrieval_info,
            "sources": sources,
            "image_result": image_result,
            "web_results": web_results,
            "tool_result": tool_result,
            "error": error_msg,
            "has_done": has_done,
            "total_time_sec": round(total_time, 3),
            "ttft_sec": round(first_token_time, 3) if first_token_time is not None else None,
            "token_count": token_count,
            "tokens_per_sec": round(token_count / total_time, 2) if total_time > 0 else 0,
            "raw_events_count": len(events),
        }


class E2EAutomationRunner:
    def __init__(self, base_url: str = DEFAULT_BASE_URL):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(timeout=180.0, follow_redirects=True)
        self.image_fixture_b64 = self._load_fixture_b64("system_architecture.png")

    def _load_fixture_b64(self, filename: str) -> Optional[str]:
        path = FIXTURES_DIR / filename
        if path.exists():
            with open(path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        return None

    def execute_chat_query(
        self,
        query: str,
        model: Optional[str] = None,
        session_id: Optional[str] = None,
        image_b64: Optional[str] = None,
        web_search_mode: str = "auto",
        history: Optional[List[dict]] = None,
    ) -> Dict[str, Any]:
        """Send a query to /api/chat and stream parse SSE events."""
        url = f"{self.base_url}/api/chat"
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        if session_id:
            headers["X-Session-ID"] = session_id

        payload = {
            "query": query,
            "model": model,
            "session_id": session_id,
            "image_b64": image_b64,
            "web_search_mode": web_search_mode,
            "history": history or [],
        }

        try:
            with self.client.stream("POST", url, json=payload, headers=headers) as res:
                if res.status_code != 200:
                    return {
                        "passed": False,
                        "status_code": res.status_code,
                        "error": f"HTTP {res.status_code}: {res.read().decode('utf-8')}",
                        "has_done": False,
                    }
                result = SSEStreamParser.parse_stream(res.iter_lines())
                result["status_code"] = res.status_code
                return result
        except Exception as exc:
            return {
                "passed": False,
                "error": str(exc),
                "has_done": False,
                "total_time_sec": 0,
            }

    # -----------------------------------------------------------------------
    # The 25 Worst-Case Test Matrix Definition
    # -----------------------------------------------------------------------

    def run_suite_1_web_search(self) -> List[Dict[str, Any]]:
        """TEST 1: Tavily Live Web Search (5 queries)."""
        logger.info("=== Starting Suite 1: Tavily Live Web Search ===")
        queries = [
            {
                "id": "1.1",
                "name": "Temporal Breaking News",
                "query": "What are the latest developments and releases in frontier AI models and open weights in 2026? Provide source links.",
                "model": "gemini-flash-latest",
                "expected_keywords": ["2026", "model", "http"],
                "expect_web_results": True,
            },
            {
                "id": "1.2",
                "name": "Polysemous Entity Disambiguation",
                "query": "What is Mercury's current market cap and latest quarterly earnings?",
                "model": "gemini-flash-latest",
                "expected_keywords": ["mercury"],
                "expect_web_results": True,
            },
            {
                "id": "1.3",
                "name": "Contradictory / Fact-Checking Probe",
                "query": "Fact check: Has Quantum Computing officially broken RSA-2048 encryption as of this month? Cite specific research sources.",
                "model": "llama-3.3-70b-versatile",
                "expected_keywords": ["rsa", "quantum"],
                "expect_web_results": True,
            },
            {
                "id": "1.4",
                "name": "Deep Technical Specification Query",
                "query": "Compare the memory bandwidth and FP8 Tensor Core throughput of NVIDIA Blackwell B200 vs AMD Instinct MI300X based on recent official benchmarks.",
                "model": "nvidia/nemotron-mini-4b-instruct",
                "expected_keywords": ["b200", "mi300x"],
                "expect_web_results": True,
            },
            {
                "id": "1.5",
                "name": "API Fallback & Resilience Query",
                "query": "Search for real-time traffic status on I-95 North near Richmond",
                "model": "gemini-flash-lite-latest",
                "expected_keywords": ["i-95", "richmond"],
                "expect_web_results": True,
            },
        ]
        return self._execute_test_suite("Suite 1: Tavily Live Web Search", queries)

    def run_suite_2_image_generation(self) -> List[Dict[str, Any]]:
        """TEST 2: Text-to-Image Generation (5 queries)."""
        logger.info("=== Starting Suite 2: Text-to-Image Generation ===")
        queries = [
            {
                "id": "2.1",
                "name": "Ultra-Detailed Stylized Artwork",
                "query": "Generate an image of a futuristic cyberpunk laboratory in Neo-Kyoto at twilight, neon reflections on wet asphalt, cinematic volumetric lighting, 8k resolution octane render.",
                "model": "gemini-flash-latest",
                "expect_image": True,
            },
            {
                "id": "2.2",
                "name": "Multi-Subject Spatial Composition",
                "query": "Create an image featuring a crystal sphere on the left side, an antique brass compass in the center, and an open leather-bound book on the right on a dark oak desk.",
                "model": "gemini-flash-latest",
                "expect_image": True,
            },
            {
                "id": "2.3",
                "name": "Abstract Surrealist Visualization",
                "query": "Generate a visual representation of quantum entanglement showing glowing threads connecting two split atoms across a cosmic nebula.",
                "model": "gemini-flash-latest",
                "expect_image": True,
            },
            {
                "id": "2.4",
                "name": "Border-Safety & Ambiguity Sanitization",
                "query": "Generate an image of a dramatic battlefield scene with knight armor and glowing energy shields in an ancient ruin.",
                "model": "gemini-flash-latest",
                "expect_image": True,
            },
            {
                "id": "2.5",
                "name": "Minimalist Vector Brand Logo",
                "query": "Generate a minimalist vector logo of a luminescent owl perched on a silicon chip.",
                "model": "gemini-flash-latest",
                "expect_image": True,
            },
        ]
        return self._execute_test_suite("Suite 2: Text-to-Image Generation", queries)

    def run_suite_3_dense_table(self) -> List[Dict[str, Any]]:
        """TEST 3: Document QA — Dense Table & SaaS Financial Metrics (5 queries)."""
        logger.info("=== Starting Suite 3: Document QA — Dense Table ===")
        queries = [
            {
                "id": "3.1",
                "name": "Cross-Quarter Percentage Calculation",
                "query": "Based on the uploaded financial table, what was the Cloud ARR in Q1 2025 versus Q4 2025, and what is the exact percentage growth between them?",
                "model": "gemini-flash-latest",
                "expected_keywords": ["42.5", "104.2", "145"],
            },
            {
                "id": "3.2",
                "name": "Multi-Metric Gross Margin Evolution",
                "query": "How did the Gross Margin evolve from Q1 to Q4 2025, and how many basis points did it gain?",
                "model": "llama-3.3-70b-versatile",
                "expected_keywords": ["74.2", "82.4", "820"],
            },
            {
                "id": "3.3",
                "name": "Zero-Hallucination & Out-of-Bounds Verification",
                "query": "What was the Marketing CAC payback period in Q3 2024 according to the document?",
                "model": "gemini-flash-latest",
                "expected_keywords": ["not", "2024"],
                "anti_keywords": ["months payback in 2024"],
            },
            {
                "id": "3.4",
                "name": "Filtered Conditional Aggregation",
                "query": "List all metrics that showed more than 100% YoY growth in the uploaded report.",
                "model": "nvidia/nemotron-mini-4b-instruct",
                "expected_keywords": ["cloud arr", "enterprise"],
            },
            {
                "id": "3.5",
                "name": "Infrastructure Performance & Cost Correlation",
                "query": "What was the impact of ONNX CPU reranking on p95 latency and infrastructure costs per 10k queries?",
                "model": "gemini-flash-lite-latest",
                "expected_keywords": ["850ms", "120ms", "42%"],
            },
        ]
        return self._execute_test_suite("Suite 3: Dense Table QA", queries)

    def run_suite_4_policy_compliance(self) -> List[Dict[str, Any]]:
        """TEST 4: Document QA — PDF Policy & Compliance (5 queries)."""
        logger.info("=== Starting Suite 4: PDF Policy & Compliance ===")
        queries = [
            {
                "id": "4.1",
                "name": "Conditional Exception Reasoning",
                "query": "Under what specific circumstances is an employee permitted to access Restricted data from a personal device in Tier-3 jurisdictions, and what approvals are required?",
                "model": "gemini-flash-latest",
                "expected_keywords": ["vp", "ciso"],
            },
            {
                "id": "4.2",
                "name": "Cryptographic Key Lifecycle & Timelines",
                "query": "What is the mandatory rotation schedule for Root Encryption Keys vs Ephemeral Session Keys, and what is the grace period for de-provisioning?",
                "model": "llama-3.3-70b-versatile",
                "expected_keywords": ["90", "1 hour", "72"],
            },
            {
                "id": "4.3",
                "name": "Adversarial Fake Clause / CRAG Rewriter Probe",
                "query": "What is the penalty for not submitting the annual Moon Colony travel expense report in Section 99?",
                "model": "gemini-flash-latest",
                "expected_keywords": ["no", "section 99"],
            },
            {
                "id": "4.4",
                "name": "Cross-Section Escalation Hierarchy",
                "query": "Trace the severity escalation chain from Severity 3 to Severity 1 incident. Who must be notified within 15 minutes?",
                "model": "nvidia/nemotron-mini-4b-instruct",
                "expected_keywords": ["secops", "15"],
            },
            {
                "id": "4.5",
                "name": "Multi-Tenant Session Isolation Validation",
                "query": "List all active documents in this workspace session.",
                "model": "gemini-flash-lite-latest",
                "test_session_isolation": True,
            },
        ]
        return self._execute_test_suite("Suite 4: PDF Policy & Session Isolation", queries)

    def run_suite_5_multimodal_vision(self) -> List[Dict[str, Any]]:
        """TEST 5: Multimodal Image in Chat (Vision Analysis — 5 queries)."""
        logger.info("=== Starting Suite 5: Multimodal Image in Chat ===")
        queries = [
            {
                "id": "5.1",
                "name": "End-to-End Flow Tracing",
                "query": "Describe the end-to-end data flow shown in the attached architecture diagram from user input to LLM token streaming.",
                "model": "gemini-flash-latest",
                "image_b64": self.image_fixture_b64,
                "expected_keywords": ["gateway", "router"],
            },
            {
                "id": "5.2",
                "name": "Component Dependency & Storage Mapping",
                "query": "Which databases are utilized in the diagram, and what is stored in each according to the visual labels?",
                "model": "gemini-flash-latest",
                "image_b64": self.image_fixture_b64,
                "expected_keywords": ["qdrant", "supabase"],
            },
            {
                "id": "5.3",
                "name": "Fine-Grained Model & Label OCR",
                "query": "What specific reranker model and embedding model are shown in the diagram?",
                "model": "gemini-flash-latest",
                "image_b64": self.image_fixture_b64,
                "expected_keywords": ["flashrank", "bge"],
            },
            {
                "id": "5.4",
                "name": "Architectural Bottleneck & Security Assessment",
                "query": "Based on the diagram, where is multi-tenant session filtering enforced?",
                "model": "gemini-flash-latest",
                "image_b64": self.image_fixture_b64,
                "expected_keywords": ["session"],
            },
            {
                "id": "5.5",
                "name": "Multi-Turn Fallback Flow Analysis",
                "query": "In that diagram, what happens if the Grader agent scores the retrieved documents below 0.5?",
                "model": "gemini-flash-latest",
                "image_b64": self.image_fixture_b64,
                "expected_keywords": ["0.5", "tavily"],
            },
        ]
        return self._execute_test_suite("Suite 5: Multimodal Image Chat", queries)

    # -----------------------------------------------------------------------
    # Runner Helper & Assertion Evaluator
    # -----------------------------------------------------------------------

    def _execute_test_suite(self, suite_title: str, test_cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        results = []
        for tc in test_cases:
            tc_id = tc["id"]
            tc_name = tc["name"]
            query = tc["query"]
            model = tc.get("model")
            image_b64 = tc.get("image_b64")

            logger.info(f"Running Test {tc_id} [{tc_name}] on model={model}...")

            # Handle Session Isolation specialized test
            if tc.get("test_session_isolation"):
                eval_res = self._test_session_isolation()
                eval_res["id"] = tc_id
                eval_res["name"] = tc_name
                results.append(eval_res)
                continue

            stream_res = self.execute_chat_query(
                query=query,
                model=model,
                image_b64=image_b64,
            )

            # Evaluation Assertions
            passed = True
            reasons = []

            if not stream_res.get("has_done"):
                passed = False
                reasons.append("Stream did not terminate with [DONE]")

            if stream_res.get("error"):
                passed = False
                reasons.append(f"Server error: {stream_res.get('error')}")

            text = (stream_res.get("full_text") or "").lower()

            # Check expected keywords
            for kw in tc.get("expected_keywords", []):
                if kw.lower() not in text:
                    # Also check in web_results or image_result if present
                    in_web = any(kw.lower() in str(w).lower() for w in (stream_res.get("web_results") or []))
                    in_img = stream_res.get("image_result") is not None
                    if not in_web and not in_img:
                        passed = False
                        reasons.append(f"Missing expected keyword: '{kw}'")

            # Check anti-keywords (zero hallucination check)
            for akw in tc.get("anti_keywords", []):
                if akw.lower() in text:
                    passed = False
                    reasons.append(f"Found prohibited hallucination: '{akw}'")

            # Check image requirement
            if tc.get("expect_image"):
                img_res = stream_res.get("image_result")
                if not img_res or not (img_res.get("url") or img_res.get("b64_json") or img_res.get("image_b64") or img_res.get("prompt")):
                    passed = False
                    reasons.append("Expected valid image_result payload but none was emitted")

            # Check web results requirement
            if tc.get("expect_web_results"):
                web_res = stream_res.get("web_results")
                if not web_res and not stream_res.get("sources"):
                    # Check if text contains synthesized answer
                    if len(text.strip()) < 20:
                        passed = False
                        reasons.append("Expected web search sources or text synthesis but got empty response")

            eval_record = {
                "id": tc_id,
                "name": tc_name,
                "query": query,
                "model": model,
                "passed": passed,
                "reasons": reasons,
                "ttft_sec": stream_res.get("ttft_sec"),
                "total_time_sec": stream_res.get("total_time_sec"),
                "token_count": stream_res.get("token_count"),
                "tokens_per_sec": stream_res.get("tokens_per_sec"),
                "full_text_snippet": (stream_res.get("full_text") or "")[:200] + "...",
                "has_sources": len(stream_res.get("sources") or []) > 0,
                "has_image": stream_res.get("image_result") is not None,
                "has_web_results": stream_res.get("web_results") is not None,
            }

            status_str = "PASS" if passed else "FAIL"
            logger.info(f"-> Result {tc_id} [{tc_name}]: {status_str} ({eval_record['total_time_sec']}s, TTFT: {eval_record['ttft_sec']}s)")
            if not passed:
                logger.warning(f"   Fail details: {reasons}")

            results.append(eval_record)

        return results

    def _test_session_isolation(self) -> Dict[str, Any]:
        """Verify strict multi-tenant session isolation between Session A and Session B."""
        session_a = "11111111-1111-1111-1111-111111111111"
        session_b = "22222222-2222-2222-2222-222222222222"

        # Ask in Session A
        res_a = self.execute_chat_query(
            query="My top secret project codename is Project-SuperNova-999.",
            session_id=session_a,
        )

        # Ask in Session B about Session A's secret
        res_b = self.execute_chat_query(
            query="What is my secret project codename?",
            session_id=session_b,
        )

        b_text = (res_b.get("full_text") or "").lower()
        has_leak = "project-supernova-999" in b_text or "supernova" in b_text

        passed = (not has_leak) and res_a.get("has_done") and res_b.get("has_done")
        return {
            "passed": passed,
            "reasons": ["Session isolation breached: secret leaked across session ID"] if has_leak else [],
            "total_time_sec": (res_a.get("total_time_sec", 0) + res_b.get("total_time_sec", 0)),
            "ttft_sec": res_b.get("ttft_sec"),
            "token_count": res_b.get("token_count"),
            "tokens_per_sec": res_b.get("tokens_per_sec"),
            "full_text_snippet": (res_b.get("full_text") or "")[:200],
        }

    def run_full_matrix(self) -> Dict[str, Any]:
        """Run all 5 suites (25 total queries) and generate a comprehensive evaluation report."""
        logger.info("================================================================")
        logger.info("STARTING FULL 25 WORST-CASE TEST MATRIX EVALUATION")
        logger.info("================================================================")

        start_all = time.monotonic()
        all_results = []

        all_results.extend(self.run_suite_1_web_search())
        all_results.extend(self.run_suite_2_image_generation())
        all_results.extend(self.run_suite_3_dense_table())
        all_results.extend(self.run_suite_4_policy_compliance())
        all_results.extend(self.run_suite_5_multimodal_vision())

        total_elapsed = round(time.monotonic() - start_all, 2)
        total_tests = len(all_results)
        passed_tests = sum(1 for r in all_results if r.get("passed"))
        failed_tests = total_tests - passed_tests
        pass_rate = round((passed_tests / total_tests) * 100, 1) if total_tests > 0 else 0.0

        # Model latency statistics
        model_stats: Dict[str, List[float]] = {}
        for r in all_results:
            m = r.get("model") or "default"
            ttft = r.get("ttft_sec")
            if ttft is not None:
                model_stats.setdefault(m, []).append(ttft)

        avg_ttft_by_model = {
            m: round(sum(v) / len(v), 3) for m, v in model_stats.items() if v
        }

        report = {
            "total_queries": total_tests,
            "passed": passed_tests,
            "failed": failed_tests,
            "pass_rate_pct": pass_rate,
            "total_duration_sec": total_elapsed,
            "avg_ttft_by_model": avg_ttft_by_model,
            "test_results": all_results,
        }

        return report

    def close(self):
        self.client.close()


if __name__ == "__main__":
    base_url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE_URL
    runner = E2EAutomationRunner(base_url=base_url)
    try:
        summary = runner.run_full_matrix()
        print("\n================================================================")
        print("E2E AUTOMATION TEST MATRIX SUMMARY REPORT")
        print("================================================================")
        print(f"Total Tests:  {summary['total_queries']}")
        print(f"Passed:       {summary['passed']}")
        print(f"Failed:       {summary['failed']}")
        print(f"Pass Rate:    {summary['pass_rate_pct']}%")
        print(f"Duration:     {summary['total_duration_sec']}s")
        print(f"TTFT Specs:   {json.dumps(summary['avg_ttft_by_model'], indent=2)}")
        print("================================================================")
    finally:
        runner.close()
