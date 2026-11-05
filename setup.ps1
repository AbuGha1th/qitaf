# Qitaf setup for Windows. Safe to run again. From this folder:  powershell -ExecutionPolicy Bypass -File setup.ps1
$ErrorActionPreference = "Stop"
function Need($cmd, $id) {
  if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
    Write-Host "Installing $id"
    winget install -e --id $id --accept-package-agreements --accept-source-agreements
  }
}
function Refresh { $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User") }
Need git Git.Git
Need node OpenJS.NodeJS.LTS
Need ffmpeg Gyan.FFmpeg
Need py Python.Python.3.12
Refresh
if (-not (py -3.12 --version 2>$null)) { winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements; Refresh }

Write-Host "Installing Qitaf's parts (a few GB, this takes a while)"
if (-not (Test-Path .venv)) { py -3.12 -m venv .venv }
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\pip install -r requirements.txt
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) { .venv\Scripts\pip install nvidia-cublas-cu12 nvidia-cudnn-cu12 }
npm install
node node_modules\hyperframes\bin\hyperframes.mjs browser ensure

Write-Host "Downloading the speech models now, so your first video doesn't wait for them"
.venv\Scripts\python -X utf8 -c "from faster_whisper import WhisperModel; WhisperModel('large-v3', device='cpu', compute_type='int8')"
.venv\Scripts\python -X utf8 -c "import torchaudio; torchaudio.pipelines.MMS_FA.get_model(with_star=False)"

Write-Host "Getting the Warsh Qur'an font"
try { Invoke-WebRequest "https://app.al-mushaf.com/_content/quranRCL/ressources/fonts/AALMAGHRIBI_v4.9.6.otf" -OutFile "fonts\Almaghribi Warsh-Quran.otf" } catch { Write-Host "Warsh font not downloaded: Warsh verses need it. Run setup again later." }

$here = (Get-Location).Path
$link = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path ([Environment]::GetFolderPath("Desktop")) "Qitaf.lnk"))
$link.TargetPath = Join-Path $here "Start Qitaf.bat"
$link.WorkingDirectory = $here
$link.Save()

.venv\Scripts\python -X utf8 check.py
Write-Host ""
Write-Host "Done. Double-click Qitaf on your Desktop. Help is inside Qitaf, top right."
