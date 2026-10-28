# CI-only helper (not packaged): summarize one gevent testrunner log --
# the runner's own totals, the passed count, and every skip grouped by reason.
from __future__ import print_function

import io
import re
import sys
from collections import Counter

ANSI = re.compile(r'\x1b\[[0-9;]*m')
RESULT = re.compile(r' \.\.\. (ok|skipped|FAIL|ERROR|expected failure|unexpected success)\b ?(.*)$')
TOTAL = re.compile(r'^Ran (\d+) tests(?: \(skipped=(\d+)\))? in (\d+) files')
DISABLED = re.compile(r'^\s*Skipped (test\S*) \(\d+\)\s*$')
FAILED_TEST = re.compile(r'^\s*(FAIL|ERROR): (\S+ \([^)]*\))')
RERUN_HEADER = re.compile(r'^\d+/\d+ tests rerun')

# Collapse per-module variants of one reason into a single line.
COLLAPSE = (
    (re.compile(r"^(['\"])Removed by patched_tests_setup: .*$"),
     "'Removed by patched_tests_setup: <stdlib test name>'"),
    (re.compile(r"^(['\"])Need stdlib counterpart to gevent\.\S+?(['\"])$"),
     "'Need stdlib counterpart to gevent.<module>'"),
    (re.compile(r"^(['\"])Module gevent\.\S+ fails the all formula; fix it(['\"])$"),
     "'Module gevent.<module> fails the all formula; fix it'"),
)

# Why the skips that are not self-explanatory cannot run on this leg.
EXPLAIN = (
    (re.compile(r"network' resource not enabled|Requires resource 'network'|network is not enabled"),
     "manylinux/musllinux wheel legs run with GEVENTTEST_USE_RESOURCES=-network exactly as "
     "upstream's make-manylinux does; the network tests run in the Linux, macOS and "
     "Windows test jobs"),
    (re.compile(r"Requires resource '(psycopg2|webpy|sendfile|unixsocket_client|unixsocket_server)'"),
     "example script upstream tags '# gevent-test-requires-resource: <name>' with a resource "
     "name that no test run enables, so it is never run as a test (psycopg2_pool.py needs a "
     "PostgreSQL server, webpy.py web.py, unixsocket_*.py and geventsendfile.py a separately "
     "started peer); example scripts, not library code"),
    (re.compile(r"_testcapi"),
     "CPython-internal _testcapi helper that this interpreter build does not provide"),
    (re.compile(r"randomly fails on Travis with ares and on appveyor"),
     "upstream skips TestEtcHosts on every CI run (round-robin DNS of the hosts it "
     "resolves makes the comparison random)"),
    (re.compile(r"import ares|ares resolver|resolver_ares|gevent\.ares"),
     "c-ares extension not compiled in: the published Windows wheels contain no "
     "gevent/resolver/cares*.pyd (appveyor builds from a zip without the git checkout "
     "setup.py needs for deps/c-ares), so building it would change the artifact"),
    (re.compile(r"dnspython"),
     "setup.py's test extra installs dnspython only for Python < 3.10 "
     "(dnspython >= 1.16.0, < 2.0; python_version < '3.10')"),
    (re.compile(r"psutil not available"),
     "psutil has no PyPy build for Windows and fails to link from source there; "
     "setup.py's test extra omits it for that platform"),
    (re.compile(r"gevent\.libev\.(watcher|corecffi|_corecffi)"),
     "setup.py does not build the libev CFFI backend on Windows"),
    (re.compile(r"Python 2, needs future backport"),
     "Python 2-only test (needs both 'thread' and the 'future' backport's '_thread'); "
     "it runs on the Python 2 legs, where run-tests.sh installs 'future'"),
    (re.compile(r"TIPC"),
     "TIPC kernel module not available in this runner's kernel"),
    (re.compile(r"Removed by patched_tests_setup"),
     "stdlib test disabled by gevent.testing.patched_tests_setup "
     "(gevent-incompatible or environment-specific; names listed above)"),
    (re.compile(r"Need stdlib counterpart|fails the all formula"),
     "gevent-only module with no stdlib module to compare against"),
)


