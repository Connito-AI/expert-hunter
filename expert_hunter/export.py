"""Turn an accepted proposal into a cycle-api task config.

`python -m expert_hunter.export exp_name --group-id 7 > config.yaml`

It reads the Hub (see `expert_hunter.shard_table`) to decide how validators
sample eval rows: when every source has a shard policy — a built-in one, or a
table of shard row counts this builds for parquet sources — the task turns on
the subnet's seeded shard pick (connito v0.6.3 or later). Otherwise it stays on
the legacy shuffle+skip path, and the header says which source is why.
`--offline` skips the Hub and always exports the legacy path.

The output is `configs/tasks/<name>/config.yaml` for the cycle-api repo. It is
a starting point for the owner, not a finished task: the task also needs an
`expert_assignment.json` from profiling the base model on this data, and an
entry in `configs/task_schedule.yaml`. Both stay with the owner.

The defaults below are the ones the live tasks use (see cycle-api's
`configs/tasks/exp_txt360_c4/config.yaml` for why each one is set).
"""
from __future__ import annotations

import argparse
import sys

import yaml

from expert_hunter import proposals as P
from expert_hunter import shard_table
from expert_hunter.schema import Proposal
from expert_hunter.shard_table import SourcePlan


def seeded(plans: list[SourcePlan] | None) -> bool:
    """The seeded pick is per task: every source needs a policy."""
    return bool(plans) and all(p.seedable for p in plans)


def task_config(proposal: Proposal, group_id: int,
                plans: list[SourcePlan] | None = None) -> dict:
    """`plans` holds one `SourcePlan` per source, in order; None means offline."""
    on = seeded(plans)
    sources = []
    for i, s in enumerate(proposal.data.dataset_sources):
        entry: dict = {"path": s.path}
        if s.name:
            entry["name"] = s.name
        entry["split"] = s.split
        entry["weight"] = s.weight
        if s.text_column:
            entry["text_column"] = s.text_column
        else:
            # The subnet's DatasetSourceCfg.text_template: the dataloader
            # renders the row with it instead of reading one column.
            entry["text_template"] = s.text_template
        if on and plans[i].table:
            entry["eval_shard_rows"] = dict(plans[i].table)
        sources.append(entry)

    data: dict = {
        "dataset_sources": sources,
        "per_device_train_batch_size": 1,
        "batch_size": 4,
        "sequence_length": proposal.data.sequence_length,
        "eval_source_seeded_shard_pick": on,
    }
    if not on:
        # Legacy shuffle+skip; widen its reach the way exp_txt360_c4 does.
        data["eval_source_skip_max"] = 1_000_000
    if plans is not None:
        # A table is only valid at the commit it was counted at, so every
        # source is pinned to the sha it was measured against.
        pins = {s.path: p.revision for s, p in zip(proposal.data.dataset_sources, plans)}
    else:
        pins = {s.path: s.revision for s in proposal.data.dataset_sources if s.revision}
    if pins:
        data["eval_source_revision_pin"] = pins
    return {"group_id": group_id, "data": data}


def _suggestion(proposal: Proposal) -> str:
    s = proposal.suggested_training
    if s is None or (s.steps is None and s.batch_size is None):
        return ""
    parts = [f"{s.steps} steps" if s.steps else "", f"batch size {s.batch_size}" if s.batch_size else ""]
    return "# The proposer suggested: " + ", ".join(p for p in parts if p) + " (not applied).\n"


def _eval_note(proposal: Proposal, plans: list[SourcePlan] | None) -> str:
    if plans is None:
        return ("# Eval sampling: legacy shuffle+skip (exported with --offline, so no\n"
                "# shard tables were built).\n#\n")
    if seeded(plans):
        lines = ["# Eval sampling: SEEDED SHARD PICK. Needs every validator on connito\n",
                 "# v0.6.3 or later, which reads `eval_shard_rows`; do not schedule it before.\n"]
        for s, p in zip(proposal.data.dataset_sources, plans):
            if p.dropped:
                lines.append(f"# {s.path}: left out {len(p.dropped)} shard(s) of "
                             f"{shard_table.MIN_HEADROOM_ROWS} rows or fewer.\n")
        return "".join(lines) + "#\n"
    reasons = "".join(f"#   - {p.problem}\n" for p in plans if not p.seedable)
    return ("# Eval sampling: legacy shuffle+skip. The seeded shard pick needs a policy\n"
            "# for every source, and these have none:\n" + reasons + "#\n")


def render(proposal: Proposal, group_id: int, plans: list[SourcePlan] | None = None) -> str:
    header = (
        f"# {proposal.name}: {proposal.title}\n"
        f"# Exported from expert-hunter proposals/{proposal.proposer.github}/{proposal.name}.yaml,\n"
        f"# proposed by @{proposal.proposer.github}.\n"
        "#\n"
        "# STILL NEEDED before this can be scheduled: expert_assignment.json from\n"
        "# profiling the base model on these sources, and an entry in\n"
        "# configs/task_schedule.yaml. Check group_id is not already taken.\n"
        "#\n"
        + _eval_note(proposal, plans)
        +
        "# Benchmarks the proposal will be judged on:\n"
        + "".join(
            f"#   - {b.name}: {b.harness}"
            + (f" task {b.task}, {b.num_fewshot}-shot" if b.task else "")
            + f", metric {b.metric} ({'higher' if b.higher_is_better else 'lower'} is better)\n"
            for b in proposal.benchmarks
        )
        + _suggestion(proposal)
    )
    return header + yaml.safe_dump(task_config(proposal, group_id, plans), sort_keys=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("name", help="task name (under proposals/ or examples/) or a .yaml path")
    parser.add_argument("--group-id", type=int, required=True,
                        help="a group id no existing task uses (see cycle-api configs/tasks/)")
    parser.add_argument("--offline", action="store_true",
                        help="do not read the Hub; export the legacy eval path without shard tables")
    args = parser.parse_args(argv)

    path = P.find(args.name)
    if path is not None:
        proposal = P.load(path)
        plans = None if args.offline else [shard_table.plan(s) for s in proposal.data.dataset_sources]
        sys.stdout.write(render(proposal, args.group_id, plans))
        return 0
    print(f"no proposal {args.name!r}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
