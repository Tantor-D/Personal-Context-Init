"""Run: python3 -m unittest discover -s tests -v"""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'skills' / 'personal-context-init' / 'scripts'
spec = importlib.util.spec_from_file_location('manage', SCRIPTS / 'manage.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class Workflows(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='context-test-')
        self.addCleanup(self.temp.cleanup)
        # macOS /var can be a symlink; use the real path as required by the helper.
        self.parent = Path(self.temp.name).resolve()
        self.root = self.parent / 'vault'
        self.root.mkdir()

    def init(self):
        p = m.plan(self.root, 'init', timezone='Asia/Shanghai')
        self.assertFalse(p['conflicts'])
        self.assertTrue(p['validation']['ok'], p['validation'])
        m.apply(p, approved=True)
        return p

    def files(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def release(self):
        templates = self.parent / 'templates'
        shutil.copytree(m.TEMPLATES / '1.0.0', templates / '1.1.0')
        p = templates / '1.1.0' / 'POLICY.md'
        p.write_text(p.read_text() + '\n## 测试版新增规则\n\n新增字段需明确单位。\n')
        return templates

    def test_empty_initialization_and_no_personal_topics(self):
        self.init()
        self.assertEqual(set(self.files()), set((*m.FILES, m.MANIFEST)))
        self.assertEqual((self.root / 'CLAUDE.md').read_text(), '@AGENTS.md\n')
        self.assertTrue(m.validate(self.root)['ok'])
        state = json.loads((self.root / m.MANIFEST).read_text())
        self.assertEqual(state['data']['policy_version'], '1.0.0')
        self.assertNotIn(str(self.root), (self.root / m.MANIFEST).read_text())

    def test_existing_directory_preserved_and_legacy_reported(self):
        (self.root / 'notes.md').write_text('# Existing note\nA fictional note.\n')
        (self.root / 'AGENTS.md').write_text('# Existing rules\nPreserve the project vocabulary.\n')
        (self.root / 'README.md').write_text('# Existing index\n[Note](notes.md)\n')
        (self.root / '.gitignore').write_text('scratch/\n')
        (self.root / 'events.jsonl').write_text('{"fictional":true}\n')
        before = self.files()
        p = self.init()
        self.assertIn('Legacy JSONL', str(p['validation']['warnings']))
        for name in ('notes.md', 'events.jsonl'):
            self.assertEqual((self.root / name).read_bytes(), before[name])
        for name in ('README.md', 'AGENTS.md', '.gitignore'):
            self.assertIn(before[name].decode(), (self.root / name).read_text())

    def test_existing_rules_block_then_reviewed_resolution(self):
        (self.root / 'POLICY.md').write_text('# Existing policy\nKeep original sources.\n')
        (self.root / 'CLAUDE.md').write_text('Require source dates.\n')
        before = self.files()
        p = m.plan(self.root, 'init', timezone='Asia/Shanghai')
        self.assertEqual({c['path'] for c in p['conflicts']}, {'POLICY.md', 'CLAUDE.md'})
        with self.assertRaises(ValueError):
            m.apply(p, approved=True)
        self.assertEqual(before, self.files())
        body = (m.TEMPLATES / '1.0.0' / 'POLICY.md').read_text()
        agent_body = (m.TEMPLATES / '1.0.0' / 'AGENTS.md').read_text()
        resolutions = {'POLICY.md': '# Existing policy\nKeep original sources.\n\n' + m.wrap(body, 'POLICY.md'),
                       'CLAUDE.md': '@AGENTS.md\n',
                       'AGENTS.md': m.wrap(agent_body, 'AGENTS.md') + '\nRequire source dates.\n'}
        resolved = m.plan(self.root, 'init', timezone='Asia/Shanghai', resolutions=resolutions)
        self.assertFalse(resolved['conflicts'])
        m.apply(resolved, approved=True)
        self.assertIn('Require source dates.', (self.root / 'AGENTS.md').read_text())
        self.assertIn('Keep original sources.', (self.root / 'POLICY.md').read_text())

    def test_repeat_is_byte_and_mtime_identical(self):
        self.init()
        before = self.files()
        mtimes = {n: (self.root / n).stat().st_mtime_ns for n in before}
        p = m.plan(self.root, 'init')
        self.assertEqual(p['changes'], {})
        self.assertEqual(m.apply(p, approved=True)['changed'], [])
        self.assertEqual(self.files(), before)
        self.assertEqual(mtimes, {n: (self.root / n).stat().st_mtime_ns for n in before})

    def test_upgrade_preserves_data_and_outside_block_changes(self):
        self.init()
        (self.root / 'notes.md').write_text('Fictional personal content\n')
        r = self.root / 'README.md'
        r.write_text(r.read_text() + '\n[Notes](notes.md)\n')
        a = self.root / 'AGENTS.md'
        a.write_text(a.read_text().replace('按需读取', '只按需读取'))
        before = self.files()
        templates = self.release()
        p = m.plan(self.root, 'upgrade', version='1.1.0', templates=templates)
        self.assertFalse(p['conflicts'])
        m.apply(p, approved=True)
        for n in ('notes.md', 'README.md', 'AGENTS.md'):
            self.assertEqual((self.root / n).read_bytes(), before[n])
        state = m.load_state((self.root / m.MANIFEST).read_text())
        self.assertEqual(state['data']['policy_version'], '1.1.0')
        self.assertIn('AGENTS.md', state['data']['customizations'])
        self.assertEqual(m.plan(self.root, 'upgrade', version='1.1.0', templates=templates)['changes'], {})

    def test_upgrade_conflict_preserves_files_until_resolution(self):
        self.init()
        policy = self.root / 'POLICY.md'
        policy.write_text(policy.read_text().replace('不补造来源没有的时间', '不得推测来源没有的时间'))
        before = self.files()
        templates = self.release()
        p = m.plan(self.root, 'upgrade', version='1.1.0', templates=templates)
        self.assertEqual([c['path'] for c in p['conflicts']], ['POLICY.md'])
        with self.assertRaises(ValueError):
            m.apply(p, approved=True)
        self.assertEqual(before, self.files())
        # Explicit choice: retain user's old rule block against the new baseline.
        resolved = m.plan(self.root, 'upgrade', version='1.1.0', templates=templates,
                          resolutions={'POLICY.md': policy.read_text()})
        m.apply(resolved, approved=True)
        self.assertIn('不得推测', policy.read_text())
        self.assertEqual(m.plan(self.root, 'upgrade', version='1.1.0', templates=templates)['changes'], {})

    def test_stale_plan_rejected(self):
        p = m.plan(self.root, 'init', timezone='Asia/Shanghai')
        (self.root / 'AGENTS.md').write_text('New work\n')
        before = self.files()
        with self.assertRaisesRegex(ValueError, 'Stale plan'):
            m.apply(p, approved=True)
        self.assertEqual(before, self.files())

    def test_invalid_json_prevents_any_write(self):
        (self.root / 'data.json').write_text('{"a":1,"a":2}')
        p = m.plan(self.root, 'init', timezone='Asia/Shanghai')
        self.assertFalse(p['validation']['ok'])
        with self.assertRaises(ValueError):
            m.apply(p, approved=True)
        self.assertEqual(set(self.files()), {'data.json'})

    def test_failure_rolls_back_and_does_not_advance_version(self):
        self.init()
        p = m.plan(self.root, 'upgrade', version='1.1.0', templates=self.release())
        before = self.files()
        original_writer = m.atomic_write
        def fail_manifest(path, text):
            if path.name == m.MANIFEST:
                raise OSError('Simulated disk failure')
            return original_writer(path, text)
        with patch.object(m, 'atomic_write', side_effect=fail_manifest):
            with self.assertRaises(OSError):
                m.apply(p, approved=True)
        self.assertEqual(before, self.files())

    def test_approval_required(self):
        p = m.plan(self.root, 'init', timezone='Asia/Shanghai')
        with self.assertRaises(ValueError):
            m.apply(p)
        self.assertEqual(self.files(), {})

    def test_symlink_managed_file_rejected(self):
        outside = self.parent / 'outside.md'
        outside.write_text('Keep me\n')
        (self.root / 'AGENTS.md').symlink_to(outside)
        with self.assertRaises(ValueError):
            m.plan(self.root, 'init', timezone='Asia/Shanghai')
        self.assertEqual(outside.read_text(), 'Keep me\n')

    def test_corrupt_manifest_rejected(self):
        self.init()
        p = self.root / m.MANIFEST
        state = json.loads(p.read_text())
        state['data']['baselines']['POLICY.md']['text'] += 'tampered'
        p.write_text(json.dumps(state))
        with self.assertRaises(ValueError):
            m.plan(self.root, 'upgrade')

    def test_missing_entrypoint_repair_preserves_other_files(self):
        self.init()
        (self.root / 'CLAUDE.md').unlink()
        before = self.files()
        p = m.plan(self.root, 'init')
        self.assertEqual(set(p['changes']) - {m.MANIFEST}, {'CLAUDE.md'})
        m.apply(p, approved=True)
        for name, content in before.items():
            if name != m.MANIFEST:
                self.assertEqual((self.root / name).read_bytes(), content)

    def test_same_version_template_mutation_is_rejected(self):
        self.init()
        templates = self.parent / 'changed-templates'
        shutil.copytree(m.TEMPLATES / '1.0.0', templates / '1.0.0')
        policy = templates / '1.0.0' / 'POLICY.md'
        policy.write_text(policy.read_text() + '\nUnversioned change\n')
        with self.assertRaisesRegex(ValueError, 'Immutable release'):
            m.plan(self.root, 'upgrade', templates=templates)

    def test_unknown_manifest_schema_is_rejected(self):
        self.init()
        path = self.root / m.MANIFEST
        state = json.loads(path.read_text())
        state['data']['schema_version'] = 99
        path.write_text(json.dumps(state))
        with self.assertRaisesRegex(ValueError, 'Unsupported manifest'):
            m.plan(self.root, 'init')

    def test_cli_roundtrip(self):
        planfile = self.parent / 'plan.json'
        def run(*args):
            return subprocess.run([sys.executable, str(SCRIPTS / 'manage.py'), *map(str, args)],
                                  capture_output=True, text=True)
        result = run('plan', 'init', self.root, '--timezone', 'Asia/Shanghai', '--output', planfile)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(self.files(), {})
        self.assertNotEqual(run('apply', planfile).returncode, 0)
        result = run('apply', planfile, '--approved')
        self.assertEqual(result.returncode, 0, result.stderr)
        check = subprocess.run([sys.executable, str(SCRIPTS / 'validate.py'), str(self.root)], capture_output=True, text=True)
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)


if __name__ == '__main__':
    unittest.main()
