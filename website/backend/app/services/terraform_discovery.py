import json
import os
from typing import Dict, List, Optional, Set

SCANNER_TO_TERRAFORM: Dict[str, Set[str]] = {
    "_scan_ec2": {"aws_instance"},
    "_scan_rds": {"aws_db_instance"},
    "_scan_ebs": {"aws_ebs_volume", "aws_volume_attachment"},
    "_scan_eips": {"aws_eip"},
    "_scan_load_balancers": {"aws_lb", "aws_alb", "aws_lb_target_group"},
    "_scan_nat_gateways": {"aws_nat_gateway"},
    "_scan_eks_clusters": {"aws_eks_cluster"},
    "_scan_ebs_snapshots": {"aws_ebs_snapshot", "aws_ebs_snapshot_copy"},
    "_scan_s3_buckets": {"aws_s3_bucket"},
    "_scan_cloudwatch_log_groups": {"aws_cloudwatch_log_group"},
}


def _load_terraform_types() -> Set[str]:
    json_path = os.path.join(os.path.dirname(__file__), "terraform_resources.json")
    if not os.path.exists(json_path):
        return set()
    with open(json_path) as f:
        data = json.load(f)
    return set(data.get("aws_resource_types", []))


_terraform_types_cache: Optional[Set[str]] = None


def _get_terraform_types() -> Set[str]:
    global _terraform_types_cache
    if _terraform_types_cache is None:
        _terraform_types_cache = _load_terraform_types()
    return _terraform_types_cache


def is_terraform_managed(method_name: str) -> bool:
    tf_types = _get_terraform_types()
    if not tf_types:
        return False
    mapped = SCANNER_TO_TERRAFORM.get(method_name, set())
    return bool(mapped & tf_types)


def get_terraform_resource_types(method_name: str) -> List[str]:
    return sorted(SCANNER_TO_TERRAFORM.get(method_name, set()))
