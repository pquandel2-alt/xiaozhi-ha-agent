"""Pure-Python Ogg Opus muxer.

Wraps raw Opus packets (as delivered by the XiaoZhi WebSocket protocol) into a
valid Ogg Opus container so Home Assistant / browsers / media players can play
them directly — without needing libopus or ffmpeg.

XiaoZhi sends TTS audio as raw Opus packets: 24 kHz, mono, 60 ms frames.
Ogg granule positions are ALWAYS counted in 48 kHz samples, so a 60 ms frame
advances the granule by 0.06 * 48000 = 2880 samples.
"""

import struct
import random

# Ogg uses CRC-32 with polynomial 0x04C11DB7, no reflection, init 0, no final xor.
_CRC_POLY = 0x04C11DB7


def _build_crc_table() -> list[int]:
    table = []
    for i in range(256):
        r = i << 24
        for _ in range(8):
            if r & 0x80000000:
                r = ((r << 1) ^ _CRC_POLY) & 0xFFFFFFFF
            else:
                r = (r << 1) & 0xFFFFFFFF
        table.append(r)
    return table


_CRC_TABLE = _build_crc_table()


def _ogg_crc(data: bytes) -> int:
    crc = 0
    for b in data:
        crc = ((crc << 8) & 0xFFFFFFFF) ^ _CRC_TABLE[((crc >> 24) & 0xFF) ^ b]
    return crc


def _build_page(serial: int, seq: int, granule: int, header_type: int, packets: list[bytes]) -> bytes:
    """Build a single Ogg page. Each packet becomes one or more lacing segments."""
    segtable = bytearray()
    body = bytearray()
    for p in packets:
        length = len(p)
        while length >= 255:
            segtable.append(255)
            length -= 255
        segtable.append(length)  # final lacing value (may be 0)
        body += p

    if len(segtable) > 255:
        raise ValueError("too many segments for a single Ogg page")

    header = bytearray()
    header += b"OggS"
    header.append(0)                     # stream structure version
    header.append(header_type)           # 0x02 BOS, 0x04 EOS, 0x00 normal
    header += struct.pack("<q", granule)  # granule position (48 kHz samples)
    header += struct.pack("<I", serial)
    header += struct.pack("<I", seq)
    header += struct.pack("<I", 0)        # CRC placeholder
    header.append(len(segtable))
    header += segtable

    page = bytes(header) + bytes(body)
    crc = _ogg_crc(page)
    # CRC field sits at byte offset 22..26
    return page[:22] + struct.pack("<I", crc) + page[26:]


def frames_to_ogg(
    frames: list[bytes],
    sample_rate: int = 24000,
    channels: int = 1,
    pre_skip: int = 3840,
) -> bytes | None:
    """Wrap raw Opus packets into an Ogg Opus stream. Returns None if no frames."""
    if not frames:
        return None

    serial = random.randint(1, 0x7FFFFFFF)
    out = bytearray()
    seq = 0

    # --- OpusHead identification header (BOS page) ---
    opus_head = (
        b"OpusHead"
        + bytes([1, channels])            # version 1, channel count
        + struct.pack("<H", pre_skip)     # pre-skip
        + struct.pack("<I", sample_rate)  # original input sample rate (informational)
        + struct.pack("<H", 0)            # output gain
        + bytes([0])                      # channel mapping family 0
    )
    out += _build_page(serial, seq, 0, 0x02, [opus_head])
    seq += 1

    # --- OpusTags comment header ---
    vendor = b"xiaozhi-ha-agent"
    opus_tags = (
        b"OpusTags"
        + struct.pack("<I", len(vendor))
        + vendor
        + struct.pack("<I", 0)  # zero user comments
    )
    out += _build_page(serial, seq, 0, 0x00, [opus_tags])
    seq += 1

    # --- Audio data pages (one Opus packet per page for simplicity) ---
    granule = 0
    samples_per_frame = 2880  # 60 ms at 48 kHz granule units
    n = len(frames)
    for i, frame in enumerate(frames):
        granule += samples_per_frame
        header_type = 0x04 if i == n - 1 else 0x00  # EOS on last page
        out += _build_page(serial, seq, granule, header_type, [frame])
        seq += 1

    return bytes(out)
