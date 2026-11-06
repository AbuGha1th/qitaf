"""Render one Qitaf clip: cut → crop 9:16 → forced-align captions → HyperFrames page → MP4.

Usage: python render_clip.py <job_dir> <clip_id>
Prints "PROGRESS <0-100> <label>" lines for the server.
Adapted from Al-Idrisi-Lesson-1/work (cut.py, fa.py): silences from the real audio,
frame-snapped one-pass cut, MMS_FA alignment on the CUT audio (Whisper times are ~0.3-0.5 s off).
"""
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import wave

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import plat
from plat import ASSETS, CLAUDE, FONTS
SFX = os.path.join(ASSETS, "sfx")
FPS = 30
SILENCE = {"gentle": (-34, 0.8), "normal": (-32, 0.45), "tight": (-30, 0.3)}  # (noise dB, min pause s)
KEEP_BEFORE, KEEP_AFTER = 0.14, 0.10

job_dir, clip_id = os.path.abspath(sys.argv[1]), int(sys.argv[2])
S = json.load(open(os.path.join(job_dir, "settings.json")))
clip = next(c for c in json.load(open(os.path.join(job_dir, "clips.json")))["clips"] if c["id"] == clip_id)
tp = next(os.path.join(job_dir, f) for f in ("transcript_edited.json", "transcript.json") if os.path.exists(os.path.join(job_dir, f)))
segs = json.load(open(tp))["segments"]
META = json.load(open(os.path.join(job_dir, "meta.json")))
TEXT_ONLY, AUDIO_ONLY = META.get("textOnly", False), META.get("audioOnly", False)
src = next((os.path.join(job_dir, f) for f in sorted(os.listdir(job_dir)) if f.startswith("source.")), None)
BG = os.path.join(job_dir, "bg.png") if S.get("background") == "picture" and os.path.exists(os.path.join(job_dir, "bg.png")) else None
if os.path.exists(os.path.join(job_dir, f"bg-clip{clip_id}.png")):  # this clip's own picture wins over the lesson's
    BG = os.path.join(job_dir, f"bg-clip{clip_id}.png")
if TEXT_ONLY or (AUDIO_ONLY and not BG):
    S["style"] = "visualy"  # no camera footage: these sources are motion graphics only
out = os.path.join(job_dir, "clips", f"clip{clip_id}")
assets = os.path.join(out, "assets")
os.makedirs(assets, exist_ok=True)


def progress(p, label):
    print(f"PROGRESS {p} {label}", flush=True)


def snap(t):
    return round(round(t * FPS) / FPS, 4)


def lines_in(a, b):
    return [s for s in segs if s["end"] > a + 0.05 and s["start"] < b - 0.05]


REBUILD = len(sys.argv) > 3 and sys.argv[3] == "rebuild"
# frame size: 9:16 reels by default; 1:1 and 16:9 (YouTube) for the lesson-reel style
RW, RH = {"1:1": (1080, 1080), "16:9": (1920, 1080)}.get(S.get("ratio"), (1080, 1920)) if S.get("style") != "visualy" else (1080, 1920)  # captions edited: reuse the cut, skip cut + align
if TEXT_ONLY:
    progress(10, "Timing the text")
    words, times, line_of = [], [], []
    for li, sg in enumerate(segs):
        ws = sg["text"].split()  # from the (possibly edited) line text, spread evenly over the line
        for k, w in enumerate(ws):
            a = sg["start"] + (sg["end"] - sg["start"]) * k / len(ws)
            words.append(w); times.append((round(a, 3), round(a + (sg["end"] - sg["start"]) / len(ws), 3))); line_of.append(li)
    duration = round(segs[-1]["end"] + 1.2, 3)
    caps, env = [], [0.0] * int(duration * FPS)
    json.dump({"duration": duration, "caps": caps, "env": env, "hook_end": 0,
               "words": [[w, line_of[i], t[0], t[1]] for i, (w, t) in enumerate(zip(words, times))]},
              open(os.path.join(out, "build.json"), "w"), ensure_ascii=False)
