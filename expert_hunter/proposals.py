"""Finding and loading proposals on disk.

A proposal is one file, `proposals/<github-login>/<task-name>.yaml`:

* the directory is the proposer's GitHub login, so everyone writes only in a
  folder of their own (the `submission-rules` check enforces that it is the
  pull request author's folder — see `expert_hunter.submission`);
* the file name is the task's `name`, so the task name is unique per folder and
  visible in the pull request's file list.

`examples/` uses the same layout; its files are checked like proposals.
"""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from expert_hunter.schema import Proposal

ROOT = Path(__file__).resolve().parent.parent
PROPOSALS_DIR = ROOT / "proposals"
EXAMPLES_DIR = ROOT / "examples"
SUFFIX = ".yaml"


def _visible(path: Path) -> bool:
    return not path.name.startswith(".")


def proposal_files(*roots: Path) -> list[Path]:
    """Every `<login>/<name>.yaml` under `roots`."""
    roots = roots or (PROPOSALS_DIR,)
    return sorted(
        f for root in roots if root.is_dir()
        for d in root.iterdir() if d.is_dir() and _visible(d)
        for f in d.iterdir() if f.is_file() and f.suffix == SUFFIX
    )


def layout_problems(*roots: Path) -> list[str]:
    """Files under `roots` that are not `<login>/<name>.yaml`."""
    roots = roots or (PROPOSALS_DIR,)
    found = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            rel = path.relative_to(root)
            if not all(_visible(Path(p)) for p in rel.parts) or path.is_dir():
                continue
            if len(rel.parts) != 2 or path.suffix != SUFFIX:
                found.append(f"{root.name}/{rel}: only <github-login>/<task-name>{SUFFIX} files belong here")
    return found


def load(path: Path) -> Proposal:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.name}: expected a mapping at the top level")
    return Proposal(**data)


def problems(path: Path) -> list[str]:
    """Everything wrong with one proposal file that can be seen offline."""
    label = f"{path.parent.name}/{path.name}"
    try:
        proposal = load(path)
    except yaml.YAMLError as exc:
        return [f"{label}: not valid YAML — {exc}"]
    except ValidationError as exc:
        found = []
        for err in exc.errors():
            where = ".".join(str(p) for p in err["loc"]) or "(top level)"
            found.append(f"{label}: {where}: {err['msg']}")
        return found
    except ValueError as exc:
        return [f"{label}: {exc}"]

    found = []
    if proposal.name != path.stem:
        found.append(f"{label}: the file must be named after the proposal's name ({proposal.name}{SUFFIX})")
    # GitHub logins are case-insensitive.
    if proposal.proposer.github.lower() != path.parent.name.lower():
        found.append(
            f"{label}: proposer.github is {proposal.proposer.github!r} but the file is in "
            f"{path.parent.name}/ — the folder must be the proposer's GitHub login"
        )
    return found


def all_problems(*roots: Path) -> list[str]:
    """Problems across every proposal, including task names used twice."""
    roots = roots or (PROPOSALS_DIR,)
    found = layout_problems(*roots)
    files = proposal_files(*roots)
    for f in files:
        found += problems(f)
    stems = [f.stem for f in files]
    for name in sorted({n for n in stems if stems.count(n) > 1}):
        owners = ", ".join(f.parent.name for f in files if f.stem == name)
        found.append(f"{name}: proposed by more than one person ({owners}); task names must be unique")
    return found


def find(name: str) -> Path | None:
    """The proposal or example file for a task name, or a path given directly."""
    path = Path(name)
    if path.is_file():
        return path
    for f in proposal_files(PROPOSALS_DIR, EXAMPLES_DIR):
        if f.stem == name:
            return f
    return None
