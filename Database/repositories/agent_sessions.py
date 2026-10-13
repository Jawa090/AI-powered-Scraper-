"""
repositories/agent_sessions.py
──────────────────────────────
Repositories for Agent, AgentSession, and AgentMessage models.
"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select

from Database.models.agent import Agent
from Database.models.message import AgentMessage
from Database.models.session import AgentSession
from Database.repositories.base import BaseRepository


class AgentRepository(BaseRepository[Agent]):
    model = Agent

    def get_by_code(self, code: str) -> Optional[Agent]:
        stmt = select(Agent).where(Agent.code == code.strip().upper()).limit(1)
        return self.session.scalars(stmt).first()

    def list_by_department(self, department_id: str) -> List[Agent]:
        return self.list(filters={"department_id": department_id})


class AgentSessionRepository(BaseRepository[AgentSession]):
    model = AgentSession

    def list_by_user(self, user_id: str, *, limit: int = 50) -> List[AgentSession]:
        return self.list(
            filters={"user_id": user_id},
            order_by="created_at",
            descending=True,
            limit=limit,
        )

    def list_by_agent(self, agent_id: str, *, limit: int = 50) -> List[AgentSession]:
        return self.list(
            filters={"agent_id": agent_id},
            order_by="created_at",
            descending=True,
            limit=limit,
        )

    def get_active_session(self, session_id: str) -> Optional[AgentSession]:
        stmt = (
            select(AgentSession)
            .where(AgentSession.id == session_id, AgentSession.status == "active")
            .limit(1)
        )
        return self.session.scalars(stmt).first()


class AgentMessageRepository(BaseRepository[AgentMessage]):
    model = AgentMessage

    def list_by_session(self, session_id: str, *, limit: int = 100) -> List[AgentMessage]:
        stmt = (
            select(AgentMessage)
            .where(AgentMessage.session_id == session_id)
            .order_by(AgentMessage.created_at.asc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt).all())
