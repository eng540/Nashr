import pytest

from app.domain.output_contracts import OutputContractDefinition


def valid_definition(**overrides) -> dict[str, object]:
    return {
        "artifact_kind": "TEXT",
        "mime_type": "text/plain",
        "content_mode": "INLINE",
        "required_metadata_fields": (),
        "max_content_chars": 1000,
        **overrides,
    }


@pytest.mark.parametrize(
    "metadata_fields",
    [
        ("language", "language"),
        ("",),
        ({"unexpected": "mapping"},),
        (1,),
    ],
)
def test_output_contract_rejects_invalid_metadata_fields(metadata_fields):
    with pytest.raises(ValueError):
        OutputContractDefinition(**valid_definition(required_metadata_fields=metadata_fields))