elif not REBUILD:
    # ---------- 1. what plays, in order: optional hook first, then the clip ----------
    progress(2, "Cutting")
    ranges = []
    if clip.get("moveHook") and clip.get("hook"):
        hl = lines_in(clip["hook"]["start"], clip["hook"]["end"])  # widen the hook to whole lines
        if hl:
            ranges.append((hl[0]["start"], hl[-1]["end"]))
    ranges.append((clip["start"], clip["end"]))
    text_lines = [l for a, b in ranges for l in lines_in(a, b)]

    # ---------- 2. keep ranges: drop real silences inside each range ----------
    noise, min_sil = SILENCE[S.get("strictness", "normal")]
    keeps, hook_n = [], 0  # hook_n: how many kept pieces belong to the hook (silences inside it split it up)
    for ri, (a, b) in enumerate(ranges):
        if ri == 1:
            hook_n = len(keeps)
        lo, hi = snap(max(0, a - 0.25)), snap(b + 0.45)
        dels = []
        if S.get("cutSilences", True):
            log = subprocess.run(["ffmpeg", "-hide_banner", "-ss", str(lo), "-to", str(hi), "-i", src, "-vn",
                                  "-af", f"silencedetect=noise={noise}dB:d={min_sil}", "-f", "null", "-"],
                                 capture_output=True, text=True).stderr
            st = [float(x) + lo for x in re.findall(r"silence_start: ([\d.]+)", log)]
            en = [float(x) + lo for x in re.findall(r"silence_end: ([\d.]+)", log)]
            for s, e in zip(st, en):
                x, y = snap(s + KEEP_BEFORE), snap(e - KEEP_AFTER)
                if y - x >= 2 / FPS:
                    dels.append((x, y))
        t = lo
        for x, y in dels:
            if x > t:
                keeps.append((t, x))
            t = max(t, y)
        if hi > t:
            keeps.append((t, hi))
    keeps = [(a, b) for a, b in keeps if b - a >= 2 / FPS]
    duration = round(sum(b - a for a, b in keeps), 3)

    # ---------- 3. framing: 9:16 window on the speaker ----------
    progress(8, "Finding the speaker")
    info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                                      "-of", "json", src], capture_output=True, text=True).stdout)["streams"][0]
    W, H = info["width"], info["height"]
    cw = min(W, int(H * RW / RH) // 2 * 2); ch = min(H, int(cw * RH / RW) // 2 * 2)
    cx = W / 2
    frame_on = clip.get("frameOn", "auto")  # set per clip on the clips page: auto / left / centre / right
    if frame_on in ("left", "right") and cw < W:
        cx = cw / 2 if frame_on == "left" else W - cw / 2
    elif frame_on == "auto" and S.get("framing") == "face" and cw < W and not BG:
        # the SPEAKER, not the biggest face: for each face, how much its mouth area changes over a fifth of a second;
        # faces are grouped by where they sit across the frame, and the group that moves its mouth most wins
        import cv2
        cap = cv2.VideoCapture(src)
        det = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        bins, samples = {}, 0  # x bin → [mouth motion samples, face centres]; samples = moments looked at
        for a, b in keeps:
            t = a
            while t < b:
                cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000); ok, f1 = cap.read()
                cap.set(cv2.CAP_PROP_POS_MSEC, (t + 0.2) * 1000); ok2, f2 = cap.read()
                if ok and ok2:
                    samples += 1
                    g1, g2 = cv2.cvtColor(f1, cv2.COLOR_BGR2GRAY), cv2.cvtColor(f2, cv2.COLOR_BGR2GRAY)
                    for x, y, w, h in det.detectMultiScale(g1, 1.15, 6, minSize=(H // 12, H // 12)):
                        if not (0.12 * H < y + h / 2 < 0.88 * H and 0.04 * W < x + w / 2 < 0.96 * W):
                            continue  # banners, logos and calligraphy at the frame's edges are not the speaker
                        m1, m2 = g1[y + h * 2 // 3:y + h, x + w // 5:x + w * 4 // 5], g2[y + h * 2 // 3:y + h, x + w // 5:x + w * 4 // 5]
                        motion = float(np.abs(m1.astype(np.int16) - m2.astype(np.int16)).mean())
                        e = bins.setdefault(int((x + w / 2) / W * 8), [[], []])
                        e[0].append(motion); e[1].append(x + w / 2)
                t += 1.5
        # AVERAGE motion, not total: a listener facing the camera is found more often, but the speaker's mouth moves more
        grp = {k: [m for kk in (k - 1, k, k + 1) for m in bins.get(kk, [[], []])[0]] for k in bins}
        grp = {k: v for k, v in grp.items() if len(v) >= max(2, 0.15 * samples)}  # seen too rarely → not a real face; keep the centre
        if grp:
            k = max(grp, key=lambda k: sum(grp[k]) / len(grp[k]))
            cx = statistics.median([c for kk in (k - 1, k, k + 1) for c in bins.get(kk, [[], []])[1]])
    crop_x = int(min(max(cx - cw / 2, 0), W - cw)); crop_y = (H - ch) // 2

    progress(12, "Cutting")
    parts = "".join(f"[0:v]trim=start={a}:end={b},setpts=PTS-STARTPTS[v{i}];[0:a]atrim=start={a}:end={b},asetpts=PTS-STARTPTS[a{i}];"
                    for i, (a, b) in enumerate(keeps))
    graph = parts + "".join(f"[v{i}][a{i}]" for i in range(len(keeps)))
    graph += (f"concat=n={len(keeps)}:v=1:a=1[cv][ca];[cv]crop={cw}:{ch}:{crop_x}:{crop_y},scale={RW}:{RH}:flags=lanczos,"
              f"unsharp=5:5:0.5:5:5:0,fps={FPS},format=yuv420p[v]")
    gf = os.path.join(out, "cut-filter.txt")
    open(gf, "w").write(graph)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-/filter_complex", gf, "-map", "[v]", "-map", "[ca]",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                    "-movflags", "+faststart", os.path.join(assets, "speaker.mp4")], check=True)
    # the raw cut: the chosen shape with only the silences removed (no captions, titles or mistake cuts), kept beside the video
    shutil.copy(os.path.join(assets, "speaker.mp4"), os.path.join(out, "raw.mp4"))
    if BG:
        # picture instead of the footage: the still fills 9:16 (cropped to fit), the cut voice plays over it
        sp = os.path.join(assets, "speaker.mp4"); tmp = os.path.join(out, "cut-voice.mp4"); os.replace(sp, tmp)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-framerate", str(FPS), "-i", BG, "-i", tmp,
                        "-vf", f"scale={RW}:{RH}:force_original_aspect_ratio=increase,crop={RW}:{RH},format=yuv420p",
                        "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-tune", "stillimage", "-crf", "18", "-c:a", "copy",
                        "-shortest", "-movflags", "+faststart", sp], check=True)
        os.remove(tmp)

    # ---------- 4. captions: forced-align the (corrected) words on the cut audio ----------
    # forced alignment is only needed for on-screen captions, motion scenes, or finding mistakes
    need_align = S.get("textMode", "captions") == "captions" or S.get("style") == "visualy" or S.get("cutMistakes", True)
    progress(30, "Syncing captions" if S.get("textMode", "captions") == "captions" else "Checking the words")
    wav = os.path.join(out, "speaker-16k.wav")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", os.path.join(assets, "speaker.mp4"), "-vn", "-ac", "1", "-ar", "16000", wav], check=True)
    with wave.open(wav) as wf:
        sr = wf.getframerate()
        pcm = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0

    LETTERS = dict(zip("اأإآٱءؤئبتثجحخدذرزسشصضطظعغفقكلمنهةويىڤگَُِ",
                       ["a", "a", "i", "a", "a", "'", "u", "i", "b", "t", "t", "j", "h", "x", "d", "d", "r", "z", "s", "sh",
                        "s", "d", "t", "z", "'", "g", "f", "q", "k", "l", "m", "n", "h", "a", "w", "y", "a", "v", "g", "a", "u", "i"]))
    import quran  # lines nobody checked on the clips page are searched here (batches, single videos)
    for l in text_lines:
        if "quran" not in l:
            l["quran"] = quran.find(l["text"])
    # a verse line whose spoken words were cleared (so they don't show twice) still needs them to time the verse:
    # take them back from the original transcription by time; words you kept (e.g. «قال تعالى») stay before the verse
    op = os.path.join(job_dir, "transcript.json")
    orig = json.load(open(op))["segments"] if os.path.exists(op) else []
    for l in text_lines:
        q = l.get("quran"); kept = l["text"].split()
        if not q or len(kept) > q["b"]:
            continue
        said = " ".join(o["text"] for o in orig if o["end"] > l["start"] + 0.05 and o["start"] < l["end"] - 0.05).split()
        if len(said) <= len(kept):
            continue
        k = len(kept) if said[:len(kept)] == kept else 0
        l["text"] = " ".join(said); q["a"], q["b"] = k, len(said) - 1
    # lines you added yourself aren't in the audio: keep them out of the voice sync (they'd pull every other word off time)
    wl = [(w, li, k) for li, l in enumerate(text_lines) if not l.get("added")
          for k, w in enumerate(l["text"].split()) if any(ch in LETTERS for ch in w)]
    words, line_of, tok_of = [w for w, _, _ in wl], [li for _, li, _ in wl], [k for _, _, k in wl]
    QR = S.get("quranReading", "hafs")
    if QR == "warsh":  # verses nobody pasted or reviewed on the clips page (batches, single videos)
        import warsh
        for l in text_lines:
            q = l.get("quran")
            if q and q.get("text") and not q.get("warsh"):
                q["warsh"] = warsh.lookup(q)

    def verse_of(i):
        """The Qur'an mark covering word i (ticked on the clips page), or None. Warsh needs its pasted text."""
        q = text_lines[line_of[i]].get("quran")
        if not q or not (q["a"] <= tok_of[i] <= q["b"]):
            return None
        return q if (q.get("warsh") if QR == "warsh" else q.get("text")) else None
    times = []
    if words and not need_align:
        # no captions on screen: spread each line's words evenly over its transcript time (enough for zoom timing)
        def _cut(x):
            acc = 0.0
            for a, b in keeps:
                if a <= x <= b:
                    return acc + x - a
                acc += b - a
            return None
        for li, l in enumerate(text_lines):
            lw = [w for w, k, _ in wl if k == li]
            a, b = _cut(l["start"]), _cut(l["end"])
            if a is None or b is None or b <= a:
                a = times[-1][1] if times else 0.0; b = a + 0.3 * len(lw)
            step = (b - a) / max(1, len(lw))
            times += [(round(a + step * k, 3), round(a + step * (k + 1), 3)) for k in range(len(lw))]
    elif words:
        import torch
        import torchaudio
        bundle = torchaudio.pipelines.MMS_FA
        model = bundle.get_model(with_star=False)
        wave_t = torch.from_numpy(pcm).unsqueeze(0)
        with torch.inference_mode():
            em = torch.cat([model(wave_t[:, i:i + 30 * sr])[0] for i in range(0, wave_t.size(1), 30 * sr)], dim=1)
        ratio = wave_t.size(1) / em.size(1) / sr
        spans = bundle.get_aligner()(em[0], bundle.get_tokenizer()(["".join(LETTERS.get(c, "") for c in w) or "a" for w in words]))
        times = [(round(sp[0].start * ratio, 3), round(sp[-1].end * ratio, 3)) for sp in spans]

    post_map = lambda x: x  # cut-time → final time after mistake cuts (identity unless 4a cuts something)
    if os.path.exists(os.path.join(out, "mistakes.json")):
        os.remove(os.path.join(out, "mistakes.json"))  # only this render's cuts are reported
    # ---------- 4a. remove mistakes: Claude marks false starts, repeats and stumbles; we cut them out ----------
    if S.get("cutMistakes", True) and len(words) > 8:
        progress(36, "Removing mistakes")
        prompt = ("Below are the words of an Arabic lesson clip as spoken, numbered, with start times. Mark speaking MISTAKES to cut: "
                  "false starts and restarts (keep the final, complete version), a word or phrase accidentally said twice in a row, "
                  "stumbles, and filler sounds (e.g. إيه، آه، يعني used as filler). Never cut deliberate repetition for emphasis, "
                  "Qur'an, hadith, or anything that changes the meaning. If unsure, don't cut. Reply JSON only: "
                  "{\"cut\":[[first,last],...]} with inclusive word-number ranges, or {\"cut\":[]}.\n\n"
                  + "\n".join(f"{i} [{t[0]:.2f}] {w}" for i, (w, t) in enumerate(zip(words, times))))
        cuts = []
        try:
            r = subprocess.run([CLAUDE, "-p", "--tools", "", "--output-format", "text"], input=prompt,
                               capture_output=True, text=True, timeout=300, cwd=out)
            cuts = [(int(a), int(b)) for a, b in json.loads(re.search(r"\{.*\}", r.stdout, re.S).group(0))["cut"]
                    if 0 <= int(a) <= int(b) < len(words)]
        except Exception as e:
            print(f"MISTAKES check skipped: {e}", flush=True)
            cuts = []

        # Only trust a cut we can verify: a real restart (most of the cut words are said again right after)
        # or pure filler sounds. This stops rhetorical questions and emphasis from being cut.
        def nz(t):
            t = re.sub(r"[ً-ْٰـ]", "", t)
            return re.sub(r"[^ء-ي]", "", t).translate(str.maketrans("أإآىة", "ااايه"))
        FILLER = {"ايه", "اه", "ام", "اا", "امم", "ها"}
        # Strict on purpose: a phrase repeated in full is emphasis (e.g. «دعوكم من الفيسبوكيين، دعوكم من الفيسبوكيين»),
        # so it is never cut. Only these count as slips:
        #   - filler sounds only
        #   - one word stuttered straight away (same word, next word, under 0.35 s apart)
        #   - a cut-off word restarted: the cut ends in a word that the next word starts with (الفيس → الفيسبوكيين)
        ok = []
        for a, b in cuts:
            seg = [nz(w) for w in words[a:b + 1]]
            nxt = nz(words[b + 1]) if b + 1 < len(words) else ""
            filler = all(w in FILLER for w in seg)
            stutter = len(seg) == 1 and seg[0] == nxt and b + 1 < len(times) and times[b + 1][0] - times[b][1] < 0.35
            cutoff = len(seg) <= 2 and nxt and seg[-1] != nxt and len(seg[-1]) >= 2 and nxt.startswith(seg[-1])
            if (filler or stutter or cutoff) and not any(verse_of(i) for i in range(a, b + 1)):  # never cut inside a verse
                ok.append((a, b))
        print(f"MISTAKES suggested {len(cuts)}, verified {len(ok)}", flush=True)
        cuts = ok
        if os.environ.get("QITAF_FORCE_CUT"):  # debugging: force a cut "a,b" to test the re-cut
            cuts = [tuple(map(int, os.environ["QITAF_FORCE_CUT"].split(",")))]
        drop = {i for a, b in cuts for i in range(a, b + 1)}
        if drop and len(drop) <= len(words) * 0.2:  # sanity cap: never remove more than a fifth of the words
            # delete from the mistake's first word to the next kept word, so the joins land between words
            dels = []
            for a, b in cuts:
                s0 = times[a][0] - 0.04
                e0 = times[b + 1][0] - 0.04 if b + 1 < len(words) else times[b][1]
                if e0 - s0 > 0.05:
                    dels.append((snap(max(0, s0)), snap(e0)))
            dels.sort()
            kp, t0 = [], 0.0
            for a, b in dels:
                if a > t0:
                    kp.append((t0, a))
                t0 = max(t0, b)
            kp.append((t0, duration))
            sp_ = os.path.join(assets, "speaker.mp4"); tmp = os.path.join(out, "speaker-premistake.mp4")
            os.replace(sp_, tmp)
            g2 = "".join(f"[0:v]trim=start={a}:end={b},setpts=PTS-STARTPTS[v{i}];[0:a]atrim=start={a}:end={b},asetpts=PTS-STARTPTS[a{i}];" for i, (a, b) in enumerate(kp))
            g2 += "".join(f"[v{i}][a{i}]" for i in range(len(kp))) + f"concat=n={len(kp)}:v=1:a=1[v][a]"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", tmp, "-filter_complex", g2, "-map", "[v]", "-map", "[a]",
                            "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                            "-movflags", "+faststart", sp_], check=True)

            def rm(x):
                acc = 0.0
                for a, b in kp:
                    if x < a:
                        return acc
                    if x <= b:
                        return acc + x - a
                    acc += b - a
                return acc
            post_map = rm
            removed = [" ".join(words[a:b + 1]) for a, b in cuts]  # kept for review in mistakes.json
            keep_i = [i for i in range(len(words)) if i not in drop]
            words = [words[i] for i in keep_i]; line_of = [line_of[i] for i in keep_i]; tok_of = [tok_of[i] for i in keep_i]
            times = [(round(rm(times[i][0]), 3), round(rm(times[i][1]), 3)) for i in keep_i]
            duration = round(sum(b - a for a, b in kp), 3)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", sp_, "-vn", "-ac", "1", "-ar", "16000", wav], check=True)
            with wave.open(wav) as wf:
                pcm = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
            json.dump({"removed": removed}, open(os.path.join(out, "mistakes.json"), "w"), ensure_ascii=False)
            print(f"MISTAKES removed {len(drop)} words in {len(cuts)} places", flush=True)

    # group into short caption lines: break on punctuation, pauses, or ~3-4 words
    # Qur'an words show the Mushaf text (Hafs from Tanzil, or the Warsh text you pasted), spread over the spoken words
    vw = {}
    for li in sorted(set(line_of)):
        idx = [i for i in range(len(words)) if line_of[i] == li and verse_of(i)]
        if idx:
            q = verse_of(idx[0]); vt = (q["warsh"] if QR == "warsh" else q["text"]).split(); n, m = len(idx), len(vt)
            for j, i in enumerate(idx):
                vw[i] = " ".join(vt[j * m // n:(j + 1) * m // n])
    caps, cur = [], []
    for i, (w, (s, e)) in enumerate(zip(words, times)):
        cur.append((vw.get(i, w), s, e))
        nxt = times[i + 1][0] if i + 1 < len(times) else None
        new_line = i + 1 < len(words) and line_of[i + 1] != line_of[i]  # never join two sentences
        q = i in vw
        if q:  # a verse: longer lines, break only where the verse or the line ends
            left = 0  # verse words still to come on this line: never leave one alone on the next caption
            while i + 1 + left in vw and line_of[i + 1 + left] == line_of[i]:
                left += 1
            brk = ((len(cur) >= 5 or len(" ".join(x[0] for x in cur)) > 34) and left != 1) or nxt is None or (i + 1 in vw) != q or new_line
        else:
            brk = len(cur) >= 4 or len(" ".join(x[0] for x in cur)) > 20 or re.search(r"[،.؟!:]$", w) or nxt is None or nxt - e > 0.35 or new_line or (i + 1 in vw)
        if brk:
            t = " ".join(x[0] for x in cur if x[0])
            caps.append({"t": t, "s": cur[0][1], "e": max(cur[-1][2], cur[0][1] + 0.3),
                         "w": [round(x[1], 3) for x in cur if x[0]], "l": line_of[i]})  # each word's start, for word-by-word animations
            if q:
                caps[-1]["q"] = QR
            cur = []
    for k, c in enumerate(caps):  # ﴿ opens a verse run, ﴾ closes it
        if c.get("q"):
            c["qo"] = not (k and caps[k - 1].get("q") and caps[k - 1]["l"] == c["l"])
            c["qc"] = not (k + 1 < len(caps) and caps[k + 1].get("q") and caps[k + 1]["l"] == c["l"])
    def src2cut(x):
        """Source-video time → time in the cut video (first play of that moment)."""
        acc = 0.0
        for a, b in keeps:
            if a <= x <= b:
                return post_map(acc + x - a)
            acc += b - a
        return None
    for li, ln in enumerate(text_lines):
        if not ln.get("pinned"):
            continue
        a, b = src2cut(ln["start"]), src2cut(ln["end"])
        if a is None or b is None or b <= a:
            continue
        group = [c for c in caps if c["l"] == li]
        nw = sum(len(c["w"]) for c in group) or 1; t, done = a, 0
        for c in group:  # share the window by word count, words evenly inside each caption
            span = (b - a) * len(c["w"]) / nw
            c["s"], c["e"] = round(t, 3), round(t + span, 3)
            c["w"] = [round(t + span * k / len(c["w"]), 3) for k in range(len(c["w"]))]
            t += span; done += len(c["w"])
        for c in group:
            c["pinned"] = True
    for li, ln in enumerate(text_lines):  # added lines: shown exactly between the times you gave them
        ws = ln["text"].split()
        if not ln.get("added") or not ws:
            continue
        a, b = src2cut(ln["start"]), src2cut(ln["end"])
        if a is None or b is None or b <= a:
            continue
        caps.append({"t": ln["text"], "s": round(a, 3), "e": round(b, 3), "w": [round(a + (b - a) * k / len(ws), 3) for k in range(len(ws))],
                     "l": li, "pinned": True})
    caps.sort(key=lambda c: c["s"])
    for a, b in zip(caps, caps[1:]):
        # never overlap the next line; bridge tiny gaps so captions don't flicker
        a["e"] = b["s"] if b["s"] - a["e"] < 0.25 else min(a["e"], b["s"])

    # voice loudness per frame, for the sound wave
    hop = sr // FPS
    env = [float(np.sqrt(np.mean(pcm[i:i + hop] ** 2))) for i in range(0, len(pcm), hop)]
    peak = max(env) or 1
    env = [round(min(1, v / peak * 1.4), 3) for v in env]

    json.dump({"duration": duration, "caps": caps, "env": env, "words": [[w, line_of[i], t[0], t[1]] for i, (w, t) in enumerate(zip(words, times))], "hook_end": round(post_map(sum(b - a for a, b in keeps[:hook_n])), 3) if len(ranges) > 1 and hook_n else 0},
              open(os.path.join(out, "build.json"), "w"), ensure_ascii=False)
    if os.path.exists(os.path.join(out, "caps_edited.json")):
        os.remove(os.path.join(out, "caps_edited.json"))  # a fresh cut makes old caption edits stale
else:
    B = json.load(open(os.path.join(out, "build.json")))
    duration, env, hook_end = B["duration"], B["env"], B["hook_end"]
    awords = B.get("words", [])
    ce = os.path.join(out, "caps_edited.json")
    caps = json.load(open(ce)) if os.path.exists(ce) else B["caps"]

# ---------- 4a. English subtitles: one per spoken line, translated by Claude (kept in en.json, so re-renders reuse it) ----------
def english(caps):
    if S.get("translate", "off") == "off" or not caps:
        return []
    lines = {}
    for c in caps:  # a line's Arabic is shown in several short captions; its English stays up for the whole line
        L = lines.setdefault(c["l"], {"ar": [], "s": c["s"], "e": c["e"], "q": False})
        L["ar"].append(c["t"]); L["s"] = min(L["s"], c["s"]); L["e"] = max(L["e"], c["e"]); L["q"] = L["q"] or bool(c.get("q"))
    order = sorted(lines, key=lambda k: lines[k]["s"])
    ep = os.path.join(out, "en.json"); cache = json.load(open(ep)) if os.path.exists(ep) else {}
    todo = [k for k in order if " ".join(lines[k]["ar"]) not in cache]
    if todo:
        progress(46, "Translating")
        prompt = ("Translate these lines from an Islamic lesson (Sunni, Arabic) into English subtitles. They are consecutive "
                  "pieces of one talk: read them all first, then translate each line faithfully and naturally so they read well "
                  "in sequence. Plain, dignified English; no additions, no commentary. Say «Allah», «the Prophet ﷺ», and keep "
                  "names as commonly written in English (Yusuf, Ya'qub). Lines marked [Q] are Qur'an: use the Sahih International "
                  "wording. Keep each line short enough for a subtitle.\n"
                  "The speech is spoken (often Gulf/Najdi) Arabic, not written Arabic — read it as a native listener would:\n"
                  "- «ما» before a past verb is usually a NEGATION in speech, also inside conditions: «ما استطعت» = «if you couldn't», "
                  "«ما قدرت» = «if you weren't able», «ما جاء» = «he didn't come». Decide from the surrounding lines; when a line "
                  "contrasts with the one before (if you can … if you can't …), the negation is almost certain.\n"
                  "- Never turn a negative into a positive or the reverse; if a line is unclear, keep its meaning literal.\n"
                  "Reply with JSON only: {\"<number>\": \"English\"}\n\n"
                  + "\n".join(f"{i}: {'[Q] ' if lines[k]['q'] else ''}{' '.join(lines[k]['ar'])}" for i, k in enumerate(order)))
        r = subprocess.run([CLAUDE, "-p", "--tools", "", "--output-format", "text"], input=prompt,
                           capture_output=True, text=True, cwd=job_dir, timeout=300)
        try:
            got = json.loads(re.search(r"\{.*\}", r.stdout, re.S).group(0))
            for i, k in enumerate(order):
                if str(i) in got:
                    cache[" ".join(lines[k]["ar"])] = re.sub(r"^\s*\[Q\]\s*", "", got[str(i)]).strip()  # the verse marker is ours, never shown
            json.dump(cache, open(ep, "w"), ensure_ascii=False, indent=1)
        except Exception:
            print("translation failed: " + r.stdout[-300:], flush=True)
    return [{"t": cache[" ".join(lines[k]["ar"])], "s": lines[k]["s"], "e": lines[k]["e"]}
            for k in order if " ".join(lines[k]["ar"]) in cache]


# ---------- 4b. zoom on what matters: Claude marks the key caption lines ----------
def pick_emphasis():
    ep = os.path.join(out, "emphasis.json")
    if os.path.exists(ep) and json.load(open(ep)).get("n") == len(caps):
        return json.load(open(ep))["idx"]
    progress(42, "Finding the key moments")
    prompt = ("These are the caption lines of a short Arabic Islamic lesson clip, numbered. Pick the lines where a zoom-in "
              "adds emphasis: the main point or punchline, a key term being defined, a Qur'an verse or hadith, a striking "
              "example, a question to the viewer, or a warning. Roughly one every 8-12 seconds, never two in a row, never "
              "filler or transitions. Reply with JSON only: {\"idx\":[numbers]}\n\n"
              + "\n".join(f"{i} [{c['s']:.1f}s] {c['t']}" for i, c in enumerate(caps)))
    try:
        r = subprocess.run([CLAUDE, "-p", "--tools", "", "--output-format", "text"], input=prompt,
                           capture_output=True, text=True, timeout=300, cwd=out)
        idx = sorted({int(i) for i in json.loads(re.search(r"\{.*\}", r.stdout, re.S).group(0))["idx"] if 0 <= int(i) < len(caps)})
    except Exception:
        # fallback: loudest caption lines (the speaker's own emphasis), spaced out
        loud = sorted(range(len(caps)), key=lambda i: -max(env[int(caps[i]["s"] * FPS):int(caps[i]["e"] * FPS) + 1] or [0]))
        idx = []
        for i in loud:
            if all(abs(caps[i]["s"] - caps[j]["s"]) > 8 for j in idx):
                idx.append(i)
        idx = sorted(idx[:max(1, int(duration // 10))])
    json.dump({"n": len(caps), "idx": idx}, open(ep, "w"))
    return idx


VIS = S.get("style") == "visualy"
emphasis = pick_emphasis() if S.get("zoom", "subtle") != "off" and caps and not VIS else []
if not REBUILD:
    awords = [[w, line_of[i], t[0], t[1]] for i, (w, t) in enumerate(zip(words, times))]
TITLE = clip.get("title") or ("" if S.get("titleAuto") else S.get("titleText", ""))
if not S.get("showTitle", True):
    TITLE = ""


def holy(w):
    """The word «الله» keeps its proper form, also inside والله، بالله، لله، عبدالله."""
    b = re.sub(r"[\u064b-\u0652\u0670\u0640]", "", w).replace("ٱ", "ا")
    return "الله" in b or bool(re.search(r"(^|[^\u0621-\u064a])[وف]?لله($|[^\u0621-\u064a])", b))


def madd(t, n):
    return re.sub(r"\S+", lambda m: m.group(0) if holy(m.group(0)) else madd_word(m.group(0), n), t or "")


def madd_word(t, n):
    """Stretch joined letters with ـ (same rule as the site preview): never after a non-joining letter, at a word's end, or inside لا."""
    n = int(n or 0)
    if not n:
        return t
    o, i = "", 0
    while i < len(t):
        c = t[i]; o += c
        if "\u0621" <= c <= "\u064a" and c not in "اأإآٱدذرزوؤةىءـ":
            while i + 1 < len(t) and ("\u064b" <= t[i + 1] <= "\u0652" or t[i + 1] == "\u0670"):
                i += 1; o += t[i]
            nx = t[i + 1] if i + 1 < len(t) else ""
            if "\u0621" <= nx <= "\u064a" and nx != "ء" and not (c == "ل" and nx in "اأإآ"):
                o += "ـ" * n
        i += 1
    return o


S["brand"] = S["outro"] = False  # «نهج الأثر» and the outro are off for good
TITLE = madd(TITLE, S.get("titleMadd"))
# the lesson's name, top right: typed, or from the upload's file name (the part before «｜», «|» or « - »)
_ln = S.get("lessonLabel", "")
def lesson_from_file(name):
    n = os.path.splitext(name)[0]
    if re.match(r"(?i)(whatsapp|img|vid|video|screen|mov|dsc)[ _-]", n):
        return ""  # a phone/device file name says nothing about the lesson
    m = re.search(r"بعنوان\s*[:：]?\s*(.+)", n)  # «… بعنوان: (أصول مهمة)» → the title itself
    t = m.group(1) if m else re.split(r"\s*[｜|]\s*|\s+-\s+", n)[0]
    return re.sub(r"[()（）\[\]«»\"]", "", t).strip(" ＊*_-:：")


S["lessonText"] = (S.get("lessonLabelText", "").strip() if _ln == "custom" else lesson_from_file(META["name"]) if _ln == "auto" else "")
S["speaker"] = "" if clip.get("hideName") else madd(clip.get("speaker") or S.get("speaker", ""), S.get("nameMadd"))  # a clip's own speaker (2+ speakers in one lesson) wins

# shared page assets (both styles)
shutil.copy(os.path.join(ASSETS, "gsap.min.js"), os.path.join(assets, "gsap.min.js"))
os.makedirs(os.path.join(assets, "sfx"), exist_ok=True)
for f in ("swoosh-in.wav", "tap.wav", "swoosh-out.wav"):
    shutil.copy(os.path.join(SFX, f), os.path.join(assets, "sfx", f))
for f in ("shutter.wav", "film.wav", "focus.wav"):  # Qitaf's own: the intro effects
    shutil.copy(os.path.join(SFX, f), os.path.join(assets, "sfx", f))
os.makedirs(os.path.join(assets, "fonts"), exist_ok=True)
for f in os.listdir(FONTS):
    shutil.copy(os.path.join(FONTS, f), os.path.join(assets, "fonts", f))

if not VIS:
    # ---------- 5. HyperFrames page ----------
    progress(45, "Building the video")

    total = duration + (4.0 if S.get("outro") else 0)
    rules = json.load(open(os.path.join(ROOT, "rules.json")))
    if RH != 1920:  # the reel safe zones are for Instagram's buttons; square and wide frames only need a margin
        rules["safe"] = {"top": .07, "bottom": .93, "left": .06, "right": .94}
        rules["slots"]["captions"]["y"] = .8; rules["slots"]["title_upper"]["y"] = .22; rules["slots"]["title_centre"]["y"] = .5
    _ic = json.load(open(os.path.join(ROOT, "pipeline", "icons.json")))  # Simple Icons (CC0) logo paths
    data = {"S": S, "R": rules, "D": duration, "TOTAL": round(total, 3), "EN": english(caps),
            "ICONS": {k: _ic[k] for k in S.get("socialIcons", []) if k in _ic},
            "CAPS": caps, "ENV": env, "TITLE": TITLE,
            "HOOK_END": json.load(open(os.path.join(out, "build.json")))["hook_end"], "EMPH": emphasis}
    html = open(os.path.join(ROOT, "pipeline", "template.html")).read()
    # Fade is static CSS: the renderer ignored it when set from JS. "auto" uses the colour the preview sampled.
    FADES = {"green": "#0f3b2a", "black": "#000000", "navy": "#0e1a33", "maroon": "#3d0f16", "brown": "#3b2516", "teal": "#0d3236",
             "plum": "#2c1433", "slate": "#1e2630", "olive": "#2b2f14", "amber": "#4a2a05", "ink": "#1F1F1D"}
    fade_css = "none"
    if S.get("fade", "green") != "none":
        hx = S.get("fadeCustom", "#14302a") if S.get("fade") == "custom" else S.get("fadeAuto", "#141414") if S.get("fade") == "auto" else FADES.get(S.get("fade"), "#141414")
        rgb = ",".join(str(int(hx[i:i + 2], 16)) for i in (1, 3, 5))
        # solid for the first third of its height, then eases out (same curve as the site preview, FADE_CURVE)
        a, h = S.get("fadeStrength", 70) / 100, S.get("fadeHeight", 40)
        stops = [(0, 1), (.35, 1), (.6, .75), (.8, .35), (1, 0)]
        grad = lambda d, a=a, h=h: f"linear-gradient({d}," + ",".join(f"rgba({rgb},{a * f:.3f}) {p * h:.1f}%" for p, f in stops) + ")"
        top = grad("to bottom", S.get("fadeTopStrength", 60) / 100, S.get("fadeTopHeight", 20))  # own, subtler size when both
        fade_css = {"bottom": grad("to top"), "top": grad("to bottom"),
                    "both": grad("to top") + "," + top}[S.get("fadeDir", "bottom")]
    blur_css = ""
    if S.get("fade") == "blur":
        # blur instead of colour: the video itself goes soft toward the edge (strength → blur radius), a light shade keeps text readable
        a, h = S.get("fadeStrength", 70) / 100, S.get("fadeHeight", 40)
        ta, th, d = S.get("fadeTopStrength", 60) / 100, S.get("fadeTopHeight", 20), S.get("fadeDir", "bottom")
        shade = lambda dr, aa, hh: f"linear-gradient({dr},rgba(0,0,0,{.28 * aa:.2f}) 0%,rgba(0,0,0,0) {hh}%)"
        fade_css = {"bottom": shade("to top", a, h), "top": shade("to bottom", a, h), "both": shade("to top", a, h) + "," + shade("to bottom", ta, th)}[d]
        lay = lambda side, aa, hh: (f"content:'';position:absolute;left:0;right:0;{side}:0;height:{hh}%;backdrop-filter:blur({4 + 26 * aa:.0f}px);"
                                    f"-webkit-backdrop-filter:blur({4 + 26 * aa:.0f}px);"
                                    f"mask-image:linear-gradient(to {'top' if side == 'bottom' else 'bottom'},#000 30%,transparent 100%);"
                                    f"-webkit-mask-image:linear-gradient(to {'top' if side == 'bottom' else 'bottom'},#000 30%,transparent 100%)")
        if d in ("bottom", "both"): blur_css += "#fade::before{" + lay("bottom", a, h) + "}"
        if d == "top": blur_css += "#fade::after{" + lay("top", a, h) + "}"
        if d == "both": blur_css += "#fade::after{" + lay("top", ta, th) + "}"
    html = html.replace("</style>", blur_css + "</style>", 1)
    fx = {"zoom": ("shutter", 0, 0.04), "film": ("film", 0, 0.03), "focus": ("focus", 0.55, 0.03)}.get(S.get("introFx"))  # soft: a hint, not a jolt
    if fx:  # the intro effect's sound: a camera shutter, a soft film whoosh, or the focus-lock beep as the picture goes sharp
        html = html.replace("<!--INTROFX-->", f'<audio id="introfx" src="assets/sfx/{fx[0]}.wav" data-start="{fx[1]}" data-duration="1" '
                                              f'data-track-index="32" data-volume="{fx[2]}"></audio>')
    he = json.load(open(os.path.join(out, "build.json")))["hook_end"]
    if he > 0.5:  # a quiet swoosh with the burn, where the hook hands over to the lesson
        html = html.replace("<!--HOOKFX-->", f'<audio id="hookfx" src="assets/sfx/swoosh-out.wav" data-start="{max(0, he - 0.3):.2f}" '
                                             f'data-duration="1.2" data-track-index="30" data-volume="0.35"></audio>')
    html = html.replace("__FADE__", fade_css).replace("width:1080px", f"width:{RW}px").replace("height:1920px", f"height:{RH}px") \
        .replace('data-width="1080" data-height="1920"', f'data-width="{RW}" data-height="{RH}"').replace("const W=1080,H=1920", f"const W={RW},H={RH}")
    html = html.replace("__DATA__", json.dumps(data, ensure_ascii=False)).replace("__D__", str(duration)).replace("__TOTAL__", str(round(total, 3)))
    open(os.path.join(out, "index.html"), "w").write(html)
    json.dump({"id": "qitaf", "name": data["TITLE"] or "clip", "width": RW, "height": RH, "fps": FPS}, open(os.path.join(out, "meta.json"), "w"), ensure_ascii=False)
    json.dump({"paths": {"assets": "assets"}}, open(os.path.join(out, "hyperframes.json"), "w"))

    out_render = out
else:
    # Motion graphic v2 (pipeline/motion.html, minimal look): Claude directs one growing visual metaphor; anchors -> times here.
    progress(45, "Planning the visuals")
    vd = os.path.join(out, "motion")
    os.makedirs(os.path.join(vd, "assets"), exist_ok=True)
    if TEXT_ONLY:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", str(duration),
                        os.path.join(vd, "assets", "voice.wav")], check=True)
    else:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", os.path.join(assets, "speaker.mp4"), "-vn", "-ac", "1", "-ar", "48000",
                        os.path.join(vd, "assets", "voice.wav")], check=True)
    for sub in ("fonts", "sfx"):
        shutil.copytree(os.path.join(assets, sub), os.path.join(vd, "assets", sub), dirs_exist_ok=True)
    shutil.copy(os.path.join(assets, "gsap.min.js"), os.path.join(vd, "assets", "gsap.min.js"))
    spoken = {}
    for w, l, *_ in awords:
        spoken.setdefault(l, []).append(w)
    sc = S.get("script", "").strip()
    prompt = open(os.path.join(ROOT, "pipeline", "motion_prompt.md")).read()
    for k, v in {"title": TITLE, "checklists": "" if S.get("checklists", True) else "(checklists are OFF: do not use list)",
                 "script": f"The user wrote what should appear on screen (use these points, in this order):\n{sc}\n" if sc else "",
                 "text": "\n".join(" ".join(ws) for ws in spoken.values())}.items():
        prompt = prompt.replace("{" + k + "}", v)

    def nrm(t):
        t = re.sub(r"[\u064b-\u0652\u0670\u0640]", "", t)
        t = re.sub(r"[^\u0621-\u064a]", "", t)
        return t.translate(str.maketrans("أإآىة", "ااايه"))
    NW = [nrm(w[0]) for w in awords]

    def resolve(plan):
        """Turn every anchor phrase into a time on the cut audio; anchors must move forward through the speech."""
        cur = [0]
        def find(spec):
            m = re.match(r"^(.*?)(?:#(\d+))?$", spec.strip()); nth = int(m.group(2) or 1)
            tg = [nrm(x) for x in m.group(1).split() if nrm(x)]
            hits = [i for i in range(cur[0], len(NW) - len(tg) + 1) if NW[i:i + len(tg)] == tg]
            if len(hits) < nth and attempt == 2:
                # last try: be forgiving: any later occurrence, then just the first word
                hits = hits[-1:] or [i for i in range(cur[0], len(NW)) if tg and NW[i] == tg[0]][:1]
                nth = 1
            if len(hits) < nth:
                if attempt == 2:
                    return None  # caller drops this step / places the scene between its neighbours
                raise ValueError(f"anchor not found in order: {spec!r} (after: {' '.join(w[0] for w in awords[cur[0]:cur[0] + 8])})")
            cur[0] = hits[nth - 1]
            return round(max(0, awords[hits[nth - 1]][2] - 0.1), 3)
        prev_t = 0.0
        for i, sc_ in enumerate(plan["scenes"]):
            t_ = 0.0 if i == 0 and "at" not in sc_ else find(sc_["at"])
            sc_["t"] = t_ if t_ is not None and (i == 0 or t_ > prev_t) else round(min(prev_t + 4, duration - 1), 3)
            prev_t = sc_["t"]
            for k in ("head", "sub", "track"):
                if sc_.get(k + "_at"):
                    v = find(sc_[k + "_at"])
                    if v is not None:
                        sc_[k + "_t"] = v
            steps = []
            for st in sc_.get("steps", []):
                st["t"] = find(st["at"]) if st.get("at") else sc_["t"] + 0.6
                if st["t"] is not None:
                    steps.append(st)
            sc_["steps"] = steps
        # a visual that carries over keeps the ground it was drawn on (its colours belong to that ground)
        for i, sc_ in enumerate(plan["scenes"]):
            if i and (sc_.get("prop") or {}).get("same"):
                sc_["bg"] = plan["scenes"][i - 1].get("bg", "cream")
        # the visual must keep changing: a scene that keeps the old visual has to move it
        flat = [i for i, sc_ in enumerate(plan["scenes"]) if i and (not sc_.get("prop") or sc_["prop"].get("same")) and not sc_.get("steps")]
        if flat and attempt < 2:
            raise ValueError(f"scenes {flat} keep the previous visual but change nothing; give each a new visual or at least one step")
        for i in flat:  # last try: a still scene becomes one big kinetic word from its heading
            sc_ = plan["scenes"][i]
            star = re.search(r"\*(.+?)\*", sc_.get("head", ""))
            sc_["prop"] = {"type": "word", "accent": True, "text": star.group(1) if star else sc_.get("head", "").replace("*", "")}
        return plan

    err = ""
    for attempt in range(3):  # feed anchor errors back to Claude
        r = subprocess.run([CLAUDE, "-p", "--tools", "", "--output-format", "text"], input=prompt + err,
                           capture_output=True, text=True, timeout=600, cwd=vd)
        m = re.search(r"\{.*\}", r.stdout, re.S)
        try:
            plan = resolve(json.loads(m.group(0)))
            break
        except Exception as e:
            err = f"\n\nYour last reply failed: {e}. Copy anchor words exactly, in spoken order, and reply with the full JSON again."
    else:
        sys.exit("Could not plan the motion graphic: " + err.strip()[-300:])
    if TITLE and plan["scenes"]:  # title on: it is the opening scene's heading only, never on top of later visuals
        plan["scenes"][0]["head"] = TITLE.replace("\n", " ")
    json.dump(plan, open(os.path.join(vd, "plan.json"), "w"), ensure_ascii=False, indent=1)
    # quiet SFX: soft swoosh when the ground changes, tap on visual steps
    ev, last_bg = [], None
    for sc_ in plan["scenes"]:
        if sc_.get("bg") != last_bg and sc_["t"] > 0.3:
            ev.append((sc_["t"] - 0.2, "swoosh-in.wav", 0.55, 0.2))
        last_bg = sc_.get("bg")
        ev += [(st["t"], "tap.wav", 0.18, 0.15) for st in sc_.get("steps", [])]
    ev.sort(); sfx, lt = [], -9
    for t, f, d, v in ev:
        if S.get("sfx") == "subtle" and t - lt >= 0.8:
            sfx.append(f'<audio id="sx{len(sfx)}" src="assets/sfx/{f}" data-start="{t:.2f}" data-duration="{d}" data-track-index="{10 + len(sfx)}" data-volume="{v}"></audio>'); lt = t
    total = round(duration + (4.0 if S.get("outro") else 0), 3)
    page = open(os.path.join(ROOT, "pipeline", "motion.html")).read()
    page = page.replace("__DATA__", json.dumps({"S": S, "R": json.load(open(os.path.join(ROOT, "rules.json"))), "D": duration,
                                                 "TOTAL": total, "PLAN": plan}, ensure_ascii=False))
    page = page.replace("__SFX__", "\n".join(sfx)).replace("__D__", str(duration)).replace("__TOTAL__", str(total))
    open(os.path.join(vd, "index.html"), "w").write(page)
    json.dump({"id": "qitaf", "name": TITLE or "clip", "width": 1080, "height": 1920, "fps": FPS}, open(os.path.join(vd, "meta.json"), "w"), ensure_ascii=False)
    json.dump({"paths": {"assets": "assets"}}, open(os.path.join(vd, "hyperframes.json"), "w"))
    out_render = vd

# ---------- 6. render ----------
if os.environ.get("QITAF_NO_RENDER"):  # debugging: stop after building the page
    sys.exit(0)
progress(50, "Rendering")
mp4 = os.path.join(out, "render.mp4")
# --gpu: the Mac's hardware encoder (≈40% quicker than software at the same quality setting)
p = subprocess.Popen(plat.hyperframes() + ["render", out_render, "-o", mp4, "-q", "high" if S.get("quality") == "1080" else "draft"] + (["--gpu"] if plat.MAC else []),
                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace", cwd=out_render)
tail = []
for line in p.stdout:
    tail = (tail + [line])[-20:]
    m = re.search(r"(\d{1,3})%", line)
    if m:
        progress(50 + int(m.group(1)) * 45 // 100, "Rendering")
if p.wait() != 0 or not os.path.exists(mp4):
    sys.exit("render failed: " + "".join(tail)[-400:])
if S.get("quality") == "720":
    small = os.path.join(out, "render-720.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", mp4, "-vf", "scale=trunc(iw*2/3/2)*2:trunc(ih*2/3/2)*2", "-c:a", "copy", small], check=True)
    os.replace(small, mp4)

# ---------- 7. deliver ----------
lesson = os.path.splitext(META["name"])[0]
dest_dir = os.path.join(plat.CLIPS, plat.safe_name(lesson))
try:  # this lesson's videos already live in a folder (maybe renamed in Finder): keep using that one
    _prev = [c.get("output") for c in json.load(open(os.path.join(job_dir, "status.json"))).get("clips", {}).values() if c.get("output")]
    _prev = [os.path.dirname(x) for x in _prev if os.path.exists(x)]
    if _prev:
        dest_dir = _prev[0]
except Exception:
    pass
os.makedirs(dest_dir, exist_ok=True)
safe = plat.safe_name((clip.get("title") or TITLE)[:60])
tag = (" (motion)" if VIS else "") + ("" if (RW, RH) == (1080, 1920) else f" ({S.get('ratio')})")
dest = os.path.join(dest_dir, f"{clip_id:02d} - {safe}{tag}.mp4")
shutil.copy(mp4, dest)
if os.path.exists(os.path.join(out, "raw.mp4")):
    os.makedirs(os.path.join(dest_dir, "raw"), exist_ok=True)  # raws live in their own folder beside the finished videos
    shutil.copy(os.path.join(out, "raw.mp4"), os.path.join(dest_dir, "raw", f"{clip_id:02d} - {safe} (raw).mp4"))
print("OUTPUT " + dest, flush=True)
progress(100, "Done")
