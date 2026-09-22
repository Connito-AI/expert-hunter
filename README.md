# expert-hunter

**Suggest what the Connito subnet (SN102) should train next.**

Every training window on the subnet trains one *expert*: a group of experts
inside the shared model that the miners specialise on one kind of data. This
repo is where anyone can propose the next one, argue for it, and show the
owner how much support it has.

```
 1. PROPOSE          2. CHECK                 3. VOTE & DISCUSS        4. PICK               5. RUN
 open a PR      ──▶  CI checks who may   ──▶  👍 on the PR = support ──▶ owner weighs the  ──▶ exported into
 adding ONE          change what, the         comments = discussion     proposals, using     cycle-api and
 proposals/<you>/    YAML, and loads the                                👍 as a reference;   scheduled on
 <task>.yaml         data like a miner                                  merges if accepted   the subnet
```

1. **Propose.** Read **[doc/GUIDE.md](doc/GUIDE.md)**, copy
   [`template/exp_your_task_name.yaml`](template/exp_your_task_name.yaml) to
   `proposals/<your-github-login>/<task-name>.yaml`, and open a pull request
   with that one file. The file says at least **what data to train on** and
   **which benchmark shows the expert got better**; the pull request
   description tells the **story** of why the subnet needs it. Complete
   examples: [`exp_biomed_pubmed`](examples/connito-ai/exp_biomed_pubmed.yaml)
   (plain text corpus) and
   [`exp_metamath_reasoning`](examples/connito-ai/exp_metamath_reasoning.yaml)
   (question/answer corpus rendered by a template); a finished proposal PR:
   [#4](https://github.com/Connito-AI/expert-hunter/pull/4).
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
3. **Vote and discuss.** Give a 👍 to the pull request you want trained.
   Comments are for discussion: better datasets, a fairer benchmark, a problem
   with the licence. Proposers update their PR in response; votes stay.
4. **Pick.** The owner decides which task runs next. The number of 👍 is one
   of the things they take into account, alongside the story, the quality of
   the data and benchmark, and what the subnet has trained already — it is a
   reference, not a ranking that decides on its own. A proposal can be turned
   down (for example, if it is too close to a task that already ran), and the
   reason is given in the PR.
5. **Run.** An accepted proposal is merged here and exported into a cycle-api
   task. The owner profiles the base model on the data to pick which experts to
   train, then schedules it.

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
