---
name: nahj-youtube
description: Long 16:9 YouTube videos for قناة نهج الأثر الدعوية (@nahjalathar_channel), made in Qitaf. Use for YouTube thumbnails, in-video layouts (title band, board, sound only), titles, descriptions, chapters, the channel cover, and uploading. Trigger on "YouTube", "long video", "thumbnail", "channel cover", "banner".
---

# Nahj al-Athar on YouTube

Long lessons, kept whole. Channel: https://www.youtube.com/@nahjalathar_channel (gold calligraphic logo). General rules come from `nahj-style`: no music, no women on screen, no AI faces, real footage only, quiet SFX.

## Where it lives

Qitaf (this project, localhost:8795) → Set up → Look → **YouTube long video**.

- `pipeline/yt_frame.html`: every design (frame, thumbnails, subtitle strips). The site preview and the renderer load this same file, so edit designs there.
- `pipeline/youtube.py`: the build. No per-frame page render: a browser draws the frame, subtitles and thumbnails once, and ffmpeg overlays them with the hardware encoder when there is one. The speech is never cut.
- `pipeline/logo.png`: transparent channel logo.

Subtitles are PNG strips in a concat list, which works on every ffmpeg build.

## Layouts (1920×1080)

| Layout | Use | Rule |
|---|---|---|
| Band | A video that should fill the screen | One plain band across the bottom: logo, name, book or series, title. Subtitles float above it in a pill |
| Board | Lessons with a static camera | Video inset on a plain board, subtitles in their own panel under it so they never cover the picture, title and name in a side column |
| Sound only | Audio, or a video turned into audio | Quiet ground, title, name, the voice as rounded bars in a dark pill, subtitles under it. Audio sources always use this |

Colours: Ink, Forest, Navy, Maroon, Paper (`THEMES` in `yt_frame.html`). Gold accent throughout.

**Zoom in** and **Move the picture** crop away what the source burned in (its border, ministry logo, title strip). Check the preview: a source's lower third must never peek out above the band.

Qur'an in subtitles: gold, between ﴿ ﴾, in Amiri Quran (Warsh: Almaghribi). Other fonts drop Uthmani marks such as U+06DF and show an empty box, so never swap this font without checking `تُخْفُوا۟`.

## Thumbnails (1280×720, three per video)

- 1 Portrait: the speaker in black and white on the theme colour, heavy two-tone headline
- 2 Cinema: the speaker in colour in a dark room, serif headline, thin gold rule, name
- 3 Title: no person, the words large on a dark softened frame. Audio sources have no face, so the words carry it

Rules: real frames only. Two or three lines, at most 7 words, the first line in yellow. The headline must read at phone size, so it fills its box. The frame is chosen automatically (sharp, front-facing); replace it if the mouth or eyes look poor.

## Packaging (`<name>.txt`, written once, kept in `clips/clipN/yt.json`)

Three titles (topic first, name last, under 70 characters), a description from what is actually said, chapters, 3 hashtags, tags, a pinned question. Faithful to the lesson: no exaggeration, no fear-mongering. Read hadith and attribution claims before publishing, since Claude writes them from the transcript. The `.srt` goes in YouTube's subtitle upload.

## Channel cover

2560×1440. Everything readable stays in the middle 1546×423, the only part every device shows. Current design: dark ink, the logo and name in gold, two thin gold lines forming a road (نهج) around them. Check desktop (2560×423) and phone (1546×423) crops.

## Uploading

Never ask for or enter the Google password. Two routes:

1. YouTube Studio in a browser the user has signed in to. Fill in the details, and confirm with the user before publishing each video.
2. YouTube Data API with the user's own OAuth login. New unverified API projects can only upload as private until Google audits them, and the default quota allows only a few uploads a day.
