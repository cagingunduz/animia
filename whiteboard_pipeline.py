"""
Whiteboard Animation pipeline.

Flow: prompt -> Claude writes a whiteboard explainer script -> per scene: a clean
black line-art drawing on white (Grok) is "drawn" with a left-to-right reveal
(ffmpeg xfade, no hand), narration (ElevenLabs) merged in + optional word-level
captions -> concat into one explainer video.
"""

import os
import json
import uuid
import tempfile
import traceback
import subprocess

import anthropic

from jobs import job_store
from image_gen import generate_whiteboard_image, generate_whiteboard_color_image
from tts import generate_speech, get_audio_duration, get_word_timestamps
from storybook_pipeline import (
    concat_video_files,
    download_file,
    upload_bytes_to_r2,
    merge_video_audio,
    build_ass,
    burn_ass_subtitles,
    log,
    set_scene_status,
)

# Whiteboard explainers use fewer, longer scenes than the animated mode.
WHITEBOARD_SCENE_MAP = {1: 5, 2: 9, 3: 13, 5: 20, 10: 38}


def whiteboard_scene_count(duration_minutes: int) -> int:
    closest = min(WHITEBOARD_SCENE_MAP.keys(), key=lambda x: abs(x - duration_minutes))
    return WHITEBOARD_SCENE_MAP[closest]


def _dims(aspect_ratio: str, resolution: str) -> tuple:
    tall = resolution in ("1080p", "2k")
    if aspect_ratio == "9:16":
        return (1080, 1920) if tall else (720, 1280)
    if aspect_ratio == "1:1":
        return (1080, 1080) if tall else (720, 720)
    return (1920, 1080) if tall else (1280, 720)  # 16:9 default


