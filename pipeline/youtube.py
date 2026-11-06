"""One long YouTube video, 16:9, in a few minutes rather than hours: no per-frame page render.
A browser draws the frame, the subtitles and the thumbnails once (pipeline/yt_frame.html); ffmpeg lays them over the
source with the hardware encoder. The speech is never cut.

Usage: python youtube.py <job_dir> <clip_id>   (same PROGRESS / OUTPUT lines as render_clip.py)
Writes beside the video: <name>.txt (titles, description, chapters, tags), <name>.srt, <name> thumbnail 1-3.jpg
"""
import base64
import json
import os
import re
import subprocess
import sys
import threading

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import plat
from plat import AAC, BROWSER, CLAUDE, FONTS, ROOT
FPS, W, H = 30, 1920, 1080
# where the subtitle strip sits: x, y, width, height, font size; band floats a pill over the video
STRIP = {"band": dict(x=120, y=710, w=1680, h=196, size=46, pad=30),
         "board": dict(x=36, y=843, w=1392, h=201, size=50, pad=40),
         "sound": dict(x=200, y=772, w=1520, h=196, size=48, pad=30)}
WAVE_X, WAVE_Y, WAVE_W, WAVE_H, BARS = 400, 600, 1120, 152, 72
LOOK_KEYS = ("ytSubFont", "ytSubSize", "ytSubColour", "ytSubBg", "ytSubBox", "ytSubY", "ytVerseColour", "ytTitleFont", "ytTitleSize", "ytTitleColour",
             "ytNameFont", "ytNameSize", "ytNameColour", "ytWave", "ytWaveColour", "ytEnglish", "ytEnColour")


def progress(p, label):
    print(f"PROGRESS {int(p)} {label}", flush=True)


def page(state, dest=None, size=(W, H), dump=False):
    """Draw yt_frame.html in the headless browser: a screenshot, or the page's text for mode=subs."""
    html = open(os.path.join(ROOT, "pipeline", "yt_frame.html")).read() \
        .replace("__FONTS__", plat.url(FONTS)).replace("__LOGO__", plat.url(os.path.join(ROOT, "pipeline", "logo.png")))
    # the state goes inside the page: a Windows command line is too short to carry a batch of subtitles
    html = html.replace('<div id="s"></div>', "<script>window.QS=" + json.dumps(state, ensure_ascii=False).replace("</", "<\\/") + '</script><div id="s"></div>', 1)
    work = os.path.join(OUT, "yt_page.html"); open(work, "w").write(html)
    url = plat.url(work)
    cmd = [BROWSER, "--headless", "--disable-gpu", "--hide-scrollbars", "--allow-file-access-from-files", "--force-device-scale-factor=1",
           "--default-background-color=00000000", f"--window-size={size[0]},{size[1]}", "--virtual-time-budget=20000"]
    if dump:
        r = subprocess.run(cmd + ["--dump-dom", url], capture_output=True, text=True, timeout=600)
        m = re.search(r'<pre id="out">(.*?)</pre>', r.stdout, re.S)
        return json.loads(m.group(1)) if m and m.group(1) else []
    plat.screenshot(url, dest, *size)
    if not os.path.exists(dest):
        raise RuntimeError("the browser did not draw " + os.path.basename(dest))


def hms(t):
    return f"{int(t // 3600):02d}:{int(t % 3600 // 60):02d}:{int(t % 60):02d},{int(t * 1000 % 1000):03d}"


