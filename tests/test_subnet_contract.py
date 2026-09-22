"""What `export` writes is what the subnet reads.

Loads every proposal's exported config through the subnet's own `ExpertCfg`
(`connito/shared/config.py` in Connito-AI/Connito), so a field renamed or
retyped on either side fails here rather than on miners at a task switch.

Shard tables (`eval_shard_rows`) also go through the subnet's own
`_SourceShardPolicy.from_table` and `_validate_policy` from
`connito/shared/eval_shard_pick.py`, the checks a validator runs before it
picks a shard.

Needs a checkout of the subnet repo: set `CONNITO_SUBNET` to its root. CI's
`subnet-contract` job does that with a sparse checkout of the two files.
Without it the tests skip. With `--network`, one test also builds a real table
from the Hub.

The subnet's config module imports torch and bittensor, which the config
classes do not need to validate data. Those, and any other module that is not
installed here, are replaced by stubs for the duration of the import.
"""
from __future__ import annotations

import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
import types
from pathlib import Path
from unittest import mock

import pytest
import yaml

from expert_hunter import proposals as P
from expert_hunter import shard_table
from expert_hunter.export import render
from expert_hunter.shard_table import SourcePlan

SUBNET = os.environ.get("CONNITO_SUBNET")
CONFIG_PY = Path(SUBNET, "connito", "shared", "config.py") if SUBNET else None
PICK_PY = Path(SUBNET, "connito", "shared", "eval_shard_pick.py") if SUBNET else None
ALL = P.proposal_files(P.PROPOSALS_DIR, P.EXAMPLES_DIR)

pytestmark = pytest.mark.skipif(
    CONFIG_PY is None or not CONFIG_PY.is_file(),
    reason="set CONNITO_SUBNET to a checkout of Connito-AI/Connito",
)

# Imported for real if installed would cost hundreds of MB (torch) for nothing.
ALWAYS_STUB = ("torch", "bittensor", "fsspec", "connito")
MODULE = "connito_subnet_config"
PICK_MODULE = "connito_subnet_eval_shard_pick"


def _stub(name: str) -> types.ModuleType:
    module = types.ModuleType(name)
    module.__getattr__ = lambda attr: mock.MagicMock(name=f"{name}.{attr}")
    module.__path__ = []  # lets `import a.b` find `b` under the stub `a`
    return module


