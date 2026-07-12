from __future__ import annotations

import base64
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from backend.client import DeepSeekBackend
from backend.images import MAX_IMAGE_EDGE, image_block, user_content
from skills.loader import load_skills, skills_catalog


class MultimodalInputTests(unittest.TestCase):
    def test_large_image_is_resized_and_encoded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "large.png"
            Image.new("RGB", (2000, 1000), "white").save(path)

            block = image_block(path)
            raw = base64.b64decode(block["source"]["data"])
            resized_path = Path(directory) / "decoded.png"
            resized_path.write_bytes(raw)

            with Image.open(resized_path) as resized:
                self.assertEqual(resized.size, (MAX_IMAGE_EDGE, 784))
            self.assertEqual(block["type"], "image")
            self.assertEqual(block["source"]["media_type"], "image/png")

    def test_content_blocks_are_translated_for_openai_api(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.png"
            Image.new("RGB", (10, 10), "red").save(path)
            content = user_content("描述图片", [str(path)])

            converted = DeepSeekBackend._to_openai_content(content)

            self.assertEqual(converted[0], {"type": "text", "text": "描述图片"})
            self.assertEqual(converted[1]["type"], "image_url")
            self.assertTrue(converted[1]["image_url"]["url"].startswith("data:image/png;base64,"))

    def test_ui_screenshot_skill_is_loaded_with_its_workflow(self) -> None:
        skills = load_skills()
        skill = next(item for item in skills if item.name == "diagnose-ui-screenshot")

        self.assertIn("提供界面截图并报告显示异常", skill.description)
        self.assertIn("1. 看图定位", skill.body)
        self.assertIn("1. 看图定位", skills_catalog(skills))


if __name__ == "__main__":
    unittest.main()
