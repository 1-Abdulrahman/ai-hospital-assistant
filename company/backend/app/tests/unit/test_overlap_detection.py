from __future__ import annotations

from datetime import UTC, datetime

from app.modules.scheduling.service import is_overlap


def test_overlap_detection_matches_frozen_rule() -> None:
    assert is_overlap(
        new_start=datetime(2026, 4, 8, 9, 0, tzinfo=UTC),
        new_end=datetime(2026, 4, 8, 9, 30, tzinfo=UTC),
        existing_start=datetime(2026, 4, 8, 9, 15, tzinfo=UTC),
        existing_end=datetime(2026, 4, 8, 9, 45, tzinfo=UTC),
    ) is True


def test_overlap_detection_allows_touching_boundaries() -> None:
    assert is_overlap(
        new_start=datetime(2026, 4, 8, 9, 0, tzinfo=UTC),
        new_end=datetime(2026, 4, 8, 9, 30, tzinfo=UTC),
        existing_start=datetime(2026, 4, 8, 9, 30, tzinfo=UTC),
        existing_end=datetime(2026, 4, 8, 10, 0, tzinfo=UTC),
    ) is False