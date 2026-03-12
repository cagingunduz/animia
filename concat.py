import subprocess
import os
import uuid
import httpx
import boto3
from botocore.config import Config

R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID")
R2_ACCESS_KEY = os.environ.get("R2_ACCESS_KEY")
R2_SECRET_KEY = os.environ.get("R2_SECRET_KEY")
R2_BUCKET = os.environ.get("R2_BUCKET", "animai-videos")
R2_PUBLIC_BASE = "https://pub-410f3488491a42f5a631e8944960bd55.r2.dev"

TMP_DIR = "/tmp/animai"


def ensure_tmp():
    os.makedirs(TMP_DIR, exist_ok=True)


def get_r2_client():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto"
    )


async def download_video(url: str, path: str):
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        with open(path, "wb") as f:
            f.write(resp.content)


def upload_video_to_r2(path: str, folder: str) -> str:
    s3 = get_r2_client()
    key = f"{folder}/{uuid.uuid4()}.mp4"
    with open(path, "rb") as f:
        s3.put_object(Bucket=R2_BUCKET, Key=key, Body=f, ContentType="video/mp4")
    return f"{R2_PUBLIC_BASE}/{key}"


async def concat_clips(clip_urls: list, output_folder: str = "scenes") -> str:
    """
    Concatenate multiple video clips into one using FFmpeg.
    Used for: K1 clip + K2 clip → scene video
    Also used for: scene1 + scene2 + ... → final video
    """
    ensure_tmp()
    run_id = uuid.uuid4().hex[:8]

    # Download all clips
    input_paths = []
    for i, url in enumerate(clip_urls):
        path = f"{TMP_DIR}/clip_{run_id}_{i}.mp4"
        await download_video(url, path)
        input_paths.append(path)

    # Create FFmpeg concat list
    list_path = f"{TMP_DIR}/list_{run_id}.txt"
    with open(list_path, "w") as f:
        for p in input_paths:
            f.write(f"file '{p}'\n")

    # Output path
    output_path = f"{TMP_DIR}/output_{run_id}.mp4"

    # Run FFmpeg concat
    result = subprocess.run([
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", list_path,
        "-c", "copy",
        output_path
    ], capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg concat failed: {result.stderr}")

    # Upload to R2
    r2_url = upload_video_to_r2(output_path, output_folder)

    # Cleanup
    for p in input_paths:
        try:
            os.remove(p)
        except:
            pass
    try:
        os.remove(list_path)
        os.remove(output_path)
    except:
        pass

    return r2_url
