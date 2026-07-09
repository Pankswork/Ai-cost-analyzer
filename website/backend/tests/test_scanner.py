import pytest
from app.services.aws_scanner import AwsResourceScanner


@pytest.fixture
def scanner():
    return AwsResourceScanner()


def test_get_tag_returns_value(scanner):
    resource = {"Tags": [{"Key": "Name", "Value": "my-instance"}]}
    assert scanner._get_tag(resource, "Name") == "my-instance"


def test_get_tag_returns_none_when_missing(scanner):
    resource = {"Tags": [{"Key": "Environment", "Value": "prod"}]}
    assert scanner._get_tag(resource, "Name") is None


def test_get_tag_returns_none_when_no_tags(scanner):
    resource = {}
    assert scanner._get_tag(resource, "Name") is None


def test_get_tag_returns_none_when_tags_empty(scanner):
    resource = {"Tags": []}
    assert scanner._get_tag(resource, "Name") is None


def test_get_tag_case_sensitive(scanner):
    resource = {"Tags": [{"Key": "Name", "Value": "correct"}]}
    assert scanner._get_tag(resource, "name") is None
    assert scanner._get_tag(resource, "Name") == "correct"


def test_get_tag_returns_first_match_for_duplicate_keys(scanner):
    resource = {
        "Tags": [
            {"Key": "Name", "Value": "first"},
            {"Key": "Name", "Value": "second"},
        ]
    }
    assert scanner._get_tag(resource, "Name") == "first"


def test_scanner_init_sets_region(scanner):
    assert scanner.region is not None
    assert isinstance(scanner.region, str)


def test_all_scanner_methods_defined():
    from app.services.aws_scanner import ALL_SCANNER_METHODS
    assert len(ALL_SCANNER_METHODS) > 0
    for method_name in ALL_SCANNER_METHODS:
        assert hasattr(AwsResourceScanner, method_name)
        assert callable(getattr(AwsResourceScanner, method_name))
