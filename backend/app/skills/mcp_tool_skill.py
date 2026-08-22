"""MCP Tool execution skill invoking tools from connected MCP servers."""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from app.services.llm_client import LLMClient
from app.services.mcp_client import MCPClientService
from app.skills.skill_registry import Skill

logger = logging.getLogger(__name__)


class MCPToolSkill(Skill):
    """Executes tools from registered MCP servers matching user queries."""

    TOOL_SELECTOR_PROMPT = """You are an intelligent MCP tool selection agent.
Given a user query and a list of available MCP tools across connected servers, select the most relevant tool to execute and construct its arguments.

Available Tools:
{tools_json}

User Query:
{query}

Respond ONLY with a JSON object in this exact format:
{{
  "server_name": "<server_name>",
  "tool_name": "<tool_name>",
  "arguments": {{<arguments_object>}}
}}
If no tool is suitable, respond with:
{{
  "server_name": "",
  "tool_name": "",
  "arguments": {{}}
}}"""

    def __init__(
        self,
        mcp_client: Optional[MCPClientService] = None,
        llm_client: Optional[LLMClient] = None,
    ) -> None:
        self.mcp_client = mcp_client or MCPClientService()
        self.llm = llm_client or LLMClient(task="router")

    @property
    def name(self) -> str:
        return "mcp_tool"

    @property
    def description(self) -> str:
        return "Dispatches queries to external Model Context Protocol (MCP) server tools."

    @property
    def category(self) -> str:
        return "integration"

    @property
    def tags(self) -> List[str]:
        return ["mcp", "tool", "integration", "zapier", "gmail", "github", "postgres", "weather"]

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "server_name": {"type": "string", "description": "Name of the registered MCP server"},
                "tool_name": {"type": "string", "description": "Name of the tool to invoke"},
                "arguments": {"type": "object", "description": "Arguments passed to the tool"},
            },
            "required": ["server_name", "tool_name"],
        }

    def can_handle(self, state: dict) -> bool:
        return state.get("route") == "mcp_tool"

    def _collect_available_tools(self, session_id: Optional[str] = None) -> List[dict]:
        """Collect all tools from registered connections."""
        connections = self.mcp_client.list_connections(session_id=session_id)
        all_tools = []
        for conn in connections:
            server_name = conn.get("name", "")
            for tool in conn.get("tools", []):
                all_tools.append({
                    "server_name": server_name,
                    "name": tool.get("name"),
                    "description": tool.get("description"),
                    "input_schema": tool.get("input_schema", {}),
                })
        return all_tools

    def _select_tool(self, query: str, tools: List[dict]) -> Optional[dict]:
        """Use LLM to select tool and generate arguments."""
        if not tools:
            return None
        try:
            tools_summary = [
                {
                    "server_name": t.get("server_name"),
                    "name": t.get("name"),
                    "description": t.get("description"),
                    "input_schema": t.get("input_schema"),
                }
                for t in tools
            ]
            prompt = self.TOOL_SELECTOR_PROMPT.format(
                tools_json=json.dumps(tools_summary, indent=2),
                query=query,
            )
            response = self.llm.generate_text([
                {"role": "user", "content": prompt}
            ], max_tokens=300, temperature=0.0)

            content = response.content.strip()
            if "```" in content:
                match = re.search(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL)
                if match:
                    content = match.group(1).strip()

            parsed = json.loads(content)
            if isinstance(parsed, dict) and parsed.get("tool_name"):
                return parsed
        except Exception as exc:
            logger.warning("MCP tool selection failed: %s; using first matching tool fallback", exc)

        # Fallback: if single tool exists, invoke with empty or query arg
        if tools:
            first_tool = tools[0]
            return {
                "server_name": first_tool.get("server_name"),
                "tool_name": first_tool.get("name"),
                "arguments": {"query": query} if "query" in str(first_tool.get("input_schema")) else {},
            }
        return None

    def execute(self, state: dict) -> dict:
        query = state.get("query", "")
        session_id = state.get("session_id")
        thinking_emitter = state.get("thinking_emitter")

        available_tools = self._collect_available_tools(session_id=session_id)

        if not available_tools:
            logger.info("No MCP tools available to handle query: %s", query[:40])
            if thinking_emitter:
                thinking_emitter("skill_executor", "No active MCP tools connected.")

            fallback_doc = {
                "chunk_id": "mcp-no-tools",
                "id": "mcp-no-tools",
                "modality": "text",
                "text_repr": "No MCP server connections with tools are currently registered. Register an MCP server via POST /api/mcp/connections to enable external tool execution.",
                "score": 1.0,
                "source": "mcp_tool",
            }
            state["retrieved_docs"] = [fallback_doc]
            state["source_docs"] = [fallback_doc]
            state["tool_result"] = {"success": False, "content": "No MCP tools available"}
            state["is_sufficient"] = True
            return state

        if thinking_emitter:
            thinking_emitter("skill_executor", f"Selecting MCP tool for: {query[:50]}")

        selection = self._select_tool(query, available_tools)

        if not selection or not selection.get("tool_name"):
            fallback_doc = {
                "chunk_id": "mcp-unmatched",
                "id": "mcp-unmatched",
                "modality": "text",
                "text_repr": f"Could not determine a matching MCP tool for query: '{query}'.",
                "score": 0.0,
                "source": "mcp_tool",
            }
            state["retrieved_docs"] = [fallback_doc]
            state["source_docs"] = [fallback_doc]
            state["tool_result"] = {"success": False, "content": "No matching tool selected"}
            state["is_sufficient"] = True
            return state

        server_name = selection.get("server_name", "")
        tool_name = selection.get("tool_name", "")
        args = selection.get("arguments", {})

        if thinking_emitter:
            thinking_emitter("skill_executor", f"Invoking tool '{tool_name}' on MCP server '{server_name}'...")

        result = self.mcp_client.invoke_tool(server_name, tool_name, args)
        state["tool_result"] = result

        output_content = result.get("content", "")
        tool_doc = {
            "chunk_id": f"mcp-{server_name}-{tool_name}",
            "id": f"mcp-{server_name}-{tool_name}",
            "modality": "text",
            "text_repr": f"MCP Tool Output [{server_name} -> {tool_name}]:\n\n{output_content}",
            "score": 1.0,
            "rerank_score": 1.0,
            "source": f"mcp:{server_name}/{tool_name}",
        }
        state["retrieved_docs"] = [tool_doc]
        state["source_docs"] = [tool_doc]
        state["is_sufficient"] = True

        return state
