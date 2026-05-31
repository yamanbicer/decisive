"""Seed the demo 'Judge Panel' org from the repo-root personas/ files.

Each persona file (personas/*.md|*.txt) becomes one agent. The YAML frontmatter
(name / role / weight / position / model / provider / voice_id / tools) configures
the agent; the body BELOW the frontmatter — minus the fenced "demo-prep reference"
block and any HTML comments — becomes the system_prompt.

The demo-prep block is the answer key (predicted scores, natural verdict) and must
never reach the model, so it is stripped here at load time. Files without
frontmatter fall back to filename-derived name + full body as the prompt.
"""
from __future__ import annotations

import re
from pathlib import Path

from ..schemas import AgentCreate, AgentUpdate

PERSONAS_DIR = Path(__file__).resolve().parents[2] / "personas"

# Everything from this marker down is demo-prep reference, not persona text.
_DEMO_MARKER = "demo-prep reference"
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def _split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Return (frontmatter dict, body). Only flat scalar keys are read; indented
    continuation lines (e.g. the nested cap_rule mapping) are skipped."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return {}, text
    fm: dict[str, str] = {}
    for ln in lines[1:end]:
        if not ln.strip() or ln[0] in " \t" or ":" not in ln:
            continue
        key, _, val = ln.partition(":")
        fm[key.strip()] = _strip_inline_comment(val).strip()
    return fm, "\n".join(lines[end + 1:])


def _strip_inline_comment(val: str) -> str:
    """Drop a trailing ` # ...` YAML comment. A '#' only starts a comment when
    preceded by whitespace (or at the start), so in-value '#' chars are safe."""
    out = []
    for i, ch in enumerate(val):
        if ch == "#" and (i == 0 or val[i - 1] in " \t"):
            break
        out.append(ch)
    return "".join(out)


def _clean_body(body: str) -> str:
    """Drop the demo-prep block and any HTML comments; the rest is the prompt."""
    kept: list[str] = []
    for ln in body.splitlines():
        if _DEMO_MARKER in ln:
            break
        kept.append(ln)
    return _COMMENT_RE.sub("", "\n".join(kept)).strip()


def _opt(val: str | None) -> str | None:
    if val is None:
        return None
    v = val.strip()
    return None if v.lower() in ("", "null", "none", "~") else v


def _float(val: str | None, default: float) -> float:
    try:
        return float(val) if val not in (None, "") else default
    except (TypeError, ValueError):
        return default


def _int(val: str | None, default: int) -> int:
    try:
        return int(val) if val not in (None, "") else default
    except (TypeError, ValueError):
        return default


def _bool(val: str | None) -> bool:
    return (val or "").strip().lower() in ("true", "yes", "1")


def _tools(val: str | None) -> list[str]:
    if not val:
        return []
    v = val.strip().strip("[]")
    return [p.strip().strip("\"'") for p in v.split(",") if p.strip().strip("\"'")]


def _council_dir(subdir: str | None) -> Path:
    return PERSONAS_DIR if not subdir else PERSONAS_DIR / subdir


def _load_council(subdir: str | None = None):
    """Parse a council's persona files. Returns a list of
    (stem, AgentCreate, conflict_partner_stem, conflict_dimension).

    The conflict_partner in frontmatter is a file *stem* (e.g. `uma`), resolved to
    the partner's real agent_id after all agents in the council are created.
    """
    directory = _council_dir(subdir)
    if not directory.exists():
        return []
    out = []
    for i, path in enumerate(sorted(directory.glob("*"))):
        if path.suffix.lower() not in (".md", ".txt"):
            continue
        fm, body = _split_frontmatter(path.read_text(encoding="utf-8", errors="ignore"))
        kwargs: dict = dict(
            name=fm.get("name") or path.stem.replace("_", " ").title(),
            role=fm.get("role") or "Panelist",
            system_prompt=_clean_body(body),
            weight=_float(fm.get("weight"), 1.0),
            position=_int(fm.get("position"), i),
            tools=_tools(fm.get("tools")),
            skills=_tools(fm.get("skills")),
            structural=_bool(fm.get("structural")),
            # A persona vetoes if it declares `veto: true` or carries a `cap_rule` block.
            veto=_bool(fm.get("veto")) or "cap_rule" in fm,
        )
        if fm.get("model"):
            kwargs["model"] = fm["model"]
        if fm.get("provider"):
            kwargs["provider"] = fm["provider"]
        if _opt(fm.get("voice_id")):
            kwargs["voice_id"] = fm["voice_id"].strip()
        out.append((path.stem, AgentCreate(**kwargs),
                    _opt(fm.get("conflict_partner")), _opt(fm.get("conflict_dimension"))))
    return out


def load_personas(subdir: str | None = None) -> list[AgentCreate]:
    """The AgentCreate list for a council (root = the Judge Panel). Back-compat."""
    return [ac for _, ac, _, _ in _load_council(subdir)]


def _seed_council(repo, owner_id: str, subdir: str | None, name: str,
                  description: str, preset: str):
    """Create one council org, its agents, then resolve conflict_partner stems
    to the partners' real agent_ids. Returns the Org (or None if no personas)."""
    metas = _load_council(subdir)
    if not metas:
        return None
    org = repo.create_org(owner_id, name=name, description=description, preset=preset)
    created: dict[str, tuple] = {}   # stem -> (agent_id, partner_stem, dimension)
    for stem, ac, cp, cd in metas:
        ag = repo.create_agent(org.id, ac)
        created[stem] = (ag.id, cp, cd)
    for stem, (aid, cp, cd) in created.items():
        if cp and cp in created:
            repo.update_agent(aid, AgentUpdate(conflict_partner=created[cp][0],
                                               conflict_dimension=cd))
    return org


def seed_judge_panel(repo, owner_id: str):
    """Create the 'Hackathon Judge Panel' org + agents. Returns the Org (or None)."""
    return _seed_council(
        repo, owner_id, None, "Hackathon Judge Panel",
        "The Most Sophisticated Harness judges, modeled as agents.", "judges")


def seed_vc_committee(repo, owner_id: str):
    """Create the 'VC Investment Committee' org from personas/vc/. Returns Org/None."""
    return _seed_council(
        repo, owner_id, "vc", "VC Investment Committee",
        "A seed-stage investment committee with role-matched research tools.", "vc")


# Council seeders by preset, used to ensure each council exists for a user.
COUNCIL_SEEDERS = {"judges": seed_judge_panel, "vc": seed_vc_committee}


def seed_all_councils(repo, owner_id: str) -> list:
    """Seed every available council (skipping any with no personas). Returns Orgs."""
    orgs = [seed(repo, owner_id) for seed in COUNCIL_SEEDERS.values()]
    return [o for o in orgs if o]
