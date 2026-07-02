import logging
import aioboto3
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from app.config import settings
from app.services.terraform_discovery import (
    is_terraform_managed,
    get_terraform_resource_types,
)

logger = logging.getLogger(__name__)

ALL_SCANNER_METHODS = [
    "_scan_ec2",
    "_scan_rds",
    "_scan_ebs",
    "_scan_eips",
    "_scan_load_balancers",
    "_scan_nat_gateways",
    "_scan_eks_clusters",
    "_scan_ebs_snapshots",
    "_scan_s3_buckets",
    "_scan_cloudwatch_log_groups",
]


class AwsResourceScanner:
    def __init__(self):
        self.region = settings.aws_region

    async def scan_resources(self, region: Optional[str] = None) -> List[Dict[str, Any]]:
        region = region or self.region
        session = aioboto3.Session()
        resources = []
        for method_name in ALL_SCANNER_METHODS:
            method = getattr(self, method_name)
            try:
                scanned = await method(session, region)
            except Exception as e:
                logger.warning("Scanner %s failed: %s", method_name, e)
                continue
            terraform_managed = is_terraform_managed(method_name)
            tf_resource_types = get_terraform_resource_types(method_name)
            for r in scanned:
                r["terraform_managed"] = terraform_managed
                r["terraform_resource_types"] = tf_resource_types
            resources.extend(scanned)
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

    async def _fetch_s3_storage_metrics(
        self, session: aioboto3.Session, region: str, bucket_name: str
    ) -> Optional[Dict[str, Any]]:
        try:
            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(days=2)
            async with session.client("cloudwatch", region_name=region) as cw:
                response = await cw.get_metric_statistics(
                    Namespace="AWS/S3",
                    MetricName="BucketSizeBytes",
                    Dimensions=[
                        {"Name": "BucketName", "Value": bucket_name},
                        {"Name": "StorageType", "Value": "StandardStorage"},
                    ],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=86400,
                    Statistics=["Average"],
                )
                datapoints = response.get("Datapoints", [])
                if not datapoints:
                    return None
                sorted_dps = sorted(datapoints, key=lambda x: x["Timestamp"], reverse=True)
                total_bytes = sorted_dps[0].get("Average", 0)
                total_gb = total_bytes / (1024 ** 3)
                price_per_gb = 0.023
                return {
                    "total_bytes": int(total_bytes),
                    "total_gb": round(total_gb, 4),
                    "hourly_cost": round(total_gb * price_per_gb / 730, 6),
                    "monthly_cost": round(total_gb * price_per_gb, 2),
                }
        except Exception:
            return None

    async def _fetch_logs_ingestion_metrics(
        self, session: aioboto3.Session, region: str, log_group_name: str
    ) -> Optional[Dict[str, float]]:
        try:
            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(days=30)
            async with session.client("cloudwatch", region_name=region) as cw:
                response = await cw.get_metric_statistics(
                    Namespace="AWS/Logs",
                    MetricName="IncomingBytes",
                    Dimensions=[{"Name": "LogGroupName", "Value": log_group_name}],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=86400,
                    Statistics=["Sum"],
                )
                datapoints = response.get("Datapoints", [])
                if not datapoints:
                    return None
                total_bytes = sum(dp.get("Sum", 0) for dp in datapoints)
                total_gb = total_bytes / (1024 ** 3)
                price_per_gb = 0.50
                return {
                    "ingested_gb_30d": round(total_gb, 4),
                    "ingestion_cost_30d": round(total_gb * price_per_gb, 2),
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
        ebs_pricing = {
            "gp3": 0.08, "gp2": 0.08,
            "io1": 0.125, "io2": 0.125,
            "st1": 0.045, "sc1": 0.015,
            "standard": 0.05,
        }
        async with session.client("ec2", region_name=region) as ec2:
            paginator = ec2.get_paginator("describe_volumes")
            async for page in paginator.paginate():
                for vol in page["Volumes"]:
                    vol_type = vol["VolumeType"]
                    size = vol["Size"]
                    iops = vol.get("Iops", 0)
                    price_per_gb = ebs_pricing.get(vol_type, 0.08)
                    monthly = round(size * price_per_gb, 2)
                    if vol_type in ("io1", "io2"):
                        monthly += round(iops * 0.065, 2)
                    volumes.append({
                        "type": "ebs",
                        "resource_id": vol["VolumeId"],
                        "name": vol["VolumeId"],
                        "region": region,
                        "state": vol["State"],
                        "volume_type": vol_type,
                        "size_gb": size,
                        "attached": len(vol.get("Attachments", [])) > 0,
                        "tags": {t["Key"]: t["Value"] for t in vol.get("Tags", [])},
                        "specs": {
                            "iops": iops,
                            "hourly_cost": round(monthly / 730, 6) if monthly else None,
                            "monthly_cost": monthly,
                        },
                    })
        return volumes

    async def _scan_eips(self, session: aioboto3.Session, region: str) -> List[Dict[str, Any]]:
        eips = []
        unassociated_cost = 0.005
        async with session.client("ec2", region_name=region) as ec2:
            response = await ec2.describe_addresses()
            for address in response["Addresses"]:
                associated = bool(address.get("AssociationId"))
                hourly = unassociated_cost if not associated else 0
                eips.append({
                    "type": "eip",
                    "resource_id": address["AllocationId"],
                    "name": address.get("PublicIp", address["AllocationId"]),
                    "region": region,
                    "state": "associated" if associated else "unassociated",
                    "public_ip": address.get("PublicIp", ""),
                    "tags": {t["Key"]: t["Value"] for t in address.get("Tags", [])},
                    "specs": {
                        "domain": address.get("Domain", ""),
                        "hourly_cost": hourly,
                        "monthly_cost": round(hourly * 730, 2),
                    },
                })
        return eips

    async def _scan_load_balancers(self, session: aioboto3.Session, region: str) -> List[Dict[str, Any]]:
        lbs = []
        lb_pricing = {
            "application": 0.0225,
            "network": 0.0225,
            "gateway": 0.0225,
        }
        async with session.client("elbv2", region_name=region) as elbv2:
            paginator = elbv2.get_paginator("describe_load_balancers")
            async for page in paginator.paginate():
                for lb in page["LoadBalancers"]:
                    lb_type = lb["Type"]
                    hourly = lb_pricing.get(lb_type, 0.0225)
                    lbs.append({
                        "type": "lb",
                        "resource_id": lb["LoadBalancerArn"],
                        "name": lb["LoadBalancerName"],
                        "region": region,
                        "state": lb["State"]["Code"],
                        "scheme": lb["Scheme"],
                        "tags": {},
                        "specs": {
                            "type": lb_type,
                            "hourly_cost": hourly,
                            "monthly_cost": round(hourly * 730, 2),
                        },
                    })
        return lbs

    async def _scan_nat_gateways(self, session: aioboto3.Session, region: str) -> List[Dict[str, Any]]:
        gateways = []
        hourly_cost = 0.045
        async with session.client("ec2", region_name=region) as ec2:
            paginator = ec2.get_paginator("describe_nat_gateways")
            async for page in paginator.paginate():
                for ngw in page["NatGateways"]:
                    gateways.append({
                        "type": "nat_gateway",
                        "resource_id": ngw["NatGatewayId"],
                        "name": self._get_tag(ngw, "Name") or ngw["NatGatewayId"],
                        "region": region,
                        "state": ngw["State"],
                        "tags": {t["Key"]: t["Value"] for t in ngw.get("Tags", [])},
                        "specs": {
                            "connectivity_type": ngw.get("ConnectivityType", "public"),
                            "hourly_cost": hourly_cost,
                            "monthly_cost": round(hourly_cost * 730, 2),
                        },
                    })
        return gateways

    async def _scan_eks_clusters(self, session: aioboto3.Session, region: str) -> List[Dict[str, Any]]:
        clusters = []
        hourly_cost = 0.10
        async with session.client("eks", region_name=region) as eks:
            paginator = eks.get_paginator("list_clusters")
            async for page in paginator.paginate():
                for cluster_name in page["clusters"]:
                    cluster = await eks.describe_cluster(name=cluster_name)
                    c = cluster["cluster"]
                    clusters.append({
                        "type": "eks",
                        "resource_id": cluster_name,
                        "name": cluster_name,
                        "region": region,
                        "state": c["status"],
                        "version": c["version"],
                        "endpoint": c.get("endpoint", ""),
                        "tags": c.get("tags", {}),
                        "specs": {
                            "node_groups": len(c.get("resourcesVpcConfig", {}).get("securityGroupIds", [])),
                            "hourly_cost": hourly_cost,
                            "monthly_cost": round(hourly_cost * 730, 2),
                        },
                    })
        return clusters

    async def _scan_ebs_snapshots(self, session: aioboto3.Session, region: str) -> List[Dict[str, Any]]:
        snapshots = []
        async with session.client("ec2", region_name=region) as ec2:
            paginator = ec2.get_paginator("describe_snapshots")
            async for page in paginator.paginate(OwnerIds=["self"]):
                for snap in page["Snapshots"]:
                    age_days = (datetime.now(timezone.utc) - snap["StartTime"]).days
                    snapshots.append({
                        "type": "ebs_snapshot",
                        "resource_id": snap["SnapshotId"],
                        "name": self._get_tag(snap, "Name") or snap["SnapshotId"],
                        "region": region,
                        "state": snap["State"],
                        "volume_id": snap.get("VolumeId", ""),
                        "size_gb": snap["VolumeSize"],
                        "created": snap["StartTime"].isoformat(),
                        "age_days": age_days,
                        "tags": {t["Key"]: t["Value"] for t in snap.get("Tags", [])},
                        "specs": {
                            "hourly_cost": None,
                            "monthly_cost": round(snap["VolumeSize"] * 0.05, 2),
                        },
                    })
        return snapshots

    async def _scan_s3_buckets(self, session: aioboto3.Session, region: str) -> List[Dict[str, Any]]:
        buckets = []
        async with session.client("s3", region_name="us-east-1") as s3:
            response = await s3.list_buckets()
            for bucket in response.get("Buckets", []):
                bucket_region = "us-east-1"
                try:
                    loc = await s3.get_bucket_location(Bucket=bucket["Name"])
                    bucket_region = loc.get("LocationConstraint") or "us-east-1"
                except Exception:
                    pass
                storage = await self._fetch_s3_storage_metrics(
                    session, bucket_region, bucket["Name"]
                )
                buckets.append({
                    "type": "s3",
                    "resource_id": bucket["Name"],
                    "name": bucket["Name"],
                    "region": bucket_region,
                    "state": "available",
                    "created": bucket["CreationDate"].isoformat(),
                    "tags": {},
                    "specs": {
                        "hourly_cost": storage["hourly_cost"] if storage else None,
                        "monthly_cost": storage["monthly_cost"] if storage else None,
                    },
                    "metrics": storage,
                })
        return buckets

    async def _scan_cloudwatch_log_groups(self, session: aioboto3.Session, region: str) -> List[Dict[str, Any]]:
        log_groups = []
        async with session.client("logs", region_name=region) as logs:
            paginator = logs.get_paginator("describe_log_groups")
            async for page in paginator.paginate():
                for lg in page.get("logGroups", []):
                    retention = lg.get("retentionInDays")
                    name = lg.get("logGroupName", "")
                    stored_gb = lg.get("storedBytes", 0) / (1024 ** 3)
                    storage_cost = round(stored_gb * 0.03, 2)
                    ingestion = await self._fetch_logs_ingestion_metrics(
                        session, region, name
                    )
                    ingested_cost = ingestion["ingestion_cost_30d"] if ingestion else 0
                    total_monthly = storage_cost + ingested_cost
                    log_groups.append({
                        "type": "cloudwatch_log_group",
                        "resource_id": name,
                        "name": name,
                        "region": region,
                        "state": "exists",
                        "retention_days": retention,
                        "stored_gb": round(stored_gb, 4),
                        "tags": lg.get("tags", {}),
                        "specs": {
                            "retention_days": retention,
                            "hourly_cost": round(total_monthly / 730, 6),
                            "monthly_cost": total_monthly,
                        },
                        "metrics": {
                            "storage_cost": storage_cost,
                            "ingested_gb_30d": ingestion["ingested_gb_30d"] if ingestion else None,
                            "ingestion_cost_30d": ingested_cost,
                        },
                    })
        return log_groups

    def _get_tag(self, resource: Dict, key: str) -> Optional[str]:
        for tag in resource.get("Tags", []):
            if tag["Key"] == key:
                return tag["Value"]
        return None
