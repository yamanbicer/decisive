"""Context optimization: budgeting helpers + the compact board stay bounded."""
from backend.config import get_settings
from backend.engine.budget import est_tokens, fit_to_budget, pack_lines
from backend.engine.debate import _render_board
from backend.schemas import Agent, Position, Stance


def test_est_tokens_rough():
    assert est_tokens("x" * 400) >= 90


def test_fit_to_budget_truncates():
    out = fit_to_budget("y" * 1000, 200)
    assert len(out) <= 200 and "truncated" in out


def test_pack_lines_keeps_recent_and_marks_drops():
    lines = [f"line-{i} " + "z" * 50 for i in range(20)]
    out = pack_lines(lines, 200, keep="tail")
    assert "omitted for budget" in out
    assert "line-19" in out                     # most-recent kept (tail)


def test_compact_board_stays_under_budget():
    agents = [Agent(id=f"a{i}", org_id="o", name=f"N{i}", role="Role title", system_prompt="")
              for i in range(8)]
    positions = {a.id: Position(stance=Stance.YES, score=7.0, confidence=0.8,
                                rationale="r" * 400) for a in agents}
    board = _render_board(positions, agents)
    assert len(board) <= get_settings().board_char_budget + 80
