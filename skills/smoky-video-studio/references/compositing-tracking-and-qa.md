# Compositing, Tracking, Privacy Redaction & Visual QA

Use this reference when cutting real screen/device recordings, tracking cursor/UI actions, building layered zoom insets, redacting PII, or choosing between FFmpeg/Python and Remotion.

## 1. Tool Selection: FFmpeg + Python vs. Remotion / HTML Canvas

| Need | Prefer | Why |
| --- | --- | --- |
| Editing real screen/phone captures, AI video clips, speed ramps, tracked zoom lenses, film grain, sub-ms DSP audio transitions | **FFmpeg + Python (`PIL` / `numpy` / optional `cv2`)** | Fast hardware decode (`-hwaccel videotoolbox` on macOS), exact frame piping, zero browser startup overhead, sample-accurate audio sync |
| Data-driven charts, kinetic typography, React component UI demos, interactive web micro-drops | **Remotion** or **headless HTML Canvas/SVG** | Native CSS/SVG layout, easing curves, web fonts, and reusable React state machines |
| Quick animated proof GIFs / contact sheets | **FFmpeg + `PIL`** | Single command, deterministic dimensions and timestamps |

## 2. Coarse-to-Fine Contact-Sheet Scouting

Never guess cut points on a multi-minute recording. Narrow in four fast passes, burning exact `MM:SS.cc` timestamps under each tile:

1. **Overview pass**: `30–60 s` step (`4×4` sheet) — identify chapters, layout geometry, and sensitive regions.
2. **Region pass**: `10–20 s` step (`5×4` sheet) — locate candidate sequences.
3. **Action pass**: `2–4 s` step (`5×4` sheet) — isolate exact clicks, transitions, and visual payoffs.
4. **Micro pass**: `0.2–1.0 s` step (`5×2` sheet) — lock exact takeoff, menu-open, and touchdown frames.

```bash
# Fast labeled contact sheet from any clip (adjust fps and tile WxH)
ffmpeg -y -v error -i clip.mp4 -vf "fps=1,scale=480:-1,tile=4x2" -frames:v 1 preview_sheet.jpg
```

For multi-minute sources, extract individual timestamped frames with a small Python `ThreadPoolExecutor` (`ffmpeg -ss <t> -i src -frames:v 1`, placing `-ss` **before** `-i` for fast keyframe seek) and composite labeled tiles with `PIL.ImageDraw`.

## 3. Cursor / Action Tracking & Non-Uniform Speed Ramping

When showcasing computer-use agents or complex desktop workflows:

1. **Detect target automatically**: Crop a clean reference template of the custom/system cursor (or UI highlight), build a color/edge mask, pipe downscaled frames (`-hwaccel videotoolbox ... -pix_fmt rgb24 -f rawvideo -`) into `cv2.matchTemplate(..., TM_CCOEFF_NORMED)`, and score windows by visibility, travel spread, and number of active motion steps.
2. **Smooth non-uniform speed ramp** (compress idle waits, linger on transit + landing):
   - Decode the action window at high temporal density (e.g., `40–50 fps`).
   - Build a Gaussian-weighted density curve peaking at movement midpoint (`approach`) and target click (`landing`), integrate with `np.cumsum`, and resample `count` output frames via `np.interp`.
   - Record exact output timestamps (`takeoff`, `touchdown`) into `cues.json`:
   ```json
   [
     { "kind": "sweep", "cut": 0.0, "depart": 0.16, "land": 0.92, "direction": 0.64 },
     { "kind": "menu",  "cut": 1.33, "depart": 1.50, "land": 2.04, "direction": -0.35 }
   ]
   ```
