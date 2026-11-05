# D. Carousels & quote posts
4:5, 1080×1350, RTL (swipe cue ← on the left edge). 5–8 slides.

## What the best niche carousels do (studied, Oct 2026)
- Teach a structure, not a wall of text: title → split into 2–4 parts with arrows → each part explained → ayah/hadith as proof → summary.
- One continuous scene runs across slide edges (a lamp, a hanging plant, a landscape) so swiping feels like moving through one picture — this drives full swipes.
- Slide counter, consistent footer with handle.

## Our version — "manuscript" look
- Background: paper `#f3ead8` with grain + faint ruled lines; alternate with a **night** slide for the turning point (the "but…" moment). Torn-paper or folded-page edge where paper meets night (ours: a clean folded-page diagonal with soft shadow, not a ragged tear).
- Panorama object: one continuous element crossing slide borders — choose from: an oil lamp + its light, a qalam ink stroke, a palm branch, a manuscript ribbon/bookmark, an old door arch. Render the full panorama 1080·N × 1350 then slice. **Instagram always shows slide 2 to the RIGHT of slide 1, even for Arabic posts** → slide 1 = leftmost 1080 px, slide N = rightmost; only the text inside each slide is RTL. Verify by tiling the slides left→right and checking the joins line up. Reference build: ~/Desktop/CLAUDE/nahj-skill/test-carousel/carousel.html (gold path, approved concept 2026-10-23).
- Slide 1 (cover/hook): Thmanyah Serif Display Black title ≤ 6 words, one gold underline sweep, small sub-question in Thmanyah Sans Light, «اسحب ←» hint.
- Content slides: one idea each, ≤ 35 words. Structure with Thmanyah Sans (Bold heading in ink, body Regular), diagram arrows in ink with gold heads, rounded panels in paper-shade (solid thin border — no dashed boxes).
- Ayah slide: Amiri Quran / Almaghribi Warsh per reading, gold ﴿ ﴾, a soft gold highlighter behind 1–3 key words only.
- Hadith/athar: AMoshref Naskh at ~74px with `word-spacing:.32em` and `line-height:2.1` (the font is tight — never letter-spacing, it breaks joining). Emphasis = a soft gold highlighter band on the lower third of the line (`linear-gradient(transparent 70%, rgba(168,123,44,.22) 70% 97%, transparent 97%)`), never a hard underline under Naskh. Full reference always: «رواه مسلم (٢٦٩٩) من حديث أبي هريرة رضي الله عنه» — collection + number + narrator, between two short gold rules; verify the number, never guess.
- Summary slide: checklist with sage ticks.
- Last slide: «احفظها لنفسك، وأرسلها لمن تحب، فالدال على الخير كفاعله» + @nahj_al.athar + series name.
- Footer every slide: «نهج الأثر» left-aligned small gold, counter «٢/٧» right, thin gold rule. Source of the benefit (book/scholar) on the title or last slide.

## Single quote post
Illustrated faceless scene (e.g. man in sujood from behind, lamp-lit room, night window with crescent) in our night/gold palette; text on a glass-paper panel; key line in Thmanyah Serif Display, rest in Thmanyah Sans; source below panel. Hijri year small top corner, handle small top.

## Build
HTML/CSS per slide (or one wide canvas sliced), fonts from ../fonts, render PNG at 2× via a headless browser; check Arabic joining and tashkeel collisions at 100% zoom before export.
