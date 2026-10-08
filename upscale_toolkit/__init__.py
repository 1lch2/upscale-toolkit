"""Standalone image restoration desktop application."""
__version__ = '0.0.0.dev0'

try:
    from ._version import __version__
except ModuleNotFoundError:
    pass  # Source checkout before a tagged build.
