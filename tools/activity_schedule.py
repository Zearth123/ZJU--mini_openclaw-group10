"""活动排期 Tool：依赖排序并生成具体起止时间。"""
from __future__ import annotations

import json
from collections import deque
from typing import Any

from .base import Tool


def _parse_time(value: str, field: str) -> int:
    try:
        hour_text, minute_text = value.split(":", 1)
        hour, minute = int(hour_text), int(minute_text)
    except (AttributeError, ValueError) as exc:
        raise ValueError(f"{field} 必须使用 HH:MM 格式") from exc
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError(f"{field} 不是合法时间")
    return hour * 60 + minute


def _format_time(total_minutes: int) -> str:
    total_minutes %= 24 * 60
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"


def _positive_int(value: Any, field: str, allow_zero: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} 必须是整数")
    if value < 0 or (value == 0 and not allow_zero):
        relation = "非负" if allow_zero else "正"
        raise ValueError(f"{field} 必须是{relation}整数")
    return value


def _topological_order(stages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    original_order: dict[str, int] = {}
    for index, stage in enumerate(stages):
        if not isinstance(stage, dict):
            raise ValueError(f"stages[{index}] 必须是对象")
        stage_id = str(stage.get("stage_id", "")).strip()
        if not stage_id:
            raise ValueError(f"stages[{index}] 缺少 stage_id")
        if stage_id in by_id:
            raise ValueError(f"stage_id 重复：{stage_id}")
        by_id[stage_id] = stage
        original_order[stage_id] = index

    indegree = {stage_id: 0 for stage_id in by_id}
    children = {stage_id: [] for stage_id in by_id}
    for stage_id, stage in by_id.items():
        dependencies = stage.get("dependencies", [])
        if not isinstance(dependencies, list):
            raise ValueError(f"环节 {stage_id} 的 dependencies 必须是数组")
        if len(set(dependencies)) != len(dependencies):
            raise ValueError(f"环节 {stage_id} 包含重复依赖")
        for dependency in dependencies:
            if dependency not in by_id:
                raise ValueError(f"环节 {stage_id} 依赖不存在的环节：{dependency}")
            if dependency == stage_id:
                raise ValueError(f"环节 {stage_id} 不能依赖自身")
            indegree[stage_id] += 1
            children[dependency].append(stage_id)

    ready = deque(sorted(
        (stage_id for stage_id, degree in indegree.items() if degree == 0),
        key=original_order.get,
    ))
    ordered_ids: list[str] = []
    while ready:
        stage_id = ready.popleft()
        ordered_ids.append(stage_id)
        newly_ready: list[str] = []
        for child in children[stage_id]:
            indegree[child] -= 1
            if indegree[child] == 0:
                newly_ready.append(child)
        ready.extend(sorted(newly_ready, key=original_order.get))

    if len(ordered_ids) != len(stages):
        raise ValueError("活动环节依赖关系存在循环")
    return [by_id[stage_id] for stage_id in ordered_ids]


def build_schedule_data(
    event_start: str,
    event_end: str,
    stages: list[dict[str, Any]],
    buffer_minutes: int = 15,
) -> dict[str, Any]:
    """顺序安排拓扑排序后的环节；结束时间不晚于开始时间时按跨午夜处理。"""
    start = _parse_time(event_start, "event_start")
    end = _parse_time(event_end, "event_end")
    if end <= start:
        end += 24 * 60
    window_minutes = end - start
    buffer_value = _positive_int(buffer_minutes, "buffer_minutes", allow_zero=True)
    if not isinstance(stages, list) or not stages:
        raise ValueError("stages 必须是非空数组")

    ordered = _topological_order(stages)
    cursor = start
    schedule: list[dict[str, Any]] = []
    for stage in ordered:
        stage_id = str(stage["stage_id"])
        name = str(stage.get("name", "")).strip()
        if not name:
            raise ValueError(f"环节 {stage_id} 缺少 name")
        duration = _positive_int(stage.get("duration_minutes"), f"环节 {stage_id} 的 duration_minutes")
        staff = _positive_int(stage.get("staff_required"), f"环节 {stage_id} 的 staff_required")
        item_end = cursor + duration
        schedule.append({
            "stage_id": stage_id,
            "stage": name,
            "start": _format_time(cursor),
            "end": _format_time(item_end),
            "duration_minutes": duration,
            "staff_required": staff,
        })
        cursor = item_end

    stages_minutes = cursor - start
    total_minutes = stages_minutes + buffer_value
    unused_minutes = window_minutes - total_minutes
    fits = unused_minutes >= 0
    warnings: list[str] = []
    if buffer_value == 0:
        warnings.append("活动流程没有预留缓冲时间")
    if not fits:
        warnings.append(f"活动流程超过时间窗口 {-unused_minutes} 分钟")

    return {
        "event_start": event_start,
        "event_end": event_end,
        "buffer_minutes": buffer_value,
        "items": schedule,
        "stages_minutes": stages_minutes,
        "total_minutes": total_minutes,
        "unused_minutes": unused_minutes,
        "fits_time_window": fits,
        "warnings": warnings,
    }


def _build_schedule(**kwargs: Any) -> str:
    try:
        result = build_schedule_data(**kwargs)
    except ValueError as exc:
        result = {"ok": False, "error": str(exc)}
    return json.dumps(result, ensure_ascii=False, indent=2)


build_schedule_tool = Tool(
    name="build_schedule",
    description=(
        "根据活动起止时间、缓冲时间和带依赖关系的环节列表生成顺序时间表，"
        "检查循环依赖、时间超限，并保留每个环节所需人数。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "event_start": {"type": "string", "description": "HH:MM"},
            "event_end": {"type": "string", "description": "HH:MM，可跨午夜"},
            "buffer_minutes": {"type": "integer", "minimum": 0, "default": 15},
            "stages": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "stage_id": {"type": "string"},
                        "name": {"type": "string"},
                        "duration_minutes": {"type": "integer", "minimum": 1},
                        "dependencies": {"type": "array", "items": {"type": "string"}},
                        "staff_required": {"type": "integer", "minimum": 1},
                    },
                    "required": [
                        "stage_id", "name", "duration_minutes", "dependencies", "staff_required"
                    ],
                },
            },
        },
        "required": ["event_start", "event_end", "stages"],
    },
    run=_build_schedule,
)