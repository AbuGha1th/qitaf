#!/usr/bin/env python3
"""Qitaf — local-only server. Run: python3 server.py → http://localhost:8795"""
import json, os, re, shutil, subprocess, sys, threading, time, uuid
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import plat
from plat import AAC, CLAUDE, CLIPS, FONTS
JOBS = os.path.join(ROOT, "jobs")
PRESETS = os.path.join(ROOT, "presets.json")
os.makedirs(JOBS, exist_ok=True)
for f in ("presets", "fixes", "channel"):  # his own copies: an update only ever replaces the .default files
    if not os.path.exists(os.path.join(ROOT, f + ".json")):
        shutil.copy(os.path.join(ROOT, f + ".default.json"), os.path.join(ROOT, f + ".json"))


def job_dir(job):
    if not re.fullmatch(r"[a-f0-9]{12}", job or ""):
        raise ValueError("bad job id")
    return os.path.join(JOBS, job)


def source_of(job):
    d = job_dir(job)
    return next((os.path.join(d, f) for f in sorted(os.listdir(d)) if f.startswith("source.")), None)


WHISPER_PY = sys.executable  # the server runs inside Qitaf's own environment


STATUS_LOCK = threading.Lock()


def set_status(job, **kw):
    p = os.path.join(job_dir(job), "status.json")
    with STATUS_LOCK:  # render and caption threads write together; replace in one step so a reader never sees half a file
        s = json.load(open(p)) if os.path.exists(p) else {}
        s.update(kw)
        json.dump(s, open(p + ".tmp", "w"), ensure_ascii=False)
        os.replace(p + ".tmp", p)


FIXES = os.path.join(ROOT, "fixes.json")
PUNCT = r"[.,!?؟،:؛…«»\"'()]"


def load_fixes():
    return json.load(open(FIXES)) if os.path.exists(FIXES) else {"words": {}, "drop": []}


def learn_fixes(job, edited):
    """Remember real mishearings from your edits (فاتقل لها → فاتق الله), never punctuation or a word you only
    lengthened for its sentence (كتب → كتبهم); 3+ words you deleted outright (Whisper's «ترجمة …» credits) are dropped next time."""
    import difflib
    orig = os.path.join(job_dir(job), "transcript.json")
    if not os.path.exists(orig):
        return
    clean = lambda ws: [w for w in (re.sub(PUNCT, "", w) for w in ws) if w]
    a = " ".join(s["text"] for s in json.load(open(orig))["segments"]).split()
    b = " ".join(s["text"] for s in edited["segments"]).split()
    F = load_fixes()
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        wa, wb = clean(a[i1:i2]), clean(b[j1:j2])
        if op == "replace" and 1 <= len(wa) <= 2 and 1 <= len(wb) <= 2:
            w, r = " ".join(wa), " ".join(wb)
            if w != r and len(w) >= 3 and not r.startswith(w) and not w.startswith(r):
                F["words"][w] = r
        elif op == "delete" and len(wa) >= 3 and " ".join(wa) not in F["drop"]:
            F["drop"].append(" ".join(wa))
    json.dump(F, open(FIXES, "w"), ensure_ascii=False, indent=1)


def apply_fixes(job):
    """Put your remembered fixes into a fresh transcript; returns how many places changed."""
    p = os.path.join(job_dir(job), "transcript.json"); t = json.load(open(p)); F = load_fixes(); n = 0
    for sg in t["segments"]:
        txt = " " + sg["text"] + " "
        for ph in F["drop"]:
            if " " + ph + " " in txt: txt = txt.replace(" " + ph + " ", " "); n += 1
        for w, r in F["words"].items():
            if " " in w:
                k = txt.count(" " + w + " ")
                if k: txt = txt.replace(" " + w + " ", " " + r + " "); n += k
        toks = txt.split()
        for i, tk in enumerate(toks):  # one-word fixes keep any punctuation stuck to the word (احضر! → احذر!)
            core = re.sub(PUNCT, "", tk)
            if " " not in core and core in F["words"] and core:
                toks[i] = tk.replace(core, F["words"][core]); n += 1
        sg["text"] = " ".join(toks)
    t["segments"] = [sg for sg in t["segments"] if sg["text"]]
    json.dump(t, open(p, "w"), ensure_ascii=False, indent=1)
    return n


def transcribe(job):
    """Background: extract 16 kHz mono audio, run Whisper, report % from its progress bar."""
    d = job_dir(job); wav = os.path.join(d, "audio.wav")
    try:
        set_status(job, stage="audio", pct=0, error=None)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", source_of(job), "-vn", "-ac", "1", "-ar", "16000", wav], check=True)
        set_status(job, stage="transcribe", pct=0)
        p = subprocess.Popen([WHISPER_PY, os.path.join(ROOT, "pipeline", "transcribe.py"), wav, os.path.join(d, "transcript.json")],
                             stderr=subprocess.PIPE, text=True, errors="replace", bufsize=1)
        buf = ""; tail = ""
        while (ch := p.stderr.read(1)):
            buf += ch; tail = (tail + ch)[-2000:]
            if ch in "\r\n":
                m = re.search(r"(\d+)%\|", buf)
                if m and "frames" in buf: set_status(job, pct=int(m.group(1)))  # only the audio-frames bar, not model loading
                buf = ""
        if p.wait() != 0:
            raise RuntimeError(tail.strip().splitlines()[-1] if tail.strip() else "transcription failed")
        set_status(job, stage="done", pct=100, fixed=apply_fixes(job))
    except Exception as e:
        set_status(job, stage="error", error=str(e))


def load_transcript(job):
    d = job_dir(job)
    for f in ("transcript_edited.json", "transcript.json"):
        if os.path.exists(os.path.join(d, f)):
            return json.load(open(os.path.join(d, f)))


