"""Rank open proposal PRs by upvotes: `python -m expert_hunter.leaderboard`.

Writes LEADERBOARD.md. Needs `GITHUB_TOKEN` (read access is enough) and
`GITHUB_REPOSITORY` (`owner/repo`); both are set inside GitHub Actions.

The rules, which doc/GUIDE.md repeats for proposers:

* A candidate is an open, non-draft PR that adds or edits exactly one
  `proposals/<name>/proposal.yaml`.
* A vote is a 👍 reaction on the PR itself (its description, not a comment).
  One per GitHub account. The PR's author, bots, and accounts younger than
  MIN_ACCOUNT_AGE_DAYS do not count — the last one because votes decide what a
  subnet trains, and fresh accounts are the cheapest way to stuff a ballot.
* Only candidates whose `data-can-run` check passed on their latest commit are
  ranked. The rest are listed below the ranking so their authors can see why.
* Ties go to the PR opened first.

The ranking decides the order the owner reviews proposals in. It is not an
automatic schedule: the owner still reviews the winner before it runs.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

API = "https://api.github.com"
CHECK_NAME = "data-can-run"
MIN_ACCOUNT_AGE_DAYS = 30
PROPOSAL_FILE_RE = re.compile(r"^proposals/([^/_][^/]*)/proposal\.yaml$")


@dataclass
class Candidate:
    number: int
    title: str
    author: str
    url: str
    created_at: str
    proposal: str | None
    upvoters: list[str] = field(default_factory=list)
    downvotes: int = 0
    comments: int = 0
    check: str = "pending"      # "success" | "failure" | "pending"
    problem: str | None = None  # why it is not a valid candidate

    @property
    def votes(self) -> int:
        return len(self.upvoters)

    @property
    def eligible(self) -> bool:
        return self.problem is None and self.check == "success"


def proposal_from_files(filenames: list[str]) -> tuple[str | None, str | None]:
    """(proposal name, problem) from the files a PR touches."""
    names = {m.group(1) for f in filenames if (m := PROPOSAL_FILE_RE.match(f))}
    touched = {f.split("/")[1] for f in filenames if f.startswith("proposals/") and f.count("/") >= 2}
    if not names:
        return None, "does not add a proposals/<name>/proposal.yaml"
    if len(names) > 1 or len(touched) > 1:
        return None, "touches more than one proposal; open one PR per proposal"
    outside = [f for f in filenames if not f.startswith("proposals/")]
    if outside:
        return next(iter(names)), f"also changes files outside proposals/: {', '.join(outside[:3])}"
    return next(iter(names)), None


def count_votes(reactions: list[dict], author: str, account_created: dict[str, str],
                now: datetime) -> tuple[list[str], int]:
    """(counted upvoters, downvote count) under the rules in the module docstring."""
    up, down = set(), set()
    for r in reactions:
        user = r.get("user") or {}
        login = user.get("login", "")
        if not login or login == author or user.get("type") == "Bot" or login.endswith("[bot]"):
            continue
        created = account_created.get(login)
        if created:
            age = now - datetime.fromisoformat(created.replace("Z", "+00:00"))
            if age.days < MIN_ACCOUNT_AGE_DAYS:
                continue
        if r.get("content") == "+1":
            up.add(login)
        elif r.get("content") == "-1":
            down.add(login)
    return sorted(up), len(down)


def rank(candidates: list[Candidate]) -> list[Candidate]:
    eligible = [c for c in candidates if c.eligible]
    return sorted(eligible, key=lambda c: (-c.votes, c.created_at, c.number))


def render(candidates: list[Candidate], repo: str, now: datetime) -> str:
    ranked = rank(candidates)
    lines = [
        "# Task proposal leaderboard",
        "",
        f"_Updated {now:%Y-%m-%d %H:%M} UTC from the open pull requests of `{repo}`. "
        "Do not edit by hand — a workflow regenerates this file._",
        "",
        "Vote with a 👍 on the pull request itself. Discuss in its comments. "
        "See [doc/GUIDE.md](doc/GUIDE.md) for the rules.",
        "",
    ]
    if ranked:
        lines += ["| Rank | Proposal | 👍 | 👎 | Comments | Proposed by |",
                  "|---|---|---|---|---|---|"]
        for i, c in enumerate(ranked, 1):
            lines.append(f"| {i} | [`{c.proposal}`]({c.url}) — {c.title} | {c.votes} | {c.downvotes} "
                         f"| {c.comments} | @{c.author} |")
    else:
        lines.append("_No eligible proposals yet._")

    waiting = [c for c in candidates if not c.eligible]
    if waiting:
        lines += ["", "## Not ranked yet", "",
                  "| PR | Why | 👍 so far |", "|---|---|---|"]
        for c in sorted(waiting, key=lambda c: c.number):
            why = c.problem or {"failure": f"the `{CHECK_NAME}` check failed",
                                "pending": f"the `{CHECK_NAME}` check has not passed yet"}[c.check]
            lines.append(f"| [#{c.number}]({c.url}) {c.title} | {why} | {c.votes} |")
    return "\n".join(lines) + "\n"


class GitHub:
    def __init__(self, repo: str, token: str | None):
        self.repo, self.token = repo, token

    def get(self, path: str, accept: str = "application/vnd.github+json"):
        url = path if path.startswith("http") else f"{API}{path}"
        results, page = [], 1
        while True:
            sep = "&" if "?" in url else "?"
            req = urllib.request.Request(f"{url}{sep}per_page=100&page={page}",
                                         headers={"Accept": accept, "User-Agent": "connito-expert-hunter"})
            if self.token:
                req.add_header("Authorization", f"Bearer {self.token}")
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.load(resp)
            if not isinstance(data, list):
                return data
            results += data
            if len(data) < 100:
                return results
            page += 1

    def candidates(self) -> list[Candidate]:
        out, created = [], {}
        for pr in self.get(f"/repos/{self.repo}/pulls?state=open"):
            if pr.get("draft"):
                continue
            n, author = pr["number"], pr["user"]["login"]
            files = [f["filename"] for f in self.get(f"/repos/{self.repo}/pulls/{n}/files")]
            proposal, problem = proposal_from_files(files)
            reactions = self.get(f"/repos/{self.repo}/issues/{n}/reactions")
            for r in reactions:
                login = (r.get("user") or {}).get("login")
                if login and login not in created:
                    created[login] = self.get(f"/users/{login}").get("created_at", "")
            up, down = count_votes(reactions, author, created, datetime.now(timezone.utc))
            issue = self.get(f"/repos/{self.repo}/issues/{n}")
            runs = self.get(f"/repos/{self.repo}/commits/{pr['head']['sha']}/check-runs"
                            f"?check_name={CHECK_NAME}").get("check_runs", [])
            conclusion = runs[0].get("conclusion") if runs else None
            check = "success" if conclusion == "success" else "failure" if conclusion else "pending"
            out.append(Candidate(
                number=n, title=pr["title"], author=author, url=pr["html_url"],
                created_at=pr["created_at"], proposal=proposal, upvoters=up, downvotes=down,
                comments=issue.get("comments", 0) + pr.get("review_comments", 0),
                check=check, problem=problem,
            ))
        return out


def main(argv: list[str] | None = None) -> int:
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        print("set GITHUB_REPOSITORY=owner/repo", file=sys.stderr)
        return 2
    out = Path(argv[0]) if argv else Path("LEADERBOARD.md")
    candidates = GitHub(repo, os.environ.get("GITHUB_TOKEN")).candidates()
    out.write_text(render(candidates, repo, datetime.now(timezone.utc)), encoding="utf-8")
    print(f"wrote {out}: {len(rank(candidates))} ranked, {len(candidates)} open proposal PR(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
