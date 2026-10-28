#!/usr/bin/env python3
"""Read-only planning and explicitly approved application of portable rules."""
import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from datetime import datetime
from zoneinfo import ZoneInfo

VERSION = '1.0.0'
MANIFEST = '.personal-context.json'
FILES = ('AGENTS.md', 'CLAUDE.md', 'POLICY.md', 'README.md', '.gitignore')
TEMPLATES = Path(__file__).resolve().parent.parent / 'assets' / 'templates'


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest() if text is not None else None


def json_load(text):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f'Duplicate JSON key: {key}')
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=unique,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError(f'Invalid JSON: {x}')))


def read(path):
    if path.is_symlink():
        raise ValueError(f'Symlink is not a writable target: {path.name}')
    if path.exists() and not path.is_file():
        raise ValueError(f'Expected file: {path.name}')
    return path.read_text(encoding='utf-8') if path.exists() else None


def root_path(value):
    path = Path(value).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Target path must not traverse symlinks; use its real path')
    if not path.is_dir():
        raise ValueError('Target must be an existing directory')
    return path


def markers(name):
    if name == '.gitignore':
        return '# personal-context:begin', '# personal-context:end'
    return '<!-- personal-context:begin -->', '<!-- personal-context:end -->'


def block(text, name):
    if name == 'CLAUDE.md':
        return text
    start, end = markers(name)
    if start not in text and end not in text:
        return None
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError(f'Malformed managed block: {name}')
    before, rest = text.split(start)
    middle, after = rest.split(end)
    if not middle.startswith('\n') or not middle.endswith('\n'):
        raise ValueError(f'Malformed managed block: {name}')
    return middle[1:]


def wrap(body, name):
    a, b = markers(name)
    return f'{a}\n{body}{b}\n'


def timestamp(text, stamp):
    if text.startswith('---\n'):
        close = text.find('\n---', 4)
        if close == -1:
            raise ValueError('Unclosed Markdown front matter')
        head = text[:close]
        if re.search(r'^updated_at:', head, re.M):
            head = re.sub(r'^updated_at:.*$', f'updated_at: "{stamp}"', head, flags=re.M)
        else:
            head += f'\nupdated_at: "{stamp}"'
        return head + text[close:]
    return f'---\nupdated_at: "{stamp}"\n---\n\n' + text


def install(text, body, name, stamp):
    if name == 'CLAUDE.md':
        return body
    if text is None:
        result = wrap(body, name)
        if name == 'README.md':
            result += '\n## 主题文件目录\n\n尚未启用个人主题。新增文件后在此登记，不预填个人事实。\n'
    elif block(text, name) is None:
        result = text + ('\n' if text.endswith('\n') else '\n\n') + wrap(body, name)
    else:
        a, b = markers(name)
        before, rest = text.split(a)
        _, after = rest.split(b)
        result = before + wrap(body, name).rstrip('\n') + after
    return timestamp(result, stamp) if name.endswith('.md') else result


def load_state(text):
    state = json_load(text)
    data = state['data']
    if data['schema_version'] != 1:
        raise ValueError('Unsupported manifest schema version')
    version_tuple(data['policy_version'])
    ZoneInfo(data['timezone'])
    if set(data['baselines']) != set(FILES):
        raise ValueError('Manifest baseline file set mismatch')
    for name, item in data['baselines'].items():
        if digest(item['text']) != item['sha256']:
            raise ValueError(f'Baseline checksum mismatch: {name}')
    return state


def version_tuple(value):
    if not re.fullmatch(r'\d+\.\d+\.\d+', value):
        raise ValueError('Version must be MAJOR.MINOR.PATCH')
    return tuple(map(int, value.split('.')))


def inventory(root):
    # Snapshot names, not personal content; catches added files before apply.
    names = []
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in ('.git', '.obsidian', '__pycache__'))
        for name in sorted(files):
            names.append(str((Path(directory) / name).relative_to(root)))
    return names


