# CI-only helper (not packaged): print every known_failures.py entry whose
# condition is active on this platform, with its reason, so the log explains
# any "expected failure" / ignored test the gevent testrunner reports.
from __future__ import print_function

import os
import sys

import traceback


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        'src', 'gevent', 'tests', 'known_failures.py')
    ns = {'__name__': 'known_failures'}
    with open(path) as f:
        code = compile(f.read(), path, 'exec')
    exec(code, ns)

    print('=== Active known_failures.py entries on this platform (name: action: reason) ===')
    for name, value in sorted(ns['Definitions'].__dict__.items()):
        actions = value._conds if isinstance(value, ns['Multi']) else (value,)
        for action in actions:
            if not isinstance(action, ns['_Action']):
                continue
            active = [label for label, cond in (
                ('when', action.when),
                ('run_alone', action.run_alone),
            ) if cond]
            if not active:
                continue
            reason = ' '.join((action.reason or '').split()) or '(no reason given)'
            print('%s.py: %s [%s]: %s' % (name, type(action).__name__, ','.join(active), reason))
    print('=== end known_failures ===')


try:
    main()
except Exception: # diagnostic output only; never a test gate
    traceback.print_exc()
    print('known_failure_reasons: could not evaluate known_failures.py')
