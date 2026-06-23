import os
import json
import secrets
import boto3

session = boto3.session.Session()
sm = session.client("secretsmanager")


def lambda_handler(event, context):
    secret_id = event["SecretId"]
    step = event["Step"]

    if step == "createSecret":
        _create_secret(secret_id)
    elif step == "setSecret":
        pass
    elif step == "testSecret":
        pass
    elif step == "finishSecret":
        _finish_secret(secret_id)
    else:
        raise ValueError(f"Unknown step: {step}")

    return {"Status": "Success"}


def _create_secret(secret_id):
    response = sm.get_secret_value(SecretId=secret_id)
    current = json.loads(response["SecretString"])

    current["jwt_secret_key"] = secrets.token_hex(32)

    sm.put_secret_value(
        SecretId=secret_id,
        SecretString=json.dumps(current),
        VersionStages=["AWSPENDING"],
    )


def _finish_secret(secret_id):
    meta = sm.describe_secret(SecretId=secret_id)

    current_version = None
    pending_version = None
    for version_id, stages in meta["VersionIdsToStages"].items():
        if "AWSCURRENT" in stages:
            current_version = version_id
        if "AWSPENDING" in stages:
            pending_version = version_id

    if not pending_version:
        return

    sm.update_secret_version_stage(
        SecretId=secret_id,
        VersionStage="AWSCURRENT",
        MoveToVersionId=pending_version,
        RemoveFromVersionId=current_version,
    )
