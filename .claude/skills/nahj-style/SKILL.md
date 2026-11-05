---
name: nahj-style
description: The original content style for the Nahj al-Athar (نهج الأثر) da'wah channel — Islamic Arabic content. Use for ANY content made for the user — Instagram carousels and quote posts, short reels (talking-head or voice-to-visuals), long lessons cut into shorts, outros, captions, hooks, covers, posting plans and growth strategy. Load it before short-form-edit, edit-video, hyperframes, video-storytelling, marketing:content-creation or any design skill, because its rules override their defaults.
---

> This is the style Qitaf was built around, from the channel it was made for. Fonts live in the project `fonts/` folder. If the owner of this copy changes their style, update this file to match.

# Nahj al-Athar content style

Channel: «قناة نهج الأثر الدعوية» — Instagram **@nahj_al.athar** (31.3k followers, Oct 2026). Bio spirit: «هذا أثري.. خذوا ما شئتم» — content meant to outlive its maker and be re-shared. Niche: scholars' benefits (فوائد), hadith, athar, Qur'an. Audience: 74% men, core 18–34, Arabic speakers.

Read the reference file for the format you are making:
| Making… | Read |
|---|---|
| a reel from a scholar's audio only (most common, most viral) | references/visuals.md |
| a reel cut from a filmed lesson (talking head) | references/reels.md |
| shorts cut from a long lesson | references/long-to-short.md |
| any 9:16 reel: where text, faces and captions go | references/placement.md (read it for every reel) |
| a carousel or single quote post | references/carousels.md |
| fonts / any on-screen Arabic | §3 below + fonts/ |

## 1. Hard rules (override every other skill)
- **No music, ever** — no beds, no melodic stings. Skip music steps in short-form-edit, make-a-video, herk-edit-kit.
- **No women** in footage, images, illustrations or generated assets.
- **No faces on figures.** Illustrated Muslim men (thobe, shemagh, kufi, bisht) are fine only if faceless: back view, hood/shadow, cropped, or a **calligraphy medallion of the person's name over the face** (for named scholars/salaf). Never an AI face.
- **SFX allowed, quiet only**: paper, soft swoosh, pen scratch, tick — well below the voice.
- **Arabic only** on screen. Correct joining; in HyperFrames never put `dir="rtl"` on `<html>` (renders black) — put it on inner elements.
- **Text accuracy beats speed.** Qur'an, hadith and scholars' words are never paraphrased. Follow the audio where clear; authentic wording on a tie; if unsure keep it off screen and flag it. Never guess an ayah, a grading or an attribution.
- **Qur'an text by reading:**
  - Hafs → font **Amiri Quran**, text pasted by the user (or from a verified Hafs source the user approves).
  - Warsh → font **Almaghribi Warsh** (fonts/Almaghribi Warsh-Quran.otf); text may be copied from https://app.al-mushaf.com/ — **Warsh text only** from that site, only in the Warsh font. Never mix readings or fonts.
  - The user says which reading each ayah is recited in; if not stated, ask.
- **Inspirations are inspirations.** Never reproduce another account's colours, frame, layout signature, footer or branding. If a result would make someone say "that's a copy of @X", change it.
- Get the user's approval of segment lists / plans before long renders.

## 2. Brand kit — "athar" (ink, paper, gold)
The identity is an *old manuscript / trace* (أثر): warm paper, deep ink, aged gold — deliberately different from the dark-photo + candy-coloured-pill look common in the niche.

| Token | Hex | Use |
|---|---|---|
| ink teal | `#0f4a44` | main text on paper, primary highlight pill |
| night | `#0b1f1d` | dark backgrounds, video grade |
| paper | `#f3ead8` | light backgrounds, cards |
| paper-shade | `#e6d9bd` | secondary panels, rules |
| gold | `#a87b2c` | keywords, underline sweeps, rims, speaker name |
| ember | `#8a3b23` | warnings / "the wrong way" (sparingly) |
| sage | `#5d7a5a` | "the right way", checkmarks (sparingly) |

