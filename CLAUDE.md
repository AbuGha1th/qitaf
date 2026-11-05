# Qitaf (قِطاف)

A local video editor for Arabic Islamic lessons. It runs on this computer (Windows, or a Mac with Apple Silicon) at http://localhost:8795 and makes two things:

1. **Reels:** from a long lesson (cut into clips) or from one short video.
2. **YouTube long videos:** a whole lesson in 16:9, with title band, subtitles, thumbnails and description.

Text-to-video and motion graphics exist in the code but are switched off in this version because they were never fully tested. Don't turn them on unless the owner asks.

The person you're helping is not a programmer. Use plain words, make the changes yourself, and tell them what changed.

**Permanent rules:** no music, no AI-generated faces, no women on screen, quiet sound effects only. Qur'an text is never changed, retyped or guessed: it comes from `quran/` (Tanzil), from al-mushaf.com through `pipeline/warsh.py` (Warsh, written for its own font, so don't clean up its odd characters), or from the user.

## First install

If `.venv` doesn't exist, or the owner says they've just got Qitaf:

1. Windows: run `powershell -ExecutionPolicy Bypass -File setup.ps1` in this folder. Mac: run `./setup.sh`. It takes a while and installs Git, Node, ffmpeg, Python, the speech models and a **Qitaf** shortcut on the Desktop.
2. If `check.py` reports anything missing, fix it. Ask the owner to sign in to Claude Code if `claude` isn't working.
3. Run the **style interview** below.
4. Ask the owner for a short video (1 to 2 minutes), start Qitaf and walk them through their first reel.

## Style interview

Qitaf comes with the style of the channel it was built for. Before changing anything, tell the owner that, then ask these one at a time. Each one can be answered "keep it".

1. **Channel name** in Arabic and English. Write it to `channel.json` as `{"name": "...", "name_en": "..."}`. Titles and descriptions use it. Leave both empty to mention no channel.
2. **Logo:** no logo is included. If they have one, save it as `pipeline/logo.png` (transparent PNG). With no file, Qitaf simply shows no logo.
3. **Handles:** Instagram and YouTube. Instagram goes in the presets (`socialHandle`). YouTube is the `ytHandle` default in `index.html`.
4. **Colours:** caption colours, fade colour, YouTube themes. Keep or change?
5. **Fonts:** none of the style's fonts are included, because their licences forbid sharing them. Help them get Thmanyah (see Fonts), or choose free ones.
6. **Captions:** look, size and animation.
7. **Sound wave:** style, or none.
8. **Reel cover and YouTube thumbnails:** keep the designs, or describe what they want.
9. **Post wording:** the call to action and hashtags in `post_kit()` in `server.py`.
10. **Presets:** the shipped ones are named after shaykhs and teachers. Keep which? Remove which?

Save their answers as a preset called "My style" in `presets.json`, and record the decisions in `.claude/skills/nahj-style/SKILL.md` so they carry forward. Show them the preview, then ask if it's right.

## Where everything lives

| What | Where |
|---|---|
| The page | `index.html` |
| Arabic wording of the page | `i18n.js` (the page is written in English; this swaps the text) |
| Help guide | `guide.html` |
| Server, AI prompts for titles and posts, reel cover | `server.py` |
| Reel building | `pipeline/render_clip.py`, design in `pipeline/template.html` |
| YouTube building | `pipeline/youtube.py`, designs and thumbnails in `pipeline/yt_frame.html` |
| How clips are chosen | `pipeline/pick_prompt.md` |
| Safe zones, where text may sit | `rules.json` |
| Mac and Windows differences | `pipeline/plat.py` |
| Style guides | `.claude/skills/nahj-style`, `.claude/skills/nahj-youtube` |
| Finished videos | `Qitaf/clips/<lesson>/` in the user folder |
| Working files | `jobs\<id>\`, removed automatically after 14 days unused |
| Presets, word fixes, channel name | `presets.json`, `fixes.json`, `channel.json` |
| Log | `qitaf.log` |

`presets.json`, `fixes.json` and `channel.json` belong to the owner. Updates only touch the `.default.json` files, so never edit those for a personal change.

**Safe zones:** the "red zone" is the part of a reel Instagram covers with its buttons. Keep all text inside the safe area in `rules.json`. Set up's preview has **Show safe zones**.

**Any new English text added to the page also needs its Arabic in `i18n.js`, or it shows in English.**

## Fonts

Fonts live directly in `fonts/`, never in a subfolder, and are not in the repo. The style was built on Thmanyah Sans and Thmanyah Serif Display. They're free from the official page (see `fonts/README.md`): the owner enters their email and receives the files. The page expects `thmanyahsans-Black.woff2` and similar names. The download may be `.otf` with other names, so point the `@font-face` rules in `index.html`, `pipeline/template.html`, `pipeline/yt_frame.html`, `guide.html` and `cover()` in `server.py` at the real files. Never rename, share or upload the font files. To add one:

1. Add an `@font-face` to `index.html` and `pipeline/template.html`. For YouTube, also `pipeline/yt_frame.html`.
2. Add it to the `FONTS` list (captions) and `TFONTS` list (titles) in `index.html`.

Qur'an verses use Amiri Quran (Hafs) or Almaghribi Warsh. Other fonts can drop Uthmani marks and show empty boxes, so don't swap these without checking `تُخْفُوا۟`.

## When something goes wrong

1. Read the error on the video's tile, and `qitaf.log`.
2. Run `check.py` with the project Python: `.venv\Scripts\python.exe -X utf8 check.py` on Windows, `.venv/bin/python -X utf8 check.py` on Mac.
3. Fix the cause. Restart Qitaf only when nothing is rendering, because queued renders are held in memory.

- Restart: close the Qitaf window, then open the Desktop shortcut.
- Transcription is slow without an NVIDIA card. That's expected.
- Never delete `jobs` or the `Qitaf/clips` folder to fix a problem. Move things to the bin, and ask first.

## Updating

**Update Qitaf** gets the latest version and keeps the owner's presets, word fixes, lessons and videos. If the owner changed tracked files such as `index.html`, `git pull` may stop with a conflict. Keep their change and take the update together.
