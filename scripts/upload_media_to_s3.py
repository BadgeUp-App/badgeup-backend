#!/usr/bin/env python3
"""Sube el contenido de media/ local al bucket S3/Supabase configurado."""
import mimetypes
import os
import sys
from pathlib import Path

import boto3

MEDIA_DIR = Path(__file__).resolve().parent.parent / "media"

ENDPOINT = os.getenv("AWS_S3_ENDPOINT_URL", "")
KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "")
SECRET = os.getenv("AWS_SECRET_ACCESS_KEY", "")
BUCKET = os.getenv("AWS_STORAGE_BUCKET_NAME", "badgeup-media")
REGION = os.getenv("AWS_S3_REGION_NAME", "us-east-1")


def main():
    if not all([ENDPOINT, KEY_ID, SECRET]):
        print(
            "Faltan env vars: AWS_S3_ENDPOINT_URL, AWS_ACCESS_KEY_ID, "
            "AWS_SECRET_ACCESS_KEY"
        )
        sys.exit(1)

    s3 = boto3.client(
        "s3",
        endpoint_url=ENDPOINT,
        aws_access_key_id=KEY_ID,
        aws_secret_access_key=SECRET,
        region_name=REGION,
    )

    if not MEDIA_DIR.is_dir():
        print(f"No existe: {MEDIA_DIR}")
        sys.exit(1)

    uploaded = 0
    skipped = 0
    for path in sorted(MEDIA_DIR.rglob("*")):
        if not path.is_file():
            continue
        key = str(path.relative_to(MEDIA_DIR))
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        try:
            s3.head_object(Bucket=BUCKET, Key=key)
            print(f"  ya existe: {key}")
            skipped += 1
            continue
        except s3.exceptions.ClientError:
            pass

        print(f"  subiendo: {key} ({content_type})")
        s3.upload_file(
            str(path),
            BUCKET,
            key,
            ExtraArgs={"ContentType": content_type},
        )
        uploaded += 1

    print(f"\nListo. {uploaded} subidos, {skipped} ya existian.")


if __name__ == "__main__":
    main()
