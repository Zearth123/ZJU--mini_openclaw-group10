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
