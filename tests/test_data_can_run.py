"""The real check: every proposal's data streams from the Hub and is usable.

Skipped unless `pytest --network`. Limit it with `--proposal NAME`.
CI runs the same check for the proposal a pull request adds (job `data-can-run`).
"""
import pytest

from expert_hunter import proposals as P
from expert_hunter.hub import check_proposal

pytestmark = pytest.mark.network


def pytest_generate_tests(metafunc):
    if "proposal_file" not in metafunc.fixturenames:
        return
    wanted = metafunc.config.getoption("--proposal")
    files = P.proposal_files(P.PROPOSALS_DIR, P.EXAMPLES_DIR)
    if wanted:
        files = [f for f in files if f.stem in wanted]
    metafunc.parametrize("proposal_file", files, ids=[f.stem for f in files])


def test_data_can_run(proposal_file):
    report = check_proposal(P.load(proposal_file), sample_rows=100)
    assert report.passed, "\n" + report.markdown()