3. **Layered readability at feed size**:
   - **Motion trail + touchdown ring**: Draw a short fading tail over the last `8–12` tracked positions (skipping jumps where cursor was hidden) and a `5–6`-frame expanding arrival ring on touchdown.
   - **Auto-docked tracked PiP magnifier lens**: Follow the smoothed cursor centroid (`lens_center = 0.31 * prev + 0.69 * curr`), magnify `~2.4×` inside a clean bordered inset, and choose left vs right (or top vs bottom) corner by **minimum overlap count** with the cut's tracked cursor trajectory so the lens never covers the action it magnifies.
   - **Live proof callout strip**: Keep the live terminal / tool-call pane visible beneath the primary window; during key explanatory beats, briefly overlay a crisp `2×` zoomed callout of the exact verification line (for example a `menu_open` or `verified` receipt).

## 4. Dual-Source Hardware B-Roll + Direct Screen-Capture Launch Demos

When launching a physical device, mobile app, or desktop runtime, filming a screen solely with an external camera produces moiré and illegible text, while pure screen recording can feel synthetic or detached from real hardware. Combine both sources cleanly:

### A. Pixel-Perfect Direct Screen Capture (Linux/Wayland & Cross-Platform)
- **Linux / Wayland (`wl-screenrec` or `wf-recorder`)**: Capture crisp, native-resolution frames before editing (`-f` / `--framerate 60`, hardware encoder when available, full-range/clean pixel format):
  ```bash
  # Direct Wayland compositor capture (zero camera moiré, pixel-sharp text)
  wl-screenrec --framerate 60 --codec h264 -f capture_screen.mp4
  # Or with wf-recorder (specify monitor/geometry when multi-display)
  wf-recorder -r 60 -g "0,0 1920x1080" -c libx264 -p crf=16 -f capture_screen.mp4
  ```
- **Syncing dual sources**: Start both camera desk B-roll and direct screen capture with a visible visual/audio clap or unmistakable UI state toggle (e.g., pressing a physical key/button that flips a high-contrast screen state) so you can align exact `trim` offsets to a single frame.
- **Normalize frame rate & color space before compositing**: Convert both B-roll and direct capture to the exact same `fps` (`30` or `60`), `setsar=1`, and `format=yuv420p` prior to PiP or cutaway concat.

### B. Clean PiP & Cutaway Framing
- **A-roll / B-roll alternation (preferred for high-craft launch cuts)**:
  1. Open (`0–2s`) on a tactile physical shot (hand reaching for the phone/laptop/hardware, LED/screen waking up).
  2. Cut sharply into **full-frame pixel-perfect direct screen capture** for the actual UI/agent/benchmark proof so every character is razor sharp.
  3. Use a **clean Picture-in-Picture (PiP) card** only when simultaneous cause-and-effect matters (for example, physical device touch/trigger in the corner while direct screen capture drives the main canvas, or vice versa).
- **FFmpeg rounded/bordered PiP composite** (direct screen capture `[0:v]` full-frame + physical desk B-roll `[1:v]` docked bottom-right with a clean `2px` border):
  ```bash
  ffmpeg -y -i capture_screen.mp4 -i desk_broll.mp4 -filter_complex "
    [0:v]scale=1920:1080:flags=lanczos,fps=30,setsar=1[main];
    [1:v]scale=520:-2:flags=lanczos,fps=30,setsar=1,pad=iw+8:ih+8:4:4:color=#14130f,pad=iw+4:ih+4:2:2:color=#e4c47d[pip];
    [main][pip]overlay=W-w-36:H-h-36:shortest=1,format=yuv420p[vout]
  " -map "[vout]" -c:v libx264 -crf 17 -preset medium -movflags +faststart composite_picture.mp4
  ```

### C. Restrained Kinetic Telemetry Callouts
- Use kinetic callouts sparingly to anchor real, verified measurements right as the viewer sees the behavior happen (for example, latency, FPS, wattage, throughput, or verified state receipt).
- Keep each callout to **one crisp line (`<= 4–6` words or metric + unit)**, anchored in a quiet corner outside the active cursor/focus zone, entering with a tight `150–250 ms` ease/fade and exiting cleanly before the next cut. Never stack persistent dashboard clutter over the whole video.

