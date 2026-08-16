import json
from app.services.llm_client import LLMClient

class RewriterAgent:
    """Three-strategy query rewriter (cycles through them on consecutive retries)."""

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client
        # Back-compat alias
        self.nvidia = llm_client

    def rewrite(self, state: dict) -> dict:
        retry_num = state.get("retrieval_count", 1)
        query = state["query"]
        strategy = ["hyde", "stepback", "decompose"][(retry_num - 1) % 3]

        print(f"Rewriting query '{query}' using strategy: {strategy} (Attempt {retry_num})")

        if strategy == "hyde":
            state["rewritten_query"] = self._hyde(query)
        elif strategy == "stepback":
            state["rewritten_query"] = self._stepback(query)
        else:
            sub_queries = self._decompose(query)
            state["sub_queries"] = sub_queries
            # Use the first sub-query for the next retrieval round
            state["rewritten_query"] = sub_queries[0] if sub_queries else query

        state["thinking_note"] = (
            f"Applied {strategy} strategy for attempt {retry_num}: "
            f"'{state['rewritten_query'][:80]}…'"
        )
        return state

    def _hyde(self, query: str) -> str:
        """Hypothetical Document Embedding (HyDE): generates a hypothetical answer to embed."""
        prompt = (
            f"Write a short, professional, hypothetical answer (3-4 sentences) to the question: '{query}'. "
            "This answer is used for dense document retrieval search matching."
        )
        resp = self.llm.generate([{"role": "user", "content": prompt}], stream=False)
        return resp.content.strip()

    def _stepback(self, query: str) -> str:
        """Step-back abstraction: creates a more generic, high-level query to fetch broad context."""
        prompt = (
            f"Reformulate the query '{query}' to be a more general, high-level question. "
            "Return only the step-back query and nothing else."
        )
        resp = self.llm.generate([{"role": "user", "content": prompt}], stream=False)
        return resp.content.strip()

    def _decompose(self, query: str) -> list[str]:
        """Decomposition: breaks complex questions into 2-3 simpler sub-queries."""
        prompt = (
            f"Break this complex question into 2-3 simpler sub-questions: '{query}'. "
            "Return the sub-questions as a JSON list of strings (e.g. [\"question 1\", \"question 2\"]). "
            "Return only the JSON string and nothing else."
        )
        try:
            resp = self.llm.generate([{"role": "user", "content": prompt}], stream=False)
            text = resp.content.strip()
            # Clean up potential markdown formatting block
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                if text.endswith("```"):
                    text = text.rsplit("\n", 1)[0]
            return json.loads(text)
        except Exception as e:
            print(f"Failed to decompose query: {e}. Defaulting to list containing original query.")
            return [query]
