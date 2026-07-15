from agent.permissions import check


def test_permissions_keep_paths_inside_workspace(tmp_path):
    assert check("read", {"path": "plan.md"}, tmp_path) == "allow"
    assert check("write", {"path": "plan.md"}, tmp_path) == "confirm"
    assert check("write", {"path": tmp_path.parent / "outside.md"}, tmp_path) == "deny"


def test_domain_and_mcp_permissions(tmp_path):
    assert check("calculate_budget", {}, tmp_path) == "allow"
    assert check("mcp__read_text_file", {}, tmp_path) == "allow"
    assert check("mcp__write_file", {}, tmp_path) == "confirm"
    assert check("bash", {"command": "rm -rf build"}, tmp_path) == "deny"



def test_safe_shell_commands_are_allowed_conservatively(tmp_path):
    for command in (
        "pwd", "ls -la", "rg TODO agent | head -20", "git status --short",
        "find . -maxdepth 2 -type f", "sed -n '1,20p' README.md",
    ):
        assert check("bash", {"command": command}, tmp_path) == "allow"

    for command in (
        "python3 -c 'print(1)'", "git checkout main", "sed -i s/a/b/ file",
        "find . -delete", "cat a > b", "echo $(whoami)",
    ):
        assert check("bash", {"command": command}, tmp_path) == "confirm"


def test_planning_artifact_write_is_allowed_inside_run_output(tmp_path):
    from agent.output import bind_output_dir, unbind_output_dir

    token = bind_output_dir(tmp_path / "output" / "run-1")
    try:
        assert check("write", {"path": "activity_plan.md"}, tmp_path) == "allow"
        assert check("edit", {"path": "event_project.json"}, tmp_path) == "allow"
        assert check("write", {"path": "source.py"}, tmp_path) == "confirm"
    finally:
        unbind_output_dir(token)


def test_gzh_validation_and_preview_are_auto_allowed_only_for_run_output(tmp_path):
    from agent.output import bind_output_dir, unbind_output_dir

    output_dir = tmp_path / "output" / "run-gzh"
    output_dir.mkdir(parents=True)
    html = output_dir / "wechat_article.html"
    html.write_text("<section></section>", encoding="utf-8")
    validator = tmp_path / "skills/gzh-design/scripts/validate_gzh_html.py"
    preview = tmp_path / "skills/gzh-design/scripts/wrap_preview.py"
    validator.parent.mkdir(parents=True)
    validator.write_text("", encoding="utf-8")
    preview.write_text("", encoding="utf-8")

    token = bind_output_dir(output_dir)
    try:
        assert check(
            "bash",
            {"command": "python3 skills/gzh-design/scripts/validate_gzh_html.py output/run-gzh/wechat_article.html"},
            tmp_path,
        ) == "allow"
        assert check(
            "bash",
            {"command": "skills/gzh-design/scripts/wrap_preview.py output/run-gzh/wechat_article.html"},
            tmp_path,
        ) == "allow"
        assert check(
            "bash",
            {"command": "python3 -c 'print(1)'"},
            tmp_path,
        ) == "confirm"
        assert check(
            "bash",
            {"command": "python3 skills/gzh-design/scripts/validate_gzh_html.py ../outside.html"},
            tmp_path,
        ) == "confirm"
    finally:
        unbind_output_dir(token)


def test_harmless_stderr_redirect_does_not_require_approval(tmp_path):
    assert check("bash", {"command": "ls references/ 2>/dev/null"}, tmp_path) == "allow"
    assert check("bash", {"command": "cat README.md 2>&1"}, tmp_path) == "allow"
