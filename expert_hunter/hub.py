"""Can this proposal's data actually run? Checked against the HuggingFace Hub.

The offline schema check says a proposal is well-formed. This says the datasets
it names can be loaded the way a miner loads them — `datasets.load_dataset(
path, name, split=split, streaming=True)`, then read `text_column` — and that
the rows are usable text. Every failure here is one that has happened, or would
happen, on the subnet in the middle of a training window:

* a path or config that does not exist (404 at dataloader build),
* a gated dataset (every miner and validator would have to accept its licence
  by hand, or file reads 403),
* a split that is not `train` but was not named (KeyError: 'train'),
* a text column (or a text_template's columns) that is missing, not text,
  or mostly empty,
* rows so short that the validator's eval gate (rows under 200 characters are
  dropped) leaves nothing to score on,
* rows that repeat, so the eval measures memorisation of a few documents.

Needs network access to huggingface.co and the `datasets` package
(`pip install -e ".[network]"`).
"""
from __future__ import annotations

import json
import statistics
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from expert_hunter.schema import Benchmark, DatasetSource, Proposal

HUB = "https://huggingface.co"
VIEWER = "https://datasets-server.huggingface.co"

# Mirrors the subnet's eval gates (`eval_min_text_chars: 200`,
# `eval_dedup_prefix_chars: 200` in the task config): rows shorter than this are
# dropped from evaluation, and rows sharing a prefix this long are deduplicated.
MIN_TEXT_CHARS = 200
DEDUP_PREFIX_CHARS = 200
# Rough characters per token for English text, to say how much of a row fits in
# one training window.
CHARS_PER_TOKEN = 4

# Extensions a streaming reader can read a piece at a time. Anything else is
# read whole, per worker.
SHARDABLE_SUFFIXES = (".parquet", ".arrow")
# Files that are not data at all.
NON_DATA_SUFFIXES = (".md", ".gitattributes", ".png", ".jpg", ".jpeg", ".svg", ".py", ".txt", ".yaml")

DEFAULT_SAMPLE_ROWS = 200
DEFAULT_TIMEOUT = 60.0


@dataclass
class Finding:
    level: str          # "error" | "warning" | "ok"
    subject: str        # which source / benchmark
    message: str


@dataclass
class Report:
    proposal: str
    findings: list[Finding] = field(default_factory=list)
    stats: dict[str, dict] = field(default_factory=dict)

    def add(self, level: str, subject: str, message: str) -> None:
        self.findings.append(Finding(level, subject, message))

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.level == "error"]

    @property
    def passed(self) -> bool:
        return not self.errors

    def markdown(self) -> str:
        icon = {"error": "❌", "warning": "⚠️", "ok": "✅"}
        verdict = "✅ **The data can run.**" if self.passed else "❌ **The data cannot run as proposed.**"
        lines = [f"### Dataset check: `{self.proposal}`", "", verdict, "",
                 "| | Subject | Result |", "|---|---|---|"]
        for f in self.findings:
            lines.append(f"| {icon[f.level]} | `{f.subject}` | {f.message.replace('|', '/')} |")
        if self.stats:
            lines += ["", "**Sampled rows**", "",
                      "| Source | Rows read | Median chars | Under 200 chars | Duplicate prefixes | Longer than one window |",
                      "|---|---|---|---|---|---|"]
            for subject, s in self.stats.items():
                lines.append(
                    f"| `{subject}` | {s['rows']} | {s['median_chars']:,} | {s['short_share']:.0%} "
                    f"| {s['dup_share']:.0%} | {s['long_share']:.0%} |"
                )
        return "\n".join(lines) + "\n"


class _Timeout(Exception):
    pass


def _with_deadline(fn, seconds: float, what: str):
    """Run `fn` on a daemon thread and stop waiting after `seconds`.

    A daemon thread because a blocked socket read cannot be interrupted, and a
    non-daemon worker would keep the process alive after the check reported.
    """
    box: dict[str, object] = {}

    def run():
        try:
            box["value"] = fn()
        except BaseException as exc:  # noqa: BLE001 — re-raised below
            box["error"] = exc

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(timeout=seconds)
    if thread.is_alive():
        raise _Timeout(f"{what} took longer than {seconds:.0f}s")
    if "error" in box:
        raise box["error"]  # type: ignore[misc]
    return box["value"]


def _get_json(url: str, timeout: float) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "connito-expert-hunter"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def hub_info(path: str, revision: str | None = None, timeout: float = 30.0) -> dict:
    url = f"{HUB}/api/datasets/{path}"
    if revision:
        url += f"/revision/{revision}"
    return _get_json(url, timeout)


def viewer_splits(path: str, timeout: float = 30.0) -> list[tuple[str, str]] | None:
    """(config, split) pairs from the dataset viewer, or None if it has none.

    The viewer does not cover every dataset, so this only ever sharpens an error
    message; the real test is the streaming load.
    """
    url = f"{VIEWER}/splits?dataset={urllib.parse.quote(path, safe='')}"
    try:
        data = _get_json(url, timeout)
    except Exception:  # noqa: BLE001 — the viewer is best-effort
        return None
    splits = data.get("splits") or []
    return [(s.get("config"), s.get("split")) for s in splits] or None


