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
python -m expert_hunter.export TASK --group-id 7 > config.yaml
```

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
  schema. It runs on maintainers' pull requests, on pushes to `main`, every
  Monday and by hand; on contributors' pull requests it is skipped (a
  proposal cannot break it, and a red X there would only confuse them).

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
