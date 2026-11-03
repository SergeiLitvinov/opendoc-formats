"""Combine straight PDF image samples and a soft mask without alpha roundoff."""

from __future__ import annotations

import struct
import zlib

from opendoc_formats.errors import ResourceLimitError


def straight_alpha_png(image: bytes, mask: bytes) -> bytes:
    import fitz

    base, alpha = fitz.Pixmap(image), fitz.Pixmap(mask)
    if base.colorspace != fitz.csRGB:
        base = fitz.Pixmap(fitz.csRGB, base)
    if (base.n != 3 or alpha.n != 1 or base.width != alpha.width or base.height != alpha.height
            or min(base.width, base.height) <= 0):
        raise ValueError('Unsupported PDF image soft-mask sample profile')
    pixels, opacity = base.samples_mv, alpha.samples_mv
    compressor = zlib.compressobj()
    encoded = []
    length = 0
    for row in range(base.height):
        rgb = pixels[row * base.stride:row * base.stride + base.width * 3]
        scanline = bytearray(base.width * 4 + 1)  # PNG filter 0, straight RGBA.
        scanline[1::4], scanline[2::4], scanline[3::4] = rgb[0::3], rgb[1::3], rgb[2::3]
        scanline[4::4] = opacity[row * alpha.stride:row * alpha.stride + alpha.width]
        data = compressor.compress(scanline)
        encoded.append(data)
        length += len(data)
        if length > 32 * 1024 * 1024:
            raise ResourceLimitError('PDF raster with mask exceeds 32 MiB')
    encoded.append(compressor.flush())

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))

    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>2I5B', base.width, base.height, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', b''.join(encoded)) + chunk(b'IEND', b''))
