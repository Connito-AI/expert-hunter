"""The data check's verdicts, with the Hub stubbed out (no network)."""
import pytest

from expert_hunter import hub
from expert_hunter import proposals as P


@pytest.fixture
def proposal():
    return P.load(P.EXAMPLES_DIR / "connito-ai" / "exp_biomed_pubmed.yaml")


def fake(monkeypatch, rows_by_path, info_by_path=None):
    info_by_path = info_by_path or {}
    monkeypatch.setattr(hub, "hub_info", lambda path, revision=None, timeout=0: info_by_path.get(path, {"id": path}))
    monkeypatch.setattr(hub, "viewer_splits", lambda path, timeout=0: None)

    def stream(path, name, split, revision, n, timeout):
        rows = rows_by_path[path]
        if isinstance(rows, Exception):
            raise rows
        return rows[:n]
    monkeypatch.setattr(hub, "_stream_rows", stream)


LONG = "x" * 300


def good_rows(col):
    return [{col: f"{i:05d} {LONG}"} for i in range(50)]


def all_good(proposal):
    rows = {s.path: good_rows(s.text_column) for s in proposal.data.dataset_sources}
    rows.update({b.dataset.path: [{"question": "q"}] for b in proposal.benchmarks})
    return rows


def messages(report, level):
    return " ".join(f.message for f in report.findings if f.level == level)


def test_good_data_passes(monkeypatch, proposal):
    fake(monkeypatch, all_good(proposal))
    report = hub.check_proposal(proposal)
    assert report.passed, report.markdown()
    assert "The data can run" in report.markdown()


def test_missing_text_column_fails(monkeypatch, proposal):
    rows = all_good(proposal)
    rows["MedRAG/pubmed"] = [{"title": LONG}] * 10
    fake(monkeypatch, rows)
    report = hub.check_proposal(proposal)
    assert not report.passed
    assert "no column 'contents'" in messages(report, "error")


def test_non_text_column_fails(monkeypatch, proposal):
    rows = all_good(proposal)
    rows["MedRAG/pubmed"] = [{"contents": ["a", "list"]}] * 10
    fake(monkeypatch, rows)
    assert "is not text" in messages(hub.check_proposal(proposal), "error")


def test_template_source_is_rendered(monkeypatch):
    """A question/answer corpus passes when its template renders usable text."""
    proposal = P.load(P.EXAMPLES_DIR / "connito-ai" / "exp_metamath_reasoning.yaml")
    rows = {"nvidia/OpenMathInstruct-2": [{"problem": f"problem {i}", "generated_solution": LONG}
                                          for i in range(50)],
            "allenai/c4": good_rows("text"),
            "openai/gsm8k": [{"question": "q", "answer": "a"}]}
    fake(monkeypatch, rows)
    report = hub.check_proposal(proposal)
    assert report.passed, report.markdown()
    assert "text_template over 'problem', 'generated_solution'" in messages(report, "ok")


def test_template_column_missing_fails(monkeypatch):
    proposal = P.load(P.EXAMPLES_DIR / "connito-ai" / "exp_metamath_reasoning.yaml")
    rows = {"nvidia/OpenMathInstruct-2": [{"problem": LONG}] * 10,
            "allenai/c4": good_rows("text"),
            "openai/gsm8k": [{"question": "q"}]}
    fake(monkeypatch, rows)
    assert "no column 'generated_solution'" in messages(hub.check_proposal(proposal), "error")


def test_mostly_short_rows_fail(monkeypatch, proposal):
    rows = all_good(proposal)
    rows["MedRAG/pubmed"] = [{"contents": f"short {i}"} for i in range(50)]
    fake(monkeypatch, rows)
    assert "under 200 characters" in messages(hub.check_proposal(proposal), "error")


def test_repeated_rows_fail(monkeypatch, proposal):
    rows = all_good(proposal)
    rows["MedRAG/pubmed"] = [{"contents": LONG}] * 50
    fake(monkeypatch, rows)
    assert "share their first 200" in messages(hub.check_proposal(proposal), "error")


def test_gated_training_data_only_warns(monkeypatch, proposal):
    fake(monkeypatch, all_good(proposal), {"MedRAG/pubmed": {"id": "MedRAG/pubmed", "gated": "manual"}})
    report = hub.check_proposal(proposal)
    assert report.passed
    assert "is gated" in messages(report, "warning")
    assert "rows were not checked" in messages(report, "warning")


def test_gated_benchmark_only_warns(monkeypatch, proposal):
    path = proposal.benchmarks[0].dataset.path
    fake(monkeypatch, all_good(proposal), {path: {"id": path, "gated": "auto"}})
    report = hub.check_proposal(proposal)
    assert report.passed
    assert "is gated" in messages(report, "warning")


def test_single_file_json_corpus_warns(monkeypatch, proposal):
    info = {"MedRAG/pubmed": {"id": "MedRAG/pubmed", "siblings": [
        {"rfilename": "README.md"}, {"rfilename": "MetaMathQA-395K.json"}]}}
    fake(monkeypatch, all_good(proposal), info)
    report = hub.check_proposal(proposal)
    assert report.passed
    assert "cannot read a piece at a time" in messages(report, "warning")


def test_sharded_parquet_corpus_does_not_warn(monkeypatch, proposal):
    info = {"MedRAG/pubmed": {"id": "MedRAG/pubmed", "siblings": [
        {"rfilename": "README.md"}, {"rfilename": "data/train-00000.parquet"},
        {"rfilename": "data/train-00001.parquet"}]}}
    fake(monkeypatch, all_good(proposal), info)
    assert messages(hub.check_proposal(proposal), "warning") == ""


def test_unloadable_split_fails(monkeypatch, proposal):
    rows = all_good(proposal)
    rows["MedRAG/pubmed"] = KeyError("train")
    fake(monkeypatch, rows)
    assert "cannot be streamed" in messages(hub.check_proposal(proposal), "error")


def test_slow_source_is_an_error(monkeypatch, proposal):
    rows = all_good(proposal)
    rows["MedRAG/pubmed"] = hub._Timeout("streaming took too long")
    fake(monkeypatch, rows)
    assert "dataloader would stall" in messages(hub.check_proposal(proposal), "error")


def test_row_stats():
    stats = hub._row_stats(["a" * 5000, "b" * 300, "", ""], 1024)
    assert stats["rows"] == 4
    assert stats["short_share"] == 0.5
    assert stats["long_share"] == 0.25
    assert stats["dup_share"] == 0.0
