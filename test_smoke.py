"""End-to-end check on this computer: python -X utf8 test_smoke.py
Makes a test video, then a reel and all three YouTube layouts, into a folder with an Arabic name. Claude isn't needed to pass."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
JOB = "abcdefabcdef"
d = os.path.join(ROOT, "jobs", JOB)
out = os.path.join(tempfile.mkdtemp(), "قطاف مقاطع")
env = {**os.environ, "QITAF_CLIPS": out, "PYTHONUTF8": "1"}
shots = os.environ.get("QITAF_SHOTS") or os.path.join(ROOT, "smoke-shots")
os.makedirs(shots, exist_ok=True)


def run(*a):
    print("→", os.path.basename(a[1]) if len(a) > 1 else a[0], *a[3:], flush=True)
    r = subprocess.run(a, env=env, capture_output=True, text=True, errors="replace", cwd=ROOT)
    if r.returncode:
        print(r.stdout[-1500:], r.stderr[-1500:], sep="\n")
        sys.exit(f"FAILED: {a[1]}")
    return r.stdout


def check(video, name):
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration", "-of", "json", video],
                       capture_output=True, text=True, errors="replace")
    j = json.loads(p.stdout)
    assert {s["codec_type"] for s in j["streams"]} == {"video", "audio"}, j
    assert float(j["format"]["duration"]) > 5, j
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "6", "-i", video, "-frames:v", "1", os.path.join(shots, name + ".jpg")], check=True)
    print("OK", name, j["streams"][0].get("width"), j["streams"][0].get("height"), flush=True)


shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=1280x720:r=30:d=16", "-f", "lavfi", "-i", "sine=f=220:d=16",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", os.path.join(d, "source.mp4")], check=True)
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", os.path.join(d, "source.mp4"), "-vn", "-ac", "1", "-ar", "16000", os.path.join(d, "audio.wav")], check=True)
lines = ["الحمد لله رب العالمين", "قل إن تخفوا ما في صدوركم أو تبدوه يعلمه الله", "هذا درس في العلم النافع", "والله أعلم"]
segs = []
for i, t in enumerate(lines):
    w = t.split(); a = i * 4 + .3; step = 3.4 / len(w)
    segs.append({"start": a, "end": a + 3.4, "text": t, "words": [{"text": x, "start": a + k * step, "end": a + (k + 1) * step} for k, x in enumerate(w)]})
json.dump({"language": "ar", "segments": segs}, open(os.path.join(d, "transcript.json"), "w"), ensure_ascii=False)
json.dump({"name": "زز اختبار. ｜ درس..mp4"}, open(os.path.join(d, "meta.json"), "w"), ensure_ascii=False)
S = json.load(open(os.path.join(ROOT, "presets.default.json"), encoding="utf-8"))["الرحيلي"]
S.update(source="video", mode="single", ratio="9:16", translate="off", quality="720", coverIntro=False, hookFirst=False, cutMistakes=False)
clip = {"id": 1, "start": 0, "end": 15.8, "title": "اختبار قطاف", "reason": "", "keep": True}
json.dump({"clips": [clip]}, open(os.path.join(d, "clips.json"), "w"), ensure_ascii=False)
json.dump(S, open(os.path.join(d, "settings.json"), "w"), ensure_ascii=False)

py = sys.executable
if os.environ.get("QITAF_WHISPER"):
    run(py, os.path.join(ROOT, "pipeline", "transcribe.py"), os.path.join(d, "audio.wav"), os.path.join(d, "t.json"))
    assert "segments" in json.load(open(os.path.join(d, "t.json"), encoding="utf-8"))
    print("OK transcribe", flush=True)

o = run(py, os.path.join(ROOT, "pipeline", "render_clip.py"), d, "1")
check(next(l[7:] for l in o.splitlines() if l.startswith("OUTPUT ")).strip(), "reel")

for layout in ("band", "board", "sound"):
    # the style options: a font, sizes, colours, no box, and a non-default wave
    S.update(ytSubFont="Cairo", ytSubSize=120, ytSubColour="#FDE68A", ytSubBox="none" if layout == "band" else "auto", ytTitleFont="Amiri", ytTitleSize=120, ytNameFont="Cairo", ytWave="dots")
    S.update(quranReading="warsh" if layout == "sound" else "hafs", style="youtube", ytLayout=layout, ytTheme="navy", ytSubs=True, ytHandle="@test", speaker="الشيخ فلان", titleText="عنوان الاختبار")
    json.dump(S, open(os.path.join(d, "settings.json"), "w"), ensure_ascii=False)
    o = run(py, os.path.join(ROOT, "pipeline", "youtube.py"), d, "1")
    v = next(l[7:] for l in o.splitlines() if l.startswith("OUTPUT ")).strip()
    check(v, "youtube-" + layout)
    assert os.path.exists(v[:-4] + " thumbnail 1.jpg") and os.path.exists(v[:-4] + ".srt")
    if layout == "sound":  # this pass uses Warsh: the verse must come from al-mushaf.com, with its own reading
        assert "قُلِ" in open(v[:-4] + ".srt", encoding="utf-8").read(), "no Warsh text"
    if layout != "sound":  # the frame must be fully painted: the bottom edge is the ground colour, never black
        g = subprocess.run(["ffmpeg", "-v", "error", "-ss", "6", "-i", v, "-frames:v", "1", "-vf", "crop=1920:8:0:1068,scale=1:1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
        assert sum(g) > 60, f"unpainted board edge: {list(g)}"
    shutil.copy(v[:-4] + " thumbnail 1.jpg", os.path.join(shots, f"thumb-{layout}.jpg"))

srv = subprocess.Popen([py, "-X", "utf8", "server.py"], env={**env, "QITAF_PORT": "8797"}, cwd=ROOT)
try:
    time.sleep(4)
    for path in ("/", "/guide", "/i18n.js", "/yt/frame", "/api/library", "/api/presets"):
        assert urllib.request.urlopen("http://localhost:8797" + path).status == 200, path
    lib = json.load(urllib.request.urlopen("http://localhost:8797/api/library"))
    assert any(r["job"] == JOB and r["videos"] for r in lib), "the library can't see the finished videos"
    print("OK server and library", flush=True)
finally:
    srv.terminate()
shutil.rmtree(d, ignore_errors=True)
print("ALL PASSED")
