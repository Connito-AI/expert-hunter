"""The proposal schema accepts what the subnet can run and rejects the rest."""
import copy

import pytest
from pydantic import ValidationError

from expert_hunter.schema import Proposal

VALID = {
    "name": "exp_finance_reports",
    "title": "Financial report reading",
    "proposer": {"github": "someone"},
    "description": "Train an expert on earnings reports and filings to improve FinQA.",
    "data": {
        "dataset_sources": [
            {"path": "org/filings", "split": "train", "weight": 0.5, "text_column": "text"},
            {"path": "allenai/c4", "name": "en", "split": "train", "weight": 0.5, "text_column": "text"},
        ],
    },
    "benchmarks": [{
        "name": "finqa", "harness": "lm_eval", "task": "finqa", "num_fewshot": 0,
        "metric": "exact_match", "higher_is_better": True,
        "dataset": {"path": "ChanceFocus/flare-finqa", "split": "test"},
    }],
    "hypothesis": "FinQA asks numerical questions about filings, and the corpus is those filings.",
    "evidence": "none known",
    "contamination": "FinQA's test split is not part of the filings corpus.",
}


def with_(**changes):
    data = copy.deepcopy(VALID)
    for dotted, value in changes.items():
        *parents, leaf = dotted.split("__")
        node = data
        for p in parents:
            node = node[int(p)] if p.isdigit() else node[p]
        if value is ...:
            del node[leaf]
        else:
            node[int(leaf) if leaf.isdigit() else leaf] = value
    return data


def reason(data) -> str:
    with pytest.raises(ValidationError) as exc:
        Proposal(**data)
    return str(exc.value)


def test_valid_proposal_loads():
    p = Proposal(**VALID)
    assert p.data.sequence_length == 4096
    assert p.data.dataset_sources[0].split == "train"


@pytest.mark.parametrize("name", ["finance", "exp_Finance", "exp__x", "exp_x_", "exp-x", "exp_" + "a" * 40])
def test_bad_names_rejected(name):
    assert "name must look like" in reason(with_(name=name))


def test_existing_task_name_rejected():
    assert "already a task" in reason(with_(name="exp_txt360_c4"))


def test_weights_must_sum_to_one():
    assert "sum to 1.0" in reason(with_(data__dataset_sources__0__weight=0.7))


def test_one_rendering_required():
    assert "not both and not neither" in reason(with_(data__dataset_sources__0__text_column=...))
    both = with_(data__dataset_sources__0__text_template="{a} {b}")
    assert "not both and not neither" in reason(both)


def test_text_template_instead_of_a_column():
    data = with_(data__dataset_sources__0__text_column=...)
    data["data"]["dataset_sources"][0]["text_template"] = "User: {query}\n\nAssistant: {response}"
    source = Proposal(**data).data.dataset_sources[0]
    assert source.template_columns == ["query", "response"]
    assert source.columns_used == ["query", "response"]


@pytest.mark.parametrize("template,message", [
    ("just words", "no {column} placeholder"),
    ("{a} {}", "not a valid format string"),
    ("{a} {b", "not a valid format string"),
])
def test_bad_templates_rejected(template, message):
    data = with_(data__dataset_sources__0__text_column=...)
    data["data"]["dataset_sources"][0]["text_template"] = template
    assert message in reason(data)


def test_hub_path_shape():
    assert "HuggingFace dataset id" in reason(with_(data__dataset_sources__0__path="just-a-name"))


def test_revision_must_be_a_full_sha():
    assert "40-character" in reason(with_(data__dataset_sources__0__revision="main"))


def test_unknown_key_rejected():
    assert "Extra inputs" in reason(with_(data__dataset_sources__0__txt_column="text"))


def test_sequence_length_limited():
    assert "sequence_length" in reason(with_(data__sequence_length=3000))


def test_duplicate_source_rejected():
    data = with_()
    data["data"]["dataset_sources"][0] = dict(data["data"]["dataset_sources"][1])
    assert "listed twice" in reason(data)


def test_lm_eval_benchmark_needs_task_and_shots():
    assert "needs `task`" in reason(with_(benchmarks__0__task=...))
    assert "needs `num_fewshot`" in reason(with_(benchmarks__0__num_fewshot=...))


def test_eval_loss_benchmark_takes_no_task():
    data = with_(benchmarks__0__harness="eval_loss")
    assert "eval_loss has no lm-eval task" in reason(data)
    del data["benchmarks"][0]["task"], data["benchmarks"][0]["num_fewshot"]
    Proposal(**data)


def test_benchmark_cannot_score_on_training_data():
    data = with_(benchmarks__0__dataset={"path": "org/filings", "split": "train"})
    assert "graded on data it trained on" in reason(data)


def test_placeholder_text_rejected():
    assert "description" in reason(with_(description="..."))
    assert "evidence" in reason(with_(evidence="..."))
    assert "evidence" in reason(with_(evidence="...\n"))  # what a `>` block yields


def test_hypothesis_and_evidence_are_required():
    assert "hypothesis" in reason(with_(hypothesis=...))
    assert "hypothesis" in reason(with_(hypothesis="it will"))
    assert "evidence" in reason(with_(evidence=...))


def test_the_light_parts_are_optional():
    Proposal(**VALID)  # no suggested_training, no benchmark `why`, no sequence_length
    assert Proposal(**VALID).data.sequence_length == 4096
    p = Proposal(**with_(suggested_training={"steps": 2000, "batch_size": 512}))
    assert (p.suggested_training.steps, p.suggested_training.batch_size) == (2000, 512)
    assert "steps" in reason(with_(suggested_training={"steps": 0}))
