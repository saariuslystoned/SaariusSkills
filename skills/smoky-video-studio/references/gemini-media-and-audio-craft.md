# Gemini Media Generation & Cinema Audio Craft

Use this reference when generating visual plates, video clips, voices, or scores via `gemini-api` (or an equivalent approved Gemini SDK consumer) and mastering audio transitions in Python DSP + FFmpeg.

## 1. Gemini Media Pipeline (`gemini-api` CLI)

Check current CLI help, auth readiness, and model availability before submitting batches. Never print or inspect API keys or credential stores.

### A. Style-Locked Keyframes (`gemini-api image`)
Generate every still plate **before** animating clips, sharing one verbatim style prefix across the entire act so grain, lighting, lens depth, and safe-square composition stay locked:

```bash
STYLE_BW="Extreme macro still from an archival 1960s 16mm black-and-white film, shallow depth of field, authentic silver halide grain, subtle optical halation, centered composition within the middle square of the frame, no text overlays, no watermarks."

gemini-api image "$STYLE_BW <shot subject and lighting>" \
  --aspect-ratio 16:9 --image-size 1K --out keyframes/kf01.png
```

Inspect **every** generated keyframe visually before spending video generation calls.

### B. Video Clips With Clean Foley (`gemini-api video`)
Always run `--dry-run` on one clip first to verify the JSON `--body` schema, then launch independent clips in parallel and record operation IDs for resume rather than duplicating jobs.

- **Single-frame (`image_to_video`)**: Pass `-i keyframes/kf01.png`.
- **Controlled morph / color ignition (two-frame transition)**: Pass `-i keyframes/kf_start.png -i keyframes/kf_end.png` so the model bridges exact start and end visual states cleanly.
- **Audio hygiene prompt rule**: End every video prompt with `"Subtle natural foley only, no music, no speech."` so the clip supplies tactile texture without fighting your voiceover or score.

```bash
BODY='{"generation_config":{"video_config":{"task":"image_to_video"}},"response_format":{"type":"video","aspect_ratio":"16:9","resolution":"1080p","duration":"8s"}}'

gemini-api video "<motion + natural foley prompt>. No music, no speech." \
  -m gemini-omni-1.2-flash \
  -i keyframes/kf01.png \
  --body "$BODY" --dry-run
```

Render a `4×2` contact sheet (`fps=1,scale=480:-1,tile=4x2`) for every returned clip and inspect for framing drift, artifacts, or unwanted camera cuts before editing.

### C. Bespoke & Multi-Speaker Voiceover (`gemini-api tts` / `voices create`)
- **Custom brand narrator**: Create one reusable voice with `gemini-api voices create --store=true --voice '{"type":"prompted","prompted":{"input":"<persona description>"}}' -o json`, then pass its returned voice ID to all act takes for consistent timbre across cuts.
- **Two-voice exchanges**: Use speaker labels in the script plus `--multi-speaker 'Narrator=Kore,Analyst=Fenrir'` and request a clean `~0.5–1.0 s` pause between turns.
- **Pronunciation & tone hygiene in `--style`**:
  - Put **only spoken words** in the script; put acting, cadence, and pronunciation cues in `--style`.
  - Spell out acronyms explicitly (`"Say C U A as three letters"`, `"Say A P I individually"`), clarify homographs (`"Pi rhymes with pie"`), and request `"Dry close-miked speech only. Say each line once. No added words or background audio."`
  - Keep technical demo narration **informative and natural** — avoid theatrical or gimmicky lines that feel awkward on repeat listens.
- **Turn slicing & timing**: Run `silencedetect` on every generated WAV to locate exact phrase boundaries:
  ```bash
  ffmpeg -hide_banner -i audio/voices.wav -af 'silencedetect=noise=-35dB:d=0.22' -f null - 2>&1 | grep silence_
  ```
  Slice each turn into an independently placed cue; if a single line runs slightly long, apply mild `atempo=1.08..1.22` rather than crowding the next cut.
- **Fast A/B voice auditioning**: Keep a locked picture-only master (`picture.mp4`) and remux candidate voice mixes with `-c:v copy` (verify identical video stream SHA-256) so the user can compare 2–3 script options by ear in seconds.

### D. Instrumental Score Stems (`gemini-api music`)
Generate separate stems per act (`music_act1.mp3`, `music_act2.mp3`) — or pair a thematic/genre-nod intro cue with a high-energy Lyria drop:

- Always specify: `"Instrumental only, strictly no vocals"`, exact BPM and key (e.g., `D minor` building into `D major` payoff), `"groove starts immediately"` (no sluggish ambient intro for short social edits), and `"keep the arrangement sparse in the voice band (1–4 kHz) with clean transients for editing"`.

---

## 2. Cinema DSP Transition Architecture (Python + NumPy)

When a standard crossfade or hard mute sounds flat, synthesize transitions deterministically at `48 kHz` stereo float64:

### A. Tape-Acceleration / Pitch-Warp Riser Into Silence
Smoothly accelerate playback speed and pitch over the final `1.2–8.0 s` before the drop (`u = (t - warp_start) / (drop_t - warp_start)`):

1. **Nonlinear playback warp**: `rate = 1.0 + 0.155 * (u ** 2.15)` (or `read_from = (t + 0.45 * warp**3) * SR`) with linear sample interpolation (`np.interp`).
2. **Progressive brightness bloom**: Blend a high-shelf FFT boost (`1 + 1.45 / (1 + (1600 / f)^2)`) scaled by `u ** 1.8`.
3. **Resonant tension riser**: Layer band-swept pink-tilted noise (`180–600 Hz -> 600–2000 Hz -> 1800–5800 Hz`) plus an octave-rising fifth/root synth tone with subtle binaural azimuth orbit collapsing to dead-center at `u = 1`.
4. **Hard gate + vacuum ghost tail**: Gate dry score cleanly over `15–20 ms` right on the cut/syllable, then leave a decaying `150–220 ms` multi-tap stereo echo ghost tail inside the first sliver of silence before true zero.

