"""
dct.tools.image
Image file reading and encoding for vision models.
"""

from __future__ import annotations
import base64
import os
from collections import namedtuple

ImageResult = namedtuple(
    "ImageResult", ["ok", "data_url", "message", "path", "mime_type"]
)

MAX_IMAGE_BYTES = 20 * 1024 * 1024  # 20 MB
SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}

MIME_MAP = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}


def read_image(path: str) -> ImageResult:
    """Read an image file and return a base64 data URL for vision models.

    Returns ImageResult with:
      - ok: bool
      - data_url: str (e.g. "data:image/png;base64,...") or ""
      - message: error message if !ok
      - path: resolved absolute path
      - mime_type: detected MIME type
    """
    try:
        abs_path = os.path.abspath(os.path.expanduser(path))
    except Exception:
        return ImageResult(False, "", f"invalid path: {path}", path, "")

    if not os.path.isfile(abs_path):
        return ImageResult(
            False, "", f"file not found: {abs_path}", abs_path, ""
        )

    ext = os.path.splitext(abs_path)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        return ImageResult(
            False,
            "",
            f"unsupported image format: {ext}. Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
            abs_path,
            "",
        )

    file_size = os.path.getsize(abs_path)
    if file_size > MAX_IMAGE_BYTES:
        return ImageResult(
            False,
            "",
            f"image too large: {file_size / 1024 / 1024:.1f} MB (max {MAX_IMAGE_BYTES / 1024 / 1024:.0f} MB)",
            abs_path,
            "",
        )

    try:
        with open(abs_path, "rb") as f:
            raw = f.read()
    except (OSError, PermissionError) as e:
        return ImageResult(False, "", f"cannot read file: {e}", abs_path, "")

    mime = MIME_MAP.get(ext, "application/octet-stream")
    b64 = base64.b64encode(raw).decode("ascii")
    data_url = f"data:{mime};base64,{b64}"

    return ImageResult(True, data_url, "", abs_path, mime)
