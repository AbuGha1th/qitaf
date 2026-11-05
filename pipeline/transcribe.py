"""Transcribe a job's audio with word timestamps (Arabic). MLX Whisper on a Mac, faster-whisper elsewhere.

Usage: python transcribe.py <audio.wav> <out.json>
Progress goes to stderr as "NN%| frames"; the server reads the percentages.
"""
import glob
import json
import os
import sys

audio, out = sys.argv[1], sys.argv[2]


def mlx():
    import mlx_whisper
    result = mlx_whisper.transcribe(
        audio,
        path_or_hf_repo="mlx-community/whisper-large-v3-mlx",
        language="ar",
        word_timestamps=True,
        condition_on_previous_text=False,  # avoids repetition loops on long audio
        verbose=False,
    )
    return [{"start": s["start"], "end": s["end"], "text": s["text"],
             "words": [{"text": w["word"], "start": w["start"], "end": w["end"]} for w in s.get("words", [])]}
            for s in result["segments"]]


def faster():
    import wave

    import ctranslate2
    import numpy as np
    from faster_whisper import WhisperModel
    # the graphics card's libraries come as pip packages; Windows has to be told where they are
    for d in glob.glob(os.path.join(sys.prefix, "Lib", "site-packages", "nvidia", "*", "bin")):
        os.add_dll_directory(d); os.environ["PATH"] = d + os.pathsep + os.environ["PATH"]
    size = os.environ.get("QITAF_WHISPER", "large-v3")
    # our audio is always 16 kHz mono PCM: read it directly, the library's own decoder breaks on newer PyAV releases
    with wave.open(audio) as w:
        pcm = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768

    def run(device, kind):
        segs, info = WhisperModel(size, device=device, compute_type=kind).transcribe(
            pcm, language="ar", word_timestamps=True, condition_on_previous_text=False, beam_size=5)
        res = []
        for s in segs:  # a generator: the work happens here, so progress is real
            print(f"{min(99, int(s.end / info.duration * 100))}%| frames", file=sys.stderr, flush=True)
            res.append({"start": s.start, "end": s.end, "text": s.text,
                        "words": [{"text": w.word, "start": w.start, "end": w.end} for w in s.words or []]})
        return res

    if ctranslate2.get_cuda_device_count():
        try:
            return run("cuda", "float16")
        except Exception as e:  # a card too old or missing libraries: slower, but still works
            print(f"graphics card failed ({str(e)[:120]}), using the processor", file=sys.stderr, flush=True)
    return run("cpu", "int8")


try:
    raw = mlx() if sys.platform == "darwin" and not os.environ.get("QITAF_WHISPER") else faster()
except ImportError as e:
    sys.exit(f"transcription is not installed: {e}")
segments = [
    {"start": round(s["start"], 3), "end": round(s["end"], 3), "text": s["text"].strip(),
     "words": [{"text": w["text"].strip(), "start": round(w["start"], 3), "end": round(w["end"], 3)} for w in s["words"]]}
    for s in raw if s["text"].strip()
]
with open(out, "w", encoding="utf-8") as f:
    json.dump({"language": "ar", "segments": segments}, f, ensure_ascii=False, indent=1)
