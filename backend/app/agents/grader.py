"""Relevance grader agent with batch document evaluation.

Evaluates retrieved document passages against the user query in a single
batched LLM prompt to minimize latency and token usage. Automatically
falls back to individual document grading if batch parsing fails.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Literal, Optional

from app.config import settings
from app.services.llm_client import LLMClient

logger = logging.getLogger(__name__)

SINGLE_GRADER_PROMPT = """You are a relevance grader for an enterprise RAG system.
Given a query and a retrieved document passage, score the relevance as exactly one of: "correct", "ambiguous", or "incorrect".

Score guide:
- correct = Directly answers the query or has highly relevant information.
- ambiguous = Partially answers, has related information, or might be relevant but needs more context.
- incorrect = Irrelevant or tangentially related.

Return ONLY a JSON: {"score": "<correct|ambiguous|incorrect>", "reason": "<one sentence>"}"""

BATCH_GRADER_PROMPT = """You are a relevance grader for an enterprise RAG system.
Given a query and a list of numbered retrieved document passages, score the relevance of each document as exactly one of: "correct", "ambiguous", or "incorrect".

Score guide:
- correct = Directly answers the query or has highly relevant information.
- ambiguous = Partially answers, has related information, or might be relevant but needs more context.
- incorrect = Irrelevant or tangentially related.

