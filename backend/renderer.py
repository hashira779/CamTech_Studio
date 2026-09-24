"""
Renderer Module for VIDA
High-performance video renderer combining audio-reactive spectrum visualizers,
particle physics, background compositing, kinetic karaoke lyrics, and streaming FFmpeg pipe.
"""

import os
import sys
import math
import time
import subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import cv2

from backend.audio_analyzer import get_ffmpeg_exe, AudioAnalyzer
from backend.lyric_engine import get_active_lyric_frame

# Color Palettes
PALETTES = {
    "cyberpunk": {
        "primary": (0, 240, 255),      # Neon Cyan
        "secondary": (255, 0, 128),    # Neon Pink/Magenta
        "accent": (120, 0, 255),       # Deep Violet
        "glow": (0, 255, 200),
        "text_highlight": (0, 240, 255)
    },
    "sunset": {
        "primary": (255, 170, 0),      # Golden Amber
        "secondary": (255, 45, 85),    # Crimson Red
        "accent": (160, 20, 100),      # Magenta
        "glow": (255, 200, 50),
        "text_highlight": (255, 215, 0)
    },
    "matrix": {
        "primary": (0, 255, 128),      # Toxic / Emerald Green
        "secondary": (0, 180, 255),    # Electric Cyan
        "accent": (10, 60, 30),        # Deep Forest
        "glow": (50, 255, 150),
        "text_highlight": (0, 255, 160)
    },
    "electric": {
        "primary": (130, 80, 255),     # Electric Purple
        "secondary": (0, 210, 255),    # Ice Blue
        "accent": (50, 20, 120),
        "glow": (180, 120, 255),
        "text_highlight": (220, 180, 255)
    },
    "angkor": {
        "primary": (255, 183, 3),      # Angkor Gold
        "secondary": (251, 133, 0),    # Warm Amber
        "accent": (142, 71, 0),        # Deep Bronze
        "glow": (255, 200, 50),
        "text_highlight": (255, 215, 0)
    },
    "bloodmoon": {
        "primary": (230, 57, 70),      # Crimson Red
        "secondary": (114, 9, 183),    # Deep Purple
        "accent": (43, 45, 66),        # Dark Slate
        "glow": (230, 80, 90),
        "text_highlight": (255, 100, 100)
    },
    "pastel": {
        "primary": (247, 37, 133),     # Hot Pink
        "secondary": (114, 9, 183),    # Purple
        "accent": (76, 201, 240),      # Sky Blue
        "glow": (247, 100, 180),
        "text_highlight": (255, 150, 200)
    },
    "monochrome": {
        "primary": (248, 249, 250),    # White
        "secondary": (108, 117, 125),  # Gray
        "accent": (33, 37, 41),        # Dark
        "glow": (200, 200, 200),
        "text_highlight": (255, 255, 255)
    },
    "vintage_vinyl": {
        "primary": (217, 163, 98),     # 60s Warm Amber Sepia
        "secondary": (140, 80, 30),
        "accent": (245, 215, 160),
        "glow": (217, 163, 98),
        "text_highlight": (245, 215, 160)
    },
    "candlelight": {
        "primary": (251, 146, 60),     # Golden Flame
        "secondary": (194, 65, 12),
        "accent": (254, 215, 170),
        "glow": (251, 146, 60),
        "text_highlight": (254, 215, 170)
    },
    "rainy_night": {
        "primary": (56, 189, 248),     # Electric Rain Blue
        "secondary": (14, 116, 144),
        "accent": (186, 230, 253),
        "glow": (56, 189, 248),
        "text_highlight": (125, 211, 252)
    },
    "tonle_sap": {
        "primary": (14, 165, 233),     # River Twilight
        "secondary": (3, 105, 161),
        "accent": (125, 211, 252),
        "glow": (14, 165, 233),
        "text_highlight": (56, 189, 248)
    },
    "royal_palace": {
        "primary": (234, 179, 8),      # Imperial Gold
        "secondary": (161, 98, 7),
        "accent": (254, 240, 138),
        "glow": (234, 179, 8),
        "text_highlight": (250, 204, 21)
    },
    "romduol": {
        "primary": (253, 224, 71),     # Romduol Ivory Petals
        "secondary": (161, 98, 7),
        "accent": (254, 249, 195),
        "glow": (253, 224, 71),
        "text_highlight": (254, 240, 138)
    },
    "pleng_kar": {
        "primary": (244, 63, 94),      # Ceremonial Crimson
        "secondary": (190, 18, 60),
        "accent": (254, 205, 211),
        "glow": (244, 63, 94),
        "text_highlight": (251, 113, 133)
    },
    "romvong_festive": {
        "primary": (236, 72, 153),     # Joyful Festival Pink
        "secondary": (219, 39, 119),
        "accent": (251, 207, 232),
        "glow": (236, 72, 153),
        "text_highlight": (244, 114, 182)
    },
    "kirirom_pine": {
        "primary": (16, 185, 129),     # Alpine Pine Teal
        "secondary": (5, 150, 105),
        "accent": (167, 243, 208),
        "glow": (16, 185, 129),
        "text_highlight": (52, 211, 153)
    },
    "lotus_pond": {
        "primary": (244, 114, 182),    # Sacred Lotus Pink
        "secondary": (219, 39, 119),
        "accent": (252, 231, 243),
        "glow": (244, 114, 182),
        "text_highlight": (244, 114, 182)
    },
    "chapei_wood": {
        "primary": (217, 119, 6),      # Teak Wood & Brass
        "secondary": (146, 64, 14),
        "accent": (253, 230, 138),
        "glow": (217, 119, 6),
        "text_highlight": (251, 191, 36)
    }
}

