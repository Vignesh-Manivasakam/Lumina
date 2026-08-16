"""Local CPU reranker using FlashRank.

Replaces the previous NVIDIA-hosted reranker. Runs entirely on CPU,
downloads a ~50 MB cross-encoder on first use.
"""
from __future__ import annotations

import copy
import logging
from functools import lru_cache
from typing import List, Optional

from flashrank import Ranker, RerankRequest

from app.config import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_ranker(model_name: str) -> Ranker:
    """Load and cache the FlashRank model.

    Uses the configured cache directory so subsequent runs skip the
    ~50 MB download. Defaults to the user's cache directory when
    ``cache_dir`` is unset in settings.
    """
    cache_dir = getattr(settings, "RERANK_CACHE_DIR", None) or None
    logger.info(
        "Loading FlashRank model %s (first run downloads ~50 MB)…", model_name
    )
    ranker = Ranker(model_name=model_name, cache_dir=cache_dir) if cache_dir else Ranker(model_name=model_name)
    logger.info("FlashRank model %s loaded.", model_name)
    return ranker


class CPUReranker:
    """FlashRank-backed cross-encoder reranker.

    Accepts either a list of plain strings (treated as passage text) or
    a list of dicts with at least an ``id`` and ``text`` (or ``text_repr``)
    field. Returns the same list annotated with a ``rerank_score`` field,
    sorted by descending score.
    """

    def __init__(self, model_name: Optional[str] = None) -> None:
        self.model_name = model_name or settings.RERANK_MODEL
        self._ranker = _get_ranker(self.model_name)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def rerank(self, query: str, passages, top_k: Optional[int] = None) -> list:
        """Rerank ``passages`` against ``query``.

        ``passages`` may be:
        - a list of ``str`` (treated as opaque passage text)
        - a list of ``dict`` with ``id`` and either ``text`` or ``text_repr``

        Returns the input list annotated with a ``rerank_score`` field
        and sorted by descending relevance. Original input is not mutated.
        """
        if not passages:
            return []

        if isinstance(passages[0], str):
            items = [{"id": str(i), "text": t} for i, t in enumerate(passages)]
            request = RerankRequest(query=query, passages=items)
            results = self._ranker.rerank(request)
            res = [
                {
                    "id": r.get("id", str(i)),
                    "text": r.get("text", ""),
                    "rerank_score": float(r.get("score", 0.0)),
                }
                for i, r in enumerate(results)
            ]
            return res[:top_k] if top_k is not None else res

        # Object/dict path - preserve original objects, just attach rerank_score
        ids = []
        items = []
        for i, p in enumerate(passages[:25]):
            if isinstance(p, dict):
                pid = str(p.get("id") or p.get("chunk_id") or i)
                text = p.get("text") or p.get("text_repr") or ""
            else:
                pid = str(getattr(p, "chunk_id", i))
                text = getattr(p, "text_repr", "") or ""
            ids.append(pid)
            # Truncate text to 512 characters to prevent ONNX memory arena spikes
            items.append({"id": pid, "text": str(text)[:512]})

        try:
            request = RerankRequest(query=query[:250], passages=items)
            results = self._ranker.rerank(request)
            score_map = {str(r.get("id")): float(r.get("score", 0.0)) for r in results}
        except Exception as err:
            logger.warning("FlashRank rerank failed (%s); using default score order", err)
            score_map = {pid: max(0.9 - (idx * 0.05), 0.1) for idx, pid in enumerate(ids)}

        annotated: list = []
        for original, pid in zip(passages, ids):
            score = score_map.get(pid, 0.0)
            if isinstance(original, dict):
                new_obj = {**original, "rerank_score": score}
            else:
                new_obj = copy.copy(original)
                setattr(new_obj, "rerank_score", score)
            annotated.append(new_obj)

        annotated.sort(
            key=lambda x: x.get("rerank_score") if isinstance(x, dict) else getattr(x, "rerank_score", 0.0),
            reverse=True,
        )
        return annotated[:top_k] if top_k is not None else annotated

    def score(self, query: str, passages: List[str]) -> List[float]:
        """Convenience helper: return just the rerank scores in input order."""
        if not passages:
            return []
        items = [{"id": str(i), "text": t} for i, t in enumerate(passages)]
        request = RerankRequest(query=query, passages=items)
        results = self._ranker.rerank(request)
        score_map = {int(r["id"]): float(r["score"]) for r in results}
        return [score_map.get(i, 0.0) for i in range(len(passages))]
