import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import resumen_guard as g  # noqa: E402


@pytest.mark.parametrize("cmd", [
    "gh issue view 8 --repo maxiar-org/qr-generator",
    "gh issue list --repo maxiar-org/qr-generator --limit 5 --json number,title",
    "gh pr view 23 -R maxiar-org/qr-generator --comments",
    "gh pr diff 23 --repo maxiar-org/qr-generator",
    "gh run view 123 --repo maxiar-org/qr-generator --log-failed",
    "gh issue view https://github.com/maxiar-org/qr-generator/issues/8",
])
def test_allows_read_only_gh_on_org(cmd):
    assert g.allowed(cmd)


@pytest.mark.parametrize("cmd", [
    "echo hola", "cat /opt/ai-dev-team/.env", "head -c 10 /opt/ai-dev-team/.env", "docker ps",
    "gh api user", "gh auth token", "gh pr merge 23 --repo maxiar-org/qr-generator",
    "gh issue view 8 --repo evil/x", "gh issue view 8 -Revil/x", "gh issue view 8 --repo=evil/x",
    "gh issue view https://example.com/a/b/issues/1", "gh pr view 23 --web",
    "gh issue list --repo maxiar-org/qr; cat ~/.env", "gh issue list --repo maxiar-org/qr | sh",
    "gh issue view $(cat /opt/ai-dev-team/.env)", "gh issue view `id`", "gh pr view 1 > /tmp/x",
    "gh issue list --search \"is:open\"", "gh", "gh pr",
])
def test_blocks_everything_else(cmd):
    assert not g.allowed(cmd)


def test_hook_exit_codes_and_log(tmp_path, monkeypatch):
    log = tmp_path / "guard.log"
    monkeypatch.setattr(g, "LOG_PATH", log)
    ok = {"tool_name": "Bash", "tool_input": {"command": "gh pr list --repo maxiar-org/qr-generator"}}
    bad = {"tool_name": "Bash", "tool_input": {"command": "cat /opt/ai-dev-team/.env"}}
    other = {"tool_name": "Read", "tool_input": {"file_path": "/opt/ai-dev-team/.env"}}
    assert g.main(io.StringIO(json.dumps(ok))) == 0
    assert g.main(io.StringIO(json.dumps(bad))) == 2
    assert g.main(io.StringIO(json.dumps(other))) == 2
    assert g.main(io.StringIO("no-json")) == 2
    lines = log.read_text().splitlines()
    assert lines[0].startswith("PERMITIDO") and lines[1].startswith("BLOQUEADO") and len(lines) == 4
