"""Check proposals: `python -m expert_hunter.check [NAME ...] [--network]`.

Without `--network`: the offline schema check of every proposal (or the ones
named). Seconds, no dependencies beyond pydantic and PyYAML.

With `--network`: also load each named proposal's datasets from the Hub the way
a miner would, and sample their rows (see `expert_hunter.hub`). Writes a Markdown
report with `--report FILE`, which CI attaches to the pull request.

Exits non-zero if anything is wrong.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from expert_hunter import proposals as P


def _resolve(names: list[str]) -> list[Path]:
    if not names:
        return P.proposal_files(P.PROPOSALS_DIR)
    files = []
    for name in names:
        path = P.find(name)
        if path is None:
            raise SystemExit(f"no proposal {name!r} (give a task name or a path to its .yaml)")
        files.append(path)
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("names", nargs="*", help="task names or .yaml paths (default: all proposals)")
    parser.add_argument("--network", action="store_true", help="also check the data can run")
    parser.add_argument("--rows", type=int, default=200, help="rows to sample per source")
    parser.add_argument("--timeout", type=float, default=90.0, help="seconds per Hub load")
    parser.add_argument("--report", type=Path, help="write the Markdown report here")
    args = parser.parse_args(argv)

    files = _resolve(args.names)
    # With no names, check the whole tree: layout, every file, and task names
    # used twice across folders. With names, just those files.
    offline = P.all_problems(P.PROPOSALS_DIR) if not args.names else \
        [p for f in files for p in P.problems(f)]
    if not files and not offline:
        print("no proposals to check")
        return 0
    for problem in offline:
        print(f"✗ {problem}", file=sys.stderr)
    report_md = []
    if offline:
        report_md.append("### Proposal file check\n\n❌ **The proposal file has problems:**\n\n"
                         + "\n".join(f"- {p}" for p in offline) + "\n")
    else:
        print(f"✓ {len(files)} proposal(s) well-formed: "
              f"{', '.join(f'{f.parent.name}/{f.name}' for f in files)}")

    failed = bool(offline)
    if args.network and not offline:
        from expert_hunter.hub import check_proposal

        for f in files:
            print(f"… checking that {f.stem}'s data can run (this streams from the Hub)")
            report = check_proposal(P.load(f), sample_rows=args.rows, timeout=args.timeout)
            for finding in report.findings:
                mark = {"error": "✗", "warning": "!", "ok": "✓"}[finding.level]
                print(f"  {mark} {finding.subject}: {finding.message}")
            report_md.append(report.markdown())
            failed |= not report.passed

    if args.report:
        args.report.write_text("\n".join(report_md) or "✅ Nothing to report.\n", encoding="utf-8")
    return 1 if failed else 0


def run() -> None:
    """Entry point. Exits with os._exit after --network: `datasets` leaves
    streaming threads running, and a normal interpreter shutdown then aborts
    with "terminate called without an active exception" and a wrong exit code."""
    code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)


if __name__ == "__main__":
    run()
