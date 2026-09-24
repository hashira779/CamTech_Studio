"""
AI Thumbnail Generator for KMVM
Composes high-impact YouTube & social media thumbnails using song title,
artist name, cinematic framing, and authentic Khmer typography.
"""

import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from typing import List, Dict, Any, Optional

class ThumbnailGenerator:
    """Generates multiple visual thumbnail concepts for a music video."""

    def __init__(self, song_title: str, artist_name: str, background_image: Optional[str] = None):
        self.song_title = song_title or "ចម្រៀងខ្មែរ"
        self.artist_name = artist_name or "Official Music Video"
        self.background_image = background_image
        self.width = 1280
        self.height = 720

    def _load_font(self, size: int, bold: bool = True, text: str = ""):
        """Loads script-aware system font for thumbnail typography across all world languages."""
        script = "latin"
        if text:
            for c in text:
                code = ord(c)
                if 0x1780 <= code <= 0x17FF:
                    script = "khmer"
                    break
                if 0x3040 <= code <= 0x30FF:
                    script = "japanese"
                    break
                if 0x4E00 <= code <= 0x9FFF:
                    script = "chinese"
                    break
                if 0xAC00 <= code <= 0xD7AF or 0x1100 <= code <= 0x11FF:
                    script = "korean"
                    break
                if 0x0E00 <= code <= 0x0E7F:
                    script = "thai"
                    break
                if 0x0900 <= code <= 0x097F:
                    script = "hindi"
                    break
                if 0x0600 <= code <= 0x06FF:
                    script = "arabic"
                    break
                if 0x0400 <= code <= 0x04FF:
                    script = "cyrillic"
                    break

        font_map = {
            "khmer": [
                "C:\\Windows\\Fonts\\KhmerOSmuollight.ttf",
                "C:\\Windows\\Fonts\\KhmerOSbattambang.ttf",
                "C:\\Windows\\Fonts\\LeelaUIb.ttf" if bold else "C:\\Windows\\Fonts\\LeelawUI.ttf"
            ],
            "chinese": [
                "C:\\Windows\\Fonts\\simsunb.ttf" if bold else "C:\\Windows\\Fonts\\simsun.ttc",
                "C:\\Windows\\Fonts\\simsun.ttc"
            ],
            "japanese": [
                "C:\\Windows\\Fonts\\msgothic.ttc",
                "C:\\Windows\\Fonts\\simsun.ttc"
            ],
            "korean": [
                "C:\\Windows\\Fonts\\malgunbd.ttf" if bold else "C:\\Windows\\Fonts\\malgun.ttf"
            ],
            "thai": [
                "C:\\Windows\\Fonts\\LeelaUIb.ttf" if bold else "C:\\Windows\\Fonts\\LeelawUI.ttf",
                "C:\\Windows\\Fonts\\tahomabd.ttf" if bold else "C:\\Windows\\Fonts\\tahoma.ttf"
            ],
            "hindi": [
                "C:\\Windows\\Fonts\\Nirmala.ttc"
            ],
            "arabic": [
                "C:\\Windows\\Fonts\\segoeuib.ttf" if bold else "C:\\Windows\\Fonts\\segoeui.ttf",
                "C:\\Windows\\Fonts\\tahoma.ttf"
            ],
            "cyrillic": [
                "C:\\Windows\\Fonts\\segoeuib.ttf" if bold else "C:\\Windows\\Fonts\\segoeui.ttf",
                "C:\\Windows\\Fonts\\arialbd.ttf" if bold else "C:\\Windows\\Fonts\\arial.ttf"
            ],
            "latin": [
                "C:\\Windows\\Fonts\\segoeuib.ttf" if bold else "C:\\Windows\\Fonts\\segoeui.ttf",
                "C:\\Windows\\Fonts\\arialbd.ttf" if bold else "C:\\Windows\\Fonts\\arial.ttf"
            ]
        }

        candidates = list(font_map.get(script, font_map["latin"]))
        candidates.extend([
            "C:\\Windows\\Fonts\\segoeuib.ttf" if bold else "C:\\Windows\\Fonts\\segoeui.ttf",
            "C:\\Windows\\Fonts\\arialbd.ttf" if bold else "C:\\Windows\\Fonts\\arial.ttf"
        ])

        for p in candidates:
            if os.path.exists(p):
                try:
                    return ImageFont.truetype(p, size)
                except Exception:
                    continue
        return ImageFont.load_default()

    def generate_concepts(self, output_dir: str) -> List[str]:
        """Generates 3 distinct thumbnail design concepts and saves them as images."""
        os.makedirs(output_dir, exist_ok=True)
        concepts = []

        # Base background
        if self.background_image and os.path.exists(self.background_image):
            try:
                base_bg = Image.open(self.background_image).convert("RGB")
                base_bg = base_bg.resize((self.width, self.height), Image.Resampling.LANCZOS)
            except Exception:
                base_bg = None
        else:
            base_bg = None

        font_title = self._load_font(64, bold=True, text=self.song_title)
        font_sub = self._load_font(32, bold=False, text=self.artist_name)
        font_badge = self._load_font(20, bold=True, text="4K ULTRA HD")

        # Concept 1: Cinematic Gold
        c1 = base_bg.copy() if base_bg else Image.new("RGB", (self.width, self.height), (12, 14, 24))
        # Dark overlay
        overlay = Image.new("RGBA", (self.width, self.height), (8, 10, 18, 160))
        c1.paste(overlay, (0, 0), mask=overlay)
        draw = ImageDraw.Draw(c1)

        # Top Badge
        badge_box = [60, 60, 220, 95]
        draw.rounded_rectangle(badge_box, radius=6, fill=(218, 165, 32))
        draw.text((75, 68), "4K OFFICIAL", font=font_badge, fill=(10, 10, 10))

        # Title shadow + text
        title_y = 380
        draw.text((64, title_y + 4), self.song_title, font=font_title, fill=(0, 0, 0))
        draw.text((60, title_y), self.song_title, font=font_title, fill=(255, 220, 100))

        # Artist
        draw.text((62, title_y + 90), self.artist_name, font=font_sub, fill=(240, 240, 250))

        p1 = os.path.join(output_dir, "thumb_concept_1.jpg")
        c1.save(p1, quality=95)
        concepts.append(p1)

        # Concept 2: Cyber Neon
        c2 = base_bg.copy() if base_bg else Image.new("RGB", (self.width, self.height), (8, 8, 16))
        c2 = c2.filter(ImageFilter.GaussianBlur(8))
        draw2 = ImageDraw.Draw(c2)

        # Center gradient glow
        draw2.rectangle([0, 0, self.width, self.height], fill=None, outline=(0, 240, 255), width=10)
        draw2.text((60, 260), self.song_title, font=font_title, fill=(0, 240, 255))
        draw2.text((60, 360), f"NEW RELEASE • {self.artist_name}", font=font_sub, fill=(255, 0, 128))

        p2 = os.path.join(output_dir, "thumb_concept_2.jpg")
        c2.save(p2, quality=95)
        concepts.append(p2)

        # Concept 3: Royal Khmer Elegant
        c3 = base_bg.copy() if base_bg else Image.new("RGB", (self.width, self.height), (20, 12, 14))
        draw3 = ImageDraw.Draw(c3)
        # Gold framing lines
        draw3.rectangle([40, 40, self.width - 40, self.height - 40], outline=(200, 150, 40), width=3)
        draw3.text((self.width // 2, 320), self.song_title, font=font_title, fill=(255, 255, 255), anchor="mm")
        draw3.text((self.width // 2, 410), self.artist_name, font=font_sub, fill=(218, 165, 32), anchor="mm")

        p3 = os.path.join(output_dir, "thumb_concept_3.jpg")
        c3.save(p3, quality=95)
        concepts.append(p3)

        return concepts
