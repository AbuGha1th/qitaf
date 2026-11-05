"""Is this computer ready for Qitaf? Prints one line per part; exits with an error if something needed is missing."""
import importlib
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pipeline"))
bad = 0


def line(ok, what, fix=""):
    global bad
    bad += not ok
    print(("OK      " if ok else "MISSING ") + what + ("" if ok else f"  → {fix}"))


line(shutil.which("ffmpeg"), "ffmpeg", "install ffmpeg")
line(shutil.which("node"), "Node.js", "install Node.js 22 or newer")
line(shutil.which("claude"), "Claude Code", "install Claude Code and sign in")
for m in ["numpy", "cv2", "torch", "torchaudio", "mlx_whisper" if sys.platform == "darwin" else "faster_whisper"]:
    try:
        importlib.import_module(m); line(True, m)
    except ImportError:
        line(False, m, "pip install -r requirements.txt")
try:
    import plat
    line(True, "browser: " + plat.BROWSER)
    line(os.path.isfile(plat.hyperframes()[1]), "HyperFrames renderer", "npm install")
    print("        video encoder: " + plat.video_args("9M")[1])
except Exception as e:
    line(False, "browser or renderer", str(e))
fonts = len([f for f in os.listdir(os.path.join(plat.ROOT, "fonts")) if f.lower().endswith((".woff2", ".ttf", ".otf"))])
print(f"        fonts in fonts/: {fonts}")
sys.exit(1 if bad else 0)
