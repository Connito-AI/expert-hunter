"""Who may change what: `python -m expert_hunter.submission`.

GitHub cannot stop anyone opening a pull request that touches any file. What it
can do is refuse to merge one whose required checks fail, and this is that
check (the `submission-rules` job). For a pull request from anyone who is not a
maintainer, every changed file must be

    proposals/<their-github-login>/<task-name>.yaml

— their own folder, a YAML file, nothing else: no README, no scripts, no edits
to the checker, the docs, or another person's folder. At most one proposal is
added or edited per pull request, so each one collects its own votes. Deleting
one's own proposal (withdrawing it) is allowed.

Maintainers are exempt: they change the code and docs, and they tidy up
proposals. Their pull requests are still reviewed. A maintainer is an author
whose GitHub author association is OWNER, MEMBER or COLLABORATOR, or who is
named in the trusted list (the workflow's TRUSTED_AUTHORS). The list exists
because the association is not enough on its own: a GitHub App opening pull
requests shows as NONE (connito-client-dev[bot] does), and an org member whose
membership is private can show as CONTRIBUTOR.

The folder is compared with the pull request author's login, which GitHub
supplies and the author cannot forge; the proposal file's own
`proposer.github` must match its folder (checked in `proposals.problems`), so
the three agree.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import PurePosixPath

MAINTAINER_ASSOCIATIONS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})
SUFFIX = ".yaml"


@dataclass(frozen=True)
class Change:
    status: str                  # git's letter: A, M, D, R (rename), C (copy), T (type)
    path: str
    old_path: str | None = None


def _own_proposal(path: str, author: str) -> str | None:
    """Why `path` is not one of `author`'s proposal files, or None if it is."""
    parts = PurePosixPath(path).parts
    if len(parts) != 3 or parts[0] != "proposals":
        return f"`{path}` is outside proposals/<your-login>/ — only `proposals/{author}/<task-name>{SUFFIX}` may change"
    if parts[1].lower() != author.lower():
        return f"`{path}` is in `{parts[1]}`'s folder — you may only add files under `proposals/{author}/`"
    if not parts[2].endswith(SUFFIX) or parts[2].startswith("."):
        return f"`{path}` is not a `{SUFFIX}` file — a submission is a single `<task-name>{SUFFIX}` and nothing else"
    return None


def is_maintainer(author: str, association: str, trusted: frozenset[str] = frozenset()) -> bool:
    return association.upper() in MAINTAINER_ASSOCIATIONS or author.lower() in trusted


def parse_trusted(value: str) -> frozenset[str]:
    return frozenset(t.strip().lower() for t in value.replace("\n", ",").split(",") if t.strip())


def violations(author: str, association: str, changes: list[Change],
               trusted: frozenset[str] = frozenset()) -> list[str]:
    """Everything this pull request changes that its author may not change."""
    if is_maintainer(author, association, trusted):
        return []
    if not changes:
        return ["this pull request changes no files"]

    found: list[str] = []
    submitted: list[str] = []
    for c in changes:
        for path in filter(None, (c.old_path, c.path)):
            why = _own_proposal(path, author)
            if why and why not in found:
                found.append(why)
        # Only files that ARE proposals count toward "one per pull request";
        # anything else has already been reported above.
        if c.status[:1] in "AMRCT" and _own_proposal(c.path, author) is None:
            submitted.append(c.path)
    if len(submitted) > 1:
        found.append(
            f"this pull request adds or edits {len(submitted)} proposals ({', '.join(submitted)}); "
            "open one pull request per proposal so each collects its own votes"
        )
    return found


def changes_from_git(base: str, repo: str = ".") -> list[Change]:
    """Changed files between `base` and HEAD, as git sees them (renames detected)."""
    out = subprocess.run(
        ["git", "-C", repo, "diff", "--name-status", "-M", f"{base}...HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout
    changes = []
    for line in out.splitlines():
        fields = line.split("\t")
        if fields[0][:1] in "RC":
            changes.append(Change(fields[0][:1], fields[2], fields[1]))
        else:
            changes.append(Change(fields[0][:1], fields[1]))
    return changes


def report(author: str, association: str, found: list[str],
           trusted: frozenset[str] = frozenset()) -> str:
    if is_maintainer(author, association, trusted):
        return (f"### Submission rules\n\n✅ @{author} is a maintainer (association {association}"
                f"{', on the trusted list' if author.lower() in trusted else ''}); "
                "the file rules do not apply.\n")
    if not found:
        return (f"### Submission rules\n\n✅ Only `proposals/{author}/` changed, and only a `{SUFFIX}` "
                "proposal.\n")
    return ("### Submission rules\n\n❌ **This pull request changes files its author may not change.**\n\n"
            + "\n".join(f"- {v}" for v in found)
            + f"\n\nA submission is exactly one file, `proposals/{author}/<task-name>{SUFFIX}`. "
              "See doc/GUIDE.md.\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--author", required=True, help="the pull request author's GitHub login")
    parser.add_argument("--association", required=True,
                        help="GitHub's author_association for the pull request (OWNER, CONTRIBUTOR, ...)")
    parser.add_argument("--base", required=True, help="the base commit to diff against")
    parser.add_argument("--repo", default=".", help="checkout of the pull request")
    parser.add_argument("--trusted", default="",
                        help="comma-separated logins treated as maintainers whatever their association")
    parser.add_argument("--report", help="also write the Markdown report here")
    args = parser.parse_args(argv)

    trusted = parse_trusted(args.trusted)
    found = violations(args.author, args.association, changes_from_git(args.base, args.repo), trusted)
    text = report(args.author, args.association, found, trusted)
    print(text)
    if args.report:
        with open(args.report, "a", encoding="utf-8") as fh:
            fh.write(text)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
