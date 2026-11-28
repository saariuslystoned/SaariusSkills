#!/usr/bin/env python3
"""Deterministic video export, MP4 faststart, audio loudness, mask, and cue verifier.

Uses only the Python standard library; invokes ``ffprobe`` / ``ffmpeg`` when
present for stream, loudness, mono-speaker, and privacy-mask inspection.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path
from typing import Any

SPEC_SCHEMA = "smoky-video-studio.spec.v1"
VERIFY_SCHEMA = "smoky-video-studio.verify.v1"
ERROR_SCHEMA = "smoky-video-studio.error.v1"

def _preset(
    description: str,
    *,
    aspect_range: list[float],
    min_width: int,
    max_width: int,
    min_duration_s: float,
    max_duration_s: float,
    max_bytes: int,
    recommended_max_bytes: int,
    allowed_video_codecs: list[str] | None = None,
    require_audio: bool = True,
    forbid_audio: bool = False,
    allowed_audio_codecs: list[str] | None = None,
    allowed_sample_rates: list[int] | None = None,
    lufs_range: list[float] | None = None,
    max_true_peak_dbtp: float | None = -1.0,
) -> dict[str, Any]:
    return {
        "description": description,
        "aspect_range": aspect_range,
        "min_width": min_width,
        "max_width": max_width,
        "min_duration_s": min_duration_s,
        "max_duration_s": max_duration_s,
        "max_bytes": max_bytes,
        "recommended_max_bytes": recommended_max_bytes,
        "allowed_video_codecs": allowed_video_codecs if allowed_video_codecs is not None else ["h264", "hevc"],
        "required_pix_fmt": "yuv420p",
        "require_audio": require_audio,
        "forbid_audio": forbid_audio,
        "allowed_audio_codecs": allowed_audio_codecs if allowed_audio_codecs is not None else (
            [] if forbid_audio else ["aac"]
        ),
        "allowed_sample_rates": allowed_sample_rates if allowed_sample_rates is not None else (
            [] if forbid_audio else [44100, 48000]
        ),
        "require_faststart": True,
        "lufs_range": None if forbid_audio else (lufs_range if lufs_range is not None else [-18.0, -12.0]),
        "max_true_peak_dbtp": None if forbid_audio else max_true_peak_dbtp,
    }


PRESETS: dict[str, dict[str, Any]] = {
    "x-square": _preset(
        "X / Twitter 1:1 square feed video (launch film or demo)",
        aspect_range=[0.95, 1.05],
        min_width=720,
        max_width=1920,
        min_duration_s=2.0,
        max_duration_s=140.0,
        max_bytes=512 * 1024 * 1024,
        recommended_max_bytes=25 * 1024 * 1024,
    ),
    "x-portrait": _preset(
        "X / Twitter tall portrait demo (app + live terminal stack, ~1:1 to 4:5)",
        aspect_range=[0.75, 1.08],
        min_width=720,
        max_width=1920,
        min_duration_s=2.0,
        max_duration_s=140.0,
        max_bytes=512 * 1024 * 1024,
        recommended_max_bytes=25 * 1024 * 1024,
    ),
    "x-landscape": _preset(
        "X / LinkedIn / blog 16:9 widescreen video",
        aspect_range=[1.70, 1.85],
        min_width=1280,
        max_width=3840,
        min_duration_s=2.0,
        max_duration_s=140.0,
        max_bytes=512 * 1024 * 1024,
        recommended_max_bytes=40 * 1024 * 1024,
    ),
    "reels-shorts": _preset(
        "Instagram Reels / YouTube Shorts / TikTok 9:16 vertical video",
        aspect_range=[0.54, 0.58],
        min_width=720,
        max_width=2160,
        min_duration_s=3.0,
        max_duration_s=180.0,
        max_bytes=512 * 1024 * 1024,
        recommended_max_bytes=40 * 1024 * 1024,
    ),
    "youtube-hd": _preset(
        "YouTube 16:9 HD/4K upload",
        aspect_range=[1.75, 1.80],
        min_width=1920,
        max_width=3840,
        min_duration_s=3.0,
        max_duration_s=43200.0,
        max_bytes=2 * 1024 * 1024 * 1024,
        recommended_max_bytes=250 * 1024 * 1024,
        allowed_video_codecs=["h264", "hevc", "av1"],
        allowed_audio_codecs=["aac", "opus"],
        allowed_sample_rates=[48000],
        lufs_range=[-17.0, -12.0],
    ),
    "web-hero": _preset(
        "Website / landing-page muted autoplay hero loop",
        aspect_range=[1.20, 2.40],
        min_width=960,
        max_width=2560,
        min_duration_s=2.0,
        max_duration_s=20.0,
        max_bytes=8 * 1024 * 1024,
        recommended_max_bytes=5 * 1024 * 1024,
        allowed_video_codecs=["h264", "vp9", "av1"],
        require_audio=False,
        forbid_audio=True,
    ),
    "demo-tall": _preset(
        "Mobile or hardware showcase clip (9:16 or 4:5)",
        aspect_range=[0.54, 0.85],
        min_width=720,
        max_width=2160,
        min_duration_s=3.0,
        max_duration_s=120.0,
        max_bytes=512 * 1024 * 1024,
        recommended_max_bytes=35 * 1024 * 1024,
        require_audio=False,
    ),
}


def inspect_mp4_atoms(path: Path) -> dict[str, Any]:
    """Inspect top-level ISO BMFF / MP4 boxes using pure stdlib I/O.

    Returns box order and whether ``moov`` appears before ``mdat`` (+faststart).
    """
    atoms: list[str] = []
    moov_offset: int | None = None
    mdat_offset: int | None = None
    size_bytes = path.stat().st_size

    with path.open("rb") as fh:
        pos = 0
        while pos + 8 <= size_bytes:
            fh.seek(pos)
            header = fh.read(8)
            if len(header) < 8:
                break
            box_size, box_type_bytes = struct.unpack(">I4s", header)
            try:
                box_type = box_type_bytes.decode("ascii")
            except UnicodeDecodeError:
                break
            if not all(32 <= ord(ch) <= 126 for ch in box_type):
                break

            header_len = 8
            if box_size == 1:
                ext = fh.read(8)
                if len(ext) < 8:
                    break
                box_size = struct.unpack(">Q", ext)[0]
                header_len = 16
            elif box_size == 0:
                box_size = size_bytes - pos

            if box_size < header_len or pos + box_size > size_bytes:
                break

            atoms.append(box_type)
            if box_type == "moov" and moov_offset is None:
                moov_offset = pos
            elif box_type == "mdat" and mdat_offset is None:
                mdat_offset = pos
            pos += box_size

    is_mp4 = bool(atoms and atoms[0] == "ftyp")
    faststart: bool | None = None
    if is_mp4 and moov_offset is not None and mdat_offset is not None:
        faststart = moov_offset < mdat_offset
    return {
        "is_mp4": is_mp4,
        "atoms": atoms,
        "moov_offset": moov_offset,
        "mdat_offset": mdat_offset,
        "faststart": faststart,
    }


def validate_cues_data(cues: Any, duration_s: float | None = None) -> tuple[list[str], dict[str, Any]]:
    """Validate frame-timed cue list structure (``cut <= depart < land``)."""
    errors: list[str] = []
    if not isinstance(cues, list) or not cues:
        return ["cues.json must be a non-empty JSON array"], {"count": 0}

    prev_cut = -1.0
    kinds: dict[str, int] = {}
    for idx, entry in enumerate(cues):
        if not isinstance(entry, dict):
            errors.append(f"cue[{idx}] must be an object")
            continue
        kind = entry.get("kind")
        if not isinstance(kind, str) or not kind.strip():
            errors.append(f"cue[{idx}].kind must be a non-empty string")
        else:
            kinds[kind] = kinds.get(kind, 0) + 1

        try:
            cut = float(entry["cut"])
            depart = float(entry["depart"])
            land = float(entry["land"])
        except (KeyError, TypeError, ValueError):
            errors.append(f"cue[{idx}] must provide numeric cut, depart, and land timestamps")
            continue

        if cut < 0 or depart < 0 or land < 0:
            errors.append(f"cue[{idx}] timestamps must be non-negative")
        if cut < prev_cut - 1e-6:
            errors.append(f"cue[{idx}].cut ({cut:.3f}) regresses before previous cut ({prev_cut:.3f})")
        if not (cut <= depart + 1e-6 and depart < land):
            errors.append(
                f"cue[{idx}] must satisfy cut <= depart < land (got {cut:.3f}, {depart:.3f}, {land:.3f})"
            )
        if duration_s is not None and land > duration_s + 0.05:
            errors.append(f"cue[{idx}].land ({land:.3f}s) exceeds video duration ({duration_s:.3f}s)")

        if "direction" in entry:
            try:
                direction = float(entry["direction"])
            except (TypeError, ValueError):
                errors.append(f"cue[{idx}].direction must be numeric")
            else:
                if not (-1.0 <= direction <= 1.0):
                    errors.append(f"cue[{idx}].direction ({direction}) must be within [-1.0, 1.0]")

        prev_cut = cut

    return errors, {"count": len(cues), "kinds": kinds}


def evaluate_preset_constraints(
    preset_name: str,
    *,
    width: int | None,
    height: int | None,
    duration_s: float | None,
    size_bytes: int,
    video_codec: str | None,
    pix_fmt: str | None,
    has_audio: bool,
    audio_codec: str | None,
    sample_rate: int | None,
    faststart: bool | None,
    allow_silent: bool = False,
    max_bytes_override: int | None = None,
) -> tuple[list[str], list[str]]:
    """Evaluate media properties against a named platform preset."""
    preset = PRESETS[preset_name]
    errors: list[str] = []
    warnings: list[str] = []

    max_bytes = max_bytes_override if max_bytes_override is not None else preset["max_bytes"]
    if size_bytes > max_bytes:
        errors.append(f"file size {size_bytes} bytes exceeds {preset_name} limit ({max_bytes} bytes)")
    elif size_bytes > preset["recommended_max_bytes"]:
        warnings.append(
            f"file size {size_bytes} bytes exceeds recommended web delivery target ({preset['recommended_max_bytes']} bytes)"
        )

    if width is not None and height is not None and height > 0:
        if width < preset["min_width"] or width > preset["max_width"]:
            errors.append(
                f"width {width}px outside {preset_name} range [{preset['min_width']}..{preset['max_width']}]"
            )
        if width % 2 != 0 or height % 2 != 0:
            errors.append(f"dimensions {width}x{height} must be even for yuv420p H.264 compatibility")
        aspect = width / height
        lo, hi = preset["aspect_range"]
        if not (lo <= aspect <= hi):
            errors.append(f"aspect ratio {aspect:.3f} ({width}x{height}) outside {preset_name} range [{lo:.2f}..{hi:.2f}]")

    if duration_s is not None:
        if duration_s < preset["min_duration_s"] or duration_s > preset["max_duration_s"]:
            errors.append(
                f"duration {duration_s:.2f}s outside {preset_name} range [{preset['min_duration_s']}..{preset['max_duration_s']}s]"
            )

    if video_codec and video_codec not in preset["allowed_video_codecs"]:
        errors.append(
            f"video codec '{video_codec}' not in {preset_name} allowed list {preset['allowed_video_codecs']}"
        )

    if pix_fmt and preset["required_pix_fmt"] and pix_fmt != preset["required_pix_fmt"]:
        errors.append(f"pixel format '{pix_fmt}' must be '{preset['required_pix_fmt']}' for cross-device playback")

    if preset.get("forbid_audio") and has_audio:
        errors.append(f"preset '{preset_name}' expects a muted video (-an), but an audio stream is present")
    elif preset["require_audio"] and not has_audio and not allow_silent:
        errors.append(f"preset '{preset_name}' expects an audio stream (pass --allow-silent to override)")

    if has_audio and not preset.get("forbid_audio"):
        if audio_codec and preset["allowed_audio_codecs"] and audio_codec not in preset["allowed_audio_codecs"]:
            errors.append(
                f"audio codec '{audio_codec}' not in {preset_name} allowed list {preset['allowed_audio_codecs']}"
            )
        if sample_rate and preset["allowed_sample_rates"] and sample_rate not in preset["allowed_sample_rates"]:
            errors.append(
                f"audio sample rate {sample_rate} Hz not in {preset_name} allowed list {preset['allowed_sample_rates']}"
            )

    if preset["require_faststart"] and faststart is False:
        errors.append("MP4 'moov' atom appears after 'mdat' (re-mux with -movflags +faststart)")

    return errors, warnings


def run_ffprobe(path: Path) -> dict[str, Any]:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("ffprobe not found on PATH")
    out = subprocess.check_output(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration,size,bit_rate,format_name:format_tags:stream=index,codec_type,codec_name,width,height,pix_fmt,avg_frame_rate,nb_frames,sample_rate,channels",
            "-of",
            "json",
            str(path),
        ],
        text=True,
    )
    return json.loads(out)


def parse_ebur128(stderr_text: str) -> dict[str, float | None]:
    integrated = None
    true_peak = None
    lra = None
    m_i = re.findall(r"^\s*I:\s*(-?\d+(?:\.\d+)?)\s*LUFS", stderr_text, re.MULTILINE)
    if m_i:
        integrated = float(m_i[-1])
    m_p = re.findall(r"^\s*Peak:\s*(-?\d+(?:\.\d+)?)\s*dBFS", stderr_text, re.MULTILINE)
    if m_p:
        true_peak = float(m_p[-1])
    m_l = re.findall(r"^\s*LRA:\s*(-?\d+(?:\.\d+)?)\s*LU", stderr_text, re.MULTILINE)
    if m_l:
        lra = float(m_l[-1])
    return {"integrated_lufs": integrated, "true_peak_dbfs": true_peak, "lra_lu": lra}


def measure_audio_ebur128(path: Path, filter_prefix: str = "") -> dict[str, float | None]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found on PATH")
    af = f"{filter_prefix},ebur128=peak=true" if filter_prefix else "ebur128=peak=true"
    proc = subprocess.run(
        [ffmpeg, "-nostdin", "-hide_banner", "-i", str(path), "-vn", "-af", af, "-f", "null", "-"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg ebur128 failed (exit {proc.returncode}): {proc.stderr.strip()[:300]}")
    return parse_ebur128(proc.stderr)


def check_opaque_mask(path: Path, box_spec: str, threshold: int = 16) -> dict[str, Any]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found on PATH")
    parts = box_spec.split(":")
    if len(parts) != 4:
        raise ValueError("--check-mask must use x:y:w:h format (for example 16:766:186:24)")
    x, y, w, h = (int(v) for v in parts)
    if w <= 0 or h <= 0 or x < 0 or y < 0:
        raise ValueError("--check-mask x,y must be >= 0 and w,h must be > 0")
    raw = subprocess.check_output(
        [
            ffmpeg,
            "-nostdin",
            "-v",
            "error",
            "-i",
            str(path),
            "-vf",
            f"crop={w}:{h}:{x}:{y},format=gray",
            "-pix_fmt",
            "gray",
            "-f",
            "rawvideo",
            "-",
        ]
    )
    frame_size = w * h
    if not raw or len(raw) % frame_size != 0:
        raise RuntimeError("Mask pixel stream did not align to whole frames")
    frames = len(raw) // frame_size
    max_luma = max(raw)
    return {
        "box": {"x": x, "y": y, "w": w, "h": h},
        "frames_checked": frames,
        "max_luma": max_luma,
        "threshold": threshold,
        "opaque": max_luma < threshold,
    }


def emit(payload: dict[str, Any], pretty: bool, code: int) -> int:
    print(json.dumps(payload, indent=2 if pretty else None))
    return code


def cmd_spec(args: argparse.Namespace) -> int:
    return emit(
        {
            "schema": SPEC_SCHEMA,
            "presets": PRESETS,
            "audio_standards": {
                "social_target_lufs": -15.0,
                "youtube_target_lufs": -14.0,
                "max_true_peak_dbtp": -1.0,
                "phone_mono_filter": "pan=mono|c0=0.5*c0+0.5*c1,highpass=f=200,lowpass=f=5000",
            },
        },
        args.pretty,
        0,
    )


def cmd_verify(args: argparse.Namespace) -> int:
    video_path = Path(args.video)
    if not video_path.is_file():
        return emit(
            {"schema": ERROR_SCHEMA, "ok": False, "error": f"File not found: {video_path}"},
            args.pretty,
            1,
        )

    errors: list[str] = []
    warnings: list[str] = []
    size_bytes = video_path.stat().st_size
    atom_info = inspect_mp4_atoms(video_path)

    probe: dict[str, Any] | None = None
    width: int | None = None
    height: int | None = None
    duration_s: float | None = None
    video_codec: str | None = None
    pix_fmt: str | None = None
    avg_frame_rate: str | None = None
    nb_frames: int | None = None
    has_audio = False
    audio_codec: str | None = None
    sample_rate: int | None = None
    channels: int | None = None
    format_tags: dict[str, Any] = {}

    if shutil.which("ffprobe"):
        try:
            probe = run_ffprobe(video_path)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"ffprobe failed: {exc}")
    else:
        if args.require_ffprobe:
            errors.append("ffprobe is required but not found on PATH")
        else:
            warnings.append("ffprobe not found on PATH; stream-level checks skipped")

    if probe is not None:
        fmt = probe.get("format", {})
        format_tags = fmt.get("tags") or {}
        if fmt.get("duration") is not None:
            try:
                duration_s = float(fmt["duration"])
            except (TypeError, ValueError):
                duration_s = None
        for stream in probe.get("streams", []):
            if stream.get("codec_type") == "video" and video_codec is None:
                video_codec = stream.get("codec_name")
                width = int(stream["width"]) if stream.get("width") is not None else None
                height = int(stream["height"]) if stream.get("height") is not None else None
                pix_fmt = stream.get("pix_fmt")
                avg_frame_rate = stream.get("avg_frame_rate")
                raw_frames = stream.get("nb_frames")
                if raw_frames is not None and str(raw_frames).isdigit():
                    nb_frames = int(raw_frames)
            elif stream.get("codec_type") == "audio" and not has_audio:
                has_audio = True
                audio_codec = stream.get("codec_name")
                raw_rate = stream.get("sample_rate")
                if raw_rate is not None and str(raw_rate).isdigit():
                    sample_rate = int(raw_rate)
                raw_channels = stream.get("channels")
                if raw_channels is not None and str(raw_channels).isdigit():
                    channels = int(raw_channels)

        if video_codec is None:
            errors.append("no video stream found")

        if args.strict_metadata:
            suspicious = {
                k: v
                for k, v in format_tags.items()
                if k.lower() in {"title", "comment", "artist", "album", "description", "location", "com.apple.quicktime.location.iso6709"}
            }
            if suspicious:
                errors.append(f"unexpected container metadata tags present (re-mux with -map_metadata -1): {sorted(suspicious)}")

    if args.require_faststart and atom_info["is_mp4"] and atom_info["faststart"] is False:
        errors.append("MP4 'moov' atom appears after 'mdat' (re-mux with -movflags +faststart)")

    if args.preset:
        p_errors, p_warnings = evaluate_preset_constraints(
            args.preset,
            width=width,
            height=height,
            duration_s=duration_s,
            size_bytes=size_bytes,
            video_codec=video_codec,
            pix_fmt=pix_fmt,
            has_audio=has_audio,
            audio_codec=audio_codec,
            sample_rate=sample_rate,
            faststart=atom_info["faststart"],
            allow_silent=args.allow_silent,
            max_bytes_override=args.max_bytes,
        )
        errors.extend(p_errors)
        warnings.extend(p_warnings)
    elif args.max_bytes is not None and size_bytes > args.max_bytes:
        errors.append(f"file size {size_bytes} bytes exceeds --max-bytes limit ({args.max_bytes} bytes)")

    loudness_result: dict[str, Any] | None = None
    mono_result: dict[str, Any] | None = None
    if (args.check_loudness or args.check_mono) and not has_audio:
        warnings.append("audio loudness/mono check skipped because no audio stream is present")
    if args.check_loudness and has_audio:
        try:
            loudness_result = measure_audio_ebur128(video_path)
            lufs = loudness_result["integrated_lufs"]
            peak = loudness_result["true_peak_dbfs"]
            lufs_range = PRESETS[args.preset]["lufs_range"] if args.preset else [-18.0, -12.0]
            max_peak = PRESETS[args.preset]["max_true_peak_dbtp"] if args.preset else -1.0
            if lufs is not None and lufs_range and not (lufs_range[0] <= lufs <= lufs_range[1]):
                errors.append(f"integrated loudness {lufs:.1f} LUFS outside target range [{lufs_range[0]}..{lufs_range[1]}]")
            if peak is not None and max_peak is not None and peak > max_peak:
                errors.append(f"true peak {peak:.2f} dBFS exceeds {max_peak:.1f} dBTP ceiling")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"loudness check failed: {exc}")

    if args.check_mono and has_audio:
        try:
            mono_result = measure_audio_ebur128(
                video_path,
                "pan=mono|c0=0.5*c0+0.5*c1,highpass=f=200,lowpass=f=5000",
            )
            if mono_result["integrated_lufs"] is not None and mono_result["integrated_lufs"] < -36.0:
                errors.append(
                    f"mono phone-speaker pass is nearly silent ({mono_result['integrated_lufs']:.1f} LUFS) — check stereo phase cancellation"
                )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"mono phone-speaker check failed: {exc}")

    mask_result: dict[str, Any] | None = None
    if args.check_mask:
        try:
            mask_result = check_opaque_mask(video_path, args.check_mask, threshold=args.mask_threshold)
            if not mask_result["opaque"]:
                errors.append(
                    f"privacy mask failed: max luma {mask_result['max_luma']} >= {mask_result['threshold']} across {mask_result['frames_checked']} frames"
                )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"privacy mask check failed: {exc}")

    cues_result: dict[str, Any] | None = None
    if args.check_cues:
        cues_path = Path(args.check_cues)
        if not cues_path.is_file():
            errors.append(f"cues file not found: {cues_path}")
        else:
            try:
                cues_data = json.loads(cues_path.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"failed to parse cues JSON: {exc}")
            else:
                c_errors, cues_result = validate_cues_data(cues_data, duration_s=duration_s)
                errors.extend(c_errors)

    payload = {
        "schema": VERIFY_SCHEMA,
        "ok": len(errors) == 0,
        "file": str(video_path),
        "preset": args.preset,
        "size_bytes": size_bytes,
        "container": atom_info,
        "video": {
            "codec": video_codec,
            "width": width,
            "height": height,
            "pix_fmt": pix_fmt,
            "avg_frame_rate": avg_frame_rate,
            "nb_frames": nb_frames,
            "duration_s": duration_s,
        },
        "audio": {
            "present": has_audio,
            "codec": audio_codec,
            "sample_rate": sample_rate,
            "channels": channels,
            "ebur128": loudness_result,
            "phone_mono": mono_result,
        },
        "privacy_mask": mask_result,
        "cues": cues_result,
        "warnings": warnings,
        "errors": errors,
    }
    return emit(payload, args.pretty, 0 if payload["ok"] else 1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="verify_video_export.py",
        description="Verify video exports against Smoky Video Studio platform, faststart, loudness, privacy-mask, and cue contracts.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_spec = sub.add_parser("spec", help="Print supported platform presets and audio loudness targets as JSON")
    p_spec.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    p_spec.set_defaults(func=cmd_spec)

    p_verify = sub.add_parser("verify", help="Verify a rendered video export")
    p_verify.add_argument("video", help="Path to rendered video file (MP4/MOV/WebM)")
    p_verify.add_argument("--preset", choices=sorted(PRESETS), help="Platform preset to enforce")
    p_verify.add_argument("--max-bytes", type=int, help="Override hard file size ceiling in bytes")
    p_verify.add_argument("--allow-silent", action="store_true", help="Allow silent video even on audio-default presets")
    p_verify.add_argument("--require-faststart", action="store_true", help="Fail if MP4 moov atom appears after mdat")
    p_verify.add_argument("--require-ffprobe", action="store_true", help="Fail if ffprobe is not installed")
    p_verify.add_argument("--strict-metadata", action="store_true", help="Fail if identifying container tags remain")
    p_verify.add_argument("--check-loudness", action="store_true", help="Measure post-encode EBU R128 loudness and true peak via ffmpeg")
    p_verify.add_argument("--check-mono", action="store_true", help="Check simulated mono phone-speaker folddown (200-5000 Hz) via ffmpeg")
    p_verify.add_argument("--check-mask", metavar="X:Y:W:H", help="Verify an opaque black privacy mask across all frames via ffmpeg")
    p_verify.add_argument("--mask-threshold", type=int, default=16, help="Max allowed grayscale luma inside --check-mask (default: 16)")
    p_verify.add_argument("--check-cues", metavar="PATH", help="Validate frame-timed cues.json against timeline invariants")
    p_verify.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    p_verify.set_defaults(func=cmd_verify)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
