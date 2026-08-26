"""Zero/Micro-Token 3-Tier Hybrid Skill Router for Lumina.

Combines:
- Tier 1: Fast Regex & Trigger Keyword Matching (0 Tokens, <1ms)
- Tier 2: Micro-LLM Intent Expansion (~25 Tokens) + Hybrid Dense (BGE) + BM25 Search
- Tier 3: Reasoning Mode Ladder Fallback (Sonnet vs Opus vs Fable)
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from app.services.llm_client import LLMClient
from app.skills.markdown_loader import MarkdownSkill, MarkdownSkillLoader, default_markdown_skill_loader

logger = logging.getLogger(__name__)

# Heuristic patterns for Tier 3 reasoning ladder classification
_COMPLEX_ANALYTICAL_RE = re.compile(
    r"\b(?:compare|trade-?offs|architecture|architectural|root cause|diagnose|adversarial|benchmark|"
    r"in-depth|evaluate|pros and cons|which is better|difference between|deep dive|step-by-step reasoning)\b",
    re.IGNORECASE,
)

_FRONTIER_NARRATIVE_RE = re.compile(
    r"\b(?:mental model|teach me|analogy|intuitive|intuitively|philosophy|first principles|"
    r"explain like I'm|story|vision|frontier|future of|conceptual framework)\b",
    re.IGNORECASE,
)


class SkillRouter:
    """Selects the optimal Markdown skill with minimal token consumption."""

    def __init__(self, loader: Optional[MarkdownSkillLoader] = None, llm_client: Optional[LLMClient] = None) -> None:
        self.loader = loader or default_markdown_skill_loader
        self.llm = llm_client or LLMClient(task="generator")

    def _tier1_match(self, query: str, skills: List[MarkdownSkill]) -> Optional[MarkdownSkill]:
        """Tier 1: Fast exact trigger/tag regex matching (0 Tokens)."""
        q_lower = query.lower().strip()

        # Check explicit @skill mentions (e.g. @opus, @contract-risk)
        for skill in skills:
            if f"@{skill.name}" in q_lower or f"@{skill.category}" in q_lower:
                logger.debug("Tier 1 matched via explicit mention: %s", skill.name)
                return skill

        # Check triggers and tags
        for skill in skills:
            for trigger in skill.triggers:
                if trigger.lower() in q_lower:
                    logger.debug("Tier 1 matched trigger '%s' -> %s", trigger, skill.name)
                    return skill

        return None

    def _tier2_hybrid_match(
        self, query: str, skills: List[MarkdownSkill], session_id: Optional[str] = None
    ) -> Optional[MarkdownSkill]:
        """Tier 2: Micro-LLM intent expansion (~25 tokens) + Hybrid Dense/Sparse matching."""
        intent_keywords = query
        try:
            # Micro-prompt: ~25 input tokens, ~8 output tokens
            resp = self.llm.generate_text(
                [
                    {
                        "role": "system",
                        "content": "Given a user query, output 3-5 core capability keywords representing the ideal AI expert skill needed (e.g., 'legal contract risk audit', 'saas financial metric model', 'code architecture review'). Output only keywords.",
                    },
                    {"role": "user", "content": query},
                ],
                max_tokens=20,
                temperature=0.0,
            )
            expanded = resp.content.strip().lower()
            if expanded:
                intent_keywords = f"{query} {expanded}"
        except Exception as exc:
            logger.warning("Micro-intent generation failed, falling back to raw query: %s", exc)

        embedder = self.loader._get_embedder()
        if not embedder:
            return None

        try:
            vecs = embedder.embed_texts([intent_keywords])
            if not vecs:
                return None
            query_vec = np.array(vecs[0], dtype=np.float32)
            norm_q = np.linalg.norm(query_vec)
            if norm_q > 0:
                query_vec = query_vec / norm_q

            best_skill: Optional[MarkdownSkill] = None
            best_score: float = 0.0

            q_tokens = set(re.findall(r"\w+", intent_keywords.lower()))

            for skill in skills:
                # 1. Dense cosine similarity
                dense_score = 0.0
                if skill.embedding is not None:
                    norm_s = np.linalg.norm(skill.embedding)
                    if norm_s > 0:
                        s_norm = skill.embedding / norm_s
                        dense_score = float(np.dot(query_vec, s_norm))

                # 2. Sparse tag overlap
                s_tokens = set(re.findall(r"\w+", f"{skill.title} {skill.description} {' '.join(skill.tags)}".lower()))
                overlap = len(q_tokens & s_tokens)
                sparse_score = min(1.0, overlap / max(1, len(s_tokens) * 0.4))

                # Hybrid score (70% dense + 30% sparse)
                hybrid_score = 0.7 * dense_score + 0.3 * sparse_score

                if hybrid_score > best_score and hybrid_score >= skill.confidence_threshold:
                    best_score = hybrid_score
                    best_skill = skill

            if best_skill:
                logger.debug("Tier 2 hybrid matched skill: %s (score: %.3f)", best_skill.name, best_score)
                return best_skill

        except Exception as exc:
            logger.warning("Tier 2 hybrid matching error: %s", exc)

        return None

    def _tier3_fallback(self, query: str, skills: List[MarkdownSkill]) -> MarkdownSkill:
        """Tier 3: Reasoning mode ladder fallback (0 Tokens)."""
        # 1. Check for frontier/narrative/mental-model indicators
        if _FRONTIER_NARRATIVE_RE.search(query):
            skill = self.loader.get_skill("fable-reasoning")
            if skill:
                return skill

        # 2. Check for complex analytical indicators or long queries (>25 words)
        if _COMPLEX_ANALYTICAL_RE.search(query) or len(query.split()) > 25:
            skill = self.loader.get_skill("opus-reasoning")
            if skill:
                return skill

        # 3. Default to Sonnet practical mode
        skill = self.loader.get_skill("sonnet-reasoning")
        if skill:
            return skill

        # Fallback to first available skill if names differed
        return skills[0] if skills else MarkdownSkill(
            name="default",
            category="general",
            title="Default Assistant",
            description="Default assistant",
            prompt="Answer accurately and concisely.",
        )

    def route_skill(self, query: str, session_id: Optional[str] = None) -> Tuple[MarkdownSkill, str]:
        """Route user query to the best accessible Markdown skill.
        
        Returns:
            Tuple of (selected_skill, routing_tier) where routing_tier is 'tier1', 'tier2', or 'tier3'.
        """
        accessible_skills = self.loader.get_accessible_skills(session_id=session_id)
        if not accessible_skills:
            fallback = self.loader.get_skill("sonnet-reasoning") or MarkdownSkill(
                name="default", category="general", title="Default Assistant", description="", prompt=""
            )
            return fallback, "tier3"

        # Tier 1: Regex & trigger keyword matching
        t1_skill = self._tier1_match(query, accessible_skills)
        if t1_skill:
            return t1_skill, "tier1"

        # Tier 2: Micro-LLM intent + Hybrid dense/sparse matching
        t2_skill = self._tier2_hybrid_match(query, accessible_skills, session_id=session_id)
        if t2_skill:
            return t2_skill, "tier2"

        # Tier 3: Reasoning ladder fallback
        t3_skill = self._tier3_fallback(query, accessible_skills)
        return t3_skill, "tier3"


default_skill_router = SkillRouter()
