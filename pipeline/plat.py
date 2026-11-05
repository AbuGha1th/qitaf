"""Everything that differs between Mac and Windows, in one place. The rest of Qitaf calls these."""
import functools
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time

WIN, MAC = sys.platform == "win32", sys.platform == "darwin"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = os.path.join(ROOT, "fonts")
ASSETS = os.path.join(ROOT, "assets")
CLIPS = os.path.realpath(os.environ.get("QITAF_CLIPS") or os.path.expanduser("~/Qitaf/clips"))
CLAUDE = shutil.which("claude") or "claude"  # on Windows this may be claude.cmd, which needs its full name
AAC = "aac_at" if MAC else "aac"
os.environ["PYTHONUTF8"] = "1"  # Arabic everywhere: child scripts must not fall back to the Windows code page


# whose channel the AI writes for: set once at install, see CLAUDE.md
_ch = os.path.join(ROOT, "channel.json")
CHANNEL = json.load(open(_ch, encoding="utf-8")) if os.path.exists(_ch) else {}


def channel(en=False):
    """The channel as a phrase for the prompts. Empty is fine: nothing is ever credited to a name nobody chose."""
    n = CHANNEL.get("name_en" if en else "name") or CHANNEL.get("name")
    return f"the channel {n}" if n else "an Islamic lessons channel"


def url(path):
    """file:// address of a local file; Windows drive letters and Arabic folders included."""
    return pathlib.Path(path).resolve().as_uri()


def _browser():
    pf = [os.environ.get(k, "") for k in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA")]
    win = [os.path.join(p, s) for p in pf if p for s in ("Google/Chrome/Application/chrome.exe", "Microsoft/Edge/Application/msedge.exe",
                                                          "BraveSoftware/Brave-Browser/Application/brave.exe")]
    mac = [f"/Applications/{a}.app/Contents/MacOS/{a}" for a in ("Google Chrome", "Brave Browser", "Microsoft Edge")]
    found = next((b for b in (win if WIN else mac) if os.path.exists(b)), None) or shutil.which("google-chrome")
    if not found:
        raise RuntimeError("Qitaf needs Chrome, Edge or Brave to draw covers and thumbnails")
    return found


BROWSER = os.environ.get("QITAF_BROWSER") or _browser()


def screenshot(page, dest, w, h):
    """Draw a page to an image. The drawing area is shorter than the window on Windows, so draw tall and crop to size."""
    tall = dest + ".tall.png"
    subprocess.run([BROWSER, "--headless", "--disable-gpu", "--hide-scrollbars", "--allow-file-access-from-files", "--force-device-scale-factor=1",
                    "--default-background-color=00000000", f"--window-size={w},{h + 200}", "--virtual-time-budget=20000",
                    f"--screenshot={tall}", page], capture_output=True, timeout=120)
    if os.path.exists(tall):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", tall, "-vf", f"crop={w}:{h}:0:0", dest], check=True)
        os.remove(tall)


def hyperframes():
    """The video renderer. Run through node: Windows can't start the .bin script directly."""
    pkg = os.path.join(ROOT, "node_modules", "hyperframes")
    b = json.load(open(os.path.join(pkg, "package.json")))["bin"]
    return [shutil.which("node") or "node", os.path.join(pkg, b if isinstance(b, str) else b["hyperframes"])]


@functools.cache
def _encoder():
    for enc in (["h264_videotoolbox"] if MAC else ["h264_nvenc", "h264_qsv", "h264_amf"]):
        r = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=s=256x256:d=0.2", "-c:v", enc, "-f", "null", "-"], capture_output=True)
        if r.returncode == 0:
            return enc
    return "libx264"


def video_args(rate):
    """ffmpeg's H.264 settings: the graphics card's encoder when there is one, else the processor."""
    enc = _encoder()
    if enc == "libx264":
        return ["-c:v", enc, "-preset", "veryfast", "-crf", "20"]
    return ["-c:v", enc, "-b:v", rate, "-maxrate", "14M", "-profile:v", "high"]


def safe_name(name):
    """A file or folder name every system accepts. Windows refuses \\ / : * ? " < > | and a trailing dot or space."""
    return re.sub(r'[\\/:*?"<>|\n\r\t]', " ", name).strip(" .")[:80].strip(" .") or "video"


def swap(src, dest):
    """Move a finished file into place. Windows refuses while the browser is still reading the old one, so wait for it."""
    for i in range(20):
        try:
            return shutil.move(src, dest) if os.path.splitdrive(src)[0] != os.path.splitdrive(dest)[0] else os.replace(src, dest)
        except PermissionError:
            if i == 19:
                raise
            time.sleep(.5)


def reveal(path):
    subprocess.run(["explorer", "/select,", os.path.normpath(path)] if WIN else ["open", "-R", path])


def notify(msg):
    if MAC:  # shortcut: no Windows toast, the Videos page shows the same state
        subprocess.run(["osascript", "-e", f'display notification "{msg}" with title "Qitaf" sound name "Glass"'])


def file_comment(video, text):
    if MAC:  # Finder's comment field; Windows has no equivalent, the text is inside the file and beside it
        esc = text.replace("\\", "\\\\").replace('"', '\\"')
        subprocess.run(["osascript", "-e", f'tell application "Finder" to set comment of (POSIX file "{video}" as alias) to "{esc}"'], capture_output=True)


def trash(path, name):
    if WIN:
        from send2trash import send2trash
        send2trash(os.path.normpath(path))
    else:
        shutil.move(path, os.path.join(os.path.expanduser("~/.Trash"), name))


_PS = ["powershell", "-NoProfile", "-NonInteractive", "-Command"]


def arabic_voices():
    """Arabic computer voices. Mac: Majed by default. Windows: only after adding Arabic speech in Settings → Time & language."""
    if WIN:
        out = subprocess.run(_PS + ["Add-Type -AssemblyName System.Speech;(New-Object System.Speech.Synthesis.SpeechSynthesizer).GetInstalledVoices()"
                                    "|%{$_.VoiceInfo.Culture.Name+'|'+$_.VoiceInfo.Name}"], capture_output=True, text=True, errors="replace").stdout
        return [l.split("|", 1)[1].strip() for l in out.splitlines() if l.lower().startswith("ar")]
    out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True).stdout
    return [re.split(r"\s{2,}", l.strip())[0] for l in out.splitlines() if re.search(r"\bar_\w+", l)]


def speak(text, voice, rate, path):
    """Read text aloud into an audio file, with a pause between lines so the visuals have room to change."""
    if WIN:
        txt = path + ".txt"
        open(txt, "w", encoding="utf-8").write(text.replace("\n", " . "))
        ps = ("Add-Type -AssemblyName System.Speech;$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;$s.SelectVoice($env:Q_VOICE);"
              "$s.Rate=[int]$env:Q_RATE;$s.SetOutputToWaveFile($env:Q_OUT);$s.Speak([IO.File]::ReadAllText($env:Q_TXT));$s.Dispose()")
        subprocess.run(_PS + [ps], check=True, env={**os.environ, "Q_VOICE": voice, "Q_RATE": str(max(-10, min(10, (int(rate) - 175) // 8))), "Q_OUT": path, "Q_TXT": txt})
        return
    subprocess.run(["say", "-v", voice, "-r", str(int(rate)), "-o", path, "[[slnc 450]]".join(text.split("\n"))], check=True)
