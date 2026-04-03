import os
import uuid
import asyncio
import subprocess
import tempfile
import traceback
import httpx
import boto3
from botocore.config import Config

from jobs import job_store
from image_gen import generate_storybook_scene_image
from tts import generate_speech, get_audio_duration

R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID")
R2_ACCESS_KEY = os.environ.get("R2_ACCESS_KEY")
R2_SECRET_KEY = os.environ.get("R2_SECRET_KEY")
R2_BUCKET = os.environ.get("R2_BUCKET", "animai-videos")
R2_PUBLIC_BASE = "https://assets.animave.com"


def get_r2_client():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto"
    )


def upload_bytes_to_r2(data: bytes, folder: str, ext: str, content_type: str) -> str:
    s3 = get_r2_client()
    key = f"{folder}/{uuid.uuid4()}.{ext}"
    s3.put_object(Bucket=R2_BUCKET, Key=key, Body=data, ContentType=content_type)
    return f"{R2_PUBLIC_BASE}/{key}"


def log(job_id: str, step: int, total: int, message: str, status: str = "processing"):
    job_store[job_id]["status"] = status
    job_store[job_id]["step"] = step
    job_store[job_id]["total_steps"] = total
    job_store[job_id]["message"] = message
    print(f"[{job_id}] Step {step}/{total}: {message}")


def set_scene_status(job_id: str, scene_index: int, status: str, video_url: str = None):
    scenes = job_store[job_id]["scenes"]
    for s in scenes:
        if s["scene_index"] == scene_index:
            s["status"] = status
            if video_url:
                s["video_url"] = video_url
            break


