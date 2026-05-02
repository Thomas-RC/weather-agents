"""MinIO (S3-compatible) — obrazy radaru i satelity."""

from __future__ import annotations

from datetime import timedelta

import boto3
from botocore.client import Config

from src.config import get_settings


def get_client(public: bool = False):
    s = get_settings()
    endpoint = s.minio_public_endpoint if public else f"http://{s.minio_endpoint}"
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=s.minio_access_key,
        aws_secret_access_key=s.minio_secret_key,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",  # MinIO ignoruje, ale boto wymaga
    )


def ensure_bucket(client=None) -> None:
    """Idempotentnie tworzy bucket jeśli nie istnieje."""
    s = get_settings()
    c = client or get_client()
    existing = {b["Name"] for b in c.list_buckets().get("Buckets", [])}
    if s.minio_bucket not in existing:
        c.create_bucket(Bucket=s.minio_bucket)


def put_object(key: str, data: bytes, content_type: str = "image/png", client=None) -> str:
    """Wrzuca obiekt do bucketu, zwraca pełen klucz."""
    s = get_settings()
    c = client or get_client()
    c.put_object(Bucket=s.minio_bucket, Key=key, Body=data, ContentType=content_type)
    return key


def get_object(key: str, client=None) -> bytes:
    s = get_settings()
    c = client or get_client()
    obj = c.get_object(Bucket=s.minio_bucket, Key=key)
    return obj["Body"].read()


def presigned_get_url(key: str, expires_in: int = 3600) -> str:
    """Generuje presigned URL dostępny z hosta (przez minio_public_endpoint)."""
    s = get_settings()
    c = get_client(public=True)
    return c.generate_presigned_url(
        "get_object",
        Params={"Bucket": s.minio_bucket, "Key": key},
        ExpiresIn=int(timedelta(seconds=expires_in).total_seconds()),
    )
