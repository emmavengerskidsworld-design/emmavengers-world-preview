"""Validate content/src and compile it into content/library (the files the app downloads).

  python3 tools/content_build.py            validate + compile every channel listed in build.json "write":
                                              live    -> content/library  (published records, active languages; the live site)
                                              preview -> content/preview  (+ drafts and in-review languages; the preview site, localhost)
                                            plus their registry locks and content/build-report.md
  python3 tools/content_build.py --check    validate and prove the committed libraries are up to date (writes nothing);
                                            exit 1 on any error - this is the required test (tools/run_tests.py)
  options: --channel live|preview|test  --src DIR --lib DIR --lock FILE --report FILE (for tests / scale runs)
           --no-files                skip picture/voice existence checks (scale tests with fake content)

After it succeeds, run python3 tools/build_sw.py so the offline cache knows the new files."""
import argparse, os, sys, tempfile, shutil, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from content.source import Source
from content.validate import Validator
from content.compile import Build
from content.report import render
from content.common import load_json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--channel', help='build only this channel (default: every channel in build.json "write")')
    ap.add_argument('--src', default=os.path.join(ROOT, 'content', 'src'))
    ap.add_argument('--lib', help='output folder (one channel: --channel, else build.json "channel"; default: the channel\'s "out")')
    ap.add_argument('--lock', help='registry lock file (only with --channel)')
    ap.add_argument('--report', default=os.path.join(ROOT, 'content', 'build-report.md'))
    ap.add_argument('--root', default=ROOT)
    ap.add_argument('--no-files', action='store_true')
    ap.add_argument('--quiet', action='store_true')
    a = ap.parse_args(argv)
    bcfg = load_json(os.path.join(a.src, 'build.json'))
    if a.channel: chans = [a.channel]
    elif a.lib or a.lock: chans = [bcfg.get('channel', 'preview')]   # one explicit output folder = the default channel
    else: chans = bcfg.get('write', [bcfg.get('channel', 'preview')])
    rc, reports = 0, []
    for ch in chans:
        out = bcfg.get('channels', {}).get(ch, {}).get('out', {})
        lib = a.lib or (os.path.join(a.root, out['lib']) if out.get('lib') else None)
        lock = a.lock or (os.path.join(a.root, out['lock']) if out.get('lock') else None)
        if not lib or not lock:
            print(f'FAILED: channel {ch} has no "out" in build.json; pass --lib and --lock', file=sys.stderr); return 1
        r, rep = build_channel(a, ch, lib, lock)
        rc = rc or r
        if rep: reports.append(rep)
    if reports and not a.check:
        # one report: the widest channel first (preview shows drafts), then the others' summaries
        reports.sort(key=lambda x: x[0] != 'preview')
        txt = reports[0][1] + ''.join(f'\n\n---\n\n{x[1]}' for x in reports[1:])
        open(a.report, 'w', encoding='utf-8').write(txt)
    return rc


def build_channel(a, channel, lib, lockp):
    say = (lambda *x: None) if a.quiet else print
    S = Source(a.src, a.root, channel=channel)
    V = Validator(S, os.path.join(ROOT, 'content', 'schema', 'v1'), channel=channel, check_files=not a.no_files)
    issues = V.run()
    errs = [i for i in issues if i.sev == 'error']
    for i in issues:
        if i.sev != 'info': say(f'[{channel}] {i}')
    if errs:
        print(f'FAILED [{channel}]: {len(errs)} errors, {sum(i.sev == "warn" for i in issues)} warnings', file=sys.stderr)
        return 1, None
    lock = load_json(lockp) if os.path.exists(lockp) else None
    B = Build(S, V, lock, channel=channel).run()
    rel = os.path.relpath(lib, a.root)
    if a.check:
        ok = _same_except_nothing(B.lock, lock)
        stale = []
        for f, b in B.files.items():
            p = os.path.join(lib, f)
            if not os.path.exists(p) or open(p, 'rb').read() != b:
                stale.append(f)
        if not ok or stale:
            print(f'FAILED [{channel}]: content/src changed but {rel} is not rebuilt ({len(stale)} files differ, lock {"same" if ok else "differs"}).'
                  f' Run: python3 tools/content_build.py && python3 tools/build_sw.py', file=sys.stderr)
            for s in stale[:5]: print('  stale:', s, file=sys.stderr)
            return 1, None
        say(f'OK [{channel}]: {len(B.recs)} records valid, {rel} up to date (sequence {B.catalog["sequence"]}), '
            f'languages {",".join(S.channel_locales)}, {sum(i.sev == "warn" for i in issues)} warnings')
        return 0, None
    removed = B.write(lib, lockp)
    say(f'OK [{channel}]: sequence {B.catalog["sequence"]}, {len(B.recs)} records, languages {",".join(S.channel_locales)}, '
        f'{len(B.files)} files in {rel}, removed {len(removed)} old files')
    return 0, (channel, render(S, V, B, issues))


def _same_except_nothing(a, b):
    return json.dumps(a, sort_keys=True) == json.dumps(b or {}, sort_keys=True)


if __name__ == '__main__':
    sys.exit(main())