def claude_titles(d, segs, clips):
    """Short Arabic titles for clips, keyed "0", "1"… in order; empty dict if Claude doesn't answer (titles can be typed later)."""
    said = lambda c: " ".join(s["text"] for s in segs if s["end"] > c["start"] and s["start"] < c["end"])
    prompt = ("Write a short Arabic title (≤ 8 words) for each clip of an Islamic lesson below: truthful, never "
              "sensational, ideally a question, a striking line from it, or a number promise. Reply JSON only: "
              "{\"titles\":{\"<number>\":\"…\"}}\n\n" + "\n\n".join(f"{i}: {said(c)}" for i, c in enumerate(clips)))
    try:
        r = subprocess.run([CLAUDE, "-p", "--tools", "", "--output-format", "text"], input=prompt,
                           capture_output=True, text=True, cwd=d, timeout=300)
        return json.loads(re.search(r"\{.*\}", r.stdout, re.S).group(0))["titles"]
    except Exception:
        return {}




def cover(d, video, title, speaker, dest):
    """9:16 reel cover (Instagram: Edit cover → Add from camera roll); title and name sit inside the middle 3:4 that the profile grid shows."""
    frame = os.path.join(d, "cover-frame.jpg"); page = os.path.join(d, "cover.html"); shot = os.path.join(d, "cover.png")
    # the frame comes from the raw cut when there is one, so the video's own title and name don't show through
    m = re.match(r"(.*?[/\\]\d+ - .*?)(?: \((?:motion|1:1|16:9)\))?\.mp4$", video); raw = m and os.path.join(os.path.dirname(m.group(1)), "raw", os.path.basename(m.group(1)) + " (raw).mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "2", "-i", raw if raw and os.path.exists(raw) else video,
                    "-frames:v", "1", "-q:v", "2", frame])
    esc = lambda t: t.replace("&", "&amp;").replace("<", "&lt;")
    open(page, "w").write(f"""<!doctype html><meta charset=utf-8><style>
@font-face{{font-family:T;src:url('{plat.url(os.path.join(FONTS, "thmanyahsans-Black.woff2"))}')}}@font-face{{font-family:TM;src:url('{plat.url(os.path.join(FONTS, "thmanyahsans-Medium.woff2"))}')}}
html,body{{margin:0;width:1080px;height:1920px;overflow:hidden;background:#1F1F1D}}
.f{{position:absolute;inset:0;background:url('{plat.url(frame)}') center 30%/cover}}
.g{{position:absolute;inset:0;background:linear-gradient(to top,rgba(20,20,18,.96) 0%,rgba(20,20,18,.82) 30%,rgba(20,20,18,0) 58%)}}
.t{{position:absolute;left:90px;right:90px;bottom:440px;direction:rtl;text-align:center;font:84px/1.35 T;color:#FFFBEB;text-wrap:balance}}
.s{{position:absolute;left:0;right:0;bottom:340px;direction:rtl;text-align:center;font:38px TM;color:#FDE68A}}
</style><div class=f></div><div class=g></div><div class=t>{esc(title)}</div><div class=s>{esc(speaker)}</div>""")
    plat.screenshot(plat.url(page), shot, 1080, 1920)
    if os.path.exists(shot):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", shot, "-q:v", "2", dest])
    for f in (frame, page, shot):
        if os.path.exists(f): os.remove(f)


def post_kit(job, c, video, keep=False):
    """Beside each finished video: <name>.txt with the Instagram caption, hashtags and a pinned-comment question
    (Nahj al-Athar caption template), and <name> cover.jpg — a 9:16 cover with the title (see cover())."""
    d = job_dir(job); S = json.load(open(os.path.join(d, "settings.json")))
    if S.get("style") == "youtube":  # youtube.py has already written its own text and thumbnails
        t = os.path.splitext(video)[0] + ".txt"
        return open(t).read().strip() if os.path.exists(t) else ""
    said = " ".join(s["text"] for s in load_transcript(job)["segments"] if s["end"] > c["start"] and s["start"] < c["end"])
    base = os.path.splitext(video)[0]
    who = "" if c.get("hideName") else c.get("speaker") or S.get("speaker", "")
    title = c.get("title") or S.get("titleText", "")
    if not title:  # no title given: Claude writes one, so the cover (and the post) always has a headline; kept with the clip
        title = claude_titles(d, load_transcript(job)["segments"], [c]).get("0", "")
        if title:
            cp = os.path.join(d, "clips.json"); cl = json.load(open(cp))
            for x in cl["clips"]:
                if x["id"] == c["id"]: x["title"] = title
            json.dump(cl, open(cp, "w"), ensure_ascii=False); c["title"] = title
    cover(d, video, title, who, base + " cover.jpg")
    if S.get("coverIntro"):
        cover_intro(video, base + " cover.jpg")
        if os.path.exists(base + " cover.jpg"):
            os.remove(base + " cover.jpg")  # it's the video's first second now: no separate picture to keep
    if keep and os.path.exists(base + ".txt"):  # only the style changed: the post stays as written
        txt = open(base + ".txt").read().strip()
        tag_post(video, txt)
        return txt
    # English subtitles chosen at set-up → the post is written in English too. Instagram allows at most 5 hashtags.
    en = S.get("translate", "off") != "off"
    src = (f"Source line: «— {who}»" + (" (the name transliterated into English, e.g. Shaykh …)" if en else "") + ". ") if who \
        else "Do NOT write any source or attribution line. "
    prompt = ((f"Write the Instagram post for this Islamic lesson clip, in {'English' if en else 'Arabic'}, for {plat.channel(en)}. Follow exactly:\n"
               "Line 1: the hook restated (≤ 10 words). Lines 2–4: the benefit in one or two sentences, faithful to what is said, "
               "nothing invented, no exaggeration. " + src +
               ("CTA line: «Send it to someone you love — the one who guides to good is like the one who does it». "
                "Then EXACTLY 5 hashtags, no more (Instagram's limit), in English: 2 broad (#Islam #Sunnah), "
                "2 from #SalafiReminders #IslamicKnowledge #SeekingKnowledge, 1 specific to the topic. Then a blank line and "
                "«Pinned comment:» with one short question that invites real answers. "
                if en else
                "CTA line: «أرسلها لمن تحب، والدال على الخير كفاعله». Then EXACTLY 5 hashtags, no more (Instagram's limit): "
                "#فوائد #السنة, then 2 of #آثار_السلف #فوائد_علمية #طلب_العلم, then 1 specific to the topic. Then a blank line and "
                "«تعليق مثبت:» with one short question that invites real answers. ") +
               "Plain text only, no emojis, no preamble, and never add notes, questions or explanations to me after it.\n\n"
               f"Title: {c.get('title', '')}\nWhat is said: {said}"))
    try:
        r = subprocess.run([CLAUDE, "-p", "--tools", "", "--output-format", "text"], input=prompt,
                           capture_output=True, text=True, cwd=d, timeout=300)
        if r.stdout.strip():
            open(base + ".txt", "w").write(r.stdout.strip() + "\n")
            tag_post(video, r.stdout.strip())
            return r.stdout.strip()
    except Exception:
        pass
    return ""


