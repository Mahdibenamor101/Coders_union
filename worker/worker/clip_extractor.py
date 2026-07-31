import os
import subprocess
import tempfile

import boto3
from botocore.exceptions import ClientError


def build_clip(frames: list[tuple[float, bytes]], fps: float, out_path: str) -> float:
    """Assemble des frames JPEG en MP4 H.264 via ffmpeg. Retourne la durée (s)."""
    if not frames:
        raise ValueError("cannot build a clip from zero frames")
    with tempfile.TemporaryDirectory() as tmp:
        for i, (_ts, jpeg) in enumerate(frames):
            with open(os.path.join(tmp, f"{i:06d}.jpg"), "wb") as f:
                f.write(jpeg)
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel", "error",
                "-framerate", str(fps),
                "-i", os.path.join(tmp, "%06d.jpg"),
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-pix_fmt", "yuv420p",
                out_path,
            ],
            check=True,
        )
    return len(frames) / fps


def make_s3_client(endpoint_url: str, access_key: str, secret_key: str):
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="us-east-1",
    )


def ensure_bucket(s3, bucket: str) -> None:
    try:
        s3.head_bucket(Bucket=bucket)
    except ClientError:
        s3.create_bucket(Bucket=bucket)


def upload_clip(s3, bucket: str, key: str, path: str) -> None:
    s3.upload_file(path, bucket, key, ExtraArgs={"ContentType": "video/mp4"})
