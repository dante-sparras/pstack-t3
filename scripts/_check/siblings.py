import importlib.util
import sys
from pathlib import Path

_cache = {}


def _load(name, filename):
    if name not in _cache:
        path = Path(__file__).resolve().parent.parent / filename
        spec = importlib.util.spec_from_file_location(f"pstack_{name}", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        _cache[name] = module
    return _cache[name]


def _catalog():
    return _load("catalog", "catalog.py")
