"""The real check: every proposal's data streams from the Hub and is usable.

Skipped unless `pytest --network`. Limit it with `--proposal NAME`.
CI runs this for the proposal a pull request adds (job `data-can-run`).
"""
import pytest

from expert_hunter import proposals as P
from expert_hunter.hub import check_proposal

pytestmark = pytest.mark.network


def pytest_generate_tests(metafunc):
    if "proposal_dir" not in metafunc.fixturenames:
        return
    wanted = metafunc.config.getoption("--proposal")
    dirs = P.proposal_dirs(P.PROPOSALS_DIR, P.EXAMPLES_DIR)
    if wanted:
        dirs = [d for d in dirs if d.name in wanted]
    metafunc.parametrize("proposal_dir", dirs, ids=[d.name for d in dirs])


def test_data_can_run(proposal_dir):
    report = check_proposal(P.load(proposal_dir), sample_rows=100)
    assert report.passed, "\n" + report.markdown()
