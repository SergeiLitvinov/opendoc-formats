"""Availability checks for optional modules, including missing dotted parents."""

from importlib import util


def missing_backends(requirements: tuple[str, ...]) -> list[str]:
    missing = []
    for name in requirements:
        try:
            available = util.find_spec(name) is not None
        except (ModuleNotFoundError, ValueError):
            available = False
        if not available:
            missing.append(name)
    return missing
