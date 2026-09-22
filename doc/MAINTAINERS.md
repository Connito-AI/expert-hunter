# For maintainers

Proposers only need [GUIDE.md](GUIDE.md). This page is for the people who run
the repository and turn accepted proposals into subnet tasks.

## Commands

```bash
pip install -e ".[network,test]"
pytest                                   # offline: schema, layout, submission rules, export
pytest --network                         # also stream every proposal's data from the Hub
CONNITO_SUBNET=../Connito pytest tests/test_subnet_contract.py   # exports load in the subnet
python -m expert_hunter.check TASK --network
python -m expert_hunter.export TASK --group-id 7 > config.yaml             # reads the Hub
python -m expert_hunter.export TASK --group-id 7 --offline > config.yaml   # legacy eval, no Hub
```

## Eval sampling in an exported task

`export` decides how validators sample eval rows. The subnet's **seeded shard
pick** reaches every row of every shard over time; the legacy shuffle+skip
path only ever reaches the first rows of each shard. Seeded pick is set per
task, so every source needs a policy:

- a built-in one (`allenai/c4` `en`, `nvidia/Nemotron-CC-Math-v1` `4plus`,
  `joelniklaus/Multi_Legal_Pile` `all_all` — `expert_hunter.shard_table.KNOWN_SOURCES`), or
- a shard table, `eval_shard_rows`: each file's row count at one pinned
  commit. Export builds it for **parquet** sources by reading each file's
  footer (seconds). JSON has no footer, so a JSON source cannot get one.

If every source has one, the task gets `eval_source_seeded_shard_pick: true`,
the tables, and a pin for every source. **Validators must be on connito v0.6.3
or later**, which reads `eval_shard_rows`. Otherwise the task stays on the
legacy path and the header names the source that kept it there. Shards of
10,000 rows or fewer are left out of a table, since the subnet rejects them.

A table is only valid at the commit it was counted at. If a dataset is
re-uploaded, re-export.

## Repository settings this relies on

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
- `subnet-contract` is deliberately **not** a required check. It loads every
  exported proposal through `ExpertCfg` from the subnet repo's default branch,
  and checks that every key export writes is a field the subnet declares (the
  subnet ignores unknown keys, so a rename would otherwise fail silently). When
  it goes red, the subnet changed: update `expert_hunter/export.py` and the
  schema. It also runs every Monday.

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
doc/MAINTAINERS.md          this page
```
