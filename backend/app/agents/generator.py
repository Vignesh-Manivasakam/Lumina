from typing import Optional
from app.services.llm_client import LLMClient

SYSTEM_PROMPT = """You are an intelligent, helpful enterprise assistant with advanced vision and document capabilities.

Guidelines:
1. IMAGE ANALYSIS: If the user has attached an image, diagram, chart, or drawing, prioritize describing, analyzing, and answering the question based on the visual contents of the image. 
2. RETRIEVED CONTEXT: Use the provided document context to assist with answering. However, if the retrieved document context is unrelated to the attached image (e.g., resumes vs technical design diagrams), focus purely on the visual content of the image to answer. Do not describe or hallucinate based on the unrelated document context.
3. CITATIONS: When using document context, cite your sources as [Source 1], [Source 2] etc.
4. REPRESENTATION: If the user asks for a chart, table, or visual representation, create a clean, formatted Markdown table or visual text diagram summarizing the key data points, metrics, and comparisons.
5. GENERAL: If referring to 'the person', 'the candidate', or 'the author', relate it directly to the subject of the document context."""


class GeneratorAgent:
    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client
        # Back-compat alias
        self.nvidia = llm_client

    def generate(self, state: dict) -> dict:
        query = state["query"]
        docs = [d for d in (state.get("relevant_docs") or []) if d.get("relevance_score", 0) >= 0.4]
        user_image = state.get("user_image_b64")
        history = state.get("chat_history", [])[-4:]  # Limit to last 2 turns

        # Assemble sources context
        context_parts = []
        attached_file = state.get("attached_file")
        if attached_file and attached_file.get("content"):
            file_name = attached_file.get("name", "attached_file")
            file_content = attached_file.get("content", "")
            context_parts.append(f"[Direct Attachment: {file_name}]\n{file_content}")

        for i, doc in enumerate(docs, 1):
            ctx = f"[Source {i}] (modality: {doc['modality']})\n{doc['text_repr']}"
            context_parts.append(ctx)

        context = (
            "\n\n---\n\n".join(context_parts)
            if context_parts
            else "No relevant documents found in the uploaded archive. Provide a comprehensive, accurate general-knowledge answer without referencing or inventing unrelated document citations."
        )

        # Setup message structure (multimodal if user uploaded an image)
        if user_image:
            image_url = user_image if user_image.startswith("data:") else f"data:image/jpeg;base64,{user_image}"
            user_content = [
                {
                    "type": "image_url",
                    "image_url": {"url": image_url},
                },
                {"type": "text", "text": f"Context:\n{context}\n\nQuestion: {query}"},
            ]
        else:
            user_content = f"Context:\n{context}\n\nQuestion: {query}"

        # Determine active system prompt (dynamic markdown skill or default)
        active_skill_prompt = state.get("system_prompt")
        if active_skill_prompt:
            effective_system = (
                f"{active_skill_prompt}\n\n---\n"
                f"Core Operational Rules:\n"
                f"1. When using document context, cite sources as [Source 1], [Source 2] etc.\n"
                f"2. Never hallucinate citations if no source documents are provided.\n"
                f"3. Maintain strict factual precision and grounded reasoning."
            )
        else:
            effective_system = SYSTEM_PROMPT

        messages = [
            {"role": "system", "content": effective_system},
        ]

        # Add history in user/assistant format
        for msg in history:
            role = msg.get("role") or "user"
            hist_content = msg.get("content")
            if hist_content is None:
                hist_content = ""
            elif not isinstance(hist_content, str):
                hist_content = str(hist_content)
            messages.append({
                "role": "assistant" if role in ("assistant", "model") else "user",
                "content": hist_content,
            })

        # Add current query
        messages.append({"role": "user", "content": user_content})

        # Generate stream with dynamic model routing if selected
        model_override = state.get("model")
        if model_override:
            from app.services.provider_registry import ProviderRegistry
            provider = ProviderRegistry.get_for_task("generator", model_override=model_override)
            stream = provider.generate(messages, stream=True)
        else:
            stream = self.llm.generate(messages, stream=True)

        state["stream"] = stream
        state["source_docs"] = docs
        return state
