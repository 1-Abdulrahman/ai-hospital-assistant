import pytest

from app.modules.otp.validators import (
    IdentityValidationError,
    infer_identity_type,
    saudi_id_checksum_is_valid,
    validate_national_id_and_infer_type,
)


VALID_SAUDI_NATIONAL_ID = "1123456780"
VALID_IQAMA = "2123456788"
VALID_BORDER_ID_3 = "3123456789"
VALID_BORDER_ID_5 = "5123456789"


def test_infer_identity_type_saudi_national_id() -> None:
    assert infer_identity_type(VALID_SAUDI_NATIONAL_ID) == "saudi_national_id"


def test_infer_identity_type_iqama() -> None:
    assert infer_identity_type(VALID_IQAMA) == "iqama"


def test_infer_identity_type_border_id_starting_with_3() -> None:
    assert infer_identity_type(VALID_BORDER_ID_3) == "border_id"


def test_infer_identity_type_border_id_starting_with_5() -> None:
    assert infer_identity_type(VALID_BORDER_ID_5) == "border_id"


def test_checksum_accepts_valid_saudi_national_id() -> None:
    assert saudi_id_checksum_is_valid(VALID_SAUDI_NATIONAL_ID) is True


def test_checksum_accepts_valid_iqama() -> None:
    assert saudi_id_checksum_is_valid(VALID_IQAMA) is True


def test_validate_accepts_valid_saudi_national_id() -> None:
    normalized, identity_type = validate_national_id_and_infer_type(VALID_SAUDI_NATIONAL_ID)
    assert normalized == VALID_SAUDI_NATIONAL_ID
    assert identity_type == "saudi_national_id"


def test_validate_accepts_valid_iqama() -> None:
    normalized, identity_type = validate_national_id_and_infer_type(VALID_IQAMA)
    assert normalized == VALID_IQAMA
    assert identity_type == "iqama"


def test_validate_accepts_valid_border_id() -> None:
    normalized, identity_type = validate_national_id_and_infer_type(VALID_BORDER_ID_3)
    assert normalized == VALID_BORDER_ID_3
    assert identity_type == "border_id"


def test_validate_rejects_bad_prefix() -> None:
    with pytest.raises(IdentityValidationError, match="start with 1, 2, 3, or 5"):
        validate_national_id_and_infer_type("4123456789")


def test_validate_rejects_bad_checksum_for_iqama() -> None:
    with pytest.raises(IdentityValidationError, match="checksum"):
        validate_national_id_and_infer_type("2123456789")


def test_validate_rejects_wrong_length() -> None:
    with pytest.raises(IdentityValidationError, match="exactly 10 digits"):
        validate_national_id_and_infer_type("312345678")