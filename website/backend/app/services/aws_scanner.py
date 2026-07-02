import aioboto3
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from app.config import settings


class AwsResourceScanner:
    def __init__(self):
        self.region = settings.aws_region

    async def scan_resources(self, region: Optional[str] = None) -> List[Dict[str, Any]]:
        region = region or self.region
        session = aioboto3.Session()
        resources = []
        resources.extend(await self._scan_ec2(session, region))
        resources.extend(await self._scan_rds(session, region))
        resources.extend(await self._scan_ebs(session, region))
        resources.extend(await self._scan_eips(session, region))
        resources.extend(await self._scan_load_balancers(session, region))
        return resources

    async def _fetch_ec2_pricing(
        self, session: aioboto3.Session, region: str, instance_type: str
    ) -> Optional[float]:
        try:
            async with session.client("pricing", region_name="us-east-1") as pricing:
                region_map = {
                    "us-east-1": "US East (N. Virginia)",
                    "us-east-2": "US East (Ohio)",
                    "us-west-1": "US West (N. California)",
                    "us-west-2": "US West (Oregon)",
                    "eu-west-1": "EU (Ireland)",
                    "eu-central-1": "EU (Frankfurt)",
                    "ap-southeast-1": "Asia Pacific (Singapore)",
                    "ap-southeast-2": "Asia Pacific (Sydney)",
                    "ap-northeast-1": "Asia Pacific (Tokyo)",
                    "ap-south-1": "Asia Pacific (Mumbai)",
                }
                loc = region_map.get(region, "US East (N. Virginia)")
                products = await pricing.get_products(
                    ServiceCode="AmazonEC2",
                    Filters=[
                        {"Type": "TERM_MATCH", "Field": "instanceType", "Value": instance_type},
                        {"Type": "TERM_MATCH", "Field": "location", "Value": loc},
                        {"Type": "TERM_MATCH", "Field": "operatingSystem", "Value": "Linux"},
                        {"Type": "TERM_MATCH", "Field": "capacitystatus", "Value": "Used"},
                        {"Type": "TERM_MATCH", "Field": "tenancy", "Value": "Shared"},
                        {"Type": "TERM_MATCH", "Field": "preInstalledSw", "Value": "NA"},
                    ],
                    MaxResults=1,
                )
                if not products["PriceList"]:
                    return None
                import json as _json
                product = _json.loads(products["PriceList"][0])
                for term in product.get("terms", {}).get("OnDemand", {}).values():
                    for dimension in term.get("priceDimensions", {}).values():
                        price = float(dimension.get("pricePerUnit", {}).get("USD", 0))
                        if price > 0:
                            return price
        except Exception:
            pass
        return None

    async def _fetch_rds_pricing(
        self, session: aioboto3.Session, region: str, instance_class: str, engine: str
    ) -> Optional[float]:
        try:
            async with session.client("pricing", region_name="us-east-1") as pricing:
                region_map = {
                    "us-east-1": "US East (N. Virginia)",
                    "us-east-2": "US East (Ohio)",
                    "us-west-1": "US West (N. California)",
                    "us-west-2": "US West (Oregon)",
                    "eu-west-1": "EU (Ireland)",
                    "eu-central-1": "EU (Frankfurt)",
                }
                loc = region_map.get(region, "US East (N. Virginia)")
                engine_map = {"postgres": "PostgreSQL", "mysql": "MySQL", "mariadb": "MariaDB"}
                db_engine = engine_map.get(engine.lower(), "PostgreSQL")
                products = await pricing.get_products(
                    ServiceCode="AmazonRDS",
                    Filters=[
                        {"Type": "TERM_MATCH", "Field": "instanceType", "Value": instance_class},
                        {"Type": "TERM_MATCH", "Field": "location", "Value": loc},
                        {"Type": "TERM_MATCH", "Field": "databaseEngine", "Value": db_engine},
                        {"Type": "TERM_MATCH", "Field": "deploymentOption", "Value": "Single-AZ"},
                    ],
                    MaxResults=1,
                )
                if not products["PriceList"]:
                    return None
                import json as _json
                product = _json.loads(products["PriceList"][0])
                for term in product.get("terms", {}).get("OnDemand", {}).values():
                    for dimension in term.get("priceDimensions", {}).values():
                        price = float(dimension.get("pricePerUnit", {}).get("USD", 0))
                        if price > 0:
                            return price
        except Exception:
            pass
        return None

    async def _fetch_cpu_metrics(
        self, session: aioboto3.Session, region: str,
        resource_id: str, namespace: str = "AWS/EC2",
        dimension_name: str = "InstanceId",
        period: int = 3600,
        days: int = 14,
    ) -> Optional[Dict[str, Any]]:
        try:
            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(days=days)
            async with session.client("cloudwatch", region_name=region) as cw:
                response = await cw.get_metric_statistics(
                    Namespace=namespace,
                    MetricName="CPUUtilization",
                    Dimensions=[{"Name": dimension_name, "Value": resource_id}],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=period,
                    Statistics=["Average", "Maximum"],
                )
                datapoints = response.get("Datapoints", [])
                if not datapoints:
                    return None
                avg_values = [dp.get("Average", 0) for dp in datapoints]
                max_values = [dp.get("Maximum", 0) for dp in datapoints]
                return {
                    "avg_cpu_pct": round(sum(avg_values) / len(avg_values), 2) if avg_values else 0,
                    "max_cpu_pct": round(max(max_values), 2) if max_values else 0,
                    "datapoints": len(datapoints),
                    "period_days": days,
                }
        except Exception:
            return None

    async def _scan_ec2(self, session: aioboto3.Session, region: str) -> List[Dict[str, Any]]:
        instances = []
        pricing_cache: Dict[str, Optional[float]] = {}
        async with session.client("ec2", region_name=region) as ec2:
            paginator = ec2.get_paginator("describe_instances")
            async for page in paginator.paginate():
                for reservation in page["Reservations"]:
                    for instance in reservation["Instances"]:
                        inst_type = instance["InstanceType"]
                        if inst_type not in pricing_cache:
                            pricing_cache[inst_type] = await self._fetch_ec2_pricing(session, region, inst_type)
                        hourly_cost = pricing_cache.get(inst_type)
                        metrics = await self._fetch_cpu_metrics(session, region, instance["InstanceId"])
                        instances.append({
                            "type": "ec2",
                            "resource_id": instance["InstanceId"],
                            "name": self._get_tag(instance, "Name") or instance["InstanceId"],
                            "region": region,
                            "state": instance["State"]["Name"],
                            "instance_type": inst_type,
                            "launch_time": instance["LaunchTime"].isoformat(),
                            "tags": {t["Key"]: t["Value"] for t in instance.get("Tags", [])},
                            "specs": {
                                "vcpu": instance.get("CpuOptions", {}).get("CoreCount", 0),
                                "hourly_cost": hourly_cost,
                                "monthly_cost": round(hourly_cost * 730, 2) if hourly_cost else None,
                            },
                            "metrics": metrics,
                        })
        return instances

    async def _scan_rds(self, session: aioboto3.Session, region: str) -> List[Dict[str, Any]]:
        instances = []
        async with session.client("rds", region_name=region) as rds:
            paginator = rds.get_paginator("describe_db_instances")
            async for page in paginator.paginate():
                for db_instance in page["DBInstances"]:
                    inst_class = db_instance["DBInstanceClass"]
                    engine = db_instance["Engine"]
                    hourly_cost = await self._fetch_rds_pricing(session, region, inst_class, engine)
                    metrics = await self._fetch_cpu_metrics(
                        session, region, db_instance["DBInstanceIdentifier"],
                        namespace="AWS/RDS", dimension_name="DBInstanceIdentifier",
                    )
                    instances.append({
                        "type": "rds",
                        "resource_id": db_instance["DBInstanceIdentifier"],
                        "name": db_instance["DBInstanceIdentifier"],
                        "region": region,
                        "state": db_instance["DBInstanceStatus"],
                        "instance_type": inst_class,
                        "engine": engine,
                        "tags": {t["Key"]: t["Value"] for t in db_instance.get("TagList", [])},
                        "specs": {
                            "storage_gb": db_instance["AllocatedStorage"],
                            "multi_az": db_instance["MultiAZ"],
                            "hourly_cost": hourly_cost,
                            "monthly_cost": round(hourly_cost * 730, 2) if hourly_cost else None,
                        },
                        "metrics": metrics,
                    })
        return instances

    async def _scan_ebs(self, session: aioboto3.Session, region: str) -> List[Dict[str, Any]]:
        volumes = []
        async with session.client("ec2", region_name=region) as ec2:
            paginator = ec2.get_paginator("describe_volumes")
            async for page in paginator.paginate():
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

    async def _scan_eips(self, session: aioboto3.Session, region: str) -> List[Dict[str, Any]]:
        eips = []
        async with session.client("ec2", region_name=region) as ec2:
            response = await ec2.describe_addresses()
            for address in response["Addresses"]:
                eips.append({
                    "type": "eip",
                    "resource_id": address["AllocationId"],
                    "name": address.get("PublicIp", address["AllocationId"]),
                    "region": region,
                    "state": "associated" if address.get("AssociationId") else "unassociated",
                    "public_ip": address.get("PublicIp", ""),
                    "tags": {t["Key"]: t["Value"] for t in address.get("Tags", [])},
                    "specs": {"domain": address.get("Domain", "")},
                })
        return eips

    async def _scan_load_balancers(self, session: aioboto3.Session, region: str) -> List[Dict[str, Any]]:
        lbs = []
        async with session.client("elbv2", region_name=region) as elbv2:
            paginator = elbv2.get_paginator("describe_load_balancers")
            async for page in paginator.paginate():
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
