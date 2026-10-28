#!/usr/bin/env bash
# CI-only wrapper (not packaged): run the gevent test command given as
# arguments, unchanged, with
#  - this directory on PYTHONPATH (sitecustomize/usercustomize raise unittest
#    verbosity to 2, so every test and every skip reason is printed),
#  - the known_failures.py entries active on this platform printed first,
#  - a summary of the run (passed count, skip reasons) printed last.
# Exits with the test command's own status.
HERE=$(cd "$(dirname "$0")" && (pwd -W 2>/dev/null || pwd))
REPO=$(cd "$(dirname "$0")/../.." && (pwd -W 2>/dev/null || pwd))
case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*) SEP=';' ;;
    *) SEP=':' ;;
esac
export PYTHONPATH="$HERE${PYTHONPATH:+$SEP$PYTHONPATH}"

echo "GEVENTTEST_USE_RESOURCES=${GEVENTTEST_USE_RESOURCES:-<unset: gevent default resources, network included>}"
case "${GEVENTTEST_USE_RESOURCES:-}" in
    *-network*)
        echo "  -> tests needing the external internet are skipped on this leg, as in upstream's" \
             "own config for it (scripts/releases/make-manylinux);" \
             "they run with network enabled in the Linux, macOS and Windows test jobs."
        ;;
esac
if python -c 'import sys; sys.exit(0 if sys.version_info[0] == 2 else 1)' \
        && ! python -c 'import _thread' >/dev/null 2>&1; then
    # test__monkey_futures_thread checks that monkey-patching also patches the
    # 'future' backport's _thread module; it skips unless that is installed.
    echo "Python 2: installing the 'future' backport for test__monkey_futures_thread"
    python -m pip install -q future
fi
python "$HERE/known_failure_reasons.py" "$REPO/src/gevent/tests/known_failures.py"

TMPD="${RUNNER_TEMP:-/tmp}"
if command -v cygpath >/dev/null 2>&1; then
    TMPD=$(cygpath -u "$TMPD")
fi
LOG="$TMPD/gevent-tests-$$.log"
LOGPY="$LOG"
if command -v cygpath >/dev/null 2>&1; then
    LOGPY=$(cygpath -m "$LOG")
fi

echo "+ $*"
"$@" 2>&1 | tee "$LOG"
status=${PIPESTATUS[0]}
{
    echo
    echo "### $* (GEVENT_LOOP=${GEVENT_LOOP:-default} GEVENT_RESOLVER=${GEVENT_RESOLVER:-default}" \
         "GEVENT_FILE=${GEVENT_FILE:-default} PURE_PYTHON=${PURE_PYTHON:-} GEVENTTEST_LEAKCHECK=${GEVENTTEST_LEAKCHECK:-})"
    python "$HERE/test_summary.py" "$LOGPY" "$status"
} | tee -a "$TMPD/gevent-test-summaries.txt"
rm -f "$LOG"
exit "$status"
