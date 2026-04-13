from typing import Literal

IdentityType = Literal["saudi_national_id", "iqama", "border_id"]


class IdentityValidationError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def normalize_identity_input(raw_value: str) -> str:
    if raw_value is None:
        raise IdentityValidationError("Identity number is required.")

    cleaned = "".join(ch for ch in str(raw_value).strip() if ch.isdigit())

    if not cleaned:
        raise IdentityValidationError("Identity number must contain digits.")

    return cleaned


def infer_identity_type(normalized: str) -> IdentityType:
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
    """
    Saudi national ID / iqama checksum validation.
    Used here for saudi_national_id and iqama only.
    """
    if len(value) != 10 or not value.isdigit():
        return False

    total = 0
    for index, char in enumerate(value[:9]):
        digit = int(char)

        if index % 2 == 0:
            digit *= 2

        total += (digit // 10) + (digit % 10)

    expected_check_digit = (10 - (total % 10)) % 10
    return expected_check_digit == int(value[-1])


def validate_national_id_and_infer_type(raw_value: str) -> tuple[str, IdentityType]:
    normalized = normalize_identity_input(raw_value)
    identity_type = infer_identity_type(normalized)

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