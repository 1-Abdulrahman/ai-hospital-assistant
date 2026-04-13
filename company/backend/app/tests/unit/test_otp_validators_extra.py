from __future__ import annotations

import pytest

from app.modules.otp.validators import (
    IdentityValidationError,
    normalize_identity_input,
    validate_national_id_and_infer_type,
)


def test_normalize_identity_input_strips_spaces_and_non_digits() -> None:
    assert normalize_identity_input("  2-1234 56788 ") == "2123456788"


def test_normalize_identity_input_rejects_empty() -> None:
    with pytest.raises(IdentityValidationError, match="digits"):
        normalize_identity_input("   ")


def test_validate_border_id_starting_with_5_is_accepted() -> None:
    normalized, identity_type = validate_national_id_and_infer_type("5123456789")
    assert normalized == "5123456789"
    assert identity_type == "border_id"