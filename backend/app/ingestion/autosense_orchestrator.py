"""Autosense Orchestrator module.

Sits above chunkers to scan documents and classify them (e.g., Tabular vs Prose)
to select the optimal ChunkingStrategy. Intercepts user queries to route them
dynamically between dense vector and hybrid search.
"""
from typing import Any, Dict, Tuple

from app.ingestion.document_analyzer import DocumentAnalyzer, ChunkingStrategy

class AutosenseOrchestrator:
    """Orchestrates adaptive chunking and dynamic query search mode routing."""

    def __init__(self) -> None:
        self.analyzer = DocumentAnalyzer()

    def determine_chunking_strategy(self, parsed_doc: Dict[str, Any]) -> ChunkingStrategy:
        """Scan incoming documents to classify and select optimal ChunkingStrategy."""
        return self.analyzer.analyze(parsed_doc)

    def route_query(self, query: str, query_type: str = "") -> Tuple[float, float]:
        """Intercept query to route between dense vector and hybrid search.

        Returns:
            Tuple of (bm25_weight, dense_weight).
        """
        query_lower = query.lower()
        query_type = query_type.strip().lower()

        # 1. Use explicit query type classification if provided by Router
        if query_type == "keyword":
            return (0.8, 0.2)
        elif query_type == "numerical":
            return (0.9, 0.1)
        elif query_type == "semantic":
            return (0.2, 0.8)
        elif query_type == "multi_hop":
            return (0.5, 0.5)

        # 2. Autosense heuristics for interception
        keyword_indicators = {"id", "code", "exact", "number", "date", "who", "when", "where"}
        semantic_indicators = {"how", "why", "explain", "concept", "theory", "meaning", "describe"}

        words = set(query_lower.split())
        
        # If it has numbers, favor exact match
        if any(char.isdigit() for char in query_lower):
            return (0.8, 0.2)
            
        if words.intersection(keyword_indicators):
            return (0.8, 0.2)

        if words.intersection(semantic_indicators) or len(words) > 7:
            return (0.2, 0.8)

        # 3. Default to balanced hybrid search
        return (0.5, 0.5)

__all__ = ("AutosenseOrchestrator",)
