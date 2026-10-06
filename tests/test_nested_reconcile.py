"""Repeated canonical joins, using only neutral CLI-owned fixture history."""
import json
import unittest
import subprocess
import shutil
from tests import test_reconcile as fixture


class NestedReconcileTests(unittest.TestCase):
    def setUp(self):
        self.f = f = fixture.ReconcileTests()
        # One historical archive is enough for the nested proof fixtures;
        # the legacy suite separately exercises twenty-archive preservation.
        write_state = f.write_state
        def write_small_state(directory, data, log):
            if directory.name.startswith('historical-') and directory.name != 'historical-0':
                return
            write_state(directory, data, log)
        f.write_state = write_small_state
        f.setUp()
        self.first = f.plan()
        self.assertEqual(f.reconcile('--apply', self.first['plan_id']).returncode, 0)
        # A normal CLI apply committed on current does not merge incoming's
        # Git parent. Later forks must accept the exact inherited proof.
        self.base = self.join_commit([f.current], 'first canonical join')
        f.base = self.base
        state = f.project / '.grilltrack'
        live = json.loads((state / 'ledger.json').read_text())
        live['decisions'].append(fixture.decision('middle-current'))
        f.write_state(state, live, (state / 'events.jsonl').read_bytes() + fixture.events(500, 1))
        middle_current = f.commit('middle current')
        f.git('checkout', '--detach', self.base)
        live = json.loads((state / 'ledger.json').read_text())
        live['decisions'].append(fixture.decision('middle-incoming'))
        f.write_state(state, live, (state / 'events.jsonl').read_bytes() + fixture.events(501, 1))
        middle_incoming = f.commit('middle incoming')
        f.git('checkout', '--detach', middle_current)
        f.current, f.incoming = middle_current, middle_incoming
        self.second = f.plan()
        self.assertEqual(f.reconcile('--apply', self.second['plan_id']).returncode, 0)
        self.nested = self.join_commit([middle_current, middle_incoming], 'second canonical join')
        f.git('checkout', '--detach', self.base)
        live = json.loads((state / 'ledger.json').read_text())
        live['decisions'].append(fixture.decision('final-current'))
        f.write_state(state, live, (state / 'events.jsonl').read_bytes() + fixture.events(502, 1))
        f.current = f.commit('final current continuation')
        f.incoming = self.nested
        self.selection = {key: {'role': 'current', 'reason': 'Retain current answer and history.'}
                          for key in self.first['decision_ids']}

    def tearDown(self):
        self.f.tearDown()

    def join_commit(self, parents, title):
        f = self.f
        f.git('add', '.grilltrack')
        tree = f.git('write-tree')
        args = ['commit-tree', tree, '-m', title]
        for parent in parents:
            args += ['-p', parent]
        commit = f.git(*args)
        f.git('checkout', '--detach', commit)
        return commit

    def plan(self):
        f = self.f
        return f.plan_with_adjudication(f.write_adjudication(self.selection))

    def mutate_incoming(self, name, mutate):
        f = self.f
        f.git('checkout', '--detach', f.incoming)
        p = f.project / '.grilltrack' / 'lineage' / self.second['plan_id'] / name
        if mutate is None:
            p.unlink()
        else:
            mutate(p)
        f.incoming = f.commit('tampered retained proof')
        f.git('checkout', '--detach', f.current)

    def test_nested_join_plans_and_applies_with_exact_retention_and_retry(self):
        f = self.f
        before = f.state_bytes()
        missing = f.reconcile()
        self.assertEqual(missing.returncode, 2)
        self.assertIn('conflicting decision', missing.stderr)
        plan = self.plan()
        self.assertEqual(plan, self.plan())
        self.assertEqual(f.state_bytes(), before)
        manifest = f.write_adjudication(self.selection)
        result = f.reconcile('--adjudication-file', str(manifest), '--apply', plan['plan_id'])
        self.assertEqual(result.returncode, 0, result.stderr)
        state = f.project / '.grilltrack'
        joined = json.loads((state / 'ledger.json').read_text())
        self.assertEqual(len(joined['decisions']), 19)
        current = json.loads(f.git('show', f.current + ':.grilltrack/ledger.json'))
        chosen = {x['id']: x for x in joined['decisions']}
        for original in current['decisions']:
            d = chosen[original['id']]
            self.assertEqual(d['choice'], original['choice'])
            self.assertEqual(d['history'][:-1], original['history'])
        root = state / 'lineage' / plan['plan_id'] / 'snapshots'
        for role, files in plan['lineage'].items():
            ref = plan['refs'][role]
            for name in files:
                self.assertEqual((root / role / 'lineage' / name).read_bytes(),
                                 subprocess.check_output(['git', '-C', str(f.project), 'show', ref + ':.grilltrack/lineage/' + name]))
        self.assertEqual(f.cli('validate').returncode, 0)
        self.assertEqual(f.cli('focus', '--domain', 'later-progress', '--cadence', 'sequential').returncode, 0)
        progress = f.state_bytes()
        retry = f.reconcile('--adjudication-file', str(manifest), '--apply', plan['plan_id'])
        self.assertEqual(retry.returncode, 0, retry.stderr)
        self.assertTrue(json.loads(retry.stdout)['already_applied'])
        self.assertEqual(progress, f.state_bytes())

    def test_nested_receipt_missing_fails_read_only(self):
        self.mutate_incoming('applied.json', None)
        before = self.f.state_bytes()
        r = self.f.reconcile('--adjudication-file', str(self.f.write_adjudication(self.selection)))
        self.assertEqual(r.returncode, 2)
        self.assertEqual(before, self.f.state_bytes())

    def test_nested_projection_tampering_fails_read_only(self):
        def tamper(p):
            data = json.loads(p.read_text())
            data['decisions'][0]['choice'] = 'forged-projection'
            p.write_text(json.dumps(data))
        self.mutate_incoming('projection/ledger.json', tamper)
        r = self.f.reconcile('--adjudication-file', str(self.f.write_adjudication(self.selection)))
        self.assertEqual(r.returncode, 2)
        self.assertIn('lineage', r.stderr)

    def test_nested_crash_recovers_and_retained_proof_tamper_blocks_retry(self):
        f = self.f
        plan = self.plan()
        manifest = f.write_adjudication(self.selection)
        crash = f.reconcile('--adjudication-file', str(manifest), '--apply', plan['plan_id'],
                            failpoint='reconcile_crash_after_ledger')
        self.assertEqual(crash.returncode, 86)
        self.assertEqual(f.cli('show').returncode, 2)
        retry = f.reconcile('--adjudication-file', str(manifest), '--apply', plan['plan_id'])
        self.assertEqual(retry.returncode, 0, retry.stderr)
        retained = f.project / '.grilltrack/lineage' / plan['plan_id'] / 'snapshots/incoming/lineage' / self.second['plan_id'] / 'applied.json'
        retained.write_text('{}\n')
        r = f.reconcile('--adjudication-file', str(manifest), '--apply', plan['plan_id'])
        self.assertEqual(r.returncode, 2)
        self.assertIn('retained reconciliation source', r.stderr)

    def test_new_join_foreign_source_fails_even_with_valid_inherited_history(self):
        def tamper(p):
            data = json.loads(p.read_text())
            data['refs']['current'] = self.first['refs']['incoming']
            p.write_text(json.dumps(data))
        self.mutate_incoming('plan.json', tamper)
        before = self.f.state_bytes()
        r = self.f.reconcile('--adjudication-file', str(self.f.write_adjudication(self.selection)))
        self.assertEqual(r.returncode, 2)
        self.assertIn('foreign lineage source', r.stderr)
        self.assertEqual(before, self.f.state_bytes())

    def test_inherited_snapshot_tampering_and_missing_proof_fail_read_only(self):
        original = self.f.incoming
        for leaf in ('snapshots/current/ledger.json', 'applied.json'):
            with self.subTest(leaf=leaf):
                self.f.incoming = original
                self.mutate_incoming('../' + self.first['plan_id'] + '/' + leaf, None)
                before = self.f.state_bytes()
                r = self.f.reconcile('--adjudication-file', str(self.f.write_adjudication(self.selection)))
                self.assertEqual(r.returncode, 2)
                self.assertIn('inherited immutable lineage', r.stderr)
                self.assertEqual(before, self.f.state_bytes())

    def test_live_event_stream_requires_the_recomputed_projection_prefix(self):
        f = self.f
        f.git('checkout', '--detach', f.incoming)
        p = f.project / '.grilltrack/events.jsonl'
        event = json.loads(p.read_bytes().splitlines()[0])
        event['action'] = 'forged-event'
        p.write_text(json.dumps(event) + '\n')
        f.incoming = f.commit('changed canonical event')
        f.git('checkout', '--detach', f.current)
        before = f.state_bytes()
        r = f.reconcile('--adjudication-file', str(f.write_adjudication(self.selection)))
        self.assertEqual(r.returncode, 2)
        self.assertIn('descendant', r.stderr)
        self.assertEqual(before, f.state_bytes())

    def test_retained_closure_accepts_another_subsequent_join(self):
        f = self.f
        plan = self.plan()
        manifest = f.write_adjudication(self.selection)
        result = f.reconcile('--adjudication-file', str(manifest), '--apply', plan['plan_id'])
        self.assertEqual(result.returncode, 0, result.stderr)
        f.current = self.join_commit([f.current, f.incoming], 'third canonical join')
        self.selection.update({key: {'role': 'current', 'reason': 'Retain current composed history.'}
                               for key in ('middle-current', 'middle-incoming')})
        before = f.state_bytes()
        fourth = self.plan()
        self.assertEqual(fourth, self.plan())
        self.assertEqual(len(fourth['decision_ids']), 19)
        self.assertEqual(f.state_bytes(), before)

    def test_canonical_event_cannot_reuse_a_retained_history_identity(self):
        f = self.f
        p = f.project / '.grilltrack/events.jsonl'
        event = json.loads(fixture.events(500, 1))
        event['data']['sequence'] = 999
        with p.open('a') as stream:
            stream.write(json.dumps(event) + '\n')
        f.current = f.commit('conflicting retained event identity')
        before = f.state_bytes()
        r = f.reconcile('--adjudication-file', str(f.write_adjudication(self.selection)))
        self.assertEqual(r.returncode, 2)
        self.assertIn('conflicting event identity', r.stderr)
        self.assertEqual(before, f.state_bytes())

    def test_common_base_can_be_a_reachable_prior_join_projection(self):
        f = self.f
        original_current = f.current
        state = f.project / '.grilltrack'
        f.git('checkout', '--detach', self.base)
        live = json.loads((state / 'ledger.json').read_text())
        live['decisions'].append(fixture.decision('advanced-base'))
        f.write_state(state, live, (state / 'events.jsonl').read_bytes() + fixture.events(600, 1))
        advanced = f.commit('advanced common input')
        for suffix, number in [('current', 601), ('incoming', 602)]:
            f.git('checkout', '--detach', advanced)
            live = json.loads((state / 'ledger.json').read_text())
            live['decisions'].append(fixture.decision('advanced-' + suffix))
            f.write_state(state, live, (state / 'events.jsonl').read_bytes() + fixture.events(number, 1))
            setattr(f, suffix, f.commit('advanced fork ' + suffix))
        f.base = advanced
        f.git('checkout', '--detach', f.current)
        plan = f.plan()
        self.assertEqual(f.reconcile('--apply', plan['plan_id']).returncode, 0)
        nested = self.join_commit([f.current, f.incoming], 'join beyond original projection')
        f.base, f.current, f.incoming = self.base, original_current, nested
        f.git('checkout', '--detach', f.current)
        before = f.state_bytes()
        composed = self.plan()
        self.assertEqual(len(composed['decision_ids']), 20)
        self.assertEqual(before, f.state_bytes())

    def test_unrelated_archive_cannot_launder_a_source_ancestral_join(self):
        f = self.f
        saved = f.base, f.current, f.incoming
        f.current, f.incoming = self.second['refs']['current'], self.second['refs']['incoming']
        f.git('checkout', '--detach', f.current)
        extra = f.reconcile('--title', 'Unrelated duplicate join')
        self.assertEqual(extra.returncode, 0, extra.stderr)
        orphan = json.loads(extra.stdout)
        applied = f.reconcile('--title', 'Unrelated duplicate join', '--apply', orphan['plan_id'])
        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.join_commit([f.current, f.incoming], 'unrelated canonical join')
        preserved = f.root / 'orphan-proof'
        shutil.copytree(f.project / '.grilltrack/lineage' / orphan['plan_id'], preserved)
        f.base, f.current, f.incoming = saved
        f.git('checkout', '--detach', f.incoming)
        shutil.copytree(preserved, f.project / '.grilltrack/lineage' / orphan['plan_id'])
        unrelated = fixture.ledger('unrelated-archive', [], 'closed')
        unrelated['reconciliation'] = {'plan_id': orphan['plan_id']}
        f.write_state(f.project / '.grilltrack/archive/unrelated-archive', unrelated, fixture.events(700, 1))
        f.incoming = f.commit('splice unrelated join via archive metadata')
        f.git('checkout', '--detach', f.current)
        before = f.state_bytes()
        r = f.reconcile('--adjudication-file', str(f.write_adjudication(self.selection)))
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn('unrelated join', r.stderr)
        self.assertEqual(before, f.state_bytes())
