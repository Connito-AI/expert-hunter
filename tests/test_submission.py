"""Who may change what in a pull request."""
import subprocess

import pytest

from expert_hunter.submission import Change, changes_from_git, parse_trusted, report, violations

A = "alice"


def v(*changes, author=A, association="CONTRIBUTOR"):
    return violations(author, association, [Change(*c) for c in changes])


def test_one_yaml_in_own_folder_passes():
    assert v(("A", "proposals/alice/exp_finance.yaml")) == []
    assert v(("M", "proposals/alice/exp_finance.yaml")) == []


def test_login_folder_is_case_insensitive():
    assert v(("A", "proposals/Alice/exp_finance.yaml")) == []


def test_someone_elses_folder_fails():
    [msg] = v(("A", "proposals/bob/exp_finance.yaml"))
    assert "`bob`'s folder" in msg


def test_editing_someone_elses_proposal_fails():
    assert "`bob`'s folder" in v(("M", "proposals/bob/exp_finance.yaml"))[0]


@pytest.mark.parametrize("path", [
    "proposals/alice/README.md",
    "proposals/alice/exp_finance.yml",
    "proposals/alice/train.py",
    "proposals/alice/.hidden.yaml",
])
def test_only_yaml_files(path):
    assert "is not a `.yaml` file" in v(("A", path))[0]


@pytest.mark.parametrize("path", [
    "README.md",
    "expert_hunter/schema.py",
    ".github/workflows/validate.yml",
    "examples/alice/exp_finance.yaml",
    "proposals/exp_finance.yaml",
    "proposals/alice/nested/exp_finance.yaml",
])
def test_nothing_outside_own_folder(path):
    assert "outside proposals/<your-login>/" in v(("A", path))[0]


def test_extra_file_alongside_a_valid_proposal_fails():
    found = v(("A", "proposals/alice/exp_finance.yaml"), ("M", "README.md"))
    assert len(found) == 1 and "README.md" in found[0]


def test_one_proposal_per_pull_request():
    found = v(("A", "proposals/alice/exp_a.yaml"), ("A", "proposals/alice/exp_b.yaml"))
    assert "one pull request per proposal" in found[0]


def test_withdrawing_own_proposal_is_allowed():
    assert v(("D", "proposals/alice/exp_finance.yaml")) == []


def test_deleting_someone_elses_proposal_fails():
    assert "`bob`'s folder" in v(("D", "proposals/bob/exp_finance.yaml"))[0]


def test_renaming_out_of_someone_elses_folder_fails():
    """A rename touches both paths; taking over bob's file is not allowed."""
    found = v(("R", "proposals/alice/exp_finance.yaml", "proposals/bob/exp_finance.yaml"))
    assert any("`bob`'s folder" in f for f in found)


def test_renaming_within_own_folder_passes():
    assert v(("R", "proposals/alice/exp_new.yaml", "proposals/alice/exp_old.yaml")) == []


def test_empty_pull_request_fails():
    assert violations(A, "NONE", []) == ["this pull request changes no files"]


@pytest.mark.parametrize("association", ["OWNER", "MEMBER", "COLLABORATOR", "member"])
def test_maintainers_are_exempt(association):
    assert v(("M", "expert_hunter/schema.py"), ("D", "proposals/bob/exp_x.yaml"),
             association=association) == []


@pytest.mark.parametrize("association", ["CONTRIBUTOR", "FIRST_TIME_CONTRIBUTOR", "FIRST_TIMER", "NONE"])
def test_everyone_else_is_bound(association):
    assert v(("M", "README.md"), association=association)


def test_trusted_list_exempts_a_bot_with_no_association():
    """connito-client-dev[bot] opens PRs with author_association NONE."""
    trusted = parse_trusted(" Connito-Client-Dev[bot] , other\n")
    changes = [Change("M", "expert_hunter/schema.py")]
    assert violations("connito-client-dev[bot]", "NONE", changes, trusted) == []
    assert violations("stranger[bot]", "NONE", changes, trusted)
    assert "trusted list" in report("connito-client-dev[bot]", "NONE", [], trusted)


def test_report_wording():
    assert "✅" in report(A, "CONTRIBUTOR", [])
    assert "❌" in report(A, "CONTRIBUTOR", ["x"])
    assert "maintainer" in report(A, "OWNER", [])


def test_changes_from_a_real_git_diff(tmp_path):
    def git(*args):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)
    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    (tmp_path / "proposals" / "bob").mkdir(parents=True)
    (tmp_path / "proposals" / "bob" / "exp_old.yaml").write_text("name: exp_old\nfiller: " + "x" * 200 + "\n")
    (tmp_path / "README.md").write_text("hi\n")
    git("add", "-A")
    git("commit", "-qm", "base")
    git("tag", "base")
    (tmp_path / "proposals" / "alice").mkdir()
    (tmp_path / "proposals" / "alice" / "exp_new.yaml").write_text("name: exp_new\n")
    git("mv", "proposals/bob/exp_old.yaml", "proposals/alice/exp_old.yaml")
    (tmp_path / "README.md").write_text("changed\n")
    git("add", "-A")
    git("commit", "-qm", "pr")

    changes = changes_from_git("base", str(tmp_path))
    assert set(changes) == {
        Change("A", "proposals/alice/exp_new.yaml"),
        Change("R", "proposals/alice/exp_old.yaml", "proposals/bob/exp_old.yaml"),
        Change("M", "README.md"),
    }
    found = violations(A, "CONTRIBUTOR", changes)
    assert any("README.md" in f for f in found)
    assert any("`bob`'s folder" in f for f in found)
    assert any("one pull request per proposal" in f for f in found)