def validate(root, overlay=None, state_text=None):
    overlay = overlay or {}
    errors, warnings = [], []
    def get(name):
        return overlay[name] if name in overlay else read(root / name)
    try:
        raw = state_text if state_text is not None else get(MANIFEST)
        if raw is None:
            raise ValueError('No initialization manifest')
        state = load_state(raw)
        data = state['data']
        for name in FILES:
            text = get(name)
            if text is None:
                errors.append(f'Missing managed file: {name}')
                continue
            current = block(text, name)
            if current is None:
                errors.append(f'Missing managed block: {name}')
            if name == 'CLAUDE.md' and text != '@AGENTS.md\n':
                errors.append('CLAUDE.md must contain only @AGENTS.md and a newline')
            if name.endswith('.md') and name != 'CLAUDE.md':
                if not re.match(r'---\n(?:[^\n]*\n)*?updated_at: "[^"\n]+"\n', text):
                    errors.append(f'Missing quoted updated_at front matter: {name}')
                # Ignore code examples when checking path links; anchors are not validated.
                clean = re.sub(r'```.*?```', '', text, flags=re.S)
                clean = re.sub(r'`[^`\n]*`', '', clean)
                for target in re.findall(r'\]\(([^)]+)\)', clean):
                    from urllib.parse import unquote
                    target = unquote(target.split('#')[0].strip('<>'))
                    if not target or re.match(r'[a-zA-Z][\w+.-]*:', target):
                        continue
                    path = root / target
                    if Path(target).is_absolute() or '..' in Path(target).parts:
                        errors.append(f'Nonportable local link in {name}: {target}')
                    elif target != MANIFEST and target not in overlay and not path.exists():
                        errors.append(f'Broken link in {name}: {target}')
            if current != data['baselines'][name]['text']:
                warnings.append(f'Local customization: {name}')
        for name in inventory(root):
            if name == MANIFEST:
                continue
            if name.endswith('.jsonl'):
                warnings.append(f'Legacy JSONL preserved; separate migration needed: {name}')
            elif name.endswith('.json'):
                try:
                    json_load(get(name))
                except (ValueError, TypeError) as exc:
                    errors.append(f'Invalid JSON {name}: {exc}')
    except (ValueError, KeyError, TypeError, OSError) as exc:
        errors.append(str(exc))
    return {'ok': not errors, 'errors': errors, 'warnings': warnings}


def plan(root, mode, version=VERSION, timezone=None, templates=TEMPLATES, resolutions=None):
    original = {name: read(root / name) for name in (*FILES, MANIFEST)}
    state = load_state(original[MANIFEST]) if original[MANIFEST] is not None else None
    if mode == 'upgrade' and state is None:
        raise ValueError('Upgrade requires an intact manifest; use reviewed adoption otherwise')
    zone = timezone or (state['data']['timezone'] if state else None)
    if not zone:
        raise ValueError('Initialization requires an explicit --timezone')
    if state and timezone and timezone != state['data']['timezone']:
        raise ValueError('Timezone changes require a separate reviewed migration')
    stamp = datetime.now(ZoneInfo(zone)).isoformat(timespec='seconds')
    new_version = version_tuple(version)
    template_dir = Path(templates) / version
    bases = {name: read(template_dir / name) for name in FILES}
    if any(body is None for body in bases.values()):
        raise ValueError('Incomplete template release')
    if state:
        old_version = version_tuple(state['data']['policy_version'])
        if new_version < old_version or new_version[0] != old_version[0]:
            raise ValueError('Downgrade or major upgrade needs a separate migration')
        if mode == 'init' and new_version != old_version:
            raise ValueError('Already initialized; use upgrade for a different release')
        if new_version == old_version and any(bases[n] != state['data']['baselines'][n]['text'] for n in FILES):
            raise ValueError('Immutable release changed under the same version')
    resolutions = resolutions or {}
    if not set(resolutions).issubset(FILES) or any(not isinstance(x, str) for x in resolutions.values()):
        raise ValueError('Resolutions must map managed filenames to full text')
    output, conflicts = {}, []
    for name in FILES:
        old = original[name]
        body = bases[name]
        issue = None
        if name in resolutions:
            proposed = resolutions[name]
            if proposed != old and name.endswith('.md') and name != 'CLAUDE.md':
                proposed = timestamp(proposed, stamp)
        elif old is None:
            proposed = install(None, body, name, stamp)
        elif state:
            current = block(old, name)
            baseline = state['data']['baselines'][name]['text']
            if current is None:
                issue = 'Managed block removed; explicit resolution required'
                proposed = old
            elif current == body or baseline == body:
                proposed = old
            elif current == baseline:
                proposed = install(old, body, name, stamp)
            else:
                issue = 'Both user and upstream changed this managed block'
                proposed = old
        elif (name == 'POLICY.md' and old.strip()) or (name == 'CLAUDE.md' and old != body):
            issue = 'Existing rules require explicit reviewed integration'
            proposed = old
        elif name != 'CLAUDE.md' and block(old, name) is not None:
            issue = 'Untracked managed block without baseline'
            proposed = old
        else:
            proposed = old if name == 'CLAUDE.md' else install(old, body, name, stamp)
        output[name] = proposed
        if issue:
            conflicts.append({'path': name, 'reason': issue})
    data = {'schema_version': 1, 'policy_version': version, 'timezone': zone,
            'template_source': 'personal-context-init bundled templates',
            'baselines': {n: {'text': b, 'sha256': digest(b)} for n, b in bases.items()},
            'customizations': [n for n in FILES if block(output[n], n) != bases[n]]}
    changed = any(output[n] != original[n] for n in FILES)
    if state and data == state['data'] and not changed:
        new_state = original[MANIFEST]
    else:
        new_state = json.dumps({'_meta': {'updated_at': stamp}, 'data': data}, ensure_ascii=False, indent=2) + '\n'
    report = validate(root, output, new_state)
    changes = {n: output[n] for n in FILES if output[n] != original[n]}
    if new_state != original[MANIFEST]:
        changes[MANIFEST] = new_state
    return {'plan_schema': 1, 'target': str(root), 'mode': mode,
            'expected': {n: digest(t) for n, t in original.items()}, 'inventory': inventory(root),
            'changes': changes, 'conflicts': conflicts, 'validation': report,
            'diff': ''.join(''.join(difflib.unified_diff((original[n] or '').splitlines(True),
                       t.splitlines(True), fromfile=n, tofile=n)) for n, t in changes.items() if n != MANIFEST)}


