"""Summarization skill for executive briefings, meeting takeaways, and synthesis."""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from app.services.llm_client import LLMClient
from app.skills.skill_registry import Skill

logger = logging.getLogger(__name__)


class SummarizationSkill(Skill):
    """Generates structured summaries, executive briefings, and action item checklists."""

    SUMMARIZE_PROMPT = """Synthesize the provided content into a highly structured briefing:
- **Executive Summary** (2-3 sentences overview)
- **Key Takeaways & Findings** (Bulleted core points)
- **Action Items & Next Steps** (Owners, deliverables, timelines if mentioned)
- **Risks & Open Questions** (Critical factors to monitor)

Content to summarize:
{query}"""

    def __init__(self, llm_client: Optional[LLMClient] = None) -> None:
        self.llm = llm_client or LLMClient(task="generator")

    @property
    def name(self) -> str:
        return "summarization"

    @property
    def description(self) -> str:
        return "Generates executive briefings, key takeaway bullets, and action item extractions."

    @property
    def category(self) -> str:
        return "analysis"

    @property
    def tags(self) -> List[str]:
        return ["summarize", "summary", "tldr", "brief", "takeaways", "action items", "digest", "meeting notes"]

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text or document content to summarize"}
            },
            "required": ["text"],
        }

    def can_handle(self, state: dict) -> bool:
        return state.get("route") == "summarization"

    def execute(self, state: dict) -> dict:
        query = state.get("query", "")
        thinking_emitter = state.get("thinking_emitter")

        if thinking_emitter:
            thinking_emitter("skill_executor", "Distilling content into structured executive summary...")

        try:
            prompt = self.SUMMARIZE_PROMPT.format(query=query)
            response = self.llm.generate_text([
                {"role": "system", "content": "You are an Executive Chief of Staff and Strategic Analyst."},
                {"role": "user", "content": prompt},
            ], max_tokens=1000, temperature=0.1)

            summary_text = response.content.strip()
            chunk_id = f"summary_{uuid.uuid4().hex[:8]}"

            doc = {
                "chunk_id": chunk_id,
                "id": chunk_id,
                "modality": "text",
                "text_repr": f"### Executive Briefing & Synthesis:\n\n{summary_text}",
                "title": "Structured Summary",
                "score": 1.0,
                "relevance_score": 1.0,
                "rerank_score": 1.0,
                "source": "summarization",
            }

            state["retrieved_docs"] = [doc]
            state["relevant_docs"] = [doc]
            state["source_docs"] = [doc]
            state["is_sufficient"] = True

            if thinking_emitter:
                thinking_emitter("skill_executor", "Executive summary synthesized successfully.")

        except Exception as exc:
            logger.warning("SummarizationSkill execution failed: %s", exc)

        return state


__all__ = ["SummarizationSkill"]
