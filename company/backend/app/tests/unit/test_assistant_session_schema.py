from app.db.models import AssistantSession


def test_assistant_session_orm_includes_expected_columns() -> None:
    expected = {
        "id",
        "tenant_id",
        "client_session_id",
        "current_state",
        "flow_mode",
        "selected_specialty_id",
        "selected_doctor_id",
        "selected_slot_id",
        "selected_slot_label",
        "selected_slot_start_utc",
        "selected_date",
        "last_input_summary",
        "renewal_item_id",
        "renewal_item_label",
        "renewal_patient_key_hash",
        "renewal_patient_ref",
        "created_at_utc",
        "updated_at_utc",
    }

    actual = set(AssistantSession.__table__.columns.keys())
    assert expected <= actual


def test_assistant_session_unique_constraint_name_is_stable() -> None:
    constraint_names = {
        constraint.name
        for constraint in AssistantSession.__table__.constraints
        if getattr(constraint, "name", None)
    }
    assert "uq_assistant_session_tenant_client" in constraint_names