def _check_hub_entry(report: Report, subject: str, path: str, revision: str | None,
                     gated_is_error: bool, timeout: float) -> bool:
    try:
        info = hub_info(path, revision, timeout)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 404):
            what = f"revision {revision} of {path}" if revision else path
            report.add("error", subject, f"{what} does not exist on the Hub (or is private)")
        else:
            report.add("error", subject, f"the Hub answered {exc.code} for {path}")
        return False
    except Exception as exc:  # noqa: BLE001
        report.add("error", subject, f"could not reach the Hub: {type(exc).__name__}: {exc}")
        return False

    if info.get("disabled"):
        report.add("error", subject, f"{path} is disabled on the Hub")
        return False
    _check_file_layout(report, subject, path, info, gated_is_error)
    if info.get("gated"):
        if gated_is_error:
            report.add("error", subject,
                       f"{path} is gated ({info['gated']}): every miner and validator would have to "
                       "accept its terms by hand, or reads fail with 403. Use an ungated dataset or mirror.")
            return False
        report.add("warning", subject, f"{path} is gated ({info['gated']}); the owner needs access to score it")
    return True


def _check_file_layout(report: Report, subject: str, path: str, info: dict,
                       is_training_source: bool) -> None:
    """Warn when a corpus is one big file rather than shards.

    `load_dataset(..., streaming=True)` reads parquet a row group at a time, but
    a JSON or JSONL dataset is pulled and parsed whole — every miner, every
    round. meta-math/MetaMathQA is one 400 MB JSON file, and checking it here
    exhausted the memory of the machine this check ran on.
    """
    if not is_training_source:
        return
    files = [s.get("rfilename", "") for s in info.get("siblings") or []]
    data = [f for f in files if not f.lower().endswith(NON_DATA_SUFFIXES)]
    if not data or any(f.lower().endswith(SHARDABLE_SUFFIXES) for f in data):
        return
    if len(data) <= 2:
        report.add("warning", subject,
                   f"{path} is published as {len(data)} file(s) ({', '.join(data[:2])}) in a format a "
                   "streaming reader cannot read a piece at a time; every miner would pull and parse the "
                   "whole file each round. Prefer a parquet-sharded export.")


def _stream_rows(source_path: str, name: str | None, split: str, revision: str | None,
                 n: int, timeout: float) -> list[dict]:
    from datasets import load_dataset  # heavy; only needed for this check

    def load():
        ds = load_dataset(source_path, name, split=split, streaming=True, revision=revision)
        rows = []
        for row in ds:
            rows.append(row)
            if len(rows) >= n:
                break
        return rows

    return _with_deadline(load, timeout, f"streaming {n} rows of {source_path}")


def _explain_load_error(path: str, name: str | None, split: str, exc: BaseException,
                        timeout: float) -> str:
    msg = f"{type(exc).__name__}: {exc}".strip()
    if len(msg) > 300:
        msg = msg[:300] + "…"
    known = viewer_splits(path, timeout)
    if known:
        pairs = sorted({f"name={c!r} split={s!r}" for c, s in known})
        if (name or "default", split) not in set(known):
            return f"{msg}. The Hub lists: {', '.join(pairs[:12])}"
    if "scripts are no longer supported" in str(exc):
        return f"{path} uses a loading script, which current `datasets` refuses to run. Use a parquet export."
    return msg


def render_rows(rows: list[dict], source: DatasetSource) -> list[str]:
    """The text the subnet would train on, one string per row.

    A `text_column` source is its column; a `text_template` source is the
    template filled from the row, which is how the experiment repo's
    `render.cpt.text_template` turns a question/answer corpus into training
    text. Values that are not strings are rendered as `str` does, the same as
    `str.format` would at training time.
    """
    if source.text_column:
        return [r.get(source.text_column) or "" for r in rows]
    template = source.text_template or ""
    out = []
    for r in rows:
        try:
            out.append(template.format(**r))
        except Exception:  # noqa: BLE001 — a row missing a column renders empty
            out.append("")
    return out


def _row_stats(texts: list[str], sequence_length: int) -> dict:
    lengths = [len(t) if isinstance(t, str) else 0 for t in texts]
    usable = [t for t in texts if isinstance(t, str) and len(t) >= MIN_TEXT_CHARS]
    prefixes = [t[:DEDUP_PREFIX_CHARS] for t in usable]
    window_chars = sequence_length * CHARS_PER_TOKEN
    return {
        "rows": len(texts),
        "median_chars": int(statistics.median(lengths)) if lengths else 0,
        "short_share": 1 - len(usable) / len(texts) if texts else 1.0,
        "dup_share": 1 - len(set(prefixes)) / len(prefixes) if prefixes else 0.0,
        "long_share": sum(1 for n in lengths if n > window_chars) / len(texts) if texts else 0.0,
    }


