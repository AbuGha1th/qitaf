# Screen placement (all 9:16 reels)
Source: the placement reference video the user supplied (`~/Desktop/CLAUDE/rules.mp4`, 17 s, narrated). Percentages are of the 9:16 frame.

## The zones
1. **Eye line (keep the face here).** Band at about 34–44% of the height. The speaker's eyes sit here. Punch-ins keep the eyeline in this same band.
2. **Safe zone.** A centred box, roughly 13%–87% of the width and 7%–86% of the height. All text, titles and graphics go inside it.
3. **Title hook zone.** The top of the safe zone, about 11%–90% wide and 11%–89% high in the reference. The title hook sits here in the first seconds.
4. **Caption zone.** Horizontally centred, about 75–80% down the frame, inside the safe zone. Subtitles go here, one line.
5. **Danger zone.** Everything outside the safe zone, especially the edges. Nothing important goes here.
6. **Avoid at all costs.** The bottom band (the bottom ~12% of the frame, full width) and the right side below about 47% height. This is where the platform's own buttons and caption overlay sit.

## Rules
- Text inside the safe zone only. Edge-to-edge text is out.
- Title underline: the gold rule spans exactly the width of the title text (inline-block wrapper), never a fixed-width bar.
- Framing: for voice-to-talking-head reels, fill the frame with the speaker (head to chest), not a wide room shot. A 1:1 band in the middle of the frame is the default; keep the eyeline in the 34–44% band.
- Captions: one line each, time slots never overlap. Build step asserts no overlap; a lint error for nested or overlapping timed clips is a blocker.
- Subtitles sit in the caption zone, one line, centred. Keep them clear of the avoid zone.
- On a busy background, add a stroke (outline) to the captions.
- When punching in, keep the eyeline in the eye-line band.
- The title hook is in the title hook zone, and it appears in the first 3 seconds.

## Questions for the user
- Highlight pill: **yellow** for reels and shorts (decided by the user). Ink teal stays for carousels and paper layouts.
- Do the zones apply to every format (talking head, voice-to-visuals, carousel covers), or only to reels?
