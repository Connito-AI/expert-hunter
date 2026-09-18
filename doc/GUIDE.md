# Proposing a task: the guide

This guide is for anyone who wants to suggest what the Connito subnet trains
next. You do not need to run a miner or a validator. You need a GitHub account,
a dataset on HuggingFace, and a benchmark that shows whether training worked.

- [What you are proposing](#what-you-are-proposing)
- [Step by step](#step-by-step)
- [Filling in proposal.yaml](#filling-in-proposalyaml)
- [Choosing the data](#choosing-the-data)
- [Choosing the benchmark](#choosing-the-benchmark)
- [The checks, and how to fix a failure](#the-checks-and-how-to-fix-a-failure)
- [Voting and discussion](#voting-and-discussion)
- [What happens if your proposal wins](#what-happens-if-your-proposal-wins)
- [FAQ](#faq)

## What you are proposing

The subnet trains one model, DeepSeek-V2-Lite, a *mixture of experts*: every
layer has 64 small expert networks and a router that picks a few for each
token. A **task** trains a small group of those experts on one kind of data,
so they become specialists — a math expert, a legal expert, a medical expert.
Miners do the training; validators score it on held-out data from the same
sources.

Your proposal answers two questions:

1. **What should the experts learn from?** One or more HuggingFace datasets.
2. **How will we know they learned it?** One or more benchmarks.

Everything else (which experts, batch sizes, how long it runs) is decided by the
subnet owner when the task is scheduled.

Tasks that have already run: `exp_math`, `exp_legal`, `exp_nemotron_c4`
(math web text + c4), `exp_txt360_c4` (reasoning traces + c4). A proposal
that repeats one of these needs a good reason.

## Step by step

1. **Fork** this repository and clone your fork.
2. **Copy the template** under a name of your own. Names start with `exp_`
   and use lowercase words joined by underscores:

   ```bash
   cp -r proposals/_template proposals/exp_finance_reports
   ```

3. **Fill in** `proposals/exp_finance_reports/proposal.yaml`
   ([field by field below](#filling-in-proposalyaml)). Look at
   [`examples/exp_biomed_pubmed/proposal.yaml`](../examples/exp_biomed_pubmed/proposal.yaml)
   for a complete one, and
   [`examples/exp_metamath_reasoning/proposal.yaml`](../examples/exp_metamath_reasoning/proposal.yaml)
   for one whose corpus is question/answer pairs joined by a template.
4. **Run the checks** (Python 3.10 or newer):

   ```bash
   pip install -e ".[network]"
   python -m expert_hunter.check exp_finance_reports             # the file: seconds
   python -m expert_hunter.check exp_finance_reports --network   # the data: a minute or two
   ```

   The second command downloads a sample of every dataset you named — the
   same way a miner's dataloader will — and prints what it found. Fix anything
   marked ✗ before you open the pull request.
5. **Open one pull request** that adds only your `proposals/<name>/` directory
   (a `README.md` next to the YAML is welcome for longer explanations). Fill in
   the PR template's checklist.
6. **Watch the checks** on your PR. When `data-can-run` is green, your
   proposal appears on the [leaderboard](../LEADERBOARD.md) within six hours.
7. **Answer comments.** People will ask questions and suggest changes. Push
   fixes to the same branch; votes stay with the PR.

One proposal per pull request. Two ideas → two PRs, so each gets its own votes.

## Filling in proposal.yaml

| Field | Required | What to write |
|---|---|---|
| `name` | yes | `exp_` + lowercase words, e.g. `exp_finance_reports`. Same as the directory. At most 40 characters, not an existing task. |
| `title` | yes | One line for the leaderboard. |
| `proposer.github` | yes | Your GitHub handle. |
| `proposer.contact` | no | Discord handle, email, or hotkey, if you want to be reachable. |
| `summary` | yes | Two or three sentences: what the expert would be able to do. |
| `motivation` | yes | Why this is worth a training window. Who would use it? What does the base model do badly now? This is what voters read — make the case. |
| `data.dataset_sources` | yes | 1 to 4 datasets; see [Choosing the data](#choosing-the-data). |
| `data.sequence_length` | no | 1024 (default), 2048 or 4096 tokens per training sample. Use more only if the domain needs long context. |
| `benchmarks` | yes | 1 to 5 benchmarks; see [Choosing the benchmark](#choosing-the-benchmark). |
| `contamination` | yes | How you know the benchmark's questions are not in the training data. |

Each **dataset source**:

| Field | Required | Meaning |
|---|---|---|
| `path` | yes | The HuggingFace dataset id, `org/name`. |
| `name` | if the dataset has several configs | The config (subset), e.g. `en` for `allenai/c4`. It is what `load_dataset(path, name)` calls `name`. |
| `split` | yes (default `train`) | Write it out. Some datasets have no `train` split — the subnet once lost a task start to exactly this. |
| `weight` | yes | Share of training samples from this source. All weights must add up to **1.0**. |
| `text_column` | one of the two | The column that already holds the text to train on. |
| `text_template` | one of the two | For a corpus whose text is spread over several columns: a line with `{column}` placeholders, e.g. `"User: {query}\n\nAssistant: {response}"`. The columns are joined into training text exactly as written. |
| `revision` | no | A 40-character commit sha to pin the exact version you checked. |
| `license` | no, but please | The dataset's licence, e.g. `cc-by-4.0`. |

Each **benchmark**:

| Field | Required | Meaning |
|---|---|---|
| `name` | yes | A short label. |
| `harness` | yes | `lm_eval` (preferred) or `eval_loss`. |
| `task` | for `lm_eval` | The [lm-evaluation-harness](https://github.com/EleutherAI/lm-evaluation-harness) task name, e.g. `gsm8k`, `medqa_4options`. |
| `num_fewshot` | for `lm_eval` | The few-shot count the benchmark is usually reported with. |
| `metric` | yes | The number to read, as lm-eval names it (`acc`, `acc_norm`, `exact_match,strict-match`), or `loss` for `eval_loss`. |
| `higher_is_better` | yes | `true` for accuracy, `false` for loss. |
| `dataset` | yes | Where the scored questions live: `path`, optional `name`, and `split` (usually `test` or `validation`). |
| `why` | yes | Why this benchmark measures what the expert should learn. |

## Choosing the data

The subnet streams training data straight from HuggingFace on hundreds of
machines at once. So a dataset must be:

- **Public and not gated.** A gated dataset ("you need to agree to share your
  contact information") would require every miner and validator to accept the
  terms by hand; anyone who has not gets a 403 and cannot work. The check fails
  gated training datasets. If the data you want is gated, look for an ungated
  mirror whose licence allows it.
- **Streamable.** Parquet or JSON files on the Hub. Datasets that rely on a
  loading script (`<name>.py`) no longer load with current `datasets`.
- **Readable as text.** Either one column already holds the text
  (`text_column`), or you write a `text_template` that joins several columns —
  the way the experiment repo's corpora do it (`corpora/metamathqa` renders
  `{query}` and `{response}` into one string). So a question/answer dataset can
  be used as published; you do not have to re-export it. Write the template the
  way you want the model to see the text, since that is also the shape it will
  produce.
- **A mix, usually.** Up to four sources with weights that add to 1.0, each
  rendered its own way — the same idea as an experiment row that mixes a domain
  corpus with a replay stream.
- **Long enough.** Validators drop rows under 200 characters from evaluation.
  If most rows are shorter, there is nothing left to score on, and the check
  fails.
- **Not repetitive.** If many rows start with the same 200 characters
  (boilerplate headers, templated records), the evaluation measures
  memorisation of a few documents. The check fails above 30% and warns above 5%.
- **Big enough.** A training window reads a lot of data and validators need
  unseen rows every round. Prefer datasets with at least hundreds of thousands
  of documents.
- **Legal to train on.** List the licence.

**Mix in general text.** Training only on one domain makes the model forget
other things. Every live task mixes 50% `allenai/c4` (`name: en`,
`text_column: text`) with the domain data, and we recommend you do too. The
template already contains it.

## Choosing the benchmark

The benchmark is how everyone will judge whether the task was worth it, so
pick one that:

- **Measures the skill, not the corpus.** An exam in the domain (MedQA for
  medicine, FinQA for finance, GSM8K for math) is better than a test built from
  the same documents you train on.
- **Exists in lm-evaluation-harness**, so the number is comparable with
  published results. The experiment repo already runs these, among others:
  `gsm8k`, `minerva_math`, `hendrycks_math`, `mmlu`, `arc_challenge`,
  `hellaswag`, `ifeval`, `humaneval`, `mbpp`, `medqa_4options`, `medmcqa`,
  `pubmedqa`, `cmmlu`, `kobest_boolq`, `haerae`, `xnli_zh`, `belebele`,
  `longbench`, `ruler`, plus custom `finqa`, `tatqa`, `legalbench`,
  `chembench`, `cti_mcqa`, `matscibench`.
- **Is held out.** The `dataset.split` you name must not be something you train
  on. The schema rejects the obvious case (the same dataset and split in both
  places); `contamination` is where you explain the rest.

If no answer-scored benchmark fits your domain, use `harness: eval_loss` with a
held-out split of your data. It shows whether training moved the model on that
text at all, but it cannot be compared with other tasks, so a proposal with a
real benchmark will usually get more support.

A custom lm-eval task (not in the harness) is allowed. Say so in the PR and
include its YAML in your proposal's `README.md`; the check will mark it
unverified and a maintainer will review it.

## The checks, and how to fix a failure

Two checks run on every pull request.

**`proposal-file`** — the YAML is valid and complete. Errors name the field:

| Message | Fix |
|---|---|
| `name must look like exp_<words>` | Lowercase, `exp_` prefix, single underscores. |
| `already a task on the subnet` | Pick a different name. |
| `directory name must equal the proposal's name` | Rename the directory or the `name`. |
| `weights must sum to 1.0` | Adjust the `weight`s. |
| `Extra inputs are not permitted` | A misspelt field name; compare with the template. |
| `graded on data it trained on` | A benchmark uses a training dataset and split. Use its `test` split, or a different dataset. |
| `only proposal.yaml (and an optional README.md) belong here` | Remove other files from the directory. |

**`data-can-run`** — the data actually loads. The full report is on the PR's
*Checks* tab under the job summary; the same report prints locally with
`--network`.

| Message | Fix |
|---|---|
| `does not exist on the Hub` | Check `path` (it is `org/name`, case-sensitive). |
| `is gated` | Use an ungated dataset or mirror. |
| `cannot be streamed: Bad split …` / `KeyError` | Set `split` (and `name`) to one the Hub lists; the message shows the available ones. |
| `uses a loading script` | Find a parquet version of the dataset. |
| `no column 'x'; the columns are [...]` | Set `text_column`, or the `{placeholders}` in `text_template`, to the listed columns. |
| `is not text` | The column holds lists or numbers; choose a text column, or render one with `text_template`. |
| `under 200 characters` | The rows are too short to evaluate on; choose a source with longer documents. |
| `share their first 200 characters` | The rows repeat; deduplicate or choose another source. |
| `took longer than …s` | The dataset is too slow to stream; a miner's dataloader would stall. Try again once; if it persists, choose another source. |
| `lm-eval has no task` | Check the task name, or mark it as custom (see above). |

## Voting and discussion

- **To vote**, add a 👍 reaction **to the pull request's description** (the
  first box on the PR page). Reactions on comments do not count.
- One vote per GitHub account. Votes on your own PR, from bots, and from
  accounts younger than 30 days do not count.
- 👎 is shown on the leaderboard so disagreement is visible, but the ranking
  is by 👍.
- Only PRs whose `data-can-run` check is green on their latest commit are
  ranked; the rest are listed below the ranking with the reason.
- Ties go to the proposal opened first.
- **Comment** on any proposal to ask questions, point out problems, or suggest
  better data or benchmarks. Good discussion is what turns a popular idea into
  a task that works. Keep it about the proposal.

The ranking sets the **order** in which the owner reviews proposals. The owner
can still decline a proposal — for example if the data's licence is unclear, it
duplicates a task that ran, or the benchmark cannot show a result — and will
say why in the PR.

## What happens if your proposal wins

1. The owner reviews it, may ask for changes in the PR, and merges it.
2. It is exported into a cycle-api task:
   `python -m expert_hunter.export <name> --group-id <N>` writes the
   `configs/tasks/<name>/config.yaml` the subnet reads.
3. The owner profiles the base model on your data to choose which experts to
   train (`expert_assignment.json`) and adds the task to the schedule.
4. The subnet trains it for one or more windows.
5. The trained expert is scored on your benchmarks and the result is reported
   back on your PR.

## FAQ

**Can I propose a task using a dataset I made?** Yes, if it is public, ungated,
has a clear licence, and passes the checks. Say that it is yours in the PR.

**Can I change my proposal after people voted?** Yes, push to the same branch.
The votes stay. Large changes (a different domain) should be a new PR.

**Why can't I set the learning rate / experts / batch size?** Those depend on
the subnet's state and are the same across tasks so results are comparable.
Suggest them in your PR's description if you have evidence; the owner may use
it.

**How long until my proposal runs?** It depends on its rank and on the task
currently running. Each task runs for at least one training window.

**Is my proposal public?** Yes — everything in a PR is public. Do not include
private data links or credentials.
