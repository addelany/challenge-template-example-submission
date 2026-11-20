"""Read a CSV from the challenge's S3 storage: by URL, or with a key for a private bucket.

Used by forecast.py (the targets) and cleanup_forecasts.py (what the challenge has
processed). A public bucket is read by its URL. With S3_KEY and S3_SECRET set, the same
address is read through the S3 API with the key, which also works when the bucket is
private (this uses boto3). A bucket on Backblaze B2 (s3.<region>.backblazeb2.com) is
signed for its region.
"""
import io
import os
import re
from urllib.parse import urlparse

import pandas as pd


def read_csv(url):
    """Read a CSV (or CSV.GZ) from `url`, with the S3 key from the environment if set."""
    key, secret = os.environ.get("S3_KEY", ""), os.environ.get("S3_SECRET", "")
    if not url.startswith(("http://", "https://")) or not (key and secret):
        return pd.read_csv(url)
    import boto3                                    # only needed for a private bucket
    from botocore.config import Config

    parts = urlparse(url)                           # https://<endpoint>/<bucket>/<object>
    bucket, _, name = parts.path.lstrip("/").partition("/")
    region = re.match(r"^s3\.([a-z0-9-]+)\.backblazeb2\.com$", parts.netloc)
    s3 = boto3.client(
        "s3", endpoint_url=f"{parts.scheme}://{parts.netloc}",
        aws_access_key_id=key, aws_secret_access_key=secret,
        region_name=region.group(1) if region else "us-east-1",
        config=Config(s3={"addressing_style": "path"}),
    )
    body = s3.get_object(Bucket=bucket, Key=name)["Body"].read()
    return pd.read_csv(io.BytesIO(body), compression="gzip" if name.endswith(".gz") else None)
