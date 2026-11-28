---
name: smoky-video-studio
description: Design, edit, score, voice, composite, and verify high-craft short-form videos — social clips (X, Reels/Shorts, YouTube), website hero loops, AI launch films, and computer-use or hardware product demos. Combines Gemini media generation (keyframes, video clips, multi-speaker TTS, Lyria scores) with frame-accurate FFmpeg, Python DSP/tracking, or procedural canvas/Remotion assembly, fail-closed privacy redaction, contact-sheet frame QA, and mono phone-speaker mastering. Use when asked to produce, recut, voice, score, redact, or polish a video from a concept, reference edit, or raw recording.
---

# Smoky Video Studio (`smoky-video-studio`)

Turn a raw screen recording, hardware capture, reference edit, or abstract brief into a **finished, verified video** — with tight pacing, intentional sound design, fail-closed privacy redaction, and proven playback on both headphones and phone speakers.

```text
Pick Track & Hook -> Scout / Generate Plates -> Frame-Numbered Edit & Speed Ramps -> Score, Voice & Synced SFX -> Privacy, Visual & Speaker QA -> Verified Export
```

Load references as needed:
- [references/platform-specs-and-framing.md](references/platform-specs-and-framing.md) — aspect ratios (`16:9`, `1:1`, `4:5`, `9:16`), duration targets, safe zones, encoding budgets, and visual restraint rules.
- [references/gemini-media-and-audio-craft.md](references/gemini-media-and-audio-craft.md) — `gemini-api` CLI patterns (keyframes, video, custom/multi-speaker TTS, Lyria stems), tape-warp risers, post-blackout re-entry transients, directional UI foley, ducking, and phone-speaker mastering.
- [references/compositing-tracking-and-qa.md](references/compositing-tracking-and-qa.md) — coarse-to-fine contact-sheet scouting, cursor/subject tracking, non-uniform speed ramps, auto-docked PiP zoom lenses, fail-closed privacy redaction, Remotion vs FFmpeg selection, and frame-QA checks.

---

## 1. Choose the Production Track First

Match tooling to the source material instead of forcing every video through one pipeline. Do not generate synthetic video when real product capture is the proof, and do not build a heavy React/Remotion project when an FFmpeg + Python pipeline is faster and more frame-accurate.

| Track | Source Material | Best Fit | Core Stack |
| --- | --- | --- | --- |
| **Track A — AI Launch / Concept Film** | Brief or reference edit | Brand teasers, abstract product reveals, moody 30–60s social films | Style-locked keyframes (`gemini-api image`) -> video + natural foley (`gemini-api video`) -> custom TTS + Lyria stems -> Python DSP + FFmpeg edit |
| **Track B — Screen / Computer-Use / Hardware Demo** | Live desktop/Wayland capture (`wf-recorder` / `wl-screenrec` / screen recorder) and/or physical phone/device desk B-roll | Product launches, agent/CUA showcases, dual-source hardware + UI demos (`15–30s` social or `45–60s` launch cuts) | Coarse-to-fine contact sheets -> privacy redaction -> dual-source PiP/cutaway compositing, subject/cursor tracking + non-uniform speed ramps, restrained kinetic telemetry callouts -> multi-voice TTS + sidechain-ducked score (`-14` to `-15 LUFS`) + frame-synced UI foley |
| **Track C — Procedural Motion / Explainer Micro-Drop** | Concept, diagram, or UI flow | 10–25s clean explainers, typographic/kinetic cards, website feature loops | Remotion / HTML Canvas / SVG animation + procedural DSP or WebAudio SFX (zero API burn) |
| **Track D — Hybrid / Multi-Ratio Campaign** | Capture + generated plates/audio | Hero launches shipping across X (`1:1`/`16:9`), Reels/Shorts (`9:16`), YouTube (`16:9`), and landing pages | Center-safe `16:9` master plates + tracked capture + shared `cues.json` timeline -> native multi-ratio reframes |

---

## 2. Core Pacing, Framing & Restraint Rules

These defaults solve the most common ways AI-assisted and demo edits feel amateur:

