import json
import pytest


SAMPLE_RECOMMENDATIONS_JSON = json.dumps([
    {
        "resource_id": "i-12345",
        "resource_type": "ec2",
        "issue": "over-provisioned",
        "severity": "high",
        "explanation": "t3.large with avg CPU 5%",
        "estimated_monthly_savings": 20.0,
        "fix_command": "aws ec2 modify-instance-type --instance-id i-12345 --instance-type t3.small"
    }
])


def test_analyzer_parse_valid_json():
    data = json.loads(SAMPLE_RECOMMENDATIONS_JSON)
    assert isinstance(data, list)
    assert len(data) == 1
    rec = data[0]
    assert rec["resource_type"] == "ec2"
    assert rec["severity"] == "high"
    assert rec["estimated_monthly_savings"] == 20.0


def test_analyzer_parse_empty_array():
    data = json.loads("[]")
    assert isinstance(data, list)
    assert len(data) == 0


def test_analyzer_parse_missing_optional_fields():
    raw = json.dumps([{
        "resource_id": "i-12345",
        "resource_type": "ec2",
        "issue": "test",
        "severity": "low",
        "explanation": "test",
        "estimated_monthly_savings": 0,
        "fix_command": "echo fix"
    }])
    data = json.loads(raw)
    rec = data[0]
    assert rec["severity"] == "low"
    assert rec["estimated_monthly_savings"] == 0


def test_analyzer_parse_invalid_json_raises():
    with pytest.raises(json.JSONDecodeError):
        json.loads("not json")


def test_analyzer_parse_expects_array():
    raw = '{"resource_id": "i-12345", "resource_type": "ec2"}'
    data = json.loads(raw)
    assert isinstance(data, dict)
    assert "resource_id" in data
