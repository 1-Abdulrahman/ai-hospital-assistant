"""Security module for authentication and authorization.

This module provides core security functionality including:
- Password hashing and verification using bcrypt
- JWT access token creation and validation
- Custom exception handling for token validation errors

All cryptographic operations use industry-standard libraries (passlib for passwords,
PyJWT for tokens) with secure defaults.
"""
from datetime import datetime, timedelta, timezone

from jose import ExpiredSignatureError, JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# Password context configured with bcrypt hashing algorithm.
# Bcrypt includes automatic salt generation and is resistant to brute-force attacks.
# The deprecated="auto" setting allows safe algorithm upgrades in the future.
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
    """Hash a plaintext password using bcrypt.

    Uses the configured password context with bcrypt and automatic scheme deprecation.
    The resulting hash is safe to store in a database.

    Args:
        password (str): Plaintext password to hash.

    Returns:
        str: Bcrypt hash of the password.
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Verify a plaintext password against its bcrypt hash.

    Safely compares the provided password with the stored hash without leaking
    timing information that could be exploited in brute-force attacks.

    Args:
        plain_password (str): Plaintext password to verify.
        password_hash (str): Bcrypt hash from password storage.

    Returns:
        bool: True if password matches the hash, False otherwise.
    """
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
    
    Security Considerations:
        - Tokens are signed with the configured secret key (HS256 or RS256).
        - Signature verification ensures token tampering is detected.
        - Expiration times prevent indefinite token usage if compromised.
        - Tenant information isolates user data in multi-tenant systems.
    """
    # Use UTC timezone to ensure consistent token timestamps across different server zones
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=expires_in_seconds)
    
    # Build JWT payload with standard (RFC 7519) and custom claims
    # Standard claims: sub (subject), iat (issued at), exp (expiration)
    # Custom claims: tenantId (multi-tenancy), email (user contact), role (authorization)
    payload = {
        "sub": subject,  # Standard JWT claim: user/subject identifier
        "tenantId": tenant_id,  # Custom claim: enables multi-tenant isolation
        "email": email,  # Custom claim: user email for notifications and identity
        "role": role,  # Custom claim: authorization level for access control
        "iat": int(now.timestamp()),  # Standard JWT claim: token issue time (Unix timestamp)
        "exp": int(expires_at.timestamp()),  # Standard JWT claim: token expiration time (Unix timestamp)
    }
    # Sign the payload with the configured secret key and algorithm
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
    
    Security Considerations:
        - Signature verification ensures the token hasn't been tampered with.
        - Expiration validation prevents use of outdated tokens.
        - Custom exceptions allow API layers to return appropriate HTTP status codes.
        - Exception chaining (from exc) preserves debugging information.
    
    Example:
        >>> payload = decode_access_token(token)
        >>> user_id = payload.get('sub')
    """
    try:
        # Decode and validate token signature using the same secret and algorithm used to create it.
        # The jwt.decode method performs both signature verification and expiration checking.
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_alg])
    except ExpiredSignatureError as exc:
        # Token's 'exp' claim indicates the token has passed its expiration time.
        # This is a normal, expected error during token refresh or re-authentication flows.
        raise TokenValidationError(
            message="Token has expired.",
            reason_code="TOKEN_EXPIRED",
            status_code=401,
        ) from exc
    except JWTError as exc:
        # Catches all JWT-related errors: malformed token, invalid signature, missing claims, etc.
        # Treating all JWT errors uniformly prevents information disclosure about attack vectors.
        raise TokenValidationError(
            message="Token is invalid.",
            reason_code="INVALID_TOKEN",
            status_code=401,
        ) from exc
