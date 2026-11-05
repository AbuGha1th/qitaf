"""Find Qur'an recitation inside transcript lines and give back the exact Uthmani (Hafs) words.

Matching runs on Tanzil's simple-clean text (no harakat), and each matched word maps to the same word in
Tanzil's Uthmani text, so the caption shows the real Mushaf spelling, never what Whisper heard.
Only runs of 4+ words count (one misheard word inside a run is tolerated and corrected), so ordinary
speech is never mistaken for a verse; shorter quotes are ticked by hand on the clips page.
"""
import os, re

QDIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "quran")
MIN_RUN = 4
_IDX = None


def norm(w):
    w = re.sub(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]", "", w)
    w = re.sub(r"[^ء-يٱ]", "", w)
    for a, b in (("أإآٱ", "ا"), ("ى", "ي"), ("ة", "ه"), ("ؤ", "و"), ("ئ", "ي")):
        w = re.sub("[" + a + "]", b, w)
    return w


def merge_voc(words):
    """Tanzil's Uthmani writes يَـٰٓأَيُّهَا as one word; join a standalone يا / ها onto the next word to match."""
    o = []
    for w in words:
        if o and norm(o[-1][1]) in ("يا", "ها", "ويا"):
            o[-1] = (o[-1][0] + [w[0]], o[-1][1] + w[1])
        else:
            o.append(([w[0]], w[1]))
    return o


def _load():
    global _IDX
    if _IDX:
        return _IDX
    rows = lambda f: [l.rstrip("\n").split("|") for l in open(os.path.join(QDIR, f), encoding="utf-8") if l.count("|") == 2]
    stream, uth = [], []  # one entry per word across the whole Qur'an: (sura, aya, normalised word)
    for (s, a, ut), (_, _, sc) in zip(rows("uthmani.txt"), rows("simple-clean.txt")):
        sw = [n for _, n in ((None, norm("".join(p))) for p, _ in merge_voc([(w, w) for w in sc.split()]))]
        uw = [w for w in ut.split() if re.search(r"[ء-يٱ]", w)]
        if len(uw) != len(sw):  # 2 ayat spell differently; spread the Uthmani words over them
            uw = [" ".join(uw[k * len(uw) // len(sw):(k + 1) * len(uw) // len(sw)]) for k in range(len(sw))]
        for n, u in zip(sw, uw):
            stream.append((int(s), int(a), n)); uth.append(u)
    tri = {}
    for i in range(len(stream) - 2):
        tri.setdefault((stream[i][2], stream[i + 1][2], stream[i + 2][2]), []).append(i)
    _IDX = (stream, uth, tri)
    return _IDX


def ar_num(n):
    return "".join("٠١٢٣٤٥٦٧٨٩"[int(d)] for d in str(n))


def find(text):
    """→ None or {"a","b": token indices in text.split() (inclusive), "ref": "2:255" / "2:255-256", "text": Uthmani words}."""
    stream, uth, tri = _load()
    toks = text.split()
    words = merge_voc([(k, norm(t)) for k, t in enumerate(toks) if norm(t)])  # [([token indices], normalised)]
    best = None
    for i in range(len(words) - 2):
        for p in tri.get((words[i][1], words[i + 1][1], words[i + 2][1]), []):
            j, q, miss = i + 3, p + 3, 0
            while j < len(words) and q < len(stream):
                if words[j][1] == stream[q][2]:
                    j += 1; q += 1
                elif miss == 0 and j + 1 < len(words) and q + 1 < len(stream) and words[j + 1][1] == stream[q + 1][2]:
                    j += 2; q += 2; miss = 1  # one misheard word: the Mushaf word replaces it
                else:
                    break
            i0, p0 = i, p  # and backwards, so a misheard first word doesn't hide the verse
            while i0 > 0 and p0 > 0:
                if words[i0 - 1][1] == stream[p0 - 1][2]:
                    i0 -= 1; p0 -= 1
                elif miss == 0 and i0 > 1 and p0 > 1 and words[i0 - 2][1] == stream[p0 - 2][2]:
                    i0 -= 2; p0 -= 2; miss = 1
                else:
                    break
            if j - i0 >= MIN_RUN and (not best or j - i0 > best[1] - best[0]):
                best = (i0, j, p0)
    if not best:
        return None
    i, j, p = best
    s0, a0 = stream[p][:2]; s1, a1 = stream[p + (j - i) - 1][:2]
    if (s0, a0) == (s1, a1) == (1, 1) and j - i == 4:
        return None  # a basmala on its own is not shown as a verse
    run = [stream[p + k][2] for k in range(j - i)]
    if j - i <= 5 and "الشيطان" in run and "الرجيم" in run:
        return None  # «أعوذ بالله من الشيطان الرجيم» is the everyday isti'adha, not a recitation
    ref = f"{s0}:{a0}" + (f"-{a1}" if (s1, a1) != (s0, a0) and s1 == s0 else f"-{s1}:{a1}" if s1 != s0 else "")
    return {"a": words[i][0][0], "b": words[j - 1][0][-1], "ref": ref, "text": " ".join(uth[p:p + (j - i)]),
            "endAya": ar_num(a1)}


if __name__ == "__main__":
    import sys
    print(find(" ".join(sys.argv[1:])))
