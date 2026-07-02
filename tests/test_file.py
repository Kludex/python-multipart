from pathlib import Path

from python_multipart.multipart import File


def test_none_file_name_with_keep_extensions_no_attribute_error() -> None:
    """File(file_name=None) must not raise AttributeError when flushed to disk
    with UPLOAD_KEEP_EXTENSIONS=True (regression: _ext was not initialised for
    the None branch)."""
    file = File(None, config={"UPLOAD_KEEP_EXTENSIONS": True, "MAX_MEMORY_FILE_SIZE": 0})
    try:
        # Writing one byte exceeds MAX_MEMORY_FILE_SIZE=0, triggering flush_to_disk()
        # which previously accessed self._ext -> AttributeError.
        file.write(b"x")
    finally:
        file.close()


def test_none_file_name_with_keep_filename_no_attribute_error() -> None:
    """File(file_name=None) must not raise AttributeError when flushed to disk
    with UPLOAD_KEEP_FILENAME=True (regression: _file_base was not initialised
    for the None branch)."""
    file = File(None, config={"UPLOAD_KEEP_FILENAME": True, "MAX_MEMORY_FILE_SIZE": 0})
    try:
        # This reaches the UPLOAD_DIR-is-None branch, which accesses self._ext
        # via the suffix assignment — previously an AttributeError.
        file.write(b"x")
    finally:
        file.close()


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
