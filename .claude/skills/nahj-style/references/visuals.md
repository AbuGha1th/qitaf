# A. Voice → visuals reel (flagship format)
Input: audio of a scholar (or the user's recording). Output 1080×1920, 15–60 s ideal (≤ 90 s).
What makes the niche's best reels work (studied from inspirations, Oct 2026): calm cinematic background, the scholar's words appearing **phrase by phrase exactly as spoken**, one phrase emphasised at a time, the scholar's name always present, and a closing source card. Viewers read along → full watch → replays → shares.

## Our version
1. **Cold open (0–1.5 s):** the strongest sentence of the clip first, OR an illustrated faceless scene + 2–4 word title. No «السلام عليكم», no logo intro.
2. **Background:** one cinematic still per clip (or 2–3 for longer), slow Ken Burns push (≤ 6% over the scene), dimmed to ~35%, night-teal colour grade + vignette + paper grain. Subjects: old masjid courtyards, manuscripts, oil lamps, desert at dawn, bookshelves, a mihrab, rain on a window. No people with faces.
3. **Intro figure (optional, first 2–4 s):** faceless illustrated man (back view, or calligraphy medallion of the scholar's/salaf's name over the face, in our gold-on-ink, not blue-tile), then dissolve to the background.
4. **Top bar:** topic title in Thmanyah Serif Display Bold on a thin paper strip or plain over the vignette, with «@nahj_al.athar» tiny under it. Keep it consistent across the series (it becomes recognisable).
5. **Text build (centre third):** each spoken phrase appears on its word timings (forced alignment). Current phrase = Thmanyah Sans Bold inside our ink-teal pill filling right→left + gold underline sweep; previous lines stay above in Medium white at 85%; max 3–4 lines, then the block clears with a soft upward fade. Glosses in Light: «(أي: …)».
6. **Ayah moments:** background darkens further, ayah in Amiri Quran (Hafs) or Almaghribi Warsh (Warsh) centred, gold ﴿ ﴾, reference small in Thmanyah Light. No pill on Qur'an — only a slow gold glow.
7. **Hadith / athar card (end):** glass-paper panel (paper at 12% + blur) holding the full text in AMoshref Naskh, source «رواه مسلم» plain below — no seal or box around it.
8. **Scholar signature:** bottom-centre, the scholar's name in calligraphic style (AMoshref Naskh or Thmanyah Serif) + «حفظه الله» / «رحمه الله» small, gold at 80%. Always on.
9. **End:** source card → outro (SKILL.md §4E).
10. **Audio:** voice only, levelled to −14 LUFS; SFX: soft paper on scene change, nothing on every line.

## Alternative looks (when the user asks)
- "classic visualy": maroon line-grid + line icons drawn in + checklist build (visualy/hadith1 approved 2026-10-19, waveform bar, no bottom karaoke).
- "bright": engine-bright.html (boxes, neon) — for lighter topics.

## Pipeline
transcript → corrected text (one phrase per row = one on-screen unit; retakes in ⟦ ⟧) → trim.py (pauses ≤ 0.5 s) → fa.py → plan.json (title, background(s), phrases, highlights, ayah/hadith blocks) → build.py → lint → review.sh → render.
