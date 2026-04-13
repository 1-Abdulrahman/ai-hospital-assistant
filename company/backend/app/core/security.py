from datetime import datetime, timedelta, timezone

from jose import ExpiredSignatureError, JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class TokenValidationError(Exception):
    """
    Custom exception raised when JWT token validation fails.

    This exception is used to handle various token validation scenarios including
    expired tokens, invalid signatures, malformed tokens, and missing credentials.

    Attributes:
        message (str): Human-readable error message describing the validation failure.
        reason_code (str): Machine-readable code identifying the specific reason for validation failure.
            Common codes include: 'token_expired', 'invalid_signature', 'malformed_token', 'missing_token'.
        status_code (int): HTTP status code to return to the client. Defaults to 401 (Unauthorized).

    Example:
        >>> raise TokenValidationError(
        ...     message="Token has expired",
        ...     reason_code="token_expired",
        ...     status_code=401
        ... )
    """

    def __init__(self, *, message: str, reason_code: str, status_code: int = 401) -> None:
        super().__init__(message)
        self.message = message
        self.reason_code = reason_code
        self.status_code = status_code


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)

    
def create_access_token(
    *,
    subject: str,
    tenant_id: str,
    email: str,
    role: str,
    expires_in_seconds: int = 3600,
) -> str:
    """
    Create a JWT access token with user and tenant information.

    Args:
        subject (str): The subject identifier (usually user ID) to include in the token.
        tenant_id (str): The tenant ID to associate with the token.
        email (str): The user's email address to include in the token.
        role (str): The user's role for authorization purposes.
        expires_in_seconds (int, optional): Token expiration time in seconds. Defaults to 3600 (1 hour).

    Returns:
        str: An encoded JWT access token signed with the configured secret and algorithm.

    Raises:
        Exception: If JWT encoding fails due to invalid configuration or payload.
    """
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=expires_in_seconds)
    payload = {
        "sub": subject,
        "tenantId": tenant_id,
        "email": email,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_alg)


def decode_access_token(token: str) -> dict:
    """
    Decode and validate a JWT access token.
    
    Decodes a JWT token using the configured secret key and algorithm.
    Validates the token's signature and expiration time.
    
    Args:
        token (str): The JWT access token to decode.
    
    Returns:
        dict: The decoded token payload containing claims and user information.
    
    Raises:
        TokenValidationError: If the token has expired (status_code: 401, 
            reason_code: 'TOKEN_EXPIRED').
        TokenValidationError: If the token is invalid or signature verification 
            fails (status_code: 401, reason_code: 'INVALID_TOKEN').
    
    Example:
        >>> payload = decode_access_token(token)
        >>> user_id = payload.get('sub')
    """
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_alg])
    except ExpiredSignatureError as exc:
        raise TokenValidationError(
            message="Token has expired.",
            reason_code="TOKEN_EXPIRED",
            status_code=401,
        ) from exc
    except JWTError as exc:
        raise TokenValidationError(
            message="Token is invalid.",
            reason_code="INVALID_TOKEN",
            status_code=401,
        ) from exc