def chunks(segs, a, b, reading):
    """Subtitles from the transcript: short lines on word times, verses in their Qur'an spelling. Times start at 0 = clip start."""
    import quran
    out = []
    for s in segs:
        if s["end"] <= a or s["start"] >= b or not s["text"].strip():
            continue
        toks = s["text"].split()
        ws = s.get("words") or []
        # edited lines no longer match the word times: spread them evenly over the line
        times = [w["start"] for w in ws] if len(ws) == len(toks) else [s["start"] + (s["end"] - s["start"]) * i / len(toks) for i in range(len(toks))]
        q = s["quran"] if "quran" in s else quran.find(s["text"])
        if reading == "warsh" and q and q.get("text") and not q.get("warsh"):
            import warsh
            q = dict(q, warsh=warsh.lookup(q))
        vt = q and (q.get("warsh") if reading == "warsh" else q.get("text"))
        parts = []  # (first token, last token + 1, verse text or None)
        if vt:
            if q["a"] > 0: parts.append((0, q["a"], None))
            parts.append((q["a"], q["b"] + 1, vt))
            if q["b"] + 1 < len(toks): parts.append((q["b"] + 1, len(toks), None))
        else:
            parts.append((0, len(toks), None))
        for i, j, verse in parts:
            words = (verse or " ".join(toks[i:j])).split()
            n = max(1, -(-len(words) // 10))  # no more than about ten words a line
            t0 = times[i]; t1 = times[j] if j < len(toks) else s["end"]
            for k in range(n):
                w = words[len(words) * k // n: len(words) * (k + 1) // n]
                out.append({"t": ("﴿" if verse and k == 0 else "") + " ".join(w) + ("﴾" if verse and k == n - 1 else ""), "q": bool(verse),
                            "s": t0 + (t1 - t0) * k / n, "e": t0 + (t1 - t0) * (k + 1) / n})
    out = [dict(c, s=max(c["s"] - a, 0), e=min(c["e"], b) - a) for c in out if c["e"] > a and c["s"] < b]
    for c, nx in zip(out, out[1:]):  # hold a line through a short pause rather than flicker; never overlap the next one
        c["e"] = nx["s"] if nx["s"] - c["e"] < .5 else min(c["e"] + .3, nx["s"])
    return out


def english(caps):
    """English for every subtitle, by Claude, in order so it reads as one talk. Kept in yt_en.json, so a re-render costs nothing."""
    p = os.path.join(OUT, "yt_en.json")
    done = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    todo = [c for c in caps if c["t"] not in done]
    for i in range(0, len(todo), 60):
        part = todo[i:i + 60]
        progress(8 + 6 * i / len(todo), "Translating")
        prompt = ("Translate these consecutive subtitle lines from an Islamic lesson into English. They are pieces of one talk: read them all, then translate each "
                  "faithfully and naturally. Plain, dignified English, no additions. Say «Allah» and «the Prophet ﷺ». Lines between ﴿ ﴾ are Qur'an: use the Sahih International wording. "
                  "The speech may be spoken Arabic: «ما» before a past verb is usually a negation; never turn a negative into a positive. Keep each line short.\n"
                  'Reply with JSON only: {"<number>": "English"}\n\n' + "\n".join(f"{k}: {c['t']}" for k, c in enumerate(part)))
        r = subprocess.run([CLAUDE, "-p", "--tools", "", "--output-format", "text"], input=prompt, capture_output=True, text=True, cwd=OUT, timeout=600)
        try:
            got = json.loads(re.search(r"\{.*\}", r.stdout, re.S).group(0))
            done.update({c["t"]: got[str(k)].strip() for k, c in enumerate(part) if str(k) in got})
            json.dump(done, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        except Exception as e:
            print("translation failed: " + str(e)[:160], flush=True)
    for c in caps:
        c["en"] = done.get(c["t"], "")


def draw_subs(caps, layout, theme, work, length, reading, look):
    """Every subtitle as a PNG, and a concat list that shows each for its time (this ffmpeg has no text filters)."""
    st = STRIP[layout]; d = os.path.join(work, "subs"); os.makedirs(d, exist_ok=True)
    box = look.get("ytSubBox") or "auto"
    bg = look.get("ytSubBg") or {"forest": "#0E3327", "navy": "#0F1C38", "maroon": "#3A1017"}.get(theme, "#131311")
    pill = bg + "D9" if box == "box" or (box == "auto" and layout == "band") else None
    args = {"mode": "subs", "layout": layout, "theme": theme, "w": st["w"], "h": st["h"], "size": st["size"], "pad": st["pad"], "pill": pill, "reading": reading,
            "ink": look.get("ytSubColour") or ("#FFFFFF" if layout == "band" else None), "style": look, "shadow": not pill and layout == "band"}
    pngs = []
    for i in range(0, len(caps), 60):  # a hash can only carry so much text
        pngs += page({**args, "items": [{"t": c["t"], "q": c["q"], "en": c.get("en", "")} for c in caps[i:i + 60]]}, dump=True)
        progress(8 + 10 * min(i + 60, len(caps)) / max(1, len(caps)), "Drawing the subtitles")
    if len(pngs) != len(caps):
        raise RuntimeError(f"subtitles: drew {len(pngs)} of {len(caps)}")
    blank = os.path.join(d, "blank.png")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=black@0:s={st['w']}x{st['h']},format=rgba", "-frames:v", "1", blank], check=True)
    lines, t = ["ffconcat version 1.0"], 0.0  # names relative to this list: no drive letters or backslashes to escape
    for i, (c, b) in enumerate(zip(caps, pngs)):
        f = os.path.join(d, f"{i:05d}.png"); open(f, "wb").write(base64.b64decode(b))
        if c["s"] > t + .01:
            lines += ["file 'blank.png'", f"duration {c['s'] - t:.3f}"]
        lines += [f"file '{i:05d}.png'", f"duration {max(c['e'] - c['s'], .2):.3f}"]; t = c["s"] + max(c["e"] - c["s"], .2)
    lines += ["file 'blank.png'", f"duration {max(length - t, .1) + 1:.3f}"]
    p = os.path.join(d, "subs.ffconcat"); open(p, "w").write("\n".join(lines) + "\n")
    return p


def wave_frames(src, start, length, colour, stdin, kind="bars"):
    """The voice as rounded bars that spread from the centre, written as raw frames for ffmpeg to lay on the picture."""
    sr = 8000
    r = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", str(start), "-t", str(length), "-i", src, "-vn", "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
                         stdout=subprocess.PIPE)
    pcm = np.frombuffer(r.stdout.read(), dtype=np.float32); r.wait()
    hop = sr // FPS; n = len(pcm) // hop
    env = np.sqrt((pcm[:n * hop].reshape(n, hop) ** 2).mean(1)) if n else np.zeros(1)
    env = np.clip(env / (np.percentile(env, 98) + 1e-6), 0, 1) ** .7
    half = BARS // 2; bw, gap = {"thin": (3, 12), "dots": (13, 2)}.get(kind, (9, 6)); ww, hh = BARS * (bw + gap), WAVE_H - 36
    levels = 24; rgb = [int(colour[i:i + 2], 16) for i in (1, 3, 5)]
    sprites = []
    for lv in range(levels + 1):  # a bar at each height, with round ends
        h = bw if kind == "dots" else max(bw, int(hh * lv / levels)); yy, xx = np.mgrid[0:h, 0:bw]
        rad = bw / 2 * (.3 + .7 * lv / levels) if kind == "dots" else bw / 2  # dots grow with the voice instead of stretching
        cy = np.clip(yy + .5, rad, h - rad) if kind != "dots" else bw / 2
        a = np.clip(rad + .5 - np.hypot(xx + .5 - bw / 2, yy + .5 - cy), 0, 1)
        sp = np.zeros((h, bw, 4), np.uint8); sp[..., :3] = rgb; sp[..., 3] = (a * 255).astype(np.uint8); sprites.append(sp)
    pad = np.concatenate([np.zeros(half * 2), env])
    for f in range(int(length * FPS)):
        fr = np.zeros((hh, ww, 4), np.uint8); i = min(f, len(env) - 1) + half * 2
        for k in range(half):  # k bars from the centre = the sound a moment ago
            lv = int(pad[i - k * 2] * (1 - .55 * k / half) * levels); sp = sprites[lv]; y = (hh - sp.shape[0]) // 2
            for x in ((half + k) * (bw + gap), (half - 1 - k) * (bw + gap)):
                fr[y:y + sp.shape[0], x:x + bw] = sp
        try:
            stdin.write(fr.tobytes())
        except BrokenPipeError:
            return
    stdin.close()


def encode(cmd, length, a=18, b=94):
    p = subprocess.Popen(cmd + ["-progress", "pipe:1", "-nostats"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace")
    err = []
    threading.Thread(target=lambda: err.extend(p.stderr.readlines()[-6:]), daemon=True).start()
    last = -1
    for line in p.stdout:
        if line.startswith("out_time_us="):
            try:
                pc = a + (b - a) * int(line[12:]) / 1e6 / length
            except ValueError:
                continue
            if int(pc) != last:
                last = int(pc); progress(min(pc, b), "Building the video")
    if p.wait() != 0:
        raise RuntimeError("ffmpeg: " + "".join(err)[-300:])


def best_frame(src, start, length, work):
    """A sharp, front-facing moment from the real footage for the thumbnails. Returns (jpg, face box) or (None, None)."""
    face = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    eyes = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_eye.xml")
    cap = cv2.VideoCapture(src); best = (0, None, None)
    for i in range(60):
        cap.set(cv2.CAP_PROP_POS_MSEC, (start + length * (i + .5) / 60) * 1000)
        ok, im = cap.read()
        if not ok:
            continue
        g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY); h, w = g.shape
        fs = face.detectMultiScale(g, 1.15, 6, minSize=(w // 14, w // 14))
        for x, y, fw, fh in fs:
            if y + fh > h * .72:  # low in the frame: usually a listener or a burned-in badge
                continue
            roi = g[y:y + fh, x:x + fw]
            sharp = cv2.Laplacian(roi, cv2.CV_64F).var()
            open_eyes = len(eyes.detectMultiScale(roi[:fh // 2 + 8], 1.1, 6))
            score = fw * (1 + min(sharp, 400) / 200) * (1.6 if open_eyes >= 2 else 1)
            if score > best[0]:
                best = (score, im.copy(), (int(x), int(y), int(fw), int(fh)))
    cap.release()
    if best[1] is None:
        return None, None
    p = os.path.join(work, "thumb-frame.jpg")  # imencode: cv2.imwrite can't handle Arabic in a Windows path
    open(p, "wb").write(cv2.imencode(".jpg", best[1], [cv2.IMWRITE_JPEG_QUALITY, 95])[1].tobytes())
    return p, best[2] + best[1].shape[1::-1]


def thumbnails(base, frame, box, lines, name, theme, work):
    """Three choices at 1280x720. Face placed by its box, so it's the same size whatever the source."""
    made = []
    for n, v in enumerate("ABC", 1):
        st = {"mode": "thumb", "variant": v, "theme": theme, "lines": lines, "name": name, "hi": 0}
        if not frame:  # no face to show: the words on three grounds to choose from
            st.update(variant="C", theme=[theme, "paper" if theme != "paper" else "ink", "maroon" if theme != "maroon" else "navy"][n - 1])
        if frame:
            x, y, fw, fh, iw, ih = box
            k = {"A": 400, "B": 370, "C": 300}[v] / fh  # face height on the thumbnail
            k = max(k, 1280 / iw, 720 / ih)
            cx = {"A": 300, "B": 300, "C": 640}[v]; cy = 300
            st.update(photo=plat.url(frame), bw=round(iw * k),
                      bx=round(min(0, max(1280 - iw * k, cx - (x + fw / 2) * k))), by=round(min(0, max(720 - ih * k, cy - (y + fh / 2) * k))))
        png = os.path.join(work, f"thumb{v}.png")
        page(st, png, (1280, 720))
        dest = f"{base} thumbnail {n}.jpg"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", png, "-q:v", "2", dest], check=True)
        made.append(dest)
    return made


def kit(said, title, name, a, b):
    """Claude writes the packaging once: thumbnail words, titles, description, chapters. Faithful to what is said."""
    stamp = lambda t: f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{int(t % 60):02d}"
    lines = [f"[{stamp(max(s['start'] - a, 0))}] {s['text']}" for s in said]
    while len("\n".join(lines)) > 60000:
        lines = lines[::2]
    prompt = ("You package a long Islamic lesson for " + plat.channel() + " on YouTube. Everything must be faithful to what is said: "
              "no exaggeration, no fear-mongering, no promise the lesson does not keep, never invent a hadith, verse or claim.\n"
              "Reply with JSON only:\n"
              '{"onscreen":"the lesson topic in 3 to 6 Arabic words, without the speaker\'s name",\n'
              ' "thumb":["2 or 3 short Arabic lines for the thumbnail, at most 4 words each, 7 words in all; the first line is the hook"],\n'
              ' "titles":["3 Arabic video titles, each under 70 characters, topic first and the speaker\'s name last"],\n'
              ' "description":"Arabic, 3 to 5 sentences: what the viewer will learn, from what is actually said",\n'
              ' "chapters":[["0:00:00","Arabic chapter name"], ...]  the first at 0:00:00, one per real change of topic, at least 10 minutes apart on a long lesson and 3 to 12 in all; none if under 3 minutes,\n'
              ' "hashtags":["exactly 3, Arabic, starting with #"],\n'
              ' "tags":["10 to 15 Arabic and English search phrases"],\n'
              ' "pinned":"one short Arabic question that invites real answers"}\n\n'
              f"Speaker: {name}\nTitle given (may be empty): {title}\nTranscript:\n" + "\n".join(lines))
    r = subprocess.run([CLAUDE, "-p", "--tools", "", "--output-format", "text"], input=prompt, capture_output=True, text=True, cwd=OUT, timeout=600)
    return json.loads(re.search(r"\{.*\}", r.stdout, re.S).group(0))


def post_text(k, name, handle):
    ch = "\n".join(f"{re.sub(r'^0:', '', c[0])} {c[1]}" for c in k.get("chapters") or [])
    return ("العناوين المقترحة:\n" + "\n".join("• " + t for t in k.get("titles", [])) + "\n\n"
            "الوصف:\n" + k.get("description", "") + (f"\n\n— {name}" if name else "") + (f"\n\nالفصول:\n{ch}" if ch else "")
            + "\n\n" + " ".join(k.get("hashtags", [])) + "\n\n"
            "الكلمات المفتاحية:\n" + ", ".join(k.get("tags", [])) + "\n\n"
            "تعليق مثبت:\n" + k.get("pinned", "") + "\n")


def main():
    global OUT
    job_dir, clip_id = os.path.abspath(sys.argv[1]), int(sys.argv[2])
    sys.path.insert(0, os.path.join(ROOT, "pipeline"))
    S = json.load(open(os.path.join(job_dir, "settings.json")))
    META = json.load(open(os.path.join(job_dir, "meta.json")))
    clip = next(c for c in json.load(open(os.path.join(job_dir, "clips.json")))["clips"] if c["id"] == clip_id)
    tp = next(os.path.join(job_dir, f) for f in ("transcript_edited.json", "transcript.json") if os.path.exists(os.path.join(job_dir, f)))
    segs = json.load(open(tp))["segments"]
    src = next(os.path.join(job_dir, f) for f in sorted(os.listdir(job_dir)) if f.startswith("source."))
    OUT = os.path.join(job_dir, "clips", f"clip{clip_id}"); os.makedirs(OUT, exist_ok=True)
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", src], capture_output=True, text=True).stdout)
    # a whole-video clip runs from the first to the last word: give it the source's own edges back, unless it was trimmed by hand
    whole = clip.get("reason") == "Whole video" and abs(clip["start"] - segs[0]["start"]) < .1 and abs(clip["end"] - segs[-1]["end"]) < .1
    a, b = (0.0, dur) if whole else (clip["start"], clip["end"])
    length = b - a
    layout = "sound" if META.get("audioOnly") else S.get("ytLayout", "band")
    theme = S.get("ytTheme", "ink")
    name = "" if clip.get("hideName") else clip.get("speaker") or S.get("speaker", "")
    title = (clip.get("title") or S.get("titleText", "")).replace("\n", " ").strip()
    handle = S.get("ytHandle", "")

    progress(2, "Writing the title and chapters")
    said = [s for s in segs if s["end"] > a and s["start"] < b]
    kp = os.path.join(OUT, "yt.json")
    k = json.load(open(kp)) if os.path.exists(kp) else {}
    if not k:
        try:
            k = kit(said, title, name, a, b); json.dump(k, open(kp, "w"), ensure_ascii=False, indent=1)
        except Exception as e:
            print("packaging failed: " + str(e)[:200], flush=True)
    title = title or k.get("onscreen", "").strip() or os.path.splitext(META["name"])[0]

    progress(6, "Drawing the frame")
    frame = os.path.join(OUT, "yt_frame.png")
    look = {k: S[k] for k in LOOK_KEYS if S.get(k) not in (None, "")}
    page({"mode": "frame", "layout": layout, "theme": theme, "title": title, "name": name, "kicker": S.get("ytKicker", ""), "handle": handle, "style": look}, frame)
    caps = chunks(segs, a, b, S.get("quranReading", "hafs")) if S.get("ytSubs", True) else []
    if caps and S.get("ytEnglish"):
        english(caps)
    subs = draw_subs(caps, layout, theme, OUT, length, S.get("quranReading", "hafs"), look) if caps else None

    lesson = os.path.splitext(META["name"])[0]
    dest_dir = os.environ.get("QITAF_OUT") or os.path.join(plat.CLIPS, plat.safe_name(lesson))
    os.makedirs(dest_dir, exist_ok=True)
    safe = plat.safe_name(title[:60])
    dest = os.path.join(dest_dir, f"{clip_id:02d} - {safe} (YouTube).mp4")
    tmp = os.path.join(OUT, "youtube.mp4")

    cut = ["-ss", f"{a:.3f}", "-t", f"{length:.3f}"]
    out = ["-map", "[o]", "-map", "0:a:0"] + plat.video_args("9M" if layout != "sound" else "5M") + [
           "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", AAC, "-b:a", "192k", "-t", f"{length:.3f}", "-movflags", "+faststart", tmp]
    sub_in = ["-f", "concat", "-safe", "0", "-i", subs] if subs else []
    st = dict(STRIP[layout]); base = ["ffmpeg", "-v", "error", "-y"]
    if layout == "sound":
        wv = S.get("ytWaveColour") or {"paper": "#F4EFE4"}.get(theme, "#E8C15A")
        wk = S.get("ytWave") or "bars"
        if wk == "off":
            n = 2
            g = "[1:v]format=rgba[a]"
            cmd = base + cut + ["-i", src, "-loop", "1", "-framerate", str(FPS), "-i", frame] + sub_in
        else:
            n = 3
            g = f"[1:v]format=rgba[bg];[2:v]format=rgba[w];[bg][w]overlay={WAVE_X + (WAVE_W - BARS * 15) // 2}:{WAVE_Y + 18}:shortest=1[a]"
            cmd = base + cut + ["-i", src, "-loop", "1", "-framerate", str(FPS), "-i", frame,
                                "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{BARS * 15}x{WAVE_H - 36}", "-r", str(FPS), "-i", "pipe:0"] + sub_in
    else:
        n = 2
        # zoom crops away what the source burned in around the picture (its own border, logos, title strip)
        z = 1 + float(S.get("ytZoom", 0)) / 100
        mx, my = (.5 + float(S.get(k, 0)) / 200 for k in ("ytX", "ytY"))  # -100…100 = to one edge of the spare picture or the other
        zc = f"crop=iw/{z}:ih/{z}:(iw-iw/{z})*{mx}:(ih-ih/{z})*{my}," if z > 1 else ""
        if layout == "board":
            g = (f"[0:v]{zc}scale=1392:783:force_original_aspect_ratio=increase,crop=1392:783,setsar=1,fps={FPS},pad={W}:{H}:36:36[v];"
                 f"[1:v]format=rgba[f];[v][f]overlay=shortest=1[a]")
        else:
            g = f"[0:v]{zc}scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={FPS}[v];[1:v]format=rgba[f];[v][f]overlay=shortest=1[a]"
        cmd = base + cut + ["-i", src, "-loop", "1", "-framerate", str(FPS), "-i", frame] + sub_in
    g += (f";[{n}:v]format=rgba[s];[a][s]overlay={st['x']}:{st['y'] + (0 if layout == "board" else int(S.get("ytSubY") or 0))}:eof_action=pass,format=yuv420p[o]" if subs else ";[a]format=yuv420p[o]")
    cmd += ["-filter_complex", g] + out

    if layout == "sound" and S.get("ytWave") != "off":
        p = subprocess.Popen(cmd + ["-progress", "pipe:1", "-nostats"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=False)
        threading.Thread(target=wave_frames, args=(src, a, length, wv, p.stdin, wk), daemon=True).start()
        err = []; threading.Thread(target=lambda: err.extend(p.stderr.readlines()[-6:]), daemon=True).start()
        last = -1
        for line in p.stdout:
            if line.startswith(b"out_time_us="):
                try:
                    pc = int(18 + 76 * int(line[12:]) / 1e6 / length)
                except ValueError:
                    continue
                if pc != last:
                    last = pc; progress(min(pc, 94), "Building the video")
        if p.wait() != 0:
            raise RuntimeError("ffmpeg: " + b"".join(err).decode("utf8", "replace")[-300:])
    else:
        encode(cmd, length)
    plat.swap(tmp, dest)

    progress(95, "Making the thumbnails")
    stem = os.path.splitext(dest)[0]
    pic, box = (None, None) if layout == "sound" and META.get("audioOnly") else best_frame(src, a, length, OUT)
    lines = [l for l in (k.get("thumb") or []) if l.strip()] or [title]
    thumbnails(stem, pic, box, lines, name, theme, OUT)
    if caps:
        open(stem + ".srt", "w").write("\n".join(f"{i}\n{hms(c['s'])} --> {hms(c['e'])}\n{c['t']}\n" for i, c in enumerate(caps, 1)))
        if S.get("ytEnglish"):
            open(stem + " English.srt", "w").write("\n".join(f"{i}\n{hms(c['s'])} --> {hms(c['e'])}\n{c.get('en', '')}\n" for i, c in enumerate(caps, 1)))
    if k:
        open(stem + ".txt", "w").write(post_text(k, name, handle))
    print("OUTPUT " + dest, flush=True)
    progress(100, "Done")


main()
