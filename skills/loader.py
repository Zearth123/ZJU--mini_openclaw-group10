"""Skills 加载器（Day7/9）。

Skill 与 Tool 的区别：
  - Tool 是一次函数调用。
  - Skill 是一包领域知识 + 操作流程，用 SKILL.md 描述。

SKILL.md 结构：
  ---
  name: my-skill
  description: 一句话说明何时使用
  ---
  正文：步骤、注意事项、示例。
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from pathlib import Path
import yaml


@dataclass
class Skill:
    name: str
    description: str
    body: str
    path: Path


def parse_skill_md(text: str, path: Path) -> Skill:
    name = description = ""
    body = text
    if text.startswith("---"):
        _, fm, body = text.split("---", 2)
        meta = yaml.safe_load(fm) or {}
        name = meta.get("name", "")
        description = meta.get("description", "")
    return Skill(name=name, description=description, body=body.strip(), path=path)


def load_skills(root: str = "skills") -> list[Skill]:
    skills: list[Skill] = []
    for md in Path(root).glob("*/SKILL.md"):
        skills.append(parse_skill_md(md.read_text(encoding="utf-8"), md))
    return skills


def skills_catalog(skills: list[Skill]) -> str:
    if not skills:
        return "（暂无可用 Skills）"
    return "\n".join(f"- {s.name}: {s.description}" for s in skills)


def skill_detail(skill: Skill) -> str:
    return f"""## Skill: {skill.name}

{skill.description}

{skill.body}"""


def _extract_keywords(text: str) -> set[str]:
    text_lower = text.lower()
    keywords: set[str] = set()
    for word in re.findall(r"[a-z][a-z0-9]+", text_lower):
        if len(word) >= 3:
            keywords.add(word)
            keywords.add(word[:4])
    chars = re.findall(r"[一-鿿]+", text_lower)
    for chunk in chars:
        if len(chunk) <= 4:
            keywords.add(chunk)
        for n in (2, 3, 4):
            for i in range(len(chunk) - n + 1):
                keywords.add(chunk[i:i + n])
    return keywords


def load_relevant_skills(task: str, skills: list[Skill]) -> list[Skill]:
    """根据任务文本筛选相关 skill（中英文关键词匹配）。"""
    task_keywords = _extract_keywords(task)
    matched = []
    for s in skills:
        combined = _extract_keywords(s.description) | _extract_keywords(s.name)
        if combined & task_keywords:
            matched.append(s)
    return matched
