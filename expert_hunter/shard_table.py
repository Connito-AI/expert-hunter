"""Eval shard tables, so an exported task can use the subnet's seeded shard pick.

Validators sample eval rows one of two ways, chosen per task by
`data.eval_source_seeded_shard_pick`:

- **seeded shard pick** (on): each round picks one shard file and an offset
  inside it from the round's seed, so over time every row of every shard is
  reachable. A source needs a policy: either one built into the subnet
  (`eval_shard_pick._KNOWN_SOURCES`, mirrored in `KNOWN_SOURCES` below), or,
  since connito v0.6.3, a table shipped with the task — `eval_shard_rows`, the
  row count of every shard file at one pinned commit.
- **legacy** (off): shuffle + skip, which only ever reaches the first rows of
  each shard.

The switch is per task, not per source, so seeded pick is only possible when
EVERY source has a policy. This module builds the tables: it resolves each
source's files the way `datasets` does (`load_dataset_builder(...).config.
data_files[split]`), pins the commit, and reads each parquet file's row count
from its footer (a range request, no download). A source that is not parquet
cannot get a table — JSON has no footer, and counting it means reading all of
it — so a task containing one stays on the legacy path, and `plan` says why.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from expert_hunter.schema import DatasetSource

# `eval_shard_pick._SourceShardPolicy.min_headroom_rows`: rows that must remain
# after the offset lands. The subnet refuses a table listing a shard with this
# many rows or fewer, so such shards are left out.
MIN_HEADROOM_ROWS = 10_000

# `eval_shard_pick._KNOWN_SOURCES`: (path, name) pairs the subnet has a policy
# for in code. They need no table. tests/test_subnet_contract.py checks this
# is a subset of the subnet's registry.
KNOWN_SOURCES = frozenset({
    ("allenai/c4", "en"),
    ("nvidia/Nemotron-CC-Math-v1", "4plus"),
    ("joelniklaus/Multi_Legal_Pile", "all_all"),
})

SHA_RE = re.compile(r"^[0-9a-f]{40}$")


@dataclass
class SourcePlan:
    """How one source is sampled for eval."""

    revision: str                                  # commit sha everything was measured at
    known: bool = False                            # the subnet has a built-in policy
    table: dict[str, int] = field(default_factory=dict)  # eval_shard_rows
    dropped: list[str] = field(default_factory=list)     # shards too small to list
    problem: str | None = None                     # why this source cannot be tabled

    @property
    def seedable(self) -> bool:
        return self.known or bool(self.table)


def resolve_revision(path: str, revision: str | None) -> str:
    if revision and SHA_RE.match(revision):
        return revision
    from huggingface_hub import HfApi

    return HfApi().dataset_info(path, revision=revision or "main").sha


def source_files(path: str, name: str | None, split: str, sha: str) -> list[str]:
    """The repo-relative files `load_dataset(path, name, split=split)` reads."""
    from datasets import load_dataset_builder

    files = load_dataset_builder(path, name, revision=sha).config.data_files[split]
    prefix = f"hf://datasets/{path}@{sha}/"
    return sorted(str(f).removeprefix(prefix) for f in files)


def parquet_rows(path: str, sha: str, filename: str) -> int:
    import pyarrow.parquet as pq
    from huggingface_hub import HfFileSystem

    with HfFileSystem().open(f"datasets/{path}@{sha}/{filename}", "rb") as fh:
        return int(pq.read_metadata(fh).num_rows)


def plan(source: DatasetSource) -> SourcePlan:
    sha = resolve_revision(source.path, source.revision)
    if (source.path, source.name) in KNOWN_SOURCES:
        return SourcePlan(revision=sha, known=True)

    files = source_files(source.path, source.name, source.split, sha)
    if not files:
        return SourcePlan(revision=sha, problem=f"{source.path}: split {source.split!r} has no files")
    others = sorted({f.rsplit(".", 1)[-1] for f in files if not f.endswith(".parquet")})
    if others:
        return SourcePlan(
            revision=sha,
            problem=(f"{source.path} is published as {', '.join('.' + o for o in others)} "
                     f"({len(files)} files), not parquet; its shard row counts cannot be read "
                     "from a footer"),
        )

    result = SourcePlan(revision=sha)
    for f in files:
        rows = parquet_rows(source.path, sha, f)
        if rows > MIN_HEADROOM_ROWS:
            result.table[f] = rows
        else:
            result.dropped.append(f)
    if not result.table:
        result.problem = (f"{source.path}: every shard has {MIN_HEADROOM_ROWS} rows or fewer, "
                          "too few for the eval's headroom")
    return result
