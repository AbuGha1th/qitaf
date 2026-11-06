"""Warsh text for a verse found in the Hafs text, from the Mohammed VI Foundation's digital Mushaf (al-mushaf.com).

Warsh counts verses differently from Hafs (Al-Baqarah has 285, not 286), so a verse number can't be looked up directly.
The verse is found by its words near where it should be, and a poor match returns None: the box stays empty for the user
rather than showing the wrong verse. The site's text is written for its own font, so it's kept exactly as given.
A surah is downloaded once and kept in quran/warsh/. shortcut: this is the site's app data, not a published API; if it changes, the paste box still works.
"""
import difflib
import json
import os
import re
import subprocess
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "quran", "warsh")
API = "https://quranapi.al-mushaf.com/api/Quran/"
VER = "mushafid=1&version=5.2.22"
MIN_MATCH = .8
_FOLD = str.maketrans({"ٱ": "ا", "أ": "ا", "إ": "ا", "آ": "ا", "ﹹ": "ا", "è": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي", "چ": "ل", "ﻟ": "ل", "ڤ": "ل", "ژ": "ك", "ڢ": "ف", "ڡ": "ف", "ٯ": "ق", "ں": "ن"})


def _get(path):
    # curl, not urllib: some Python installs have no certificates and every download would fail
    return subprocess.run(["curl", "-fsSL", "-m", "30", "-A", "Qitaf", API + path], capture_output=True, check=True).stdout.decode("utf-8")


def skeleton(word):
    """Letters only, without long vowels and hamza: what Hafs and Warsh spellings of one word have in common."""
    w = word.replace("ﻟ﮲", "لذ").translate(_FOLD)  # the site's one-symbol «الذي»
    return re.sub(r"(.)\1\1", r"\1", re.sub(r"[^ب-ي]|[يو]", "", w.replace("ـ", "")))  # tripled letters are font codes for one letter


def _surahs():
    """[(first page, verses)] per surah, in order."""
    p = os.path.join(CACHE, "surahs.json")
    if not os.path.exists(p):
        os.makedirs(CACHE, exist_ok=True)
        rows = json.loads(_get("ListSurat/" + VER))
        json.dump(rows, open(p, "w", encoding="utf-8"), ensure_ascii=False)
    return json.load(open(p, encoding="utf-8"))


def _key(row, *names):
    return next(row[k] for k in row for n in names if k.lower() == n)


def words(sura):
    """Every word of a surah, in order, as the site writes them. Verse numbers and hizb marks are left out."""
    p = os.path.join(CACHE, f"{sura}.json")
    if os.path.exists(p):
        return json.load(open(p, encoding="utf-8"))
    rows = _surahs()
    first = [_key(r, "pagenum", "startpage", "pagenumber") for r in rows]
    counts = [_key(r, "ayatcount", "ayacount", "ayascount", "versescount", "numberofayat") for r in rows]
    lo = sum(counts[:sura - 1]) + 1; hi = lo + counts[sura - 1] - 1  # the site numbers verses straight through the Qur'an
    last = first[sura] if sura < len(first) else first[-1]
    out = []
    for page in range(first[sura - 1], last + 1):
        for line in _get(f"QuranPageWordsContentByPageNum/pagenum={page}&{VER}").split("\n"):
            f = line.split("‖")
            if len(f) < 5 or not f[1].isdigit() or " aya " in f[3] or "suraTitle" in f[3]:
                continue
            # anything in an Arabic block is a word, however it's encoded: only marks like ® are left out
            if lo <= int(f[1]) <= hi and re.search(r"[\u0600-\u06FF\uFB50-\uFEFF]", f[4]):
                out.append(f[4].strip())
        time.sleep(.1)  # be gentle with their server
    if not out:
        raise RuntimeError(f"no words for surah {sura}")
    json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False)
    return out


_HAFS = {}


def _hafs_offsets(sura):
    """{verse: its first word's position in the surah}, and the surah's word count, from the Hafs text."""
    if not _HAFS:
        for l in open(os.path.join(ROOT, "quran", "uthmani.txt"), encoding="utf-8"):
            f = l.rstrip("\n").split("|")
            if len(f) == 3:
                d = _HAFS.setdefault(int(f[0]), {"at": {}, "n": 0})
                d["at"][int(f[1])] = d["n"]; d["n"] += len(f[2].split())
    return _HAFS[sura]


def lookup(q):
    """The Warsh words for {"ref": "3:29", "text": Hafs words}, or None if they can't be found with confidence."""
    m = re.match(r"(\d+):(\d+)", q.get("ref") or "")
    if not m or not q.get("text"):
        return None
    sura, aya = int(m.group(1)), int(m.group(2))
    try:
        ww = words(sura)
    except Exception as e:
        print("Warsh text unavailable: " + str(e)[:120], flush=True)
        return None
    hw = [s for s in map(skeleton, q["text"].split()) if s]
    h = _hafs_offsets(sura)
    want = "".join(hw); sk = [skeleton(w) for w in ww]
    expect = h["at"].get(aya, 0) / max(1, h["n"]) * len(ww)
    reach = max(80, len(ww) // 12, len(hw) * 2)
    best = (0, 0, 0, 0)  # (match, closeness to where the verse should be, start, length)
    for i in range(max(0, int(expect) - reach), min(len(ww), int(expect) + reach)):
        for n in range(max(1, len(hw) - 2), len(hw) + 3):
            r = difflib.SequenceMatcher(None, want, "".join(sk[i:i + n]), autojunk=False).ratio()
            c = (round(r, 3), -abs(i - expect))
            if c > best[:2]:
                best = (*c, i, n)
    if best[0] < MIN_MATCH:
        return None
    # a long verse scores well even with its first words missing, so pin both ends on the words themselves
    i, n = best[2:]
    k = min(4, len(hw))
    like = lambda a, b: difflib.SequenceMatcher(None, "".join(a), "".join(b), autojunk=False).ratio()
    far = max(8, len(hw) // 3)  # repetitive verses can pull the first search well off its true start
    start = max(range(max(0, i - far), min(len(ww), i + far + 1)), key=lambda s: (round(like(hw[:k], sk[s:s + k]) + like(hw[:1], sk[s:s + 1]), 3), -abs(s - i)))
    end = max(range(max(start + 1, start + len(hw) - far), min(len(ww), start + len(hw) + far) + 1),
              key=lambda e: (round(like(hw[-k:], sk[max(start, e - k):e]) + like(hw[-1:], sk[e - 1:e]), 3), -abs(e - start - len(hw))))
    if like(hw[:k], sk[start:start + k]) < MIN_MATCH or like(hw[-k:], sk[max(start, end - k):end]) < MIN_MATCH:
        return None
    return " ".join(ww[start:end])


if __name__ == "__main__":
    import sys
    print(lookup({"ref": sys.argv[1], "text": " ".join(sys.argv[2:])}))
