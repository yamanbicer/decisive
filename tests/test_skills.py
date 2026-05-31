"""Skill files: progressive disclosure (short manifest always, full body on demand)."""
from backend.engine.skills import load_skills, reset_skills, skill_manifest, use_skill


async def test_use_skill_returns_full_body():
    reset_skills()
    res = await use_skill({"name": "product-teardown"}, None)
    assert res.get("skill") == "product-teardown"
    assert "Rubric" in res["body"]


def test_manifest_is_much_shorter_than_body():
    skills = load_skills()
    assert "product-teardown" in skills, "expected the bundled skill files to load"
    manifest = skill_manifest(["product-teardown"])
    body = skills["product-teardown"].body
    assert 0 < len(manifest) < len(body)   # the whole point of progressive disclosure


async def test_unknown_skill_returns_error():
    res = await use_skill({"name": "does-not-exist"}, None)
    assert "error" in res and "available" in res
