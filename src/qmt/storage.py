"""Media storage — local disk by default, Cloudflare R2 when configured.

Railway's filesystem is ephemeral: everything under data/uploads dies on the
next deploy, which is fatal the day the trainer records real exercise videos.
With the four R2_* env vars set, uploads land in the bucket instead and
/media/{name} redirects to a short-lived presigned URL — the auth gate stays
in the app, the bytes (and R2's free egress) come from Cloudflare.

The interface is deliberately tiny: save / delete / stream / serve-info. Callers
never know which backend they got, and tests run on the local one unchanged.
"""

from __future__ import annotations

from pathlib import Path
from typing import IO

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


def stream(name: str) -> tuple[IO[bytes], str | None]:
    """The stored bytes as a stream, and their content type where the backend
    keeps one (R2 does, the local disk does not). For a route that serves the
    bytes itself instead of redirecting: /slika, whose public URL must stay
    the same to be cached. The caller closes the stream. A name that is not
    stored raises FileNotFoundError on both backends."""
    if r2_enabled():
        from botocore.exceptions import ClientError

        try:
            obj = _client().get_object(Bucket=config.R2_BUCKET, Key=name)
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                raise FileNotFoundError(name) from e
            raise
        return obj["Body"], obj.get("ContentType")
    return local_path(name).open("rb"), None


def presigned_url(name: str, expires_s: int = 600) -> str:
    """A short-lived direct link — handed out only AFTER the app's own auth
    check on /media/{name}; the bucket itself stays private."""
    return _client().generate_presigned_url(
        "get_object", Params={"Bucket": config.R2_BUCKET, "Key": name},
        ExpiresIn=expires_s)


def local_path(name: str) -> Path:
    return config.MEDIA_DIR / name