1. **Hook With the Real Flex in the First 2 Seconds**:
   - Open straight on the defining motion, outcome, or visual transformation — never on a slow logo card, empty setup, or generic background gameplay/UI.
   - For computer-use or workflow demos, select cuts by **visible pointer/action travel, target landings, UI state changes, and live tool/terminal receipts**; aggressively compress dead idle waits.
2. **Strip Redundant Headers & Caption Clutter**:
   - When the surrounding X post, YouTube description, or landing-page section already names the stack or product, **do not burn redundant title banners or gimmicky play-by-play labels over the video**. Let clean framing and crisp voiceover carry the story.
   - Only keep on-screen callouts that prove something the viewer cannot otherwise read at feed size (for example, an enlarged terminal verification receipt, a restrained kinetic telemetry callout synced to a hardware/benchmark beat, or a <=6-word explainer step).
3. **Prefer Unbroken Camera Moves Over Awkward Jump Cuts**:
   - Never splice two similar angles of the same opening shot mid-move. Use one continuous slow dolly/pull or cut decisively to a contrasting scale or subject.
4. **Tension-Warp -> Silence -> Re-Entry Transient (Beat-Drop Architecture)**:
   - Cutting music abruptly into black feels accidental, and fading lazily back out of black kills energy.
   - **Into the drop:** Accelerate/pitch-warp the score (`1.00x -> ~1.15x` nonlinear curve), tighten and speed-ramp the final 1–2 cuts (`1.35x–1.45x`), layer a rising tension sweep, and slam cleanly to silence on an exact syllable or action landing with a brief hollow tail (`~100–220 ms`).
   - **Silence pocket:** Hold pure silence/black (`0.10–0.20 s` for snappy 15–20s demos; `1.5–1.8 s` for dramatic 45–60s films).
   - **Out of the drop:** **Hard-cut visuals on frame 1** (zero fade-in), land the new score section on a measured **chord/beat onset**, fire a synthesized **re-entry transient** (sub-kick + warm `120–680 Hz` mid-body so phone speakers feel the hit), and bring narration back `+200–250 ms` *after* the hit.
5. **Respect Runtime & Narrative Beat Budgets**:
   - **Social product/CUA demo:** `15–20 s` — fast hook, 2–3 distinct proof beats (giving one key interaction room to breathe), optional 1-beat architecture callout so each collaborator/component gets a clear moment.
   - **Narrative launch film:** `45–60 s` — stillness -> rhythm/escalation -> blackout drop -> turn -> color/visual payoff.
   - **Website hero background loop:** `6–12 s` — muted-first readability, smooth loop point, lightweight file size (`< 3–5 MB`).

---

## 3. Production Workflow (Keep Assets & Timeline Modular)

Keep source media, intermediate picture masters, and audio stems in separate folders (`keyframes/`, `clips/`, `audio/`, `final/`) driven by a frame-numbered `cues.json` timeline so voice or score revisions remux in seconds (`-c:v copy`) without re-rendering picture or burning duplicate API calls.

1. **Scout or Reverse-Engineer First**:
   - **Reference edit:** Probe with `ffprobe`, render a labeled contact sheet, extract audio, and log exact timestamps of shots, split-screens, buildups, silences, and payoffs before designing original material.
   - **Long recording:** Run coarse-to-fine contact sheets (`60s -> 10s -> 2s -> 0.2s` steps) and optional CV template matching to rank high-action windows before cutting.
2. **Generate Only the Missing Modalities** (see [references/gemini-media-and-audio-craft.md](references/gemini-media-and-audio-craft.md)):
   - **Keyframes (`gemini-api image`):** Lock look, lens, lighting, and centered safe-square framing first; visually inspect every still before animating.
   - **Video clips (`gemini-api video`):** Validate `--body` with `--dry-run`, launch independent clips in parallel, use two-frame (`-i start -i end`) prompts for controlled color/state morphs, and request **natural foley only — no music, no speech** so audio layers stay cleanly separated. Inspect contact sheets of every clip before assembly.
   - **Voiceover (`gemini-api tts` / `voices create`):** Put spoken text in the script and pacing/pronunciation rules in `--style` (spell out acronyms like `C U A` or `A P I`, clarify homographs like *"Pi rhymes with pie"*). For two-voice exchanges, use `--multi-speaker` and split turns via `silencedetect` into independently timed cues. Keep delivery informative and natural; audition 2–3 script options over the locked picture (`-c:v copy`) when tuning tone.
   - **Score (`gemini-api music` / Lyria or local DSP):** Request strictly instrumental stems with explicit BPM, key, immediate downbeat, and a sparse vocal register. Use genre-twist intros warped into an energetic drop when matching playful/technical footage.