async def download_file(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


def apply_ken_burns(image_path: str, output_path: str, duration: int = 8, aspect_ratio: str = "9:16") -> bool:
    size_map = {"9:16": "1080x1920", "16:9": "1920x1080", "1:1": "1080x1080"}
    size = size_map.get(aspect_ratio, "1080x1920")
    result = subprocess.run([
        "ffmpeg", "-loop", "1", "-i", image_path, "-y",
        "-filter_complex",
        f"[0]scale=8000:-2,setsar=1:1[out];[out]zoompan=z='zoom+0.001':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=200:s={size}:fps=25[out]",
        "-vcodec", "libx264", "-map", "[out]", "-pix_fmt", "yuv420p", "-r", "25", "-t", str(duration),
        output_path
    ], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Ken Burns error: {result.stderr}")
        return False
    return True


def make_static_video(image_path: str, output_path: str, duration: int = 8, aspect_ratio: str = "9:16") -> bool:
    """Static video without Ken Burns — just image held for duration."""
    size_map = {"9:16": "1080x1920", "16:9": "1920x1080", "1:1": "1080x1080"}
    size = size_map.get(aspect_ratio, "1080x1920")
    result = subprocess.run([
        "ffmpeg", "-loop", "1", "-i", image_path, "-y",
        "-vf", f"scale={size}:force_original_aspect_ratio=decrease,pad={size}:(ow-iw)/2:(oh-ih)/2",
        "-vcodec", "libx264", "-pix_fmt", "yuv420p", "-r", "25", "-t", str(duration),
        output_path
    ], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Static video error: {result.stderr}")
        return False
    return True


def merge_video_audio(video_path: str, audio_path: str, output_path: str) -> bool:
    result = subprocess.run([
        "ffmpeg", "-y", "-i", video_path, "-i", audio_path,
        "-c:v", "copy", "-c:a", "aac", "-shortest", output_path
    ], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"FFmpeg merge error: {result.stderr}")
        return False
    return True


def concat_video_files(video_paths: list, output_path: str) -> bool:
    tmp = tempfile.mkdtemp()
    list_path = f"{tmp}/concat_list.txt"
    with open(list_path, "w") as f:
        for vp in video_paths:
            f.write(f"file '{vp}'\n")
    result = subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path, "-c", "copy", output_path
    ], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"FFmpeg concat error: {result.stderr}")
        return False
    return True


async def generate_single_scene(
    scene_description: str,
    narrator_text: str,
    narrator_voice_id: str,       # kullanıcının seçtiği ses — değiştirme
    aspect_ratio: str = "9:16",
    scene_duration: int = 8,
    ken_burns: bool = True,
    include_narrator: bool = True,
) -> dict:
    """
    Single scene pipeline: Grok → Ken Burns/Static → Narrator → Merge → R2
    Returns: { image_url, video_url }
    """
    tmp = tempfile.mkdtemp()
    run_id = uuid.uuid4().hex[:8]

    # 1. Generate image with Grok
    image_url = await generate_storybook_scene_image(
        scene_prompt=scene_description,
        aspect_ratio=aspect_ratio
    )

    # 2. Download image
    image_bytes = await download_file(image_url)
    image_path = f"{tmp}/scene_{run_id}.jpg"
    with open(image_path, "wb") as f:
        f.write(image_bytes)

    # 3. Apply Ken Burns or static
    video_path = f"{tmp}/video_{run_id}.mp4"
    if ken_burns:
        success = apply_ken_burns(image_path, video_path, duration=scene_duration, aspect_ratio=aspect_ratio)
    else:
        success = make_static_video(image_path, video_path, duration=scene_duration, aspect_ratio=aspect_ratio)

    if not success:
        raise RuntimeError("Video generation failed")

    # 4. Generate narrator audio and merge
    final_video_path = video_path
    _valid_voice = narrator_voice_id and narrator_voice_id.strip().lower() != 'none'
    if include_narrator and narrator_text and _valid_voice:
        try:
            audio_bytes = await generate_speech(narrator_text, narrator_voice_id)
            audio_path = f"{tmp}/audio_{run_id}.mp3"
            with open(audio_path, "wb") as f:
                f.write(audio_bytes)

            merged_path = f"{tmp}/merged_{run_id}.mp4"
            success = merge_video_audio(video_path, audio_path, merged_path)
            if success:
                final_video_path = merged_path
            else:
                print(f"[WARN] Audio merge failed, returning video without audio")
        except Exception as e:
            status_code = getattr(e, 'status_code', None)
            body = getattr(e, 'body', None)
            print(f"[WARN] TTS failed for narrator: {repr(e)} | status={status_code} | body={body}")

    # 5. Upload to R2
    with open(final_video_path, "rb") as f:
        video_data = f.read()

    video_url = upload_bytes_to_r2(video_data, "storybook-scenes", "mp4", "video/mp4")

    # Cleanup
    for path in [image_path, video_path, final_video_path]:
        try:
            os.remove(path)
        except:
            pass

    return {"image_url": image_url, "video_url": video_url}


async def process_storybook_scene(
    job_id: str,
    scene: dict,
    scene_index: int,
    total_scenes: int,
    step: int,
    total_steps: int,
    narrator_voice_id: str,
    aspect_ratio: str = "9:16",
    scene_duration: int = 8,
) -> str:
    set_scene_status(job_id, scene_index, "processing")

    step += 1
    log(job_id, step, total_steps, f"Sahne {scene_index}/{total_scenes}: Gorsel + video uretiliyor...")

    result = await generate_single_scene(
        scene_description=scene.get("scene_description") or "",
        narrator_text=scene.get("narrator_text") or "",
        narrator_voice_id=narrator_voice_id,
        aspect_ratio=aspect_ratio,
        scene_duration=scene_duration,
        ken_burns=True,
        include_narrator=True,
    )

    scenes = job_store[job_id]["scenes"]
    for s in scenes:
        if s["scene_index"] == scene_index:
            s["image_url"] = result["image_url"]
            break

    set_scene_status(job_id, scene_index, "completed", video_url=result["video_url"])
    job_store[job_id]["step"] = step
    return result["video_url"]


async def run_storybook_pipeline(job_id: str, payload: dict):
    try:
        scenes_list = payload["scenes"]
        narrator_voice_id = payload.get("narrator_voice_id")
        aspect_ratio = payload.get("aspect_ratio", "9:16")
        scene_duration = payload.get("scene_duration", 8)

        if not narrator_voice_id:
            raise ValueError("narrator_voice_id is required")

        total_scenes = len(scenes_list)
        total_steps = total_scenes + 1
        job_store[job_id]["total_steps"] = total_steps
        step = 0

        scene_video_urls = []
        for i, scene in enumerate(scenes_list):
            scene_index = i + 1
            scene_url = await process_storybook_scene(
                job_id=job_id, scene=scene, scene_index=scene_index,
                total_scenes=total_scenes, step=step, total_steps=total_steps,
                narrator_voice_id=narrator_voice_id,
                aspect_ratio=aspect_ratio, scene_duration=scene_duration,
            )
            scene_video_urls.append(scene_url)
            step = job_store[job_id]["step"]

        if len(scene_video_urls) == 1:
            final_url = scene_video_urls[0]
        else:
            step += 1
            log(job_id, step, total_steps, "Tüm sahneler birleştiriliyor...")
            tmp = tempfile.mkdtemp()
            run_id = uuid.uuid4().hex[:8]
            local_paths = []
            for idx, url in enumerate(scene_video_urls):
                video_bytes = await download_file(url)
                local_path = f"{tmp}/scene_{idx}_{run_id}.mp4"
                with open(local_path, "wb") as f:
                    f.write(video_bytes)
                local_paths.append(local_path)

            final_path = f"{tmp}/final_{run_id}.mp4"
            if not concat_video_files(local_paths, final_path):
                raise RuntimeError("Final concat failed")

            with open(final_path, "rb") as f:
                final_data = f.read()

            final_url = upload_bytes_to_r2(final_data, "storybook-final", "mp4", "video/mp4")

            for p in local_paths + [final_path]:
                try:
                    os.remove(p)
                except:
                    pass

        job_store[job_id]["status"] = "completed"
        job_store[job_id]["message"] = "Tamamlandı!"
        job_store[job_id]["final_video_url"] = final_url

    except Exception as e:
        tb = traceback.format_exc()
        print(f"[{job_id}] Storybook pipeline hatası: {repr(e)}\n{tb}")
        job_store[job_id]["status"] = "failed"
        job_store[job_id]["error"] = repr(e)
        job_store[job_id]["traceback"] = tb
