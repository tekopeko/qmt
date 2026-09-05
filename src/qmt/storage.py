"""Media storage — local disk by default, Cloudflare R2 when configured.

Railway's filesystem is ephemeral: everything under data/uploads dies on the
next deploy, which is fatal the day the trainer records real exercise videos.
With the four R2_* env vars set, uploads land in the bucket instead and
/media/{name} redirects to a short-lived presigned URL — the auth gate stays
in the app, the bytes (and R2's free egress) come from Cloudflare.

The interface is deliberately tiny: save / delete / serve-info. Callers never
know which backend they got, and tests run on the local one unchanged.
"""

from __future__ import annotations

from pathlib import Path

from . import config


def r2_enabled() -> bool:
    return bool(config.R2_ACCOUNT_ID and config.R2_ACCESS_KEY_ID
                and config.R2_SECRET_ACCESS_KEY and config.R2_BUCKET)


def _client():
    """boto3 S3 client against the R2 endpoint — imported lazily so the local
    backend never needs boto3 at all."""
    import boto3
    from botocore.config import Config as BotoConfig

    return boto3.client(
        "s3",
        endpoint_url=f"https://{config.R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=config.R2_ACCESS_KEY_ID,
        aws_secret_access_key=config.R2_SECRET_ACCESS_KEY,
        region_name="auto",
        config=BotoConfig(signature_version="s3v4"),
    )


def save(name: str, local_path: Path, content_type: str | None) -> None:
    """Persist an already-validated temp file under `name`. The size cap and
    format checks happened while spooling — storage only stores."""
    if r2_enabled():
        extra = {"ContentType": content_type} if content_type else {}
        _client().upload_file(str(local_path), config.R2_BUCKET, name,
                              ExtraArgs=extra)
        local_path.unlink(missing_ok=True)
    else:
        config.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
        local_path.replace(config.MEDIA_DIR / name)


def delete(name: str) -> None:
    if r2_enabled():
        _client().delete_object(Bucket=config.R2_BUCKET, Key=name)
    (config.MEDIA_DIR / name).unlink(missing_ok=True)   # covers pre-R2 leftovers


def presigned_url(name: str, expires_s: int = 600) -> str:
    """A short-lived direct link — handed out only AFTER the app's own auth
    check on /media/{name}; the bucket itself stays private."""
    return _client().generate_presigned_url(
        "get_object", Params={"Bucket": config.R2_BUCKET, "Key": name},
        ExpiresIn=expires_s)


def local_path(name: str) -> Path:
    return config.MEDIA_DIR / name
