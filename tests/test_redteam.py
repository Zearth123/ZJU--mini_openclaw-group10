from __future__ import annotations

import unittest
from pathlib import Path

from security.redteam import CASES, render_report, run_case


class RedTeamTests(unittest.TestCase):
    def test_all_four_attack_surfaces_are_blocked_without_crashing(self) -> None:
        results = [run_case(category, prompt, Path.cwd()) for category, prompt in CASES]

        self.assertEqual(len(results), 4)
        self.assertTrue(all(result.status == "已拦截" for result in results))
        self.assertTrue(all(result.answer.startswith("请求已拒绝：") for result in results))
        self.assertIn("<external source=", "\n".join(results[1].observations))

        report = render_report(results)
        for category, _ in CASES:
            self.assertIn(category, report)
        self.assertIn("暴露缺口与改进", report)


if __name__ == "__main__":
    unittest.main()
