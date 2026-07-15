from __future__ import annotations

import unittest  # Python 单元测试框架

from tools.planning import (
    TODO,  # 全局待办事项列表对象
    reset_todo,  # 重置待办事项
    todo_write_tool,  # 写入（创建）待办事项的工具
    update_todo_tool,  # 更新待办事项状态的工具
)


class PlanningToolTests(unittest.TestCase):
    """待办事项（TODO）工具的单元测试。"""

    def setUp(self):
        """每个测试用例前重置 TODO 列表，保证测试隔离。"""
        reset_todo()

    def test_write_todo(self):
        """测试写入待办事项：添加多项，验证数量和初始状态。"""
        result = todo_write_tool.run(
            items=["生成方案", "计算预算", "统一校验"]
        )

        self.assertEqual(len(TODO.items), 3)
        self.assertEqual(TODO.items[0]["status"], "pending")  # 初始状态为 pending
        self.assertIn("生成方案", result)

    def test_update_todo(self):
        """测试更新待办事项状态为 in_progress，检查渲染输出含 [~] 标记。"""
        todo_write_tool.run(items=["计算预算"])

        result = update_todo_tool.run(
            id=1,
            status="in_progress",
        )

        self.assertEqual(TODO.items[0]["status"], "in_progress")
        self.assertIn("[~]", result)  # 进行中的标记

    def test_complete_todo(self):
        """测试完成待办事项：all_done 返回 True，渲染输出含 [x] 标记。"""
        todo_write_tool.run(items=["计算预算"])
        update_todo_tool.run(id=1, status="completed")

        self.assertTrue(TODO.all_done())
        self.assertIn("[x]", TODO.render())  # 已完成标记

    def test_block_todo(self):
        """测试阻塞待办事项：状态设为 blocked，渲染输出含 [!] 标记。"""
        todo_write_tool.run(items=["等待场地审批"])
        update_todo_tool.run(id=1, status="blocked")

        self.assertEqual(TODO.items[0]["status"], "blocked")
        self.assertIn("[!]", TODO.render())  # 阻塞标记

    def test_reset_todo(self):
        """测试重置待办事项：添加后重置，列表应恢复为空。"""
        todo_write_tool.run(items=["计算预算"])
        reset_todo()

        self.assertEqual(TODO.items, [])

    def test_invalid_status_rejected(self):
        """测试无效状态值被拒绝（应抛出 ValueError）。"""
        todo_write_tool.run(items=["计算预算"])

        with self.assertRaises(ValueError):
            update_todo_tool.run(id=1, status="unknown")

    def test_unknown_id_rejected(self):
        """测试不存在的待办项 ID 被拒绝（应抛出 ValueError）。"""
        todo_write_tool.run(items=["计算预算"])

        with self.assertRaises(ValueError):
            update_todo_tool.run(id=999, status="completed")


if __name__ == "__main__":
    unittest.main()