3. **Edit Picture, Dual-Source Hardware Compositing, Tracking & Synced Foley** (see [references/compositing-tracking-and-qa.md](references/compositing-tracking-and-qa.md)):
   - For **hardware + live UI launch demos**, pair real physical phone/device desk B-roll with pixel-perfect direct screen captures (`wf-recorder` / `wl-screenrec` on Wayland, or lossless desktop/device capture) using clean PiP insets or crisp cutaways so viewers get both physical authenticity and razor-sharp UI legibility.
   - Apply **non-uniform speed ramps** (compress idle edges, slow transit & target landings) and write exact output cue times (`cut`, `depart`, `land`, `direction`) to `cues.json`.
   - When small UI interactions would disappear at mobile feed size, layer an accent motion trail, touchdown ring, and a **smoothed tracked zoom inset** auto-docked to the lowest-overlap corner (or brief kinetic telemetry callouts for key hardware/runtime beats).
   - Drive UI foley directly from `cues.json`: stereo-pan swishes along travel direction, fire crisp pitch-varied clicks on exact landing frames, duck music (`sidechaincompress` or `-10` to `-12 dB` envelope) under speech, and master via EBU R128 `loudnorm` (`I=-14` for YouTube/launch demos, `I=-15` for punchy social feeds; `TP=-1.5..-1.8`, `LRA=7`).

---

## 4. Fail-Closed Privacy, Visual QA & Speaker Mastering

Never hand back an uninspected render. Every finished video must pass four checks:

1. **Privacy Redaction Before Reframing (Screen/Device Captures)**:
   - Mask usernames, window titles, emails, tokens, and private tabs on the source geometry **before** any crop, scale, or PiP zoom duplicates pixels.
   - Strip container metadata and chapters (`-map_metadata -1 -map_chapters -1`).
   - Verify **every output frame**: assert opaque black mask luma (`max < 16`) across 100% of frames and run an OCR sweep for redacted identifiers plus terminal secret markers (`password`, `bearer`, `api_key`, `token`, `private key`).
2. **Visual Frame-QA at Feed Size**:
   - Render and inspect a contact sheet covering the **first shot, fastest sequence, beat-drop/transition, zoomed callout, and final frame** at realistic feed width. Verify the cut still tells a clear story **muted**.
3. **Stereo + Simulated Mono Phone-Speaker Check**:
   - Verify post-AAC loudness and true peak (`ebur128=peak=true`).
   - Render and audition a simulated phone speaker pass (`pan=mono|c0=0.5*c0+0.5*c1,highpass=f=200,lowpass=f=5000`) — and optionally run local ASR (`whisper`) on it — to prove narration and low-end transients stay punchy and intelligible out loud, not just in studio headphones.
4. **Deterministic Export Verification**:
   - Export an archival master (`crf 16–17`) plus a social/web delivery copy (`crf 22–23`, `yuv420p`, `48 kHz` AAC, `+faststart`, collision-safe filename), and verify it with the bundled standard-library checker:

```bash
python3 skills/smoky-video-studio/scripts/verify_video_export.py spec --pretty
python3 skills/smoky-video-studio/scripts/verify_video_export.py verify \
  <path/to/export.mp4> \
  --preset x-square \
  --check-loudness \
  --check-mono \
  --check-cues <path/to/cues.json> \
  --pretty
```

Report provenance clearly at handoff: which elements are **real capture**, **AI-generated**, or **locally synthesized**, alongside exact dimensions, duration, loudness, file size, and any remaining limitations. Publishing to social platforms, uploading to external release shelves, spending API budget beyond task scope, and overwriting existing final exports remain governed by the active repository's authorization gates.
