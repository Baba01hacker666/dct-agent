"""Tests for dct.tools.files.read_file — slicing, binary detection, metadata."""

import sys
import os
import tempfile
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dct.tools.files import read_file, ReadResult, fmt_size, _is_binary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_file(tmp_path, name, content, binary=False):
    """Create a file in tmp_path and return its path string."""
    p = tmp_path / name
    if binary:
        p.write_bytes(content)
    else:
        p.write_text(content, encoding="utf-8")
    return str(p)


def _make_lines(n):
    """Return a string with n numbered lines."""
    return "\n".join(f"line {i}" for i in range(1, n + 1))


# ---------------------------------------------------------------------------
# Basic reads
# ---------------------------------------------------------------------------

class TestBasicRead:
    def test_read_simple_file(self, tmp_path):
        path = _make_file(tmp_path, "hello.txt", "hello world\n")
        r = read_file(path)
        assert r.ok
        assert "hello world" in r.content
        assert r.total_lines == 1
        assert r.file_size > 0
        assert not r.is_binary

    def test_read_multiline(self, tmp_path):
        content = "aaa\nbbb\nccc\n"
        path = _make_file(tmp_path, "multi.txt", content)
        r = read_file(path)
        assert r.ok
        assert r.total_lines == 3
        # Line numbers should be embedded (right-aligned, 4-wide)
        assert "   1  aaa" in r.content
        assert "   2  bbb" in r.content
        assert "   3  ccc" in r.content

    def test_read_empty_file(self, tmp_path):
        path = _make_file(tmp_path, "empty.txt", "")
        r = read_file(path)
        assert r.ok
        assert r.total_lines == 0
        assert r.file_size == 0

    def test_read_nonexistent(self, tmp_path):
        r = read_file(str(tmp_path / "nope.txt"))
        assert not r.ok
        assert "not found" in r.message

    def test_metadata_header(self, tmp_path):
        content = "x\n" * 10
        path = _make_file(tmp_path, "meta.txt", content)
        r = read_file(path)
        assert r.ok
        assert "lines 1-10 of 10" in r.content
        assert "size:" in r.content


# ---------------------------------------------------------------------------
# Binary detection
# ---------------------------------------------------------------------------

class TestBinaryDetection:
    def test_binary_file_rejected(self, tmp_path):
        data = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        path = _make_file(tmp_path, "image.png", data, binary=True)
        r = read_file(path)
        assert not r.ok
        assert r.is_binary
        assert "binary" in r.message.lower()

    def test_text_with_high_bytes_not_binary(self, tmp_path):
        # UTF-8 text with accented chars — no null bytes
        content = "café résumé naïve\n"
        path = _make_file(tmp_path, "accent.txt", content)
        r = read_file(path)
        assert r.ok
        assert not r.is_binary

    def test_binary_detection_utility(self, tmp_path):
        from pathlib import Path
        bin_path = _make_file(tmp_path, "b.bin", b"\x00\x01\x02", binary=True)
        txt_path = _make_file(tmp_path, "t.txt", "hello")
        assert _is_binary(Path(bin_path))
        assert not _is_binary(Path(txt_path))


# ---------------------------------------------------------------------------
# Line slicing — start_line / end_line
# ---------------------------------------------------------------------------

class TestLineSlicing:
    @pytest.fixture(autouse=True)
    def make_test_file(self, tmp_path):
        self.path = _make_file(tmp_path, "lines.txt", _make_lines(50))

    def test_start_line_only(self):
        r = read_file(self.path, start_line=10)
        assert r.ok
        assert "line 10" in r.content
        assert "line 9" not in r.content
        assert "lines 10-50 of 50" in r.content

    def test_end_line_only(self):
        r = read_file(self.path, end_line=5)
        assert r.ok
        assert "line 5" in r.content
        assert "line 6" not in r.content
        assert "lines 1-5 of 50" in r.content

    def test_start_and_end(self):
        r = read_file(self.path, start_line=10, end_line=15)
        assert r.ok
        assert "line 10" in r.content
        assert "line 15" in r.content
        assert "line 9" not in r.content
        assert "line 16" not in r.content
        assert "lines 10-15 of 50" in r.content

    def test_start_beyond_file(self):
        r = read_file(self.path, start_line=100)
        assert r.ok
        assert r.total_lines == 50
        # Should show an empty range
        assert "lines" in r.content

    def test_end_beyond_file_clamped(self):
        r = read_file(self.path, end_line=999)
        assert r.ok
        assert "lines 1-50 of 50" in r.content


