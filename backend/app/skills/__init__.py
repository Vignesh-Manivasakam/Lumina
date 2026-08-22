"""Skills package for Lumina RAG with categorization and intent discovery."""
from app.skills.causal_reasoning_skill import DeepCausalReasoningSkill
from app.skills.code_analysis_skill import CodeAnalysisSkill
from app.skills.contract_risk_skill import ContractRiskAnalyzerSkill
from app.skills.data_extraction_skill import DataExtractionSkill
from app.skills.deep_reasoning_skill import DeepReasoningSkill
from app.skills.image_gen_skill import ImageGenSkill
from app.skills.mcp_tool_skill import MCPToolSkill
from app.skills.skill_registry import Skill, SkillRegistry, default_skill_registry
from app.skills.summarization_skill import SummarizationSkill
from app.skills.web_search_skill import WebSearchSkill

# Populate default skills onto default_skill_registry singleton
for _skill_cls in (
    WebSearchSkill,
    ImageGenSkill,
    MCPToolSkill,
    DeepReasoningSkill,
    CodeAnalysisSkill,
    SummarizationSkill,
    DataExtractionSkill,
    ContractRiskAnalyzerSkill,
    DeepCausalReasoningSkill,
):
    try:
        _inst = _skill_cls()
        if not default_skill_registry.get_skill(_inst.name):
            default_skill_registry.register(_inst)
    except Exception:
        pass

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
    "ContractRiskAnalyzerSkill",
    "DeepCausalReasoningSkill",
]
