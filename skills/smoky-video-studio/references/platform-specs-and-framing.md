# Platform Specs, Aspect Ratios & Visual Restraint

Use this reference to pick target dimensions, duration budgets, encoding ceilings, and framing safe zones before generating keyframes or cropping captures.

## 1. Platform & Placement Matrix

| Preset ID | Target Surface | Dimensions (Aspect) | FPS | Ideal Runtime | Video / Audio Target | Size / Special Rules |
| --- | --- | --- | --- | --- | --- | --- |
| `x-square` | X / Twitter feed (film or demo) | `1080×1080` (`1:1`) | `24` or `30` | `15–20s` demo; `45–60s` film | H.264 `yuv420p`, CRF 22–23 (`maxrate 3.5–5M`), AAC 192k 48kHz stereo, `+faststart` | `< 512 MB` platform cap (`< 20 MB` target for instant mobile start); max 140s standard |
| `x-portrait` | X feed tall demo (app + terminal stack) | `1080×1020` to `1080×1350` (`~1:1` to `4:5`) | `30` | `15–20s` | H.264 `yuv420p`, CRF 16–22, AAC 192k 48kHz stereo, `+faststart` | Keeps desktop/app viewport + live terminal legible on mobile without vertical feed cropping |
| `x-landscape` | X / LinkedIn / blog widescreen | `1920×1080` (`16:9`) | `24` or `30` | `15–60s` | H.264 `yuv420p`, CRF 20–23, AAC 192k 48kHz stereo, `+faststart` | Keep primary subject inside central `1080×1080` safe square if also exporting `1:1` or `9:16` |
| `reels-shorts` | Instagram Reels / YouTube Shorts / TikTok | `1080×1920` (`9:16`) | `30` or `60` | `15–45s` | H.264 `yuv420p`, CRF 20–22, AAC 192k 48kHz stereo, `+faststart` | Reserve **top 14%**, **bottom 22%**, and **right 15%** for native platform HUD/buttons |
| `youtube-hd` | YouTube standard upload / launch film | `1920×1080` or `3840×2160` (`16:9`) | `24`, `30`, or `60` | `45s–3m+` | H.264/HEVC `yuv420p`, CRF 16–18 archival, AAC 256k 48kHz stereo, `+faststart` | Integrated loudness `-14 LUFS` target, true peak `<= -1.0 dBTP` |
| `web-hero` | Website / landing-page hero loop | `1920×1080` or `1280×720` (`16:9`) | `24` or `30` | `6–12s` | H.264 `yuv420p` (`-an` muted by default) + optional VP9/WebM, `+faststart` | `< 3–5 MB` hard budget; ship a matching `< 150 KB` WebP/JPEG poster frame (`frame 0`) |
| `demo-tall` | Mobile / phone app showcase | `1080×1920` (`9:16`) or `1080×1350` (`4:5`) | `30` or `60` | `12–25s` | H.264 `yuv420p`, AAC 192k 48kHz stereo, `+faststart` | Frame device cleanly on subtle neutral backdrop; never clip status bar or bottom gesture bar accidentally |

## 2. Multi-Ratio Safe-Zone Framing Strategy

When one piece must ship across `16:9`, `1:1`, and `9:16` without regenerating video clips:

1. **Generate `16:9` (`1920×1080`) master keyframes and video clips** with explicit prompt direction: *"centered composition within the middle square of the frame"*.
2. **Center-crop for `1:1` (`1080×1080`)**: `crop=1080:1080:420:0,setsar=1`.
3. **Tight punch-in surge (`1.25×`)**: `crop=864:864:528:108,scale=1080:1080:flags=lanczos,setsar=1` — great for accelerating energy right before a beat drop without generating extra shots.
4. **Native `9:16` reframe**: Center-crop `608×1080` (`crop=608:1080:656:0,scale=1080:1920:flags=lanczos`) only when source resolution is `>= 1080p` and subject stays tight; for rich `9:16` campaigns, generate native `9:16` keyframes/clips directly instead of upscaling `3×`.
5. **Split-screen comparison inside `1:1` (`1080×1080`)**: Crop two `538×1080` halves (`crop=538:1080:691:0`) separated by a `4px` black divider (`color=c=black:s=4x1080`) via `hstack=inputs=3`.

## 3. Two-Tier Export Standard

Always produce two cleanly separated outputs from the same verified master timeline:

- **Archival master**: `libx264 -preset medium -crf 16` (or `17`), `yuv420p`, `aac -b:a 192k -ar 48000`, `-movflags +faststart`.
- **Social / web delivery copy**: Re-encode video with bitrate cap (`-crf 23 -maxrate 3500k -bufsize 7000k`) while stream-copying the mastered audio (`-c:a copy`), `-movflags +faststart`, and `-map_metadata -1 -map_chapters -1`.
- **Collision-safe writes**: Never silently clobber an earlier version the owner may still compare (`name.mp4`, `name-2.mp4`, or explicit revision suffix) unless overwrite was requested.

## 4. Visual Restraint & Taste Checklist

Apply these filters before showing a cut to the owner:

- **Kill redundant headers**: If the tweet, README, or page heading already says `"Tool X + Model Y"`, removing the baked-in top header bar almost always makes the video look 2× cleaner and lets the footage fill the feed.
- **Kill gimmicky play-by-play captions**: Avoid noisy HUD text describing obvious action (`"Out of ammo"`, `"Clicking menu"`). Use captions only when muted comprehension genuinely needs a concise <=6-word beat or an enlarged proof receipt.
- **No mid-move jump cuts**: If an opening dolly or pan needs to last 10–12 seconds, slow one continuous clip smoothly (`setpts=1.25*(PTS-STARTPTS)`) rather than cutting between two mismatched takes of the same angle.
- **Let one proof moment breathe**: Rapid 0.7–1.1s cuts create kinetic energy, but giving the single most important proof beat `3–4 s` (with a crisp zoomed receipt or slow landing) turns "cool montage" into "I understand what this actually does".
- **Subtle film finish, never heavy Instagram filters**: For archival/cinematic films, keep finish restrained (`vignette=PI/6,noise=alls=5:allf=t+u`) so compression does not turn heavy grain into blocky artifacts on X or YouTube.
- **Keep social copy synced to the cut**: When drafting launch copy alongside the video, map 1 concise beat in the clip to each key component or collaborator mentioned in the post so viewers immediately recognize what each tag refers to.
