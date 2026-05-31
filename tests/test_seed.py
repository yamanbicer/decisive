"""Per-user auto-seed of the Judge Panel is idempotent (spec: ensure-seed)."""
import pytest

from backend.api import orgs as orgs_mod
from backend.db.repository import InMemoryRepository
from backend.db.seed import PERSONAS_DIR, load_personas, seed_vc_committee
from backend.schemas import Provider


def test_ensure_seed_is_idempotent_per_user(monkeypatch):
    repo = InMemoryRepository()
    monkeypatch.setattr(orgs_mod, "get_repo", lambda: repo)

    first = orgs_mod.ensure_seed(user="user-1")
    # Both councils (judges + vc) are seeded on first login.
    assert {o.preset for o in first} == {"judges", "vc"}
    assert all(o.owner_id == "user-1" for o in first)

    # Second call for the same user must NOT create duplicate orgs.
    again = orgs_mod.ensure_seed(user="user-1")
    assert {o.id for o in again} == {o.id for o in first}


def test_ensure_seed_is_per_user(monkeypatch):
    repo = InMemoryRepository()
    monkeypatch.setattr(orgs_mod, "get_repo", lambda: repo)

    orgs_mod.ensure_seed(user="user-1")
    other = orgs_mod.ensure_seed(user="user-2")

    assert {o.preset for o in other} == {"judges", "vc"}
    assert all(o.owner_id == "user-2" for o in other)
    # user-1 still owns exactly their own two councils.
    assert len(repo.list_orgs("user-1")) == 2


# ── persona parsing: honor the YAML frontmatter the persona files actually use ──

@pytest.fixture
def personas():
    if not PERSONAS_DIR.exists():
        pytest.skip("personas/ not present")
    loaded = load_personas()
    assert loaded, "expected the Judge Panel personas to load"
    return {p.name: p for p in loaded}


def test_names_come_from_frontmatter(personas):
    # NOT the title-cased filename ("Raad", "Skeptic", "Nicolas").
    names = set(personas)
    assert "The Skeptic" in names
    assert "Ra'ad Siraj" in names
    assert "Nicolas (Nico) Remerscheid" in names


def test_weights_come_from_frontmatter(personas):
    # The designed panel is unevenly weighted; the Skeptic is the lightest at 0.10.
    assert personas["The Skeptic"].weight == pytest.approx(0.10)
    assert personas["Nicolas (Nico) Remerscheid"].weight == pytest.approx(0.25)
    weights = [p.weight for p in personas.values()]
    assert len(set(weights)) > 1, "weights must not all collapse to the 1.0 default"


def test_seat_order_comes_from_frontmatter(personas):
    by_position = sorted(personas.values(), key=lambda a: a.position)
    assert by_position[0].name == "Nicolas (Nico) Remerscheid"  # position 0
    assert personas["The Skeptic"].position == 4


def test_system_prompt_excludes_demo_reference(personas):
    # The fenced "demo-prep reference" block (predicted scores / natural verdict)
    # is the answer key — it must never reach the model.
    for p in personas.values():
        assert "demo-prep reference" not in p.system_prompt
        assert "Predicted scores" not in p.system_prompt
        assert "Natural verdict" not in p.system_prompt


def test_system_prompt_excludes_raw_frontmatter(personas):
    # The YAML block is metadata, not persona text — strip it but keep the body.
    for p in personas.values():
        assert "conflict_partner:" not in p.system_prompt
        assert "preset: judges" not in p.system_prompt
    assert "## Who you are" in personas["The Skeptic"].system_prompt


def test_model_and_provider_come_from_frontmatter(personas):
    # The council runs entirely on W&B Inference open models (no Anthropic), and the
    # panel is model-diverse — each judge carries its own W&B catalog id.
    for p in personas.values():
        assert p.provider == Provider.wandb
        assert "/" in p.model               # a W&B Inference id, e.g. "moonshotai/Kimi-K2.6"
    assert len({p.model for p in personas.values()}) > 1, "the panel must be model-diverse"


def test_skeptic_is_structural_and_has_veto(personas):
    skeptic = personas["The Skeptic"]
    assert skeptic.structural is True   # `structural: true` in frontmatter
    assert skeptic.veto is True         # carries a `cap_rule` block
    # The other panelists neither pin nor veto.
    others = [p for n, p in personas.items() if n != "The Skeptic"]
    assert all(not p.veto and not p.structural for p in others)


def test_every_persona_has_a_distinct_voice(personas):
    voices = [p.voice_id for p in personas.values()]
    assert all(voices), "every board member needs a voice_id for the voice boardroom"
    assert len(set(voices)) == len(voices), "voices must be distinct"


def test_personas_carry_the_research_tool(personas):
    for p in personas.values():
        assert "research" in p.tools


def test_judges_have_role_matched_tools_and_skills(personas):
    # Retooled judges: the toolkit grew beyond bare `research`, and at least one
    # judge carries a skill file.
    assert any(len(p.tools) > 1 for p in personas.values())
    assert any(p.skills for p in personas.values())


# ── the new VC Investment Committee council ──

def test_vc_committee_seeds_with_resolved_conflict_pairs():
    repo = InMemoryRepository()
    org = seed_vc_committee(repo, "u")
    assert org is not None and org.preset == "vc"
    agents = repo.list_agents(org.id)
    assert len(agents) == 5

    ids = {a.id for a in agents}
    paired = [a for a in agents if a.conflict_partner]
    assert paired, "expected declared conflict partners"
    # conflict_partner stems were resolved to real agent_ids in this council
    assert all(a.conflict_partner in ids for a in paired)

    skeptic = next(a for a in agents if a.veto)
    assert skeptic.structural
    assert any("market_research" in a.tools for a in agents)
    assert any(a.skills for a in agents)
