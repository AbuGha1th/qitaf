"""Accuracy check for Warsh look-ups against a separate Warsh text: python test_warsh.py <warshData.json>
Downloads the sample surahs from al-mushaf.com once, so it needs the internet."""
import difflib
import json
import random
import sys
sys.path.insert(0, "pipeline")
import warsh

K = {}
for r in json.load(open(sys.argv[1], encoding="utf-8")):
    K.setdefault(r["sura_no"], []).append(warsh.skeleton(r["aya_text"].replace(" ", "")))
H = {}
for l in open("quran/uthmani.txt", encoding="utf-8"):
    f = l.rstrip("\n").split("|")
    if len(f) == 3:
        H.setdefault(int(f[0]), {})[int(f[1])] = f[2].split()
sim = lambda a, b: difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()
sk = lambda ws: "".join(warsh.skeleton(w) for w in ws)
random.seed(7)
cases = []
for s in range(1, 115):
    vs = [a for a in H[s] if not (a == 1 and s != 1)]
    for a in random.sample(vs, min(12, len(vs))):
        w = H[s][a]
        cases.append((s, a, w, "whole"))
        if len(w) >= 8:
            k = random.randrange(0, len(w) - 5); cases.append((s, a, w[k:k + random.randint(4, 7)], "part"))
tot = {"whole": [0, 0, 0], "part": [0, 0, 0]}; bad = []
for s, a, w, kind in cases:
    t = tot[kind]; t[0] += 1
    got = warsh.lookup({"ref": f"{s}:{a}", "text": " ".join(w)})
    if got is None:
        t[2] += 1; bad.append(("empty", s, a, " ".join(w)[:60])); continue
    hw = [x for x in map(warsh.skeleton, w) if x]; gw = [x for x in map(warsh.skeleton, got.split()) if x]
    k = min(3, len(hw))
    if sim("".join(hw[:k]), "".join(gw[:k])) < .7 or sim("".join(hw[-k:]), "".join(gw[-k:])) < .7:  # a cut start or end
        t[1] += 1; bad.append(("ENDS", s, a, " ".join(w)[:45], got[:45], "...", got[-30:])); continue
    if abs(len(gw) - len(hw)) > 1 + len(hw) // 15:  # a missing or extra word
        t[1] += 1; bad.append(("WORDS", s, a, len(hw), len(gw), " ".join(w)[:45], got[:45])); continue
    g = sk(got.split())
    # the independent Warsh text must contain what came back
    best = max(sim(g, v) if kind == "whole" else max(sim(g, v[i:i + len(g)]) for i in range(0, max(1, len(v) - len(g) + 1))) for v in K[s])
    if best < .85:
        t[1] += 1; bad.append(("WRONG", s, a, round(best, 2), " ".join(w)[:50], got[:60]))
print(tot, "[tested, wrong, left empty]")
for b in bad[:60]:
    print(b)