def _whiteboard_draw(image_path: str, out_path: str, total_dur: float,
                     aspect_ratio: str, resolution: str, colored: bool = False,
                     render_style: str = "classic") -> bool:
    """Whiteboard 'being drawn' effect (no hand): trace the contours and draw clean
    lines following their own shape. When `colored`, draw the black outlines first,
    then wash the colour in over the line art (then hold the finished image)."""
    import math
    import numpy as np
    import cv2

    w, h = _dims(aspect_ratio, resolution)
    fps = 30
    total = max(3.0, float(total_dur))
    draw = max(1.5, min(total * 0.5, total - 0.5))  # draw faster, then hold the finished art

    src = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if src is None:
        return False
    # Fit the drawing onto a white w×h canvas
    ih, iw = src.shape[:2]
    scale = min(w / iw, h / ih)
    nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
    interp = cv2.INTER_LANCZOS4 if scale > 1 else cv2.INTER_AREA  # sharper upscaling
    resized = cv2.resize(src, (nw, nh), interpolation=interp)
    canvas_img = np.full((h, w, 3), 255, np.uint8)
    ox, oy = (w - nw) // 2, (h - nh) // 2
    canvas_img[oy:oy + nh, ox:ox + nw] = resized

    # Clean (kill JPEG ringing/speckle) → binary ink mask. In colour mode only the
    # near-black OUTLINES become "ink" (so colour fills are not traced as lines).
    gray = cv2.cvtColor(canvas_img, cv2.COLOR_BGR2GRAY)
    gray = cv2.medianBlur(gray, 3)
    ink_thresh = 95 if colored else 185
    _, ink = cv2.threshold(gray, ink_thresh, 255, cv2.THRESH_BINARY_INV)  # ink = white(255)

    # Vector trace: extract stroke contours, smooth out jitter/ripples, then DRAW them as
    # clean anti-aliased black lines (no raster copy → crisp, even strokes at any size).
    raw_contours, _ = cv2.findContours(ink, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    min_len = max(12, h / 90.0)  # drop tiny specks
    contours = [c for c in raw_contours if cv2.arcLength(c, True) >= min_len]
    band = max(20, h // 20)
    contours = sorted(contours, key=lambda c: (cv2.boundingRect(c)[1] // band, cv2.boundingRect(c)[0]))

    def _smooth_pts(c, passes=3):
        p = c[:, 0, :].astype(np.float32)
        if len(p) < 6:
            return p.astype(np.int32)
        for _ in range(passes):  # moving-average rounds off the wobble/scallops
            p = (np.roll(p, 1, 0) + p + np.roll(p, -1, 0)) / 3.0
        return p.astype(np.int32)

    segs = []  # (x1,y1,x2,y2) in draw order
    for c in contours:
        p = _smooth_pts(c)
        for k in range(len(p) - 1):
            segs.append((int(p[k][0]), int(p[k][1]), int(p[k + 1][0]), int(p[k + 1][1])))
        if len(p) > 2:
            segs.append((int(p[-1][0]), int(p[-1][1]), int(p[0][0]), int(p[0][1])))
    MAX_SEG = 200000
    if len(segs) > MAX_SEG:
        segs = segs[:: math.ceil(len(segs) / MAX_SEG)]
    n = len(segs)

    draw_frames = max(1, int(draw * fps))
    remaining = max(1, int(total * fps) - draw_frames)
    settle_frames = max(1, int(remaining * 0.45)) if colored else 0  # let colour finish filling
    hold_frames = max(1, remaining - settle_frames)
    thick = max(3, int(round(h / 260)))  # thick enough to merge the two stroke edges

    # Stream raw frames straight to ffmpeg (no lossy MJPG step) → crisp libx264.
    proc = subprocess.Popen(
        [
            "ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
            "-s", f"{w}x{h}", "-r", str(fps), "-i", "-", "-an",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-pix_fmt", "yuv420p", out_path,
        ],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    def emit(fr) -> bool:
        try:
            proc.stdin.write(fr.tobytes())
            return True
        except (BrokenPipeError, ValueError):
            return False

    frame = np.full((h, w, 3), 255, np.uint8)  # white board, lines drawn incrementally
    per = max(1, math.ceil(n / draw_frames)) if n > 0 else 0

    if not colored:
        # Phase A only — draw black outlines along their strokes, then hold the drawing
        idx = 0
        for _f in range(draw_frames):
            target = min(n, idx + per)
            for j in range(idx, target):
                x1, y1, x2, y2 = segs[j]
                cv2.line(frame, (x1, y1), (x2, y2), (0, 0, 0), thick, cv2.LINE_AA)
            idx = target
            if not emit(frame):
                break
        for _ in range(hold_frames):
            if not emit(frame):
                break
    elif render_style == "illustrated":
        # Canvas-style explainer mode: reveal the final illustration as ordered
        # visual components. This is intentionally not stroke-by-stroke tracing:
        # premium AI whiteboard products keep component/timing structure and then
        # render a scene reveal. We approximate that from the final image.
        gray_for_ink = cv2.cvtColor(canvas_img, cv2.COLOR_BGR2GRAY)
        ink_mask = ((gray_for_ink < 105) & (np.max(canvas_img, axis=2) < 135)).astype(np.uint8) * 255
        color_layer = canvas_img.copy()
        color_layer[ink_mask > 0] = (255, 255, 255)
        color_f = color_layer.astype(np.float32)
        white_f = np.full((h, w, 3), 255, np.float32)
        color_reveal_mask = np.zeros((h, w), np.uint8)
        line_reveal_mask = np.zeros((h, w), np.uint8)

        subject = (np.min(canvas_img, axis=2) < 248).astype(np.uint8) * 255
        close_size = max(9, int(round(h / 95)) | 1)
        close_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (close_size, close_size))
        small_size = max(7, int(round(h / 135)) | 1)
        small_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (small_size, small_size))
        subject = cv2.morphologyEx(subject, cv2.MORPH_CLOSE, close_kernel, iterations=2)
        subject = cv2.dilate(subject, small_kernel, iterations=1)

        def _fill_holes(mask):
            if mask is None or mask.max() == 0:
                return mask
            flood = mask.copy()
            cv2.floodFill(flood, np.zeros((h + 2, w + 2), np.uint8), (0, 0), 255)
            holes = cv2.bitwise_not(flood)
            return cv2.bitwise_or(mask, holes)

        subject = _fill_holes(subject)
        component_seed = cv2.morphologyEx(subject, cv2.MORPH_CLOSE, close_kernel, iterations=1)
        num, labels, stats, _centroids = cv2.connectedComponentsWithStats(component_seed, 8)
        min_component_area = max(400, (w * h) // 9000)
        regions = []

        def _add_region(mask, bbox, order_bias=0):
            mask = _fill_holes(mask)
            visible = cv2.bitwise_and(subject, mask)
            area = int(cv2.countNonZero(visible))
            if area < min_component_area:
                return
            x, y, rw, rh = bbox
            ink_area = int(cv2.countNonZero(cv2.bitwise_and(ink_mask, visible)))
            seed_source = cv2.bitwise_and(ink_mask, visible)
            seed_source = cv2.morphologyEx(seed_source, cv2.MORPH_CLOSE, small_kernel, iterations=1)
            seed_contours, _ = cv2.findContours(seed_source, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
            if not seed_contours:
                seed_contours, _ = cv2.findContours(visible, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
            seed_contours = [c for c in seed_contours if cv2.arcLength(c, True) > max(8, h / 180)]
            raw_paths = []
            for contour in seed_contours:
                pts = contour[:, 0, :]
                if len(pts) < 2:
                    continue
                step = max(1, int(math.ceil(len(pts) / 260)))
                sampled = pts[::step].astype(np.int32)
                if len(sampled) < 2:
                    continue
                if np.linalg.norm(sampled[0] - sampled[-1]) > max(3, thick * 2):
                    sampled = np.concatenate([sampled, sampled[:1]], axis=0)
                raw_paths.append(sampled)

            paths = []
            current = np.array([x, y], dtype=np.int32)
            while raw_paths:
                best_i = 0
                best_start = 0
                best_dist = None
                for i, sampled in enumerate(raw_paths):
                    d = np.sum((sampled - current) ** 2, axis=1)
                    start = int(np.argmin(d))
                    dist = int(d[start])
                    if best_dist is None or dist < best_dist:
                        best_i, best_start, best_dist = i, start, dist
                sampled = raw_paths.pop(best_i)
                if len(sampled) > 3:
                    sampled = np.concatenate([sampled[best_start:], sampled[:best_start + 1]], axis=0)
                path = [(int(px), int(py)) for px, py in sampled]
                paths.append(path)
                current = np.array(path[-1], dtype=np.int32)

            if not paths:
                paths = [[(int(x + rw / 2), int(y + rh / 2)), (int(x + rw / 2) + 1, int(y + rh / 2) + 1)]]

            regions.append({
                "mask": visible,
                "bbox": (int(x), int(y), int(rw), int(rh)),
                "area": area,
                "ink": ink_area,
                "order_bias": order_bias,
                "paths": paths,
            })

        for lab in range(1, num):
            area = int(stats[lab, cv2.CC_STAT_AREA])
            if area < min_component_area:
                continue
            x = int(stats[lab, cv2.CC_STAT_LEFT])
            y = int(stats[lab, cv2.CC_STAT_TOP])
            cw = int(stats[lab, cv2.CC_STAT_WIDTH])
            ch = int(stats[lab, cv2.CC_STAT_HEIGHT])
            comp = ((labels == lab).astype(np.uint8) * 255)
            comp = cv2.dilate(comp, small_kernel, iterations=1)
            _add_region(comp, (x, y, cw, ch))

        if not regions:
            regions = [{
                "mask": subject,
                "bbox": (0, 0, w, h),
                "area": max(1, int(cv2.countNonZero(subject))),
                "ink": int(cv2.countNonZero(ink_mask)),
                "order_bias": 0,
                "paths": [[(w // 2, h // 2), (w // 2 + 1, h // 2 + 1)]],
            }]

        # Strict top-to-bottom build: lower regions do not start until upper
        # regions have finished their own contour-led drawing.
        regions = sorted(
            regions,
            key=lambda r: (
                r["bbox"][1],
                r["bbox"][0],
                r["order_bias"],
            ),
        )
        def _region_path_len(region):
            return max(1, sum(max(1, len(path) - 1) for path in region.get("paths", [])))

        total_weight = max(1, sum(max(_region_path_len(r), r["ink"] ** 0.65, 1) for r in regions))
        total_frames = max(1, int(total * fps))
        hold_frames = min(2, max(0, total_frames // 60))
        reveal_frames = max(1, total_frames - hold_frames)
        soft_ksize = max(25, int(round(h / 48)) | 1)
        edge_kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (max(5, int(h / 180) | 1), max(5, int(h / 180) | 1)),
        )

        rng = np.random.default_rng(1729)
        noise_h = max(24, h // 28)
        noise_w = max(24, w // 28)
        noise_a = cv2.resize(
            rng.random((noise_h, noise_w)).astype(np.float32),
            (w, h),
            interpolation=cv2.INTER_CUBIC,
        )
        noise_b = cv2.resize(
            rng.random((noise_h, noise_w)).astype(np.float32),
            (w, h),
            interpolation=cv2.INTER_CUBIC,
        )

        def _organic_edge(mask, frame_no):
            if mask.max() == 0:
                return mask
            mix = (frame_no % 19) / 19.0
            noise = noise_a * (1.0 - mix) + noise_b * mix
            edge = cv2.morphologyEx(mask, cv2.MORPH_GRADIENT, edge_kernel)
            jitter = ((noise - 0.5) * 110.0).astype(np.float32)
            out = mask.astype(np.float32)
            out[edge > 0] = np.clip(out[edge > 0] + jitter[edge > 0], 0, 255)
            return out.astype(np.uint8)

        def _mask_from_drawn_strokes(region, stroke_seed, progress, frame_no):
            x, y, rw, rh = region["bbox"]
            radius = max(12, int(round(min(max(rw, 1), max(rh, 1)) / 15)))
            radius = min(radius, max(54, int(h / 16)))
            kernel_size = max(5, (radius * 2 + 1) | 1)
            stroke_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
            bloom = cv2.dilate(stroke_seed, stroke_kernel, iterations=1)

            # Late in the component, widen only the contour-guided bloom. Do not
            # reveal the whole region as a shortcut; the image must keep drawing
            # until the end instead of snapping to the source art.
            if progress > 0.72:
                grow = int((progress - 0.72) / 0.28 * max(rw, rh) / 8)
                if grow > 0:
                    grow_size = max(5, (grow * 2 + 1) | 1)
                    grow_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (grow_size, grow_size))
                    bloom = cv2.dilate(bloom, grow_kernel, iterations=1)
            bloom = cv2.GaussianBlur(bloom, (soft_ksize, soft_ksize), 0)

            progressive = bloom
            progressive = cv2.bitwise_and(progressive, region["mask"])
            progressive = _organic_edge(progressive, frame_no)
            progressive = cv2.dilate(progressive, edge_kernel, iterations=1)
            return progressive

        def _expand_paint_to_region(region, color_seed, frames, frame_no):
            if frames <= 0:
                return
            x, y, rw, rh = region["bbox"]
            base = max(7, int(round(max(rw, rh) / max(12, frames))))
            base = min(max(base, 7), max(45, h // 18))
            grow_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, ((base * 2 + 1) | 1, (base * 2 + 1) | 1))
            for k in range(frames):
                color_seed = cv2.dilate(color_seed, grow_kernel, iterations=1)
                active = cv2.bitwise_and(color_seed, region["mask"])
                active = _organic_edge(active, frame_no + k)
                yield active, color_seed

        def _composite(active_mask=None):
            a = cv2.GaussianBlur(color_reveal_mask, (soft_ksize, soft_ksize), 0)
            a = cv2.bitwise_and(a, subject).astype(np.float32) / 255.0
            a3 = cv2.merge([a, a, a])
            out = (color_f * a3 + white_f * (1.0 - a3)).astype(np.uint8)
            visible_ink = cv2.bitwise_and(line_reveal_mask, ink_mask) > 0
            out[visible_ink] = canvas_img[visible_ink]
            return out

        used = 0
        for ri, region in enumerate(regions):
            remaining_regions = len(regions) - ri
            frames_left = max(remaining_regions, reveal_frames - used)
            if ri == len(regions) - 1:
                region_frames = frames_left
            else:
                weight = max(_region_path_len(region), region["ink"] ** 0.65, 1)
                region_frames = max(5, int(round(reveal_frames * weight / total_weight)))
                region_frames = min(region_frames, max(5, frames_left - remaining_regions + 1))
            used += region_frames

            paths = region.get("paths") or []
            total_segments = _region_path_len(region)
            stroke_seed = np.zeros((h, w), np.uint8)
            color_seed = np.zeros((h, w), np.uint8)
            line_kernel_size = max(5, (thick * 6 + 1) | 1)
            line_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (line_kernel_size, line_kernel_size))
            path_idx = 0
            point_idx = 0
            drawn_segments = 0
            color_segments = 0
            delayed_segments = []
            color_lag_frames = max(5, min(10, int(round(fps * 0.24))))
            paint_tail_frames = max(color_lag_frames + 3, int(region_frames * 0.22))
            paint_tail_frames = min(max(0, region_frames - 3), paint_tail_frames)
            stroke_frames = max(1, region_frames - paint_tail_frames)
            segs_per_frame = max(1, int(math.ceil(total_segments / max(1, stroke_frames))))

            # Start the active mask exactly at the first drawable point. If a hand
            # overlay is added later, this same point is the pen-tip coordinate.
            if paths and paths[0]:
                cv2.circle(stroke_seed, paths[0][0], max(2, thick), 255, -1)

            for fidx in range(stroke_frames):
                budget = segs_per_frame
                frame_segments = []
                while budget > 0 and path_idx < len(paths):
                    path = paths[path_idx]
                    if len(path) < 2 or point_idx >= len(path) - 1:
                        path_idx += 1
                        point_idx = 0
                        if path_idx < len(paths) and paths[path_idx]:
                            cv2.circle(stroke_seed, paths[path_idx][0], max(2, thick), 255, -1)
                        continue
                    p1 = path[point_idx]
                    p2 = path[point_idx + 1]
                    cv2.line(stroke_seed, p1, p2, 255, max(2, thick + 1), cv2.LINE_AA)
                    frame_segments.append((p1, p2))
                    point_idx += 1
                    drawn_segments += 1
                    budget -= 1

                delayed_segments.append(frame_segments)
                line_reveal_mask = cv2.max(
                    line_reveal_mask,
                    cv2.bitwise_and(cv2.dilate(stroke_seed, line_kernel, iterations=1), region["mask"]),
                )
                if len(delayed_segments) > color_lag_frames:
                    for p1, p2 in delayed_segments.pop(0):
                        cv2.line(color_seed, p1, p2, 255, max(2, thick + 2), cv2.LINE_AA)
                        color_segments += 1

                progress = min(1.0, color_segments / float(total_segments))
                active = _mask_from_drawn_strokes(region, color_seed, progress, used - region_frames + fidx)
                color_reveal_mask = cv2.max(color_reveal_mask, active)
                if not emit(_composite(active)):
                    break

            for queued in delayed_segments:
                for p1, p2 in queued:
                    cv2.line(color_seed, p1, p2, 255, max(2, thick + 2), cv2.LINE_AA)
                    color_segments += 1
            color_reveal_mask = cv2.max(
                color_reveal_mask,
                _mask_from_drawn_strokes(region, color_seed, 1.0, used),
            )
            line_reveal_mask = cv2.max(
                line_reveal_mask,
                cv2.bitwise_and(cv2.dilate(stroke_seed, line_kernel, iterations=1), region["mask"]),
            )

            tail_start = used - region_frames + stroke_frames
            for active, color_seed in _expand_paint_to_region(region, color_seed, paint_tail_frames, tail_start):
                color_reveal_mask = cv2.max(color_reveal_mask, active)
                if not emit(_composite(active)):
                    break

        for _ in range(hold_frames):
            if not emit(_composite()):
                break
    else:
        # ── Colour mode: TWO visible passes ──
        # Phase A: draw the black outlines (clearly visible sketch, no colour yet)
        outline_frames = max(1, int(total * 0.42 * fps))
        color_frames = max(1, int(total * 0.40 * fps))
        col_hold = max(1, int(total * fps) - outline_frames - color_frames)
        op = max(1, math.ceil(n / outline_frames)) if n > 0 else 0
        idx = 0
        for _f in range(outline_frames):
            target = min(n, idx + op)
            for j in range(idx, target):
                x1, y1, x2, y2 = segs[j]
                cv2.line(frame, (x1, y1), (x2, y2), (0, 0, 0), thick, cv2.LINE_AA)
            idx = target
            if not emit(frame):
                break

        # Phase B: colour blooms along the SAME strokes (radial matte), filling interiors
        colmask = np.zeros((h, w), np.uint8)
        radius = max(14, int(round(h / 30)))
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
        colored_f = canvas_img.astype(np.float32)
        frame_f = frame.astype(np.float32)  # the finished outline (static during Phase B)

        def composite():
            a = cv2.GaussianBlur(colmask, (31, 31), 0).astype(np.float32) / 255.0
            a3 = cv2.merge([a, a, a])
            return (colored_f * a3 + frame_f * (1.0 - a3)).astype(np.uint8)

        cp = max(1, math.ceil(n / color_frames)) if n > 0 else 0
        cidx = 0
        for _f in range(color_frames):
            ctarget = min(n, cidx + cp)
            for j in range(cidx, ctarget):
                _, _, x2, y2 = segs[j]
                cv2.circle(colmask, (x2, y2), radius, 255, -1)  # seed colour at the stroke
            cidx = ctarget
            colmask = cv2.dilate(colmask, kernel)               # spread to fill interiors
            if not emit(composite()):
                break
        for _ in range(col_hold):  # hold the full coloured image
            if not emit(canvas_img):
                break

    try:
        proc.stdin.close()
    except (BrokenPipeError, ValueError):
        pass
    proc.wait()
    if proc.returncode != 0:
        print(f"[WARN] whiteboard draw encode rc={proc.returncode}")
    return proc.returncode == 0


async def generate_whiteboard_script(title: str, duration_minutes: int,
                                     scene_count: int | None = None,
                                     render_style: str = "classic") -> list:
    """Claude writes a whiteboard explainer: each scene is one clear thing to draw
    plus the narration that explains it."""
    if scene_count is None:
        scene_count = whiteboard_scene_count(duration_minutes)

    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    if render_style == "illustrated":
        visual_rules = """- "visual_concept": ONE rich illustrated explainer tableau that can be revealed in
  3-7 visual components (28-45 words). Include characters, props, arrows, symbols,
  maps, coins, charts, or cause-effect metaphors when they clarify the beat. Avoid
  tiny text; prefer symbols and readable shapes."""
        style_rules = """- Each visual_concept should feel like a premium AI whiteboard/canvas explainer:
  expressive black-ink drawing, warm colour fills, cross-hatching, editorial
  composition, storytelling tableau, market/classroom/historical scene, map,
  timeline, or simple visual metaphor.
- Do not request a lone icon unless the beat absolutely needs one. Build a small
  scene with multiple separated objects that can appear one by one."""
    else:
        visual_rules = """- "visual_concept": ONE simple thing to draw as a black-ink line doodle on a white
  board (10-20 words). A single clear object / icon / simple diagram / metaphor that
  illustrates this beat. Simple silhouettes draw well; avoid busy scenes, photos,
  text labels, or fine detail."""
        style_rules = """- Each visual_concept is a DISTINCT, simple drawable doodle.
- Keep it concrete and visual — prefer icons/metaphors over abstract words."""

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=8000,
        messages=[{
            "role": "user",
            "content": f"""You are a whiteboard explainer-video director. Write a clear, engaging
whiteboard animation script.

TOPIC: {title}
TOTAL SCENES: {scene_count} (each is one drawing + one narration beat, ~10-12s)

For each scene produce:
- "title": short scene title
{visual_rules}
- "narrator_text": the spoken explanation for this beat (1-2 sentences, <= 28 words).
  Clear, friendly, informative — like a teacher explaining. Builds on the previous beat.
- "tone": one of "calm", "informative", "exciting", "emotional", "closing".

RULES
- Logical flow: hook -> explanation -> build-up -> takeaway. The FINAL scene is the
  CLOSING (a clear takeaway / call to action), tone "closing".
{style_rules}

Respond with a valid JSON array ONLY, no other text:
[{{"scene_number":1,"title":"...","visual_concept":"...","narrator_text":"...","tone":"..."}}]"""
        }]
    )
    text = message.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


async def generate_single_whiteboard_scene(
    scene: dict,
    aspect_ratio: str,
    resolution: str,
    narrator_voice_id: str,
    include_narrator: bool,
    include_subtitles: bool,
    narrator_speed: float = 1.0,
    colored: bool = False,
    render_style: str = "classic",
) -> dict:
    tmp = tempfile.mkdtemp()
    run_id = uuid.uuid4().hex[:8]
    concept = scene.get("visual_concept", "") or scene.get("title", "")
    narrator_text = scene.get("narrator_text", "")
    tone = scene.get("tone", "informative")

    # 1) Drawing — black line-art, or colour illustration with black outlines
    if colored:
        img_url = await generate_whiteboard_color_image(concept, aspect_ratio, render_style)
    else:
        img_url = await generate_whiteboard_image(concept, aspect_ratio)
    img_bytes = await download_file(img_url)
    img_path = f"{tmp}/draw_{run_id}.jpg"
    with open(img_path, "wb") as f:
        f.write(img_bytes)

    # 2) Narration (optional) — drives the clip length
    _valid_voice = narrator_voice_id and str(narrator_voice_id).strip().lower() != "none"
    do_narrator = include_narrator and narrator_text and _valid_voice
    audio_bytes = None
    audio_path = None
    clip_dur = 6.0
    if do_narrator:
        try:
            from animated_story_pipeline import _speed_audio
            audio_bytes = await generate_speech(narrator_text, narrator_voice_id, tone=tone)
            audio_bytes = _speed_audio(audio_bytes, narrator_speed, tmp, run_id)
            audio_dur = get_audio_duration(audio_bytes)
            clip_dur = max(4.0, audio_dur + 0.6)
            audio_path = f"{tmp}/audio_{run_id}.mp3"
            with open(audio_path, "wb") as f:
                f.write(audio_bytes)
        except Exception as e:
            print(f"[WARN] whiteboard narration failed: {repr(e)}")
            audio_bytes = None

    # 3) Whiteboard "being drawn" animation
    reveal_path = f"{tmp}/reveal_{run_id}.mp4"
    if not _whiteboard_draw(
        img_path, reveal_path, clip_dur, aspect_ratio, resolution,
        colored=colored, render_style=render_style,
    ):
        raise RuntimeError("Whiteboard draw render failed")
    final_path = reveal_path

    # 4) Merge narration (xfade output is silent already)
    if audio_bytes and audio_path:
        merged = f"{tmp}/merged_{run_id}.mp4"
        if merge_video_audio(reveal_path, audio_path, merged):
            final_path = merged

    # 5) Captions
    if include_subtitles and audio_bytes:
        try:
            word_ts = await get_word_timestamps(audio_bytes)
            if word_ts:
                ass = build_ass(word_ts, aspect_ratio=aspect_ratio)
                ass_path = f"{tmp}/subs_{run_id}.ass"
                with open(ass_path, "w", encoding="utf-8") as f:
                    f.write(ass)
                subbed = f"{tmp}/subbed_{run_id}.mp4"
                if burn_ass_subtitles(final_path, ass_path, subbed):
                    final_path = subbed
        except Exception as e:
            print(f"[WARN] whiteboard captions failed: {repr(e)}")

    # 6) Upload
    with open(final_path, "rb") as f:
        out_url = upload_bytes_to_r2(f.read(), "whiteboard-scenes", "mp4", "video/mp4")
    return {"image_url": img_url, "video_url": out_url}


async def run_whiteboard_pipeline(job_id: str, payload: dict):
    try:
        title = payload["title"]
        duration_minutes = payload.get("duration_minutes", 1)
        aspect_ratio = payload.get("aspect_ratio", "16:9")
        resolution = payload.get("resolution", "1080p")
        scene_count = payload.get("scene_count")
        narrator_voice_id = payload.get("narrator_voice_id")
        narrator_speed = payload.get("narrator_speed", 1.0) or 1.0
        include_narrator = bool(payload.get("include_narrator", False))
        include_subtitles = bool(payload.get("include_subtitles", False))
        colored = bool(payload.get("colored", False))
        render_style = payload.get("render_style", "classic")
        if render_style not in ("classic", "illustrated"):
            render_style = "classic"
        if render_style == "illustrated":
            colored = True

        # 1) Script
        log(job_id, 1, 1, "Senaryo yazılıyor...")
        scenes = await generate_whiteboard_script(title, duration_minutes, scene_count, render_style)

        total = len(scenes)
        total_steps = total + 1
        job_store[job_id]["total_steps"] = total_steps
        job_store[job_id]["scenes"] = [
            {"scene_index": i + 1, "status": "queued", "video_url": None, "image_url": None}
            for i in range(total)
        ]

        # 2) Per scene
        clip_urls = []
        for i, scene in enumerate(scenes):
            idx = i + 1
            set_scene_status(job_id, idx, "processing")
            log(job_id, idx, total_steps, f"Sahne {idx}/{total}: çizim + animasyon...")
            res = await generate_single_whiteboard_scene(
                scene=scene,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                narrator_voice_id=narrator_voice_id,
                include_narrator=include_narrator,
                include_subtitles=include_subtitles,
                narrator_speed=narrator_speed,
                colored=colored,
                render_style=render_style,
            )
            for s in job_store[job_id]["scenes"]:
                if s["scene_index"] == idx:
                    s["image_url"] = res["image_url"]
                    break
            set_scene_status(job_id, idx, "completed", video_url=res["video_url"])
            clip_urls.append(res["video_url"])

        # 3) Concat
        if len(clip_urls) == 1:
            final_url = clip_urls[0]
        else:
            log(job_id, total_steps, total_steps, "Sahneler birleştiriliyor...")
            tmp = tempfile.mkdtemp()
            run_id = uuid.uuid4().hex[:8]
            paths = []
            for j, url in enumerate(clip_urls):
                data = await download_file(url)
                p = f"{tmp}/clip_{j}_{run_id}.mp4"
                with open(p, "wb") as f:
                    f.write(data)
                paths.append(p)
            final_path = f"{tmp}/final_{run_id}.mp4"
            if not concat_video_files(paths, final_path):
                raise RuntimeError("Final concat failed")
            with open(final_path, "rb") as f:
                final_url = upload_bytes_to_r2(f.read(), "whiteboard-final", "mp4", "video/mp4")

        job_store[job_id]["status"] = "completed"
        job_store[job_id]["message"] = "Tamamlandı!"
        job_store[job_id]["final_video_url"] = final_url

    except Exception as e:
        tb = traceback.format_exc()
        print(f"[{job_id}] Whiteboard pipeline hatası: {repr(e)}\n{tb}")
        job_store[job_id]["status"] = "failed"
        job_store[job_id]["error"] = repr(e)
        job_store[job_id]["traceback"] = tb
