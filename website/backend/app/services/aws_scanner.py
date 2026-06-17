import boto3
from typing import List, Dict, Any, Optional
from app.config import settings


class AwsResourceScanner:
    def __init__(self):
        self.session = boto3.Session(region_name=settings.aws_region)

    async def scan_resources(self, region: Optional[str] = None) -> List[Dict[str, Any]]:
        region = region or settings.aws_region
        resources = []
        resources.extend(await self._scan_ec2(region))
        resources.extend(await self._scan_rds(region))
        resources.extend(await self._scan_ebs(region))
        resources.extend(await self._scan_eips(region))
        resources.extend(await self._scan_load_balancers(region))
        return resources

    async def _scan_ec2(self, region: str) -> List[Dict[str, Any]]:
        ec2 = self.session.client("ec2", region_name=region)
        instances = []
        paginator = ec2.get_paginator("describe_instances")
        for page in paginator.paginate():
            for reservation in page["Reservations"]:
                for instance in reservation["Instances"]:
                    instances.append({
                        "type": "ec2",
                        "resource_id": instance["InstanceId"],
                        "name": self._get_tag(instance, "Name") or instance["InstanceId"],
                        "region": region,
                        "state": instance["State"]["Name"],
                        "instance_type": instance["InstanceType"],
                        "launch_time": instance["LaunchTime"].isoformat(),
                        "tags": {t["Key"]: t["Value"] for t in instance.get("Tags", [])},
                        "specs": {
                            "vcpu": instance.get("CpuOptions", {}).get("CoreCount", 0),
                        },
                    })
        return instances

    async def _scan_rds(self, region: str) -> List[Dict[str, Any]]:
        rds = self.session.client("rds", region_name=region)
        instances = []
        paginator = rds.get_paginator("describe_db_instances")
        for page in paginator.paginate():
            for db_instance in page["DBInstances"]:
                instances.append({
                    "type": "rds",
                    "resource_id": db_instance["DBInstanceIdentifier"],
                    "name": db_instance["DBInstanceIdentifier"],
                    "region": region,
                    "state": db_instance["DBInstanceStatus"],
                    "instance_type": db_instance["DBInstanceClass"],
                    "engine": db_instance["Engine"],
                    "tags": {t["Key"]: t["Value"] for t in db_instance.get("TagList", [])},
                    "specs": {
                        "storage_gb": db_instance["AllocatedStorage"],
                        "multi_az": db_instance["MultiAZ"],
                    },
                })
        return instances

    async def _scan_ebs(self, region: str) -> List[Dict[str, Any]]:
        ec2 = self.session.client("ec2", region_name=region)
        volumes = []
        paginator = ec2.get_paginator("describe_volumes")
        for page in paginator.paginate():
            for vol in page["Volumes"]:
                volumes.append({
                    "type": "ebs",
                    "resource_id": vol["VolumeId"],
                    "name": vol["VolumeId"],
                    "region": region,
                    "state": vol["State"],
                    "volume_type": vol["VolumeType"],
                    "size_gb": vol["Size"],
                    "attached": len(vol.get("Attachments", [])) > 0,
                    "tags": {t["Key"]: t["Value"] for t in vol.get("Tags", [])},
                    "specs": {"iops": vol.get("Iops", 0)},
                })
        return volumes

    async def _scan_eips(self, region: str) -> List[Dict[str, Any]]:
        ec2 = self.session.client("ec2", region_name=region)
        eips = []
        response = ec2.describe_addresses()
        for address in response["Addresses"]:
            eips.append({
                "type": "eip",
                "resource_id": address["AllocationId"],
                "name": address.get("PublicIp", address["AllocationId"]),
                "region": region,
                "state": "associated" if "InstanceId" in address else "unassociated",
                "public_ip": address.get("PublicIp", ""),
                "tags": {t["Key"]: t["Value"] for t in address.get("Tags", [])},
                "specs": {"domain": address.get("Domain", "")},
            })
        return eips

    async def _scan_load_balancers(self, region: str) -> List[Dict[str, Any]]:
        elbv2 = self.session.client("elbv2", region_name=region)
        lbs = []
        paginator = elbv2.get_paginator("describe_load_balancers")
        for page in paginator.paginate():
            for lb in page["LoadBalancers"]:
                lbs.append({
                    "type": "lb",
                    "resource_id": lb["LoadBalancerArn"],
                    "name": lb["LoadBalancerName"],
                    "region": region,
                    "state": lb["State"]["Code"],
                    "scheme": lb["Scheme"],
                    "tags": {},
                    "specs": {"type": lb["Type"]},
                })
        return lbs

    def _get_tag(self, resource: Dict, key: str) -> Optional[str]:
        for tag in resource.get("Tags", []):
            if tag["Key"] == key:
                return tag["Value"]
        return None
