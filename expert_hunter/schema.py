"""What a task proposal is.

A proposal is one `proposals/<github-login>/<name>.yaml`. It says what the subnet
should train a new expert on (`data`) and how we will know the expert is any
good (`benchmarks`). Everything else a running task needs — the group id, the
expert assignment, batch geometry — is the owner's job once the proposal wins,
so it is deliberately not asked for here.

The `data` block mirrors `data:` in cycle-api's
`configs/tasks/<name>/config.yaml` (`path`, `name`, `split`, `weight`,
`text_column`), so an accepted proposal exports into a task payload without
translation (see `expert_hunter.export`). A source may instead render several
columns into training text with `text_template`, which is the experiment repo's
`render.cpt.text_template` — a mix of corpora, each rendered its own way, is how
that repo's capability rows are built.

Strict by design: `extra="forbid"` means a typo'd key fails the check in the PR,
not silently later.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Task names that already exist on the subnet (cycle-api configs/tasks/ and the
# group ids its task configs record as taken). A proposal may not reuse one: the
# name becomes the task directory, and two tasks with one name cannot both be
# scheduled.
TAKEN_NAMES = frozenset({
    "exp_math",
    "exp_dummy",
    "exp_c4_p02",
    "exp_legal",
    "exp_nemotron_c4",
    "exp_txt360_c4",
})

NAME_RE = re.compile(r"^exp_[a-z0-9]+(?:_[a-z0-9]+)*$")
HUB_PATH_RE = re.compile(r"^[A-Za-z0-9][\w.-]*/[\w.-]+$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
# `{column}` placeholders in a text_template, ignoring `{{` escapes.
TEMPLATE_FIELD_RE = re.compile(r"(?<!\{)\{([^{}]+)\}")

# The subnet trains at these sequence lengths; anything else would need a code
# change on miners, which a proposal cannot ask for.
SEQUENCE_LENGTHS = (1024, 2048, 4096)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _hub_path(value: str) -> str:
    if not HUB_PATH_RE.match(value):
        raise ValueError(f"{value!r} is not a HuggingFace dataset id like 'org/name'")
    return value


class DatasetSource(_Strict):
    """One training corpus — the same shape as cycle-api's `dataset_sources`."""

    path: str
    # The HF *config* (what `load_dataset(path, name)` calls `name`), e.g. "en"
    # for allenai/c4. Leave it out when the dataset has only a default config.
    name: str | None = None
    # Must be spelled out: a dataset whose only split is not `train` makes the
    # miner's loader die with KeyError: 'train' (this happened on exp_txt360_c4).
    split: str = "train"
    weight: float = Field(gt=0, le=1)
    # How this corpus becomes training text. Exactly one of the two, the same
    # choice the experiment repo's `corpora/<name>/dataset.yaml` offers:
    #
    #   text_column   — the column IS the text (`pubmed`: `contents`).
    #   text_template — several columns rendered into one string, with
    #                   `{column}` placeholders. This is experiment's
    #                   `render.cpt.text_template`, and it is what lets a
    #                   question/answer corpus be trained on without being
    #                   re-exported first (`metamathqa`: 'User: {query}\n\n
    #                   Assistant: {response}').
    text_column: str | None = None
    text_template: str | None = None
    # Optional pin to a dataset commit. Recorded so the exact data that was
    # checked travels with the task.
    revision: str | None = None
    license: str | None = None

    @field_validator("path")
    @classmethod
    def _path(cls, value: str) -> str:
        return _hub_path(value)

    @field_validator("revision")
    @classmethod
    def _sha(cls, value: str | None) -> str | None:
        if value is not None and not SHA_RE.match(value):
            raise ValueError("revision must be a full 40-character commit sha")
        return value

    @model_validator(mode="after")
    def _one_rendering(self) -> "DatasetSource":
        if bool(self.text_column) == bool(self.text_template):
            raise ValueError(
                f"{self.path}: set either `text_column` (the column is the text) or "
                "`text_template` (several columns rendered into one), not both and not neither"
            )
        if self.text_template:
            if not self.template_columns:
                raise ValueError(
                    f"{self.path}: text_template has no {{column}} placeholder — "
                    "use text_column if the text is one column"
                )
            # `str.format` on a row dict is what renders this, so a stray brace
            # would raise mid-run rather than here.
            try:
                self.text_template.format(**{c: "" for c in self.template_columns})
            except (IndexError, KeyError, ValueError) as exc:
                raise ValueError(f"{self.path}: text_template is not a valid format string ({exc})")
        return self

    @property
    def template_columns(self) -> list[str]:
        """The `{column}` names a template reads, in order of first use."""
        if not self.text_template:
            return []
        seen: list[str] = []
        for match in TEMPLATE_FIELD_RE.finditer(self.text_template):
            field = match.group(1).split(".")[0].split("[")[0].strip()
            if field and field not in seen:
                seen.append(field)
        return seen

    @property
    def columns_used(self) -> list[str]:
        return [self.text_column] if self.text_column else self.template_columns


