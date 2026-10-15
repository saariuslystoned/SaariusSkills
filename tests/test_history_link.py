"""Explicit canonical witnesses preserve genuine paused history without closure."""
import json
import unittest
from tests import test_nested_reconcile as nested
from tests import test_reconcile as fixture


class HistoryLinkTests(unittest.TestCase):
    def setUp(self):
        self.n = nested.NestedReconcileTests()
        self.n.setUp()
        self.f = f = self.n.f
        _, self.r = fixture.retention_modules()
        f.git('checkout', '--detach', self.n.nested)
        paused = f.cli('pause', '--reason', 'Synthetic proof remains historical',
                       '--next-safe-action', 'Keep earlier verification historical')
        self.assertEqual(paused.returncode, 0, paused.stderr)
        self.witness = f.commit('real paused canonical witness')
        self.original = {name: self.r.git(f.project, 'show', self.witness + ':.grilltrack/' + name)
                         for name in ('ledger.json', 'events.jsonl')}
        for name in self.original:
            (f.project / '.grilltrack' / name).write_bytes(
                self.r.git(f.project, 'show', self.n.base + ':.grilltrack/' + name))
        self.anchor = f.commit('retained later join with earlier live canonical history')
        f.base = f.current = f.incoming = self.anchor

    def tearDown(self):
        self.n.tearDown()

    def link(self, *args, witness=None):
        return self.f.cli('history-link', '--anchor-ref', self.anchor,
                          '--witness-ref', witness or self.witness, *args)

    def test_paused_witness_links_history_without_changing_canonical_state(self):
        f = self.f
        before = f.state_bytes()
        refused = f.reconcile()
        self.assertEqual(refused.returncode, 2)
        self.assertIn('unrelated join', refused.stderr)
        result = self.link()
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        self.assertEqual(before, f.state_bytes())
        self.assertEqual(self.link('--apply', plan['plan_id']).returncode, 0)
        after = f.state_bytes()
        self.assertEqual(before, {key: raw for key, raw in after.items() if not key.startswith('history-links/')})
        self.assertEqual(self.link('--apply', plan['plan_id']).returncode, 0)
        f.base = f.current = f.incoming = f.commit('add immutable historical link')
        self.assertEqual(f.reconcile().returncode, 0)
        for name, raw in self.original.items():
            self.assertEqual(self.r.git(f.project, 'show', self.witness + ':.grilltrack/' + name), raw)
        old = json.loads(self.original['ledger.json'])
        self.assertEqual(old['status'], 'paused')
        self.assertTrue(any(d['status'] == 'needs_reverification' for d in old['decisions']))

    def apply_link(self):
        result = self.link()
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        applied = self.link('--apply', plan['plan_id'])
        self.assertEqual(applied.returncode, 0, applied.stderr)
        return self.f.project / plan['path']

    def test_ambient_uncommitted_record_does_not_authorize_a_plan(self):
        self.apply_link()
        result = self.f.reconcile()
        self.assertEqual(result.returncode, 2)
        self.assertIn('unrelated join', result.stderr)

    def test_unconnected_valid_earlier_witness_does_not_whitelist_all_roots(self):
        result = self.link(witness=self.n.base)
        self.assertEqual(result.returncode, 2)
        self.assertIn('unrelated join', result.stderr)

    def test_nonancestor_witness_and_mutable_refs_are_refused(self):
        f = self.f
        (f.project / '.grilltrack/proof').mkdir(exist_ok=True)
        (f.project / '.grilltrack/proof/later.txt').write_text('Neutral later source')
        later = f.commit('nonancestral later witness')
        self.assertEqual(self.link(witness=later).returncode, 2)
        self.assertEqual(self.link(witness='HEAD').returncode, 2)

    def test_tampered_record_is_not_authority(self):
        f = self.f
        path = self.apply_link()
        data = json.loads(path.read_bytes())
        data['canonical']['ledger.json'] = '0' * 64
        path.write_text(json.dumps(data))
        f.base = f.current = f.incoming = f.commit('forged witness record')
        result = f.reconcile()
        self.assertEqual(result.returncode, 2)
        self.assertIn('historical link', result.stderr)

    def test_inherited_link_cannot_disappear(self):
        f = self.f
        path = self.apply_link()
        linked = f.commit('real historical link')
        path.unlink()
        removed = f.commit('remove historical authority')
        f.base, f.current, f.incoming = linked, removed, linked
        self.assertEqual(f.reconcile().returncode, 2)

    def test_apply_is_bound_to_exact_target_commit(self):
        f = self.f
        plan = json.loads(self.link().stdout)
        (f.project / 'neutral.txt').write_text('Later source state')
        f.git('add', 'neutral.txt')
        f.commit('later source identity')
        result = self.link('--apply', plan['plan_id'])
        self.assertEqual(result.returncode, 2)
        self.assertIn('digest', result.stderr)

    def test_dirty_missing_retained_artifact_cannot_be_linked(self):
        path = self.f.project / '.grilltrack/lineage' / self.n.second['plan_id'] / 'retention.json'
        path.unlink()
        result = self.link()
        self.assertEqual(result.returncode, 2)
        self.assertIn('target immutable lineage differs', result.stderr)

    def test_anchor_must_be_in_target_ancestry(self):
        f = self.f
        f.git('checkout', '--detach', self.n.base)
        result = self.link()
        self.assertEqual(result.returncode, 2)

    def test_forged_witness_canonical_event_prefix_is_refused(self):
        f = self.f
        f.git('checkout', '--detach', self.witness)
        (f.project / '.grilltrack/events.jsonl').write_bytes(fixture.events(900, 1))
        forged = f.commit('forged canonical event prefix')
        for name in self.original:
            (f.project / '.grilltrack' / name).write_bytes(
                self.r.git(f.project, 'show', self.anchor + ':.grilltrack/' + name))
        self.anchor = f.commit('anchor forged witness')
        result = self.link(witness=forged)
        self.assertEqual(result.returncode, 2)
        self.assertIn('lineage', result.stderr)

    def test_incoming_link_is_retained_when_join_is_applied(self):
        f = self.f
        path = self.apply_link()
        linked = f.commit('incoming historical authority')
        f.git('checkout', '--detach', self.anchor)
        f.base, f.current, f.incoming = self.anchor, self.anchor, linked
        plan = f.plan()
        result = f.reconcile('--apply', plan['plan_id'])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(path.is_file(), 'incoming plan authority must be retained explicitly')

    def test_nested_source_link_cannot_become_unbound_ambient_authority(self):
        f = self.f
        path = self.apply_link()
        linked = f.commit('bound historical authority')
        f.base, f.current, f.incoming = self.anchor, linked, linked
        plan = f.plan()
        self.assertEqual(f.reconcile('--apply', plan['plan_id']).returncode, 0)
        f.commit('joined bound source history')
        path.unlink()
        removed = f.commit('drop record but keep old source commits')
        f.base, f.current, f.incoming = self.anchor, removed, removed
        result = f.reconcile()
        self.assertEqual(result.returncode, 2, result.stdout)

    def test_incoming_only_anchor_is_refused_before_a_single_parent_apply(self):
        f = self.f
        self.apply_link()
        incoming = f.commit('link anchored only on incoming history')
        f.git('checkout', '--detach', self.n.base)
        f.base = f.current = self.n.base
        f.incoming = incoming
        result = f.reconcile()
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn('historical link anchor must precede current', result.stderr)


if __name__ == '__main__':
    unittest.main()
