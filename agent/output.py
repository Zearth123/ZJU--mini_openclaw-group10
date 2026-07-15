"""Run-scoped locations for generated planning artifacts."""
from __future__ import annotations

from contextvars import ContextVar
from pathlib import Path

CANONICAL_ARTIFACTS = {
    "event_project.json",
    "activity_plan.md",
    "wechat_article.md",
    "wechat_article.html",
}
_OUTPUT_DIR: ContextVar[Path | None] = ContextVar("agent_output_dir", default=None)


def bind_output_dir(path: str | Path | None):
    output = Path(path).resolve() if path is not None else None
    if output is not None:
        output.mkdir(parents=True, exist_ok=True)
    return _OUTPUT_DIR.set(output)


def unbind_output_dir(token) -> None:
    _OUTPUT_DIR.reset(token)


def current_output_dir() -> Path | None:
    return _OUTPUT_DIR.get()


def resolve_artifact_path(path: str | Path) -> Path:
    candidate = Path(path)
    output = current_output_dir()
    if (
        output is not None
        and not candidate.is_absolute()
        and candidate.parent == Path(".")
        and candidate.name in CANONICAL_ARTIFACTS
    ):
        return output / candidate.name
    return candidate


def finalize_artifacts(root: str | Path = ".") -> list[Path]:
    """Move canonical artifacts left at the workspace root into this run."""
    output = current_output_dir()
    if output is None:
        return []
    output.mkdir(parents=True, exist_ok=True)
    moved = []
    root_path = Path(root).resolve()
    for name in CANONICAL_ARTIFACTS:
        source = root_path / name
        target = output / name
        if source.is_file() and source.resolve() != target.resolve():
            source.replace(target)
            moved.append(target)
    return moved
