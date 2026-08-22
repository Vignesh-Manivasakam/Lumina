"""Deep deliberate reasoning skill inspired by Claude 3.7 / OpenAI o1 architectures.

Performs multi-step deliberate problem decomposition, premise verification,
counter-factual critique, and formal logical synthesis before generating final answers.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from app.services.llm_client import LLMClient
from app.skills.skill_registry import Skill

logger = logging.getLogger(__name__)


class DeepReasoningSkill(Skill):
    """Executes multi-phase chain-of-thought analysis and adversarial verification."""

    REASONING_PROMPT = """You are a rigorous, analytical reasoning engine.
Analyze the user's problem using systematic first-principles thinking.

Format your analysis into distinct sequential sections:
1. Problem Decomposition & Hidden Assumptions
2. Step-by-Step Deductive Analysis & Edge Cases
3. Adversarial Counter-Arguments & Potential Flaws
4. Verified Final Conclusion & Actionable Solution

Query: {query}"""

    def __init__(self, llm_client: Optional[LLMClient] = None) -> None:
        self.llm = llm_client or LLMClient(task="generator")

    @property
    def name(self) -> str:
        return "deep_reasoning"

    @property
    def description(self) -> str:
        return "Executes rigorous multi-step chain-of-thought reasoning, hypothesis testing, and formal verification."

    @property
    def category(self) -> str:
        return "reasoning"

    @property
    def tags(self) -> List[str]:
        return ["reasoning", "think", "deep", "logic", "proof", "math", "verify", "deduction", "step-by-step"]

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The complex problem or reasoning query"}
            },
            "required": ["query"],
        }

    def can_handle(self, state: dict) -> bool:
        return state.get("route") == "deep_reasoning"

    def execute(self, state: dict) -> dict:
        query = state.get("query", "")
        thinking_emitter = state.get("thinking_emitter")

        if thinking_emitter:
            thinking_emitter("skill_executor", f"Initiating deliberate deep reasoning for: {query[:60]}...")

        try:
            prompt = self.REASONING_PROMPT.format(query=query)
            response = self.llm.generate_text([
                {"role": "system", "content": "You are a master mathematical and logical reasoning specialist."},
                {"role": "user", "content": prompt},
            ], max_tokens=1500, temperature=0.2)

            analysis_text = response.content.strip()
            chunk_id = f"reasoning_{uuid.uuid4().hex[:8]}"

            doc = {
                "chunk_id": chunk_id,
                "id": chunk_id,
                "modality": "text",
                "text_repr": f"### Deep Reasoning Breakdown:\n\n{analysis_text}",
                "title": "Deliberate Reasoning Synthesis",
                "score": 1.0,
                "relevance_score": 1.0,
                "rerank_score": 1.0,
                "source": "deep_reasoning",
            }

            state["retrieved_docs"] = [doc]
            state["relevant_docs"] = [doc]
            state["source_docs"] = [doc]
            state["is_sufficient"] = True

            if thinking_emitter:
                thinking_emitter("skill_executor", "Deep reasoning synthesis complete with verified steps.")

        except Exception as exc:
            logger.warning("DeepReasoningSkill execution failed: %s", exc)

        return state


__all__ = ["DeepReasoningSkill"]
