import os
from dct.tools.image import read_image, MAX_IMAGE_BYTES


def test_read_image_valid(tmp_path):
    img_file = tmp_path / "test.png"
    img_file.write_bytes(b"mock image content")
    result = read_image(str(img_file))

    assert result.ok is True
    assert result.mime_type == "image/png"
    assert "data:image/png;base64," in result.data_url
    assert result.message == ""
    assert result.path == str(img_file.resolve())


def test_read_image_missing(tmp_path):
    img_file = tmp_path / "missing.png"
    result = read_image(str(img_file))

    assert result.ok is False
    assert "file not found" in result.message
    assert result.data_url == ""


def test_read_image_invalid_extension(tmp_path):
    img_file = tmp_path / "test.txt"
    img_file.write_bytes(b"not an image")
    result = read_image(str(img_file))

    assert result.ok is False
    assert "unsupported image format" in result.message
    assert result.data_url == ""


def test_read_image_too_large(tmp_path, monkeypatch):
    img_file = tmp_path / "large.jpg"
    img_file.write_bytes(b"content")

    monkeypatch.setattr(os.path, "getsize", lambda x: MAX_IMAGE_BYTES + 1)

    result = read_image(str(img_file))

    assert result.ok is False
    assert "image too large" in result.message


def test_read_image_read_error(tmp_path, monkeypatch):
    img_file = tmp_path / "error.png"
    img_file.write_bytes(b"content")

    def mock_open(*args, **kwargs):
        raise PermissionError("mock permission error")

    monkeypatch.setattr("builtins.open", mock_open)

    result = read_image(str(img_file))

    assert result.ok is False
    assert "cannot read file" in result.message
    assert "mock permission error" in result.message


def test_read_image_invalid_path(monkeypatch):
    def mock_abspath(path):
        raise ValueError("mock error")

    monkeypatch.setattr(os.path, "abspath", mock_abspath)

    result = read_image("any_path")

    assert result.ok is False
    assert "invalid path: any_path" in result.message
