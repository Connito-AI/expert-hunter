# expert-hunter

**Suggest what the Connito subnet (SN102) should train next.**

Every training window on the subnet trains one *expert*: a group of experts
inside the shared model that the miners specialise on one kind of data. This
repo is where anyone can propose the next one, and where the community decides
the order.

| | |
|---|---|
| **Want to propose a task?** | Read **[doc/GUIDE.md](doc/GUIDE.md)**, copy [`template/exp_your_task_name.yaml`](template/exp_your_task_name.yaml) to `proposals/<your-github-login>/<task-name>.yaml`, open a pull request with that one file. |
| **Want to vote?** | Give a 👍 to the pull request you want trained. Comment to discuss it. |
| **What is winning?** | **[Open proposals, most 👍 first](https://github.com/Connito-AI/expert-hunter/pulls?q=is%3Apr+is%3Aopen+sort%3Areactions-%2B1-desc)** |
| **Complete examples** | [`exp_biomed_pubmed`](examples/connito-ai/exp_biomed_pubmed.yaml) (plain text corpus), [`exp_metamath_reasoning`](examples/connito-ai/exp_metamath_reasoning.yaml) (question/answer corpus rendered by a template) |

## How it works

```
 1. PROPOSE          2. CHECK                 3. VOTE & DISCUSS        4. PICK             5. RUN
 open a PR      ──▶  CI checks who may   ──▶  👍 on the PR = a vote ──▶ owner reviews  ──▶ exported into
 adding ONE          change what, the         comments = discussion     the most-voted     cycle-api and
 proposals/<you>/    YAML, and loads the                                proposals; merges  scheduled on
 <task>.yaml         data like a miner                                  if accepted        the subnet
```

1. **Propose.** A proposal is one file, `proposals/<your-github-login>/<task-name>.yaml`.
   It must say at least **what data to train on** and **which benchmark shows
   the expert got better**. The pull request contains that file and nothing
   else.
2. **Check.** Every pull request runs three checks:
   - `submission-rules` — the PR changes only one `.yaml` file, inside a folder
     named after the PR author's GitHub login. Anything else (a README, a
     script, an edit to someone else's folder or to the code) fails.
   - `proposal-file` — the YAML is valid and complete.
   - `data-can-run` — streams real rows from every dataset the proposal names,
     the same way a miner's dataloader does, and fails if a dataset is missing,
     gated, has the wrong split or column, or its text is too short or
     repetitive to evaluate on.

   Reports appear on the PR's *Checks* tab. A PR can only be merged when all
   three pass.
3. **Vote and discuss.** A 👍 reaction on the pull request is a vote. Comments
   are for discussion: better datasets, a fairer benchmark, a problem with the
   licence. Proposers update their PR in response; votes stay.
4. **Pick.** The owner reviews the [most-voted open proposals](https://github.com/Connito-AI/expert-hunter/pulls?q=is%3Apr+is%3Aopen+sort%3Areactions-%2B1-desc)
   first. Votes set the order of review, not the schedule: a proposal still
   needs the owner's approval, and it can be turned down (for example, if it is
   too close to a task that already ran).
5. **Run.** An accepted proposal is merged here and exported into a cycle-api
   task (`python -m expert_hunter.export <name> --group-id N`). The owner profiles
   the base model on the data to pick which experts to train, then schedules it.

Merged proposals stay in `proposals/` as the record of what was accepted.

## How a task is defined

A proposal is a subset of a real subnet task. Its `data` block is the same
shape as `data.dataset_sources` in cycle-api's
`configs/tasks/<name>/config.yaml` (`path`, `name`, `split`, `weight`,
`text_column`), extended with the experiment repo's `text_template` so a mix
can include a corpus whose text is spread over several columns. Its
`benchmarks` follow the experiment repo's benchmark registry (an
lm-evaluation-harness task at its published few-shot count, or a held-out
loss). What a proposal does **not** set — the group id, the expert
assignment, batch sizes, eval gates — is decided by the owner when it is
scheduled.

## Repository layout

```
proposals/
  <github-login>/<task>.yaml  one file per proposal, in its author's folder (merged = accepted)
template/exp_your_task_name.yaml  copy this to start
examples/connito-ai/        worked examples in the same layout; checked by CI, never voted on
expert_hunter/
  schema.py                 what a proposal may contain
  proposals.py              the proposals/<login>/<task>.yaml layout
  submission.py             who may change what in a pull request
  check.py                  python -m expert_hunter.check [TASK] [--network]
  hub.py                    the "can the data run" check
  export.py                 proposal → cycle-api configs/tasks/<name>/config.yaml
tests/                      pytest; `--network` adds the real Hub check
doc/GUIDE.md                the guide for proposers
```

## For maintainers

```bash
pip install -e ".[network,test]"
pytest                                   # offline: schema, layout, submission rules, export
pytest --network                         # also stream every proposal's data from the Hub
python -m expert_hunter.check TASK --network
python -m expert_hunter.export TASK --group-id 7 > config.yaml
```

Repository settings this relies on:

- A ruleset on `main` requiring a pull request, an owner approval, and the
  **`submission-rules`, `proposal-file` and `data-can-run`** status checks.
  GitHub cannot stop anyone *opening* a pull request that touches any file;
  what enforces the rules is that a failing required check blocks the merge.
- Maintainers are exempt from the file rules: authors whose association is
  OWNER, MEMBER or COLLABORATOR, plus the logins in `TRUSTED_AUTHORS` in
  `.github/workflows/validate.yml`. That list is needed because a GitHub App
  opening pull requests shows as `NONE`, and an org member with private
  membership can show as `CONTRIBUTOR`.
- `submission-rules` and `data-can-run` run the checker from the base branch,
  never from the pull request, so a proposal cannot change the rules it is
  judged by.
