#!/bin/zsh
# Qitaf setup for Mac (Apple Silicon). Safe to run again.
cd "$(dirname "$0")" || exit 1
set -e
if [[ "$(uname -m)" != "arm64" ]]; then echo "Qitaf needs a Mac with Apple Silicon (M1 or newer)."; exit 1; fi
if ! command -v brew >/dev/null; then
  echo "Installing Homebrew (it may ask for your Mac password)"
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  eval "$(/opt/homebrew/bin/brew shellenv)"
fi
for pkg in git node ffmpeg python@3.12; do brew list "$pkg" >/dev/null 2>&1 || command -v "${pkg%@*}" >/dev/null || brew install "$pkg"; done
PY=$(command -v python3.12 || echo /opt/homebrew/bin/python3.12)

echo "Installing Qitaf's parts (a few GB, this takes a while)"
[[ -d .venv ]] || "$PY" -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
npm install
node node_modules/hyperframes/bin/hyperframes.mjs browser ensure

echo "Downloading the speech models now, so your first video doesn't wait for them"
.venv/bin/python -X utf8 -c "from huggingface_hub import snapshot_download; snapshot_download('mlx-community/whisper-large-v3-mlx')"
.venv/bin/python -X utf8 -c "import torchaudio; torchaudio.pipelines.MMS_FA.get_model(with_star=False)"

echo "Getting the Warsh Qur'an font"
curl -fsSL -o "fonts/Almaghribi Warsh-Quran.otf" "https://app.al-mushaf.com/_content/quranRCL/ressources/fonts/AALMAGHRIBI_v4.9.6.otf" || echo "Warsh font not downloaded: Warsh verses need it. Run setup again later."

DESK="${QITAF_DESKTOP:-$HOME/Desktop}"
printf '#!/bin/zsh\nexec "%s/Start Qitaf.command"\n' "$PWD" > "$DESK/Qitaf.command"
chmod +x "$DESK/Qitaf.command"

.venv/bin/python -X utf8 check.py
echo
echo "Done. Double-click Qitaf on your Desktop. Help is inside Qitaf, top right."