Texture: subtle paper grain + faint ruled manuscript lines (not a graph grid). Light vignette on photos. Ornament budget: at most one quiet mark (small gold ✦ or thin gold rule). No seals or boxes around source text, no swirls, no star clutter.
**Highlight signature (ours):** the spoken key phrase gets a highlight pill that fills right→left with a gold underline sweeping under it; then the pill fades and the words stay with the gold underline. On reels and shorts the pill is **yellow** (`#f2d32e`, per the user's placement reference, confirm the exact shade against it); on carousels and paper layouts it is ink teal. Warnings use ember, the right answer sage. Never more than one coloured pill on screen.

## 3. Fonts (files in fonts/ — embed with @font-face from that folder)
| Role | Font | Weights |
|---|---|---|
| Default for everything (captions, body, labels, counters) | **Thmanyah Sans** (`thmanyahsans-*.woff2`) | Light context lines · Regular body · Medium spoken lines · Bold key phrase · Black hooks/cover titles |
| Titles with a classical feel, big quotes, cover headlines | **Thmanyah Serif Display** | Bold/Black titles, Regular big quotes |
| Long quoted passages in carousels | **Thmanyah Serif Text** | Regular/Medium |
| Hadith / athar with full tashkeel, honoured text | **AMoshref Naskh** | one weight — "sometimes", never for UI |
| Display accents (series name, big numerals) — optional | **Basseet** (`BasseetFree-*.ttf`) | rarely |
| Qur'an, Hafs | **Amiri Quran** (Google Fonts) | — |
| Qur'an, Warsh | **Almaghribi Warsh** | — |
Max 2 families per frame (+ the Qur'an font when an ayah is on). Thmanyah usage-guide PDFs: ~/Desktop/CLAUDE/nahj-skill/.

## 4. Formats at a glance
- **A. Voice → visuals reel** (flagship) — references/visuals.md.
- **B. Talking-head reel** — references/reels.md.
- **C. Long lesson → series of shorts** — references/long-to-short.md.
- **D. Carousel / quote post** — references/carousels.md.
- **E. Outro (~4 s, all videos)** — video pulls to centre with blur while a circular mask closes → paper circle with gold rim on night: «قناة / نهج الأثر / الدعوية», camera glyph + @nahj_al.athar, «تابعونا على إنستغرام». Hold 2.5 s, shrink to a dot. Simple.

## 5. Pipeline & tools
- Transcribe locally (mlx-whisper / faster-whisper, venv `~/.venvs/whisper`); no ElevenLabs.
- **Always MMS_FA forced-align on the final cut audio** before any text timing — raw Whisper is 0.3–0.5 s off and the user notices.
- Render with HyperFrames via `npx --prefix ~/herk-edit-kit`; lint → snapshot review sheet → render.
- Reuse: `~/Desktop/CLAUDE/visualy/tools/` (fa.py, score.py, trim.py, build.py, engine.html, engine-bright.html, icons.js, review.sh), `~/Desktop/CLAUDE/Al-Idrisi-Lesson-1/work/` (align/cut/fa/build), SFX in Al-Idrisi shared/sfx.
- Carousels: HTML per slide → PNG 1080×1350 at 2×.
- Pair with installed skills: short-form-edit, cut-silences, cut-mistakes, video-storytelling, hyperframes(+cli), gsap, style-library, anthropic-skills:canvas-design, frontend-design, vectorlab-ux-skills:typography / anti-slop, marketing:content-creation / draft-content / campaign-plan, anthropic-skills:hormozi (hook thinking). This skill wins on every conflict.

## 6. Every deliverable ships with a "post kit"

### Reel cover — approved format (2026-10-28, always use it)
- 1080×1920 (9:16), uploaded via Instagram "Edit cover → Add from camera roll".
- Background: a real frame of the speaker from the clip (raw/source footage, never a frame with burned-in captions), framed at ~30% from the top so the face sits in the upper half.
- Dark fade from the bottom: rgba(20,20,18) .96 → .82 at 30% → clear at 58%.
- Title: Thmanyah Sans Black, 84px, ivory #FFFBEB, centred, balanced line breaks, bottom edge at 440px from the foot; keep the title's own madd/harakat as written.
- Speaker: Thmanyah Sans Medium 38px, amber #FDE68A, centred, 340px from the foot.
- Title and name stay inside the middle 3:4 (y 240–1680) so the profile grid shows them.
- Generated by `cover()` in ~/Desktop/CLAUDE/reel-studio/server.py; example: reel-studio/design/example-cover.jpg.

## 7. Examples
