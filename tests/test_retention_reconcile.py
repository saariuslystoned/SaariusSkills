"""Single-storage reconciliation, using fresh neutral fork histories only."""
import json
import hashlib
import unittest
import subprocess
from types import SimpleNamespace
from tests import test_reconcile as fixture


class RetentionReconcileTests(unittest.TestCase):
    def setUp(self):
        self.f = fixture.ReconcileTests()
        self.f.setUp()

    def tearDown(self):
        self.f.tearDown()

    def test_git_batch_reader_accepts_sha256_blob_identities(self):
        _, reconcile = fixture.retention_modules()
        project = self.f.root / 'sha256-object-fixture'; project.mkdir()
        subprocess.run(['git', 'init', '--object-format=sha256', '-q', str(project)], check=True)
        raw = b'neutral SHA-256 blob\n'
        oid = subprocess.check_output(['git', '-C', str(project), 'hash-object', '-w', '--stdin'], input=raw).decode().strip()
        self.assertEqual(len(oid), 64)
        self.assertEqual(reconcile.read_blobs(project, {'ledger.json': oid}), {'ledger.json': raw})

    def test_default_plan_binds_single_storage_format(self):
        before = self.f.state_bytes()
        plan = self.f.plan()
        self.assertEqual(plan['schema'], 'grilltrack/reconcile/v2')
        self.assertEqual(plan['retention']['schema'], 'grilltrack/retained/v2')
        self.assertEqual(before, self.f.state_bytes())

    def test_apply_stores_objects_and_references_without_snapshot_copies(self):
        plan = self.f.plan()
        result = self.f.reconcile('--apply', plan['plan_id'])
        self.assertEqual(result.returncode, 0, result.stderr)
        root = self.f.project / '.grilltrack/lineage'
        retained = root / plan['plan_id']
        self.assertTrue((retained / 'retention.json').is_file())
        self.assertFalse((retained / 'snapshots').exists())
        self.assertTrue((root / 'objects/sha256').is_dir())
        retry = self.f.reconcile('--apply', plan['plan_id'])
        self.assertEqual(retry.returncode, 0, retry.stderr)
        self.assertTrue(json.loads(retry.stdout)['already_applied'])

    def arguments(self):
        f = self.f
        return SimpleNamespace(base_ref=f.base, current_ref=f.current, incoming_ref=f.incoming,
                               title='Composed fixture', adjudication_file=None)

    def legacy_fixture(self):
        """Construct an applied v1 fixture with original raw artifact bytes."""
        _, reconcile = fixture.retention_modules()
        import grilltrack_ledger as api
        f = self.f
        plan, sources, decisions, prior = reconcile.build_plan(api.Store(str(f.project)), self.arguments(), api, schema=reconcile.V1)
        files = reconcile.expected_retention(plan, sources, decisions, prior, api)
        root = f.project / '.grilltrack/lineage' / plan['plan_id']
        for name, data in files.items():
            path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
        for name, data in reconcile.projected_files(plan, sources, decisions, api).items():
            (f.project / '.grilltrack' / name).write_bytes(data)
        return plan, files

    def fork_round(self, number):
        f = self.f
        f.base = f.commit('retained join ' + str(number))
        state = f.project / '.grilltrack'
        for role in ('current', 'incoming'):
            f.git('checkout', '--detach', f.base)
            live = json.loads((state / 'ledger.json').read_text())
            live['decisions'].append(fixture.decision(f'round-{number}-{role}'))
            stream = (state / 'events.jsonl').read_bytes() + fixture.events(1000 + 2 * number + (role == 'incoming'), 1)
            f.write_state(state, live, stream)
            setattr(f, role, f.commit(f'neutral {role} round {number}'))
        f.git('checkout', '--detach', f.current)

    def test_v1_readability_completed_retry_and_additive_v2_composition(self):
        f = self.f
        old, old_bytes = self.legacy_fixture()
        self.assertEqual(f.cli('focus', '--domain', 'later', '--cadence', 'sequential').returncode, 0)
        progressed = f.state_bytes()
        retry = f.reconcile('--apply', old['plan_id'])
        self.assertEqual(retry.returncode, 0, retry.stderr)
        self.assertEqual(f.state_bytes(), progressed)
        self.assertTrue(json.loads(retry.stdout)['already_applied'])
        self.fork_round(1)
        new = f.plan()
        self.assertEqual(new['schema'], 'grilltrack/reconcile/v2')
        result = f.reconcile('--apply', new['plan_id'])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(fixture.retained(f.project, old['plan_id']), old_bytes)
        for name, raw in old_bytes.items():
            self.assertEqual((f.project / '.grilltrack/lineage' / old['plan_id'] / name).read_bytes(), raw)
        # A committed mixed-format source must itself remain valid on a later join.
        self.fork_round(2)
        self.assertEqual(f.plan()['schema'], 'grilltrack/reconcile/v2')

    def test_malformed_legacy_plan_fails_cleanly_without_canonical_writes(self):
        f = self.f
        old, _ = self.legacy_fixture()
        path = f.project / '.grilltrack/lineage' / old['plan_id'] / 'plan.json'
        path.write_bytes(b'[]')
        canonical = {n: (f.project / '.grilltrack' / n).read_bytes()
                     for n in ('ledger.json', 'events.jsonl')}
        r = f.reconcile('--apply', old['plan_id'])
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertNotIn('Traceback', r.stderr)
        for name, raw in canonical.items():
            self.assertEqual((f.project / '.grilltrack' / name).read_bytes(), raw)

    def test_unapplied_v1_digest_cannot_authorize_v2_storage(self):
        _, reconcile = fixture.retention_modules()
        import grilltrack_ledger as api
        old, _, _, _ = reconcile.build_plan(api.Store(str(self.f.project)), self.arguments(), api, schema=reconcile.V1)
        before = self.f.state_bytes()
        r = self.f.reconcile('--apply', old['plan_id'])
        self.assertEqual(r.returncode, 2)
        self.assertIn('approved plan digest', r.stderr)
        self.assertEqual(before, self.f.state_bytes())

    def test_interrupted_v1_journal_recovers_original_format_losslessly(self):
        f = self.f
        _, reconcile = fixture.retention_modules()
        old, old_bytes = self.legacy_fixture()
        state = f.project / '.grilltrack'
        (state / 'lineage' / old['plan_id'] / 'applied.json').unlink()
        # Simulate the documented old-ledger/new-events publication boundary.
        (state / 'ledger.json').write_bytes(reconcile.paths(f.current, f.project)['ledger.json'])
        (state / 'work/reconcile-transaction.json').write_text(json.dumps({'plan_id': old['plan_id']}))
        self.assertEqual(f.cli('show').returncode, 2)
        r = f.reconcile('--apply', old['plan_id'])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)['schema'], 'grilltrack/reconcile/v1')
        self.assertFalse((state / 'work/reconcile-transaction.json').exists())
        self.assertEqual(fixture.retained(f.project, old['plan_id']), old_bytes)
        self.assertEqual((state / 'ledger.json').read_bytes(), old_bytes['projection/ledger.json'])
        self.assertEqual((state / 'events.jsonl').read_bytes(), old_bytes['projection/events.jsonl'])

    def test_object_missing_corrupt_foreign_and_symlink_fail_without_state_loss(self):
        f = self.f
        plan = f.plan()
        self.assertEqual(f.reconcile('--apply', plan['plan_id']).returncode, 0)
        path = fixture.retained_leaf_path(f.project, plan['plan_id'], 'snapshots/current/ledger.json')
        original = path.read_bytes()
        canonical = {n: (f.project / '.grilltrack' / n).read_bytes() for n in ('ledger.json', 'events.jsonl')}
        for kind in ('missing', 'corrupt', 'symlink'):
            with self.subTest(kind=kind):
                path.unlink()
                if kind == 'corrupt': path.write_bytes(b'foreign reference payload')
                elif kind == 'symlink':
                    outside = f.root / 'outside'; outside.write_bytes(original); path.symlink_to(outside)
                r = f.reconcile('--apply', plan['plan_id'])
                self.assertEqual(r.returncode, 2)
                for name, raw in canonical.items(): self.assertEqual((f.project / '.grilltrack' / name).read_bytes(), raw)
                if path.exists() or path.is_symlink(): path.unlink()
                path.write_bytes(original)
        pointer = f.project / '.grilltrack/lineage' / plan['plan_id'] / 'retention.json'
        saved = pointer.read_bytes()
        pointer.write_text(json.dumps({'schema': 'grilltrack/retained/v2', 'root': '0' * 64}))
        r = f.reconcile('--apply', plan['plan_id'])
        self.assertEqual(r.returncode, 2)
        self.assertEqual(pointer.read_text(), json.dumps({'schema': 'grilltrack/retained/v2', 'root': '0' * 64}))
        pointer.write_bytes(saved)
        self.assertEqual(f.reconcile('--apply', plan['plan_id']).returncode, 0)

    def test_many_nested_joins_add_unique_objects_without_copying_prior_roots(self):
        f = self.f
        codec, reconcile = fixture.retention_modules()
        deltas = []
        previous = {}
        preserved = {}
        for number in range(6):
            if number: self.fork_round(number)
            plan = f.plan()
            self.assertEqual(plan, f.plan())
            result = f.reconcile('--apply', plan['plan_id'])
            self.assertEqual(result.returncode, 0, result.stderr)
            state = f.project / '.grilltrack/lineage'
            current = {p.name: p.read_bytes() for p in (state / 'objects/sha256').iterdir()}
            self.assertTrue(all(current[key] == raw for key, raw in previous.items()))
            self.assertEqual(len(set(current.values())), len(current))
            self.assertTrue(all(hashlib.sha256(raw).hexdigest() == key for key, raw in current.items()))
            own = fixture.retained(f.project, plan['plan_id'])
            self.assertFalse(any('/lineage/' in name for name in own))
            self.assertEqual({p.name for p in (state / plan['plan_id']).iterdir()}, {'retention.json', 'applied.json'})
            for role, root in plan['retention']['lineage'].items():
                self.assertEqual(codec.unpack(root, current), reconcile.lineage_paths(plan['refs'][role], f.project))
            for old_id, old_bytes in preserved.items(): self.assertEqual(fixture.retained(f.project, old_id), old_bytes)
            preserved[plan['plan_id']] = own
            deltas.append(len(current) - len(previous)); previous = current
            complete = f.state_bytes()
            self.assertEqual(f.reconcile('--apply', plan['plan_id']).returncode, 0)
            self.assertEqual(complete, f.state_bytes())
        # Six joins add a bounded number of new directory/leaf objects each;
        # recursive snapshot copies would grow with all prior repeated paths.
        self.assertTrue(all(delta < 50 for delta in deltas[1:]), deltas)
        self.assertLessEqual(max(deltas[1:]), 2 * min(deltas[1:]))
        self.growth_statistics = {'joins': len(deltas), 'new_objects_per_join': deltas,
                                  'final_unique_objects': len(previous),
                                  'final_object_bytes': sum(map(len, previous.values())),
                                  'all_prior_roots_preserved': True,
                                  'no_nested_snapshot_copies': True}