def check_source(report: Report, source: DatasetSource, sequence_length: int,
                 sample_rows: int, timeout: float) -> None:
    subject = source.path + (f" [{source.name}]" if source.name else "") + f" / {source.split}"
    if not _check_hub_entry(report, subject, source.path, source.revision, True, timeout):
        return
    try:
        rows = _stream_rows(source.path, source.name, source.split, source.revision,
                            sample_rows, timeout)
    except _Timeout as exc:
        report.add("error", subject, f"{exc}; a miner's dataloader would stall the same way")
        return
    except Exception as exc:  # noqa: BLE001
        report.add("error", subject, "cannot be streamed: "
                   + _explain_load_error(source.path, source.name, source.split, exc, timeout))
        return
    if not rows:
        report.add("error", subject, f"split {source.split!r} streamed zero rows")
        return

    columns = sorted(rows[0].keys())
    missing = [c for c in source.columns_used if c not in rows[0]]
    if missing:
        what = "no column" if len(missing) == 1 else "no columns"
        report.add("error", subject, f"{what} {', '.join(repr(c) for c in missing)}; "
                                     f"the columns are {columns}")
        return
    if source.text_column:
        non_text = sum(1 for r in rows if not isinstance(r.get(source.text_column), str))
        if non_text:
            report.add("error", subject,
                       f"{source.text_column!r} is not text in {non_text} of {len(rows)} rows; "
                       "use a text column, or a text_template that renders one")
            return

    texts = render_rows(rows, source)
    stats = _row_stats(texts, sequence_length)
    report.stats[subject] = stats
    if stats["short_share"] > 0.5:
        report.add("error", subject,
                   f"{stats['short_share']:.0%} of sampled rows are under {MIN_TEXT_CHARS} characters; "
                   "the validator's eval drops those, so there would be too little to score on")
    elif stats["short_share"] > 0.1:
        report.add("warning", subject,
                   f"{stats['short_share']:.0%} of sampled rows are under {MIN_TEXT_CHARS} characters "
                   "and would be dropped from evaluation")
    if stats["dup_share"] > 0.3:
        report.add("error", subject,
                   f"{stats['dup_share']:.0%} of sampled rows share their first {DEDUP_PREFIX_CHARS} "
                   "characters with another row; the eval would measure memorising a few documents")
    elif stats["dup_share"] > 0.05:
        report.add("warning", subject,
                   f"{stats['dup_share']:.0%} of sampled rows share a {DEDUP_PREFIX_CHARS}-character prefix")
    if not any(f.subject == subject and f.level == "error" for f in report.findings):
        what = (f"{source.text_column!r} is usable text" if source.text_column
                else f"text_template over {', '.join(repr(c) for c in source.template_columns)} renders usable text")
        report.add("ok", subject, f"streams, and {what} ({len(rows)} rows sampled)")


def _lm_eval_task_exists(task: str) -> bool | None:
    """True/False if lm-eval is installed, None if it is not (then unverified)."""
    try:
        from lm_eval.tasks import TaskManager
    except ImportError:
        return None
    return task in TaskManager().all_tasks


def check_benchmark(report: Report, bench: Benchmark, timeout: float) -> None:
    subject = f"benchmark {bench.name}"
    ds = bench.dataset
    if not _check_hub_entry(report, subject, ds.path, None, False, timeout):
        return
    try:
        rows = _stream_rows(ds.path, ds.name, ds.split, None, 1, timeout)
    except _Timeout as exc:
        report.add("warning", subject, f"{exc}; could not confirm the split is readable")
        rows = None
    except Exception as exc:  # noqa: BLE001
        report.add("error", subject, "scored split cannot be read: "
                   + _explain_load_error(ds.path, ds.name, ds.split, exc, timeout))
        return
    if rows is not None and not rows:
        report.add("error", subject, f"split {ds.split!r} of {ds.path} is empty")
        return

    if bench.harness == "lm_eval":
        exists = _lm_eval_task_exists(bench.task or "")
        if exists is False:
            report.add("error", subject,
                       f"lm-eval has no task {bench.task!r}. If it is a custom task, say so in the PR "
                       "and include its YAML; the owner will review it.")
            return
        if exists is None:
            report.add("ok", subject, f"{ds.path} / {ds.split} is readable "
                                      f"(lm-eval task {bench.task!r} not verified: lm-eval is not installed)")
            return
        report.add("ok", subject, f"{ds.path} / {ds.split} is readable and lm-eval knows {bench.task!r}")
    else:
        report.add("ok", subject, f"{ds.path} / {ds.split} is readable for a held-out loss")


def check_proposal(proposal: Proposal, sample_rows: int = DEFAULT_SAMPLE_ROWS,
                   timeout: float = DEFAULT_TIMEOUT) -> Report:
    report = Report(proposal.name)
    for source in proposal.data.dataset_sources:
        check_source(report, source, proposal.data.sequence_length, sample_rows, timeout)
    for bench in proposal.benchmarks:
        check_benchmark(report, bench, timeout)
    return report
