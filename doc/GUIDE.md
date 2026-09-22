# Proposing an experiment

Have an idea for what the Connito subnet should train next? Proposing it takes
one YAML file and one pull request. You don't need to run a miner, and you
don't need to write a research paper.

This is a **pre-alpha of our training-as-a-service platform**. Every proposal,
and every insight from how its experiment goes, helps us build a better
platform for the customers who will later train their own experts on it.

**The short version:** idea → copy the template → fill in a few fields → open a PR.

- [What you are proposing](#what-you-are-proposing)
- [Step by step](#step-by-step)
- [The fields](#the-fields)
- [Choosing the data](#choosing-the-data)
- [Choosing the benchmark](#choosing-the-benchmark)
- [If a check fails](#if-a-check-fails)
- [After you open the PR](#after-you-open-the-pr)
- [FAQ](#faq)

## What you are proposing

The subnet trains a *mixture-of-experts* model: every layer has many small
expert networks, and each task trains a group of them on one kind of data so
they become specialists — a math expert, a legal expert, a medical expert.
Right now the base model is **DeepSeek-V2-Lite**, the default and the only one
supported so far; we expect to support more base models later.

Your proposal answers four questions:

1. **What dataset do you want to train on?**
2. **What benchmark do you expect it to improve?**
3. **Why do you expect this dataset to improve that benchmark?** A few sentences.
4. **Is there research, a paper, or a result that supports it?** "None known" is
   a fine answer.

If you have a feel for it, you can also suggest **how many training steps** and
**what batch size**. These are guesses, not requirements — the owner makes the
final call.

Tasks that have already run: `exp_math`, `exp_legal`, `exp_nemotron_c4`
(math web text + c4), `exp_txt360_c4` (reasoning traces + c4).

## Step by step

Say your GitHub login is `octocat` and your idea is training on financial
reports.

1. **Clone this repository.** You'll need your own fork to push to;
   `gh repo fork Connito-AI/expert-hunter --clone` does both in one go.

2. **Copy the template that's already in this repo** —
   [`template/exp_your_task_name.yaml`](../template/exp_your_task_name.yaml) —
   into a folder named after your login, as `exp_<task_name>.yaml`:

   ```bash
   mkdir -p proposals/octocat
   cp template/exp_your_task_name.yaml proposals/octocat/exp_finance_reports.yaml
   ```

3. **Edit the copy.** Set `name` to the file name (`exp_finance_reports`),
   `proposer.github` to your login, and fill in the rest
   ([the fields](#the-fields)). Two complete examples to crib from:
   [`exp_biomed_pubmed`](../examples/connito-ai/exp_biomed_pubmed.yaml) and
   [`exp_metamath_reasoning`](../examples/connito-ai/exp_metamath_reasoning.yaml).

4. **Check it** (optional but saves a round trip; Python 3.10+):

   ```bash
   pip install -e ".[network]"
   python -m expert_hunter.check exp_finance_reports --network
   ```

   This loads a sample of your data the way a miner would. Fix anything
   marked ✗.

5. **Open a pull request with just that one file.** The PR description has a
   short checklist. That's it — the checks run automatically.

**The one rule for the PR:** it adds or edits exactly one file,
`proposals/<your-login>/<task_name>.yaml`, and nothing else — no READMEs,
no scripts, no edits to other people's folders. The folder must be the login
of the account opening the PR. One proposal per PR; open another PR for a
second idea.

## The fields

Here is what a filled-in proposal looks like (trimmed):

```yaml
name: exp_finance_reports
title: Reading financial reports
proposer:
  github: octocat
description: >
  Train an expert on SEC filings to improve FinQA.
data:
  dataset_sources:
    - path: org/sec-filings
      split: train
      weight: 0.5
      text_column: text
    - path: allenai/c4
      name: en
      split: train
      weight: 0.5
      text_column: text
benchmarks:
  - name: finqa
    harness: lm_eval
    task: finqa
    num_fewshot: 0
    metric: exact_match
    higher_is_better: true
    dataset: {path: ChanceFocus/flare-finqa, split: test}
hypothesis: >
  FinQA asks numerical questions about the text and tables of earnings
  reports. Filings are exactly that kind of document, so the model sees the
  vocabulary and table layouts the benchmark uses.
evidence: >
  BloombergGPT (Wu et al., 2023) trained on a large share of financial
  documents and did better on financial benchmarks than general models its size.
suggested_training:
  steps: 2000
contamination: >
  FinQA's test questions are not in the filings corpus.
```

| Field | Required | What to write |
|---|---|---|
| `name` | yes | `exp_` + lowercase words joined by `_`, same as the file name. At most 40 characters. |
| `title` | yes | One line: what the expert gets good at. |
| `proposer.github` | yes | Your GitHub login (= your folder name). `contact` is optional. |
| `description` | yes | A sentence or two: what is trained, on which dataset, to improve which benchmark. |
| `data.dataset_sources` | yes | 1–4 datasets whose `weight`s add up to 1.0 ([choosing the data](#choosing-the-data)). |
| `data.sequence_length` | no | Tokens per training sample: 4096 (default), 2048 or 1024. |
| `benchmarks` | yes | 1–5 benchmarks ([choosing the benchmark](#choosing-the-benchmark)). |
| `hypothesis` | yes | A few sentences: why training on this data should improve this benchmark. |
| `evidence` | yes | Research, papers or results that support it, or `none known`. |
| `suggested_training` | no | Your guess at `steps` and `batch_size`. Leave it out if you have no idea. |
| `contamination` | yes | One line: how you know the benchmark's questions aren't in the training data. |

**The hypothesis doesn't need to be long.** It's there so we can understand
why the experiment might work. Name the link between the data and the
benchmark ("the exam asks about drug mechanisms; the abstracts describe
them"), not just the domain ("medical text helps a medical exam"). If you know
of a paper or an earlier result, put it in `evidence` — a title or a link is
enough; no literature review needed. Want to say more? Use the PR description.

Each **dataset source**:

| Field | Meaning |
|---|---|
| `path` | The HuggingFace dataset id, `org/name`. |
| `name` | The config (subset), if the dataset has several — e.g. `en` for `allenai/c4`. |
| `split` | Which split to train on. Write it out; some datasets have no `train`. |
| `weight` | Share of training samples from this source. |
| `text_column` | The column that holds the text, **or instead** … |
| `text_template` | … for a dataset whose text is spread over columns, a template joining them: `"User: {question}\n\nAssistant: {answer}"`. |
| `revision`, `license` | Optional: a 40-character commit sha to pin, and the licence (`cc-by-4.0`). |

Each **benchmark**: `name` (a label), `harness` (`lm_eval` or `eval_loss`),
`task` and `num_fewshot` (for `lm_eval`), `metric` (as lm-eval names it, e.g.
`acc`, `acc_norm`, `exact_match,strict-match`, or `loss`), `higher_is_better`,
and `dataset` (`path`, optional `name`, `split` — usually `test`). An optional
`why` can say what the benchmark measures.

## Choosing the data

Pick data that teaches the skill your benchmark tests. A few practical things
make it work well on the subnet, where hundreds of machines stream it at once:

- **It streams from the Hub.** Parquet (or sharded JSON) files load fine.
  Datasets that need a loading script (`<name>.py`) don't load with current
  `datasets`, and one huge single file is slow for every miner — prefer a
  parquet export.
- **The rows are real documents.** Rows under 200 characters are dropped from
  evaluation, and rows that start with the same 200 characters (boilerplate,
  templated records) are deduplicated, so short or repetitive data leaves
  little to score on.
- **There's plenty of it** — ideally hundreds of thousands of documents.
- **Mix in general text.** Training on one domain only makes the model forget
  the rest. Every live task mixes 50% `allenai/c4`; the template already
  includes it.
- **List the licence**, so we know it can be trained on.
- **Question/answer data works as published**: use `text_template` to join
  the columns the way you want the model to see them.

If a dataset is gated (you have to accept terms to download it), that's
allowed, but the check can't read its rows and every miner and validator will
have to accept the terms too — say so in the PR.

## Choosing the benchmark

Pick a benchmark that tests the skill, not the training documents themselves:
an exam in the domain (MedQA for medicine, FinQA for finance, GSM8K for math)
beats a test built from your training data.

- **Keep it held out.** Don't train on the split the benchmark scores (the
  check rejects the obvious case).
- **Nothing fits?** Use `harness: eval_loss` on a held-out split of your data.
  It shows whether training moved the model at all, though it can't be
  compared across tasks.
- **A custom lm-eval task** is fine: paste its YAML into the PR description.

## If a check fails

Three checks run on every PR, and all three must pass before it can be
merged. The full report is on the PR's *Checks* tab.

**`submission-rules`** — the PR changes only your one proposal file.

| Message | Fix |
|---|---|
| `` `X` is outside proposals/<your-login>/ `` | Remove every change except your proposal file. |
| `` `X` is in `someone`'s folder `` | Move your file to `proposals/<your-login>/`; undo changes to other people's files. |
| `` `X` is not a `.yaml` file `` | Remove it; explanations go in the PR description. |
| `adds or edits N proposals` | Keep one proposal here; open a PR for each of the others. |

**`proposal-file`** — the YAML is valid and complete. Errors name the field.

| Message | Fix |
|---|---|
| `Field required` | A required field is missing; compare with the template. |
| `String should have at least N characters` | A field still says `...`; fill it in. |
| `name must look like exp_<words>` | Lowercase, `exp_` prefix, single underscores. |
| `already a task on the subnet` / `proposed by more than one person` | Pick a different name (or 👍 the existing proposal). |
| `the file must be named after the proposal's name` | Make the file name and `name` match. |
| `the folder must be the proposer's GitHub login` | Set `proposer.github` to your login and keep the file in `proposals/<your-login>/`. |
| `weights must sum to 1.0` | Adjust the `weight`s. |
| `Extra inputs are not permitted` | A misspelt field name; compare with the template. |
| `graded on data it trained on` | A benchmark scores a split you train on; use its `test` split or other data. |

**`data-can-run`** — the data actually loads.

| Message | Fix |
|---|---|
| `does not exist on the Hub` | Check `path` (`org/name`, case-sensitive). |
| `cannot be streamed: Bad split …` / `KeyError` | Set `split` (and `name`) to one the Hub lists; the message shows them. |
| `uses a loading script` | Find a parquet version of the dataset. |
| `no column 'x'; the columns are [...]` | Fix `text_column` or the `{placeholders}` in `text_template`. |
| `is not text` | The column holds lists or numbers; choose another, or use `text_template`. |
| `under 200 characters` / `share their first 200 characters` | The rows are too short or too repetitive; choose other data. |
| `took longer than …s` | Too slow to stream. Retry once; if it persists, choose other data. |
| `lm-eval has no task` | Check the task name, or mark it custom in the PR. |

## After you open the PR

- **People vote and discuss.** A 👍 on the PR description is a vote. Comments
  suggest better data or benchmarks; push fixes to the same branch and the
  votes stay.
- **The owner picks what runs next.** They take the number of 👍 into account
  as a reference, alongside the hypothesis, the data and benchmark, and what
  the subnet has already trained. Votes are read with judgment (a burst of 👍
  from brand-new accounts counts for less), and a proposal can be declined
  with the reason given in the PR.
- **If it's picked**, the owner merges it, turns it into a subnet task,
  chooses which experts to train, and schedules it. The trained expert is
  scored on your benchmarks and the result is reported on your PR.

## FAQ

**Can I use a dataset I made?** Yes, if it loads from the Hub and has a clear
licence. Say it's yours in the PR.

**Can I change my proposal after people voted?** Yes — push to the same
branch. A different idea should be a new PR.

**Why can't I set the learning rate or pick the experts?** Those depend on the
subnet's state and stay the same across tasks so results compare. Suggest
steps and batch size in `suggested_training`; anything else, in the PR
description.

**Can I propose for a team?** Open the PR from your own account, in your own
folder, and credit them in the description.

**Does the proposal with the most 👍 always run next?** No. The owner uses 👍
as a reference, together with everything else in the proposal.

**Is my proposal public?** Yes. Don't include private links or credentials.
