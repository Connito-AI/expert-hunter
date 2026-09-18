"""Every proposal in the repo is well-formed, and exports into a cycle-api task."""
import shutil

import pytest
import yaml

from expert_hunter import proposals as P
from expert_hunter.export import render, task_config

ALL = P.proposal_dirs(P.PROPOSALS_DIR, P.EXAMPLES_DIR)


def test_template_is_not_a_proposal():
    assert "_template" not in {d.name for d in ALL}


def test_there_is_at_least_the_example():
    assert any(d.parent == P.EXAMPLES_DIR for d in ALL)


@pytest.mark.parametrize("proposal_dir", ALL, ids=lambda d: d.name)
def test_proposal_is_well_formed(proposal_dir):
    assert P.problems(proposal_dir) == []


def test_names_are_unique_across_the_repo():
    assert P.all_problems(P.PROPOSALS_DIR, P.EXAMPLES_DIR) == []


def test_directory_must_match_name(tmp_path):
    bad = tmp_path / "exp_other_name"
    shutil.copytree(P.EXAMPLES_DIR / "exp_biomed_pubmed", bad)
    assert any("directory name must equal" in p for p in P.problems(bad))


def test_stray_files_are_flagged(tmp_path):
    d = tmp_path / "exp_biomed_pubmed"
    shutil.copytree(P.EXAMPLES_DIR / "exp_biomed_pubmed", d)
    (d / "train.py").write_text("print('hi')")
    assert any("only proposal.yaml" in p for p in P.problems(d))


def test_unparseable_yaml_is_reported(tmp_path):
    d = tmp_path / "exp_broken"
    d.mkdir()
    (d / "proposal.yaml").write_text("name: [unclosed\n")
    assert any("not valid YAML" in p for p in P.problems(d))


@pytest.mark.parametrize("proposal_dir", ALL, ids=lambda d: d.name)
def test_export_matches_cycle_api_task_shape(proposal_dir):
    """The same checks cycle-api's `validate._check_config` makes on a task."""
    proposal = P.load(proposal_dir)
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
