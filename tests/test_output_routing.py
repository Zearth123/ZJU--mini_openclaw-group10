from pathlib import Path

from agent.output import bind_output_dir, finalize_artifacts, unbind_output_dir
from mcp.wechat_mp_server import TOOLS
from tools.fs import _write


def test_canonical_planning_artifacts_are_routed_per_run(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    output_dir = tmp_path / "output" / "run-123"
    token = bind_output_dir(output_dir)
    try:
        result = _write("activity_plan.md", "# Plan")
        _write("event_project.json", "{}")
        _write("ordinary.txt", "ordinary")
    finally:
        unbind_output_dir(token)

    assert (output_dir / "activity_plan.md").read_text() == "# Plan"
    assert (output_dir / "event_project.json").read_text() == "{}"
    assert not (tmp_path / "activity_plan.md").exists()
    assert (tmp_path / "ordinary.txt").read_text() == "ordinary"
    assert str(output_dir / "activity_plan.md") in result


def test_wechat_automatic_publish_tools_remain_registered():
    names = {tool["name"] for tool in TOOLS}
    assert {"publish_markdown", "create_draft", "publish_draft"} <= names
    publish = next(tool for tool in TOOLS if tool["name"] == "publish_markdown")
    assert "file_path" in publish["inputSchema"]["properties"]
    assert "publish" in publish["inputSchema"]["properties"]


def test_mcp_paths_are_routed_to_current_output(tmp_path):
    from mcp.client import register_mcp_tools
    from tools.base import ToolRegistry

    class FakeClient:
        arguments = None

        def list_tools(self):
            return [{
                "name": "publish_markdown",
                "description": "",
                "inputSchema": {
                    "type": "object",
                    "properties": {"file_path": {"type": "string"}},
                },
            }]

        def call_tool(self, name, arguments):
            self.arguments = arguments
            return name

    client = FakeClient()
    registry = ToolRegistry()
    register_mcp_tools(registry, client)
    token = bind_output_dir(tmp_path / "output" / "run-mcp")
    try:
        registry.get("mcp__publish_markdown").run(
            file_path="activity_plan.md",
            publish=False,
        )
    finally:
        unbind_output_dir(token)

    assert client.arguments["file_path"] == str(
        (tmp_path / "output" / "run-mcp" / "activity_plan.md").resolve()
    )


def test_root_artifact_is_finalized_into_run_directory(tmp_path):
    output_dir = tmp_path / "output" / "run-finalize"
    (tmp_path / "activity_plan.md").write_text("# fallback")
    token = bind_output_dir(output_dir)
    try:
        moved = finalize_artifacts(tmp_path)
    finally:
        unbind_output_dir(token)

    assert moved == [output_dir / "activity_plan.md"]
    assert (output_dir / "activity_plan.md").read_text() == "# fallback"
    assert not (tmp_path / "activity_plan.md").exists()


def test_publish_prompt_uses_only_wechat_skills_and_latest_artifacts(tmp_path, monkeypatch):
    from backend.web_app import system_prompt

    output_dir = tmp_path / "output" / "prior-run"
    output_dir.mkdir(parents=True)
    plan = output_dir / "activity_plan.md"
    plan.write_text("# latest plan", encoding="utf-8")
    prompt = system_prompt("发布草稿", output_dir)

    assert "Skill: wechat-publish" in prompt
    assert "Skill: gzh-design" in prompt
    assert "Skill: activity-planning" not in prompt
    assert str(plan.resolve()) in prompt
    assert "Do not regenerate the activity plan" in prompt
    assert "create_draft_from_html_file" in prompt
    assert "publish=false" in prompt
    assert "do not call publish_draft" in prompt
    assert "wechat_article.html" in prompt


def test_html_file_draft_preserves_polished_content(tmp_path, monkeypatch):
    from mcp.wechat_mp_server import WeChatClient

    html = '<section style="color: #123456;"><strong>春日墨韵</strong></section>'
    source = tmp_path / "wechat_article.html"
    source.write_text(html, encoding="utf-8")
    client = WeChatClient.__new__(WeChatClient)
    captured = {}

    def fake_create_draft(**kwargs):
        captured.update(kwargs)
        return {"media_id": "draft-123"}

    monkeypatch.setattr(client, "create_draft", fake_create_draft)
    result = client.create_draft_from_html_file(
        str(source), "春日墨韵", thumb_media_id="cover-123"
    )

    assert result["media_id"] == "draft-123"
    assert captured["content"] == html
    assert captured["thumb_media_id"] == "cover-123"