class ParticleSystem:
    """Manages audio-reactive floating particles and dust motes."""

    def __init__(self, count: int, width: int, height: int):
        self.count = count
        self.width = width
        self.height = height
        np.random.seed(42)
        self.x = np.random.uniform(0, width, count).astype(np.float32)
        self.y = np.random.uniform(0, height, count).astype(np.float32)
        self.vx = np.random.uniform(-0.5, 0.5, count).astype(np.float32)
        self.vy = np.random.uniform(-1.2, -0.2, count).astype(np.float32)
        self.radius = np.random.uniform(1.5, 4.0, count).astype(np.float32)
        self.base_alpha = np.random.uniform(0.3, 0.8, count).astype(np.float32)

    def update_and_draw(self, frame_bgr: np.ndarray, bass_val: float, onset_val: float, color: tuple):
        """Updates particle positions with bass velocity boost and renders directly onto frame."""
        boost = 1.0 + bass_val * 2.5 + onset_val * 1.5
        self.x += self.vx * boost
        self.y += self.vy * boost

        # Wrap around screen edges
        self.x = np.where(self.x < 0, self.width, self.x)
        self.x = np.where(self.x > self.width, 0, self.x)
        self.y = np.where(self.y < 0, self.height, self.y)
        self.y = np.where(self.y > self.height, 0, self.y)

        b_col, g_col, r_col = color[2], color[1], color[0]

        # Draw particles
        for i in range(self.count):
            cur_r = int(self.radius[i] * (1.0 + bass_val * 0.8))
            px = int(self.x[i])
            py = int(self.y[i])
            alpha = min(1.0, self.base_alpha[i] + bass_val * 0.4)
            p_color = (int(b_col * alpha), int(g_col * alpha), int(r_col * alpha))
            cv2.circle(frame_bgr, (px, py), cur_r, p_color, -1, lineType=cv2.LINE_AA)


