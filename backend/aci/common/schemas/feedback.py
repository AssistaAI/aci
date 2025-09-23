"""
Schemas for function search feedback.
"""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class FunctionSearchFeedbackCreate(BaseModel):
    """Schema for creating function search feedback."""

    intent: str | None = Field(None, description="The search intent/query used")
    returned_function_names: list[str] = Field(..., description="List of function names returned by the search")
    selected_function_name: str | None = Field(None, description="The function that was ultimately selected/used")
    was_helpful: bool = Field(..., description="Whether the search results were helpful")
    feedback_type: Literal["explicit", "implicit_selection", "implicit_execution"] = Field(
        "explicit",
        description="Type of feedback: explicit (user provided), implicit_selection (based on what was chosen), implicit_execution (based on successful execution)",
    )
    feedback_comment: str | None = Field(None, description="Optional user comment about the search quality")
    search_metadata: dict = Field(default_factory=dict, description="Additional metadata about the search")


class FunctionSearchFeedbackResponse(BaseModel):
    """Response schema for function search feedback."""

    id: UUID
    agent_id: UUID
    project_id: UUID
    intent: str | None
    returned_function_names: list[str]
    selected_function_name: str | None
    was_helpful: bool
    feedback_type: str
    feedback_comment: str | None
    search_metadata: dict
    created_at: datetime