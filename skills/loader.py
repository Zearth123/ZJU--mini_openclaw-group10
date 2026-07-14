"""Skills 加载器（Day7）。

Skill 与 Tool 的区别：
  - Tool 是一次函数调用（read 一个文件）。
  - Skill 是一包"领域知识 + 操作流程 + 可选脚本/资源"，用一个 SKILL.md 描述，
    在合适的时候被加载进上下文，告诉模型"面对这类任务该怎么一步步做"。

SKILL.md 结构（约定）：
  ---
  name: pdf-report
  description: 一句话说明何时该用这个 skill（用于召回判断）
  ---
  正文：步骤、注意事项、可调用的脚本路径、示例。

加载器要做：扫描 skills/ 下每个含 SKILL.md 的目录，解析 frontmatter，
按需把正文注入系统提示词 / 作为可发现的能力清单。
"""
from __future__ import annotations
from dataclasses import dataclass  # 数据类，用于定义 Skill 结构
from pathlib import Path  # 路径操作，用于扫描 SKILL.md 文件


@dataclass
class Skill:
    """技能定义：包含名称、描述、正文内容和文件路径。

    Skill 与 Tool 的区别：
        - Tool 是一次函数调用（如 read 一个文件）
        - Skill 是一包领域知识 + 操作流程，通过 SKILL.md 描述，
          在适当时被加载进上下文，指导模型面对特定类型任务该如何操作
    """
    name: str  # 技能名称
    description: str  # 技能描述（用于召回判断）
    body: str  # 技能正文：步骤、注意事项、示例等
    path: Path  # SKILL.md 文件路径

def parse_skill_md(text: str, path: Path) -> Skill:
    """解析 SKILL.md 文件，提取 YAML frontmatter（name/description）和正文 body。

    参数:
        text: SKILL.md 文件内容
        path: 文件路径

    返回:
        解析后的 Skill 对象
    """
    # TODO[Day6] 解析 YAML frontmatter（name/description）+ 正文 body
    raise NotImplementedError("Day7：解析 SKILL.md frontmatter")


def load_skills(root: str = "skills") -> list[Skill]:
    """扫描 root 目录下所有 SKILL.md 文件并解析为 Skill 对象。

    参数:
        root: 扫描根目录，默认为 "skills"

    返回:
        Skill 对象列表
    """
    skills: list[Skill] = []
    for md in Path(root).glob("*/SKILL.md"):
        skills.append(parse_skill_md(md.read_text(encoding="utf-8"), md))
    return skills


def skills_catalog(skills: list[Skill]) -> str:
    """生成给模型看的可用 skill 清单（name + description），用于按需召回。

    渲染结果会被拼接到系统提示词中，让模型知道可用的领域技能。

    参数:
        skills: Skill 对象列表

    返回:
        渲染后的文本清单，每行一个 skill
    """
    # TODO[Day6] 渲染成一段文本，放进系统提示词
    return "\n".join(f"- {s.name}: {s.description}" for s in skills)
