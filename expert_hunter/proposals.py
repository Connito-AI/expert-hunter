"""Finding and loading proposals on disk."""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from expert_hunter.schema import Proposal

ROOT = Path(__file__).resolve().parent.parent
PROPOSALS_DIR = ROOT / "proposals"
EXAMPLES_DIR = ROOT / "examples"
PROPOSAL_FILE = "proposal.yaml"


def proposal_dirs(*roots: Path) -> list[Path]:
    """Every proposal directory under `roots` (`_template` is not a proposal)."""
    roots = roots or (PROPOSALS_DIR,)
    return sorted(
        d for root in roots if root.is_dir()
        for d in root.iterdir()
        if d.is_dir() and not d.name.startswith(("_", "."))
    )


def load(proposal_dir: Path) -> Proposal:
    path = proposal_dir / PROPOSAL_FILE
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a mapping at the top level")
    return Proposal(**data)


def problems(proposal_dir: Path) -> list[str]:
    """Everything wrong with one proposal directory that can be seen offline."""
    label = proposal_dir.name
    path = proposal_dir / PROPOSAL_FILE
    if not path.is_file():
        return [f"{label}: missing {PROPOSAL_FILE}"]
    extra = sorted(p.name for p in proposal_dir.iterdir() if p.name not in (PROPOSAL_FILE, "README.md"))
    found: list[str] = []
    if extra:
        found.append(f"{label}: only {PROPOSAL_FILE} (and an optional README.md) belong here, found {extra}")
    try:
        proposal = load(proposal_dir)
    except yaml.YAMLError as exc:
        return found + [f"{label}/{PROPOSAL_FILE}: not valid YAML — {exc}"]
    except ValidationError as exc:
        for err in exc.errors():
            where = ".".join(str(p) for p in err["loc"]) or "(top level)"
            found.append(f"{label}/{PROPOSAL_FILE}: {where}: {err['msg']}")
        return found
    except ValueError as exc:
        return found + [str(exc)]
    if proposal.name != proposal_dir.name:
        found.append(
            f"{label}: directory name must equal the proposal's name ({proposal.name!r})"
        )
    return found


def all_problems(*roots: Path) -> list[str]:
    """Problems across every proposal, including names used twice."""
    found: list[str] = []
    for d in proposal_dirs(*roots):
        found += problems(d)
    names = [d.name for d in proposal_dirs(*roots)]
    for name in sorted({n for n in names if names.count(n) > 1}):
        found.append(f"{name}: two proposals share this name")
    return found
