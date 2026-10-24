from __future__ import annotations

from pathlib import Path

import truststore

truststore.inject_into_ssl()

import boto3
from botocore.client import BaseClient
from botocore.config import Config

from app.config import Settings


class DocumentStorage:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.local_root = Path(settings.local_storage_path).resolve()
        self.client: BaseClient | None = None
        if settings.aws_endpoint_url_s3:
            self.client = boto3.client(
                "s3",
                endpoint_url=settings.aws_endpoint_url_s3,
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key,
                region_name=settings.aws_region,
                config=Config(
                    signature_version="s3v4", s3={"addressing_style": "path"}
                ),
            )

    def initialize(self) -> None:
        if self.client:
            self.client.head_bucket(Bucket=self.settings.s3_bucket)
        else:
            self.local_root.mkdir(parents=True, exist_ok=True)

    def put(self, key: str, data: bytes, media_type: str) -> None:
        if self.client:
            self.client.put_object(
                Bucket=self.settings.s3_bucket,
                Key=key,
                Body=data,
                ContentType=media_type,
            )
            return
        path = self._local_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> bytes:
        if self.client:
            result = self.client.get_object(Bucket=self.settings.s3_bucket, Key=key)
            return result["Body"].read()
        return self._local_path(key).read_bytes()

    def delete(self, key: str) -> None:
        if self.client:
            self.client.delete_object(Bucket=self.settings.s3_bucket, Key=key)
            return
        self._local_path(key).unlink(missing_ok=True)

    def _local_path(self, key: str) -> Path:
        path = (self.local_root / key).resolve()
        if self.local_root not in path.parents:
            raise ValueError("Invalid storage key")
        return path
