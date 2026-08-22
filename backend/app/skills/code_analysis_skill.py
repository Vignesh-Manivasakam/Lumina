"""Code analysis & review skill for automated bug detection, architecture auditing, and refactoring."""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from app.services.llm_client import LLMClient
from app.skills.skill_registry import Skill

logger = logging.getLogger(__name__)


class CodeAnalysisSkill(Skill):
    """Audits code snippets for syntax errors, anti-patterns, security flaws, and performance bottlenecks."""

    ANALYSIS_PROMPT = """Perform an in-depth code review on the provided code:
1. Syntax & Logic Correctness (Identify runtime errors, off-by-one bugs, race conditions)
2. Time & Space Complexity (Big-O analysis)
3. Security Audit (Injection risks, unvalidated inputs, resource leaks)
4. Idiomatic Refactoring & Clean Production Code

Code to review:
{query}"""

    def __init__(self, llm_client: Optional[LLMClient] = None) -> None:
        self.llm = llm_client or LLMClient(task="generator")

    @property
    def name(self) -> str:
        return "code_analysis"

    @property
    def description(self) -> str:
        return "Reviews source code for security vulnerabilities, performance bottlenecks, and provides refactored implementations."

    @property
    def category(self) -> str:
        return "coding"

    @property
    def tags(self) -> List[str]:
        return ["code", "review", "refactor", "bug", "audit", "security", "complexity", "python", "typescript", "clean code"]

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Source code snippet or file to analyze"}
            },
            "required": ["code"],
        }

    def can_handle(self, state: dict) -> bool:
        return state.get("route") == "code_analysis"

    def execute(self, state: dict) -> dict:
        query = state.get("query", "")
        thinking_emitter = state.get("thinking_emitter")

        if thinking_emitter:
            thinking_emitter("skill_executor", "Performing code architecture & vulnerability review...")

        try:
            prompt = self.ANALYSIS_PROMPT.format(query=query)
            response = self.llm.generate_text([
                {"role": "system", "content": "You are a Principal Software Architect and Security Auditor."},
                {"role": "user", "content": prompt},
            ], max_tokens=1500, temperature=0.1)

            analysis_text = response.content.strip()
            chunk_id = f"code_{uuid.uuid4().hex[:8]}"

            doc = {
                "chunk_id": chunk_id,
                "id": chunk_id,
                "modality": "text",
                "text_repr": f"### Code Review & Optimization Report:\n\n{analysis_text}",
                "title": "Automated Code Analysis",
                "score": 1.0,
                "relevance_score": 1.0,
                "rerank_score": 1.0,
                "source": "code_analysis",
            }

            state["retrieved_docs"] = [doc]
            state["relevant_docs"] = [doc]
            state["source_docs"] = [doc]
            state["is_sufficient"] = True

            if thinking_emitter:
                thinking_emitter("skill_executor", "Code review completed with architectural recommendations.")

        except Exception as exc:
            logger.warning("CodeAnalysisSkill execution failed: %s", exc)

        return state


__all__ = ["CodeAnalysisSkill"]