def finish_posts():
    """At start-up: captions that were still being written when the server stopped are written now."""
    for j in os.listdir(JOBS):
        sp = os.path.join(JOBS, j, "status.json")
        try:
            st = json.load(open(sp))
            clips = json.load(open(os.path.join(JOBS, j, "clips.json")))["clips"]
        except Exception:
            continue
        for cid, r in (st.get("clips") or {}).items():
            c = next((c for c in clips if str(c["id"]) == cid), None)
            if c and r.get("output") and "post" in r and r["post"] is None and os.path.exists(r["output"]):
                r["post"] = post_kit(j, c, r["output"])
                set_status(j, clips={**json.load(open(sp))["clips"], cid: r})


def cover_intro(video, cover, secs=1.0):
    """The cover as the video's first second (what WhatsApp, Telegram… show as the thumbnail), then the video.
    The cover is fitted to the video's own frame; the sound starts after it."""
    if not os.path.exists(cover):
        return
    w, h = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", video],
                          capture_output=True, text=True).stdout.strip().split(",")[:2]
    tmp = video + ".intro.mp4"
    # picture: the cover joined in front of the video; sound: the clip's own audio delayed by the same second
    # (joining a silent piece onto quiet audio raised its hiss ~5 dB; a delay leaves it untouched)
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-framerate", "30", "-t", str(secs), "-i", cover, "-i", video,
                        "-filter_complex",
                        f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,fps=30,format=yuv420p[c];"
                        f"[1:v]setsar=1,fps=30,format=yuv420p[v];[c][v]concat=n=2:v=1:a=0[ov];[1:a]adelay={int(secs * 1000)}:all=1[oa]",
                        "-map", "[ov]", "-map", "[oa]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                        # Apple's AAC encoder: ffmpeg's own one fills the highs with synthetic noise
                        "-c:a", AAC, "-b:a", "256k", "-movflags", "+faststart", tmp])
    if r.returncode == 0:
        plat.swap(tmp, video)


def tag_post(video, text):
    """The Instagram caption inside the video file: MP4 description/comment tags (they travel with the file, e.g. to the
    iPhone) and Finder's Comments field (Get Info). Picture and sound are copied untouched."""
    tmp = video + ".tag.mp4"
    # plus Apple's own QuickTime keys (written as "mdta" items), which is where the iPhone's Photos app looks for a caption
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", video, "-map", "0", "-c", "copy", "-metadata", f"description={text}",
                        "-metadata", f"comment={text}", "-metadata", f"synopsis={text}",
                        "-metadata", f"com.apple.quicktime.description={text}", "-metadata", f"com.apple.quicktime.comment={text}",
                        "-movflags", "+faststart+use_metadata_tags", tmp])
    if r.returncode == 0:
        plat.swap(tmp, video)
    plat.file_comment(video, text)


notify = plat.notify