class Data(_Strict):
    dataset_sources: list[DatasetSource] = Field(min_length=1, max_length=4)
    sequence_length: int = 1024

    @field_validator("sequence_length")
    @classmethod
    def _seq_len(cls, value: int) -> int:
        if value not in SEQUENCE_LENGTHS:
            raise ValueError(f"sequence_length must be one of {SEQUENCE_LENGTHS}")
        return value

    @model_validator(mode="after")
    def _mix(self) -> "Data":
        total = sum(s.weight for s in self.dataset_sources)
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"dataset_sources weights must sum to 1.0 (they sum to {total:g})")
        seen = set()
        for s in self.dataset_sources:
            key = (s.path, s.name, s.split)
            if key in seen:
                raise ValueError(f"dataset source {key} is listed twice")
            seen.add(key)
        return self


class HubSplit(_Strict):
    """Where a benchmark's scored items live on the Hub."""

    path: str
    name: str | None = None
    split: str

    @field_validator("path")
    @classmethod
    def _path(cls, value: str) -> str:
        return _hub_path(value)


class Benchmark(_Strict):
    """How the trained expert is scored.

    `lm_eval` — a task in EleutherAI's lm-evaluation-harness, run at the named
    few-shot count. This is what the experiment repo's `configs/benchmarks/`
    entries are, and the preferred kind: its number is comparable to published
    ones.

    `eval_loss` — held-out next-token loss on `dataset`. For domains with no
    good answer-scored benchmark. Only comparable across runs on the same data.
    """

    name: str
    harness: Literal["lm_eval", "eval_loss"]
    task: str | None = None
    num_fewshot: int | None = Field(default=None, ge=0)
    metric: str
    higher_is_better: bool
    dataset: HubSplit
    why: str = Field(min_length=20)

    @model_validator(mode="after")
    def _harness_fields(self) -> "Benchmark":
        if self.harness == "lm_eval":
            if not self.task:
                raise ValueError(f"benchmark {self.name!r}: an lm_eval benchmark needs `task`")
            if self.num_fewshot is None:
                raise ValueError(f"benchmark {self.name!r}: an lm_eval benchmark needs `num_fewshot`")
        elif self.task or self.num_fewshot is not None:
            raise ValueError(
                f"benchmark {self.name!r}: eval_loss has no lm-eval task or few-shot count; "
                "remove `task` / `num_fewshot`"
            )
        return self


class Proposer(_Strict):
    github: str
    contact: str | None = None


class Proposal(_Strict):
    name: str
    title: str = Field(min_length=5, max_length=80)
    proposer: Proposer
    summary: str = Field(min_length=20)
    # Why the subnet should spend a training window on this.
    motivation: str = Field(min_length=50)
    data: Data
    benchmarks: list[Benchmark] = Field(min_length=1, max_length=5)
    # How you know the benchmark's scored items are not in the training data.
    contamination: str = Field(min_length=20)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        if not NAME_RE.match(value) or len(value) > 40:
            raise ValueError(
                "name must look like exp_<words> (lowercase letters, digits, single "
                "underscores, at most 40 characters)"
            )
        if value in TAKEN_NAMES:
            raise ValueError(f"{value!r} is already a task on the subnet; pick another name")
        return value

    @model_validator(mode="after")
    def _benchmarks_are_held_out(self) -> "Proposal":
        names = [b.name for b in self.benchmarks]
        if len(set(names)) != len(names):
            raise ValueError("benchmark names must be unique")
        trained = {(s.path, s.name, s.split) for s in self.data.dataset_sources}
        for b in self.benchmarks:
            if (b.dataset.path, b.dataset.name, b.dataset.split) in trained:
                raise ValueError(
                    f"benchmark {b.name!r} scores on {b.dataset.path} split "
                    f"{b.dataset.split!r}, which is also a training source — "
                    "the expert would be graded on data it trained on"
                )
        return self
