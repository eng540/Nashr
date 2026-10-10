import pytest

from app.domain.policies import ProductionPolicyDefinition


def test_policy_validation_enforces_content_rules():
    definition = ProductionPolicyDefinition(min_content_chars=4, max_content_chars=40,
        required_terms=("source",), forbidden_terms=("fabricated",), allow_urls=False)
    assert definition.validate_content("tiny") == ["Content is missing required policy term: source."]
    assert definition.validate_content("source fabricated") == ["Content contains forbidden policy term: fabricated."]
    assert definition.validate_content("source https://example.com")[-1] == "Content contains a URL disallowed by the production policy."


def test_policy_definition_round_trips_and_normalizes_terms():
    definition = ProductionPolicyDefinition.from_dict({
        "min_content_chars": 1, "max_content_chars": 100,
        "required_terms": [" source "], "forbidden_terms": ["fabricated"], "allow_urls": False,
    })
    assert definition.to_dict() == {
        "min_content_chars": 1, "max_content_chars": 100,
        "required_terms": ["source"], "forbidden_terms": ["fabricated"], "allow_urls": False,
    }


@pytest.mark.parametrize("value", [
    {"min_content_chars": True, "max_content_chars": 100, "required_terms": [], "forbidden_terms": [], "allow_urls": True},
    {"min_content_chars": 101, "max_content_chars": 100, "required_terms": [], "forbidden_terms": [], "allow_urls": True},
    {"min_content_chars": 1, "max_content_chars": 100, "required_terms": ["same"], "forbidden_terms": ["SAME"], "allow_urls": True},
    {"min_content_chars": 1, "max_content_chars": 100, "required_terms": [], "forbidden_terms": [], "allow_urls": "yes"},
])
def test_policy_definition_rejects_invalid_rules(value):
    with pytest.raises(ValueError):
        ProductionPolicyDefinition.from_dict(value)
