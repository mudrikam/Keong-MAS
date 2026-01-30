"""Helpers to determine Pillow-supported image extensions and utility checks.

Deterministic: computes the supported extensions from PIL.Image.registered_extensions()
at import time so callers can rely on a stable set without trying to open files.
"""
from PIL import Image

# Build a set of lowercase extensions that Pillow recognizes (keys of registered_extensions())
PIL_EXTENSIONS = set(k.lower() for k in Image.registered_extensions().keys())

def get_supported_extensions():
    """Return a set of supported extensions (lowercase, including leading dot).
    e.g. {'.png', '.jpg', '.jpeg', '.webp', ...}
    """
    return PIL_EXTENSIONS

def extension_supported(path_or_ext):
    """Check if a path or extension is supported by Pillow deterministically.

    Accepts either a filename/path or a string extension (with or without leading dot).
    Returns True/False without attempting to open the file.
    """
    if not path_or_ext:
        return False
    ext = path_or_ext
    if not ext.startswith('.') and len(ext) > 1:
        # Possibly a filename
        import os
        ext = os.path.splitext(ext)[1]
    return ext.lower() in PIL_EXTENSIONS