# ---------------------------------------------------------------------------
# Tail slicing
# ---------------------------------------------------------------------------

class TestTailSlicing:
    @pytest.fixture(autouse=True)
    def make_test_file(self, tmp_path):
        self.path = _make_file(tmp_path, "tail.txt", _make_lines(100))

    def test_tail_basic(self):
        r = read_file(self.path, tail=5)
        assert r.ok
        assert "line 96" in r.content
        assert "line 100" in r.content
        assert "line 95" not in r.content
        assert "lines 96-100 of 100" in r.content

    def test_tail_more_than_file(self):
        r = read_file(self.path, tail=500)
        assert r.ok
        assert "lines 1-100 of 100" in r.content

    def test_tail_zero(self):
        r = read_file(self.path, tail=0)
        assert r.ok
        assert r.total_lines == 100

    def test_tail_overrides_start_end(self):
        r = read_file(self.path, start_line=1, end_line=5, tail=3)
        assert r.ok
        assert r.warning != ""
        assert "tail takes precedence" in r.warning
        # Should show last 3 lines, not first 5
        assert "line 98" in r.content
        assert "line 100" in r.content


# ---------------------------------------------------------------------------
# Line limit / truncation
# ---------------------------------------------------------------------------

class TestLineLimit:
    def test_truncation(self, tmp_path):
        content = _make_lines(3000)
        path = _make_file(tmp_path, "big.txt", content)
        r = read_file(path, line_limit=100)
        assert r.ok
        assert "TRUNCATED" in r.content
        assert r.total_lines == 3000

    def test_default_limit(self, tmp_path):
        content = _make_lines(2500)
        path = _make_file(tmp_path, "big2.txt", content)
        r = read_file(path)
        assert r.ok
        assert "TRUNCATED" in r.content

    def test_no_truncation_under_limit(self, tmp_path):
        content = _make_lines(50)
        path = _make_file(tmp_path, "small.txt", content)
        r = read_file(path)
        assert r.ok
        assert "TRUNCATED" not in r.content


# ---------------------------------------------------------------------------
# Size limits
# ---------------------------------------------------------------------------

class TestSizeLimits:
    def test_reject_oversized_file(self, tmp_path):
        # Create a file just over 512KB
        path = tmp_path / "large.txt"
        path.write_text("x" * 600_000)
        r = read_file(str(path))
        assert not r.ok
        assert "too large" in r.message
        assert r.file_size > 0

    def test_custom_max_bytes(self, tmp_path):
        path = _make_file(tmp_path, "med.txt", "x" * 2000)
        r = read_file(str(path), max_bytes=1000)
        assert not r.ok
        assert "too large" in r.message

    def test_exact_max_bytes(self, tmp_path):
        content = "x" * 1000
        path = _make_file(tmp_path, "exact.txt", content)
        r = read_file(str(path), max_bytes=1000)
        assert r.ok


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_single_line_no_newline(self, tmp_path):
        path = _make_file(tmp_path, "oneline.txt", "just one line")
        r = read_file(path)
        assert r.ok
        assert r.total_lines == 1

    def test_only_newlines(self, tmp_path):
        path = _make_file(tmp_path, "newlines.txt", "\n\n\n")
        r = read_file(path)
        assert r.ok
        assert r.total_lines == 3

    def test_unicode_content(self, tmp_path):
        content = "日本語テスト\nélève\n🚀 rocket\n"
        path = _make_file(tmp_path, "unicode.txt", content)
        r = read_file(path)
        assert r.ok
        assert "日本語" in r.content
        assert "🚀" in r.content

    def test_returns_readresult_type(self, tmp_path):
        path = _make_file(tmp_path, "type.txt", "x")
        r = read_file(path)
        assert isinstance(r, ReadResult)
        assert isinstance(r, ReadResult)  # also a FileResult via inheritance


# ---------------------------------------------------------------------------
# fmt_size utility
# ---------------------------------------------------------------------------

class TestFmtSize:
    def test_bytes(self):
        assert fmt_size(500) == "500B"

    def test_kilobytes(self):
        assert fmt_size(2048) == "2.0KB"

    def test_megabytes(self):
        assert fmt_size(5 * 1024 * 1024) == "5.0MB"

    def test_zero(self):
        assert fmt_size(0) == "0B"
