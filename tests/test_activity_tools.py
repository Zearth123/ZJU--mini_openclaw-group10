from __future__ import annotations

import unittest  # Python 单元测试框架

from agent.permissions import check  # 权限检查函数
from pathlib import Path  # 路径操作
from tools.activity_budget import calculate_budget_data  # 预算计算核心函数
from tools.activity_schedule import build_schedule_data  # 日程编排核心函数
from tools.activity_validate import validate_project_data  # 项目数据校验函数
from tools.base import build_default_registry  # 构建默认工具注册表
import json  # JSON 序列化/反序列化，用于验证工具返回的 JSON 字符串

class BudgetTests(unittest.TestCase):
    """预算计算工具的单元测试。"""

    def test_budget_with_reserve(self):
        """测试正常预算计算：含备用金比例，验证小计、备用金、总计和剩余金额正确。"""
        result = calculate_budget_data(1000, [
            {
                "name": "材料",
                "category": "material",
                "unit_price": 2.5,
                "quantity": 40,
                "priority": "required",
                "price_status": "confirmed",
            }
        ], 0.1)
        self.assertEqual(result["subtotal"], 100)
        self.assertEqual(result["reserve"], 10)
        self.assertEqual(result["total"], 110)
        self.assertEqual(result["remaining"], 890)
        self.assertFalse(result["over_budget"])

    def test_reserve_can_cause_over_budget(self):
        """测试备用金导致总预算超限的场景。"""
        result = calculate_budget_data(100, [
            {"name": "材料", "category": "material", "unit_price": 100, "quantity": 1}
        ], 0.1)
        self.assertTrue(result["over_budget"])
        self.assertEqual(result["remaining"], -10)

    def test_negative_price_rejected(self):
        """测试负单价被拒绝（应抛出 ValueError）。"""
        with self.assertRaises(ValueError):
            calculate_budget_data(100, [
                {"name": "错误项目", "category": "material", "unit_price": -1, "quantity": 1}
            ])


class ScheduleTests(unittest.TestCase):
    """日程编排工具的单元测试。"""

    def setUp(self):
        """每个测试用例前初始化：定义两个互相关联的阶段，用于测试依赖排序。"""
        self.stages = [
            {
                "stage_id": "stage-002",
                "name": "开场",
                "duration_minutes": 15,
                "dependencies": ["stage-001"],
                "staff_required": 2,
            },
            {
                "stage_id": "stage-001",
                "name": "签到",
                "duration_minutes": 20,
                "dependencies": [],
                "staff_required": 3,
            },
        ]

    def test_dependency_order_and_buffer(self):
        """测试依赖排序正确（stage-001 必须在 stage-002 之前）且缓冲时间计算准确。"""
        result = build_schedule_data("13:30", "16:30", self.stages, 15)
        self.assertEqual([item["stage_id"] for item in result["items"]], ["stage-001", "stage-002"])
        self.assertEqual(result["stages_minutes"], 35)
        self.assertEqual(result["total_minutes"], 50)
        self.assertEqual(result["unused_minutes"], 130)
        self.assertTrue(result["fits_time_window"])

    def test_cycle_rejected(self):
        """测试循环依赖被正确检测并抛出 ValueError（匹配"循环"关键字）。"""
        stages = [
            {"stage_id": "a", "name": "A", "duration_minutes": 10, "dependencies": ["b"], "staff_required": 1},
            {"stage_id": "b", "name": "B", "duration_minutes": 10, "dependencies": ["a"], "staff_required": 1},
        ]
        with self.assertRaisesRegex(ValueError, "循环"):
            build_schedule_data("10:00", "11:00", stages)

    def test_cross_midnight(self):
        """测试跨午夜时段的时间窗口计算（如 23:30 到 01:00）。"""
        stages = [{"stage_id": "a", "name": "夜间环节", "duration_minutes": 60, "dependencies": [], "staff_required": 1}]
        result = build_schedule_data("23:30", "01:00", stages, 10)
        self.assertEqual(result["unused_minutes"], 20)


def valid_project() -> dict:
    """构造一个完整的、合法的活动项目数据，用于校验测试。

    包含基础信息、阶段定义、预算计算、日程编排等完整字段。
    返回的项目应能通过 validate_project_data 的校验。
    """
    stages = [{
        "stage_id": "stage-001",
        "name": "签到",
        "description": "参与者签到",
        "duration_minutes": 20,
        "dependencies": [],
        "staff_required": 3,
        "resource_ids": [],
    }]
    budget = calculate_budget_data(1000, [{
        "name": "签到材料",
        "category": "material",
        "unit_price": 20,
        "quantity": 1,
        "price_status": "confirmed",
    }])
    schedule = build_schedule_data("13:30", "16:30", stages, 15)
    return {
        "schema_version": "1.0",
        "event_id": "event-001",
        "status": "PLANNING",
        "brief": {
            "activity_type": "春季交流活动",
            "goal": "促进交流",
            "participants": 40,
            "budget_limit": 1000,
            "duration_minutes": 180,
            "event_start": "13:30",
            "event_end": "16:30",
            "venue": "校内教室",
            "available_staff": 5,
            "constraints": [],
            "assumptions": [],
        },
        "plan": {
            "theme": "春日相遇",
            "objectives": ["促进交流"],
            "stages": stages,
            "required_resources": [],
            "success_metrics": ["到场率达到 80%"],
        },
        "budget": budget,
        "schedule": schedule,
        "tasks": [],
        "publicity": {"summary": "欢迎报名参加春季交流活动"},
        "outputs": {
            "event_project": {"path": "event_project.json", "generated": False},
            "activity_plan": {"path": "activity_plan.md", "generated": False},
        },
    }


