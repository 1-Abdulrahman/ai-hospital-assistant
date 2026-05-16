from typing import Literal

IdentityType = Literal["saudi_national_id", "iqama", "border_id"]
"""Valid Saudi identity document types.

Values:
    - 'saudi_national_id': Saudi Arabia National ID (starts with 1)
    - 'iqama': Resident ID for foreign nationals (starts with 2)
    - 'border_id': Border region resident ID (starts with 3 or 5)
"""


class IdentityValidationError(Exception):
    """Raised when an identity number fails local validation.

    This exception encapsulates all identity validation errors including format
    issues, checksum validation failures, and unsupported identity types.

    Attributes:
        message (str): Human-readable error message describing the validation failure.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def normalize_identity_input(raw_value: str) -> str:
    """Normalize and validate identity input by extracting digits only.

    Removes all non-digit characters and ensures the result contains at least one digit.
    This handles user input that may include spaces, dashes, or formatting characters.

    Args:
        raw_value (str): Raw user input (may contain formatting).

    Returns:
        str: String containing only digits.

    Raises:
        IdentityValidationError: If input is None, empty, or contains no digits.
    """

    if raw_value is None:
        raise IdentityValidationError("Identity number is required.")

    cleaned = "".join(ch for ch in str(raw_value).strip() if ch.isdigit())

    if not cleaned:
        raise IdentityValidationError("Identity number must contain digits.")

    return cleaned


def infer_identity_type(normalized: str) -> IdentityType:
    """Infer the identity type from the leading digit of a normalized 10-digit number.

    Saudi Arabia uses different ID formats for different population groups:
    - 1: Saudi National ID
    - 2: Iqama (Resident ID for expatriates)
    - 3 or 5: Border ID (for border region residents)

    Args:
        normalized (str): 10-digit identity number.

    Returns:
        IdentityType: One of 'saudi_national_id', 'iqama', or 'border_id'.

    Raises:
        IdentityValidationError: If length is not exactly 10 digits or first digit is invalid.
    """

    if len(normalized) != 10 or not normalized.isdigit():
        raise IdentityValidationError("Identity number must be exactly 10 digits.")

    first_digit = normalized[0]

    if first_digit == "1":
        return "saudi_national_id"

    if first_digit == "2":
        return "iqama"

    if first_digit in {"3", "5"}:
        return "border_id"

    raise IdentityValidationError(
        "Identity number must start with 1, 2, 3, or 5."
    )


def saudi_id_checksum_is_valid(value: str) -> bool:
    """Validate the checksum digit of a Saudi national ID or Iqama using the Luhn-like algorithm.

    Saudi ID and Iqama formats both use a 10-digit structure where the last digit is a
    checksum calculated from the first 9 digits. This function implements the official
    validation algorithm:
    - Double every digit at even positions (0-indexed)
    - Sum all digits (both original and results of doubling)
    - Calculate expected check digit as (10 - (sum % 10)) % 10
    - Verify the check digit matches the last digit

    Args:
        value (str): 10-digit identity number to validate.

    Returns:
        bool: True if checksum is valid, False otherwise.
    """
    if len(value) != 10 or not value.isdigit():
        return False

    total = 0
    for index, char in enumerate(value[:9]):
        digit = int(char)

        # The alternating doubling pattern is part of the local checksum rule.
        if index % 2 == 0:
            digit *= 2

        total += (digit // 10) + (digit % 10)

    expected_check_digit = (10 - (total % 10)) % 10
    return expected_check_digit == int(value[-1])


def validate_national_id_and_infer_type(raw_value: str) -> tuple[str, IdentityType]:
    """Normalize, validate, and infer the type of a Saudi identity number.

    This is the main entry point for identity validation. It orchestrates the full
    validation pipeline:
    1. Normalize the input (extract digits only)
    2. Infer the identity type from the leading digit
    3. Apply type-specific validation rules (checksum for national IDs and Iqama)

    Args:
        raw_value (str): User input identity number (may include formatting).

    Returns:
        tuple[str, IdentityType]: (normalized_value, identity_type)

    Raises:
        IdentityValidationError: If any validation step fails (format, type, or checksum).
    """

    normalized = normalize_identity_input(raw_value)
    identity_type = infer_identity_type(normalized)

    # Apply the checksum only to the formats that use the Saudi ID algorithm.
    if identity_type == "saudi_national_id":
        if not saudi_id_checksum_is_valid(normalized):
            raise IdentityValidationError("Saudi national ID checksum is invalid.")

    elif identity_type == "iqama":
        if not saudi_id_checksum_is_valid(normalized):
            raise IdentityValidationError("Iqama checksum is invalid.")

    elif identity_type == "border_id":
        # NHIC format rule only for local validation in this MVP.
        pass

    return normalized, identity_type