from __future__ import annotations

import base64
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile


SOURCE = Path(__file__).resolve().parents[1] / "skills/dinkuskit-e2e-blackbox/scripts/cloudflare-probe/decode.py"
spec = importlib.util.spec_from_file_location("public_blackbox_artifacts", SOURCE)
decoder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(decoder)


def passing_records(trace_bytes=None):
    trace = io.BytesIO()
    with zipfile.ZipFile(trace, "w") as archive:
        archive.writestr("trace.trace", '{"type":"context-options"}\n')
    files = {
        "page.png": b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 200,
        "trace.zip": trace.getvalue() if trace_bytes is None else trace_bytes,
        "result.json": json.dumps({"runId": "run1", "status": "PASS"}).encode(),
    }
    records = []
    for name, data in files.items():
        digest = hashlib.sha256(data).hexdigest()
        records.append(dict(kind="begin", runId="run1", name=name, size=len(data),
                            sha256=digest, chunks=(len(data) + 32767) // 32768))
        for n, start in enumerate(range(0, len(data), 32768)):
            records.append(dict(kind="chunk", runId="run1", name=name, n=n,
                                data=base64.b64encode(data[start:start + 32768]).decode()))
        records.append(dict(kind="end", runId="run1", name=name, sha256=digest))
    records.append(dict(kind="complete", runId="run1", status="PASS"))
    return records, files


class PublicArtifactTransferTests(unittest.TestCase):
    def capture(self, root, records):
        source = root / "capture.txt"
        source.write_text("provider lifecycle message\n" + "".join(
            decoder.PREFIX + json.dumps(record) + "\n" for record in records))
        return source

    def test_multichunk_transfer_preserves_bytes_and_hashes(self):
        records, files = passing_records()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            receipt = decoder.decode(self.capture(root, records), root / "output", "run1")
            self.assertEqual(receipt["status"], "PASS")
            for name, data in files.items():
                self.assertEqual((root / "output" / name).read_bytes(), data)
                self.assertEqual(receipt["artifacts"][name]["sha256"], hashlib.sha256(data).hexdigest())

    def test_truncated_reordered_wrong_identity_and_hash_fail_without_output(self):
        for corruption in ("truncated", "reordered", "identity", "hash", "missing_file"):
            with self.subTest(corruption=corruption), tempfile.TemporaryDirectory() as temp:
                records, _ = passing_records()
                if corruption == "truncated": records.pop()
                if corruption == "reordered": records[1], records[2] = records[2], records[1]
                if corruption == "identity": records[0]["runId"] = "run2"
                if corruption == "hash": records[0]["sha256"] = "0" * 64
                if corruption == "missing_file": records = [r for r in records if r.get("name") != "page.png"]
                root = Path(temp)
                with self.assertRaises(ValueError):
                    decoder.decode(self.capture(root, records), root / "output", "run1")
                self.assertFalse((root / "output").exists())

    def test_unexpected_artifact_path_is_never_written(self):
        records, _ = passing_records()
        records[0]["name"] = "../outside.png"
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaises(ValueError):
                decoder.decode(self.capture(root, records), root / "output", "run1")
            self.assertFalse((root / "outside.png").exists())
            self.assertFalse((root / "output").exists())

    def test_oversized_record_is_rejected_before_json_decode(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "capture.txt"
            source.write_text(decoder.PREFIX + "x" * decoder.MAX_LINE)
            with self.assertRaisesRegex(ValueError, "line limit"):
                decoder.decode(source, root / "output", "run1")
            self.assertFalse((root / "output").exists())

    def test_existing_output_is_preserved(self):
        records, _ = passing_records()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "output"
            output.mkdir()
            (output / "keep.txt").write_text("prior evidence")
            with self.assertRaises(FileExistsError):
                decoder.decode(self.capture(root, records), output, "run1")
            self.assertEqual((output / "keep.txt").read_text(), "prior evidence")

    def test_trace_expansion_limits_rejected_before_decompression(self):
        cases = (
            ("entry", [2048], 1024, 4096, 8),
            ("total", [512, 512, 512], 1024, 1024, 8),
            ("count", [8, 8, 8], 1024, 4096, 2),
        )
        for reason, sizes, entry_cap, total_cap, count_cap in cases:
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as temp:
                trace = io.BytesIO()
                with zipfile.ZipFile(trace, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                    for index, size in enumerate(sizes):
                        archive.writestr(f"{index}.trace", b"x" * size)
                records, _ = passing_records(trace.getvalue())
                root = Path(temp)
                with mock.patch.object(decoder, "TRACE_ENTRY_CAP", entry_cap), \
                        mock.patch.object(decoder, "TRACE_TOTAL_CAP", total_cap), \
                        mock.patch.object(decoder, "TRACE_ENTRY_COUNT", count_cap), \
                        mock.patch.object(zipfile.ZipFile, "testzip") as decompress:
                    with self.assertRaisesRegex(ValueError, "expansion limits"):
                        decoder.decode(self.capture(root, records), root / "output", "run1")
                    decompress.assert_not_called()
                self.assertFalse((root / "output").exists())