Return ONLY a JSON array of objects: [{"doc_index": <int>, "score": "<correct|ambiguous|incorrect>", "reason": "<one sentence>"}, ...]
Do not include any explanation or markdown preamble outside the JSON array."""


class GraderAgent:
    """Grader agent evaluating document relevance in batch with fallback."""

    def __init__(self, llm_client: Optional[Any] = None) -> None:
        self.llm = llm_client or LLMClient(task="grader")
        # Back-compat alias for code paths that still read .nvidia
        self.nvidia = self.llm

    def _grade_single_doc(self, query: str, doc: dict) -> float:
        """Fallback method: grade a single document individually."""
        messages = [
            {"role": "system", "content": SINGLE_GRADER_PROMPT},
            {"role": "user", "content": f"Query: {query}\n\nDocument: {doc.get('text_repr', '')[:800]}"},
        ]
        try:
            resp = self.llm.generate_text(messages)
            content = resp.content.strip()

            if "```" in content:
                match = re.search(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL)
                if match:
                    content = match.group(1).strip()

            try:
                result = json.loads(content)
                if isinstance(result, dict):
                    val = result.get("score", 0.7)
                elif isinstance(result, list) and result:
                    val = result[0].get("score", 0.7) if isinstance(result[0], dict) else result[0]
                else:
                    val = result
                try:
                    return float(val)
                except (ValueError, TypeError):
                    s_str = str(val).lower()
                    if "correct" in s_str:
                        return 1.0
                    elif "ambiguous" in s_str:
                        return 0.7
                    return 0.1
            except Exception:
                score_match = re.search(r'"score"\s*:\s*([0-9.]+)', content)
                if score_match:
                    return float(score_match.group(1))
                try:
                    return float(content)
                except ValueError:
                    return 0.7
        except Exception as exc:
            logger.warning(
                "Error grading individual document: %s. Defaulting score to 0.7.",
                exc,
            )
            return 0.7

    def _grade_batch_docs(self, query: str, docs: List[dict]) -> Dict[int, str]:
        """Grade all retrieved documents in a single LLM prompt."""
        doc_sections: List[str] = []
        for i, doc in enumerate(docs):
            passage = (doc.get("text_repr") or "")[:800]
            doc_sections.append(f"[Document {i}]\n{passage}")

        docs_formatted = "\n\n".join(doc_sections)
        prompt = f"Query: {query}\n\nDocuments to grade:\n{docs_formatted}\n\nJSON Array:"

        resp = self.llm.generate_text(
            [
                {"role": "system", "content": BATCH_GRADER_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=64 * len(docs) + 128,
            temperature=0.0,
        )
        content = resp.content.strip()

        if "```" in content:
            match = re.search(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL)
            if match:
                content = match.group(1).strip()

        scores: Dict[int, float] = {}
        try:
            parsed = json.loads(content)
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict):
                        idx = item.get("doc_index") if "doc_index" in item else item.get("index")
                        score_val = item.get("score")
                        if idx is not None and score_val is not None:
                            try:
                                scores[int(idx)] = float(score_val)
                            except (ValueError, TypeError):
                                s_str = str(score_val).lower()
                                if "correct" in s_str:
                                    scores[int(idx)] = 1.0
                                elif "ambiguous" in s_str:
                                    scores[int(idx)] = 0.7
                                else:
                                    scores[int(idx)] = 0.1
            elif isinstance(parsed, dict) and "score" in parsed and len(docs) == 1:
                score_val = parsed["score"]
                try:
                    scores[0] = float(score_val)
                except (ValueError, TypeError):
                    scores[0] = 0.7
        except Exception:
            # Fallback regex extraction of doc_index and score
            matches = re.findall(
                r'\{\s*"(?:doc_)?index"\s*:\s*(\d+)\s*,\s*"score"\s*:\s*([0-9.]+)',
                content,
            )
            for idx_str, score_str in matches:
                scores[int(idx_str)] = float(score_str)

        return scores

    def _log_decisions(self, query: str, docs: List[dict]) -> None:
        try:
            import os, datetime
            log_dir = getattr(settings, "GRADER_LOG_DIR", "grader_logs")
            os.makedirs(log_dir, exist_ok=True)
            log_path = os.path.join(log_dir, "decisions.jsonl")
            with open(log_path, "a") as f:
                log_entry = {
                    "timestamp": datetime.datetime.utcnow().isoformat(),
                    "query": query,
                    "decisions": [{"id": d.get("id", ""), "grade": d.get("relevance_score", "unknown")} for d in docs]
                }
                f.write(json.dumps(log_entry) + "\n")
        except Exception as exc:
            logger.error("Failed to log grader decisions: %s", exc)

    def grade(self, state: dict) -> dict:
        """Score retrieved documents against query and filter relevant ones."""
        query = state["query"]
        docs = state.get("retrieved_docs", [])

        if not docs:
            state["relevant_docs"] = []
            state["is_sufficient"] = False
            state["thinking_note"] = "No documents retrieved to grade."
            return state

        batch_scores: Dict[int, float] = {}
        try:
            batch_scores = self._grade_batch_docs(query, docs)
        except Exception as exc:
            logger.warning(
                "Batch grading failed: %s; falling back to individual grading",
                exc,
            )
            batch_scores = {}

        scored_docs: List[dict] = []
        for i, doc in enumerate(docs):
            if i in batch_scores:
                score = batch_scores[i]
            else:
                score = self._grade_single_doc(query, doc)

            doc["relevance_score"] = score
            if doc["relevance_score"] >= settings.RELEVANCE_THRESHOLD:
                scored_docs.append(doc)

        self._log_decisions(query, docs)

        state["relevant_docs"] = scored_docs
        state["is_sufficient"] = len(scored_docs) >= 2
        decision = (
            "Sufficient context — proceeding to generation."
            if state["is_sufficient"]
            else "Context insufficient — will rewrite and re-retrieve."
        )
        state["thinking_note"] = (
            f"Graded {len(scored_docs)} of {len(docs)} docs as relevant "
            f"(threshold {settings.RELEVANCE_THRESHOLD}). {decision}"
        )
        return state

    def should_rewrite(self, state: dict) -> Literal["rewrite", "generate"]:
        """LangGraph conditional edge to decide next state node."""
        if state.get("route") == "multimodal":
            return "generate"

        if state.get("is_sufficient"):
            return "generate"

        # If we exceeded the max retrievals limit, stop looping and generate
        if state.get("retrieval_count", 0) >= settings.MAX_RETRIEVAL_RETRIES:
            if "relevant_docs" not in state or not state["relevant_docs"]:
                state["relevant_docs"] = state.get("retrieved_docs", [])[:2]
            return "generate"

        return "rewrite"

