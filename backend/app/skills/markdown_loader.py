"""Dynamic Markdown Skill Loader for Lumina.

Auto-discovers and indexes markdown skill definitions from disk, parses YAML frontmatter,
and provides session-isolated custom skill management with in-memory FastEmbed + BM25 indexing.
"""
from __future__ import annotations

import glob
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


@dataclass
class MarkdownSkill:
    name: str
    category: str
    title: str
    description: str
    prompt: str
    triggers: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    confidence_threshold: float = 0.60
    session_id: Optional[str] = None  # None for global system skills
    embedding: Optional[np.ndarray] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "title": self.title,
            "description": self.description,
            "triggers": self.triggers,
            "tags": self.tags,
            "confidence_threshold": self.confidence_threshold,
            "is_custom": self.session_id is not None,
            "session_id": self.session_id,
        }


def parse_markdown_skill(content: str, session_id: Optional[str] = None) -> Optional[MarkdownSkill]:
    """Parse YAML frontmatter and markdown body into a MarkdownSkill."""
    match = _FRONTMATTER_RE.match(content.strip())
    if not match:
        return None

    yaml_block, body = match.groups()
    metadata: Dict[str, Any] = {}
    current_list_key: Optional[str] = None

    for line in yaml_block.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, val = line.split(":", 1)
            key = key.strip().lower()
            val = val.strip().strip('"\'')
            if not val:
                # Key with list items on subsequent lines
                metadata[key] = []
                current_list_key = key
            elif val.startswith("[") and val.endswith("]"):
                # Inline list format: [item1, item2]
                items = [item.strip().strip('"\'') for item in val[1:-1].split(",") if item.strip()]
                metadata[key] = items
                current_list_key = None
            elif val.replace(".", "", 1).isdigit():
                metadata[key] = float(val) if "." in val else int(val)
                current_list_key = None
            else:
                metadata[key] = val
                current_list_key = None
        elif line.startswith("- ") and current_list_key and isinstance(metadata.get(current_list_key), list):
            metadata[current_list_key].append(line[2:].strip().strip('"\''))

    name = metadata.get("name")
    if not name:
        return None

    triggers = metadata.get("triggers", [])
    if isinstance(triggers, str):
        triggers = [t.strip() for t in triggers.split(",") if t.strip()]

    tags = metadata.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]

    return MarkdownSkill(
        name=name,
        category=metadata.get("category", "general"),
        title=metadata.get("title", name.replace("-", " ").title()),
        description=metadata.get("description", ""),
        prompt=body.strip(),
        triggers=triggers,
        tags=tags,
        confidence_threshold=float(metadata.get("confidence_threshold", 0.60)),
        session_id=session_id,
    )


class MarkdownSkillLoader:
    """Manages global and session-scoped markdown skills with in-memory FastEmbed vectors."""

    def __init__(self, definitions_dir: Optional[str] = None) -> None:
        self.definitions_dir = Path(
            definitions_dir or os.path.join(os.path.dirname(__file__), "definitions")
        )
        self.global_skills: Dict[str, MarkdownSkill] = {}
        # Scoped custom skills: session_id -> {skill_name: MarkdownSkill}
        self.session_skills: Dict[str, Dict[str, MarkdownSkill]] = {}
        self._embedder = None
        self._load_global_skills()

    def _get_embedder(self):
        if self._embedder is None:
            try:
                from app.ingestion.fast_embedder import LocalEmbedder
                self._embedder = LocalEmbedder()
            except Exception as exc:
                logger.warning("FastEmbed not available for skill loader: %s", exc)
                self._embedder = None
        return self._embedder

    def _compute_embedding(self, skill: MarkdownSkill) -> Optional[np.ndarray]:
        embedder = self._get_embedder()
        if not embedder:
            return None
        text_repr = f"{skill.title} {skill.description} {' '.join(skill.tags)} {' '.join(skill.triggers)}"
        try:
            vecs = embedder.embed_texts([text_repr])
            return np.array(vecs[0], dtype=np.float32) if vecs else None
        except Exception as exc:
            logger.warning("Failed to embed skill %s: %s", skill.name, exc)
            return None

    def _load_global_skills(self) -> None:
        """Scan definitions_dir recursively for .md skill files."""
        if not self.definitions_dir.exists():
            logger.warning("Skills definitions directory does not exist: %s", self.definitions_dir)
            return

        md_files = glob.glob(str(self.definitions_dir / "**" / "*.md"), recursive=True)
        for path in md_files:
            try:
                content = Path(path).read_text(encoding="utf-8")
                skill = parse_markdown_skill(content, session_id=None)
                if skill:
                    skill.embedding = self._compute_embedding(skill)
                    self.global_skills[skill.name] = skill
                    logger.debug("Loaded global markdown skill: %s (%s)", skill.name, skill.category)
            except Exception as exc:
                logger.error("Failed to load skill file %s: %s", path, exc)

        logger.info("Loaded %d global markdown skills", len(self.global_skills))

    def register_custom_skill(self, session_id: str, markdown_content: str) -> MarkdownSkill:
        """Register a user custom skill scoped strictly to their session_id."""
        if not session_id:
            raise ValueError("session_id is required to register a custom skill.")

        skill = parse_markdown_skill(markdown_content, session_id=session_id)
        if not skill:
            raise ValueError("Invalid markdown skill format. Must contain YAML frontmatter with 'name'.")

        skill.embedding = self._compute_embedding(skill)

        if session_id not in self.session_skills:
            self.session_skills[session_id] = {}

        self.session_skills[session_id][skill.name] = skill
        logger.info("Registered custom skill '%s' for session '%s'", skill.name, session_id)
        return skill

    def delete_custom_skill(self, session_id: str, skill_name: str) -> bool:
        """Delete a custom skill scoped to session_id."""
        if session_id in self.session_skills and skill_name in self.session_skills[session_id]:
            del self.session_skills[session_id][skill_name]
            return True
        return False

    def get_skill(self, name: str, session_id: Optional[str] = None) -> Optional[MarkdownSkill]:
        """Look up a skill by name, checking session-scoped custom skills first."""
        if session_id and session_id in self.session_skills:
            if name in self.session_skills[session_id]:
                return self.session_skills[session_id][name]
        return self.global_skills.get(name)

    def get_accessible_skills(self, session_id: Optional[str] = None) -> List[MarkdownSkill]:
        """Return list of all global skills + session-scoped custom skills for session_id."""
        skills = list(self.global_skills.values())
        if session_id and session_id in self.session_skills:
            skills.extend(self.session_skills[session_id].values())
        return skills


# Singleton instance
default_markdown_skill_loader = MarkdownSkillLoader()
