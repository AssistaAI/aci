"""
CRUD operations for OAuth1 temporary tokens.
These tokens are used to store state during the OAuth1 flow.
"""

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from aci.common.db.sql_models import OAuth1TempToken


def create_temp_token(
    db_session: Session,
    oauth_token: str,
    state_jwt: str,
    expires_in_minutes: int = 10,
) -> OAuth1TempToken:
    """
    Create a temporary token to store OAuth1 state.

    Args:
        db_session: Database session
        oauth_token: The OAuth1 request token
        state_jwt: The JWT-encoded state
        expires_in_minutes: Token expiration time in minutes

    Returns:
        The created OAuth1TempToken
    """
    temp_token = OAuth1TempToken(
        oauth_token=oauth_token,
        state_jwt=state_jwt,
        expires_at=datetime.utcnow() + timedelta(minutes=expires_in_minutes),
    )
    db_session.add(temp_token)
    return temp_token


def get_temp_token(
    db_session: Session,
    oauth_token: str,
) -> OAuth1TempToken | None:
    """
    Get a temporary token by oauth_token.

    Args:
        db_session: Database session
        oauth_token: The OAuth1 request token

    Returns:
        The OAuth1TempToken if found and not expired, None otherwise
    """
    temp_token = (
        db_session.query(OAuth1TempToken)
        .filter(
            OAuth1TempToken.oauth_token == oauth_token,
            OAuth1TempToken.expires_at > datetime.utcnow(),
        )
        .first()
    )
    return temp_token


def delete_temp_token(
    db_session: Session,
    oauth_token: str,
) -> None:
    """
    Delete a temporary token.

    Args:
        db_session: Database session
        oauth_token: The OAuth1 request token
    """
    db_session.query(OAuth1TempToken).filter(OAuth1TempToken.oauth_token == oauth_token).delete()


def cleanup_expired_tokens(
    db_session: Session,
) -> int:
    """
    Clean up expired tokens.

    Args:
        db_session: Database session

    Returns:
        Number of deleted tokens
    """
    result = (
        db_session.query(OAuth1TempToken)
        .filter(OAuth1TempToken.expires_at <= datetime.utcnow())
        .delete()
    )
    return result
