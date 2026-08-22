"""Skills package for Lumina RAG with categorization and intent discovery."""
from app.skills.code_analysis_skill import CodeAnalysisSkill
from app.skills.data_extraction_skill import DataExtractionSkill
from app.skills.deep_reasoning_skill import DeepReasoningSkill
from app.skills.image_gen_skill import ImageGenSkill
from app.skills.mcp_tool_skill import MCPToolSkill
from app.skills.skill_registry import Skill, SkillRegistry, default_skill_registry
from app.skills.summarization_skill import SummarizationSkill
from app.skills.web_search_skill import WebSearchSkill

# Automatically register default skills on module load
default_skill_registry.register(WebSearchSkill())
default_skill_registry.register(ImageGenSkill())
default_skill_registry.register(MCPToolSkill())
default_skill_registry.register(DeepReasoningSkill())
default_skill_registry.register(CodeAnalysisSkill())
default_skill_registry.register(SummarizationSkill())
default_skill_registry.register(DataExtractionSkill())

__all__ = [
    "Skill",
    "SkillRegistry",
    "default_skill_registry",
    "WebSearchSkill",
    "ImageGenSkill",
    "MCPToolSkill",
    "DeepReasoningSkill",
    "CodeAnalysisSkill",
    "SummarizationSkill",
    "DataExtractionSkill",
]
