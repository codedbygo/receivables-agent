"""HACK-003 F8: the collection-rate formula the CFO page states."""

from app.services.executive import collection_rate


def test_collection_rate_is_collected_over_collected_plus_overdue() -> None:
    assert collection_rate(30_000_000, 45_000_000) == 40
    assert collection_rate(1, 0) == 100


def test_collection_rate_is_none_with_nothing_to_measure() -> None:
    assert collection_rate(0, 0) is None
