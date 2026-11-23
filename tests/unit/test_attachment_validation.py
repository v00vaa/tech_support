"""Content-based validation tests for private message attachments."""

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from app.web.routes import _detect_attachment_content_type


@pytest.mark.parametrize(
    ("filename", "payload", "expected"),
    [
        ("photo.jpg", bytes.fromhex("FFD8FF") + b"image-data", "image/jpeg"),
        ("photo.png", bytes.fromhex("89504E470D0A1A0A") + b"image-data", "image/png"),
        ("animation.gif", b"GIF89a" + b"image-data", "image/gif"),
        ("photo.webp", b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"image-data", "image/webp"),
        ("document.pdf", b"%PDF-1.7\nbody", "application/pdf"),
        ("notes.txt", b"Hello, support!\n", "text/plain"),
        ("table.csv", "name;value\nitem;42\n".encode(), "text/csv"),
        ("archive.zip", b"PK\x03\x04" + b"archive", "application/zip"),
        (
            "legacy.doc",
            bytes.fromhex("D0CF11E0A1B11AE1") + b"legacy-office",
            "application/msword",
        ),
        (
            "legacy.xls",
            bytes.fromhex("D0CF11E0A1B11AE1") + b"legacy-office",
            "application/vnd.ms-excel",
        ),
    ],
)
def test_detect_attachment_content_type_accepts_matching_signatures(
    filename: str,
    payload: bytes,
    expected: str,
) -> None:
    if filename == "archive.zip":
        buffer = BytesIO()
        with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
            archive.writestr("readme.txt", "archive")
        payload = buffer.getvalue()

    assert _detect_attachment_content_type(filename, payload) == expected


@pytest.mark.parametrize(
    ("filename", "payload"),
    [
        ("fake.png", b"not an image"),
        ("fake.pdf", b"<html>not a PDF</html>"),
        ("fake.jpg", b"GIF89a"),
        ("fake.zip", b"PK but not a valid archive"),
        ("fake.docx", b"PK but not a valid Office document"),
        ("fake.xlsx", b"PK but not a valid spreadsheet"),
        ("binary.txt", b"hello\x00world"),
        ("binary.csv", b"\xff\xfe\x00"),
    ],
)
def test_detect_attachment_content_type_rejects_mismatched_content(
    filename: str,
    payload: bytes,
) -> None:
    with pytest.raises(ValueError, match="не соответствует"):
        _detect_attachment_content_type(filename, payload)


def test_detect_attachment_content_type_checks_office_archive_structure() -> None:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("word/document.xml", "<document />")

    assert (
        _detect_attachment_content_type("report.docx", buffer.getvalue())
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    with pytest.raises(ValueError, match="не соответствует"):
        _detect_attachment_content_type("report.xlsx", buffer.getvalue())