## 5. Fail-Closed Privacy & PII Redaction Protocol

Real screen recordings frequently leak usernames, window title bars, chat input prompts, browser tabs, emails, or terminal secrets. Enforce this exact order:

1. **Inventory sensitive zones first**: Scan full-frame samples (including window title bars, chat boxes, dock/menu bar, and terminal output) with OCR before cutting.
2. **Mask BEFORE any crop, scale, or PiP magnification**:
   - Apply solid opaque black redaction boxes (`drawbox=x=...:y=...:w=...:h=...:color=black:t=fill` or NumPy zero-fill `frame[y1:y2, x1:x2] = 0`) directly on the raw source region before duplicating that frame into zoomed lenses or split-screen views.
3. **Strip container metadata**: Always pass `-map_metadata -1 -map_chapters -1` on every intermediate and final render so source filenames, macOS creation metadata, or chapters never leak.
4. **Verify 100% of output frames**:
   - **Opaque mask check**: Pipe the redacted rectangle across all output frames (`-vf crop=W:H:X:Y,format=gray -f rawvideo -`) and assert `max(bytes) < 16` and exact expected frame count.
   - **Full-timeline OCR sweep**: Extract frames across the finished export (`15–30 fps`) and run OCR (e.g., Apple Vision `VNRecognizeTextRequest` on macOS or Tesseract) asserting zero matches for redacted usernames/emails and zero matches for terminal secret markers (`password`, `bearer`, `private key`, `api_key`, `access_token`, `refresh_token`).
   - **Re-verify after every layout/crop revision**: Changing canvas height shifts Y coordinates — re-derive mask coordinates and re-run verification on the final file.

## 6. FFmpeg Assembly Recipes & Pitfalls

- **Consistent SAR & pixel format before `concat`**: Every input segment to `concat=n=K:v=1:a=0` MUST share identical `width×height`, `fps`, and `setsar=1`. Mismatched SAR or timebases silently desync or abort concat.
- **Exact frame count on rawvideo piping**: Drain decoder stdout cleanly before `wait()` to avoid broken-pipe exit codes, and assert `nb_frames == duration * fps` with `ffprobe`.
- **Keep audio channels & sample rate uniform before `amix`**: Normalize every audio leg with `aformat=sample_rates=48000:channel_layouts=stereo` and pass `normalize=0` to `amix` so FFmpeg does not silently halve gain every time you add a track; finish with `alimiter=limit=0.92:attack=5:release=60` before final `loudnorm`.
- **Lossless picture revision check**: When swapping voiceover or music on a locked picture, remux with `-c:v copy` and verify identical video stream digest:
  ```bash
  ffmpeg -nostdin -v error -i final.mp4 -map 0:v:0 -c copy -f hash -hash sha256 -
  ```

## 7. Final Pre-Handoff QA Checklist

- [ ] **First 2 seconds**: Opens immediately on the real flex/hook — no dead setup or cluttered header.
- [ ] **Contact sheet inspected**: First shot, fastest sequence, beat-drop/transition, callout/lens, and last frame checked visually at feed width.
- [ ] **Muted readability**: Visual story and focus are clear with audio off.
- [ ] **Audio balance**: Speech clear over ducked music, no clipping, `I` near `-14` to `-16 LUFS`, true peak `<= -1.0 dBTP` post-AAC.
- [ ] **Phone-speaker pass**: Mono band-limited check (`200–5000 Hz`) confirms transitions hit and narration stays crisp.
- [ ] **Privacy verified**: Opaque mask confirmed on all frames, OCR sweep clean, container metadata stripped.
- [ ] **Technical spec verified**: `verify_video_export.py verify` passes (`h264`/`yuv420p`, `+faststart`, exact dimensions/FPS/duration, file size under target).
