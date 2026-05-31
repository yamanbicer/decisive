"""Per-agent tool registry + allowlist enforcement (mock mode, no network)."""
from backend.engine import web_research
from backend.engine.tool_registry import ToolContext, default_registry, reset_registry
from backend.engine.tools import execute_tool
from backend.schemas import Agent


def _agent(tools, skills=None):
    return Agent(id="a", org_id="o", name="A", role="r", system_prompt="",
                 tools=tools, skills=skills or [])


async def test_allowlist_blocks_unlisted_tool():
    reset_registry()
    ctx = ToolContext(agent=_agent(["research"]))
    res = await execute_tool("market_research", {"company": "x"}, ctx)
    assert "error" in res and "allowlist" in res["error"]


async def test_allowed_tool_runs_and_returns_evidence():
    ctx = ToolContext(agent=_agent(["market_research"]))
    res = await execute_tool("market_research", {"company": "Acme"}, ctx)
    assert "evidence" in res and isinstance(res["evidence"], list)


def test_manifest_lists_only_allowed_tools():
    reg = default_registry()
    manifest = reg.manifest_for(_agent(["research", "market_research"]))
    assert "market_research" in manifest
    assert "competitor_scan" not in manifest


def test_use_skill_allowed_only_when_agent_has_skills():
    reg = default_registry()
    assert "use_skill" not in reg.effective_tool_names(_agent(["research"]))
    assert "use_skill" in reg.effective_tool_names(_agent(["research"], skills=["product-teardown"]))


async def test_web_mock_provider_is_deterministic():
    web_research.reset_web_provider()
    p = web_research.get_web_provider()
    assert await p.search("startup x") == await p.search("startup x")
