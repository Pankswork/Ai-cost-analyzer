import json
import os
from typing import Set

SCANNER_METHODS = {
    "_scan_ec2": {"aws_instance"},
    "_scan_rds": {"aws_db_instance"},
    "_scan_ebs": {"aws_ebs_volume", "aws_volume_attachment"},
    "_scan_eips": {"aws_eip"},
    "_scan_load_balancers": {"aws_lb", "aws_alb", "aws_alb", "aws_lb_target_group"},
    "_scan_nat_gateways": {"aws_nat_gateway"},
    "_scan_eks_clusters": {"aws_eks_cluster"},
    "_scan_ebs_snapshots": {"aws_ebs_snapshot", "aws_ebs_snapshot_copy"},
    "_scan_s3_buckets": {"aws_s3_bucket"},
    "_scan_cloudwatch_log_groups": {"aws_cloudwatch_log_group"},
}


def load_terraform_resource_types() -> Set[str]:
    json_path = os.path.join(os.path.dirname(__file__), "terraform_resources.json")
    if not os.path.exists(json_path):
        return set()
    with open(json_path) as f:
        data = json.load(f)
    return set(data.get("aws_resource_types", []))


def get_active_scanner_methods() -> Set[str]:
    terraform_types = load_terraform_resource_types()
    if not terraform_types:
        return set()
    active: Set[str] = set()
    for method, tf_types in SCANNER_METHODS.items():
        if tf_types & terraform_types:
            active.add(method)
    return active
