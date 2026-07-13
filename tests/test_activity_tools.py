import json

from agent.loop import AgentLoop
from tools.activity_budget import calculate_budget_data, calculate_budget_tool
from tools.activity_schedule import build_schedule_data
from tools.activity_validate import validate_project_data
from tools.base import Tool, ToolRegistry, build_default_registry


def complete_project():
    budget = calculate_budget_data(1000, [{
        "name": "宣纸", "category": "material", "unit_price": 2,
        "quantity": 40, "priority": "required", "price_status": "confirmed",
    }])
    stages = [{
        "stage_id": "sign-in", "name": "签到与布场", "duration_minutes": 165,
        "dependencies": [], "staff_required": 2,
    }]
    schedule = build_schedule_data("13:30", "16:30", stages, 15)
    return {
        "event_id": "event-001", "status": "PLANNING",
        "brief": {
            "activity_type": "书画社春季活动", "goal": "促进成员交流",
            "participants": 40, "budget_limit": 1000, "duration_minutes": 180,
            "event_start": "13:30", "event_end": "16:30", "venue": "校内教室",
        },
        "plan": {
            "theme": "春日墨韵", "objectives": ["交流"], "stages": stages,
            "success_metrics": ["到场率不低于80%"],
        },
        "budget": budget, "schedule": schedule,
        "publicity": {"wechat_article": "春日墨韵活动招募"},
        "outputs": {
            "event_project": {"path": "event_project.json"},
            "activity_plan": {"path": "activity_plan.md"},
        },
    }


def test_domain_tools_are_registered():
    names = build_default_registry().names()
    assert {"calculate_budget", "build_schedule", "validate_project"} <= set(names)


def test_low_budget_is_reported_truthfully():
    result = calculate_budget_data(50, [
        {"name": "茶歇", "category": "food", "unit_price": 5, "quantity": 40},
        {"name": "伴手礼", "category": "gift", "unit_price": 3, "quantity": 40},
    ])
    assert result["total"] == 352
    assert result["remaining"] == -302
    assert result["over_budget"] is True


def test_schedule_exactly_fills_three_hour_window():
    result = build_schedule_data("13:30", "16:30", [{
        "stage_id": "main", "name": "活动", "duration_minutes": 165,
        "dependencies": [], "staff_required": 2,
    }], 15)
    assert result["total_minutes"] == 180
    assert result["unused_minutes"] == 0
    assert result["fits_time_window"] is True


def test_complete_project_validates_and_detects_tampering():
    project = complete_project()
    assert validate_project_data(project)["valid"] is True
    project["budget"]["remaining"] = 999
    result = validate_project_data(project)
    assert result["valid"] is False
    assert "REMAINING_MISMATCH" in {v["code"] for v in result["violations"]}

def test_output_paths_must_be_root_level_contract_names():
    project = complete_project()
    project["outputs"]["event_project"]["path"] = "output/event_project.json"
    project["outputs"]["activity_plan"]["path"] = "output/activity_plan.md"

    result = validate_project_data(project)

    assert result["valid"] is False
    assert [v["code"] for v in result["violations"]].count("INVALID_OUTPUT_PATH") == 2


class ScriptedBackend:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.messages = []

    def chat(self, messages, tools):
        self.messages.append([dict(message) for message in messages])
        return next(self.responses)


def test_activity_can_finish_without_todo(tmp_path):
    backend = ScriptedBackend([{"content": "方案完成", "tool_calls": []}])
    loop = AgentLoop(backend, build_default_registry(), "system", workdir=tmp_path)
    assert loop.run("设计40人活动，预算1000元") == "方案完成"


def test_domain_parameter_error_is_labeled(tmp_path):
    backend = ScriptedBackend([
        {"content": "", "tool_calls": [{"name": "calculate_budget", "arguments": {
            "budget_limit": 100, "items": [{"name": "茶歇", "category": "food",
            "unit_price": -1, "quantity": 2}],
        }}]},
        {"content": "已修正", "tool_calls": []},
    ])
    registry = ToolRegistry()
    registry.register(calculate_budget_tool)
    loop = AgentLoop(backend, registry, "system", workdir=tmp_path)
    assert loop.run("算预算") == "已修正"
    observation = backend.messages[1][-1]["content"]
    assert observation.startswith("[参数错误]")
