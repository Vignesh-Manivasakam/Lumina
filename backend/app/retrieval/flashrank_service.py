"""Local CPU reranker using FlashRank — alternate class wrapper.

NOTE: Vestigial duplicate of ``app.retrieval.cpu_reranker.CPUReranker``.
Kept for backward compatibility with code paths that import
``FlashRankReranker`` directly. The active retrieval path uses
``CPUReranker``.
"""
from typing import List, Dict, Any

class FlashRankReranker:
    """
    Local FlashRank cross-encoder reranker. Pure CPU, no API cost.
    Uses ms-marco-MiniLM-L-12-v2 (~30 MB).
    """

    def __init__(self, model_name: str = "ms-marco-MiniLM-L-12-v2"):
        self.model_name = model_name
        self._ranker = None

    def _get_ranker(self):
        if self._ranker is None:
            try:
                from flashrank import Ranker
                print(f"[FlashRankReranker] Loading local FlashRank model '{self.model_name}'...")
                self._ranker = Ranker(model_name=self.model_name)
            except Exception as e:
                print(f"[FlashRankReranker] Warning: FlashRank init failed: {e}")
                self._ranker = False
        return self._ranker

    def rerank(self, query: str, docs: List[Dict[str, Any]], top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Rerank a list of doc dicts based on semantic similarity to query.
        Each doc dict is expected to have 'text_repr' or 'text' or 'content'.
        """
        if not docs:
            return []

        ranker = self._get_ranker()
        if not ranker:
            return docs[:top_k]

        try:
            from flashrank import RerankRequest
            passages = [
                {
                    "id": doc.get("chunk_id", str(idx)),
                    "text": doc.get("text_repr", doc.get("text", doc.get("content", ""))),
                    "meta": doc
                }
                for idx, doc in enumerate(docs)
            ]

            rerank_request = RerankRequest(query=query, passages=passages)
            results = ranker.rerank(rerank_request)

            reranked_docs = []
            for item in results[:top_k]:
                doc_meta = item.get("meta", {}).copy()
                doc_meta["score"] = float(item.get("score", 0.0))
                reranked_docs.append(doc_meta)

            return reranked_docs
        except Exception as e:
            print(f"[FlashRankReranker] Rerank error: {e}")
            return docs[:top_k]
