"""Image generation skill supporting NVIDIA NIM SDXL and high-reliability fallback."""
from __future__ import annotations

import base64
import logging
import urllib.parse
from typing import Any, Dict, Optional

import httpx

from app.config import settings
from app.services.llm_client import LLMClient
from app.skills.skill_registry import Skill

logger = logging.getLogger(__name__)


class ImageGenSkill(Skill):
    """Refines user prompt and generates image using NVIDIA NIM SDXL with high-fidelity fallback."""

    REFINER_PROMPT = (
        "You are an expert prompt engineer for Stable Diffusion XL (SDXL) and Flux.\n"
        "Convert the user's image request into a rich, detailed, visually stunning prompt.\n"
        "Specify lighting, artistic style, high resolution detail, camera perspective, and color palette.\n"
        "Output ONLY the final refined prompt string with no commentary, quotation marks, or markdown fences."
    )

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        llm_client: Optional[LLMClient] = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else getattr(settings, "NVIDIA_API_KEY", "")
        self.base_url = base_url or getattr(settings, "NVIDIA_BASE_URL", "https://ai.api.nvidia.com/v1/genai")
        self.model = model or getattr(settings, "NVIDIA_IMAGE_MODEL", "stabilityai/sdxl-turbo")
        self.llm = llm_client or LLMClient(task="router")

    @property
    def name(self) -> str:
        return "image_gen"

    @property
    def description(self) -> str:
        return "Generates high-resolution images from textual descriptions using SDXL and Flux."

    @property
    def category(self) -> str:
        return "creative"

    @property
    def tags(self) -> List[str]:
        return ["image", "art", "drawing", "picture", "sdxl", "generate image", "illustration"]

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Text prompt describing the image to generate"}
            },
            "required": ["prompt"],
        }

    def can_handle(self, state: dict) -> bool:
        return state.get("route") == "image_gen"

    def _refine_prompt(self, user_prompt: str) -> str:
        """Use LLM to refine the user's prompt into an optimized image generation prompt."""
        try:
            res = self.llm.generate_text([
                {"role": "system", "content": self.REFINER_PROMPT},
                {"role": "user", "content": user_prompt},
            ], max_tokens=250, temperature=0.7)
            refined = res.content.strip().strip('"\'')
            if refined:
                return refined
        except Exception as exc:
            logger.warning("Prompt refinement failed: %s; using raw prompt", exc)
        return user_prompt

    def _generate_nvidia_nim(self, prompt: str) -> Optional[str]:
        """Attempt image generation via NVIDIA NIM SDXL endpoint."""
        if not self.api_key:
            return None

        # Endpoint 1: NVIDIA AI GenAI endpoint
        candidates = [
            f"https://ai.api.nvidia.com/v1/genai/{self.model}",
            "https://ai.api.nvidia.com/v1/genai/stabilityai/sdxl-turbo",
            "https://ai.api.nvidia.com/v1/genai/stabilityai/stable-diffusion-xl-base-1.0",
        ]

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        payload = {
            "text_prompts": [{"text": prompt, "weight": 1.0}],
            "seed": 0,
            "sampler": "K_EULER_ANCESTRAL",
            "steps": 25,
        }

        for url in candidates:
            try:
                with httpx.Client(timeout=30.0) as client:
                    resp = client.post(url, headers=headers, json=payload)
                    if resp.is_success:
                        data = resp.json()
                        artifacts = data.get("artifacts", [])
                        if artifacts and artifacts[0].get("base64"):
                            return artifacts[0]["base64"]
            except Exception as e:
                logger.debug("NVIDIA NIM endpoint %s failed: %s", url, e)

        # Endpoint 2: OpenAI-compatible proxy format
        try:
            url = f"{self.base_url.rstrip('/')}/images/generations"
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    url,
                    headers=headers,
                    json={"model": self.model, "prompt": prompt, "response_format": "b64_json"},
                )
                if resp.is_success:
                    items = resp.json().get("data", [])
                    if items and items[0].get("b64_json"):
                        return items[0]["b64_json"]
        except Exception as e:
            logger.debug("NVIDIA OpenAI proxy image call failed: %s", e)

        return None

    def _generate_fallback(self, prompt: str) -> Optional[str]:
        """High-reliability fast image generation fallback via Pollinations Flux/SDXL."""
        try:
            encoded_prompt = urllib.parse.quote(prompt[:300])
            url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&nologo=true&seed=42&model=flux"
            with httpx.Client(timeout=25.0, follow_redirects=True) as client:
                resp = client.get(url)
                if resp.is_success and len(resp.content) > 1000:
                    return base64.b64encode(resp.content).decode("utf-8")
        except Exception as exc:
            logger.warning("Fallback image generation failed: %s", exc)
        return None

    def execute(self, state: dict) -> dict:
        user_prompt = state.get("query", "")
        thinking_emitter = state.get("thinking_emitter")

        if thinking_emitter:
            thinking_emitter("skill_executor", "Refining image prompt for visual generation...")

        refined_prompt = self._refine_prompt(user_prompt)

        if thinking_emitter:
            thinking_emitter("skill_executor", f"Generating artwork with prompt: {refined_prompt[:65]}...")

        # 1. Try NVIDIA NIM first
        image_b64 = self._generate_nvidia_nim(refined_prompt)

        # 2. If NVIDIA NIM failed or missing, use high-speed fallback
        if not image_b64:
            if thinking_emitter:
                thinking_emitter("skill_executor", "NVIDIA NIM endpoint unavailable; using high-fidelity fallback generator...")
            image_b64 = self._generate_fallback(refined_prompt)

        error_msg = None
        if not image_b64:
            error_msg = "Image generation service temporarily unreachable. Please try again."

        state["image_result"] = {
            "image_b64": image_b64 or "",
            "prompt": user_prompt,
            "refined_prompt": refined_prompt,
        }
        if error_msg:
            state["image_result"]["error"] = error_msg

        # Image skills produce visual artifacts, so clear text generation stream
        state["stream"] = None

        return state
