#!/usr/bin/env python3
"""Deterministic headless Chrome verification & 24fps loop recorder for emdash-motion-studio.

Verifies Mode A (3D Cutaway / Studio PBR), Mode B (Multiplane Occlusion + Pigment Drift),
and Mode C (Choreographed Timeline Stage) animations across:
  - Camera angles (?free=1&yaw=...) and See-through + Labels (?xr=1&labels=1)
  - Deterministic timeline scrubs (?t=0.0..1.0) and 3D Exploded Multiplane (?explode=1)
  - Button/action sequences (?press=...)
  - True mobile viewport (390x844) via Chrome DevTools Protocol Emulation.setDeviceMetricsOverride
    (defeating macOS Cocoa NSWindow's 500px headless window width clamp)
  - Optional 24fps end-to-end MP4 & palette-optimized GIF motion loop recording (--record-mp4, --record-gif)
  - DOM & SVG geometry health (<html data-errors>, NaN attributes, non-empty SVG primitives, viewport width)

Outputs retina PNG screenshots, optional MP4/GIF loops, proof-report.json, and PROOF.md in --out-dir.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
BUILD_PY = HERE / "build.py"

CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "google-chrome",
    "chromium",
    "chromium-browser",
)


def find_chrome(override: str | None = None) -> str:
    if override:
        if Path(override).is_file() or shutil.which(override):
            return override
        sys.exit(f"error: specified --chrome-bin not found: {override}")
    for c in CHROME_CANDIDATES:
        if Path(c).is_file():
            return c
        w = shutil.which(c)
        if w:
            return w
    sys.exit("error: Google Chrome / Chromium binary not found")


def parse_size(size_str: str) -> tuple[int, int]:
    parts = [p.strip() for p in size_str.split(",")]
    if len(parts) != 2:
        return 1100, 760
    return max(240, int(parts[0])), max(240, int(parts[1]))


def detect_mode(html_text: str) -> str:
    if "mountFigure(" in html_text:
        return "mode-a"
    if "mountMultiplane(" in html_text or "multiplane.js" in html_text:
        return "mode-b"
    if "mountChoreo(" in html_text or "choreo.js" in html_text:
        return "mode-c"
    if "mountDitherShader(" in html_text or "mountReceipt(" in html_text:
        return "mode-c"
    return "mode-a"


def extract_meta_probes(html_text: str) -> list[dict]:
    m = re.search(r'<meta\s+name=["\']motion-probes["\']\s+content=[\'"]([^\'"]+)[\'"]', html_text, re.I)
    if not m:
        return []
    out: list[dict] = []
    for item in m.group(1).split(";"):
        item = item.strip()
        if not item or ":" not in item:
            continue
        name, rest = item.split(":", 1)
        size = "960,820"
        if "@" in rest:
            rest, size = rest.rsplit("@", 1)
        out.append({
            "name": name.strip(),
            "query": rest.strip(),
            "size": size.strip(),
            "budget": 2200,
            "dump_dom": True,
        })
    return out


def default_probes(mode: str, full_angles: bool = False, press_seq: str | None = None) -> list[dict]:
    probes: list[dict] = []
    if mode == "mode-a":
        if full_angles:
            angles = [
                ("yaw_45", "free=1&yaw=45"),
                ("yaw_110", "free=1&yaw=110"),
                ("yaw_170", "free=1&yaw=170"),
                ("yaw_230", "free=1&yaw=230"),
                ("yaw_300", "free=1&yaw=300"),
                ("yaw_20_pitch_62", "free=1&yaw=20&pitch=62"),
                ("yaw_200_pitch_70", "free=1&yaw=200&pitch=70"),
            ]
        else:
            angles = [
                ("yaw_45_closed", "free=1&yaw=45"),
                ("yaw_225_back", "free=1&yaw=225"),
            ]
        for name, q in angles:
            probes.append({"name": name, "query": q, "size": "900,800", "budget": 1800, "dump_dom": False})
        probes.append(
            {
                "name": "cutaway_xr_labels",
                "query": "free=1&yaw=45&xr=1&labels=1",
                "size": "900,800",
                "budget": 2000,
                "dump_dom": True,
            }
        )
        probes.append(
            {
                "name": "scrub_t050_xr",
                "query": "free=1&yaw=45&xr=1&labels=1&t=0.5",
                "size": "900,800",
                "budget": 2000,
                "dump_dom": True,
            }
        )
        probes.append(
            {
                "name": "mobile_390x844",
                "query": "free=1&yaw=45&xr=1&labels=1&t=0.5",
                "size": "390,844",
                "budget": 2000,
                "dump_dom": True,
            }
        )
    elif mode == "mode-b":
        for label, t_val in (("scrub_t012", "0.12"), ("scrub_t045", "0.45"), ("scrub_t088", "0.88")):
            probes.append(
                {
                    "name": label,
                    "query": f"t={t_val}",
                    "size": "1100,760",
                    "budget": 1800,
                    "dump_dom": label == "scrub_t045",
                }
            )
        probes.append(
            {
                "name": "exploded_multiplane",
                "query": "t=0.45&explode=1",
                "size": "1100,760",
                "budget": 1800,
                "dump_dom": True,
            }
        )
        probes.append(
            {
                "name": "mobile_390x844",
                "query": "t=0.45",
                "size": "390,844",
                "budget": 1800,
                "dump_dom": True,
            }
        )
    else:  # mode-c
        for label, t_val in (("cue1_t012", "0.12"), ("cue2_t040", "0.40"), ("cue3_t068", "0.68"), ("cue4_t092", "0.92")):
            probes.append(
                {
                    "name": label,
                    "query": f"t={t_val}",
                    "size": "1100,760",
                    "budget": 1800,
                    "dump_dom": label == "cue3_t068",
                }
            )
        probes.append(
            {
                "name": "mobile_390x844",
                "query": "t=0.68",
                "size": "390,844",
                "budget": 1800,
                "dump_dom": True,
            }
        )

    if press_seq:
        probes.append(
            {
                "name": "press_sequence",
                "query": f"free=1&xr=1&labels=1&press={press_seq}",
                "size": "900,800",
                "budget": 3200,
                "dump_dom": True,
            }
        )
    return probes


def audit_dom(dom_html: str, expected_width: int | None = None, inner_width: int | None = None, scroll_width: int | None = None) -> dict:
    errors_match = re.search(r'<html[^>]*\bdata-errors="([^"]*)"', dom_html, re.IGNORECASE)
    data_errors = errors_match.group(1).strip() if errors_match else ""

    svg_blocks = re.findall(r"<svg\b.*?</svg>", dom_html, flags=re.DOTALL | re.IGNORECASE)
    svg_joined = "\n".join(svg_blocks)
    nan_hits = re.findall(r'(?:d|transform|x|y|x1|y1|x2|y2|cx|cy|r|rx|ry|width|height|viewBox)="[^"]*\bNaN\b[^"]*"', svg_joined)

    primitive_count = len(re.findall(r"<(?:path|rect|circle|ellipse|line|polygon|polyline|text)\b", svg_joined, re.IGNORECASE))
    has_fig = bool(re.search(r'<svg[^>]*\bid="fig"', dom_html, re.IGNORECASE))

    width_ok = True
    if expected_width is not None and inner_width is not None:
        width_ok = abs(inner_width - expected_width) <= 2
    overflow_x = False
    if inner_width is not None and scroll_width is not None:
        overflow_x = scroll_width > inner_width + 2

    passed = (not data_errors) and (len(nan_hits) == 0) and has_fig and (primitive_count > 5) and width_ok and (not overflow_x)
    return {
        "passed": passed,
        "data_errors": data_errors,
        "nan_attribute_hits": nan_hits[:10],
        "svg_primitive_count": primitive_count,
        "has_fig_svg": has_fig,
        "inner_width": inner_width,
        "scroll_width": scroll_width,
        "width_ok": width_ok,
        "overflow_x": overflow_x,
    }


class _CdpSession:
    """Minimal zero-dependency Chrome DevTools Protocol client over 127.0.0.1 WebSocket."""

    def __init__(self, chrome_bin: str) -> None:
        self._prof_dir = tempfile.TemporaryDirectory(prefix="emdash-motion-cdp-")
        self._proc = subprocess.Popen(
            [
                chrome_bin,
                "--headless=new",
                "--remote-debugging-port=0",
                "--remote-allow-origins=*",
                "--hide-scrollbars",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-background-networking",
                "--disable-gpu-sandbox",
                "--allow-file-access-from-files",
                f"--user-data-dir={self._prof_dir.name}",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        self._ws_leftover = b""
        self._sock: socket.socket | None = None
        try:
            ws_browser_url = self._read_ws_url()
            parsed = urlparse(ws_browser_url)
            port = parsed.port
            if not port:
                raise RuntimeError("CDP port missing from DevTools stderr")

            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            page_ws_url = None
            deadline = time.monotonic() + 10.0
            while time.monotonic() < deadline:
                with opener.open(f"http://127.0.0.1:{port}/json/list", timeout=3) as resp:
                    targets = json.loads(resp.read().decode("utf-8"))
                for t in targets:
                    if t.get("type") == "page" and t.get("webSocketDebuggerUrl"):
                        page_ws_url = t["webSocketDebuggerUrl"]
                        break
                if page_ws_url:
                    break
                time.sleep(0.05)
            if not page_ws_url:
                raise RuntimeError("No page target exposed on CDP /json/list")

            self._sock, self._ws_leftover = self._connect_ws(page_ws_url)
            self._msg_id = 0
            self.call("Page.enable")
            self.call("Runtime.enable")
        except Exception:
            self.close()
            raise

    def _read_ws_url(self) -> str:
        assert self._proc.stderr is not None
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            line = self._proc.stderr.readline()
            if not line:
                if self._proc.poll() is not None:
                    break
                time.sleep(0.02)
                continue
            m = re.search(r"DevTools listening on (ws://127\.0\.0\.1:\d+/\S+)", line)
            if m:
                return m.group(1)
        raise RuntimeError("Timed out waiting for Headless Chrome DevTools WebSocket")

    @staticmethod
    def _connect_ws(ws_url: str) -> tuple[socket.socket, bytes]:
        parsed = urlparse(ws_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 80
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        sock = socket.create_connection((host, port), timeout=30)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        req = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        sock.sendall(req.encode("ascii"))
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = sock.recv(4096)
            if not chunk:
                raise RuntimeError("EOF during WebSocket handshake")
            buf += chunk
        header, rest = buf.split(b"\r\n\r\n", 1)
        if b" 101 " not in header.splitlines()[0]:
            raise RuntimeError(f"WebSocket upgrade failed: {header.splitlines()[0]!r}")
        expected_accept = base64.b64encode(
            hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()
        )
        if expected_accept not in header:
            raise RuntimeError("WebSocket Sec-WebSocket-Accept mismatch")
        return sock, rest

    def _recv_exact(self, n: int) -> bytes:
        assert self._sock is not None
        buf = self._ws_leftover
        self._ws_leftover = b""
        while len(buf) < n:
            chunk = self._sock.recv(max(65536, n - len(buf)))
            if not chunk:
                raise RuntimeError("Unexpected EOF on CDP WebSocket")
            buf += chunk
        self._ws_leftover = buf[n:]
        return buf[:n]

    def _send_frame(self, payload: bytes, opcode: int = 0x1) -> None:
        assert self._sock is not None
        mask_key = os.urandom(4)
        length = len(payload)
        header = bytearray([0x80 | opcode])
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", length))
        header.extend(mask_key)
        masked = bytes(b ^ mask_key[i & 3] for i, b in enumerate(payload))
        self._sock.sendall(bytes(header) + masked)

    def _recv_message(self) -> str:
        chunks: list[bytes] = []
        while True:
            b0, b1 = self._recv_exact(2)
            fin = bool(b0 & 0x80)
            opcode = b0 & 0x0F
            masked = bool(b1 & 0x80)
            length = b1 & 0x7F
            if length == 126:
                (length,) = struct.unpack("!H", self._recv_exact(2))
            elif length == 127:
                (length,) = struct.unpack("!Q", self._recv_exact(8))
            mask_key = self._recv_exact(4) if masked else b""
            data = self._recv_exact(length)
            if masked:
                data = bytes(b ^ mask_key[i & 3] for i, b in enumerate(data))
            if opcode == 0x9:  # ping
                self._send_frame(data, opcode=0xA)
                continue
            if opcode == 0x8:  # close
                raise RuntimeError("CDP WebSocket closed by Chrome")
            if opcode in (0x1, 0x2, 0x0):
                chunks.append(data)
                if fin:
                    return b"".join(chunks).decode("utf-8")

    def call(self, method: str, params: dict | None = None) -> dict:
        self._msg_id += 1
        req_id = self._msg_id
        msg = json.dumps({"id": req_id, "method": method, "params": params or {}}).encode("utf-8")
        self._send_frame(msg)
        while True:
            raw = self._recv_message()
            obj = json.loads(raw)
            if obj.get("id") == req_id:
                if "error" in obj:
                    raise RuntimeError(f"CDP error in {method}: {obj['error']}")
                return obj.get("result", {})

    def set_viewport(self, width: int, height: int, scale: int = 2) -> None:
        self.call(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": width,
                "height": height,
                "deviceScaleFactor": scale,
                "mobile": width <= 560,
            },
        )

    def navigate_and_settle(self, url: str, settle_sec: float = 0.22) -> None:
        self.call("Page.navigate", {"url": url})
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            res = self.call(
                "Runtime.evaluate",
                {"expression": "document.readyState", "returnByValue": True},
            )
            if res.get("result", {}).get("value") == "complete":
                break
            time.sleep(0.03)
        self.call(
            "Runtime.evaluate",
            {
                "expression": "new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))",
                "awaitPromise": True,
                "returnByValue": True,
            },
        )
        if settle_sec > 0:
            time.sleep(settle_sec)
            self.call(
                "Runtime.evaluate",
                {
                    "expression": "new Promise(r => requestAnimationFrame(r))",
                    "awaitPromise": True,
                    "returnByValue": True,
                },
            )

    def inspect_page(self, include_html: bool = True) -> dict:
        expr = (
            "JSON.stringify({"
            "innerWidth: window.innerWidth,"
            "innerHeight: window.innerHeight,"
            "scrollWidth: document.documentElement.scrollWidth,"
            f"html: {'document.documentElement.outerHTML' if include_html else '\"\"'}"
            "})"
        )
        res = self.call("Runtime.evaluate", {"expression": expr, "returnByValue": True})
        val = res.get("result", {}).get("value", "{}")
        return json.loads(val)

    def capture_png(self, out_png: Path) -> None:
        shot = self.call(
            "Page.captureScreenshot",
            {"format": "png", "captureBeyondViewport": False},
        )
        out_png.write_bytes(base64.b64decode(shot["data"]))

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        try:
            self._proc.terminate()
            self._proc.wait(timeout=5)
        except Exception:
            try:
                self._proc.kill()
                self._proc.wait(timeout=2)
            except Exception:
                pass
        shutil.rmtree(self._prof_dir.name, ignore_errors=True)
        try:
            self._prof_dir.cleanup()
        except Exception:
            pass


def _max_press_delay_sec(query: str) -> float:
    if "press=" not in query:
        return 0.18
    max_ms = 250
    for part in query.split("&"):
        if part.startswith("press="):
            for item in part[len("press=") :].split(","):
                if "@" in item:
                    try:
                        max_ms = max(max_ms, int(item.rsplit("@", 1)[1]))
                    except ValueError:
                        pass
    return min(4.0, (max_ms + 450) / 1000.0)


def run_cdp_probe(cdp: _CdpSession, url: str, out_png: Path, size: str, dump_dom: bool) -> dict:
    w, h = parse_size(size)
    cdp.set_viewport(w, h, scale=2)
    cdp.navigate_and_settle(url, settle_sec=_max_press_delay_sec(url))
    cdp.capture_png(out_png)
    shot_ok = out_png.is_file() and out_png.stat().st_size > 1000

    need_dom = dump_dom or (w <= 560)
    info = cdp.inspect_page(include_html=need_dom)
    dom_audit = None
    if need_dom:
        dom_audit = audit_dom(
            info.get("html", ""),
            expected_width=w,
            inner_width=info.get("innerWidth"),
            scroll_width=info.get("scrollWidth"),
        )
    passed = shot_ok and (dom_audit["passed"] if dom_audit else True)
    return {
        "screenshot": str(out_png),
        "screenshot_bytes": out_png.stat().st_size if out_png.is_file() else 0,
        "screenshot_ok": shot_ok,
        "inner_width": info.get("innerWidth"),
        "scroll_width": info.get("scrollWidth"),
        "dom_audit": dom_audit,
        "passed": passed,
    }


def run_cli_fallback_probe(chrome_bin: str, url: str, out_png: Path, size: str, budget: int, dump_dom: bool) -> dict:
    with tempfile.TemporaryDirectory(prefix="emdash-motion-chrome-") as prof_dir:
        cmd_shot = [
            chrome_bin,
            "--headless=new",
            "--hide-scrollbars",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-gpu-sandbox",
            f"--user-data-dir={prof_dir}",
            "--force-device-scale-factor=2",
            f"--window-size={size}",
            f"--virtual-time-budget={budget}",
            f"--screenshot={out_png}",
            url,
        ]
        res_shot = subprocess.run(cmd_shot, capture_output=True, text=True, timeout=45)
        shot_ok = res_shot.returncode == 0 and out_png.is_file() and out_png.stat().st_size > 1000

    dom_audit = None
    if dump_dom:
        with tempfile.TemporaryDirectory(prefix="emdash-motion-dom-") as prof_dir2:
            cmd_dom = [
                chrome_bin,
                "--headless=new",
                "--hide-scrollbars",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-gpu-sandbox",
                f"--user-data-dir={prof_dir2}",
                f"--window-size={size}",
                f"--virtual-time-budget={budget}",
                "--dump-dom",
                url,
            ]
            res_dom = subprocess.run(cmd_dom, capture_output=True, text=True, timeout=45)
            dom_audit = audit_dom(res_dom.stdout)

    passed = shot_ok and (dom_audit["passed"] if dom_audit else True)
    return {
        "screenshot": str(out_png),
        "screenshot_bytes": out_png.stat().st_size if out_png.is_file() else 0,
        "screenshot_ok": shot_ok,
        "dom_audit": dom_audit,
        "passed": passed,
    }


def record_motion_loop(
    cdp: _CdpSession,
    built_html: Path,
    target_dir: Path,
    size: str,
    fps: int,
    frames: int,
    want_mp4: bool,
    want_gif: bool,
    explode: bool = False,
) -> dict:
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        sys.exit("error: --record-mp4 / --record-gif requires ffmpeg in PATH")

    w, h = parse_size(size)
    suffix = "-exploded" if explode else ""
    extra_q = "&explode=1" if explode else ""
    cdp.set_viewport(w, h, scale=2)
    base_url = f"file://{built_html.resolve()}?t=0{extra_q}"
    cdp.navigate_and_settle(base_url, settle_sec=0.18)

    has_setter_res = cdp.call(
        "Runtime.evaluate",
        {"expression": "typeof window.__setMotionTime === 'function'", "returnByValue": True},
    )
    has_setter = bool(has_setter_res.get("result", {}).get("value"))

    with tempfile.TemporaryDirectory(prefix="emdash-motion-frames-") as fdir:
        fdir_path = Path(fdir)
        for i in range(frames):
            t_val = i / frames
            if has_setter:
                cdp.call(
                    "Runtime.evaluate",
                    {
                        "expression": f"window.__setMotionTime({t_val:.6f}); new Promise(r => requestAnimationFrame(r))",
                        "awaitPromise": True,
                        "returnByValue": True,
                    },
                )
            else:
                cdp.navigate_and_settle(f"file://{built_html.resolve()}?t={t_val:.6f}{extra_q}", settle_sec=0.04)
            cdp.capture_png(fdir_path / f"frame_{i:04d}.png")

        out_info: dict = {"fps": fps, "frames": frames, "size": size, "explode": explode}
        pattern = str(fdir_path / "frame_%04d.png")

        if want_mp4:
            mp4_path = target_dir / f"loop-{fps}fps{suffix}.mp4"
            subprocess.run(
                [
                    ffmpeg_bin,
                    "-y",
                    "-framerate",
                    str(fps),
                    "-i",
                    pattern,
                    "-vf",
                    "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-movflags",
                    "+faststart",
                    str(mp4_path),
                ],
                check=True,
                capture_output=True,
            )
            out_info["mp4"] = str(mp4_path)
            out_info["mp4_bytes"] = mp4_path.stat().st_size

        if want_gif:
            gif_path = target_dir / f"loop-{fps}fps{suffix}.gif"
            subprocess.run(
                [
                    ffmpeg_bin,
                    "-y",
                    "-framerate",
                    str(fps),
                    "-i",
                    pattern,
                    "-vf",
                    f"fps={fps},scale=min(960\\,iw):-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=192[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3",
                    str(gif_path),
                ],
                check=True,
                capture_output=True,
            )
            out_info["gif"] = str(gif_path)
            out_info["gif_bytes"] = gif_path.stat().st_size

        return out_info


def verify_target(
    src_file: Path,
    out_dir: Path,
    chrome_bin: str,
    mode_override: str | None,
    full_angles: bool,
    press_seq: str | None,
    record_mp4: bool = False,
    record_gif: bool = False,
    record_explode: bool = False,
    fps: int = 24,
    frames: int = 48,
    record_size: str = "1100,720",
) -> dict:
    raw = src_file.read_text(encoding="utf-8")
    mode = mode_override or detect_mode(raw)
    stem = src_file.stem
    target_dir = out_dir / stem
    target_dir.mkdir(parents=True, exist_ok=True)

    built_html = target_dir / f"{stem}.built.html"
    if re.search(
        r'<script\s+src=["\'][^"\']*(?:core|multiplane|choreo|tactile-audio|ephemera|dither|viewport-pool|surface-micro|three\.min)\.js["\']',
        raw,
        re.I,
    ):
        subprocess.run([sys.executable, str(BUILD_PY), str(src_file), str(built_html)], check=True)
    else:
        shutil.copyfile(src_file, built_html)

    built_text = built_html.read_text(encoding="utf-8")
    three_vendor = (HERE.parent / "assets" / "vendor" / "three.min.js").resolve()
    if re.search(r'<script\s+src=["\'][^"\']*three\.min\.js["\']', built_text, re.I) and three_vendor.is_file():
        patched = re.sub(
            r'<script\s+src=["\'][^"\']*three\.min\.js["\']\s*>\s*</script>',
            f'<script src="file://{three_vendor}"></script>',
            built_text,
            count=1,
        )
        built_html.write_text(patched, encoding="utf-8")

    meta_probes = extract_meta_probes(raw)
    if meta_probes:
        probes = meta_probes
        if press_seq:
            probes.append({
                "name": "press_sequence",
                "query": f"free=1&xr=1&labels=1&press={press_seq}",
                "size": "960,820",
                "budget": 3200,
                "dump_dom": True,
            })
    else:
        probes = default_probes(mode, full_angles=full_angles, press_seq=press_seq)

    results = []
    recordings: list[dict] = []
    all_passed = True

    cdp: _CdpSession | None = None
    try:
        try:
            cdp = _CdpSession(chrome_bin)
        except Exception as exc:
            if sys.platform == "darwin" and any(parse_size(p["size"])[0] < 500 for p in probes):
                raise RuntimeError(
                    f"CDP required on macOS for sub-500px mobile viewports (NSWindow clamps --window-size): {exc}"
                ) from exc
            cdp = None

        for p in probes:
            png_path = target_dir / f"shot-{p['name']}.png"
            url = f"file://{built_html.resolve()}?{p['query']}"
            if cdp is not None:
                res = run_cdp_probe(cdp, url, png_path, p["size"], p["dump_dom"])
            else:
                res = run_cli_fallback_probe(chrome_bin, url, png_path, p["size"], p["budget"], p["dump_dom"])
            res["name"] = p["name"]
            res["query"] = p["query"]
            res["size"] = p["size"]
            results.append(res)
            if not res["passed"]:
                all_passed = False

        if (record_mp4 or record_gif) and cdp is not None:
            recordings.append(
                record_motion_loop(
                    cdp,
                    built_html,
                    target_dir,
                    size=record_size,
                    fps=fps,
                    frames=frames,
                    want_mp4=record_mp4,
                    want_gif=record_gif,
                    explode=False,
                )
            )
            if record_explode:
                recordings.append(
                    record_motion_loop(
                        cdp,
                        built_html,
                        target_dir,
                        size=record_size,
                        fps=fps,
                        frames=frames,
                        want_mp4=record_mp4,
                        want_gif=record_gif,
                        explode=True,
                    )
                )
    finally:
        if cdp is not None:
            cdp.close()

    return {
        "source": str(src_file),
        "built_html": str(built_html),
        "mode": mode,
        "passed": all_passed,
        "probes": results,
        "recordings": recordings,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify emdash-motion-studio animations in headless Chrome.")
    parser.add_argument("inputs", nargs="+", help="One or more .html animation files to verify")
    parser.add_argument("--out-dir", default=".grilltrack/proof/motion", help="Directory for screenshots and proof report")
    parser.add_argument("--mode", choices=("mode-a", "mode-b", "mode-c"), default=None, help="Override auto-detected mode")
    parser.add_argument("--full-angles", action="store_true", help="Run all 7 Colorfigures camera angles for Mode A")
    parser.add_argument("--press", default=None, help="Optional ?press= button sequence (e.g. 'Push the lever@200')")
    parser.add_argument("--record-mp4", action="store_true", help="Record a 24fps H.264 MP4 loop via CDP + ffmpeg")
    parser.add_argument("--record-gif", action="store_true", help="Record a 24fps palette-optimized GIF loop via CDP + ffmpeg")
    parser.add_argument("--record-explode", action="store_true", help="Also record an ?explode=1 3D multiplane loop")
    parser.add_argument("--fps", type=int, default=24, help="Frame rate for MP4/GIF loop capture (default: 24)")
    parser.add_argument("--frames", type=int, default=48, help="Total frames across t=0..1 loop (default: 48)")
    parser.add_argument("--record-size", default="1100,720", help="Viewport width,height for loop recording (default: 1100,720)")
    parser.add_argument("--chrome-bin", default=None, help="Path to Chrome/Chromium binary")
    args = parser.parse_args()

    chrome_bin = find_chrome(args.chrome_bin)
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    reports = []
    overall_passed = True
    for inp in args.inputs:
        src_path = Path(inp).resolve()
        if not src_path.is_file():
            sys.exit(f"error: input file not found: {src_path}")
        rep = verify_target(
            src_path,
            out_dir,
            chrome_bin,
            args.mode,
            args.full_angles,
            args.press,
            record_mp4=args.record_mp4,
            record_gif=args.record_gif,
            record_explode=args.record_explode,
            fps=max(8, args.fps),
            frames=max(8, args.frames),
            record_size=args.record_size,
        )
        reports.append(rep)
        if not rep["passed"]:
            overall_passed = False

    summary = {
        "overall_passed": overall_passed,
        "chrome_bin": chrome_bin,
        "targets": reports,
    }
    json_path = out_dir / "proof-report.json"
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    md_lines = [
        "# EmDash Motion Studio — Headless Chrome Verification Proof",
        "",
        f"- **Overall Result:** `{'PASS' if overall_passed else 'FAIL'}`",
        f"- **Targets Verified:** {len(reports)}",
        "",
    ]
    for r in reports:
        md_lines.append(f"## `{Path(r['source']).name}` (`{r['mode']}`) — `{'PASS' if r['passed'] else 'FAIL'}`")
        md_lines.append("")
        md_lines.append("| Probe | Query | Viewport | Screenshot | DOM & Viewport Audit |")
        md_lines.append("| --- | --- | --- | --- | --- |")
        for p in r["probes"]:
            dom_info = "—"
            if p["dom_audit"]:
                da = p["dom_audit"]
                iw = da.get("inner_width")
                sw = da.get("scroll_width")
                vp_note = f", iw={iw}, sw={sw}" if iw is not None else ""
                dom_info = f"errors=`{da['data_errors'] or 'none'}`, NaN={len(da['nan_attribute_hits'])}, svg_nodes={da['svg_primitive_count']}{vp_note}"
            shot_rel = Path(p["screenshot"]).relative_to(out_dir)
            md_lines.append(
                f"| `{p['name']}` | `?{p['query']}` | `{p['size']}` | `{shot_rel}` ({p['screenshot_bytes']} B) | {dom_info} |"
            )
        if r.get("recordings"):
            md_lines.append("")
            md_lines.append("### Motion Loop Recordings")
            for rec in r["recordings"]:
                tag = "exploded (`?explode=1`)" if rec.get("explode") else "composited"
                parts = []
                if "mp4" in rec:
                    parts.append(f"`{Path(rec['mp4']).relative_to(out_dir)}` ({rec['mp4_bytes']} B)")
                if "gif" in rec:
                    parts.append(f"`{Path(rec['gif']).relative_to(out_dir)}` ({rec['gif_bytes']} B)")
                md_lines.append(f"- **{rec['fps']} fps {tag} ({rec['frames']} frames):** " + ", ".join(parts))
        md_lines.append("")

    md_path = out_dir / "PROOF.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    print(json.dumps({"overall_passed": overall_passed, "report": str(json_path), "proof_md": str(md_path)}))
    if not overall_passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
