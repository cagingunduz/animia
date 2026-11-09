"""
Video Analysis: what each shot of the reference is made of — a generated picture (AI still or AI clip), animation built in
code (motion graphics, vector, kinetic type, code 3D), or real footage / real photos. Remakes pick their engine from it.

    probe()     two sharp frames per shot (30 % and 70 % in) + three measurements:
                  independent motion — how much of the frame still changes after the camera move between the two frames
                                       is cancelled (a still pushed in: ~0; code animation, footage: high)
                  flat               — share of pixels in flat fills (vector / code art: high; photos, paintings: low)
                  grain              — fine noise in the smooth areas (camera footage: high; code art: ~0)
    classify()  Claude labels every probed shot from its frame + the numbers, with a confidence and a reason
    decide()    the engine, computed (not written) from the duration-weighted shares, so the same labels always give
                the same answer: code ≥ 75 % → animation (Cinecode); otherwise pictures + code graphics (doc-analysis)
"""

import base64
import json
import os

import anthropic

MAX_SHOTS = int(os.environ.get("ANALYSIS_PROBE_SHOTS", "30"))
FRAME_W = 768                       # what Claude sees per shot (sharp enough for texture, line weight, AI artefacts)
SOURCES = ("generated", "code", "footage")


def _frame(video: str, t: float):
    """The exact frame at t (ffmpeg seeks precisely; OpenCV lands on the previous keyframe in long-GOP files)."""
    import subprocess
    import cv2
    import numpy as np
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0.0, t):.3f}", "-i", video, "-frames:v", "1", "-f", "image2pipe",
                        "-vcodec", "png", "-"], capture_output=True, timeout=60)
    if r.returncode or not r.stdout:
        return None
    return cv2.imdecode(np.frombuffer(r.stdout, np.uint8), cv2.IMREAD_COLOR)


def _metrics(f1, f2) -> dict:
    """Independent motion after an affine camera fit, flat-fill share and grain, on 320-px greys."""
    import cv2
    import numpy as np
    w = 320
    g1 = cv2.cvtColor(cv2.resize(f1, (w, round(w * f1.shape[0] / f1.shape[1]))), cv2.COLOR_BGR2GRAY)
    g2 = cv2.cvtColor(cv2.resize(f2, (g1.shape[1], g1.shape[0])), cv2.COLOR_BGR2GRAY)
    # a light blur first: resampling fine detail during a zoom must not count as motion
    a = cv2.GaussianBlur(g1, (5, 5), 0).astype(np.float32) / 255
    b = cv2.GaussianBlur(g2, (5, 5), 0).astype(np.float32) / 255
    m = 12                                   # ignore the borders a camera move uncovers
    changed = lambda x, y: float((np.abs(x - y)[m:-m, m:-m] > 0.1).mean())
    still = changed(a, b)                    # no camera at all
    warp = np.eye(2, 3, dtype=np.float32)
    moved = still
    try:
        # ECC finds the warp from frame 1's coordinates into frame 2; frame 2 pulled back onto frame 1 compares like for like
        _, warp = cv2.findTransformECC(a, b, warp, cv2.MOTION_AFFINE,
                                       (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 80, 1e-6), None, 5)
        moved = changed(a, cv2.warpAffine(b, warp, (a.shape[1], a.shape[0]), flags=cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP))
    except cv2.error:
        pass
    # whichever explains the change better: a camera move (still picture pushed / panned) or no camera (things move on
    # their own). On flat backgrounds the fit can latch onto a moving shape, so it only counts when it helps.
    independent = min(still, moved)
    camera = 0.0 if still <= moved else float(np.hypot(warp[0, 2], warp[1, 2]) / w + abs(1 - np.sqrt(abs(np.linalg.det(warp[:, :2])))))
    raw = g1.astype(np.float32) / 255                       # flatness and grain on the unblurred frame
    std = cv2.blur(raw * raw, (5, 5)) - cv2.blur(raw, (5, 5)) ** 2
    flat = float((std < (2 / 255) ** 2).mean())
    lap = cv2.Laplacian(raw, cv2.CV_32F)
    smooth = std < (6 / 255) ** 2
    grain = float(np.abs(lap[smooth]).mean() * 255) if smooth.sum() > 500 else 0.0
    return {"independent_motion": round(independent, 3), "camera_move": round(camera, 3),
            "flat": round(flat, 3), "grain": round(grain, 2)}


def probe(video: str, shots: list, duration: float, out_dir: str) -> list[dict]:
    """Up to MAX_SHOTS shots, spread evenly over the video; each with its sharp frame (saved) and its measurements."""
    import cv2
    spans = [(float(a), float(b)) for a, b in (shots or [[0.0, duration]]) if b - a > 0.15] or [(0.0, duration)]
    idx = list(range(len(spans)))
    if len(idx) > MAX_SHOTS:
        idx = sorted({round(i * (len(spans) - 1) / (MAX_SHOTS - 1)) for i in range(MAX_SHOTS)})
    os.makedirs(out_dir, exist_ok=True)
    res = []
    for i in idx:
        a, b = spans[i]
        f1, f2 = _frame(video, a + (b - a) * .3), _frame(video, a + (b - a) * .7)
        if f1 is None or f2 is None:
            continue
        mid = _frame(video, (a + b) / 2)
        mid = mid if mid is not None else f2
        path = os.path.join(out_dir, f"shot_{i + 1:03d}.jpg")
        cv2.imwrite(path, cv2.resize(mid, (FRAME_W, round(FRAME_W * mid.shape[0] / mid.shape[1]))), [cv2.IMWRITE_JPEG_QUALITY, 86])
        res.append({"shot": i + 1, "start": round(a, 2), "end": round(b, 2), "frame": path, **_metrics(f1, f2)})
    return res


