import subprocess

import pytest

from dispatcher.workspace import Workspace, WorkspaceError


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def remote(tmp_path):
    """Remoto bare con main (README) y la rama agent/3-wa (wa.txt)."""
    bare = tmp_path / "remotes" / "maxiar-org" / "qr.git"
    bare.parent.mkdir(parents=True)
    git(tmp_path, "init", "--bare", "-b", "main", str(bare))
    seed = tmp_path / "seed"
    git(tmp_path, "clone", str(bare), str(seed))
    (seed / "README.md").write_text("hola\n")
    git(seed, "add", ".")
    git(seed, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "init")
    git(seed, "push", "origin", "main")
    git(seed, "checkout", "-b", "agent/3-wa")
    (seed / "wa.txt").write_text("wa\n")
    git(seed, "add", ".")
    git(seed, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "wa")
    git(seed, "push", "origin", "agent/3-wa")
    return f"file://{tmp_path / 'remotes'}"


def make(tmp_path, remote_base):
    return Workspace(tmp_path / "projects", remote_base, "maxiar-org", "bot", "bot@example.com")


def test_prepare_issue_clones_default_branch_with_bot_identity(tmp_path, remote):
    path = make(tmp_path, remote).prepare("qr", "issue", 3, None)
    assert path == tmp_path / "projects" / "qr" / "issue-3"
    assert (path / "README.md").read_text() == "hola\n"
    head = subprocess.run(["git", "branch", "--show-current"], cwd=path, capture_output=True, text=True)
    assert head.stdout.strip() == "main"
    email = subprocess.run(["git", "config", "user.email"], cwd=path, capture_output=True, text=True)
    assert email.stdout.strip() == "bot@example.com"


def test_prepare_pr_checks_out_its_branch(tmp_path, remote):
    path = make(tmp_path, remote).prepare("qr", "pr", 7, "agent/3-wa")
    assert (path / "wa.txt").exists()


def test_prepare_again_discards_local_leftovers(tmp_path, remote):
    ws = make(tmp_path, remote)
    path = ws.prepare("qr", "issue", 3, None)
    (path / "README.md").write_text("roto\n")
    (path / "basura.txt").write_text("x")
    ws.prepare("qr", "issue", 3, None)
    assert (path / "README.md").read_text() == "hola\n"
    assert not (path / "basura.txt").exists()


def test_git_error_does_not_leak_token(tmp_path):
    ws = Workspace(
        tmp_path / "projects",
        f"file://{tmp_path}/no-existe-secret-token",
        "maxiar-org",
        "bot",
        "bot@example.com",
    )
    with pytest.raises(WorkspaceError) as exc:
        ws.prepare("qr", "issue", 3, None)
    assert "secret-token" not in str(exc.value)
