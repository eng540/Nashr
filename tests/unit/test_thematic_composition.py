from uuid import uuid4

import pytest

from app.application.thematic_composition import validate_thematic_selection


def test_thematic_selection_requires_two_or_more_units():
    with pytest.raises(ValueError, match="at least two"):
        validate_thematic_selection("الصبر", [uuid4()])


def test_thematic_selection_rejects_duplicate_units():
    unit_id = uuid4()
    with pytest.raises(ValueError, match="duplicates"):
        validate_thematic_selection("الصبر", [unit_id, unit_id])


def test_thematic_selection_requires_theme():
    with pytest.raises(ValueError, match="Theme"):
        validate_thematic_selection("  ", [uuid4(), uuid4()])


def test_thematic_selection_accepts_explicit_multi_book_selection():
    validate_thematic_selection("الصبر عند العرب", [uuid4(), uuid4(), uuid4()])



def test_thematic_selection_preserves_user_supplied_order_contract():
    first, second, third = uuid4(), uuid4(), uuid4()
    validate_thematic_selection("ثيمة", [third, first, second])
