"""Style Studio footage stage (Caption News): the user's uploads, archive search, Claude's pick by eye, the shot list.

  uploads(urls)            download the user's files, a contact sheet of each (for the writer to see)
  shots(...)               each voice line's media -> candidates -> Claude picks by thumbnail -> files -> shot list
The shot list feeds studio_plate.build(); a copy without paths goes to the film as T.shots (times + credits).
"""

import asyncio
import base64
import io
import os

import httpx

import studio_media as M
import studio_plate as P

PICK_TOOL = {
    "name": "pick_footage",
    "description": "Pick the footage for each search.",
    "input_schema": {"type": "object", "properties": {"picks": {"type": "array", "items": {"type": "object", "properties": {
        "query": {"type": "string"}, "choice": {"type": "integer", "description": "the candidate number, or -1 for none"},
        "why": {"type": "string"}}, "required": ["query", "choice"]}}}, "required": ["picks"]},
}
SPAN_TOOL = {
    "name": "pick_spans",
    "description": "Pick where each clip should start.",
    "input_schema": {"type": "object", "properties": {"spans": {"type": "array", "items": {"type": "object", "properties": {
        "query": {"type": "string"}, "start": {"type": "number", "description": "seconds into the clip"},
        "clean_until": {"type": "number", "description": "seconds into the clip where clean footage ends"}},
        "required": ["query", "start"]}}}, "required": ["spans"]},
}
SPAN_SYSTEM = """Each sheet shows one archive clip, one frame every few seconds with its time in the corner. For each
clip, give the start second of the longest stretch of clean footage of the subject: no title cards, no burned-in
captions or big text, no logos, no presenter talking to camera, no graphics when real footage exists."""
PICK_SYSTEM = """You pick archive footage for a vertical social news reel. For each search you see numbered candidate
thumbnails (from Wikimedia Commons or NASA, all openly licensed). Pick the one that best shows what the line is about.
Reject (choice -1 if all are bad): burned-in titles or big text, logos and watermarks, collages and diagrams when the
line needs real footage, close-ups of identifiable private people, anything off-topic or misleading for the line.
Prefer real footage over graphics, sharp over blurry, wide or medium shots with a clear subject."""


def _jpeg(raw: bytes, w: int = 360) -> str | None:
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(raw)).convert("RGB"); im.thumbnail((w, w)); b = io.BytesIO(); im.save(b, "JPEG", quality=78)
        return base64.b64encode(b.getvalue()).decode()
    except Exception:
        return None


async def uploads(urls: list[str], tmp: str) -> list[dict]:
    out = []
    for i, url in enumerate((urls or [])[:12]):
        ext = os.path.splitext(url.split("?")[0])[1].lower()[:6] or ".bin"
        path = os.path.join(tmp, f"upload{i}{ext}")
        try:
            await M.fetch(url, path, max_mb=400)
        except Exception as e:
            print(f"[footage] upload {i} failed: {e!r}")
            continue
        kind = M.kind_of(path)
        info = M.probe(path) if kind == "video" else {"duration": 0}
        rec = {"i": i, "path": path, "kind": kind, "duration": info.get("duration", 0), "every": 1.0}
        try:
            if kind == "video":
                rec["every"] = max(1.0, round(info["duration"] / 36, 1))
                sheet = os.path.join(tmp, f"upload{i}_sheet.jpg")
                await asyncio.to_thread(P.frames_sheet, path, sheet, rec["every"], 6, 240)
                rec["sheet"] = _jpeg(open(sheet, "rb").read(), 1400)
            else:
                rec["sheet"] = _jpeg(open(path, "rb").read(), 640)
        except Exception as e:
            print(f"[footage] sheet {i} failed: {e!r}")
        if rec.get("sheet"):
            out.append(rec)
    return out


