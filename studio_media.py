"""Style Studio footage: the user's own uploads first, otherwise open-licensed archive material.

Sources (each file's licence is read from its own record; anything unclear is skipped):
  - Wikimedia Commons: CC0, public domain marks and CC BY (any version). Not used: BY-SA, BY-ND, NC, unclear.
  - NASA Image and Video Library (images.nasa.gov): NASA media is generally not copyrighted; credited "NASA".
Every used file carries a credit ("Author · Licence") that the film shows on screen, and the job keeps the list.
"""

import asyncio
import json
import os
import re
import subprocess
import urllib.parse

import httpx

UA = os.environ.get("STUDIO_MEDIA_UA", "AnimaveStudio/1.0 (https://animave.app; media@animave.app)")
MAX_VIDEO_MB = 120
MAX_IMAGE_MB = 25


def _strip(s: str) -> str:
    return re.sub(r"<[^>]+>", "", str(s or "")).strip()


def licence_ok(lic: str) -> bool:
    """CC0, public domain or CC BY (any version); never share-alike, no-derivatives or non-commercial."""
    l = (lic or "").strip().lower()
    toks = [t for t in re.split(r"[\s\-_/,()]+", l) if t]
    if not toks or any(t in ("sa", "nd", "nc", "unknown", "fair", "copyrighted") for t in toks):
        return False
    if "cc0" in toks or "zero" in toks or "public domain" in l or toks[0] in ("pd", "pdm") or l.startswith("pd-"):
        return True
    return toks[0] == "cc" and "by" in toks


async def _get(c: httpx.AsyncClient, url: str, **kw):
    for attempt in range(4):
        r = await c.get(url, headers={"User-Agent": UA}, **kw)
        if r.status_code != 429:
            return r
        await asyncio.sleep(2 * (attempt + 1))
    return r


async def search_commons(q: str, kind: str = "video", n: int = 6) -> list[dict]:
    ft = "video" if kind == "video" else "bitmap"
    url = ("https://commons.wikimedia.org/w/api.php?action=query&format=json&generator=search&gsrnamespace=6"
           f"&gsrlimit={n * 3}&gsrsearch={urllib.parse.quote(f'filetype:{ft} {q}')}"
           "&prop=imageinfo&iiprop=url|size|mime|extmetadata&iiurlwidth=640"
           "&iiextmetadatafilter=LicenseShortName|Artist|Credit|ImageDescription|DateTimeOriginal")
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
        r = await _get(c, url)
    if r.status_code != 200:
        print(f"[media] commons search failed {r.status_code}")
        return []
    pages = (r.json().get("query") or {}).get("pages") or {}
    out = []
    for p in sorted(pages.values(), key=lambda p: p.get("index", 0)):
        ii = (p.get("imageinfo") or [{}])[0]
        md = ii.get("extmetadata") or {}
        lic = _strip((md.get("LicenseShortName") or {}).get("value"))
        if not licence_ok(lic):
            continue
        size_mb = (ii.get("size") or 0) / 1e6
        if size_mb > (MAX_VIDEO_MB if kind == "video" else MAX_IMAGE_MB):
            continue
        author = _strip((md.get("Artist") or {}).get("value")) or "Wikimedia Commons"
        author = re.sub(r"\s+", " ", author)[:60]
        out.append({
            "source": "commons", "kind": kind, "title": p.get("title", "")[5:], "url": ii.get("url"),
            "thumb": ii.get("thumburl"), "w": ii.get("width"), "h": ii.get("height"), "duration": ii.get("duration"),
            "page": ii.get("descriptionurl"), "licence": lic, "author": author,
            "credit": f"{author} · {lic}" if not lic.lower().startswith(("public domain", "cc0", "pd")) else f"{author} · {lic}",
            "about": _strip((md.get("ImageDescription") or {}).get("value"))[:200],
        })
        if len(out) >= n:
            break
    return out


async def search_nasa(q: str, kind: str = "video", n: int = 6) -> list[dict]:
    mt = "video" if kind == "video" else "image"
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
        r = await _get(c, f"https://images-api.nasa.gov/search?q={urllib.parse.quote(q)}&media_type={mt}")
        if r.status_code != 200:
            return []
        items = (r.json().get("collection") or {}).get("items") or []
        out = []
        for it in items[: n * 2]:
            d = (it.get("data") or [{}])[0]
            thumb = next((l.get("href") for l in it.get("links") or [] if l.get("rel") == "preview"), None)
            try:
                files = (await _get(c, it["href"])).json()
            except Exception:
                continue
            if kind == "video":
                url = next((f for f in files if f.endswith("~medium.mp4")), None) or next((f for f in files if f.endswith("~mobile.mp4")), None) \
                    or next((f for f in files if f.endswith(".mp4") and "~orig" not in f), None)
            else:
                url = next((f for f in files if f.endswith("~large.jpg")), None) or next((f for f in files if f.endswith("~orig.jpg")), None)
            if not url or not thumb:
                continue
            out.append({"source": "nasa", "kind": kind, "title": d.get("title", ""), "url": url.replace("http://", "https://"),
                        "thumb": thumb.replace("http://", "https://"), "page": f"https://images.nasa.gov/details/{d.get('nasa_id')}",
                        "licence": "NASA (not copyrighted)", "author": f"NASA {d.get('center', '')}".strip(),
                        "credit": f"NASA {d.get('center', '')}".strip(), "about": (d.get("description") or "")[:200]})
            if len(out) >= n:
                break
    return out


async def search(q: str, kind: str = "video", n: int = 4) -> list[dict]:
    """Candidates for one query: Commons first, NASA to fill (space, Earth, weather, science topics)."""
    got = []
    for f in (search_commons, search_nasa):
        try:
            got += await f(q, kind, n)
        except Exception as e:
            print(f"[media] {f.__name__} failed: {e!r}")
        if len(got) >= n:
            break
    return got[:n]


async def thumb(c: httpx.AsyncClient, cand: dict) -> bytes | None:
    if not cand.get("thumb"):
        return None
    try:
        r = await _get(c, cand["thumb"])
        return r.content if r.status_code == 200 and len(r.content) > 500 else None
    except Exception:
        return None


async def fetch(url: str, dest: str, max_mb: float = MAX_VIDEO_MB) -> str:
    async with httpx.AsyncClient(timeout=300, follow_redirects=True) as c:
        async with c.stream("GET", url, headers={"User-Agent": UA}) as r:
            r.raise_for_status()
            n = 0
            with open(dest, "wb") as f:
                async for b in r.aiter_bytes(1 << 16):
                    n += len(b)
                    if n > max_mb * 1e6:
                        raise ValueError("file too large")
                    f.write(b)
    return dest


def probe(path: str) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,codec_type:format=duration",
                        "-of", "json", path], capture_output=True, text=True)
    try:
        d = json.loads(r.stdout)
        s = (d.get("streams") or [{}])[0]
        dur = float((d.get("format") or {}).get("duration") or 0)
        return {"w": int(s.get("width") or 0), "h": int(s.get("height") or 0), "duration": dur}
    except Exception:
        return {"w": 0, "h": 0, "duration": 0}


IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff")


def kind_of(path: str) -> str:
    p = path.lower().split("?")[0]
    if p.endswith(IMAGE_EXT):
        return "image"
    info = probe(path)
    return "image" if info["duration"] <= 0.05 else "video"
