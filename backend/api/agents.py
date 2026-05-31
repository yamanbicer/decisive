from fastapi import APIRouter, Depends, HTTPException

from ..db.repository import get_repo
from ..schemas import Agent, AgentUpdate
from .deps import get_current_user

router = APIRouter(prefix="/agents", tags=["agents"])


@router.patch("/{agent_id}", response_model=Agent)
def update_agent(agent_id: str, body: AgentUpdate, user: str = Depends(get_current_user)):
    agent = get_repo().update_agent(agent_id, body)
    if not agent:
        raise HTTPException(404, "agent not found")
    return agent