async def shots(job_id: str, claude, lines: list[dict], timing: dict, ups: list[dict], tmp: str) -> list[dict]:
    """Each line's media -> a shot list with files. `claude(system, content, max_tokens, role, tool)` is the pipeline's call."""
    tl = timing["lines"]
    by_up = {u["i"]: u for u in ups}
    queries = []
    for ln in lines:
        m = ln.get("media") or {}
        if m.get("search") and (m["search"], m.get("kind") or "video") not in queries:
            queries.append((m["search"], m.get("kind") or "video"))
    # search the archives, then let Claude look at the thumbnails and choose
    found = {}
    if queries:
        cands = await asyncio.gather(*[M.search(q, k, 4) for q, k in queries])
        content, picks_for = [], {}
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
            for (q, k), cs in zip(queries, cands):
                thumbs = await asyncio.gather(*[M.thumb(c, x) for x in cs])
                ok = [(x, _jpeg(t)) for x, t in zip(cs, thumbs) if t]
                ok = [(x, j) for x, j in ok if j]
                if not ok:
                    continue
                picks_for[q] = [x for x, _ in ok]
                content.append({"type": "text", "text": f"SEARCH: {q} ({k})"})
                for n, (x, j) in enumerate(ok):
                    content.append({"type": "text", "text": f"#{n}: {x['title'][:80]} — {x.get('about', '')[:120]}"})
                    content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": j}})
        if content:
            try:
                res = await claude(PICK_SYSTEM, content, 2000, "footage", PICK_TOOL)
                for pk in res.get("picks") or []:
                    cs = picks_for.get(pk.get("query"))
                    ch = int(pk.get("choice", -1))
                    if cs and 0 <= ch < len(cs):
                        found[pk["query"]] = cs[ch]
            except Exception as e:
                print(f"[footage] pick failed: {e!r}")
                for q, cs in picks_for.items():
                    found.setdefault(q, cs[0])
        # download the picks
        for n, (q, cand) in enumerate(list(found.items())):
            ext = ".mp4" if cand["kind"] == "video" else os.path.splitext(cand["url"].split("?")[0])[1][:5] or ".jpg"
            path = os.path.join(tmp, f"arch{n}{ext}")
            try:
                await M.fetch(cand["url"], path, M.MAX_VIDEO_MB if cand["kind"] == "video" else M.MAX_IMAGE_MB)
                cand["path"] = path
                if cand["kind"] == "video":
                    cand["duration"] = M.probe(path)["duration"]
            except Exception as e:
                print(f"[footage] fetch failed for {q}: {e!r}")
                found.pop(q, None)
    # where to start in each chosen video (avoid title cards and burned-in text inside the clip)
    vids = [(q, f) for q, f in found.items() if f["kind"] == "video" and f.get("path") and (f.get("duration") or 0) > 4]
    if vids:
        content = []
        for n, (q, f) in enumerate(vids):
            try:
                every = max(1.0, round(f["duration"] / 18, 1))
                sheet = os.path.join(tmp, f"arch_sheet{n}.jpg")
                await asyncio.to_thread(P.frames_sheet, f["path"], sheet, every, 6, 240)
                content += [{"type": "text", "text": f"CLIP for '{q}' ({f['duration']:.0f} s, a frame every {every:g} s)"},
                            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": _jpeg(open(sheet, "rb").read(), 1400)}}]
            except Exception as e:
                print(f"[footage] sheet failed for {q}: {e!r}")
        if content:
            try:
                res = await claude(SPAN_SYSTEM, content, 1500, "footage", SPAN_TOOL)
                for sp in res.get("spans") or []:
                    if sp.get("query") in found:
                        found[sp["query"]]["start"] = max(0.0, float(sp.get("start") or 0))
                        if sp.get("clean_until"):
                            found[sp["query"]]["clean_until"] = float(sp["clean_until"])
            except Exception as e:
                print(f"[footage] spans failed: {e!r}")
    # the shot list: one shot per line (from its start to the next line's start), same media merged
    out, used = [], {}
    for i, ln in enumerate(lines):
        m = ln.get("media") or {}
        t0 = 0.0 if i == 0 else tl[i]["start"] - 0.05
        t1 = timing["end"] if i == len(lines) - 1 else tl[i + 1]["start"] - 0.05
        src = None
        if m.get("upload") is not None and int(m["upload"]) in by_up:
            u = by_up[int(m["upload"])]
            src = {"path": u["path"], "kind": u["kind"], "duration": u.get("duration", 0), "credit": "", "key": f"u{u['i']}",
                   "at": m.get("at")}
        elif m.get("search") and m["search"] in found:
            f = found[m["search"]]
            src = {"path": f["path"], "kind": f["kind"], "duration": f.get("duration", 0), "credit": f["credit"], "key": m["search"], "start": f.get("start"), "clean_until": f.get("clean_until"),
                   "page": f.get("page"), "licence": f.get("licence"), "title": f.get("title")}
        elif m.get("card") or not m:
            src = {"kind": None, "credit": "", "key": "card"}
        if src is None:                                # nothing found: keep the previous picture running
            src = dict(out[-1]["_src"]) if out else {"kind": None, "credit": "", "key": "card"}
        if out and out[-1]["_src"].get("key") == src.get("key") and src.get("kind") != "video":
            out[-1]["t1"] = t1
            continue
        sh = {"t0": t0, "t1": t1, "kind": src.get("kind"), "path": src.get("path"), "credit": src.get("credit", ""), "_src": src}
        if src.get("kind") == "video":
            d = src.get("duration") or 0
            first = src["start"] if src.get("start") is not None else min(d * .15, 4.0)
            start = float(src["at"]) if src.get("at") is not None else used.get(src["key"], first)
            cu = src.get("clean_until")
            if cu and start + (t1 - t0) > cu and src.get("at") is None:
                start = first if first + (t1 - t0) <= cu + 1 else start      # reuse the clean stretch rather than run past it
            if d and start + (t1 - t0) > d:
                start = max(0.0, d - (t1 - t0) - .1)
            sh["src"] = start
            used[src["key"]] = start + (t1 - t0)
        out.append(sh)
    return out


def public(shots_: list[dict]) -> list[dict]:
    """What the film sees: times, kind and credit of each shot."""
    return [{"t0": round(s["t0"], 3), "t1": round(s["t1"], 3), "kind": s.get("kind") or "card", "credit": s.get("credit", "")} for s in shots_]


def sources(shots_: list[dict]) -> list[dict]:
    seen, out = set(), []
    for s in shots_:
        src = s.get("_src") or {}
        if src.get("page") and src["page"] not in seen:
            seen.add(src["page"]); out.append({"title": src.get("title"), "page": src["page"], "licence": src.get("licence"), "credit": src.get("credit")})
    return out
