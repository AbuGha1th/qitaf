You direct a 9:16 motion-graphic video for an Arabic Islamic lesson clip (Nahj al-Athar channel). No camera footage:
the speaker's voice plays over flat, minimal animated visuals (style: cream / deep green / black grounds, one big Arabic
heading, one simple growing visual in the middle — like a well-made explainer). Arabic only on screen. Faceless figures only.
Never add claims the speaker did not make.

THE KEY IDEA: pick ONE central visual metaphor for the whole clip and make it GROW or CHANGE as he speaks (a seed that
becomes spikes, a heart that loses a layer per sin, scales that tip, links being cut, a counter climbing). Cut to a
new visual only when the topic truly changes. Fewer, stronger visuals beat many icons.
EVERY scene must visibly change something: either a new "prop", or "same" with at least one step (tilt, strip a layer,
grow, cut, tick an item, count up). A scene where nothing moves is not allowed. Aim for 2–3 different props per minute,
and use the tracker when the speaker lists several bad/good things.

Return JSON only:
{"tracker": null | {"type":"heart","layers":N},   // optional small heart under the visual that loses one layer per enumerated point
 "scenes":[ {
   "at": "anchor",            // omit on the first scene (starts at 0)
   "bg": "cream|green|black", // alternate grounds when a new point starts; title/intro scenes on green
   "num": "١/٥",              // optional counter for enumerated points (Arabic digits)
   "head": "short heading, ≤ 5 words; wrap ONE key word in *stars* for the accent colour",
   "head_at": "anchor",       // optional: when the heading appears (default: scene start)
   "sub": "optional second line ≤ 8 words", "sub_at": "anchor",
   "prop": {"type": …params} or {"same": true} to keep growing the previous visual,
   "steps": [ {"at":"anchor", …action} ],   // changes to the current visual, timed to words
   "track": 0, "track_at": "anchor"         // tracker layer to strip in this scene (0,1,2…)
 } ]}

Visual types and their steps:
- heart {"layers":N}            steps {"layer":k}  — strip layer k (a sin/corruption hitting the heart)
- plant {"spikes":7}            steps {"do":"sprout"|"spikes"|"grains"} — growth, multiplied reward, a deed bearing fruit
- scale {"a":"…","b":"…"}       steps {"tilt":"a"|"b"|"level"} — weighing two things, justice, preferring one over another
- links {"items":["…","…"]}     steps {"do":"cut"} — attachment of the heart to things / cutting ties
- figure {}                     steps {"do":"think"|"glow"} — a person reflecting, wishing (thought bubbles), guidance (glow)
- crowd {}                      steps {"do":"gather"|"leave"|"shrink"|"glow"} — public vs private, shame in front of people, being alone with Allah
- clock {}                      steps {} or {"do":"spin"} — time, sleep, delay, the hour
- counter {"from":0,"suffix":"…"} steps {"to":700} — numbers, multiplied rewards, counts
- list {"items":["…","…"]}      steps {"item":k} — show item k as it is said (recap of points) {checklists}
- word {"text":"…","accent":true} — one big word when nothing visual fits
- ayah {"text":"exact recited verse words","ref":"سورة … ٢٦١"} — only when a Qur'an verse is recited

ANCHORS: every "at" / "*_at" is 1–3 consecutive words copied EXACTLY from the spoken text below, in order through the clip
(each anchor after the previous one). "phrase#2" = 2nd occurrence. Never invent anchor words. 3–9 scenes, ~5–10 s each.

Clip title: {title}
{script}
Spoken text (one sentence per line, exactly as said):
{text}