def pick(job):
    """Background: ask Claude (local `claude` CLI, no tools) to pick clips; single-video mode skips this."""
    d = job_dir(job)
    try:
        S = json.load(open(os.path.join(d, "settings.json")))
        segs = load_transcript(job)["segments"]
        if S.get("mode") == "single":
            clips = [{"start": segs[0]["start"], "end": segs[-1]["end"], "title": "" if S.get("titleAuto") else S.get("titleText", ""),
                      "reason": "Whole video", "score": None, "hook": None}]
            if S.get("titleAuto") and S.get("showTitle", True):
                set_status(job, stage="picking", pct=0, error=None)
                clips[0]["title"] = claude_titles(d, segs, clips).get("0", "")
        elif S.get("clipMode") == "manual":
            # The user's own from → to times, used exactly. Claude only suggests titles for rows left blank.
            def hms(v):
                p = [float(x) for x in str(v).strip().split(":")] if str(v).strip() else []
                return sum(x * 60 ** k for k, x in enumerate(reversed(p))) if p else None
            clips = []
            for r in S.get("manualClips", []):
                a, b = hms(r.get("from")), hms(r.get("to"))
                if a is not None and b is not None and b > a:
                    clips.append({"start": round(a, 3), "end": round(b, 3), "title": (r.get("title") or "").strip(),
                                  "reason": "Your times", "score": None, "hook": None})
            if not clips:
                raise RuntimeError("no valid from → to times")
            blank = [i for i, c in enumerate(clips) if not c["title"]]
            if blank:
                set_status(job, stage="picking", pct=0, error=None)
                t = claude_titles(d, segs, [clips[i] for i in blank])
                for k, i in enumerate(blank):
                    clips[i]["title"] = t.get(str(k), "")
        else:
            set_status(job, stage="picking", pct=0, error=None)
            g = S.get("guidance", "").strip()
            prompt = open(os.path.join(ROOT, "pipeline", "pick_prompt.md")).read()
            for k, v in {"minLen": S["minLen"], "maxLen": min(S["maxLen"], 179), "count": S["clipCount"],
                         "guidance": f"- The user asked to focus on: {g}" if g else "",
                         "transcript": "\n".join(f"{s['start']:.1f}–{s['end']:.1f} {s['text']}" for s in segs)}.items():
                prompt = prompt.replace("{" + k + "}", str(v))
            r = subprocess.run([CLAUDE, "-p", "--tools", "", "--output-format", "text"], input=prompt,
                               capture_output=True, text=True, cwd=d, timeout=900)
            m = re.search(r"\{.*\}", r.stdout, re.S)
            if not m:
                raise RuntimeError((r.stderr or r.stdout or "Claude gave no answer").strip()[-300:])
            clips = json.loads(m.group(0))["clips"]
            # Snap to real line boundaries so no clip starts or ends mid-sentence.
            starts = [s["start"] for s in segs]; ends = [s["end"] for s in segs]
            for c in clips:
                c["start"] = min(starts, key=lambda t: abs(t - c["start"]))
                c["end"] = min((e for e in ends if e > c["start"]), key=lambda t: abs(t - c["end"]))
        for i, c in enumerate(clips):
            c.update(id=i + 1, keep=True, moveHook=bool(c.get("hook")) and bool(S.get("hookFirst")))  # hook first is an option, off unless chosen
        json.dump({"clips": clips}, open(os.path.join(d, "clips.json"), "w"), ensure_ascii=False, indent=1)
        set_status(job, stage="picked", pct=100)
    except Exception as e:
        set_status(job, stage="error", error=str(e))


RENDER_LOCKS = {}
LIVE = {}     # job → clip states shared by all its renders, so a queued render can't wipe a caption written meanwhile
WAITING = {}  # job → renders queued behind the running one


def live_state(job):
    if job not in LIVE:
        p = os.path.join(job_dir(job), "status.json")
        LIVE[job] = (json.load(open(p)).get("clips") or {}) if os.path.exists(p) else {}
    return LIVE[job]


def queue_ids(job, ids):
    """Show "Queued" on a tile the moment it's asked for. Returns the ids not already in the queue (a second click adds nothing)."""
    state = live_state(job)
    fresh = [i for i in ids if state.get(str(i), {}).get("label") != "Queued"]
    for i in fresh:
        state.setdefault(str(i), {}).update(pct=0, label="Queued", output=None, error=None)
    if fresh:
        set_status(job, clips=state)
    return fresh


def render_all(job, ids=None, rebuild=False, keep_post=False):
    """Background: render kept clips (or just `ids`) in turn; per-clip progress goes into status.json.
    rebuild=True reuses the existing cut and only re-renders (after caption edits).
    One lesson renders one request at a time: a second request (e.g. one tile's Re-render) waits for the first,
    so it can't mark the lesson finished while clips are still in the queue."""
    WAITING[job] = WAITING.get(job, 0) + 1
    with RENDER_LOCKS.setdefault(job, threading.Lock()):
        WAITING[job] -= 1
        _render_all(job, ids, rebuild, keep_post)


