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

UA = os.environ.get("STUDIO_MEDIA_UA", "AnimaveStudio/1.0 (https://animave.com; support@animave.com)")
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
           "&prop=imageinfo&iiprop=url|size|mime|extmetadata&iiurlwidth=500"
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


PEXELS_KEY = os.environ.get("PEXELS_API_KEY", "")
PIXABAY_KEY = os.environ.get("PIXABAY_API_KEY", "")


def _ia_licence(url: str) -> str:
    u = (url or "").lower()
    if "publicdomain" in u:
        return "Public domain"
    m = re.search(r"creativecommons\.org/licenses/([a-z-]+)/([\d.]+)", u)
    return f"CC {m.group(1).upper()} {m.group(2)}" if m else ""


async def search_archive(q: str, kind: str = "video", n: int = 6) -> list[dict]:
    """Internet Archive: films, newsreels and photos marked public domain or CC BY (licence read from each item)."""
    mt = "movies" if kind == "video" else "image"
    query = f"({q}) AND mediatype:{mt} AND licenseurl:[* TO *]"          # any licence; only PD / CC BY are kept below
    url = ("https://archive.org/advancedsearch.php?q=" + urllib.parse.quote(query)
           + "&fl[]=identifier&fl[]=title&fl[]=licenseurl&fl[]=creator&rows=" + str(n * 5) + "&output=json")
    out = []
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
        r = await _get(c, url)
        if r.status_code != 200:
            return []
        for d in (r.json().get("response") or {}).get("docs") or []:
            lic = _ia_licence(d.get("licenseurl"))
            if not licence_ok(lic):
                continue
            ident = d["identifier"]
            if ident.lower().startswith(("youtube-", "yt-")) or "youtube" in str(d.get("title", "")).lower():
                continue                    # re-uploads of other channels' videos: never used
            try:
                meta = (await _get(c, f"https://archive.org/metadata/{ident}")).json()
            except Exception:
                continue
            files = meta.get("files") or []
            if kind == "video":
                vids = [f for f in files if str(f.get("name", "")).lower().endswith(".mp4") and 0 < int(f.get("size") or 0) < MAX_VIDEO_MB * 1e6]
                vids.sort(key=lambda f: int(f.get("size") or 0))
                pick = next((f for f in vids if "512kb" in f["name"].lower() or "h.264" in str(f.get("format", "")).lower()), vids[0] if vids else None)
            else:
                imgs = [f for f in files if str(f.get("name", "")).lower().endswith((".jpg", ".jpeg", ".png")) and "thumb" not in f["name"].lower()]
                pick = max(imgs, key=lambda f: int(f.get("size") or 0), default=None)
            if not pick:
                continue
            author = re.sub(r"\s+", " ", str(d.get("creator") or "Internet Archive"))[:60] if not isinstance(d.get("creator"), list) else str(d["creator"][0])[:60]
            out.append({"source": "archive", "kind": kind, "title": str(d.get("title") or ident)[:120],
                        "url": f"https://archive.org/download/{ident}/{urllib.parse.quote(pick['name'])}", "thumb": f"https://archive.org/services/img/{ident}",
                        "w": 1280, "h": 720, "page": f"https://archive.org/details/{ident}", "licence": lic, "author": author,
                        "credit": f"{author} · {lic} · Internet Archive", "about": ""})
            if len(out) >= n:
                break
    return out


async def search_pexels(q: str, kind: str = "video", n: int = 6) -> list[dict]:
    """Pexels (free API key): real stock footage and photos, free for commercial use (Pexels licence); credited anyway."""
    if not PEXELS_KEY:
        return []
    base = "https://api.pexels.com/videos/search" if kind == "video" else "https://api.pexels.com/v1/search"
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(base, params={"query": q, "per_page": n, "orientation": "landscape"}, headers={"Authorization": PEXELS_KEY})
    if r.status_code != 200:
        print(f"[media] pexels {r.status_code}"); return []
    out = []
    for it in (r.json().get("videos") if kind == "video" else r.json().get("photos")) or []:
        if kind == "video":
            files = sorted([f for f in it.get("video_files") or [] if (f.get("width") or 0) >= 960 and f.get("file_type") == "video/mp4"], key=lambda f: f.get("width") or 0)
            f = next((f for f in files if (f.get("width") or 0) >= 1280), files[-1] if files else None)
            if not f:
                continue
            url, thumb, who = f["link"], it.get("image"), (it.get("user") or {}).get("name", "Pexels")
        else:
            url, thumb, who = (it.get("src") or {}).get("large2x"), (it.get("src") or {}).get("medium"), it.get("photographer", "Pexels")
        out.append({"source": "pexels", "kind": kind, "title": str(it.get("alt") or it.get("url", "").rstrip("/").rsplit("/", 1)[-1].replace("-", " "))[:120],
                    "url": url, "thumb": thumb, "w": it.get("width"), "h": it.get("height"), "duration": it.get("duration"), "page": it.get("url"),
                    "licence": "Pexels licence", "author": who, "credit": f"{who} · Pexels", "about": ""})
    return out


async def search_pixabay(q: str, kind: str = "video", n: int = 6) -> list[dict]:
    """Pixabay (free API key): real stock footage and photos, free for commercial use (Pixabay content licence)."""
    if not PIXABAY_KEY:
        return []
    base = "https://pixabay.com/api/videos/" if kind == "video" else "https://pixabay.com/api/"
    params = {"key": PIXABAY_KEY, "q": q[:100], "per_page": max(3, n), "safesearch": "true"}
    if kind != "video":
        params["image_type"] = "photo"
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(base, params=params)
    if r.status_code != 200:
        print(f"[media] pixabay {r.status_code}"); return []
    out = []
    for it in r.json().get("hits") or []:
        if kind == "video":
            v = (it.get("videos") or {}).get("medium") or (it.get("videos") or {}).get("large") or {}
            if not v.get("url"):
                continue
            url, thumb, w, h = v["url"], v.get("thumbnail"), v.get("width"), v.get("height")
        else:
            url, thumb, w, h = it.get("largeImageURL"), it.get("webformatURL"), it.get("imageWidth"), it.get("imageHeight")
        who = it.get("user", "Pixabay")
        out.append({"source": "pixabay", "kind": kind, "title": str(it.get("tags") or "")[:120], "url": url, "thumb": thumb, "w": w, "h": h,
                    "duration": it.get("duration"), "page": it.get("pageURL"), "licence": "Pixabay licence", "author": who,
                    "credit": f"{who} · Pixabay", "about": ""})
    return out


async def search(q: str, kind: str = "video", n: int = 4) -> list[dict]:
    """Candidates for one query from every open source at once: the real-event archives first (Internet Archive,
    Wikimedia Commons, NASA), then real stock footage (Pexels, Pixabay: what is named, shown for real). The picker
    chooses the one that shows what is said."""
    fns = (search_archive, search_commons, search_nasa, search_pexels, search_pixabay)
    res = await asyncio.gather(*[f(q, kind, max(2, n // 2 + 1)) for f in fns], return_exceptions=True)
    got = []
    for f, r in zip(fns, res):
        if isinstance(r, Exception):
            print(f"[media] {f.__name__} failed: {r!r}")
        else:
            got += r
    return got[:max(n, 8)]


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
