"""Every proposal in the repo is well-formed, and exports into a cycle-api task."""
import shutil

import pytest
import yaml

from expert_hunter import proposals as P
from expert_hunter.export import render, task_config

ALL = P.proposal_files(P.PROPOSALS_DIR, P.EXAMPLES_DIR)
EXAMPLE = P.EXAMPLES_DIR / "connito-ai" / "exp_biomed_pubmed.yaml"


def test_there_are_the_examples():
    assert {f.stem for f in ALL} >= {"exp_biomed_pubmed", "exp_metamath_reasoning"}


@pytest.mark.parametrize("path", ALL, ids=lambda f: f.stem)
def test_proposal_is_well_formed(path):
    assert P.problems(path) == []


def test_the_whole_tree_is_clean():
    assert P.all_problems(P.PROPOSALS_DIR, P.EXAMPLES_DIR) == []


def copy_to(tmp_path, folder, filename):
    dest = tmp_path / folder / filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(EXAMPLE, dest)
    return dest


def test_file_must_be_named_after_the_task(tmp_path):
    f = copy_to(tmp_path, "connito-ai", "exp_other_name.yaml")
    assert any("must be named after" in p for p in P.problems(f))


def test_folder_must_be_the_proposers_login(tmp_path):
    f = copy_to(tmp_path, "someone-else", "exp_biomed_pubmed.yaml")
    assert any("folder must be the proposer's GitHub login" in p for p in P.problems(f))


def test_login_match_ignores_case(tmp_path):
    f = copy_to(tmp_path, "Connito-AI", "exp_biomed_pubmed.yaml")
    assert P.problems(f) == []


@pytest.mark.parametrize("relpath", [
    "connito-ai/README.md",            # not yaml
    "connito-ai/exp_x.yml",            # .yml is not .yaml
    "connito-ai/sub/exp_x.yaml",       # too deep
    "exp_x.yaml",                      # no login folder
])
def test_layout_rejects_anything_but_login_slash_yaml(tmp_path, relpath):
    root = tmp_path / "proposals"
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x: 1\n")
    assert any("only <github-login>/<task-name>.yaml" in p for p in P.layout_problems(root))


def test_dotfiles_are_ignored(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    (root / ".gitkeep").write_text("")
    assert P.layout_problems(root) == []


def test_task_name_unique_across_folders(tmp_path):
    root = tmp_path / "proposals"
    copy_to(root, "connito-ai", "exp_biomed_pubmed.yaml")
    other = copy_to(root, "alice", "exp_biomed_pubmed.yaml")
    other.write_text(other.read_text().replace("github: connito-ai", "github: alice"))
    assert any("proposed by more than one person (alice, connito-ai)" in p for p in P.all_problems(root))


def test_unparseable_yaml_is_reported(tmp_path):
    f = tmp_path / "alice" / "exp_broken.yaml"
    f.parent.mkdir()
    f.write_text("name: [unclosed\n")
    assert any("not valid YAML" in p for p in P.problems(f))


def test_find_by_task_name():
    assert P.find("exp_metamath_reasoning") == P.EXAMPLES_DIR / "connito-ai" / "exp_metamath_reasoning.yaml"
    assert P.find("exp_nope") is None


@pytest.mark.parametrize("path", ALL, ids=lambda f: f.stem)
def test_export_matches_cycle_api_task_shape(path):
    """The same checks cycle-api's `validate._check_config` makes on a task."""
    proposal = P.load(path)
    config = yaml.safe_load(render(proposal, group_id=99))
    assert config == task_config(proposal, 99)
    assert config["group_id"] == 99
    sources = config["data"]["dataset_sources"]
    assert sources and all(s.get("path") and s.get("split") for s in sources)
    # Each source renders text one way or the other, as in experiment's corpora.
    assert all(bool(s.get("text_column")) ^ bool(s.get("text_template")) for s in sources)
    assert abs(sum(s["weight"] for s in sources) - 1.0) < 1e-9
    # A new corpus is not a registered eval source; the seeded pick would KeyError.
    assert config["data"]["eval_source_seeded_shard_pick"] is False
