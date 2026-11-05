"""Style Studio: the HyperFrames page around a model-written film(K, T, c) function.

Every style shares this page: a 1080x1920 canvas, the style's kit (render_service/studio/kits/<style>.js, a global such
as WB), its fonts, the narration timing, and the film. film() runs once and returns { seek(t, c), cues?, sfx? };
the timeline calls seek for every frame. `cues` (the kit's own sound events, e.g. every marker stroke) and `sfx`
(extra effects keyed to words) are handed to the sound designer through window.__kCues.
"""

import json

W, H = 1080, 1920


def compose(style: dict, code: str, timing: dict, start: float = 0.0, duration: float | None = None,
            probe: bool = False, plate: str | None = None) -> str:
    """style: a studio_styles.STYLES entry. The page is always 1080x1920 (the kits draw in screen pixels and some
    reset the canvas transform). plate: an optional footage video (project-relative path) under the canvas."""
    w, h = style.get("size") or (W, H)          # 1080x1920 reels; long videos set (1920, 1080)
    total = round(timing["end"], 3)
    dur = round(duration if duration is not None else total, 4)
    fonts = "".join(f"@font-face{{font-family:{f['family']};src:url(studio/fonts/{f['file']}) format('woff2');font-weight:{f.get('weight', 400)};font-style:{f.get('style', 'normal')}}}"
                    for f in style.get("fonts", []))
    preload = "".join(f'<span style="position:absolute;left:-999px;font:{f.get("style", "normal")} {f.get("weight", 400)} 20px {f["family"]}">A</span>'
                      for f in style.get("fonts", []))
    # pictures (Collage Documentary): hidden <img> tags the page loads before it renders; the film gets them as T.img[id]
    imgs = "".join(f'<img data-k="{im["id"]}" src="{im["file"]}" alt="">' for im in (timing.get("images") or []))
    imgs_html = f'<div style="position:absolute;left:-99999px;top:0;width:1px;height:1px;overflow:hidden">{imgs}</div>' if imgs else ""
    plate_html = (f'<video id="plate" src="{plate}" muted playsinline data-start="0" data-duration="{total}" '
                  f'style="position:absolute;inset:0;width:{w}px;height:{h}px;object-fit:cover"></video>') if plate else ""
    probe_js = ""
    if probe:
        times = [round(x * 0.5, 2) for x in range(int(total * 2) + 1)]
        probe_js = f"""
  for (const t of {json.dumps(times)}) {{
    try {{ c.setTransform(1, 0, 0, 1, 0, 0); F.seek(t, c); }}
    catch (e) {{ window.__kCues.push({{ t: 0, kind: 'error', msg: 'at ' + t.toFixed(1) + ' s: ' + String((e && e.message) || e).slice(0, 400) }}); break; }}
  }}"""
    return f"""<!doctype html><html><head><meta charset="utf-8">
<style>
{fonts}
html,body{{margin:0;background:#000}}
#root{{width:{w}px;height:{h}px;position:relative;overflow:hidden;background:{style.get('background', '#000')}}}
#film{{position:absolute;inset:0;width:{w}px;height:{h}px}}
</style></head><body>
<div id="root" data-composition-id="studio" data-no-timeline data-start="0" data-duration="{dur}" data-width="{w}" data-height="{h}">
{plate_html}<canvas id="film" width="{w}" height="{h}"></canvas>{preload}{imgs_html}</div>
<script src="lib/anime.umd.min.js"></script><script src="lib/kit.js"></script>
<script src="studio/kits/{style['kit_file']}"></script>
<script>window.TIMING = {json.dumps(timing)};</script>
<script>
{code}
</script>
<script>
(function () {{
  const tl = K.timeline(), OFFSET = {round(start, 4)}, KIT = window.{style['kit_global']};
  window.__kCues = window.__kCues || [];
  const canvas = document.getElementById('film'), c = canvas.getContext('2d');
  if (KIT.setScreen) KIT.setScreen({w}, {h});
  if (KIT.use && window.TIMING.look) KIT.use(window.TIMING.look);
  const T = window.TIMING;
  T.img = {{}};
  for (const el of document.querySelectorAll('img[data-k]')) if (el.naturalWidth) T.img[el.dataset.k] = el;
  T.w = (i, word, n = 1) => {{
    const L = T.lines[i]; if (!L) throw new Error('T.w(' + i + "): there is no line " + i);
    const b = s => String(s).toLowerCase().replace(/[^a-z0-9':.%-]/g, ''); let k = 0;
    for (const x of L.words) if (b(x.w) === b(word) && ++k === n) return x.s;
    for (const x of L.words) if (b(x.w).startsWith(b(word)) && ++k >= n) return x.s;
    return L.start;
  }};
  let F = null;
  try {{
    if (typeof film !== 'function') throw new Error('film(K, T, c) is not defined');
    c.setTransform(1, 0, 0, 1, 0, 0);
    F = film(KIT, T, c);
    if (!F || typeof F.seek !== 'function') throw new Error('film() must return {{ seek(t, c), cues, sfx }}');
    window.__kCues.push({{ t: 0, kind: 'spec', spec: F.sfx || {{}} }});
    if (Array.isArray(F.cues)) window.__kCues.push({{ t: 0, kind: 'foley', events: F.cues.slice(0, 4000) }});
  }} catch (e) {{ window.__kCues.push({{ t: 0, kind: 'error', msg: String((e && e.stack) || e).slice(0, 900) }}); F = null; }}
  {probe_js}
  const draw = t => {{ if (!F) return; c.setTransform(1, 0, 0, 1, 0, 0); c.globalAlpha = 1; F.seek(Math.min(t, {total} - 0.001), c); }};
  let last = -1;   // the timeline calls its hooks on render AND update: draw each time once
  tl._kHooks.push(ms => {{ if (ms === last) return; last = ms; draw(ms / 1000 + OFFSET); }});
  tl.add({{ k: 0 }}, {{ k: 1, duration: {round(dur * 1000)}, ease: 'linear' }}, 0);
  draw(OFFSET);
}})();
</script></body></html>"""
