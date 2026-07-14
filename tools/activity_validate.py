"""EventProject v1.0 统一校验 Tool。"""
from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from typing import Any

from .base import Tool


def _number(value: Any) -> Decimal | None:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return number if number.is_finite() else None


def _add_violation(
    violations: list[dict[str, str]],
    module: str,
    severity: str,
    code: str,
    message: str,
) -> None:
    violations.append({
        "module": module,
        "severity": severity,
        "code": code,
        "message": message,
    })


def validate_project_data(project: dict[str, Any]) -> dict[str, Any]:
    """校验当前策划阶段要求；不检查风险、成员姓名、实际结果或复盘。"""
    if not isinstance(project, dict):
        raise ValueError("project 必须是对象")

    violations: list[dict[str, str]] = []
    checks = {
        "brief": True,
        "plan": True,
        "budget": True,
        "schedule": True,
        "staffing": True,
        "publicity": True,
        "outputs": True,
    }

    brief = project.get("brief")
    if not isinstance(brief, dict):
        brief = {}
        checks["brief"] = False
        _add_violation(violations, "brief", "error", "MISSING_BRIEF", "缺少活动基本需求 brief")

    required_brief = {
        "activity_type": "活动类型",
        "goal": "活动目标",
        "participants": "参与人数",
        "budget_limit": "预算上限",
        "duration_minutes": "活动时长",
        "event_start": "开始时间",
        "event_end": "结束时间",
        "venue": "活动地点",
    }
    for key, label in required_brief.items():
        value = brief.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            checks["brief"] = False
            _add_violation(violations, "brief", "error", f"MISSING_{key.upper()}", f"缺少{label}")

    participants = brief.get("participants")
    if isinstance(participants, bool) or not isinstance(participants, int) or participants <= 0:
        checks["brief"] = False
        _add_violation(violations, "brief", "error", "INVALID_PARTICIPANTS", "participants 必须是正整数")

    duration = brief.get("duration_minutes")
    if isinstance(duration, bool) or not isinstance(duration, int) or duration <= 0:
        checks["brief"] = False
        _add_violation(violations, "brief", "error", "INVALID_DURATION", "duration_minutes 必须是正整数")

    budget_limit = _number(brief.get("budget_limit"))
    if budget_limit is None or budget_limit < 0:
        checks["brief"] = False
        _add_violation(violations, "brief", "error", "INVALID_BUDGET_LIMIT", "budget_limit 必须是非负数字")

    plan = project.get("plan")
    if not isinstance(plan, dict):
        plan = {}
        checks["plan"] = False
        _add_violation(violations, "plan", "error", "MISSING_PLAN", "缺少活动方案 plan")
    if not str(plan.get("theme", "")).strip():
        checks["plan"] = False
        _add_violation(violations, "plan", "error", "MISSING_THEME", "缺少活动主题")
    if not plan.get("objectives"):
        checks["plan"] = False
        _add_violation(violations, "plan", "error", "MISSING_OBJECTIVES", "缺少活动目标列表")
    stages = plan.get("stages")
    if not isinstance(stages, list) or not stages:
        stages = []
        checks["plan"] = False
        _add_violation(violations, "plan", "error", "MISSING_STAGES", "缺少活动环节")
    if not plan.get("success_metrics"):
        checks["plan"] = False
        _add_violation(violations, "plan", "error", "MISSING_SUCCESS_METRICS", "缺少可衡量的成功指标")

    budget = project.get("budget")
    if not isinstance(budget, dict):
        budget = {}
        checks["budget"] = False
        _add_violation(violations, "budget", "error", "MISSING_BUDGET", "缺少预算结果")
    budget_items = budget.get("items")
    if not isinstance(budget_items, list) or not budget_items:
        checks["budget"] = False
        _add_violation(violations, "budget", "error", "MISSING_BUDGET_ITEMS", "预算项目不能为空")
        budget_items = []

    calculated_subtotal = Decimal("0")
    for index, item in enumerate(budget_items, 1):
        if not isinstance(item, dict):
            checks["budget"] = False
            _add_violation(violations, "budget", "error", "INVALID_BUDGET_ITEM", f"第 {index} 个预算项不是对象")
            continue
        unit_price = _number(item.get("unit_price"))
        quantity = _number(item.get("quantity"))
        subtotal = _number(item.get("subtotal"))
        if unit_price is None or quantity is None or unit_price < 0 or quantity < 0:
            checks["budget"] = False
            _add_violation(violations, "budget", "error", "INVALID_BUDGET_ITEM", f"预算项 {index} 的单价或数量非法")
            continue
        expected = unit_price * quantity
        if subtotal is None or abs(subtotal - expected) > Decimal("0.01"):
            checks["budget"] = False
            _add_violation(violations, "budget", "error", "ITEM_SUBTOTAL_MISMATCH", f"预算项 {index} 的小计不等于单价乘数量")
        calculated_subtotal += expected

    stored_subtotal = _number(budget.get("subtotal"))
    if stored_subtotal is None or abs(stored_subtotal - calculated_subtotal) > Decimal("0.01"):
        checks["budget"] = False
        _add_violation(violations, "budget", "error", "BUDGET_SUBTOTAL_MISMATCH", "预算 subtotal 与项目加总不一致")

    reserve = _number(budget.get("reserve"))
    total = _number(budget.get("total"))
    remaining = _number(budget.get("remaining"))
    if reserve is None or reserve < 0 or total is None:
        checks["budget"] = False
        _add_violation(violations, "budget", "error", "INVALID_BUDGET_TOTAL", "预算 reserve 或 total 非法")
    else:
        if abs(total - (calculated_subtotal + reserve)) > Decimal("0.01"):
            checks["budget"] = False
            _add_violation(violations, "budget", "error", "BUDGET_TOTAL_MISMATCH", "预算 total 不等于 subtotal 加 reserve")
        if budget_limit is not None:
            if total > budget_limit:
                checks["budget"] = False
                _add_violation(violations, "budget", "error", "BUDGET_EXCEEDED", f"总预算超过上限 {float(total - budget_limit):g} 元")
            expected_remaining = budget_limit - total
            if remaining is None or abs(remaining - expected_remaining) > Decimal("0.01"):
                checks["budget"] = False
                _add_violation(violations, "budget", "error", "REMAINING_MISMATCH", "预算 remaining 计算错误")

    schedule = project.get("schedule")
    if not isinstance(schedule, dict):
        schedule = {}
        checks["schedule"] = False
        _add_violation(violations, "schedule", "error", "MISSING_SCHEDULE", "缺少排期结果")
    schedule_items = schedule.get("items")
    if not isinstance(schedule_items, list) or not schedule_items:
        schedule_items = []
        checks["schedule"] = False
        _add_violation(violations, "schedule", "error", "MISSING_SCHEDULE_ITEMS", "活动时间表不能为空")
    if schedule.get("fits_time_window") is not True:
        checks["schedule"] = False
        _add_violation(violations, "schedule", "error", "TIME_WINDOW_EXCEEDED", "活动流程未通过时间窗口检查")
    if schedule.get("event_start") != brief.get("event_start") or schedule.get("event_end") != brief.get("event_end"):
        checks["schedule"] = False
        _add_violation(violations, "schedule", "error", "SCHEDULE_WINDOW_MISMATCH", "排期使用的起止时间与 brief 不一致")
    scheduled_total = schedule.get("total_minutes")
    if (
        isinstance(duration, int)
        and duration > 0
        and (
            isinstance(scheduled_total, bool)
            or not isinstance(scheduled_total, int)
            or scheduled_total > duration
        )
    ):
        checks["schedule"] = False
        _add_violation(violations, "schedule", "error", "DURATION_EXCEEDED", "排期总时长超过 brief.duration_minutes")
    buffer_minutes = schedule.get("buffer_minutes")
    if isinstance(buffer_minutes, bool) or not isinstance(buffer_minutes, int) or buffer_minutes <= 0:
        checks["schedule"] = False
        _add_violation(violations, "schedule", "warning", "MISSING_BUFFER", "活动流程未预留正数缓冲时间")

    stage_ids = {str(stage.get("stage_id")) for stage in stages if isinstance(stage, dict)}
    stage_staff = {
        str(stage.get("stage_id")): stage.get("staff_required")
        for stage in stages
        if isinstance(stage, dict)
    }
    scheduled_ids: set[str] = set()
    for index, item in enumerate(schedule_items, 1):
        if not isinstance(item, dict):
            checks["schedule"] = False
            _add_violation(violations, "schedule", "error", "INVALID_SCHEDULE_ITEM", f"第 {index} 个排期项不是对象")
            continue
        stage_id = str(item.get("stage_id", ""))
        scheduled_ids.add(stage_id)
        if not item.get("start") or not item.get("end"):
            checks["schedule"] = False
            _add_violation(violations, "schedule", "error", "MISSING_STAGE_TIME", f"排期项 {stage_id or index} 缺少起止时间")
        if stage_id in stage_staff and item.get("staff_required") != stage_staff[stage_id]:
            checks["staffing"] = False
            _add_violation(violations, "staffing", "error", "SCHEDULE_STAFF_MISMATCH", f"环节 {stage_id} 在方案与排期中的人数不一致")
    if stage_ids and stage_ids != scheduled_ids:
        checks["schedule"] = False
        _add_violation(violations, "schedule", "error", "SCHEDULE_STAGE_MISMATCH", "计划环节与排期环节不一致")

    available_staff = brief.get("available_staff")
    if available_staff is not None and (
        isinstance(available_staff, bool)
        or not isinstance(available_staff, int)
        or available_staff <= 0
    ):
        checks["staffing"] = False
        _add_violation(violations, "staffing", "error", "INVALID_AVAILABLE_STAFF", "available_staff 必须是正整数或 null")
        available_staff = None
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        staff = stage.get("staff_required")
        stage_id = str(stage.get("stage_id", "unknown"))
        if isinstance(staff, bool) or not isinstance(staff, int) or staff <= 0:
            checks["staffing"] = False
            _add_violation(violations, "staffing", "error", "INVALID_STAFF_COUNT", f"环节 {stage_id} 的 staff_required 必须是正整数")
        elif available_staff is not None and staff > available_staff:
            checks["staffing"] = False
            _add_violation(violations, "staffing", "error", "STAFF_CAPACITY_EXCEEDED", f"环节 {stage_id} 需要 {staff} 人，超过可用人数 {available_staff}")

    publicity = project.get("publicity")
    if not isinstance(publicity, dict) or not any(
        str(publicity.get(key, "")).strip()
        for key in ("summary", "wechat_article", "group_notice", "poster_copy")
    ):
        checks["publicity"] = False
        _add_violation(violations, "publicity", "error", "MISSING_PUBLICITY", "至少需要一种宣传内容")

    outputs = project.get("outputs")
    expected_outputs = {
        "event_project": "event_project.json",
        "activity_plan": "activity_plan.md",
    }
    if not isinstance(outputs, dict):
        checks["outputs"] = False
        _add_violation(violations, "outputs", "error", "MISSING_OUTPUTS", "缺少输出文件定义")
    else:
        for key, expected_path in expected_outputs.items():
            spec = outputs.get(key)
            if not isinstance(spec, dict) or spec.get("path") != expected_path:
                checks["outputs"] = False
                _add_violation(violations, "outputs", "error", "INVALID_OUTPUT_PATH", f"{key} 的输出路径必须是 {expected_path}")

    valid = not any(item["severity"] == "error" for item in violations)
    return {
        "valid": valid,
        "hard_checks": checks,
        "violations": violations,
        "validated_at": None,
    }


def _validate_project(project: dict[str, Any]) -> str:
    try:
        result = validate_project_data(project)
    except ValueError as exc:
        result = {"valid": False, "error": str(exc), "violations": []}
    return json.dumps(result, ensure_ascii=False, indent=2)


validate_project_tool = Tool(
    name="validate_project",
    description=(
        "校验 EventProject v1.0 的需求、方案、预算、排期、各环节所需人数、"
        "宣传内容和两个输出文件定义。当前版本不检查风险、具体成员分配和复盘。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "project": {"type": "object", "description": "完整的 EventProject v1.0 对象"},
        },
        "required": ["project"],
    },
    run=_validate_project,
)