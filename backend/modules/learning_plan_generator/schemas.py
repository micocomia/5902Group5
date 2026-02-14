from __future__ import annotations

from enum import Enum
from typing import List, Sequence

from pydantic import BaseModel, Field, field_validator


class Proficiency(str, Enum):
    beginner = "beginner"
    intermediate = "intermediate"
    advanced = "advanced"


class DesiredOutcome(BaseModel):
    name: str = Field(..., description="Skill name")
    level: Proficiency = Field(..., description="Desired proficiency when completed")


class SessionItem(BaseModel):
    id: str = Field(..., description="Session identifier, e.g., 'Session 1'")
    title: str
    abstract: str
    if_learned: bool
    associated_skills: List[str] = Field(default_factory=list)
    desired_outcome_when_completed: List[DesiredOutcome] = Field(default_factory=list)

    @field_validator("associated_skills")
    @classmethod
    def ensure_nonempty_strings(cls, v: Sequence[str]) -> List[str]:
        return [s for s in (str(x).strip() for x in v) if s]


class LearningPath(BaseModel):
    learning_path: List[SessionItem]

    @field_validator("learning_path")
    @classmethod
    def limit_sessions(cls, v: List[SessionItem]) -> List[SessionItem]:
        if not (1 <= len(v) <= 10):
            raise ValueError("Learning path must contain between 1 and 10 sessions.")
        return v
