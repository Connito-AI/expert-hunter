"""Vote counting and ranking rules (no GitHub calls)."""
from datetime import datetime, timezone

from expert_hunter.leaderboard import Candidate, count_votes, proposal_from_files, rank, render

NOW = datetime(2026, 9, 18, tzinfo=timezone.utc)
OLD = "2020-01-01T00:00:00Z"
NEW = "2026-09-10T00:00:00Z"


def r(login, content="+1", type_="User"):
    return {"content": content, "user": {"login": login, "type": type_}}


def test_one_proposal_per_pr():
    assert proposal_from_files(["proposals/exp_a/proposal.yaml"]) == ("exp_a", None)
    assert proposal_from_files(["proposals/exp_a/proposal.yaml", "proposals/exp_a/README.md"]) == ("exp_a", None)
    _, problem = proposal_from_files(["proposals/exp_a/proposal.yaml", "proposals/exp_b/proposal.yaml"])
    assert "more than one proposal" in problem
    _, problem = proposal_from_files(["README.md"])
    assert "does not add" in problem
    name, problem = proposal_from_files(["proposals/exp_a/proposal.yaml", "expert_hunter/schema.py"])
    assert name == "exp_a" and "outside proposals/" in problem
    _, problem = proposal_from_files(["proposals/_template/proposal.yaml"])
    assert "does not add" in problem


def test_vote_rules():
    reactions = [
        r("alice"), r("alice"),              # one vote per account
        r("bob"), r("bob", "heart"),         # other reactions ignored
        r("author"),                         # own PR does not count
        r("ci[bot]"), r("dependabot", type_="Bot"),
        r("fresh"),                          # account younger than 30 days
        r("carol", "-1"),
    ]
    created = {"alice": OLD, "bob": OLD, "carol": OLD, "fresh": NEW, "author": OLD}
    up, down = count_votes(reactions, "author", created, NOW)
    assert up == ["alice", "bob"]
    assert down == 1


def cand(n, votes, check="success", created="2026-09-01", problem=None):
    return Candidate(number=n, title=f"t{n}", author="a", url=f"u{n}", created_at=created,
                     proposal=f"exp_{n}", upvoters=[f"v{i}" for i in range(votes)],
                     check=check, problem=problem)


def test_rank_by_votes_then_age():
    cs = [cand(1, 3, created="2026-09-02"), cand(2, 5), cand(3, 3, created="2026-09-01"),
          cand(4, 9, check="failure"), cand(5, 9, problem="touches more than one proposal")]
    assert [c.number for c in rank(cs)] == [2, 3, 1]


def test_render_lists_unranked_with_reason():
    md = render([cand(1, 2), cand(4, 9, check="failure"), cand(6, 0, check="pending")], "Connito-AI/expert-hunter", NOW)
    assert "| 1 | [`exp_1`](u1)" in md
    assert "`data-can-run` check failed" in md
    assert "has not passed yet" in md


def test_candidates_from_api_responses():
    """The GitHub glue, fed canned API responses in the shapes the REST API returns."""
    from expert_hunter.leaderboard import GitHub

    pr = {"number": 7, "title": "Finance", "user": {"login": "author"}, "draft": False,
          "html_url": "https://github.com/o/r/pull/7", "created_at": "2026-09-01T00:00:00Z",
          "head": {"sha": "abc"}, "review_comments": 2}
    draft = dict(pr, number=8, draft=True)
    responses = {
        "/repos/o/r/pulls?state=open": [pr, draft],
        "/repos/o/r/pulls/7/files": [{"filename": "proposals/exp_fin/proposal.yaml"}],
        "/repos/o/r/issues/7/reactions": [r("alice"), r("bob"), r("fresh"), r("author")],
        "/users/alice": {"created_at": OLD}, "/users/bob": {"created_at": OLD},
        "/users/fresh": {"created_at": "2099-01-01T00:00:00Z"}, "/users/author": {"created_at": OLD},
        "/repos/o/r/issues/7": {"comments": 3},
        "/repos/o/r/commits/abc/check-runs?check_name=data-can-run":
            {"check_runs": [{"conclusion": "success"}]},
    }
    gh = GitHub("o/r", None)
    gh.get = lambda path, accept=None: responses[path]
    [c] = gh.candidates()
    assert (c.number, c.proposal, c.upvoters, c.comments, c.check) == (7, "exp_fin", ["alice", "bob"], 5, "success")
    assert c.eligible
