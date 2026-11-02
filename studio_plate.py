"""Style Studio footage plates: the shot list cut into one 1080x1920 video that plays under the film's canvas.

A shot: { t0, t1 (film seconds), path, kind: 'video' | 'image' | None (black), src: seconds into the source (video),
          speed: 1 (0.5 = slow motion), reverse: False, freeze: film second where the picture stops (holds to t1),
          punch: film second where a 0.3 s punch-in to 1.25x starts, fit: 'band' (top 1080x1560) | 'full',
          box: [x, y, w, h] in 0..1 of the source to frame (optional, for telestrator moments) }
Everything is graded alike (a touch more contrast, a touch less saturation), scaled to cover and cropped.
"""

import os
import subprocess

FPS = 30
W, H = 1080, 1920
BAND = 1560
TELE = (250, 1350)          # telestrator band: y offset, height (4:5 window of the match clip)
GRADE = "eq=contrast=1.07:saturation=0.92:brightness=-0.01"


def _run(args: list[str]):
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg: " + r.stderr[-800:])


def _enc(out: str) -> list[str]:
    return ["-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(FPS), "-g", str(FPS), out]


def _segment(sh: dict, out: str):
    dur = round(sh["t1"] - sh["t0"], 4)
    n = max(1, round(dur * FPS))
    fit = sh.get("fit")
    fh = H if fit == "full" else (TELE[1] if fit == "tele" else BAND)
    y_off = TELE[0] if fit == "tele" else 0
    cover = (f"scale={W}:{fh}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{fh},unsharp=5:5:0.4")
    box = sh.get("box")
    pre = f"crop=iw*{box[2]:.4f}:ih*{box[3]:.4f}:iw*{box[0]:.4f}:ih*{box[1]:.4f}," if box else ""
    pad = f",pad={W}:{H}:0:{y_off}:black" if fh < H else ""
    kind = sh.get("kind")
    if kind == "video" and sh.get("path"):
        speed = max(.1, float(sh.get("speed") or 1))
        play = dur if sh.get("freeze") is None else max(1 / FPS, float(sh["freeze"]) - sh["t0"])
        src_len = play * speed + 0.2
        chain = f"{pre}setpts=(PTS-STARTPTS)/{speed},fps={FPS},{cover},{GRADE}"
        if sh.get("reverse"):
            chain = f"{pre}reverse,setpts=(PTS-STARTPTS)/{speed},fps={FPS},{cover},{GRADE}"
        chain += f",tpad=stop_mode=clone:stop_duration={dur + 1:.2f},trim=end_frame={round(play * FPS)}" if sh.get("freeze") is not None else ""
        chain += f",tpad=stop_mode=clone:stop_duration={dur + 1:.2f},trim=end_frame={n},setpts=PTS-STARTPTS"
        if sh.get("freeze") is not None and sh.get("desat", fit == "tele"):   # the analysis look while frozen
            chain += f",eq=saturation=0.58:contrast=1.03:enable='gte(t,{max(0.0, float(sh['freeze']) - sh['t0']):.3f})'"
        if sh.get("punch") is not None:
            p0 = max(0, round((float(sh["punch"]) - sh["t0"]) * FPS))
            chain += (f",zoompan=z='if(lt(on,{p0}),1,min(1.25,1+(on-{p0})*0.25/9))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                      f":d=1:s={W}x{fh}:fps={FPS}")
        _run(["-ss", f"{float(sh.get('src') or 0):.3f}", "-t", f"{src_len:.3f}", "-i", sh["path"], "-vf", chain + pad, "-frames:v", str(n), *_enc(out)])
    elif kind == "image" and sh.get("path"):
        z = f"1+0.06*on/{n}" if sh.get("punch") is None else f"if(lt(on,{round((float(sh['punch']) - sh['t0']) * FPS)}),1,1.25)"
        chain = (f"{pre}scale={int(W * 1.12)}:{int(fh * 1.12)}:force_original_aspect_ratio=increase:flags=lanczos,crop={int(W * 1.12)}:{int(fh * 1.12)},"
                 f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={n}:s={W}x{fh}:fps={FPS},{GRADE},trim=end_frame={n}")
        _run(["-loop", "1", "-t", f"{dur + .5:.3f}", "-i", sh["path"], "-vf", chain + pad, "-frames:v", str(n), *_enc(out)])
    else:
        _run(["-f", "lavfi", "-i", f"color=c=black:s={W}x{H}:r={FPS}:d={dur + .2:.3f}", "-frames:v", str(n), *_enc(out)])


def build(shots: list[dict], total: float, out: str, tmp: str) -> str:
    """The shots (sorted, gaps filled with black) -> one plate video of exactly `total` seconds."""
    shots = sorted([dict(s) for s in shots if s["t1"] > s["t0"]], key=lambda s: s["t0"])
    seq, t = [], 0.0
    for s in shots:
        s["t0"] = max(s["t0"], t)
        if s["t0"] - t > 1 / FPS:
            seq.append({"t0": t, "t1": s["t0"], "kind": None})
        if s["t1"] - s["t0"] > 1 / FPS:
            seq.append(s)
        t = max(t, s["t1"])
    if total - t > 1 / FPS:
        seq.append({"t0": t, "t1": total, "kind": None})
    # snap cuts to frames so the plate stays in sync
    for s in seq:
        s["t0"], s["t1"] = round(s["t0"] * FPS) / FPS, round(s["t1"] * FPS) / FPS
    paths = []
    for i, s in enumerate(seq):
        if s["t1"] <= s["t0"]:
            continue
        p = os.path.join(tmp, f"seg{i:03d}.mp4")
        try:
            _segment(s, p)
        except Exception as e:
            print(f"[plate] shot {i} failed ({e}); black instead")
            _segment({**s, "kind": None}, p)
        paths.append(p)
    lst = os.path.join(tmp, "plate.txt")
    open(lst, "w").write("".join(f"file '{p}'\n" for p in paths))
    _run(["-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out])
    return out


def cut(plate: str, start: float, dur: float, out: str) -> str:
    """The plate's frames for one render chunk (frame-accurate)."""
    _run(["-ss", f"{start:.4f}", "-i", plate, "-t", f"{dur:.4f}", "-vf", f"fps={FPS}", "-frames:v", str(round(dur * FPS)), *_enc(out)])
    return out


def proxy(plate: str, out: str) -> str:
    """A small copy for the stills (review), same timing."""
    _run(["-i", plate, "-vf", "scale=540:960", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "30", "-pix_fmt", "yuv420p", "-r", str(FPS), out])
    return out


def frames_sheet(path: str, out: str, every: float = 1.0, cols: int = 6, width: int = 320) -> list[float]:
    """A contact sheet of a source clip (for Claude to look at), one frame per `every` seconds; returns the times."""
    from studio_media import probe
    d = probe(path)["duration"]
    times = [round(i * every, 2) for i in range(int(d / every) + 1)][:60]
    _run(["-i", path, "-vf", f"fps=1/{every},scale={width}:-2,drawtext=text='%{{pts\\:hms}}':x=6:y=6:fontcolor=yellow:fontsize=18:box=1:boxcolor=black@0.6,"
          f"tile={cols}x{max(1, (len(times) + cols - 1) // cols)}", "-frames:v", "1", out])
    return times
