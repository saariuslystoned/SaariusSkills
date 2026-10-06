import hashlib
import importlib.util
import json
import unittest
from unittest import mock
from pathlib import Path


MODULE = Path(__file__).resolve().parents[1] / "skills/grilltrack/scripts/grilltrack_retention.py"
SPEC = importlib.util.spec_from_file_location("grilltrack_retention", MODULE)
codec = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(codec)


class RetentionCodecTests(unittest.TestCase):
    def test_binary_and_text_roundtrip_with_exact_hashes(self):
        files = {
            "docs/readme.txt": "retention\n".encode(),
            "bin/data": b"\x00\xff\x80\x00",
        }
        root, objects = codec.pack(files)
        self.assertEqual(codec.unpack(root, objects), files)
        self.assertEqual(hashlib.sha256(files["bin/data"]).hexdigest(), next(
            key for key, value in objects.items() if value == files["bin/data"]
        ))

    def test_empty_tree_is_a_valid_deterministic_root(self):
        root, objects = codec.pack({})
        self.assertEqual(codec.unpack(root, objects), {})
        self.assertEqual(codec.pack({}), (root, objects))

    def test_unique_file_content_is_stored_once_and_repeated_subtree_is_reused(self):
        payload = b"same bytes in every copy"
        files = {
            "left/deep/payload": payload,
            "right/deep/payload": payload,
            "other": b"left-only",
        }
        root, objects = codec.pack(files)
        self.assertEqual(codec.unpack(root, objects), files)
        self.assertEqual(sum(value == payload for value in objects.values()), 1)
        root_node = json.loads(objects[root])
        self.assertEqual(
            root_node["entries"]["left"]["sha256"],
            root_node["entries"]["right"]["sha256"],
        )

    def test_unordered_input_is_deterministic(self):
        first = {"z/file": b"z", "a/file": b"a", "a/other": b"b"}
        second = dict(reversed(list(first.items())))
        self.assertEqual(codec.pack(first), codec.pack(second))

    def test_missing_and_corrupt_reachable_objects_fail_closed(self):
        root, objects = codec.pack({"a": b"a", "b": b"b"})
        root_node = json.loads(objects[root])
        missing = dict(objects)
        del missing[root_node["entries"]["a"]["sha256"]]
        with self.assertRaisesRegex(ValueError, "missing object"):
            codec.unpack(root, missing)
        corrupt = dict(objects)
        b_hash = root_node["entries"]["b"]["sha256"]
        corrupt[b_hash] = b"foreign"
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            codec.unpack(root, corrupt)

    def test_foreign_valid_object_cannot_bypass_root_binding(self):
        root, objects = codec.pack({"a": b"a", "b": b"b"})
        other_root, other_objects = codec.pack({"a": b"foreign", "b": b"b"})
        self.assertNotEqual(root, other_root)
        substituted = {**objects, **other_objects}
        self.assertEqual(
            codec.unpack(other_root, substituted), {"a": b"foreign", "b": b"b"}
        )
        self.assertEqual(codec.unpack(root, objects), {"a": b"a", "b": b"b"})

    def test_unsafe_paths_and_file_directory_collisions_are_rejected(self):
        for path in ("", "/absolute", "a//b", "a/./b", "a/../b", "a\\b", "a/\x00b",
                     "a/b?"):
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    codec.pack({path: b"x"})
        with self.assertRaisesRegex(ValueError, "collision"):
            codec.pack({"a": b"x", "a/b": b"y"})

    def test_duplicate_keys_and_malformed_descriptors_are_rejected(self):
        duplicate = b'{"entries":{},"entries":{},"schema":"grilltrack/retention-tree/v1"}'
        duplicate_hash = hashlib.sha256(duplicate).hexdigest()
        with self.assertRaisesRegex(ValueError, "duplicate"):
            codec.unpack(duplicate_hash, {duplicate_hash: duplicate})

        malformed = json.dumps(
            {"schema": "wrong", "entries": {}}, separators=(",", ":")
        ).encode()
        malformed_hash = hashlib.sha256(malformed).hexdigest()
        with self.assertRaisesRegex(ValueError, "schema"):
            codec.unpack(malformed_hash, {malformed_hash: malformed})

        unsafe = json.dumps(
            {
                "schema": "grilltrack/retention-tree/v1",
                "entries": {
                    "../escape": {"kind": "file", "sha256": "0" * 64}
                },
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        unsafe_hash = hashlib.sha256(unsafe).hexdigest()
        with self.assertRaisesRegex(ValueError, "unsafe"):
            codec.unpack(unsafe_hash, {unsafe_hash: unsafe})

    def test_depth_bound_and_bounded_object_growth(self):
        files = {"a/b/c/data": b"payload", "x/y/z/data": b"payload"}
        root, objects = codec.pack(files)
        self.assertEqual(codec.unpack(root, objects), files)
        self.assertLessEqual(len(objects), 8)

        path = '/'.join(['d'] * (codec.MAX_DIRECTORY_DEPTH + 1) + ['leaf'])
        with self.assertRaisesRegex(ValueError, 'depth'):
            codec.pack({path: b'x'})
        objects = {hashlib.sha256(b'x').hexdigest(): b'x'}
        child = {'kind': 'file', 'sha256': hashlib.sha256(b'x').hexdigest()}
        for _ in range(codec.MAX_DIRECTORY_DEPTH + 2):
            raw = json.dumps({'schema': codec.SCHEMA, 'entries': {'d': child}},
                             sort_keys=True, separators=(',', ':')).encode()
            key = hashlib.sha256(raw).hexdigest()
            objects[key] = raw
            child = {'kind': 'tree', 'sha256': key}
        with self.assertRaisesRegex(ValueError, 'depth'):
            codec.unpack(key, objects)

    def test_cached_subtree_cannot_bypass_depth_limit(self):
        # Visit the same subtree shallowly before referencing it too deeply.
        shallow, objects = codec.pack({'a/b/leaf': b'x'})
        deep = shallow
        for _ in range(codec.MAX_DIRECTORY_DEPTH):
            raw = json.dumps({'schema': codec.SCHEMA, 'entries': {
                'd': {'kind': 'tree', 'sha256': deep}}},
                sort_keys=True, separators=(',', ':')).encode()
            deep = hashlib.sha256(raw).hexdigest()
            objects[deep] = raw
        raw = json.dumps({'schema': codec.SCHEMA, 'entries': {
            'a': {'kind': 'tree', 'sha256': shallow},
            'z': {'kind': 'tree', 'sha256': deep}}},
            sort_keys=True, separators=(',', ':')).encode()
        root = hashlib.sha256(raw).hexdigest(); objects[root] = raw
        with self.assertRaisesRegex(ValueError, 'depth'):
            codec.unpack(root, objects)

    def test_shared_dag_expansion_is_rejected_before_materialization(self):
        leaf = b'x'
        leaf_hash = hashlib.sha256(leaf).hexdigest()
        objects = {leaf_hash: leaf}
        child = {'kind': 'file', 'sha256': leaf_hash}
        for _ in range(12):
            raw = json.dumps({'schema': codec.SCHEMA, 'entries': {
                'a': child, 'b': child}}, sort_keys=True, separators=(',', ':')).encode()
            root = hashlib.sha256(raw).hexdigest(); objects[root] = raw
            child = {'kind': 'tree', 'sha256': root}
        with mock.patch.object(codec, 'MAX_EXPANDED_FILES', 1024, create=True):
            with self.assertRaisesRegex(ValueError, 'expansion'):
                codec.unpack(root, objects)

    def test_expansion_budget_counts_repeated_bytes_and_full_paths(self):
        files = {'left/leaf': b'payload', 'right/leaf': b'payload'}
        root, objects = codec.pack(files)
        exact = sum(len(path.encode()) + len(raw) for path, raw in files.items())
        with mock.patch.object(codec, 'MAX_EXPANDED_BYTES', exact, create=True):
            self.assertEqual(codec.unpack(root, objects), files)
            self.assertEqual(codec.pack(files), (root, objects))
        with mock.patch.object(codec, 'MAX_EXPANDED_BYTES', exact - 1, create=True):
            with self.assertRaisesRegex(ValueError, 'expansion'):
                codec.unpack(root, objects)
            with self.assertRaisesRegex(ValueError, 'expansion'):
                codec.pack(files)

    def test_non_string_reference_kind_fails_with_value_error(self):
        raw = json.dumps({'schema': codec.SCHEMA, 'entries': {
            'x': {'kind': [], 'sha256': '0' * 64}}},
            sort_keys=True, separators=(',', ':')).encode()
        root = hashlib.sha256(raw).hexdigest()
        with self.assertRaises(ValueError):
            codec.unpack(root, {root: raw})



if __name__ == "__main__":
    unittest.main()
