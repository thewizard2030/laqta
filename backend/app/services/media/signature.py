"""File signature (magic byte) validation for media assets.

Extensions alone can be easily forged, renamed, or disguised.
This module verifies that the binary contents begin with legitimate
media container headers before invoking parser subprocesses.
"""

# ISO Base Media File Format box signatures (MP4, MOV)
_ISOBMFF_BOXES = {b"ftyp", b"moov", b"mdat", b"wide", b"skip"}

# EBML header magic bytes (Matroska / WebM)
_EBML_MAGIC = b"\x1a\x45\xdf\xa3"


def validate_media_signature(header_bytes: bytes) -> tuple[bool, str, str]:
    """Validate initial file bytes against known video container signatures.

    Args:
        header_bytes: First 32 to 512 bytes of the uploaded file.

    Returns:
        tuple (is_valid, detected_format, explanation)
    """
    if len(header_bytes) < 12:
        return (
            False,
            "insufficient_data",
            "File header is truncated (fewer than 12 bytes). Not a valid media file.",
        )

    # 1. Check for Matroska / WebM (EBML header)
    if header_bytes.startswith(_EBML_MAGIC):
        return (
            True,
            "ebml_matroska_webm",
            "Verified EBML container header (MKV / WebM format).",
        )

    # 2. Check for ISO-BMFF / MP4 / QuickTime (MOV)
    # Box structure: 4 bytes length + 4 bytes box type (e.g. 'ftyp', 'moov', 'mdat')
    box_type = header_bytes[4:8]
    if box_type in _ISOBMFF_BOXES:
        return (
            True,
            "isobmff_mp4_mov",
            f"Verified ISO-BMFF container box '{box_type.decode('ascii', errors='replace')}'.",
        )

    # 3. QuickTime classic alternate start
    if header_bytes[0:4] in {b"moov", b"mdat", b"wide"}:
        return (
            True,
            "quicktime_mov",
            "Verified QuickTime header.",
        )

    return (
        False,
        "unknown_or_fake",
        "File signature does not match an allowable video container (MP4, MOV, MKV, WebM). "
        "File extensions can be trivially renamed or spoofed, "
        "so binary headers are strictly verified.",
    )
