# expert-hunter

**Suggest what the Connito subnet (SN102) should train next.**

Every training window on the subnet trains one *expert*: a group of experts
inside the shared model that the miners specialise on one kind of data. This
repo is where anyone can propose the next one, and where the community decides
the order.

| | |
|---|---|
| **Want to propose a task?** | Read **[doc/GUIDE.md](doc/GUIDE.md)**, copy [`proposals/_template/`](proposals/_template/proposal.yaml), open a pull request. |
| **Want to vote?** | Give a 👍 to the pull request you want trained. Comment to discuss it. |
| **What is winning?** | **[LEADERBOARD.md](LEADERBOARD.md)**, updated every six hours. |
| **Complete examples** | [`exp_biomed_pubmed`](examples/exp_biomed_pubmed/proposal.yaml) (plain text corpus), [`exp_metamath_reasoning`](examples/exp_metamath_reasoning/proposal.yaml) (question/answer corpus rendered by a template) |

## How it works

```
 1. PROPOSE        2. CHECK                 3. VOTE & DISCUSS        4. PICK             5. RUN
 open a PR    ──▶  CI loads the data   ──▶  👍 on the PR = a vote ──▶ owner reviews  ──▶ exported into
 adding one        the way a miner          comments = discussion     the top-ranked     cycle-api and
 proposal.yaml     would; must pass         LEADERBOARD.md ranks      proposal; merges   scheduled on
                   to be ranked             by 👍                      it if accepted     the subnet
```

1. **Propose.** A proposal is one file, `proposals/<name>/proposal.yaml`. It
   must say at least **what data to train on** and **which benchmark shows the
   expert got better**.
2. **Check.** Every pull request runs two checks. `proposal-file` validates the
   file offline. `data-can-run` streams real rows from every dataset the
   proposal names, the same way a miner's dataloader does, and fails if a
   dataset is missing, gated, has the wrong split or column, or its text is too
   short or repetitive to evaluate on. The report appears on the PR's
   *Checks* tab.
3. **Vote and discuss.** A 👍 reaction on the pull request is a vote. Comments
   are for discussion: better datasets, a fairer benchmark, a problem with the
   licence. Proposers update their PR in response; votes stay.
4. **Pick.** The owner reviews proposals in leaderboard order. The top one is
   not scheduled automatically: it still needs a review, and it can be turned
   down (for example, if it is too close to a task that already ran).
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
  _template/proposal.yaml   copy this to start
  <name>/proposal.yaml      one per proposal (added by PRs; merged = accepted)
examples/                   worked examples; checked by CI, never ranked
expert_hunter/
  schema.py                 what a proposal may contain
  check.py                  python -m expert_hunter.check [NAME] [--network]
  hub.py                    the "can the data run" check
  leaderboard.py            ranks open PRs by 👍 → LEADERBOARD.md
  export.py                 proposal → cycle-api configs/tasks/<name>/config.yaml
tests/                      pytest; `--network` adds the real Hub check
doc/GUIDE.md                the guide for proposers
```

## For maintainers

```bash
pip install -e ".[network,test]"
pytest                                   # offline: schema, leaderboard rules, export
pytest --network                         # also stream every proposal's data from the Hub
python -m expert_hunter.check NAME --network
python -m expert_hunter.export NAME --group-id 7 > config.yaml
GITHUB_REPOSITORY=Connito-AI/expert-hunter GITHUB_TOKEN=... python -m expert_hunter.leaderboard
```

Recommended repository settings:

- Protect `main`: require the `proposal-file` and `data-can-run` checks and one
  owner approval before merging.
- Add `expert_hunter/`, `tests/` and `.github/` to CODEOWNERS so changes to the
  rules are reviewed separately from proposals. (The `data-can-run` check always
  runs the checker from the base branch, and the leaderboard ignores PRs that
  touch anything outside `proposals/`, so a proposal PR cannot change the rules
  it is judged by.)