def _render_all(job, ids=None, rebuild=False, keep_post=False):
    d = job_dir(job)
    clips = [c for c in json.load(open(os.path.join(d, "clips.json")))["clips"] if c.get("keep") and (ids is None or c["id"] in ids)]
    state = live_state(job) if ids is not None else LIVE.setdefault(job, {})
    if ids is None:
        state.clear()
    state.update({str(c["id"]): {"pct": 0, "label": "Waiting", "output": None, "error": None} for c in clips})
    set_status(job, stage="rendering", clips=state, error=None)
    script = "youtube.py" if json.load(open(os.path.join(d, "settings.json"))).get("style") == "youtube" else "render_clip.py"
    for c in clips:
        st = state[str(c["id"])]
        # a lesson whose working files were cleaned has no cut to reuse: that clip is cut again
        rb = rebuild and os.path.exists(os.path.join(d, "clips", f"clip{c['id']}", "build.json"))
        p = subprocess.Popen([WHISPER_PY, os.path.join(ROOT, "pipeline", script), d, str(c["id"])] + (["rebuild"] if rb else []),
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace", bufsize=1)
        tail = []
        for line in p.stdout:
            tail = (tail + [line.strip()])[-8:]
            if line.startswith("PROGRESS "):
                _, pct, label = line.strip().split(" ", 2)
                st.update(pct=int(pct), label=label); set_status(job, clips=state)
            elif line.startswith("OUTPUT "):
                st["output"] = line[7:].strip()
        if p.wait() != 0:
            st.update(error=next((l for l in reversed(tail) if l), "render failed")[-300:], label="Failed")
        if st.get("output") and not st.get("error"):
            # the caption is written while the next clip renders
            st["post"] = None
            threading.Thread(target=lambda c=c, st=st: (st.update(post=post_kit(job, c, st["output"], keep_post)), set_status(job, clips=state)),
                             daemon=True).start()
        mj = os.path.join(d, "clips", f"clip{c['id']}", "mistakes.json")
        st["removed"] = json.load(open(mj)).get("removed", []) if os.path.exists(mj) else []
        set_status(job, clips=state)
    if WAITING.get(job):  # more renders are queued for this lesson: it isn't finished yet
        return
    set_status(job, stage="rendered")
    ok = sum(1 for c in clips if state[str(c["id"])].get("output"))
    notify(f"{ok} of {len(clips)} video{'s' if len(clips) != 1 else ''} ready" + (" — some failed" if ok < len(clips) else ""))


def batch(jobs):
    """Background: several uploads edited the same way, one after another: transcribe → whole video → render."""
    for job in jobs:
        if not os.path.exists(os.path.join(job_dir(job), "transcript.json")):
            transcribe(job)
        if json.load(open(os.path.join(job_dir(job), "status.json"))).get("stage") == "error":
            continue
        pick(job)
        if json.load(open(os.path.join(job_dir(job), "status.json"))).get("stage") == "error":
            continue
        render_all(job)


def dir_size(d):
    # lstat: render work folders hold links that may already point nowhere
    return sum(os.lstat(os.path.join(r, f)).st_size for r, _, fs in os.walk(d) for f in fs)


def clean(d):
    """Drop per-clip work folders and the extracted audio; source, transcript, settings and clip list stay."""
    shutil.rmtree(os.path.join(d, "clips"), ignore_errors=True)
    if os.path.exists(os.path.join(d, "audio.wav")): os.remove(os.path.join(d, "audio.wav"))


CLEAN_DAYS = 14


def auto_clean():
    """Working files of jobs untouched for CLEAN_DAYS are removed at start-up (finished videos are never touched)."""
    for j in os.listdir(JOBS):
        d = os.path.join(JOBS, j)
        if os.path.isdir(d) and time.time() - os.path.getmtime(d) > CLEAN_DAYS * 86400 and \
                (os.path.exists(os.path.join(d, "clips")) or os.path.exists(os.path.join(d, "audio.wav"))):
            clean(d)


def library():
    """Every lesson Qitaf has worked on, newest first, with the finished videos found for it."""
    out = []
    for j in os.listdir(JOBS):
        d = os.path.join(JOBS, j); m = os.path.join(d, "meta.json")
        if not os.path.exists(m):
            continue
        name = json.load(open(m)).get("name", j); lesson = os.path.splitext(name)[0]
        vd = os.path.join(CLIPS, plat.safe_name(lesson))
        vids = sorted(os.path.join(vd, f) for f in os.listdir(vd) if f.endswith(".mp4")) if os.path.isdir(vd) else []
        st = json.load(open(os.path.join(d, "status.json"))).get("stage") if os.path.exists(os.path.join(d, "status.json")) else None
        out.append({"job": j, "name": lesson, "time": os.path.getmtime(m), "stage": st, "videos": vids,
                    "picked": os.path.exists(os.path.join(d, "clips.json")), "mb": round(dir_size(d) / 1e6)})
    return sorted(out, key=lambda r: -r["time"])


def attach_voice(job, raw):
    """Make a recording (yours, uploaded, or the computer voice) the text job's audio. Returns its length or None."""
    d = job_dir(job); mp4 = os.path.join(d, "source.mp4")
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=320x568:r=30", "-i", raw,
                        "-shortest", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-b:a", "192k", mp4],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return None
    dur = probe(mp4)["duration"]
    # spread the lines over the recording (only the overall span matters; words are aligned at render)
    tp = os.path.join(d, "transcript.json"); T = json.load(open(tp)); segs = T["segments"]
    total = sum(len(s["text"].split()) for s in segs) or 1; t = 0.0
    for sg in segs:
        span = dur * len(sg["text"].split()) / total; sg["start"], sg["end"] = round(t, 3), round(t + span, 3); t += span
    json.dump(T, open(tp, "w"), ensure_ascii=False)
    meta = json.load(open(os.path.join(d, "meta.json"))); meta.update(textOnly=False, audioOnly=True, voiced=True)
    json.dump(meta, open(os.path.join(d, "meta.json"), "w"), ensure_ascii=False)
    return dur


arabic_voices, say_to = plat.arabic_voices, plat.speak


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=width,height",
                          "-of", "json", path], capture_output=True, text=True).stdout
    j = json.loads(out)
    s = next((s for s in j.get("streams", []) if "width" in s), {})
    return {"duration": float(j["format"]["duration"]), "width": s.get("width"), "height": s.get("height")}