class ValidationTests(unittest.TestCase):
    """项目数据校验工具的单元测试。"""

    def test_valid_project(self):
        """测试一个完整合法的项目数据应通过校验。"""
        result = validate_project_data(valid_project())
        self.assertTrue(result["valid"], result["violations"])

    def test_staff_capacity(self):
        """测试人手不足应触发 STAFF_CAPACITY_EXCEEDED 违规。"""
        project = valid_project()
        project["brief"]["available_staff"] = 2  # 人手设为不足
        result = validate_project_data(project)
        self.assertFalse(result["valid"])
        self.assertIn("STAFF_CAPACITY_EXCEEDED", {v["code"] for v in result["violations"]})

    def test_missing_risk_does_not_fail(self):
        """测试缺少风险预案字段不会导致校验失败（风险非必填）。"""
        project = valid_project()
        self.assertNotIn("risks", project)
        self.assertTrue(validate_project_data(project)["valid"])

    def test_schedule_window_must_match_brief(self):
        """测试日程窗口与活动简要不一致应触发 SCHEDULE_WINDOW_MISMATCH 违规。"""
        project = valid_project()
        project["schedule"]["event_start"] = "14:00"  # 与 brief 中的时间冲突
        result = validate_project_data(project)
        self.assertFalse(result["valid"])
        self.assertIn("SCHEDULE_WINDOW_MISMATCH", {v["code"] for v in result["violations"]})


class IntegrationTests(unittest.TestCase):
    """集成测试：验证工具注册、权限检查和工具执行结果的 JSON 格式。"""

    def test_tools_registered_and_allowed(self):
        """测试三个活动工具已正确注册到默认注册表且权限允许。"""
        registry = build_default_registry()
        for name in ("calculate_budget", "build_schedule", "validate_project"):
            self.assertIn(name, registry.names())  # 工具名在注册表中
            self.assertEqual(check(name, {}, Path.cwd()), "allow")  # 权限允许

    def test_budget_tool_returns_json_string(self):
        """测试预算工具通过注册表调用返回 JSON 字符串，且内容正确。"""
        registry = build_default_registry()
        tool = registry.get("calculate_budget")

        self.assertIsNotNone(tool)

        raw = tool.run(
            budget_limit=1000,
            reserve_ratio=0.1,
            items=[
                {
                    "name": "签到材料",
                    "category": "material",
                    "unit_price": 20,
                    "quantity": 2,
                    "priority": "required",
                    "price_status": "confirmed",
                }
            ],
        )

        self.assertIsInstance(raw, str)  # 验证返回字符串

        result = json.loads(raw)  # 再验证字符串是合法 JSON
        self.assertEqual(result["subtotal"], 40)
        self.assertEqual(result["reserve"], 4)
        self.assertEqual(result["total"], 44)
        self.assertEqual(result["remaining"], 956)

    def test_schedule_tool_returns_json_string(self):
        """测试日程工具通过注册表调用返回 JSON 字符串，且内容正确。"""
        registry = build_default_registry()
        tool = registry.get("build_schedule")

        raw = tool.run(
            event_start="13:30",
            event_end="16:30",
            buffer_minutes=15,
            stages=[
                {
                    "stage_id": "stage-001",
                    "name": "签到",
                    "duration_minutes": 20,
                    "dependencies": [],
                    "staff_required": 2,
                }
            ],
        )

        result = json.loads(raw)

        self.assertEqual(result["event_start"], "13:30")
        self.assertEqual(result["event_end"], "16:30")
        self.assertTrue(result["fits_time_window"])
        self.assertEqual(result["items"][0]["stage_id"], "stage-001")

    def test_validation_tool_returns_json_string(self):
        """测试校验工具通过注册表调用返回 JSON 字符串，且内容正确。"""
        registry = build_default_registry()
        tool = registry.get("validate_project")

        raw = tool.run(project=valid_project())
        result = json.loads(raw)

        self.assertIsInstance(raw, str)
        self.assertTrue(result["valid"], result["violations"])
        self.assertIn("violations", result)

    def test_budget_tool_invalid_arguments_return_error_json(self):
        """测试预算工具处理无效参数时返回包含错误信息的 JSON（非抛异常）。"""
        registry = build_default_registry()
        tool = registry.get("calculate_budget")

        raw = tool.run(
            budget_limit=100,
            items=[
                {
                    "name": "错误项目",
                    "category": "material",
                    "unit_price": -1,
                    "quantity": 1,
                }
            ],
        )

        result = json.loads(raw)

        self.assertFalse(result["ok"])
        self.assertIn("error", result)

    def test_schedule_tool_cycle_returns_error_json(self):
        """测试日程工具检测到循环依赖时返回包含错误信息的 JSON（非抛异常）。"""
        registry = build_default_registry()
        tool = registry.get("build_schedule")

        raw = tool.run(
            event_start="13:30",
            event_end="16:30",
            stages=[
                {
                    "stage_id": "a",
                    "name": "A",
                    "duration_minutes": 10,
                    "dependencies": ["b"],
                    "staff_required": 1,
                },
                {
                    "stage_id": "b",
                    "name": "B",
                    "duration_minutes": 10,
                    "dependencies": ["a"],
                    "staff_required": 1,
                },
            ],
        )

        result = json.loads(raw)

        self.assertFalse(result["ok"])
        self.assertIn("循环", result["error"])

if __name__ == "__main__":
    unittest.main()