def atomic_write(path, text):
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
    fd, tmp = tempfile.mkstemp(prefix='.context-write-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def apply(plan_data, approved=False):
    if not approved:
        raise ValueError('Apply requires approval of this concrete plan')
    if plan_data.get('plan_schema') != 1 or plan_data['conflicts']:
        raise ValueError('Unsupported or unresolved plan')
    root = root_path(plan_data['target'])
    expected = plan_data['expected']
    changes = plan_data['changes']
    if set(expected) != set((*FILES, MANIFEST)) or not set(changes).issubset(expected):
        raise ValueError('Invalid plan file scope')
    original = {n: read(root / n) for n in expected}
    if any(digest(original[n]) != h for n, h in expected.items()) or inventory(root) != plan_data['inventory']:
        raise ValueError('Stale plan; inspect changes and re-plan')
    if any(not isinstance(t, str) for t in changes.values()):
        raise ValueError('Plans cannot delete files')
    candidate_state = changes.get(MANIFEST, original[MANIFEST])
    report = validate(root, changes, candidate_state)
    if not report['ok']:
        raise ValueError('Validation failed: ' + '; '.join(report['errors']))
    written = []
    try:
        for name in FILES:
            if name in changes:
                atomic_write(root / name, changes[name])
                written.append(name)
        report = validate(root, state_text=candidate_state)
        if not report['ok']:
            raise ValueError('Post-write validation failed: ' + '; '.join(report['errors']))
        if MANIFEST in changes:
            atomic_write(root / MANIFEST, candidate_state)
            written.append(MANIFEST)
    except Exception:
        for name in reversed(written):
            if original[name] is None:
                (root / name).unlink()
            else:
                atomic_write(root / name, original[name])
        raise
    return {'changed': written, 'validation': report}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('plan')
    p.add_argument('mode', choices=['init', 'upgrade'])
    p.add_argument('target')
    p.add_argument('--timezone')
    p.add_argument('--version', default=VERSION)
    p.add_argument('--templates', type=Path, default=TEMPLATES)
    p.add_argument('--resolutions', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = commands.add_parser('apply')
    a.add_argument('plan', type=Path)
    a.add_argument('--approved', action='store_true')
    args = parser.parse_args()
    try:
        if args.command == 'plan':
            root = root_path(args.target)
            out = args.output.resolve()
            if out == root or root in out.parents:
                raise ValueError('Store the plan outside the target folder')
            result = plan(root, args.mode, args.version, args.timezone, args.templates,
                          json_load(args.resolutions.read_text()) if args.resolutions else None)
            if out.exists():
                raise ValueError('Plan output exists; choose a new path')
            atomic_write(out, json.dumps(result, ensure_ascii=False, indent=2) + '\n')
            print(json.dumps({'output': str(out), 'changed': list(result['changes']),
                              'conflicts': result['conflicts'], 'validation': result['validation']}, ensure_ascii=False, indent=2))
            return 0 if not result['conflicts'] and result['validation']['ok'] else 2
        print(json.dumps(apply(json_load(args.plan.read_text()), args.approved), ensure_ascii=False, indent=2))
        return 0
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
