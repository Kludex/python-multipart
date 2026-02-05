from pathlib import Path

from python_multipart.multipart import File


def test_file_content_type() -> None:
    """Test that content_type is properly stored and accessible."""
    # Test with content_type provided
    file_with_ct = File(b"test.png", b"image", content_type=b"image/png")
    assert file_with_ct.content_type == b"image/png"
    assert file_with_ct.file_name == b"test.png"
    assert file_with_ct.field_name == b"image"

    # Test without content_type (defaults to None)
    file_without_ct = File(b"test.txt", b"document")
    assert file_without_ct.content_type is None
    assert file_without_ct.file_name == b"test.txt"

    # Test with explicit None content_type
    file_explicit_none = File(b"test.txt", content_type=None)
    assert file_explicit_none.content_type is None


def test_file_repr_with_content_type() -> None:
    """Test that the repr includes content_type."""
    file_with_ct = File(b"test.png", b"image", content_type=b"image/png")
    repr_str = repr(file_with_ct)
    assert "content_type=b'image/png'" in repr_str
    assert "file_name=b'test.png'" in repr_str
    assert "field_name=b'image'" in repr_str

    file_without_ct = File(b"test.txt", b"doc")
    repr_str = repr(file_without_ct)
    assert "content_type=None" in repr_str


def test_upload_dir_with_leading_slash_in_filename(tmp_path: Path) -> None:
    upload_dir = tmp_path / "upload"
    upload_dir.mkdir()

    # When the file_name provided has a leading slash, we should only use the basename.
    # This is to avoid directory traversal.
    to_upload = tmp_path / "foo.txt"

    file = File(
        bytes(to_upload),
        config={
            "UPLOAD_DIR": bytes(upload_dir),
            "UPLOAD_KEEP_FILENAME": True,
            "UPLOAD_KEEP_EXTENSIONS": True,
            "MAX_MEMORY_FILE_SIZE": 10,
        },
    )
    file.write(b"123456789012")
    assert not file.in_memory
    assert Path(upload_dir / "foo.txt").exists()
    assert Path(upload_dir / "foo.txt").read_bytes() == b"123456789012"
