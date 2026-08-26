# Lumina Enterprise Implementation Rules

## Architecture Constraints
- All LLM calls MUST go through `ProviderRegistry` — never import `google.generativeai` directly in agent files
- NVIDIA NIM is the primary provider; Gemini is kept as fallback only
- All new backend files go in appropriate subdirectories under `backend/app/`
- All new frontend components go in `frontend/components/{category}/`
- No file should exceed 500 lines (split into modules if needed)
- Every new service must have graceful degradation (work without API key for demo mode)

## Provider Pattern
- Use `ProviderRegistry.get_for_task("task_name")` to get the right provider
- Never hardcode model names in agent files — they come from `config.py`
- All providers must implement the same `LLMProvider` interface
- The `LLMClient` class is a backward-compatible facade over `ProviderRegistry`

## NVIDIA NIM Integration
- Base URL: `https://integrate.api.nvidia.com/v1`
- All NIM endpoints are OpenAI-compatible — use the `openai` Python SDK
- Free tier limit: ~40 RPM — implement request throttling
- Models: nemotron-3.5-lightning (fast tasks), nemotron-3-ultra (generation), SDXL (images), Whisper (ASR), Magpie (TTS)

## Token Optimization Rules
- Batch LLM calls whenever possible (contextual headers: 10 per call, grading: all docs in one call)
- Use heuristic pre-filters before LLM classification (direct patterns, image keywords)
- Use the cheapest model that can handle the task (classification → small model, generation → large model)
- Cache embedding results for repeated queries (LRU cache on `embed_query`)

## File Organization
- `backend/app/services/` — external service clients (provider_registry, mcp_client, voice_service)
- `backend/app/skills/` — skill implementations (web_search, image_gen, mcp_tool)
- `backend/app/ingestion/` — chunking strategies (document_analyzer, semantic_chunker, section_chunker)
- `frontend/components/chat/` — chat-related components (ChatWindow, ChatInput, VoiceInput, etc.)
- `frontend/components/sidebar/` — sidebar components (ConversationList, MCPConnections, Settings)
- `backend/migrations/` — Supabase SQL migration files

## Testing Requirements
- Every new module needs a corresponding test file in `backend/tests/`
- Test with `NVIDIA_API_KEY=""` to verify graceful degradation
- Frontend components must pass `npm run build` (TypeScript compilation)
- Run `pytest` after every phase completion

## Coding Style
- Use type hints on all Python function signatures
- Use `from __future__ import annotations` for modern type syntax
- Preserve all existing docstrings and comments unrelated to changes
- Use async/await for all new API endpoints
- SSE events must follow the existing `{type: ..., ...}` wire format
