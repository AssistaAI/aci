"""
CRUD operations for function search feedback.
"""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from aci.common.db.sql_models import FunctionSearchFeedback
from aci.common.schemas.feedback import FunctionSearchFeedbackCreate


def create_search_feedback(
    db_session: Session,
    agent_id: UUID,
    project_id: UUID,
    feedback_data: FunctionSearchFeedbackCreate,
) -> FunctionSearchFeedback:
    """
    Create a new function search feedback entry.

    Args:
        db_session: Database session
        agent_id: ID of the agent performing the search
        project_id: ID of the project
        feedback_data: Feedback data to store

    Returns:
        Created FunctionSearchFeedback instance
    """
    feedback = FunctionSearchFeedback(
        agent_id=agent_id,
        project_id=project_id,
        intent=feedback_data.intent,
        returned_function_names=feedback_data.returned_function_names,
        selected_function_name=feedback_data.selected_function_name,
        was_helpful=feedback_data.was_helpful,
        feedback_type=feedback_data.feedback_type,
        feedback_comment=feedback_data.feedback_comment,
        search_metadata=feedback_data.search_metadata,
    )

    db_session.add(feedback)
    db_session.flush()

    # Created search feedback

    return feedback


def get_feedback_by_project(
    db_session: Session,
    project_id: UUID,
    limit: int = 100,
    offset: int = 0,
) -> list[FunctionSearchFeedback]:
    """
    Get feedback entries for a specific project.

    Args:
        db_session: Database session
        project_id: ID of the project
        limit: Maximum number of results
        offset: Pagination offset

    Returns:
        List of FunctionSearchFeedback instances
    """
    statement = (
        select(FunctionSearchFeedback)
        .filter(FunctionSearchFeedback.project_id == project_id)
        .order_by(FunctionSearchFeedback.created_at.desc())
        .limit(limit)
        .offset(offset)
    )

    return list(db_session.execute(statement).scalars().all())


def get_feedback_by_agent(
    db_session: Session,
    agent_id: UUID,
    limit: int = 100,
    offset: int = 0,
) -> list[FunctionSearchFeedback]:
    """
    Get feedback entries for a specific agent.

    Args:
        db_session: Database session
        agent_id: ID of the agent
        limit: Maximum number of results
        offset: Pagination offset

    Returns:
        List of FunctionSearchFeedback instances
    """
    statement = (
        select(FunctionSearchFeedback)
        .filter(FunctionSearchFeedback.agent_id == agent_id)
        .order_by(FunctionSearchFeedback.created_at.desc())
        .limit(limit)
        .offset(offset)
    )

    return list(db_session.execute(statement).scalars().all())


def get_unhelpful_searches(
    db_session: Session,
    project_id: UUID | None = None,
    limit: int = 50,
) -> list[FunctionSearchFeedback]:
    """
    Get search feedback where results were not helpful.
    Useful for identifying areas where search quality needs improvement.

    Args:
        db_session: Database session
        project_id: Optional project ID filter
        limit: Maximum number of results

    Returns:
        List of unhelpful FunctionSearchFeedback instances
    """
    statement = select(FunctionSearchFeedback).filter(FunctionSearchFeedback.was_helpful == False)

    if project_id:
        statement = statement.filter(FunctionSearchFeedback.project_id == project_id)

    statement = statement.order_by(FunctionSearchFeedback.created_at.desc()).limit(limit)

    return list(db_session.execute(statement).scalars().all())