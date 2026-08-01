import boto3
from botocore.exceptions import ClientError

from .config import get_settings


def _internal_client():
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name="us-east-1",
    )


def delete_object(object_key: str) -> None:
    """Suppression best-effort d'un objet (jobs RGPD et suppressions manuelles)."""
    try:
        _internal_client().delete_object(
            Bucket=get_settings().s3_bucket, Key=object_key
        )
    except ClientError:
        pass


def object_exists(object_key: str) -> bool:
    try:
        _internal_client().head_object(
            Bucket=get_settings().s3_bucket, Key=object_key
        )
        return True
    except ClientError:
        return False


def _presign_client():
    # Client dédié à la présignature : la signature inclut le host, donc on utilise
    # l'endpoint public (accessible hors du réseau Docker) et non l'endpoint interne.
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_public_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name="us-east-1",
    )


def presign_clip_url(object_key: str, expires_in: int = 3600) -> str:
    settings = get_settings()
    return _presign_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket, "Key": object_key},
        ExpiresIn=expires_in,
    )