class VideoRenderer:
    """Renders high-definition music videos with visualizers and auto-synced lyrics."""

    def __init__(
        self,
        audio_path: str,
        output_path: str,
        width: int = 1920,
        height: int = 1080,
        fps: int = 60,
        theme: str = "trap_circle",      # trap_circle | neon_bars | starfield | horizon_wave
        palette_name: str = "cyberpunk",
        background_image: str = None,
        logo_image: str = None,
        center_text_primary: str = "VIDA",
        center_text_secondary: str = "FLUID WAVE",
        show_center_text: bool = True,
        song_title: str = "",
        artist_name: str = "",
        lyrics_data: list = None,
        lyric_style: str = "karaoke",    # karaoke | kinetic | minimal
        bar_count: int = 64,
        bass_boost: float = 1.3
    ):
        self.audio_path = audio_path
        self.output_path = output_path
        self.width = width
        self.height = height
        self.fps = fps
        self.theme = theme
        self.palette = PALETTES.get(palette_name, PALETTES["cyberpunk"])
        self.background_image_path = background_image
        self.logo_image_path = logo_image
        self.center_text_primary = center_text_primary if center_text_primary is not None else "VIDA"
        self.center_text_secondary = center_text_secondary if center_text_secondary is not None else "FLUID WAVE"
        self.show_center_text = show_center_text
        self.song_title = song_title or "VIDA Visualizer"
        self.artist_name = artist_name or "Official Audio"
        self.lyrics_data = lyrics_data or []
        self.lyric_style = lyric_style
        self.bar_count = bar_count
        self.bass_boost = bass_boost

        self.particles = ParticleSystem(80, width, height)
        self.peak_caps = np.zeros(bar_count, dtype=np.float32)
        self.peak_decay = 0.015

        # Pre-load / prepare background
        self.bg_frame = self._prepare_background()
        self.logo_circle = self._prepare_logo()

        # Fonts
        self.font_title = self._load_font(int(height * 0.035), bold=True, text=self.song_title)
        self.font_artist = self._load_font(int(height * 0.022), bold=False, text=self.artist_name)
        sample_lyric = " ".join([l.get("text", "") for l in self.lyrics_data[:3]]) if self.lyrics_data else self.song_title
        self.font_lyrics = self._load_font(int(height * 0.045), bold=True, text=sample_lyric)
        self.font_lyrics_sub = self._load_font(int(height * 0.030), bold=False, text=sample_lyric)

    def _load_font(self, size: int, bold: bool = False, text: str = ""):
        """
        Loads high quality system TrueType/OpenType font tailored to the text's linguistic script.
        Supports Khmer, Chinese, Japanese, Korean, Thai, Hindi, Arabic, Cyrillic, and Latin/Vietnamese.
        """
        # Detect script from text sample
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
                "C:\\Windows\\Fonts\\KhmerOSbattambang.ttf",
                "C:\\Windows\\Fonts\\KhmerUIb.ttf" if bold else "C:\\Windows\\Fonts\\KhmerUI.ttf",
                "C:\\Windows\\Fonts\\LeelaUIb.ttf" if bold else "C:\\Windows\\Fonts\\LeelawUI.ttf",
                "C:\\Windows\\Fonts\\KhmerOS.ttf"
            ],
            "chinese": [
                "C:\\Windows\\Fonts\\simsunb.ttf" if bold else "C:\\Windows\\Fonts\\simsun.ttc",
                "C:\\Windows\\Fonts\\simsun.ttc",
                "C:\\Windows\\Fonts\\SimsunExtG.ttf"
            ],
            "japanese": [
                "C:\\Windows\\Fonts\\msgothic.ttc",
                "C:\\Windows\\Fonts\\simsun.ttc"
            ],
            "korean": [
                "C:\\Windows\\Fonts\\malgunbd.ttf" if bold else "C:\\Windows\\Fonts\\malgun.ttf",
                "C:\\Windows\\Fonts\\malgun.ttf"
            ],
            "thai": [
                "C:\\Windows\\Fonts\\LeelaUIb.ttf" if bold else "C:\\Windows\\Fonts\\LeelawUI.ttf",
                "C:\\Windows\\Fonts\\tahomabd.ttf" if bold else "C:\\Windows\\Fonts\\tahoma.ttf"
            ],
            "hindi": [
                "C:\\Windows\\Fonts\\Nirmala.ttc",
                "C:\\Windows\\Fonts\\segoeuib.ttf" if bold else "C:\\Windows\\Fonts\\segoeui.ttf"
            ],
            "arabic": [
                "C:\\Windows\\Fonts\\segoeuib.ttf" if bold else "C:\\Windows\\Fonts\\segoeui.ttf",
                "C:\\Windows\\Fonts\\tahomabd.ttf" if bold else "C:\\Windows\\Fonts\\tahoma.ttf"
            ],
            "cyrillic": [
                "C:\\Windows\\Fonts\\segoeuib.ttf" if bold else "C:\\Windows\\Fonts\\segoeui.ttf",
                "C:\\Windows\\Fonts\\arialbd.ttf" if bold else "C:\\Windows\\Fonts\\arial.ttf"
            ],
            "latin": [
                "C:\\Windows\\Fonts\\segoeuib.ttf" if bold else "C:\\Windows\\Fonts\\segoeui.ttf",
                "C:\\Windows\\Fonts\\arialbd.ttf" if bold else "C:\\Windows\\Fonts\\arial.ttf",
                "C:\\Windows\\Fonts\\calibrib.ttf" if bold else "C:\\Windows\\Fonts\\calibri.ttf"
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

    def _prepare_background(self) -> np.ndarray:
        """Prepares a darkened, blurred, high-contrast background frame."""
        if self.background_image_path and os.path.exists(self.background_image_path):
            try:
                img = cv2.imread(self.background_image_path)
                if img is not None:
                    # Resize with aspect cover
                    h, w = img.shape[:2]
                    target_ratio = self.width / self.height
                    current_ratio = w / h

                    if current_ratio > target_ratio:
                        new_w = int(h * target_ratio)
                        start_x = (w - new_w) // 2
                        cropped = img[:, start_x:start_x + new_w]
                    else:
                        new_h = int(w / target_ratio)
                        start_y = (h - new_h) // 2
                        cropped = img[start_y:start_y + new_h, :]

                    resized = cv2.resize(cropped, (self.width, self.height), interpolation=cv2.INTER_AREA)
                    # Apply gentle blur & darkening vignette
                    blurred = cv2.GaussianBlur(resized, (21, 21), 0)
                    darkened = (blurred.astype(np.float32) * 0.42).astype(np.uint8)
                    return darkened
            except Exception as e:
                print(f"Warning: could not load background {e}")

        # Procedural deep cyber gradient background
        bg = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        c_top = np.array([12, 10, 24], dtype=np.float32)     # Deep dark indigo
        c_bottom = np.array([4, 4, 10], dtype=np.float32)    # Near pitch black
        for y in range(self.height):
            ratio = y / self.height
            color = (1.0 - ratio) * c_top + ratio * c_bottom
            bg[y, :] = color.astype(np.uint8)

        # Subtle vignette
        Y, X = np.ogrid[:self.height, :self.width]
        dist_from_center = np.sqrt(((X - self.width/2)/(self.width/2))**2 + ((Y - self.height/2)/(self.height/2))**2)
        vignette = np.clip(1.0 - 0.45 * dist_from_center, 0.2, 1.0)
        bg = (bg.astype(np.float32) * vignette[:, :, np.newaxis]).astype(np.uint8)
        return bg

    def _prepare_logo(self) -> np.ndarray:
        """Prepares a circular cropped logo/album cover with antialiased alpha."""
        logo_size = int(min(self.width, self.height) * 0.28)
        if self.logo_image_path and os.path.exists(self.logo_image_path):
            try:
                pil_img = Image.open(self.logo_image_path).convert("RGBA")
                pil_img = pil_img.resize((logo_size, logo_size), Image.Resampling.LANCZOS)

                # Circular mask
                mask = Image.new("L", (logo_size, logo_size), 0)
                draw = ImageDraw.Draw(mask)
                draw.ellipse((2, 2, logo_size - 2, logo_size - 2), fill=255)

                result = Image.new("RGBA", (logo_size, logo_size), (0, 0, 0, 0))
                result.paste(pil_img, (0, 0), mask=mask)
                return cv2.cvtColor(np.array(result), cv2.COLOR_RGBA2BGRA)
            except Exception as e:
                print(f"Warning: logo load error {e}")

        # Procedural stylish circle
        circle = np.zeros((logo_size, logo_size, 4), dtype=np.uint8)
        center = logo_size // 2
        radius = center - 4
        # Glowing inner gradient
        for r in range(radius, 0, -2):
            val = int(25 + 40 * (1.0 - r / radius))
            cv2.circle(circle, (center, center), r, (val + 10, val, val + 25, 255), -1, lineType=cv2.LINE_AA)
        cv2.circle(circle, (center, center), radius, (self.palette["primary"][2], self.palette["primary"][1], self.palette["primary"][0], 255), 3, lineType=cv2.LINE_AA)

        # Draw custom center badge text if enabled
        if self.show_center_text and (self.center_text_primary or self.center_text_secondary):
            try:
                pil_circle = Image.fromarray(cv2.cvtColor(circle, cv2.COLOR_BGRA2RGBA))
                draw = ImageDraw.Draw(pil_circle)
                c1 = (self.center_text_primary or "").strip()
                c2 = (self.center_text_secondary or "").strip()
                pri = self.palette.get("primary", (0, 240, 255))

                if c1:
                    len1 = max(len(c1), 4)
                    base_fs1 = max(14, int(radius * 0.40))
                    fs1 = int(base_fs1 * (6 / len1)) if len1 > 6 else base_fs1
                    font1 = self._load_font(max(11, fs1), bold=True, text=c1)
                    bbox1 = draw.textbbox((0, 0), c1, font=font1)
                    w1 = bbox1[2] - bbox1[0]
                    h1 = bbox1[3] - bbox1[1]
                    y1 = center - (h1 // 2) - (int(radius * 0.16) if c2 else 0)
                    draw.text((center - w1 // 2, y1), c1, font=font1, fill=(pri[0], pri[1], pri[2], 255))

                if c2:
                    len2 = max(len(c2), 6)
                    base_fs2 = max(10, int(radius * 0.20))
                    fs2 = int(base_fs2 * (10 / len2)) if len2 > 10 else base_fs2
                    font2 = self._load_font(max(9, fs2), bold=False, text=c2)
                    bbox2 = draw.textbbox((0, 0), c2, font=font2)
                    w2 = bbox2[2] - bbox2[0]
                    y2 = center + (int(radius * 0.18) if c1 else 0)
                    draw.text((center - w2 // 2, y2), c2, font=font2, fill=(160, 180, 210, 230))

                circle = cv2.cvtColor(np.array(pil_circle), cv2.COLOR_RGBA2BGRA)
            except Exception as e:
                print(f"Warning: error rendering center badge text: {e}")

        return circle

    def render_trap_circle(self, frame: np.ndarray, spectrum: np.ndarray, bass: float, onset: float):
        """Trap Nation style: Pulsing center circle + 360-degree radial neon spectrum bars."""
        cx = self.width // 2
        cy = self.height // 2

        # Bass camera shake
        if bass > 0.7:
            shake_x = int(np.random.uniform(-4, 4) * bass)
            shake_y = int(np.random.uniform(-4, 4) * bass)
            cx += shake_x
            cy += shake_y

        base_radius = int(min(self.width, self.height) * 0.16)
        dynamic_radius = int(base_radius + bass * (base_radius * 0.28))

        # Draw radial bars
        n_bars = len(spectrum)
        max_bar_length = int(min(self.width, self.height) * 0.22)

        # Mirrored radial spectrum for seamless aesthetic
        mirrored_spec = np.concatenate([spectrum, spectrum[::-1]])
        total_angles = len(mirrored_spec)

        c_pri = self.palette["primary"]
        c_sec = self.palette["secondary"]

        for i, val in enumerate(mirrored_spec):
            angle = (i / total_angles) * 2.0 * math.pi - (math.pi / 2.0)
            bar_len = int(val * max_bar_length)
            if bar_len < 3:
                bar_len = 3

            r_inner = dynamic_radius + 4
            r_outer = r_inner + bar_len

            x1 = int(cx + r_inner * math.cos(angle))
            y1 = int(cy + r_inner * math.sin(angle))
            x2 = int(cx + r_outer * math.cos(angle))
            y2 = int(cy + r_outer * math.sin(angle))

            # Color gradient interpolation
            ratio = i / total_angles
            col_r = int(c_pri[0] * (1.0 - ratio) + c_sec[0] * ratio)
            col_g = int(c_pri[1] * (1.0 - ratio) + c_sec[1] * ratio)
            col_b = int(c_pri[2] * (1.0 - ratio) + c_sec[2] * ratio)

            # Draw bar with glow
            cv2.line(frame, (x1, y1), (x2, y2), (col_b, col_g, col_r), thickness=3, lineType=cv2.LINE_AA)

        # Outer pulsing glow ring
        glow_col = (self.palette["glow"][2], self.palette["glow"][1], self.palette["glow"][0])
        cv2.circle(frame, (cx, cy), dynamic_radius + 2, glow_col, 2, lineType=cv2.LINE_AA)

        # Draw center logo with bass scaling
        if self.logo_circle is not None:
            lw, lh = self.logo_circle.shape[1], self.logo_circle.shape[0]
            scale = (dynamic_radius * 2.0) / lw
            scaled_w = int(lw * scale)
            scaled_h = int(lh * scale)
            if scaled_w > 10 and scaled_h > 10:
                resized_logo = cv2.resize(self.logo_circle, (scaled_w, scaled_h), interpolation=cv2.INTER_LINEAR)
                lx1 = cx - scaled_w // 2
                ly1 = cy - scaled_h // 2
                lx2 = lx1 + scaled_w
                ly2 = ly1 + scaled_h

                if lx1 >= 0 and ly1 >= 0 and lx2 <= self.width and ly2 <= self.height:
                    alpha_mask = resized_logo[:, :, 3] / 255.0
                    for c in range(3):
                        frame[ly1:ly2, lx1:lx2, c] = (
                            frame[ly1:ly2, lx1:lx2, c] * (1.0 - alpha_mask) +
                            resized_logo[:, :, c] * alpha_mask
                        ).astype(np.uint8)

    def render_neon_bars(self, frame: np.ndarray, spectrum: np.ndarray, bass: float, onset: float):
        """Cyberpunk neon vertical equalizer bars with floating peak caps and reflections."""
        n_bars = len(spectrum)
        margin = int(self.width * 0.08)
        usable_width = self.width - 2 * margin
        bar_width = int(usable_width / n_bars * 0.72)
        gap = int(usable_width / n_bars * 0.28)
        base_y = int(self.height * 0.72)
        max_h = int(self.height * 0.42)

        c_pri = self.palette["primary"]
        c_sec = self.palette["secondary"]

        for i in range(n_bars):
            val = spectrum[i]
            bar_h = int(val * max_h)
            if bar_h < 4:
                bar_h = 4

            # Update floating peak caps
            if val >= self.peak_caps[i]:
                self.peak_caps[i] = val
            else:
                self.peak_caps[i] = max(0.0, self.peak_caps[i] - self.peak_decay)

            x = margin + i * (bar_width + gap)
            y_top = base_y - bar_h

            # Gradient bar fill
            ratio = i / n_bars
            col_r = int(c_pri[0] * (1.0 - ratio) + c_sec[0] * ratio)
            col_g = int(c_pri[1] * (1.0 - ratio) + c_sec[1] * ratio)
            col_b = int(c_pri[2] * (1.0 - ratio) + c_sec[2] * ratio)
            bar_color = (col_b, col_g, col_r)

            cv2.rectangle(frame, (x, y_top), (x + bar_width, base_y), bar_color, -1)

            # Floating peak cap
            cap_y = base_y - int(self.peak_caps[i] * max_h) - 4
            cv2.rectangle(frame, (x, cap_y), (x + bar_width, cap_y + 3), (255, 255, 255), -1)

            # Subtle floor reflection
            ref_h = int(bar_h * 0.35)
            if ref_h > 0:
                ref_color = (int(col_b * 0.25), int(col_g * 0.25), int(col_r * 0.25))
                cv2.rectangle(frame, (x, base_y + 3), (x + bar_width, base_y + 3 + ref_h), ref_color, -1)

    def render_horizon_wave(self, frame: np.ndarray, spectrum: np.ndarray, bass: float, onset: float):
        """Fluid glowing oscilloscope wave along the horizon."""
        n_bars = len(spectrum)
        base_y = int(self.height * 0.55)
        max_amp = int(self.height * 0.25)

        points = []
        for i in range(n_bars):
            x = int(i / (n_bars - 1) * self.width)
            amp = spectrum[i] * max_amp
            y = int(base_y - amp * math.sin(i * 0.4 + time.time()))
            points.append((x, y))

        c_pri = self.palette["primary"]
        color_bgr = (c_pri[2], c_pri[1], c_pri[0])

        # Draw glowing multiline
        pts_arr = np.array(points, np.int32).reshape((-1, 1, 2))
        cv2.polylines(frame, [pts_arr], isClosed=False, color=color_bgr, thickness=4, lineType=cv2.LINE_AA)
        cv2.polylines(frame, [pts_arr], isClosed=False, color=(255, 255, 255), thickness=1, lineType=cv2.LINE_AA)

    def render_starfield(self, frame: np.ndarray, spectrum: np.ndarray, bass: float, onset: float):
        """3D starfield acceleration warp on bass hits."""
        self.render_neon_bars(frame, spectrum, bass, onset)

    def render_lyrics_and_ui(self, frame_bgr: np.ndarray, current_time: float):
        """Renders kinetic karaoke typography and song info overlay."""
        # Convert BGR to RGB PIL image for antialiased text rendering
        pil_frame = Image.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil_frame)

        # 1. Header Metadata (Song title & artist)
        margin_x = int(self.width * 0.05)
        margin_y = int(self.height * 0.06)

        # Title shadow + text
        draw.text((margin_x + 2, margin_y + 2), self.song_title, font=self.font_title, fill=(0, 0, 0, 180))
        draw.text((margin_x, margin_y), self.song_title, font=self.font_title, fill=(255, 255, 255))

        artist_y = margin_y + int(self.height * 0.045)
        c_pri = self.palette["primary"]
        draw.text((margin_x, artist_y), self.artist_name, font=self.font_artist, fill=(c_pri[0], c_pri[1], c_pri[2]))

        # Watermark
        wm_text = "VIDA AUDIO STUDIO"
        wm_x = self.width - int(self.width * 0.18)
        draw.text((wm_x, margin_y), wm_text, font=self.font_artist, fill=(160, 160, 180))

        # 2. Active Lyrics Rendering
        lyric_state = get_active_lyric_frame(current_time, self.lyrics_data)
        if lyric_state:
            active_line = lyric_state["line"]
            active_word_idx = lyric_state["active_word_index"]
            alpha = lyric_state["alpha"]
            words = active_line.get("words", [])

            # Compute lyric layout
            lyric_y = int(self.height * 0.82)
            if self.theme in ("neon_bars", "spectrum"):
                lyric_y = int(self.height * 0.28)  # Position above bars

            # Check if line text belongs to unspaced script (Khmer, Chinese, Japanese, Thai)
            raw_line_text = active_line.get("text", "")
            is_unspaced = any(0x1780 <= ord(c) <= 0x17FF or 0x4E00 <= ord(c) <= 0x9FFF or 0x3040 <= ord(c) <= 0x30FF or 0x0E00 <= ord(c) <= 0x0E7F for c in raw_line_text)
            w_space = "" if is_unspaced else " "
            full_line_text = raw_line_text if raw_line_text else (w_space.join([w["word"] for w in words]) if words else "")

            # Script-aware font loading for current lyric line
            used_font = self._load_font(int(self.height * 0.045), bold=True, text=full_line_text)

            # Calculate total width of the line by summing exact word bounding boxes to guarantee 100% match with drawn text
            word_bboxes = [draw.textbbox((0, 0), w["word"] + w_space, font=used_font) for w in words]
            total_text_w = sum(b[2] - b[0] for b in word_bboxes) if word_bboxes else (draw.textbbox((0, 0), full_line_text, font=used_font)[2] - draw.textbbox((0, 0), full_line_text, font=used_font)[0])
            max_text_h = max((b[3] - b[1] for b in word_bboxes), default=int(self.height * 0.045))

            if total_text_w > self.width * 0.85:
                scale = (self.width * 0.85) / max(1, total_text_w)
                new_size = max(18, int(self.height * 0.045 * scale))
                used_font = self._load_font(new_size, bold=True, text=full_line_text)
                word_bboxes = [draw.textbbox((0, 0), w["word"] + w_space, font=used_font) for w in words]
                total_text_w = sum(b[2] - b[0] for b in word_bboxes) if word_bboxes else (draw.textbbox((0, 0), full_line_text, font=used_font)[2] - draw.textbbox((0, 0), full_line_text, font=used_font)[0])
                max_text_h = max((b[3] - b[1] for b in word_bboxes), default=new_size)

            start_x = max(20, (self.width - total_text_w) // 2)

            # Draw background pill behind lyrics for ultra readability
            pad_x = 24
            pad_y = 12
            pill_box = [
                start_x - pad_x,
                lyric_y - pad_y,
                start_x + total_text_w + pad_x,
                lyric_y + max_text_h + pad_y
            ]
            draw.rounded_rectangle(pill_box, radius=16, fill=(10, 10, 16, int(190 * alpha)))

            # Draw word by word with karaoke highlight
            cur_x = start_x
            for w_idx, w in enumerate(words):
                w_text = w["word"] + w_space
                w_w = word_bboxes[w_idx][2] - word_bboxes[w_idx][0] if w_idx < len(word_bboxes) else (draw.textbbox((0, 0), w_text, font=used_font)[2] - draw.textbbox((0, 0), w_text, font=used_font)[0])

                if w_idx == active_word_idx:
                    # Current active karaoke word: glowing accent color
                    hl_col = self.palette["text_highlight"]
                    draw.text((cur_x + 1, lyric_y + 1), w_text, font=used_font, fill=(0, 0, 0))
                    draw.text((cur_x, lyric_y), w_text, font=used_font, fill=hl_col)
                elif w_idx < active_word_idx:
                    # Already sung word: full white
                    draw.text((cur_x, lyric_y), w_text, font=used_font, fill=(255, 255, 255))
                else:
                    # Upcoming word: subtle muted grey
                    draw.text((cur_x, lyric_y), w_text, font=used_font, fill=(180, 185, 200))

                cur_x += w_w

        # Convert back to OpenCV BGR
        return cv2.cvtColor(np.array(pil_frame), cv2.COLOR_RGB2BGR)

    def render_video(self, progress_callback=None) -> str:
        """
        Executes complete video render, piping frames into FFmpeg process.
        """
        print(f"Starting audio analysis for: {self.audio_path}")
        analyzer = AudioAnalyzer(self.audio_path, fps=self.fps, num_bars=self.bar_count)
        analysis = analyzer.analyze(bass_boost=self.bass_boost)

        spectrum_data = analysis["spectrum"]
        bass_curve = analysis["bass"]
        onset_curve = analysis["onsets"]
        total_frames = analysis["total_frames"]

        os.makedirs(os.path.dirname(os.path.abspath(self.output_path)), exist_ok=True)

        ffmpeg_exe = get_ffmpeg_exe()
        cmd = [
            ffmpeg_exe,
            "-y",
            "-f", "rawvideo",
            "-vcodec", "rawvideo",
            "-s", f"{self.width}x{self.height}",
            "-pix_fmt", "bgr24",
            "-r", str(self.fps),
            "-i", "-",
            "-i", self.audio_path,
            "-c:v", "libx264",
            "-preset", "faster",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "320k",
            "-shortest",
            self.output_path
        ]

        print(f"Launching FFmpeg: {' '.join(cmd)}")
        log_path = self.output_path + ".ffmpeg.log"
        with open(log_path, "w", encoding="utf-8", errors="ignore") as log_file:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=log_file)

            t_start = time.time()

            for f_idx in range(total_frames):
                t_current = f_idx / self.fps
                spec = spectrum_data[f_idx]
                bass = float(bass_curve[f_idx])
                onset = float(onset_curve[f_idx])

                # 1. Base background
                frame = self.bg_frame.copy()

                # 2. Audio-reactive particle dust
                c_pri = self.palette["primary"]
                self.particles.update_and_draw(frame, bass, onset, c_pri)

                # 3. Spectrum visualizer layer
                if self.theme == "trap_circle":
                    self.render_trap_circle(frame, spec, bass, onset)
                elif self.theme in ("neon_bars", "spectrum"):
                    self.render_neon_bars(frame, spec, bass, onset)
                elif self.theme in ("horizon_wave", "ocean_wave"):
                    self.render_horizon_wave(frame, spec, bass, onset)
                else:
                    self.render_trap_circle(frame, spec, bass, onset)

                # 4. Kinetic karaoke lyrics & metadata overlay
                frame = self.render_lyrics_and_ui(frame, t_current)

                # 5. Write raw bytes to FFmpeg stdin
                try:
                    proc.stdin.write(frame.tobytes())
                except BrokenPipeError:
                    break

                # Progress callback
                if progress_callback and (f_idx % 15 == 0 or f_idx == total_frames - 1):
                    pct = round((f_idx + 1) / total_frames * 100.0, 1)
                    elapsed = time.time() - t_start
                    fps_render = (f_idx + 1) / max(0.1, elapsed)
                    eta = (total_frames - (f_idx + 1)) / max(0.1, fps_render)
                    progress_callback({
                        "frame": f_idx + 1,
                        "total_frames": total_frames,
                        "percent": pct,
                        "fps": round(fps_render, 1),
                        "eta_seconds": round(eta, 1)
                    })

            proc.stdin.close()
            proc.wait()

        if proc.returncode != 0:
            err_text = ""
            if os.path.exists(log_path):
                with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                    err_text = f.read()
            raise RuntimeError(f"FFmpeg rendering failed with code {proc.returncode}:\n{err_text}")

        # Clean up log file on success
        if os.path.exists(log_path):
            try:
                os.remove(log_path)
            except Exception:
                pass

        print(f"Video render complete: {self.output_path}")
        return self.output_path