CLASSIFY_TOOL = {
    "name": "submit_sources",
    "description": "Submit what each shot is made of.",
    "input_schema": {
        "type": "object",
        "required": ["shots"],
        "properties": {
            "shots": {"type": "array", "items": {
                "type": "object", "required": ["shot", "source", "confidence", "why"],
                "properties": {
                    "shot": {"type": "integer"},
                    "source": {"type": "string", "enum": list(SOURCES),
                               "description": "generated = an AI-made picture or clip (painted / photoreal / illustrated still, usually moved by a camera push or pan); code = drawn and animated in code (motion graphics, vector shapes, kinetic type, charts, code-built 3D); footage = real camera footage or real photographs"},
                    "overlay": {"type": "boolean", "description": "code-made text / marks / graphics sit on top of it"},
                    "confidence": {"type": "number", "description": "0-1"},
                    "why": {"type": "string", "description": "the visual and measured cues, in a few words"}}}},
            "notes": {"type": "string", "description": "anything that makes the call uncertain"},
        },
    },
}

SYSTEM = """You tell how each shot of a short video was made, from one sharp frame per shot plus measurements taken from two
frames of the same shot. The cues:
- code animation: flat colour fills, perfect geometry, uniform line weights, crisp aligned type, chart / diagram layouts;
  in motion, parts move independently of each other (high independent_motion) while the frame is clean (grain ~0, flat high).
- generated picture: painterly or photographic texture, rich light and shadow, organic clutter, AI artefacts (melted objects,
  garbled pseudo-text, odd hands, faces on objects); in motion usually ONE still moved by the camera (camera_move > 0,
  independent_motion near 0). An AI video clip moves inside the frame but keeps the AI look.
- footage: real people and places, sensor noise (grain high), motion blur, imperfect framing, natural light.
Text or graphics drawn over a picture do not make it code: label the picture underneath and set overlay. Judge every shot
on its own; give a low confidence when the cues disagree."""


def _img(path: str) -> dict:
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                        "data": base64.b64encode(open(path, "rb").read()).decode()}}


async def classify(job_id: str, probes: list[dict], client, model: str, effort: str, think_room: int, record_usage) -> list[dict]:
    content = []
    for p in probes:
        meas = {k: p[k] for k in ("independent_motion", "camera_move", "flat", "grain")}
        content += [{"type": "text", "text": f"Shot {p['shot']} ({p['start']:.1f}-{p['end']:.1f} s) · measured {json.dumps(meas)}"}, _img(p["frame"])]
    content.append({"type": "text", "text": "Label every shot above. Answer by calling the `submit_sources` tool."})
    try:
        async with client.messages.stream(
            model=model, max_tokens=4000 + think_room, output_config={"effort": effort}, system=SYSTEM,
            tools=[CLASSIFY_TOOL], tool_choice={"type": "auto"}, messages=[{"role": "user", "content": content}],
        ) as stream:
            msg = await stream.get_final_message()
    except anthropic.APIStatusError as e:
        raise RuntimeError(str(e)[:200]) from e
    record_usage(job_id, "classify", model, msg.usage)
    labels = {}
    for blk in msg.content:
        if getattr(blk, "type", "") == "tool_use":
            for x in blk.input.get("shots") or []:
                if x.get("source") in SOURCES:
                    labels[int(x.get("shot") or 0)] = x
    out = []
    for p in probes:
        x = labels.get(p["shot"])
        if not x:
            continue
        try:
            conf = round(max(0.0, min(1.0, float(x.get("confidence")))), 2)
        except (TypeError, ValueError):
            conf = 0.5
        out.append({"shot": p["shot"], "start": p["start"], "end": p["end"], "source": x["source"], "overlay": bool(x.get("overlay")),
                    "confidence": conf, "why": str(x.get("why") or "")[:160],
                    "metrics": {k: p[k] for k in ("independent_motion", "camera_move", "flat", "grain")}})
    return out


def decide(labels: list[dict], shots: list, duration: float) -> dict:
    """Duration-weighted shares over ALL shots (an unprobed shot takes the label of the nearest probed one) and the engine."""
    if not labels:
        return {"shares": {}, "engine": None, "confidence": 0.0}
    spans = [(float(a), float(b)) for a, b in (shots or [[0.0, duration]])] or [(0.0, duration)]
    by_shot = {x["shot"]: x for x in labels}
    probed = sorted(by_shot)
    tot = {k: 0.0 for k in SOURCES}
    conf_w = 0.0
    for i, (a, b) in enumerate(spans, 1):
        near = min(probed, key=lambda s: abs(s - i))
        x = by_shot[near]
        tot[x["source"]] += b - a
        conf_w += (b - a) * x["confidence"]
    total = sum(tot.values()) or 1.0
    shares = {k: round(v / total, 2) for k, v in tot.items()}
    engine = "animation" if shares["code"] >= 0.75 else "images" if shares["code"] <= 0.25 else "mixed"
    return {"shares": shares, "engine": engine, "confidence": round(conf_w / total, 2),
            "template": "cinecode-film" if engine == "animation" else "doc-analysis"}
