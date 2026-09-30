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
from backend.theme_renderers import AdvancedThemeRenderer

try:
    from backend.gpu_renderer import is_cuda_available, CUDAVideoRenderer
except ImportError:
    def is_cuda_available(): return False
    CUDAVideoRenderer = None

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

from numba import njit

@njit(fastmath=True)
def _draw_particles_numba(frame_bgr, x_arr, y_arr, radii, alphas, b_col, g_col, r_col, width, height):
    count = x_arr.shape[0]
    for i in range(count):
        cx = x_arr[i]
        cy = y_arr[i]
        rad = radii[i]
        a = alphas[i]
        if a <= 0: continue
        
        r2 = rad * rad
        min_x = max(0, cx - rad)
        max_x = min(width - 1, cx + rad)
        min_y = max(0, cy - rad)
        max_y = min(height - 1, cy + rad)
        
        inv_a = 1.0 - a
        cb = b_col * a
        cg = g_col * a
        cr = r_col * a
        
        for yy in range(min_y, max_y + 1):
            dy = yy - cy
            for xx in range(min_x, max_x + 1):
                dx = xx - cx
                if dx*dx + dy*dy <= r2:
                    frame_bgr[yy, xx, 0] = int(frame_bgr[yy, xx, 0] * inv_a + cb)
                    frame_bgr[yy, xx, 1] = int(frame_bgr[yy, xx, 1] * inv_a + cg)
                    frame_bgr[yy, xx, 2] = int(frame_bgr[yy, xx, 2] * inv_a + cr)


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
        """Updates particle positions with bass velocity boost and renders using JIT machine code."""
        boost = 1.0 + bass_val * 2.5 + onset_val * 1.5
        self.x += self.vx * boost
        self.y += self.vy * boost

        # Wrap around screen edges
        self.x = np.where(self.x < 0, self.width, self.x)
        self.x = np.where(self.x > self.width, 0, self.x)
        self.y = np.where(self.y < 0, self.height, self.y)
        self.y = np.where(self.y > self.height, 0, self.y)

        b_col, g_col, r_col = color[2], color[1], color[0]

        cur_radii = (self.radius * (1.0 + bass_val * 0.8)).astype(np.int32)
        px_arr = self.x.astype(np.int32)
        py_arr = self.y.astype(np.int32)
        alphas = np.clip(self.base_alpha + bass_val * 0.4, 0.0, 1.0)

        # Draw all particles instantly using LLVM machine code instead of Python loop
        _draw_particles_numba(frame_bgr, px_arr, py_arr, cur_radii, alphas, b_col, g_col, r_col, self.width, self.height)


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
        bass_boost: float = 1.3,
        title_scale: float = 1.0
    ):
        self.audio_path = audio_path
        self.output_path = output_path
        self.width = width
        self.height = height
        self.fps = fps
        self.theme = theme
        self.palette = PALETTES.get(palette_name, PALETTES["cyberpunk"])
        self.background_image_path = background_image
        default_logo = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads", "images", "vibetunes_logo.png")
        if (not logo_image or not os.path.exists(logo_image)) and os.path.exists(default_logo):
            self.logo_image_path = default_logo
        else:
            self.logo_image_path = logo_image
        self.center_text_primary = center_text_primary if center_text_primary is not None else "VibeTunes"
        self.center_text_secondary = center_text_secondary if center_text_secondary is not None else "OFFICIAL"
        self.show_center_text = show_center_text
        self.song_title = song_title or "VIDA Visualizer"
        self.artist_name = artist_name or "Official Audio"
        self.lyrics_data = lyrics_data or []
        self.lyric_style = lyric_style
        self.bar_count = bar_count
        self.bass_boost = bass_boost

        self.particles = ParticleSystem(80, width, height)
        self.peak_caps = np.zeros(bar_count, dtype=np.float32)
        self.wave_overlay = np.zeros((height, width, 3), dtype=np.uint8)

        # Lyric text rendering cache: avoids re-rendering identical text frames
        self._lyric_cache_key = None
        self._lyric_cache_overlay = None
        self._lyric_cache_data = None
        self.peak_decay = 0.015

        self.bg_video_cap = None
        self.vignette_mask = None
        # Pre-load / prepare background
        self.bg_frame = self._prepare_background()
        self.logo_circle = self._prepare_logo()

        self.title_scale = title_scale

        # Fonts
        self.font_title = self._load_font(int(height * 0.035 * self.title_scale), bold=True, text=self.song_title)
        self.font_artist = self._load_font(int(height * 0.022 * self.title_scale), bold=False, text=self.artist_name)
        sample_lyric = " ".join([l.get("text", "") for l in self.lyrics_data[:3]]) if self.lyrics_data else self.song_title
        self.font_lyrics = self._load_font(int(height * 0.045), bold=True, text=sample_lyric)
        self.font_lyrics_sub = self._load_font(int(height * 0.030), bold=False, text=sample_lyric)

        # Precompute trigonometry for radial spectrum (trap_circle)
        total_angles = bar_count * 2
        angles = np.linspace(-math.pi / 2.0, 1.5 * math.pi, total_angles, endpoint=False)
        self.cos_angles = np.cos(angles).astype(np.float32)
        self.sin_angles = np.sin(angles).astype(np.float32)
        self.total_angles = total_angles

        # Pre-calculated color interpolation array for radial bars
        c_pri = np.array(self.palette["primary"], dtype=np.float32)
        c_sec = np.array(self.palette["secondary"], dtype=np.float32)
        ratios = np.linspace(0.0, 1.0, total_angles, endpoint=False)[:, np.newaxis]
        colors_rgb = c_pri * (1.0 - ratios) + c_sec * ratios
        self.bar_colors_bgr = [
            (int(c[2]), int(c[1]), int(c[0])) for c in colors_rgb
        ]

        # Logo resize cache: {quantized_radius: (w, h, inv_alpha, premul_logo)}
        self._logo_cache = {}

        # Bake static header (Song Title, Artist, Watermark) directly onto bg_frame ONCE!
        self._bake_header_onto_bg()

        # Initialize advanced theme renderers for all 12 themes
        self._adv_themes = AdvancedThemeRenderer(self.width, self.height)

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
            ]
        }

        if "♪" in text or script == "latin":
            candidates = [
                "C:\\Windows\\Fonts\\arialbd.ttf" if bold else "C:\\Windows\\Fonts\\arial.ttf",
                "C:\\Windows\\Fonts\\segoeuib.ttf" if bold else "C:\\Windows\\Fonts\\segoeui.ttf",
                "C:\\Windows\\Fonts\\seguisym.ttf",
                "C:\\Windows\\Fonts\\calibrib.ttf" if bold else "C:\\Windows\\Fonts\\calibri.ttf"
            ]
        else:
            candidates = list(font_map.get(script, []))
            candidates.extend([
                "C:\\Windows\\Fonts\\arialbd.ttf" if bold else "C:\\Windows\\Fonts\\arial.ttf",
                "C:\\Windows\\Fonts\\segoeuib.ttf" if bold else "C:\\Windows\\Fonts\\segoeui.ttf"
            ])

        for p in candidates:
            if os.path.exists(p):
                try:
                    return ImageFont.truetype(p, size)
                except Exception:
                    continue
        return ImageFont.load_default()

    def _process_bg_frame(self, img: np.ndarray, apply_blur: bool = True) -> np.ndarray:
        """Resizes, crops, and darkens a background frame. Blur can be skipped for video bg frames after the first."""
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
        if apply_blur:
            resized = cv2.GaussianBlur(resized, (15, 15), 0)  # Reduced kernel from 21 to 15 for speed
        
        # Use highly optimized OpenCV C++ SIMD instead of slow Python numpy float conversion
        darkened = cv2.convertScaleAbs(resized, alpha=0.42, beta=0)
        
        if self.vignette_mask is None:
            Y, X = np.ogrid[:self.height, :self.width]
            dist_from_center = np.sqrt(((X - self.width/2)/(self.width/2))**2 + ((Y - self.height/2)/(self.height/2))**2)
            self.vignette_mask = np.clip(1.0 - 0.45 * dist_from_center, 0.2, 1.0)[:, :, np.newaxis]
            
        return darkened

    def _prepare_background(self) -> np.ndarray:
        """Prepares a darkened, blurred, high-contrast background frame or initializes video."""
        if self.background_image_path and os.path.exists(self.background_image_path):
            try:
                # Check if video
                if self.background_image_path.lower().endswith(('.mp4', '.webm', '.avi', '.mov')):
                    self.bg_video_cap = cv2.VideoCapture(self.background_image_path)
                    ret, img = self.bg_video_cap.read()
                    if ret and img is not None:
                        return self._process_bg_frame(img)
                else:
                    img = cv2.imread(self.background_image_path)
                    if img is not None:
                        return self._process_bg_frame(img)
            except Exception as e:
                print(f"Warning: could not load background {e}")

        # Procedural background matching frontend visualizer.js radial gradient exactly
        # Frontend (lines 73-79): createRadialGradient(w/2, h*0.45, w*0.05, w/2, h/2, w*0.75)
        #   stop 0: rgba(secondary, 0.08)
        #   stop 0.55: #0b0e17
        #   stop 1: #040508
        bg = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        cx, cy_inner = self.width / 2.0, self.height * 0.45
        r_inner = self.width * 0.05
        r_outer = self.width * 0.75
        Y, X = np.ogrid[:self.height, :self.width]
        dist = np.sqrt((X - cx)**2 + (Y - cy_inner)**2).astype(np.float32)

        # Normalize distance between inner and outer radius
        norm_dist = np.clip((dist - r_inner) / max(1.0, r_outer - r_inner), 0.0, 1.0)

        # Color stops: 0 -> secondary*0.08, 0.55 -> #0b0e17, 1.0 -> #040508
        c_sec_rgb = np.array([self.palette["secondary"][2], self.palette["secondary"][1], self.palette["secondary"][0]], dtype=np.float32)
        c_mid = np.array([23, 14, 11], dtype=np.float32)   # #0b0e17 in BGR
        c_end = np.array([8, 5, 4], dtype=np.float32)      # #040508 in BGR

        # Fully vectorized radial gradient interpolation (no Python loops)
        nd3 = norm_dist[:, :, np.newaxis]  # (H, W, 1) for broadcasting
        mask_inner = (nd3 < 0.55)
        # Inner region: blend secondary*0.08 -> mid
        t_inner = nd3 / 0.55
        color_inner = (c_sec_rgb * 0.08) * (1.0 - t_inner) + c_mid * t_inner
        # Outer region: blend mid -> end
        t_outer = (nd3 - 0.55) / 0.45
        color_outer = c_mid * (1.0 - t_outer) + c_end * t_outer
        bg = np.where(mask_inner, color_inner, color_outer).clip(0, 255).astype(np.uint8)

        # Subtle vignette
        if self.vignette_mask is None:
            Y2, X2 = np.ogrid[:self.height, :self.width]
            dist_from_center = np.sqrt(((X2 - self.width/2)/(self.width/2))**2 + ((Y2 - self.height/2)/(self.height/2))**2)
            self.vignette_mask = np.clip(1.0 - 0.45 * dist_from_center, 0.2, 1.0)[:, :, np.newaxis]

        bg = (bg.astype(np.float32) * self.vignette_mask).astype(np.uint8)
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

    def _bake_header_onto_bg(self):
        """Bakes the static song title, artist name, and watermark directly onto bg_frame ONCE at start."""
        overlay = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        margin_x = int(self.width * 0.05)
        margin_y = int(self.height * 0.06)

        # Title shadow + text
        draw.text((margin_x + 2, margin_y + 2), self.song_title, font=self.font_title, fill=(0, 0, 0, 180))
        draw.text((margin_x, margin_y), self.song_title, font=self.font_title, fill=(255, 255, 255, 255))

        artist_y = margin_y + int(self.height * 0.045 * self.title_scale)
        c_pri = self.palette["primary"]
        draw.text((margin_x, artist_y), self.artist_name, font=self.font_artist, fill=(c_pri[0], c_pri[1], c_pri[2], 255))

        # Alpha-blend onto self.bg_frame
        overlay_np = cv2.cvtColor(np.array(overlay), cv2.COLOR_RGBA2BGRA)
        alpha = overlay_np[:, :, 3:4].astype(np.float32) / 255.0
        self.bg_frame[:] = (self.bg_frame * (1.0 - alpha) + overlay_np[:, :, :3] * alpha).astype(np.uint8)

    def render_trap_circle(self, frame: np.ndarray, spectrum: np.ndarray, bass: float, onset: float):
        """Trap Nation style: Pulsing center circle + 360-degree radial neon spectrum bars (vectorized)."""
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

        # Mirrored radial spectrum for seamless aesthetic
        mirrored_spec = np.concatenate([spectrum, spectrum[::-1]])
        if len(mirrored_spec) != self.total_angles:
            angles = np.linspace(-math.pi / 2.0, 1.5 * math.pi, len(mirrored_spec), endpoint=False)
            cos_a = np.cos(angles).astype(np.float32)
            sin_a = np.sin(angles).astype(np.float32)
        else:
            cos_a = self.cos_angles
            sin_a = self.sin_angles

        max_bar_length = int(min(self.width, self.height) * 0.22)
        bar_lens = np.clip((mirrored_spec * max_bar_length).astype(np.int32), 3, max_bar_length)

        r_inner = dynamic_radius + 4
        r_outer_arr = r_inner + bar_lens

        x1_arr = (cx + r_inner * cos_a).astype(np.int32)
        y1_arr = (cy + r_inner * sin_a).astype(np.int32)
        x2_arr = (cx + r_outer_arr * cos_a).astype(np.int32)
        y2_arr = (cy + r_outer_arr * sin_a).astype(np.int32)

        # Batch draw lines with precomputed gradient colors
        colors = self.bar_colors_bgr
        for i in range(len(mirrored_spec)):
            cv2.line(frame, (x1_arr[i], y1_arr[i]), (x2_arr[i], y2_arr[i]), colors[i], thickness=3)

        # Outer pulsing glow ring
        glow_col = (self.palette["glow"][2], self.palette["glow"][1], self.palette["glow"][0])
        cv2.circle(frame, (cx, cy), dynamic_radius + 2, glow_col, 2)

        # Draw center logo with bass scaling (cached by quantized radius for 200+ FPS)
        if self.logo_circle is not None:
            r_quantized = int(dynamic_radius // 2 * 2)
            if r_quantized not in self._logo_cache:
                lw, lh = self.logo_circle.shape[1], self.logo_circle.shape[0]
                scale = (r_quantized * 2.0) / lw
                scaled_w = int(lw * scale)
                scaled_h = int(lh * scale)
                if scaled_w > 10 and scaled_h > 10:
                    resized_logo = cv2.resize(self.logo_circle, (scaled_w, scaled_h), interpolation=cv2.INTER_LINEAR)
                    alpha_m = (resized_logo[:, :, 3:4].astype(np.float32) / 255.0)
                    inv_alpha_m = 1.0 - alpha_m
                    premul_logo = (resized_logo[:, :, :3].astype(np.float32) * alpha_m)
                    self._logo_cache[r_quantized] = (scaled_w, scaled_h, inv_alpha_m, premul_logo)
                else:
                    self._logo_cache[r_quantized] = None

            cached_logo = self._logo_cache.get(r_quantized)
            if cached_logo is not None:
                scaled_w, scaled_h, inv_alpha_m, premul_logo = cached_logo
                lx1 = cx - scaled_w // 2
                ly1 = cy - scaled_h // 2
                lx2 = lx1 + scaled_w
                ly2 = ly1 + scaled_h

                if lx1 >= 0 and ly1 >= 0 and lx2 <= self.width and ly2 <= self.height:
                    frame[ly1:ly2, lx1:lx2] = (frame[ly1:ly2, lx1:lx2] * inv_alpha_m + premul_logo).astype(np.uint8)

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

    def render_ocean_wave(self, frame: np.ndarray, spectrum: np.ndarray, bass: float, onset: float, anim_time: float = 0.0):
        """
        Multi-Layer Fluid Wave Harmonic Layers + Glowing Crests + Center Core Emblem.
        Directly matches frontend/js/themes/wave.js for consistent studio export.
        """
        cx = self.width // 2
        cy = self.height // 2
        count = len(spectrum)
        if count == 0:
            return

        c_pri = self.palette["primary"]
        c_sec = self.palette["secondary"]
        glow_val = self.palette.get("glow", c_pri)
        if isinstance(glow_val, (list, tuple)) and len(glow_val) >= 3:
            glow_bgr = (int(glow_val[2]), int(glow_val[1]), int(glow_val[0]))
        else:
            glow_bgr = (int(c_pri[2]), int(c_pri[1]), int(c_pri[0]))

        # Smooth resampled points across width for organic fluid curves
        n_pts = 260
        x_coords = np.linspace(0, self.width, n_pts, dtype=np.float32)

        interp_spec = np.interp(
            np.linspace(0, count - 1, n_pts),
            np.arange(count),
            spectrum
        ).astype(np.float32)
        interp_spec = np.maximum(0.04, interp_spec)

        # Match frontend: waveAnim += 0.02 per frame => at 60fps that's 1.2/sec
        # So we use: anim_time * fps * 0.02 * (layer + 1.2)
        wave_anim = anim_time * self.fps * 0.02

        # 0. Ambient Background Radial Aura
        if not hasattr(self, '_aura_base'):
            r_inner = min(self.width, self.height) * 0.1
            r_outer = min(self.width, self.height) * 0.7
            Y, X = np.ogrid[:self.height, :self.width]
            dist = np.sqrt((X - cx)**2 + (Y - cy)**2)
            
            norm_dist = np.clip((dist - r_inner) / (r_outer - r_inner), 0.0, 1.0)
            
            # Map distances to the exact stops: 0 -> primary, 0.6 -> secondary, 1.0 -> transparent
            r_map = np.interp(norm_dist, [0.0, 0.6, 1.0], [c_pri[0], c_sec[0], 0])
            g_map = np.interp(norm_dist, [0.0, 0.6, 1.0], [c_pri[1], c_sec[1], 0])
            b_map = np.interp(norm_dist, [0.0, 0.6, 1.0], [c_pri[2], c_sec[2], 0])
            
            alpha_base_map = np.interp(norm_dist, [0.0, 0.6, 1.0], [0.15, 0.05, 0.0])
            alpha_bass_map = np.interp(norm_dist, [0.0, 0.6, 1.0], [0.15, 0.08, 0.0])
            
            self._aura_base = np.stack([b_map * alpha_base_map, g_map * alpha_base_map, r_map * alpha_base_map], axis=-1).astype(np.float32)
            self._aura_bass = np.stack([b_map * alpha_bass_map, g_map * alpha_bass_map, r_map * alpha_bass_map], axis=-1).astype(np.float32)
            self._y_coords = np.arange(self.height, dtype=np.float32)

        # Apply pre-computed perfect radial aura
        current_aura = (self._aura_base + self._aura_bass * bass).astype(np.uint8)
        frame[:] = cv2.add(frame, current_aura)

        # 1. Multi-Layer Fluid Wave Harmonic Layers (layer 2, 1, 0 from back to front)
        overlay = self.wave_overlay
        for layer in (2, 1, 0):
            opacity = 0.25 + layer * 0.25  # Match frontend: 0.25 + layer * 0.25
            amplitude = (self.height * 0.14) * (1.0 + layer * 0.45) * (0.8 + bass * 0.8)
            y_offset = cy + (layer - 1) * 36

            t = layer / 3.0
            col_b = int(c_pri[2] * (1.0 - t) + c_sec[2] * t)
            col_g = int(c_pri[1] * (1.0 - t) + c_sec[1] * t)
            col_r = int(c_pri[0] * (1.0 - t) + c_sec[0] * t)
            layer_bgr = (col_b, col_g, col_r)

            # Match frontend exactly: Math.sin((i / count) * Math.PI * 4 + waveAnim * (layer + 1.2))
            phase = (x_coords / self.width) * (math.pi * 4.0) + (wave_anim * (layer + 1.2))
            wave_y = y_offset + np.sin(phase) * amplitude * interp_spec

            pts_top = np.stack([x_coords, wave_y], axis=1)
            pts_bottom = np.array([[self.width, self.height], [0, self.height]], dtype=np.float32)
            poly_pts = np.vstack([pts_top, pts_bottom]).astype(np.int32)

            # Calculate exact dynamic vertical gradient starting from the crest of the wave
            crest_y = int(y_offset - amplitude)
            norm_y = np.clip((self._y_coords - crest_y) / float(max(1, self.height - crest_y)), 0.0, 1.0)
            grad_alpha = np.interp(norm_y, [0.0, 0.5, 1.0], [opacity * 0.85, opacity * 0.25, 0.0]).reshape(self.height, 1, 1)

            # Match frontend: linear gradient fill instead of solid color
            overlay.fill(0)
            cv2.fillPoly(overlay, [poly_pts], layer_bgr)
            
            # Apply exact vertical gradient mask to the overlay before blending
            grad_overlay = (overlay.astype(np.float32) * grad_alpha).astype(np.uint8)
            cv2.addWeighted(grad_overlay, 1.0, frame, 1.0, 0, frame)

            # Glowing crest stroke matching UI: strokeStyle with opacity + 0.35, lineWidth 2.5 - layer*0.4, shadowBlur
            crest_pts = pts_top.astype(np.int32).reshape((-1, 1, 2))
            stroke_thickness = max(1, int(2.5 - layer * 0.4))
            
            # Fake Gaussian shadowBlur for the wave crests (matches Canvas shadowBlur)
            base_glow_thick = stroke_thickness
            for gw in range(4, 0, -1):
                gw_thick = base_glow_thick + gw * 4
                gw_alpha = (0.25 / gw) * (opacity + 0.35)
                gw_col = (int(col_b * gw_alpha), int(col_g * gw_alpha), int(col_r * gw_alpha))
                cv2.polylines(frame, [crest_pts], isClosed=False, color=gw_col, thickness=gw_thick, lineType=cv2.LINE_AA)
                
            # Main stroke
            stroke_alpha = min(1.0, opacity + 0.35)
            stroke_col = (int(col_b * stroke_alpha), int(col_g * stroke_alpha), int(col_r * stroke_alpha))
            cv2.polylines(frame, [crest_pts], isClosed=False, color=stroke_col, thickness=stroke_thickness, lineType=cv2.LINE_AA)

        # 2. Center Glowing Audio-Pulse Core Emblem
        base_radius = int(min(self.width, self.height) * 0.085 + bass * 20)
        dynamic_radius = max(24, base_radius)

        # Dark emblem background circle
        cv2.circle(frame, (cx, cy), dynamic_radius, (10, 14, 24), -1, lineType=cv2.LINE_AA)

        # Draw Center Logo badge if available
        if self.logo_circle is not None:
            r_quantized = int(dynamic_radius // 2 * 2)
            if r_quantized not in self._logo_cache:
                lw, lh = self.logo_circle.shape[1], self.logo_circle.shape[0]
                target_d = int(r_quantized * 2.0 * 0.92)
                if target_d > 10:
                    resized_logo = cv2.resize(self.logo_circle, (target_d, target_d), interpolation=cv2.INTER_LINEAR)
                    alpha_m = (resized_logo[:, :, 3:4].astype(np.float32) / 255.0)
                    inv_alpha_m = 1.0 - alpha_m
                    premul_logo = (resized_logo[:, :, :3].astype(np.float32) * alpha_m)
                    self._logo_cache[r_quantized] = (target_d, target_d, inv_alpha_m, premul_logo)
                else:
                    self._logo_cache[r_quantized] = None

            cached_logo = self._logo_cache.get(r_quantized)
            if cached_logo is not None:
                scaled_w, scaled_h, inv_alpha_m, premul_logo = cached_logo
                lx1 = cx - scaled_w // 2
                ly1 = cy - scaled_h // 2
                lx2 = lx1 + scaled_w
                ly2 = ly1 + scaled_h
                if lx1 >= 0 and ly1 >= 0 and lx2 <= self.width and ly2 <= self.height:
                    frame[ly1:ly2, lx1:lx2] = (frame[ly1:ly2, lx1:lx2] * inv_alpha_m + premul_logo).astype(np.uint8)

        # Pulsing glowing outline ring
        ring_thickness = max(2, int(2.5 + bass * 2))
        pri_bgr = (int(c_pri[2]), int(c_pri[1]), int(c_pri[0]))
        
        # Fake Gaussian shadowBlur for the center emblem (matches Canvas shadowBlur=15)
        for gw in range(5, 0, -1):
            gw_thick = ring_thickness + gw * 3
            gw_alpha = 0.2 / gw
            gw_col = (int(glow_bgr[0]*gw_alpha), int(glow_bgr[1]*gw_alpha), int(glow_bgr[2]*gw_alpha))
            cv2.circle(frame, (cx, cy), dynamic_radius, gw_col, gw_thick, lineType=cv2.LINE_AA)
            
        cv2.circle(frame, (cx, cy), dynamic_radius, pri_bgr, ring_thickness, lineType=cv2.LINE_AA)

    def render_horizon_wave(self, frame: np.ndarray, spectrum: np.ndarray, bass: float, onset: float, anim_time: float = 0.0):
        """Aliases to render_ocean_wave for smooth organic multi-layer wave rendering."""
        self.render_ocean_wave(frame, spectrum, bass, onset, anim_time=anim_time)

    def render_starfield(self, frame: np.ndarray, spectrum: np.ndarray, bass: float, onset: float):
        """3D starfield acceleration warp on bass hits."""
        self.render_neon_bars(frame, spectrum, bass, onset)

    def render_lyrics_and_ui(self, frame_bgr: np.ndarray, current_time: float):
        """
        Renders kinetic karaoke typography overlay matching frontend lyrics.js exactly.
        Uses glassmorphism pill, correct word coloring, next-line preview, and matching positions.
        """
        lyric_state = get_active_lyric_frame(current_time, self.lyrics_data)
        if not lyric_state:
            self._lyric_cache_key = None
            self._lyric_cache_data = None
            return frame_bgr

        active_line = lyric_state["line"]
        active_word_idx = lyric_state["active_word_index"]
        word_progress = lyric_state.get("word_progress", 0.0)
        alpha = lyric_state["alpha"]
        next_line = lyric_state.get("next_line")
        is_instrumental = active_line.get("is_instrumental", False) if active_line else False
        line_id = active_line.get("line_id", active_line.get("text", ""))
        
        # Optimize cache: round progress to 1 decimal place (10 steps) instead of 2 (100 steps)
        # This increases cache hits by 10x during karaoke sweeps, massively speeding up PIL rendering.
        cache_key = (line_id, active_word_idx, round(word_progress, 1) if active_word_idx >= 0 else -1)

        # FAST-PATH: Blend only the small cached lyric box slice! (2ms instead of 75ms)
        if cache_key == self._lyric_cache_key and self._lyric_cache_data is not None:
            bx1, by1, bx2, by2, inv_alpha, premul_fg = self._lyric_cache_data
            frame_slice = frame_bgr[by1:by2, bx1:bx2]
            frame_bgr[by1:by2, bx1:bx2] = (frame_slice * inv_alpha + premul_fg).astype(np.uint8)
            return frame_bgr

        # Cache miss: render the lyric pill box matching frontend exactly
        words = active_line.get("words", [])
        raw_line_text = active_line.get("text", "")
        is_unspaced = any(0x1780 <= ord(c) <= 0x17FF or 0x4E00 <= ord(c) <= 0x9FFF or 0x3040 <= ord(c) <= 0x30FF or 0x0E00 <= ord(c) <= 0x0E7F for c in raw_line_text)
        w_space = "" if is_unspaced else " "

        def _get_w_str(w_obj):
            if isinstance(w_obj, dict):
                return str(w_obj.get("word", ""))
            return str(w_obj)

        # Match frontend font size: h * 0.054 (frontend lyrics.js line 219)
        full_line_text = raw_line_text if raw_line_text else (w_space.join([_get_w_str(w) for w in words]) if words else "")
        font_size = int(self.height * 0.054)
        used_font = self._load_font(font_size, bold=True, text=full_line_text)

        temp_img = Image.new("RGBA", (1, 1))
        draw_temp = ImageDraw.Draw(temp_img)

        # Measure natural space width and scale to 85% to match frontend (lyrics.js line 238)
        space_w = int((draw_temp.textbbox((0, 0), " ", font=used_font)[2] - draw_temp.textbbox((0, 0), " ", font=used_font)[0]) * 0.85) if not is_unspaced else 0

        word_bboxes = []
        for w in words:
            w_str = _get_w_str(w)
            bbox = draw_temp.textbbox((0, 0), w_str, font=used_font)
            word_bboxes.append((bbox[0], bbox[1], bbox[2], bbox[3], w_str))
        
        total_text_w = sum((b[2] - b[0]) for b in word_bboxes) + space_w * max(0, len(words) - 1) if word_bboxes else (draw_temp.textbbox((0, 0), full_line_text, font=used_font)[2] - draw_temp.textbbox((0, 0), full_line_text, font=used_font)[0])
        max_text_h = max((b[3] - b[1] for b in word_bboxes), default=font_size)

        # Auto-scale if text exceeds 86% of screen width (matching frontend line 251)
        if total_text_w > self.width * 0.86:
            scale = (self.width * 0.86) / max(1, total_text_w)
            font_size = max(15, int(font_size * scale))
            used_font = self._load_font(font_size, bold=True, text=full_line_text)
            space_w = int((draw_temp.textbbox((0, 0), " ", font=used_font)[2] - draw_temp.textbbox((0, 0), " ", font=used_font)[0]) * 0.85) if not is_unspaced else 0
            word_bboxes = []
            for w in words:
                w_str = _get_w_str(w)
                bbox = draw_temp.textbbox((0, 0), w_str, font=used_font)
                word_bboxes.append((bbox[0], bbox[1], bbox[2], bbox[3], w_str))
            total_text_w = sum((b[2] - b[0]) for b in word_bboxes) + space_w * max(0, len(words) - 1) if word_bboxes else (draw_temp.textbbox((0, 0), full_line_text, font=used_font)[2] - draw_temp.textbbox((0, 0), full_line_text, font=used_font)[0])
            max_text_h = max((b[3] - b[1] for b in word_bboxes), default=font_size)

        # Match frontend padding: paddingX = fontSize * 0.80, paddingY = fontSize * 0.72
        pad_x = int(font_size * 0.80)
        pad_y = int(font_size * 0.72)
        box_w = total_text_w + 2 * pad_x
        box_h = max_text_h + 2 * pad_y

        # Match frontend Y position: textY = h * 0.85 (frontend lyrics.js line 230)
        lyric_y = int(self.height * 0.85)
        if self.theme in ("neon_bars", "spectrum"):
            lyric_y = int(self.height * 0.28)

        start_x = max(24, (self.width - total_text_w) // 2)
        bx1 = start_x - pad_x
        by1 = lyric_y - pad_y
        bx2 = bx1 + box_w
        by2 = by1 + box_h

        # Clip coordinates within frame bounds
        bx1 = max(0, min(bx1, self.width - 1))
        by1 = max(0, min(by1, self.height - 1))
        bx2 = max(bx1 + 1, min(bx2, self.width))
        by2 = max(by1 + 1, min(by2, self.height))
        actual_w = bx2 - bx1
        actual_h = by2 - by1

        # Create small PIL image for this box
        pill_img = Image.new("RGBA", (actual_w, actual_h), (0, 0, 0, 0))
        draw_pill = ImageDraw.Draw(pill_img)

        c_p = self.palette["primary"]
        hl_col = self.palette["text_highlight"]
        corner_radius = pad_y

        # Main pill background (Web UI: flat rgba(15, 20, 25, 0.4) + linear gradient sheen)
        bg_layer = Image.new("RGBA", (actual_w, actual_h), (0, 0, 0, 0))
        bg_draw = ImageDraw.Draw(bg_layer)
        
        r, g, b = 15, 20, 25
        base_a = int(0.4 * 255 * alpha)
        sheen_h = int(actual_h * 0.4)
        
        for y in range(actual_h):
            row_r, row_g, row_b, row_a = r, g, b, base_a
            
            # Apply sheen overlay (Web UI: rgba(255,255,255, 0.1) fading to 0 over top 40%)
            if y <= sheen_h and sheen_h > 0:
                t = y / sheen_h
                sheen_alpha_f = (0.1 * alpha) * (1.0 - t)
                
                s_a = sheen_alpha_f
                b_a = base_a / 255.0
                out_a = s_a + b_a * (1.0 - s_a)
                if out_a > 0:
                    row_r = int((255 * s_a + r * b_a * (1.0 - s_a)) / out_a)
                    row_g = int((255 * s_a + g * b_a * (1.0 - s_a)) / out_a)
                    row_b = int((255 * s_a + b * b_a * (1.0 - s_a)) / out_a)
                    row_a = int(out_a * 255)
                    
            bg_draw.line([(0, y), (actual_w, y)], fill=(row_r, row_g, row_b, row_a))

        # Mask it with rounded rectangle
        mask_layer = Image.new("L", (actual_w, actual_h), 0)
        mask_draw = ImageDraw.Draw(mask_layer)
        mask_draw.rounded_rectangle([0, 0, actual_w - 1, actual_h - 1], radius=corner_radius, fill=255)
        pill_img.paste(bg_layer, (0, 0), mask_layer)

        # Draw Outline (Web UI: rgba(255, 255, 255, 0.1))
        draw_pill.rounded_rectangle(
            [0, 0, actual_w - 1, actual_h - 1],
            radius=corner_radius,
            fill=None,
            outline=(255, 255, 255, int(25.5 * alpha)),
            width=1
        )

        # --- Next line preview above the pill (lyrics.js lines 306-317) ---
        if next_line and not is_instrumental:
            next_text = next_line.get("text", "") if isinstance(next_line, dict) else ""
            if next_text and active_line:
                line_end = active_line.get("end", 0)
                next_start = next_line.get("start", 0) if isinstance(next_line, dict) else 0
                if next_start - line_end <= 6.0:
                    next_font_size = max(12, int(font_size * 0.58))
                    next_font = self._load_font(next_font_size, bold=False, text=next_text)
                    next_bbox = draw_temp.textbbox((0, 0), next_text, font=next_font)
                    next_tw = next_bbox[2] - next_bbox[0]
                    next_th = next_bbox[3] - next_bbox[1]
                    # Position above the pill (centered)
                    next_x = (self.width - next_tw) // 2
                    next_y = by1 - int(next_font_size * 1.1)
                    if next_y > 10:
                        # Efficient small-region rendering (not full-frame overlay)
                        nx1 = max(0, next_x - 4)
                        ny1 = max(0, next_y - 4)
                        nx2 = min(self.width, next_x + next_tw + 6)
                        ny2 = min(self.height, next_y + next_th + 6)
                        nw = nx2 - nx1
                        nh = ny2 - ny1
                        if nw > 0 and nh > 0:
                            next_pill = Image.new("RGBA", (nw, nh), (0, 0, 0, 0))
                            next_draw = ImageDraw.Draw(next_pill)
                            local_x = next_x - nx1
                            local_y = next_y - ny1
                            # Shadow
                            next_draw.text((local_x + 1, local_y + 1), next_text, font=next_font, fill=(0, 0, 0, 200))
                            # Text at 42% opacity matching frontend
                            next_draw.text((local_x, local_y), next_text, font=next_font, fill=(255, 255, 255, int(107 * alpha)))
                            next_np = cv2.cvtColor(np.array(next_pill), cv2.COLOR_RGBA2BGRA)
                            next_a = next_np[:, :, 3:4].astype(np.float32) / 255.0
                            next_inv = 1.0 - next_a
                            next_fg = next_np[:, :, :3].astype(np.float32) * next_a
                            frame_bgr[ny1:ny2, nx1:nx2] = (frame_bgr[ny1:ny2, nx1:nx2] * next_inv + next_fg).astype(np.uint8)

        # Draw words inside pill matching frontend coloring exactly (lyrics.js lines 320-397)
        cur_x = pad_x
        text_draw_y = pad_y
        glow_layer = Image.new("RGBA", (actual_w, actual_h), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow_layer)

        for w_idx, (b0, b1, b2, b3, w_str) in enumerate(word_bboxes):
            w_w = b2 - b0
            w_text = w_str

            if w_idx == active_word_idx:
                # Current word: Draw base muted text first, then sweep highlight overlay
                # Base muted word (white 0.85 alpha)
                draw_pill.text((cur_x, text_draw_y), w_text, font=used_font, fill=(255, 255, 255, int(216 * alpha)))
                # Sweep highlight: fill only the portion of the word that has been sung
                sweep_w = max(1, int(w_w * word_progress))
                # Create a clipped highlight overlay for the sweep effect
                sweep_img = Image.new("RGBA", (sweep_w, actual_h), (0, 0, 0, 0))
                sweep_draw = ImageDraw.Draw(sweep_img)
                # Draw on sweep overlay and glow overlay
                sweep_draw.text((0, text_draw_y), w_text, font=used_font, fill=(hl_col[0], hl_col[1], hl_col[2], 255))
                glow_draw.text((cur_x, text_draw_y), w_text, font=used_font, fill=(hl_col[0], hl_col[1], hl_col[2], 255))
                
                # We need to mask the glow for the swept part too, but let's approximate by glowing the whole word 
                # slightly and fully pasting the sharp swept text
                pill_img.paste(sweep_img, (cur_x, 0), sweep_img)
            elif w_idx < active_word_idx:
                # Past words: use highlight color (matching frontend: ctx.fillStyle = pal.highlight)
                draw_pill.text((cur_x, text_draw_y), w_text, font=used_font, fill=(hl_col[0], hl_col[1], hl_col[2], 255))
                glow_draw.text((cur_x, text_draw_y), w_text, font=used_font, fill=(hl_col[0], hl_col[1], hl_col[2], 255))
            else:
                # Future words: white with 0.85 alpha (matching frontend: rgba(255, 255, 255, 0.85))
                draw_pill.text((cur_x, text_draw_y), w_text, font=used_font, fill=(255, 255, 255, int(216 * alpha)))

            cur_x += w_w + space_w

        # Apply glow layer if there are past/current words
        if active_word_idx >= 0:
            blurred_glow = glow_layer.filter(ImageFilter.GaussianBlur(radius=6))
            # Paste glow behind the text
            pill_img.alpha_composite(blurred_glow)
            # Re-draw the sharp highlighted text on top to prevent wash-out
            cur_x = pad_x
            for w_idx, (b0, b1, b2, b3, w_str) in enumerate(word_bboxes):
                w_w = b2 - b0
                w_text = w_str
                if w_idx == active_word_idx:
                    sweep_w = max(1, int(w_w * word_progress))
                    sweep_img = Image.new("RGBA", (sweep_w, actual_h), (0, 0, 0, 0))
                    sweep_draw = ImageDraw.Draw(sweep_img)
                    sweep_draw.text((0, text_draw_y), w_text, font=used_font, fill=(hl_col[0], hl_col[1], hl_col[2], 255))
                    pill_img.paste(sweep_img, (cur_x, 0), sweep_img)
                elif w_idx < active_word_idx:
                    draw_pill.text((cur_x, text_draw_y), w_text, font=used_font, fill=(hl_col[0], hl_col[1], hl_col[2], 255))
                cur_x += w_w + space_w

        # Convert to numpy BGRA and pre-compute alpha masks
        pill_np = cv2.cvtColor(np.array(pill_img), cv2.COLOR_RGBA2BGRA)
        box_alpha = (pill_np[:, :, 3:4].astype(np.float32) / 255.0)
        box_inv_alpha = 1.0 - box_alpha
        box_fg = (pill_np[:, :, :3].astype(np.float32) * box_alpha)

        self._lyric_cache_key = cache_key
        self._lyric_cache_data = (bx1, by1, bx2, by2, box_inv_alpha, box_fg)

        # Blend box
        frame_slice = frame_bgr[by1:by2, bx1:bx2]
        frame_bgr[by1:by2, bx1:bx2] = (frame_slice * box_inv_alpha + box_fg).astype(np.uint8)
        return frame_bgr

    @staticmethod
    def _detect_nvenc() -> bool:
        """Checks if NVIDIA h264_nvenc encoder is available via FFmpeg."""
        try:
            ffmpeg_exe = get_ffmpeg_exe()
            result = subprocess.run(
                [ffmpeg_exe, "-hide_banner", "-encoders"],
                capture_output=True, text=True, timeout=5
            )
            return "h264_nvenc" in result.stdout
        except Exception:
            return False

    def render_video(self, progress_callback=None) -> str:
        """
        Executes complete video render, piping frames into FFmpeg process.
        Auto-detects NVIDIA GPU and uses h264_nvenc for YouTube-standard 60fps hardware-accelerated encoding.
        Falls back to libx264 CPU encoding if GPU unavailable.
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

        # Auto-detect NVIDIA GPU for hardware-accelerated encoding (YouTube standard 60fps)
        use_nvenc = self._detect_nvenc()
        if use_nvenc:
            print("[VIDA Renderer] ⚡ NVIDIA GPU detected — using h264_nvenc hardware encoder (MAX SPEED PRESET)")
            video_codec_args = [
                "-c:v", "h264_nvenc",
                "-preset", "p1",         # MAXIMUM SPEED PRESET for NVENC
                "-tune", "ull",          # Ultra-low latency tuning for speed
                "-rc", "vbr",
                "-cq", "20",             # Slightly lower constant quality (20 instead of 18) for speed
                "-b:v", "20M",           # Target bitrate (higher for 2K)
                "-maxrate", "30M",
                "-bufsize", "40M",
                "-multipass", "0",       # Disable multipass for maximum speed
            ]
        else:
            print("[VIDA Renderer] 🖥️ No NVIDIA GPU — using libx264 CPU encoder")
            video_codec_args = [
                "-c:v", "libx264",
                "-preset", "faster",
                "-crf", "18",
            ]

        cmd = [
            ffmpeg_exe,
            "-y",
            "-thread_queue_size", "16",
            "-f", "rawvideo",
            "-vcodec", "rawvideo",
            "-s", f"{self.width}x{self.height}",
            "-pix_fmt", "yuv420p",
            "-r", str(self.fps),
            "-i", "-",
            "-thread_queue_size", "64",
            "-i", self.audio_path,
            *video_codec_args,
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

            # Pre-initialize GPU renderer if available
            gpu_renderer = None
            if is_cuda_available() and CUDAVideoRenderer is not None:
                try:
                    gpu_renderer = CUDAVideoRenderer(self.width, self.height)
                except Exception as e:
                    print(f"[VIDA Renderer] Failed to init GPU renderer: {e}. Falling back to CPU.")
                    gpu_renderer = None

            t_start = time.time()

            for f_idx in range(total_frames):
                t_current = f_idx / self.fps
                spec = spectrum_data[f_idx]
                bass = float(bass_curve[f_idx])
                onset = float(onset_curve[f_idx])

                # 1. Base background
                if self.bg_video_cap is not None:
                    ret, v_frame = self.bg_video_cap.read()
                    if not ret:
                        self.bg_video_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        ret, v_frame = self.bg_video_cap.read()
                    if ret and v_frame is not None:
                        frame = self._process_bg_frame(v_frame, apply_blur=(f_idx == 0))
                    else:
                        frame = self.bg_frame.copy()
                else:
                    frame = self.bg_frame.copy()

                if gpu_renderer and self.theme not in ("horizon_wave", "ocean_wave"):
                    # ── GPU ACCELERATED RENDERING (trap_circle / neon_bars) ──
                    frame_bgr = gpu_renderer.render_frame(
                        bg_frame_bgr=frame,
                        spectrum=spec,
                        bass=bass,
                        onset=onset,
                        palette=self.palette,
                        theme=self.theme,
                        peak_caps=self.peak_caps
                    )
                else:
                    # ── CPU FALLBACK RENDERING ──
                    frame_bgr = frame
                    c_pri = self.palette["primary"]
                    self.particles.update_and_draw(frame_bgr, bass, onset, c_pri)

                    _adv = self._adv_themes
                    _lc = self.logo_circle
                    _lcache = self._logo_cache
                    if self.theme == "trap_circle":
                        self.render_trap_circle(frame_bgr, spec, bass, onset)
                    elif self.theme in ("neon_bars", "spectrum"):
                        self.render_neon_bars(frame_bgr, spec, bass, onset)
                    elif self.theme in ("horizon_wave", "ocean_wave"):
                        self.render_ocean_wave(frame_bgr, spec, bass, onset, anim_time=t_current)
                    elif self.theme == "quantum_vortex":
                        _adv.render_quantum_vortex(frame_bgr, spec, bass, onset, t_current, self.palette, _lc, _lcache)
                    elif self.theme == "neural_synapse":
                        _adv.render_neural_synapse(frame_bgr, spec, bass, onset, t_current, self.palette, _lc, _lcache)
                    elif self.theme == "hyper_liquid":
                        _adv.render_hyper_liquid(frame_bgr, spec, bass, onset, t_current, self.palette, _lc, _lcache)
                    elif self.theme == "angkor_mandala":
                        _adv.render_angkor_mandala(frame_bgr, spec, bass, onset, t_current, self.palette, _lc, _lcache)
                    elif self.theme == "hologram_hud":
                        _adv.render_hologram_hud(frame_bgr, spec, bass, onset, t_current, self.palette, _lc, _lcache)
                    elif self.theme == "aurora_borealis":
                        _adv.render_aurora_borealis(frame_bgr, spec, bass, onset, t_current, self.palette, _lc, _lcache)
                    elif self.theme == "dna_helix":
                        _adv.render_dna_helix(frame_bgr, spec, bass, onset, t_current, self.palette, _lc, _lcache)
                    elif self.theme == "sonic_nebula":
                        _adv.render_sonic_nebula(frame_bgr, spec, bass, onset, t_current, self.palette, _lc, _lcache)
                    else:
                        self.render_trap_circle(frame_bgr, spec, bass, onset)

                # 4. Kinetic karaoke lyrics & metadata overlay (cached on CPU)
                frame_bgr = self.render_lyrics_and_ui(frame_bgr, t_current)

                # Convert to native YUV420 planar buffer: 50% less RAM/pipe I/O and zero FFmpeg swscale filter memory leaks
                frame_yuv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2YUV_I420)

                # 5. Write raw bytes to FFmpeg stdin (zero-copy memoryview)
                try:
                    proc.stdin.write(memoryview(frame_yuv))
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
            if self.bg_video_cap is not None:
                self.bg_video_cap.release()
            if gpu_renderer is not None:
                gpu_renderer.release()

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
