"""Turn a winning proposal into a cycle-api task config.

`python -m expert_hunter.export exp_name --group-id 7 > config.yaml`

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
from expert_hunter.schema import Proposal


def task_config(proposal: Proposal, group_id: int) -> dict:
    sources = []
    for s in proposal.data.dataset_sources:
        entry: dict = {"path": s.path}
        if s.name:
            entry["name"] = s.name
        entry["split"] = s.split
        entry["weight"] = s.weight
        if s.text_column:
            entry["text_column"] = s.text_column
        else:
            # experiment's render.cpt.text_template. Flagged in the header,
            # because a source rendered from several columns needs the loader
            # to apply the template rather than read one column.
            entry["text_template"] = s.text_template
        sources.append(entry)

    data: dict = {
        "dataset_sources": sources,
        "per_device_train_batch_size": 1,
        "batch_size": 4,
        "sequence_length": proposal.data.sequence_length,
        # A new corpus is not in the validator's registered-source list, so the
        # seeded shard pick would raise KeyError; the legacy path is the only one
        # that works for it (exp_txt360_c4 made the same call).
        "eval_source_seeded_shard_pick": False,
        "eval_source_skip_max": 1_000_000,
    }
    pins = {s.path: s.revision for s in proposal.data.dataset_sources if s.revision}
    if pins:
        data["eval_source_revision_pin"] = pins
    return {"group_id": group_id, "data": data}


def render(proposal: Proposal, group_id: int) -> str:
    header = (
        f"# {proposal.name}: {proposal.title}\n"
        f"# Exported from expert-hunter proposals/{proposal.proposer.github}/{proposal.name}.yaml,\n"
        f"# proposed by @{proposal.proposer.github}.\n"
        "#\n"
        "# STILL NEEDED before this can be scheduled: expert_assignment.json from\n"
        "# profiling the base model on these sources, and an entry in\n"
        "# configs/task_schedule.yaml. Check group_id is not already taken.\n"
        "#\n"
        + ("# NOTE: a source below uses `text_template` (several columns rendered into\n"
           "# one, as in experiment's render.cpt.text_template). Confirm the miner\n"
           "# build renders templates before scheduling; otherwise re-export the\n"
           "# corpus with a single text column.\n#\n"
           if any(s.text_template for s in proposal.data.dataset_sources) else "")
        +
        "# Benchmarks the proposal will be judged on:\n"
        + "".join(
            f"#   - {b.name}: {b.harness}"
            + (f" task {b.task}, {b.num_fewshot}-shot" if b.task else "")
            + f", metric {b.metric} ({'higher' if b.higher_is_better else 'lower'} is better)\n"
            for b in proposal.benchmarks
        )
    )
    return header + yaml.safe_dump(task_config(proposal, group_id), sort_keys=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("name", help="task name (under proposals/ or examples/) or a .yaml path")
    parser.add_argument("--group-id", type=int, required=True,
                        help="a group id no existing task uses (see cycle-api configs/tasks/)")
    args = parser.parse_args(argv)

    path = P.find(args.name)
    if path is not None:
        sys.stdout.write(render(P.load(path), args.group_id))
        return 0
    print(f"no proposal {args.name!r}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
