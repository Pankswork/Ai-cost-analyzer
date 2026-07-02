#!/usr/bin/env python3
"""Parse Terraform .tf files in the repo to discover AWS resource types.

Outputs terraform_resources.json into the destination directory so the
backend scanner knows which resource types to scan.
"""

import json
import os
import re
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
TERRAFORM_DIR = os.path.join(REPO_ROOT, "terraform")
OUTPUT_DIR = os.path.join(REPO_ROOT, "website", "backend", "app", "services")


def discover_aws_resource_types(terraform_dir: str) -> list[str]:
    resource_types: set[str] = set()
    pattern = re.compile(r'resource\s+"(aws_\w+)"\s+"')
    for root, _dirs, files in os.walk(terraform_dir):
        for f in files:
            if not f.endswith(".tf"):
                continue
            path = os.path.join(root, f)
            try:
                with open(path) as fh:
                    content = fh.read()
                resource_types.update(pattern.findall(content))
            except Exception:
                pass
    return sorted(resource_types)


def main():
    tf_dir = sys.argv[1] if len(sys.argv) > 1 else TERRAFORM_DIR
    out_dir = sys.argv[2] if len(sys.argv) > 2 else OUTPUT_DIR

    resource_types = discover_aws_resource_types(tf_dir)
    os.makedirs(out_dir, exist_ok=True)
    output_path = os.path.join(out_dir, "terraform_resources.json")
    with open(output_path, "w") as f:
        json.dump({"aws_resource_types": resource_types}, f, indent=2)
    print(f"Discovered {len(resource_types)} AWS resource types: {resource_types}")
    print(f"Written to {output_path}")


if __name__ == "__main__":
    main()