class H(BaseHTTPRequestHandler):
    def send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        return json.loads(self.rfile.read(int(self.headers["Content-Length"])) or b"{}")

    def do_GET(self):
        u = urlparse(self.path); q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path == "/":
                return self.send(200, open(os.path.join(ROOT, "index.html"), "rb").read(), "text/html; charset=utf-8")
            if u.path == "/i18n.js":
                return self.send(200, open(os.path.join(ROOT, "i18n.js"), "rb").read(), "text/javascript; charset=utf-8")
            if u.path == "/guide":
                return self.send(200, open(os.path.join(ROOT, "guide.html"), "rb").read(), "text/html; charset=utf-8")
            if u.path == "/yt/frame":  # the YouTube designs, for the set-up preview (the renderer loads the same file)
                html = open(os.path.join(ROOT, "pipeline", "yt_frame.html")).read().replace("__FONTS__", "/fonts").replace("__LOGO__", "/yt/logo.png") \
                    .replace("<style>", "<style>:root{color-scheme:dark}", 1)  # same scheme as the page, or the browser paints the iframe solid
                return self.send(200, html.encode(), "text/html; charset=utf-8")
            if u.path == "/yt/logo.png":
                f = os.path.join(ROOT, "pipeline", "logo.png")  # optional: no file, no logo
                return self.send(200, open(f, "rb").read(), "image/png") if os.path.exists(f) else self.send(404, {"error": "no logo"})
            if u.path == "/icons.json":  # platform logos (Simple Icons, CC0) for the handle block
                return self.send(200, open(os.path.join(ROOT, "pipeline", "icons.json"), "rb").read())
            if u.path == "/rules.json":
                return self.send(200, open(os.path.join(ROOT, "rules.json"), "rb").read())
            if u.path == "/api/presets":
                return self.send(200, json.load(open(PRESETS)) if os.path.exists(PRESETS) else {})
            if u.path == "/api/frame":
                # One frame cropped to 9:16 around the centre, for the live preview.
                img = subprocess.run(["ffmpeg", "-v", "error", "-ss", q.get("t", "5"), "-i", source_of(q["job"]),
                                      "-frames:v", "1", "-vf", "crop='min(iw,ih*9/16)':ih,scale=540:960",
                                      "-f", "image2", "-c:v", "mjpeg", "-"], capture_output=True).stdout
                return self.send(200, img, "image/jpeg")
            if u.path == "/api/settings":
                f = os.path.join(job_dir(q["job"]), "settings.json")
                return self.send(200, json.load(open(f)) if os.path.exists(f) else {})
            if u.path == "/api/fixes":
                return self.send(200, load_fixes())
            if u.path == "/api/en":
                # a clip's English subtitles {Arabic line: English}, to correct by hand on the videos page
                f = os.path.join(job_dir(q["job"]), "clips", f"clip{int(q['clip'])}", "en.json")
                return self.send(200, json.load(open(f)) if os.path.exists(f) else {})
            if u.path == "/api/bgimg":
                # a clip's own picture, for its card on the clips page (404 when it has none)
                f = os.path.join(job_dir(q["job"]), f"bg-clip{int(q['clip'])}.png")
                return self.send(200, open(f, "rb").read(), "image/png") if os.path.exists(f) else self.send(404, {"error": "none"})
            if u.path == "/api/library":
                return self.send(200, library())
            if u.path == "/api/voices":
                return self.send(200, arabic_voices())
            if u.path == "/api/quran":
                # Qur'an recited inside transcript lines: {segment index: {a, b, ref, text}} (see pipeline/quran.py)
                import sys; sys.path.insert(0, os.path.join(ROOT, "pipeline")); import quran
                segs = load_transcript(q["job"])["segments"]
                return self.send(200, {str(k): m for k, sg in enumerate(segs) if (m := quran.find(sg["text"]))})
            if u.path == "/api/warsh":
                import warsh
                return self.send(200, {"warsh": warsh.lookup({"ref": q.get("ref"), "text": q.get("text")})})
            if u.path == "/api/status":
                p = os.path.join(job_dir(q["job"]), "status.json")
                return self.send(200, json.load(open(p)) if os.path.exists(p) else {"stage": "none"})
            if u.path == "/api/transcript":
                d = job_dir(q["job"])
                p = next((os.path.join(d, f) for f in ("transcript_edited.json", "transcript.json") if os.path.exists(os.path.join(d, f))))
                return self.send(200, open(p, "rb").read())
            if u.path == "/api/clips":
                return self.send(200, open(os.path.join(job_dir(q["job"]), "clips.json"), "rb").read())
            if u.path.startswith("/fonts/"):
                # The channel's own fonts live in the nahj-style skill.
                f = os.path.basename(unquote(u.path))
                ctype = {".woff2": "font/woff2", ".ttf": "font/ttf", ".otf": "font/otf"}[os.path.splitext(f)[1]]
                return self.send(200, open(os.path.join(FONTS, f), "rb").read(), ctype)
            if u.path == "/api/caps":
                cd = os.path.join(job_dir(q["job"]), "clips", f"clip{int(q['id'])}")
                ce = os.path.join(cd, "caps_edited.json")
                return self.send(200, json.load(open(ce)) if os.path.exists(ce) else json.load(open(os.path.join(cd, "build.json")))["caps"])
            if u.path == "/api/size":
                return self.send(200, {"mb": round(dir_size(job_dir(q["job"])) / 1e6)})
            if u.path == "/api/video":
                p = os.path.realpath(q["path"])
                if not p.startswith(CLIPS + os.sep):
                    raise ValueError("not a Qitaf clip")
                return self.send_file(p, "image/jpeg" if p.endswith(".jpg") else "video/mp4")
            if u.path == "/api/source":
                # the uploaded video itself, for the live preview (Range-capable so it can seek)
                src = source_of(q["job"])
                ctype = {".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm", ".m4v": "video/mp4"}.get(os.path.splitext(src)[1].lower(), "video/mp4")
                return self.send_file(src, ctype)
            if u.path == "/api/audio":
                return self.send_file(os.path.join(job_dir(q["job"]), "audio.wav"), "audio/wav")
            self.send(404, {"error": "not found"})
        except Exception as e:
            self.send(400, {"error": str(e)})

    def send_file(self, path, ctype):
        # Range support so the transcript editor can seek in the audio.
        size = os.path.getsize(path); start, end = 0, size - 1
        m = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
        if m:
            start = int(m.group(1) or 0); end = int(m.group(2) or end)
        self.send_response(206 if m else 200)
        self.send_header("Content-Type", ctype); self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if m: self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with open(path, "rb") as f:
            f.seek(start); left = end - start + 1
            while left > 0:
                chunk = f.read(min(left, 1 << 20)); self.wfile.write(chunk); left -= len(chunk)

    def do_POST(self):
        u = urlparse(self.path)
        try:
            if u.path == "/api/upload":
                job = uuid.uuid4().hex[:12]; d = job_dir(job); os.makedirs(d)
                name = os.path.basename(unquote(self.headers.get("X-Filename", "video.mp4")))
                ext = os.path.splitext(name)[1].lower() or ".mp4"
                left = int(self.headers["Content-Length"])
                with open(os.path.join(d, "source" + ext), "wb") as f:
                    while left:
                        chunk = self.rfile.read(min(left, 1 << 20)); f.write(chunk); left -= len(chunk)
                json.dump({"name": name}, open(os.path.join(d, "meta.json"), "w"), ensure_ascii=False)
                try:
                    info = probe(source_of(job))
                except Exception:
                    shutil.rmtree(d)  # not readable media — don't keep it
                    return self.send(400, {"error": "this file isn't a video or audio file ffmpeg can read"})
                if not info.get("width"):
                    # Audio only (mp3, m4a…): wrap it in a tiny black video so the same cut/align pipeline works.
                    # Audio sources are motion-graphic only, so the picture is never shown.
                    src = source_of(job); mp4 = os.path.join(d, "source.mp4")
                    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=320x568:r=30", "-i", src,
                                    "-shortest", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-b:a", "192k", mp4], check=True)
                    os.rename(src, os.path.join(d, "original" + ext)); info = probe(mp4); info["audioOnly"] = True
                    json.dump({"name": name, "audioOnly": True}, open(os.path.join(d, "meta.json"), "w"), ensure_ascii=False)
                return self.send(200, {"job": job, "name": name, **info})
            if u.path == "/api/voice":
                # A recording of someone reading the text: it becomes the job's audio. The written lines stay the
                # transcript (no mishearing); the render aligns each word to the real voice.
                job = parse_qs(u.query)["job"][0]; d = job_dir(job)
                ext = {"audio/webm": ".webm", "audio/mp4": ".m4a", "audio/mpeg": ".mp3", "audio/wav": ".wav"}.get(
                    self.headers.get("Content-Type", "").split(";")[0], ".webm")
                raw = os.path.join(d, "voice" + ext); left = int(self.headers["Content-Length"])
                with open(raw, "wb") as f:
                    while left:
                        chunk = self.rfile.read(min(left, 1 << 20)); f.write(chunk); left -= len(chunk)
                dur = attach_voice(job, raw)
                if dur is None:
                    return self.send(400, {"error": "couldn't read that recording"})
                return self.send(200, {"ok": True, "duration": round(dur, 1)})
            if u.path == "/api/bg":
                # A picture to use instead of the footage; stored as a PNG so ffmpeg reads any format the browser sent.
                # ?clip=N: a picture for that one clip only (bg-clipN.png); &remove=1 takes it away again
                qs = parse_qs(u.query); job = qs["job"][0]; d = job_dir(job); raw = os.path.join(d, "bg-upload")
                name = f"bg-clip{int(qs['clip'][0])}.png" if "clip" in qs else "bg.png"
                if "remove" in qs:
                    if os.path.exists(os.path.join(d, name)): os.remove(os.path.join(d, name))
                    return self.send(200, {"ok": True})
                left = int(self.headers["Content-Length"])
                with open(raw, "wb") as f:
                    while left:
                        chunk = self.rfile.read(min(left, 1 << 20)); f.write(chunk); left -= len(chunk)
                r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", raw, "-frames:v", "1", os.path.join(d, name)])
                os.remove(raw)
                return self.send(200, {"ok": True} if r.returncode == 0 else {"error": "couldn't read that picture"})
            if u.path == "/api/tts":
                # Computer voiceover of the job's text, read by a macOS Arabic voice, then attached like a recording.
                b = self.read_json(); job = b["job"]; d = job_dir(job)
                voice = b.get("voice") if b.get("voice") in arabic_voices() else "Majed"
                text = "\n".join(sg["text"] for sg in json.load(open(os.path.join(d, "transcript.json")))["segments"])
                raw = os.path.join(d, "voice-tts.aiff"); say_to(text, voice, b.get("rate", 170), raw)
                dur = attach_voice(job, raw)
                return self.send(200, {"ok": True, "duration": round(dur, 1)} if dur else {"error": "the computer voice failed"})
            if u.path == "/api/ttssample":
                # a short sample so the voice and speed can be heard before making the video
                b = self.read_json(); voice = b.get("voice") if b.get("voice") in arabic_voices() else "Majed"
                tmp = os.path.join(JOBS, "tts-sample.aiff"); m4a = os.path.join(JOBS, "tts-sample.m4a")
                say_to((b.get("text") or "بسم الله الرحمن الرحيم")[:300], voice, b.get("rate", 170), tmp)
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", tmp, "-c:a", "aac", m4a], check=True)
                return self.send(200, open(m4a, "rb").read(), "audio/mp4")
            if u.path == "/api/textjob":
                # Text-only motion graphic: no recording. Lines are timed at a calm reading pace;
                # the video is silent apart from the quiet sound effects.
                b = self.read_json(); lines = [l.strip() for l in b["text"].split("\n") if l.strip()]
                if not lines:
                    return self.send(400, {"error": "write at least one line"})
                job = uuid.uuid4().hex[:12]; d = job_dir(job); os.makedirs(d)
                t, segs = 0.6, []
                for l in lines:
                    n = len(l.split()); dur = max(1.6, n / 2.2)
                    words = [{"text": w, "start": round(t + k * dur / n, 3), "end": round(t + (k + 1) * dur / n, 3)} for k, w in enumerate(l.split())]
                    segs.append({"start": round(t, 3), "end": round(t + dur, 3), "text": l, "words": words}); t += dur + 0.7
                json.dump({"language": "ar", "segments": segs}, open(os.path.join(d, "transcript.json"), "w"), ensure_ascii=False)
                json.dump({"name": b.get("name") or "text", "textOnly": True}, open(os.path.join(d, "meta.json"), "w"), ensure_ascii=False)
                set_status(job, stage="done", pct=100)
                return self.send(200, {"job": job, "duration": round(t, 1)})
            if u.path == "/api/presets":
                body = self.read_json()
                presets = json.load(open(PRESETS)) if os.path.exists(PRESETS) else {}
                if os.path.exists(PRESETS):  # one step of undo: an overwritten preset can be recovered from presets.prev.json
                    shutil.copy(PRESETS, PRESETS.replace(".json", ".prev.json"))
                presets[body["name"]] = body["settings"]
                json.dump(presets, open(PRESETS, "w"), ensure_ascii=False, indent=2)
                return self.send(200, presets)
            if u.path == "/api/settings":
                body = self.read_json()
                json.dump(body["settings"], open(os.path.join(job_dir(body["job"]), "settings.json"), "w"),
                          ensure_ascii=False, indent=2)
                return self.send(200, {"ok": True})
            if u.path == "/api/transcribe":
                job = self.read_json()["job"]
                if os.path.exists(os.path.join(job_dir(job), "transcript.json")):
                    set_status(job, stage="done", pct=100)
                else:
                    threading.Thread(target=transcribe, args=(job,), daemon=True).start()
                return self.send(200, {"ok": True})
            if u.path == "/api/batch":
                threading.Thread(target=batch, args=(self.read_json()["jobs"],), daemon=True).start()
                return self.send(200, {"ok": True})
            if u.path == "/api/render":
                b = self.read_json(); ids = b.get("ids")
                if ids is not None:
                    ids = queue_ids(b["job"], ids)
                    if not ids:
                        return self.send(200, {"ok": True})
                threading.Thread(target=render_all, args=(b["job"], ids, b.get("rebuild", False), b.get("restyle", False)), daemon=True).start()
                return self.send(200, {"ok": True})
            if u.path == "/api/caps":
                b = self.read_json()
                json.dump(b["caps"], open(os.path.join(job_dir(b["job"]), "clips", f"clip{int(b['id'])}", "caps_edited.json"), "w"),
                          ensure_ascii=False)
                return self.send(200, {"ok": True})
            if u.path == "/api/cleanup":
                # Free space: drop per-clip work folders and the extracted audio. Finished videos in
                # Desktop/CLAUDE/clips, the transcript, settings and clip list are kept.
                d = job_dir(self.read_json()["job"]); before = dir_size(d)
                clean(d)
                return self.send(200, {"freed_mb": round((before - dir_size(d)) / 1e6)})
            if u.path == "/api/en":
                b = self.read_json()
                json.dump(b["en"], open(os.path.join(job_dir(b["job"]), "clips", f"clip{int(b['clip'])}", "en.json"), "w"),
                          ensure_ascii=False, indent=1)
                return self.send(200, {"ok": True})
            if u.path == "/api/fixes":
                # forget one remembered fix
                b = self.read_json(); F = load_fixes()
                F["words"].pop(b.get("word", ""), None); F["drop"] = [d for d in F["drop"] if d != b.get("drop")]
                json.dump(F, open(FIXES, "w"), ensure_ascii=False, indent=1)
                return self.send(200, F)
            if u.path == "/api/trash":
                # Library deletes go to the macOS Trash (so a mistake can be undone): a whole lesson's job
                # folders, and optionally its finished videos, or a single finished video.
                b = self.read_json(); moved = 0
                def bin_(p):
                    plat.trash(p, f"Qitaf {uuid.uuid4().hex[:6]} {os.path.basename(p)}")
                for j in b.get("jobs", []):
                    d = job_dir(j)
                    if os.path.isdir(d): bin_(d); moved += 1
                for v in b.get("videos", []):
                    p = os.path.realpath(v)
                    if p.startswith(CLIPS + os.sep) and os.path.exists(p):
                        bin_(p); moved += 1
                        if os.path.isdir(os.path.dirname(p)) and not os.listdir(os.path.dirname(p)): os.rmdir(os.path.dirname(p))
                return self.send(200, {"moved": moved})
            if u.path == "/api/reveal":
                # Show a finished clip in Finder — only files Qitaf itself wrote to the clips folder.
                p = os.path.realpath(self.read_json()["path"])
                if p.startswith(CLIPS + os.sep) and os.path.exists(p):
                    plat.reveal(p)
                return self.send(200, {"ok": True})
            if u.path == "/api/pick":
                threading.Thread(target=pick, args=(self.read_json()["job"],), daemon=True).start()
                return self.send(200, {"ok": True})
            if u.path == "/api/clips":
                body = self.read_json()
                json.dump(body["clips"], open(os.path.join(job_dir(body["job"]), "clips.json"), "w"),
                          ensure_ascii=False, indent=1)
                return self.send(200, {"ok": True})
            if u.path == "/api/transcript":
                body = self.read_json()
                json.dump(body["transcript"], open(os.path.join(job_dir(body["job"]), "transcript_edited.json"), "w"),
                          ensure_ascii=False, indent=1)
                learn_fixes(body["job"], body["transcript"])
                return self.send(200, {"ok": True})
            self.send(404, {"error": "not found"})
        except Exception as e:
            self.send(400, {"error": str(e)})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    auto_clean()
    threading.Thread(target=finish_posts, daemon=True).start()
    port = int(os.environ.get("QITAF_PORT", 8795))
    print(f"Qitaf → http://localhost:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
