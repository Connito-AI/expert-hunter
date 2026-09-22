"""Shard tables for the seeded eval pick, and when export turns it on. Offline: the Hub is faked."""
import pytest
import yaml

from expert_hunter import proposals as P
from expert_hunter import shard_table as T
from expert_hunter.export import render, task_config
from expert_hunter.schema import DatasetSource

SHA = "a" * 40
METAMATH = P.EXAMPLES_DIR / "connito-ai" / "exp_metamath_reasoning.yaml"
BIOMED = P.EXAMPLES_DIR / "connito-ai" / "exp_biomed_pubmed.yaml"


@pytest.fixture
def hub(monkeypatch):
    """files[(path, split)] -> [filename]; rows[filename] -> row count."""
    state = {"files": {}, "rows": {}}
    monkeypatch.setattr(T, "resolve_revision", lambda path, revision: revision or SHA)
    monkeypatch.setattr(T, "source_files",
                        lambda path, name, split, sha: state["files"][(path, split)])
    monkeypatch.setattr(T, "parquet_rows", lambda path, sha, f: state["rows"][f])
    return state


def src(path="org/data", **kw):
    return DatasetSource(path=path, split=kw.pop("split", "train"), weight=1.0,
                         text_column="text", **kw)


def test_parquet_source_gets_a_table(hub):
    hub["files"][("org/data", "train")] = ["data/train-0.parquet", "data/train-1.parquet"]
    hub["rows"] = {"data/train-0.parquet": 400_000, "data/train-1.parquet": 399_999}
    p = T.plan(src())
    assert p.seedable and p.revision == SHA
    assert p.table == {"data/train-0.parquet": 400_000, "data/train-1.parquet": 399_999}


def test_a_pinned_revision_is_kept(hub):
    hub["files"][("org/data", "train")] = ["a.parquet"]
    hub["rows"] = {"a.parquet": 50_000}
    assert T.plan(src(revision="b" * 40)).revision == "b" * 40


def test_small_shards_are_left_out(hub):
    hub["files"][("org/data", "train")] = ["big.parquet", "tiny.parquet"]
    hub["rows"] = {"big.parquet": 50_000, "tiny.parquet": T.MIN_HEADROOM_ROWS}
    p = T.plan(src())
    assert p.table == {"big.parquet": 50_000} and p.dropped == ["tiny.parquet"]


def test_all_small_shards_means_no_table(hub):
    hub["files"][("org/data", "train")] = ["tiny.parquet"]
    hub["rows"] = {"tiny.parquet": 10}
    p = T.plan(src())
    assert not p.seedable and "rows or fewer" in p.problem


def test_json_source_cannot_be_tabled(hub):
    hub["files"][("org/data", "train")] = ["chunk/a.jsonl", "chunk/b.jsonl"]
    p = T.plan(src())
    assert not p.seedable and ".jsonl" in p.problem and "not parquet" in p.problem


def test_known_source_needs_no_table(hub):
    p = T.plan(src("allenai/c4", name="en"))
    assert p.known and p.seedable and p.table == {}


def test_export_turns_seeded_pick_on_when_every_source_has_a_policy(hub):
    proposal = P.load(METAMATH)
    hub["files"][("nvidia/OpenMathInstruct-2", "train_1M")] = ["data/train_1M-0.parquet"]
    hub["rows"] = {"data/train_1M-0.parquet": 333_334}
    plans = [T.plan(s) for s in proposal.data.dataset_sources]
    data = task_config(proposal, 9, plans)["data"]
    assert data["eval_source_seeded_shard_pick"] is True
    assert "eval_source_skip_max" not in data
    assert data["dataset_sources"][0]["eval_shard_rows"] == {"data/train_1M-0.parquet": 333_334}
    assert "eval_shard_rows" not in data["dataset_sources"][1]  # c4 is built in
    assert data["eval_source_revision_pin"] == {"nvidia/OpenMathInstruct-2": SHA, "allenai/c4": SHA}
    assert "v0.6.3" in render(proposal, 9, plans)


def test_one_untabled_source_keeps_the_whole_task_on_the_legacy_path(hub):
    proposal = P.load(BIOMED)
    hub["files"][("MedRAG/pubmed", "train")] = ["chunk/a.jsonl"]
    plans = [T.plan(s) for s in proposal.data.dataset_sources]
    out = render(proposal, 9, plans)
    data = yaml.safe_load(out)["data"]
    assert data["eval_source_seeded_shard_pick"] is False
    assert data["eval_source_skip_max"] == 1_000_000
    assert all("eval_shard_rows" not in s for s in data["dataset_sources"])
    assert "MedRAG/pubmed is published as .jsonl" in out


def test_offline_export_is_the_legacy_path():
    proposal = P.load(METAMATH)
    out = render(proposal, 9)
    data = yaml.safe_load(out)["data"]
    assert data["eval_source_seeded_shard_pick"] is False
    assert "--offline" in out
