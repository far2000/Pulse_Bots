"""Image processing — resize, strip EXIF, convert to WebP, build thumbnails.

Heavy Pillow operations are CPU-bound; we run them in a thread executor so we
never block the asyncio event loop driving Telethon/aiogram.
"""

from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass

from PIL import Image, ImageOps


@dataclass(slots=True)
class ProcessedImage:
    full_bytes: bytes
    full_mime: str
    full_ext: str
    width: int
    height: int
    thumb_bytes: bytes
    thumb_mime: str
    thumb_ext: str


class ImageProcessor:
    def __init__(
        self,
        *,
        max_side: int = 1920,
        thumbnail_side: int = 400,
        quality: int = 85,
    ) -> None:
        self.max_side = max_side
        self.thumbnail_side = thumbnail_side
        self.quality = quality

    async def process(self, raw: bytes) -> ProcessedImage:
        """Resize + WebP encode in a worker thread."""
        return await asyncio.to_thread(self._process_sync, raw)

    def _process_sync(self, raw: bytes) -> ProcessedImage:
        with Image.open(io.BytesIO(raw)) as img:
            # Respect EXIF orientation before stripping EXIF.
            img = ImageOps.exif_transpose(img)
            # Drop EXIF: re-load without metadata.
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGB")

            # Full-size (downscale only).
            full = img.copy()
            full.thumbnail((self.max_side, self.max_side), Image.Resampling.LANCZOS)
            full_buf = io.BytesIO()
            full.save(full_buf, format="WEBP", quality=self.quality, method=6)
            full_bytes = full_buf.getvalue()

            # Thumbnail.
            thumb = img.copy()
            thumb.thumbnail(
                (self.thumbnail_side, self.thumbnail_side), Image.Resampling.LANCZOS
            )
            thumb_buf = io.BytesIO()
            thumb.save(thumb_buf, format="WEBP", quality=80, method=6)
            thumb_bytes = thumb_buf.getvalue()

            return ProcessedImage(
                full_bytes=full_bytes,
                full_mime="image/webp",
                full_ext="webp",
                width=full.width,
                height=full.height,
                thumb_bytes=thumb_bytes,
                thumb_mime="image/webp",
                thumb_ext="webp",
            )
