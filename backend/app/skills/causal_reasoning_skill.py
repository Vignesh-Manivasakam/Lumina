"""Deep Causal Reasoning & Hypothesis Testing skill for root cause investigation and driver analysis."""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from app.services.llm_client import LLMClient
from app.skills.skill_registry import Skill

logger = logging.getLogger(__name__)


class DeepCausalReasoningSkill(Skill):
    """Structured causal hypothesis testing, confound evaluation, and root-cause analysis."""

    SYSTEM_PROMPT = """You are a Principal Systems Diagnostician and Empirical Causal Inference specialist.
Investigate the causal question using rigorous hypothesis testing and evidence synthesis.

Reasoning Protocol:
1. **Effect Deconstruction**: Pin down the metric, magnitude, timeframe, affected segment, and baseline.
2. **Divergent Hypothesis Space**: Formulate candidate explanations across (a) internal releases/config changes, (b) infrastructure/bug incidents, (c) external/market factors, and (d) measurement/data pipeline artifacts.
3. **Causal Heuristics & Verification**:
   - Temporal Precedence (Did cause precede effect?)
   - Mechanism Plausibility (Direct verifiable pathway)
   - Magnitude & Dose-Response Match
   - Confound & Alternative Explanation Checks
4. **Hypothesis Ranking & Confidence**:
   - Status: Confirmed / Likely / Possible / Unlikely / Ruled Out

Output Format:
# Causal Analysis Report

## Executive Answer
(1 short paragraph with calibrated status and best-supported explanation)

## Hypothesis Ranking Table
| # | Hypothesis | Status | Key Supporting Evidence | Key Disconfirming Factors Checked |

## Detailed Causal Pathways & Confounds
For top candidate hypotheses, detail the mechanism, temporal checks, and confound analysis.

## Residual Uncertainty & Recommended Next Checks
State open questions and data sources required to confirm inconclusive hypotheses."""

    def __init__(self, llm_client: Optional[LLMClient] = None) -> None:
        self.llm = llm_client or LLMClient(task="generator")

    @property
    def name(self) -> str:
        return "causal_reasoning"

    @property
    def description(self) -> str:
        return "Investigates root causes, metric anomalies, and post-mortems using empirical causal inference and hypothesis testing."

    @property
    def category(self) -> str:
        return "analytical-reasoning"

    @property
    def tags(self) -> List[str]:
        return [
            "causal",
            "root-cause",
            "hypothesis",
            "why",
            "anomaly",
            "post-mortem",
            "driver-analysis",
            "5-whys",
            "investigation",
            "incident",
        ]

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "The causal question or anomaly to investigate"},
                "scope": {"type": "object", "description": "Time range, affected systems, or metric definitions"},
                "confidence_threshold": {"type": "string", "enum": ["low", "medium", "high"], "default": "low"},
            },
            "required": ["question"],
        }

    def can_handle(self, state: dict) -> bool:
        route = state.get("route", "")
        return route in ("causal_reasoning", "deep-causal-reasoning")

    def execute(self, state: dict) -> dict:
        query = state.get("query", "")
        thinking_emitter = state.get("thinking_emitter")

        if thinking_emitter:
            thinking_emitter("skill_executor", "Formulating divergent causal hypothesis space & testing confounds...")

        try:
            response = self.llm.generate_text([
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": f"Investigate causal drivers for: {query}"},
            ], max_tokens=1600, temperature=0.1)

            analysis_text = response.content.strip()
            chunk_id = f"causal_{uuid.uuid4().hex[:8]}"

            doc = {
                "chunk_id": chunk_id,
                "id": chunk_id,
                "modality": "text",
                "text_repr": f"### Deep Causal Investigation:\n\n{analysis_text}",
                "title": "Empirical Causal Analysis",
                "score": 1.0,
                "relevance_score": 1.0,
                "rerank_score": 1.0,
                "source": "deep_causal_reasoning",
            }

            state["retrieved_docs"] = [doc]
            state["relevant_docs"] = [doc]
            state["source_docs"] = [doc]
            state["is_sufficient"] = True

            if thinking_emitter:
                thinking_emitter("skill_executor", "Causal hypothesis evaluation and confound checks complete.")

        except Exception as exc:
            logger.warning("DeepCausalReasoningSkill execution failed: %s", exc)

        return state


__all__ = ["DeepCausalReasoningSkill"]
