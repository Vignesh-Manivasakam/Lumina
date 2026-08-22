"""Data extraction skill for structured JSON/Entity extraction from unstructured documents."""
from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any, Dict, List, Optional

from app.services.llm_client import LLMClient
from app.skills.skill_registry import Skill

logger = logging.getLogger(__name__)


class DataExtractionSkill(Skill):
    """Parses unstructured text, financial figures, dates, and tables into strictly formatted JSON."""

    EXTRACTION_PROMPT = """Extract all key entities, facts, numerical metrics, dates, and tabular records from the input text into a clean JSON structure.

Return ONLY a JSON object with:
{{
  "entities": [{{"name": "<entity>", "category": "<type>", "attribute": "<value>"}}],
  "metrics": [{{"metric_name": "<name>", "value": "<val>", "unit": "<unit>", "period": "<time>"}}],
  "timeline_events": [{{"date": "<date>", "event": "<description>"}}],
  "key_parameters": {{}}
}}

Text to parse:
{query}"""

    def __init__(self, llm_client: Optional[LLMClient] = None) -> None:
        self.llm = llm_client or LLMClient(task="generator")

    @property
    def name(self) -> str:
        return "data_extraction"

    @property
    def description(self) -> str:
        return "Extracts structured JSON entities, financial metrics, dates, and parameters from raw text."

    @property
    def category(self) -> str:
        return "analysis"

    @property
    def tags(self) -> List[str]:
        return ["extract", "json", "entities", "metrics", "financials", "table", "schema", "parse"]

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Raw text or document to extract structured data from"}
            },
            "required": ["text"],
        }

    def can_handle(self, state: dict) -> bool:
        return state.get("route") == "data_extraction"

    def execute(self, state: dict) -> dict:
        query = state.get("query", "")
        thinking_emitter = state.get("thinking_emitter")

        if thinking_emitter:
            thinking_emitter("skill_executor", "Extracting structured JSON entities and metrics...")

        try:
            prompt = self.EXTRACTION_PROMPT.format(query=query)
            response = self.llm.generate_text([
                {"role": "system", "content": "You are a Structured Data Extraction & Schema Specialist."},
                {"role": "user", "content": prompt},
            ], max_tokens=1200, temperature=0.0)

            content = response.content.strip()
            if "```" in content:
                match = re.search(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL)
                if match:
                    content = match.group(1).strip()

            chunk_id = f"extract_{uuid.uuid4().hex[:8]}"
            doc = {
                "chunk_id": chunk_id,
                "id": chunk_id,
                "modality": "text",
                "text_repr": f"### Extracted Structured Schema:\n\n```json\n{content}\n```",
                "title": "Structured Data Extraction",
                "score": 1.0,
                "relevance_score": 1.0,
                "rerank_score": 1.0,
                "source": "data_extraction",
            }

            state["retrieved_docs"] = [doc]
            state["relevant_docs"] = [doc]
            state["source_docs"] = [doc]
            state["is_sufficient"] = True

            if thinking_emitter:
                thinking_emitter("skill_executor", "Structured schema extracted successfully.")

        except Exception as exc:
            logger.warning("DataExtractionSkill execution failed: %s", exc)

        return state


__all__ = ["DataExtractionSkill"]
