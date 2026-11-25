from copy import deepcopy
from uuid import uuid4

import pytest

from app.application.video_library_metadata import validate_entries


def sample():
    return {"artifact_id": str(uuid4()), "filename": "b1v1-example.mp4",
            "title": "Example", "source_file": "source.txt", "source_original": "Original",
            "tiktok_text": "Full description", "telegram_caption": "Short description",
            "catalog_caption_original": "Original upload", "editorial_notes": []}


def test_valid_video_entry():
    validate_entries([sample()])


def test_duplicate_identity_is_rejected():
    entry = sample()
    with pytest.raises(ValueError, match="Duplicate"):
        validate_entries([entry, deepcopy(entry)])


@pytest.mark.parametrize("field,value", [("filename", "../escape.mp4"), ("source_original", ""),
    ("telegram_caption", "x" * 1025), ("title", "x" * 501), ("editorial_notes", "not a list")])
def test_invalid_fields(field, value):
    entry = sample()
    entry[field] = value
    with pytest.raises(ValueError):
        validate_entries([entry])


@pytest.mark.parametrize("value", ["raw", [None], ["x" * 10001], ["x"] * 101])
def test_invalid_curated_notes(value):
    entry = sample()
    entry["review_notes"] = value
    with pytest.raises(ValueError, match="Curated"):
        validate_entries([entry])