class _StubMissing(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Last on sys.meta_path: any module nothing else can find becomes a stub."""

    def find_spec(self, fullname, path=None, target=None):
        return importlib.machinery.ModuleSpec(fullname, self, is_package=True)

    def create_module(self, spec):
        return _stub(spec.name)

    def exec_module(self, module):
        pass


def _load(module_name: str, path: Path):
    saved = dict(sys.modules)
    finder = _StubMissing()
    for name in ALWAYS_STUB:
        sys.modules[name] = _stub(name)
    sys.meta_path.append(finder)
    try:
        spec = importlib.util.spec_from_file_location(module_name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    finally:
        sys.meta_path.remove(finder)
        for name in set(sys.modules) - set(saved):
            del sys.modules[name]
        sys.modules.update(saved)
    # pydantic resolves the classes' postponed annotations through
    # sys.modules[cls.__module__], so the module itself stays registered.
    sys.modules[module_name] = module
    return module


@pytest.fixture(scope="module")
def subnet():
    yield _load(MODULE, CONFIG_PY)
    sys.modules.pop(MODULE, None)


@pytest.fixture(scope="module")
def pick():
    if not PICK_PY.is_file():
        pytest.skip("the subnet checkout has no eval_shard_pick.py")
    yield _load(PICK_MODULE, PICK_PY)
    sys.modules.pop(PICK_MODULE, None)


def _check_tables(subnet, pick, raw: dict) -> None:
    """What a validator does with a tabled source before it picks a shard."""
    cfg = subnet.ExpertCfg(**raw)  # DataCfg demands a pin for every tabled source
    pins = raw["data"].get("eval_source_revision_pin") or {}
    for source in cfg.data.dataset_sources:
        if source.eval_shard_rows:
            policy = pick._SourceShardPolicy.from_table(
                source.eval_shard_rows, revision=pins.get(source.path),
                max_offset_rows=source.eval_max_offset_rows,
            )
            pick._validate_policy((source.path, source.name), policy)
        elif raw["data"]["eval_source_seeded_shard_pick"]:
            assert (source.path, source.name) in pick._KNOWN_SOURCES, source.path


@pytest.mark.parametrize("path", ALL, ids=lambda f: f.stem)
def test_export_loads_in_the_subnet(subnet, path):
    raw = yaml.safe_load(render(P.load(path), group_id=99))
    cfg = subnet.ExpertCfg(**raw)
    assert cfg.group_id == 99

    # The subnet's configs ignore unknown keys, so a renamed field would load
    # "fine" and silently fall back to its default. Every key export writes
    # must be one the subnet declares.
    assert set(raw) <= set(subnet.ExpertCfg.model_fields)
    assert set(raw["data"]) <= set(subnet.DataCfg.model_fields)
    for source in raw["data"]["dataset_sources"]:
        assert set(source) <= set(subnet.DatasetSourceCfg.model_fields), source["path"]

    # And the values arrive as written.
    for written, loaded in zip(raw["data"]["dataset_sources"], cfg.data.dataset_sources):
        for key, value in written.items():
            assert getattr(loaded, key) == value, (written["path"], key)
    assert cfg.data.sequence_length == raw["data"]["sequence_length"]


def test_known_sources_are_known_to_the_subnet(pick):
    # A source export believes is built in, but the subnet does not, would
    # raise KeyError at the first eval of a seeded task.
    assert shard_table.KNOWN_SOURCES <= set(pick._KNOWN_SOURCES)


def test_headroom_matches_the_subnet(pick):
    default = pick._SourceShardPolicy.__dataclass_fields__["min_headroom_rows"].default
    assert shard_table.MIN_HEADROOM_ROWS == default


def _fake_plans(proposal) -> list[SourcePlan]:
    plans = []
    for i, s in enumerate(proposal.data.dataset_sources):
        sha = f"{i:x}" * 40
        if (s.path, s.name) in shard_table.KNOWN_SOURCES:
            plans.append(SourcePlan(revision=sha[:40], known=True))
        else:
            table = {f"data/{s.split}-{n:05d}-of-00003.parquet": 333_333 for n in range(3)}
            plans.append(SourcePlan(revision=sha[:40], table=table))
    return plans


@pytest.mark.parametrize("path", ALL, ids=lambda f: f.stem)
def test_seeded_export_passes_the_validators_checks(subnet, pick, path):
    proposal = P.load(path)
    raw = yaml.safe_load(render(proposal, group_id=99, plans=_fake_plans(proposal)))
    assert raw["data"]["eval_source_seeded_shard_pick"] is True
    assert set(raw["data"]) <= set(subnet.DataCfg.model_fields)
    for source in raw["data"]["dataset_sources"]:
        assert set(source) <= set(subnet.DatasetSourceCfg.model_fields), source["path"]
    _check_tables(subnet, pick, raw)


@pytest.mark.network
def test_a_real_table_passes_the_validators_checks(subnet, pick):
    """End to end: build the tables from the Hub, then run the subnet's checks."""
    proposal = P.load(P.EXAMPLES_DIR / "connito-ai" / "exp_metamath_reasoning.yaml")
    plans = [shard_table.plan(s) for s in proposal.data.dataset_sources]
    assert all(p.seedable for p in plans), [p.problem for p in plans]
    raw = yaml.safe_load(render(proposal, group_id=99, plans=plans))
    assert raw["data"]["eval_source_seeded_shard_pick"] is True
    _check_tables(subnet, pick, raw)
