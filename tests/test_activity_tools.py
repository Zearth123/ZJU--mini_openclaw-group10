from __future__ import annotations

import unittest

from agent.permissions import check
from pathlib import Path
from tools.activity_budget import calculate_budget_data
from tools.activity_schedule import build_schedule_data
from tools.activity_validate import validate_project_data
from tools.base import build_default_registry


class BudgetTests(unittest.TestCase):
    def test_budget_with_reserve(self):
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
        result = calculate_budget_data(100, [
            {"name": "材料", "category": "material", "unit_price": 100, "quantity": 1}
        ], 0.1)
        self.assertTrue(result["over_budget"])
        self.assertEqual(result["remaining"], -10)

    def test_negative_price_rejected(self):
        with self.assertRaises(ValueError):
            calculate_budget_data(100, [
                {"name": "错误项目", "category": "material", "unit_price": -1, "quantity": 1}
            ])


class ScheduleTests(unittest.TestCase):
    def setUp(self):
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
        result = build_schedule_data("13:30", "16:30", self.stages, 15)
        self.assertEqual([item["stage_id"] for item in result["items"]], ["stage-001", "stage-002"])
        self.assertEqual(result["stages_minutes"], 35)
        self.assertEqual(result["total_minutes"], 50)
        self.assertEqual(result["unused_minutes"], 130)
        self.assertTrue(result["fits_time_window"])

    def test_cycle_rejected(self):
        stages = [
            {"stage_id": "a", "name": "A", "duration_minutes": 10, "dependencies": ["b"], "staff_required": 1},
            {"stage_id": "b", "name": "B", "duration_minutes": 10, "dependencies": ["a"], "staff_required": 1},
        ]
        with self.assertRaisesRegex(ValueError, "循环"):
            build_schedule_data("10:00", "11:00", stages)

    def test_cross_midnight(self):
        stages = [{"stage_id": "a", "name": "夜间环节", "duration_minutes": 60, "dependencies": [], "staff_required": 1}]
        result = build_schedule_data("23:30", "01:00", stages, 10)
        self.assertEqual(result["unused_minutes"], 20)


def valid_project() -> dict:
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
    def test_valid_project(self):
        result = validate_project_data(valid_project())
        self.assertTrue(result["valid"], result["violations"])

    def test_staff_capacity(self):
        project = valid_project()
        project["brief"]["available_staff"] = 2
        result = validate_project_data(project)
        self.assertFalse(result["valid"])
        self.assertIn("STAFF_CAPACITY_EXCEEDED", {v["code"] for v in result["violations"]})

    def test_missing_risk_does_not_fail(self):
        project = valid_project()
        self.assertNotIn("risks", project)
        self.assertTrue(validate_project_data(project)["valid"])

    def test_schedule_window_must_match_brief(self):
        project = valid_project()
        project["schedule"]["event_start"] = "14:00"
        result = validate_project_data(project)
        self.assertFalse(result["valid"])
        self.assertIn("SCHEDULE_WINDOW_MISMATCH", {v["code"] for v in result["violations"]})


class IntegrationTests(unittest.TestCase):
    def test_tools_registered_and_allowed(self):
        registry = build_default_registry()
        for name in ("calculate_budget", "build_schedule", "validate_project"):
            self.assertIn(name, registry.names())
            self.assertEqual(check(name, {}, Path.cwd()), "allow")


if __name__ == "__main__":
    unittest.main()