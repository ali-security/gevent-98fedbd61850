# CI-only helper (not packaged: MANIFEST.in ships only .github/*.md).
# Imported from sitecustomize.py / usercustomize.py in this directory, which a
# test step puts on PYTHONPATH, so every unittest run (gevent.tests launches
# each test module as its own unittest.main()) uses TextTestRunner
# verbosity >= 2: one line per test, and each skip printed as
# "test_x ... skipped '<reason>'". usercustomize covers the --coverage legs,
# whose coveragesite/sitecustomize.py shadows ours.
import sys


def _patch(mod):
    cls = getattr(mod, 'TextTestRunner', None)
    if cls is None or getattr(cls, '_seal_verbose', False):
        return
    orig = cls.__init__

    def __init__(self, *args, **kwargs):
        # (stream, descriptions, verbosity, ...)
        if len(args) >= 3:
            args = args[:2] + (max(args[2], 2),) + args[3:]
        else:
            kwargs['verbosity'] = max(kwargs.get('verbosity', 1), 2)
        orig(self, *args, **kwargs)

    cls.__init__ = __init__
    cls._seal_verbose = True


class _VerboseRunnerFinder(object):
    _target = 'unittest.runner'
    _busy = False

    # Python 3
    def find_spec(self, name, path=None, target=None):
        if name != self._target or self._busy:
            return None
        import importlib.util
        self._busy = True
        try:
            spec = importlib.util.find_spec(name)
        finally:
            self._busy = False
        if spec is None or spec.loader is None or not hasattr(spec.loader, 'exec_module'):
            return spec
        orig_exec = spec.loader.exec_module

        def exec_module(module):
            orig_exec(module)
            _patch(module)

        spec.loader.exec_module = exec_module
        return spec

    # Python 2 / PyPy2
    def find_module(self, name, path=None):
        if sys.version_info[0] >= 3:
            return None
        if name != self._target or self._busy:
            return None
        return self

    def load_module(self, name):
        if name in sys.modules:
            mod = sys.modules[name]
        else:
            self._busy = True
            try:
                __import__(name)
            finally:
                self._busy = False
            mod = sys.modules[name]
        _patch(mod)
        return mod


if 'unittest.runner' in sys.modules:
    _patch(sys.modules['unittest.runner'])
else:
    sys.meta_path.insert(0, _VerboseRunnerFinder())
