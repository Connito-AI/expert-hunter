# Proposing a task: the guide

This guide is for anyone who wants to suggest what the Connito subnet trains
next. You do not need to run a miner or a validator. You need a GitHub account,
a dataset on HuggingFace, and a benchmark that shows whether training worked.

- [What you are proposing](#what-you-are-proposing)
- [Step by step](#step-by-step)
- [Filling in the proposal file](#filling-in-the-proposal-file)
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
2. **Copy the template into a folder named after your GitHub login**, and name
   the file after your task. Task names start with `exp_` and use lowercase
   words joined by underscores. If your login is `octocat`:

   ```bash
   mkdir -p proposals/octocat
   cp template/exp_your_task_name.yaml proposals/octocat/exp_finance_reports.yaml
   ```

3. **Fill in** `proposals/octocat/exp_finance_reports.yaml`
   ([field by field below](#filling-in-the-proposal-file)). Set `proposer.github` to
   your login and `name` to the file name. Look at
   [`examples/connito-ai/exp_biomed_pubmed.yaml`](../examples/connito-ai/exp_biomed_pubmed.yaml)
   for a complete one, and
   [`examples/connito-ai/exp_metamath_reasoning.yaml`](../examples/connito-ai/exp_metamath_reasoning.yaml)
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
5. **Open one pull request containing only that one file.** Fill in the PR
   template's checklist. Anything longer you want to say — a custom benchmark,
   how you built a dataset — goes in the PR description, not in extra files.
6. **Watch the checks** on your PR. All three must be green before it can be
   merged ([what each one means](#the-checks-and-how-to-fix-a-failure)).
7. **Answer comments.** People will ask questions and suggest changes. Push
   fixes to the same branch; votes stay with the PR.

### What a pull request may contain

| Allowed | Not allowed |
|---|---|
| Adding **one** file `proposals/<your-login>/<task-name>.yaml` | A second proposal in the same PR — open another PR |
| Editing that file | A README, images, scripts, or any file that is not `.yaml` (`.yml` included) |
| Deleting a proposal of your own (withdrawing it) | Anything in someone else's folder, even a typo fix — comment on their PR instead |
| | Anything outside `proposals/<your-login>/`: code, docs, examples, workflows |

The folder is compared with **the GitHub account that opened the pull
request**, so it has to be your own login — not your team's, not the person
you are proposing on behalf of. The `submission-rules` check fails any pull
request that breaks these rules, and a failing check blocks the merge.

## Filling in the proposal file

| Field | Required | What to write |
|---|---|---|
| `name` | yes | `exp_` + lowercase words, e.g. `exp_finance_reports`. Same as the file name, without `.yaml`. At most 40 characters, not an existing task, not already proposed by someone else. |
| `title` | yes | One line: what the expert gets good at. Use it as your PR title. |
| `proposer.github` | yes | Your GitHub login — the same as your folder name and the account opening the PR. |
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
paste its YAML into the PR description (a submission cannot contain extra
files); the check will mark it unverified and a maintainer will review it.

## The checks, and how to fix a failure

Three checks run on every pull request. All three must pass before it can be
merged.

**`submission-rules`** — the pull request changes only one `.yaml` file, in
your own folder ([the rules](#what-a-pull-request-may-contain)):

| Message | Fix |
|---|---|
| `` `X` is outside proposals/<your-login>/ `` | Remove every change except your proposal file from the PR. |
| `` `X` is in `someone`'s folder `` | Move your file to `proposals/<your-login>/`, and undo changes to other people's files. |
| `` `X` is not a `.yaml` file `` | Remove it. Only the proposal itself is submitted; put explanations in the PR description. |
| `adds or edits N proposals` | Keep one proposal in this PR and open a separate PR for each of the others. |

**`proposal-file`** — the YAML is valid and complete. Errors name the field:

| Message | Fix |
|---|---|
| `name must look like exp_<words>` | Lowercase, `exp_` prefix, single underscores. |
| `already a task on the subnet` | Pick a different name. |
| `the file must be named after the proposal's name` | Rename the file to `<name>.yaml`, or change `name`. |
| `the folder must be the proposer's GitHub login` | Set `proposer.github` to your login, and keep the file in `proposals/<your-login>/`. |
| `proposed by more than one person` | Someone already proposed a task with this name; pick another name (or support theirs with a 👍). |
| `only <github-login>/<task-name>.yaml files belong here` | The file is in the wrong place or is not `.yaml`. |
| `weights must sum to 1.0` | Adjust the `weight`s. |
| `Extra inputs are not permitted` | A misspelt field name; compare with the template. |
| `graded on data it trained on` | A benchmark uses a training dataset and split. Use its `test` split, or a different dataset. |

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
  first box on the PR page). GitHub allows one 👍 per account per pull request.
- **To see what is winning**, open the
  [open proposals sorted by 👍](https://github.com/Connito-AI/expert-hunter/pulls?q=is%3Apr+is%3Aopen+sort%3Areactions-%2B1-desc).
- **Comment** on any proposal to ask questions, point out problems, or suggest
  better data or benchmarks. Good discussion is what turns a popular idea into
  a task that works. Keep it about the proposal.

Votes set the **order** in which the owner reviews proposals. The owner reads
the vote count with judgment — a sudden burst of 👍 from brand-new accounts is
not the same as support from people who mine or validate — and can decline a
proposal, for example if the data's licence is unclear, it duplicates a task
that ran, or the benchmark cannot show a result. The reason is given in the PR.

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

**Can I propose on behalf of someone else, or as a team?** Open the pull
request from your own account, into your own folder, and credit them in the
description. The folder always belongs to the account that opened the PR.

**How long until my proposal runs?** It depends on its votes and on the task
currently running. Each task runs for at least one training window.

**Is my proposal public?** Yes — everything in a PR is public. Do not include
private data links or credentials.
