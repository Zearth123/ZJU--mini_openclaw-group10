from __future__ import annotations

import unittest

from tools.planning import (
    TODO,
    reset_todo,
    todo_write_tool,
    update_todo_tool,
)


class PlanningToolTests(unittest.TestCase):
    def setUp(self):
        reset_todo()

    def test_write_todo(self):
        result = todo_write_tool.run(
            items=["生成方案", "计算预算", "统一校验"]
        )

        self.assertEqual(len(TODO.items), 3)
        self.assertEqual(TODO.items[0]["status"], "pending")
        self.assertIn("生成方案", result)

    def test_update_todo(self):
        todo_write_tool.run(items=["计算预算"])

        result = update_todo_tool.run(
            id=1,
            status="in_progress",
        )

        self.assertEqual(TODO.items[0]["status"], "in_progress")
        self.assertIn("[~]", result)

    def test_complete_todo(self):
        todo_write_tool.run(items=["计算预算"])
        update_todo_tool.run(id=1, status="completed")

        self.assertTrue(TODO.all_done())
        self.assertIn("[x]", TODO.render())

    def test_block_todo(self):
        todo_write_tool.run(items=["等待场地审批"])
        update_todo_tool.run(id=1, status="blocked")

        self.assertEqual(TODO.items[0]["status"], "blocked")
        self.assertIn("[!]", TODO.render())

    def test_reset_todo(self):
        todo_write_tool.run(items=["计算预算"])
        reset_todo()

        self.assertEqual(TODO.items, [])

    def test_invalid_status_rejected(self):
        todo_write_tool.run(items=["计算预算"])

        with self.assertRaises(ValueError):
            update_todo_tool.run(id=1, status="unknown")

    def test_unknown_id_rejected(self):
        todo_write_tool.run(items=["计算预算"])

        with self.assertRaises(ValueError):
            update_todo_tool.run(id=999, status="completed")


if __name__ == "__main__":
    unittest.main()