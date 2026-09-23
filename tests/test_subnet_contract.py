"""What `export` writes is what the subnet reads.

Loads every proposal's exported config through the subnet's own `ExpertCfg`
(`connito/shared/config.py` in Connito-AI/Connito), so a field renamed or
retyped on either side fails here rather than on miners at a task switch.

Needs a checkout of the subnet repo: set `CONNITO_SUBNET` to its root. CI's
`subnet-contract` job does that with a sparse checkout of the one file.
Without it the tests skip.

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
from expert_hunter.export import render

SUBNET = os.environ.get("CONNITO_SUBNET")
CONFIG_PY = Path(SUBNET, "connito", "shared", "config.py") if SUBNET else None
ALL = P.proposal_files(P.PROPOSALS_DIR, P.EXAMPLES_DIR)

pytestmark = pytest.mark.skipif(
    CONFIG_PY is None or not CONFIG_PY.is_file(),
    reason="set CONNITO_SUBNET to a checkout of Connito-AI/Connito",
)

# Imported for real if installed would cost hundreds of MB (torch) for nothing.
ALWAYS_STUB = ("torch", "bittensor", "fsspec", "connito")
MODULE = "connito_subnet_config"


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


@pytest.fixture(scope="module")
def subnet():
    saved = dict(sys.modules)
    finder = _StubMissing()
    for name in ALWAYS_STUB:
        sys.modules[name] = _stub(name)
    sys.meta_path.append(finder)
    try:
        spec = importlib.util.spec_from_file_location(MODULE, CONFIG_PY)
        module = importlib.util.module_from_spec(spec)
        sys.modules[MODULE] = module
        spec.loader.exec_module(module)
    finally:
        sys.meta_path.remove(finder)
        for name in set(sys.modules) - set(saved):
            del sys.modules[name]
        sys.modules.update(saved)
    # pydantic resolves the classes' postponed annotations through
    # sys.modules[cls.__module__], so the module itself stays registered.
    sys.modules[MODULE] = module
    yield module
    sys.modules.pop(MODULE, None)


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
