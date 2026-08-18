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
Given a query and a retrieved document passage, score the relevance from 0.0 to 1.0.

Score guide:
1.0 = Directly answers the query
0.7 = Partially answers, has related information
0.4 = Tangentially related
0.0 = Irrelevant

Return ONLY a JSON: {"score": <float>, "reason": "<one sentence>"}"""

BATCH_GRADER_PROMPT = """You are a relevance grader for an enterprise RAG system.
Given a query and a list of numbered retrieved document passages, score the relevance of each document from 0.0 to 1.0.

Score guide:
1.0 = Directly answers the query
0.7 = Partially answers, has related information
0.4 = Tangentially related
0.0 = Irrelevant

Return ONLY a JSON array of objects: [{"doc_index": <int>, "score": <float>, "reason": "<one sentence>"}, ...]
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
                    return float(result.get("score", 0.0))
                elif isinstance(result, list) and result:
                    return float(result[0].get("score", 0.0))
                return float(result)
            except Exception:
                score_match = re.search(r'"score"\s*:\s*([0-9.]+)', content)
                if score_match:
                    return float(score_match.group(1))
                return float(content)
        except Exception as exc:
            logger.warning(
                "Error grading individual document: %s. Defaulting score to 0.7.",
                exc,
            )
            return 0.7

    def _grade_batch_docs(self, query: str, docs: List[dict]) -> Dict[int, float]:
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
                        score = item.get("score")
                        if idx is not None and score is not None:
                            scores[int(idx)] = float(score)
            elif isinstance(parsed, dict) and "score" in parsed and len(docs) == 1:
                scores[0] = float(parsed["score"])
        except Exception:
            # Fallback regex extraction of doc_index and score
            matches = re.findall(
                r'\{\s*"(?:doc_)?index"\s*:\s*(\d+)\s*,\s*"score"\s*:\s*([0-9.]+)',
                content,
            )
            for idx_str, score_str in matches:
                scores[int(idx_str)] = float(score_str)

        return scores

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
        # If this is a multimodal query, skip rewriting and go straight to generation
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