def main(path, status):
    with io.open(path, encoding='utf-8', errors='replace') as f:
        lines = [ANSI.sub('', l.rstrip('\r\n')) for l in f]

    outcomes = Counter()
    reasons = Counter()
    empty_reason_tests = Counter()
    disabled = Counter()
    total = None
    modules = {}    # module command -> Counter of results; a rerun replaces the earlier one
    current = None
    failed_tests = []
    reruns = []
    in_reruns = False
    for line in lines:
        if line.startswith('| '):
            current = modules[line[2:].strip()] = Counter()
            continue
        if line.startswith(('- ', '! ')):
            current = None
        if RERUN_HEADER.match(line.strip()):
            in_reruns = True
            continue
        if in_reruns:
            if line.strip().startswith('- '):
                reruns.append(line.strip()[2:])
                continue
            if line.strip():
                in_reruns = False
        m = FAILED_TEST.match(line)
        if m:
            failed_tests.append('%s %s' % (m.group(1), m.group(2)))
        m = TOTAL.match(line.strip())
        if m:
            total = m
            continue
        m = DISABLED.match(line)
        if m:
            disabled[m.group(1)] += 1
            continue
        m = RESULT.search(line)
        if m and current is not None:
            current[m.group(1)] += 1
        if m:
            outcomes[m.group(1)] += 1
            if m.group(1) == 'skipped':
                reason = m.group(2).strip()
                for pattern, replacement in COLLAPSE:
                    if pattern.match(reason):
                        reason = replacement
                        break
                if len(reason) > 160:
                    reason = reason[:157] + '...'
                if not reason.strip("'\""):
                    name = line[:m.start()].strip().split(' ')[0]
                    empty_reason_tests[name] += 1
                reasons[reason or '(no reason)'] += 1

    print()
    print('=' * 70)
    print('gevent test summary (exit status %s)' % status)
    final = Counter()
    for counts in modules.values():
        final.update(counts)
    if total:
        print('Runner totals: Ran %s tests (skipped=%s) in %s files. The runner reads '
              'each module\'s "OK (skipped=N)" line and misses it when a module prints a '
              'warning after it (e.g. stdlib test_socket.py), so its skipped figure is low; '
              'the per-test counts below are taken from the verbose result lines.'
              % (total.group(1), total.group(2) or 0, total.group(3)))
    else:
        print('Runner totals: (no "Ran N tests ... in N files" line found)')
    if final:
        print('Per-test results, last run of each module: %s'
              % ', '.join('%s=%d' % kv for kv in sorted(final.items())))
    print('Per-test result lines (including --second-chance reruns): %s'
          % ', '.join('%s=%d' % kv for kv in sorted(outcomes.items())))
    if reruns or failed_tests:
        print('Failed on the first attempt (rerun by --second-chance; the run exit status '
              'above is the outcome after the rerun and known_failures.py):')
        for name in sorted(set(failed_tests)):
            print('  - %s' % name)
        for cmd in reruns:
            print('  rerun group: %s' % cmd[:200])
    print('Skipped tests by reason (count x reason [why it cannot run here]):')
    for reason, count in sorted(reasons.items(), key=lambda kv: (kv[1], kv[0])):
        why = ''
        if not reason.strip("'\""):
            why = ('  [the test itself calls skipTest("") (CPython test_selectors does for '
                   'selector classes it cannot mock): %s]'
                   % ', '.join(sorted(empty_reason_tests)))
        for pattern, text in EXPLAIN:
            if pattern.search(reason):
                why = '  [%s]' % text
                break
        print('  %5d x %s%s' % (count, reason, why))
    explained = sum(c for r, c in reasons.items()
                    if not r.strip("'\"") or any(p.search(r) for p, _ in EXPLAIN))
    print('Per-test skip lines printed: %d, every one with its reason above; %d also '
          'annotated [why it cannot run here]; the rest are the tests\' own '
          'platform/version/feature conditions.'
          % (sum(reasons.values()), explained))
    if disabled:
        print('Stdlib tests removed by gevent.testing.patched_tests_setup '
              '(gevent-incompatible or environment-specific): %d names'
              % len(disabled))
    if final:
        print('Tests passed: %d (per-test "ok" lines, last run of each module); skipped: %d; '
              'exit status %s%s'
              % (final['ok'], final['skipped'], status,
                 ' (no unexpected failures)' if str(status) == '0' else ''))
    print('=' * 70)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else '?')