### B. Post-Blackout Re-Entry Transient ("Shock It Into Action")
Never bring Act II back with a slow fade-in after a blackout. Combine three aligned events on **exact frame 1 out of silence**:

1. **Hard visual cut** (zero fade-in).
2. **Chord/beat onset alignment in the new score**: Scan the target music stem in `20–50 ms` RMS windows and pick the sharpest positive energy jump (`argmax(diff(rms))`) as the `atrim` start point, with a crisp `8–12 ms` anti-click attack.
3. **Layered phone-translatable transient (`reentry_thump.wav`)**:
   - *Sub-kick body*: Pitch-dropped sine `155 Hz -> 52 Hz` (`tau = 28 ms`) with warm `tanh` 2nd-harmonic saturation so small speakers hear harmonic punch even below their bass rolloff.
   - *Felted low-mid snap*: Bandpassed noise burst (`120–680 Hz`, `3 ms` attack, `32 ms` decay) — critical for unmistakable punch on mobile speakers.
   - *Stereo harmonic bloom*: Wide detuned chord pad (`8–12 ms` attack, `1.2–1.5 s` exponential decay) bridging smoothly into the Act II score.
4. **Narration offset**: Re-enter voiceover `+200–250 ms` *after* the visual cut and transient hit.

### C. Cursor / UI-Synced Procedural Foley
Drive every sound from the retimed `cues.json` (`depart`, `land`, `direction` in `[-1, 1]`):

- **Swipe / movement**: Bandpassed noise (`650–4300 Hz`) + subtle rising sine sweep, shaped by `sin(pi * progress)^1.55`, panned dynamically from `-0.65 * dir` to `+0.72 * dir`.
- **Landing click / menu open**: Short damped resonant tap (`1440 Hz` + `390 Hz` + `2100–8400 Hz` crisp transient burst) with small per-hit pitch variation (`(i % 5) * 75 Hz`) to prevent machine-gun fatigue. Double-tap (`+41 ms` at `0.43×` gain) for menu opens or finish beats.
- **Split-screen binaural foley**: Separate left/right clip foley with `pan=stereo|c0=0.80*c0|c1=0.30*c1` vs `c0=0.30*c0|c1=0.80*c1` so headphones feel subtle spatial width without collapsing poorly to mono.

---

## 3. Mixing, Loudness & Phone-Speaker Mastering

- **Voice EQ & presence**: `highpass=f=75..100`, subtle presence lift (`equalizer=f=2800:t=q:w=1.2:g=1.5`), gentle soft-clip saturation (`tanh(x * 2.2) / 2.2`).
- **Music ducking under speech** (choose deterministic envelope ducking in Python/NumPy — `0.27–0.32` linear gain / `-10` to `-11.5 dB` with `80–90 ms` ramps — **or** automatic FFmpeg `sidechaincompress` driven by the Gemini TTS voiceover track):
  ```bash
  # Automatic FFmpeg sidechain-ducked music bed under Gemini TTS voiceover, mastered to -14 LUFS
  ffmpeg -y -i composite_picture.mp4 -i audio/vo.wav -i audio/music_bed.mp3 -filter_complex "
    [1:a]aformat=sample_rates=48000:channel_layouts=stereo,highpass=f=80,equalizer=f=2800:t=q:w=1.2:g=1.5,asplit=2[vo_mix][vo_sc];
    [2:a]aformat=sample_rates=48000:channel_layouts=stereo,volume=0.45[bed];
    [bed][vo_sc]sidechaincompress=threshold=0.025:ratio=6:attack=25:release=260:makeup=1[bed_ducked];
    [vo_mix][bed_ducked]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=7,aresample=48000[aout]
  " -map 0:v:0 -map "[aout]" -c:v copy -c:a aac -b:a 192k -movflags +faststart final_launch.mp4
  ```
- **Final loudness normalization** (`I=-14` for YouTube / hardware launch demos; `I=-15` for punchy X / Reels / Shorts feeds):
  ```bash
  ffmpeg -i picture.mp4 -i mix.wav -map 0:v:0 -map 1:a:0 -c:v copy \
    -af 'loudnorm=I=-15:TP=-1.7:LRA=7,aresample=48000' \
    -c:a aac -b:a 192k -movflags +faststart final.mp4
  ```
- **Verify *after* AAC encoding** (lossy AAC can raise inter-sample true peaks by `0.5–1.5 dB`; apply `-1.5` to `-1.8 dB` trim if true peak exceeds `-1.0 dBTP`):
  ```bash
  ffmpeg -hide_banner -i final.mp4 -vn -af 'ebur128=peak=true' -f null - 2>&1 | grep -E 'I:|Peak:'
  ```
- **Simulated mono phone-speaker audit**:
  ```bash
  ffmpeg -y -v error -i final.mp4 -vn \
    -af 'pan=mono|c0=0.5*c0+0.5*c1,highpass=f=200,lowpass=f=5000' \
    -ar 16000 phone_mono.wav
  ```
  Audition `phone_mono.wav` (and optionally run local `whisper` ASR against it) to confirm zero phase cancellation, clear speech intelligibility, and audible transition impact on small speakers.
