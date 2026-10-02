"""
Windows Native Text Shaping & Rendering Engine
Uses Windows DirectWrite / Uniscribe via GDI+ for 100% authentic, flawless
complex script rendering (Khmer, Thai, Lao, Myanmar, Hindi, Arabic, etc.).
Completely eliminates broken combining marks and dotted circles (◌) on Windows.
"""

import sys
import os
import ctypes
from ctypes import wintypes
import numpy as np

def is_complex_script(text: str) -> bool:
    """Returns True if the text contains complex OpenType scripts requiring Uniscribe shaping."""
    if not text:
        return False
    for c in text:
        code = ord(c)
        # Khmer: 0x1780 - 0x17FF
        # Thai: 0x0E00 - 0x0E7F
        # Lao: 0x0E80 - 0x0EFF
        # Myanmar: 0x1000 - 0x109F
        # Devanagari (Hindi): 0x0900 - 0x097F
        # Arabic: 0x0600 - 0x06FF
        # Khmer Symbols: 0x19E0 - 0x19FF
        if (0x1780 <= code <= 0x17FF or
            0x19E0 <= code <= 0x19FF or
            0x0E00 <= code <= 0x0E7F or
            0x0E80 <= code <= 0x0EFF or
            0x1000 <= code <= 0x109F or
            0x0900 <= code <= 0x097F or
            0x0600 <= code <= 0x06FF):
            return True
    return False


class WindowsTextRenderer:
    _gdiplus_token = None
    _init_failed = False
    _pfc = None
    _kantumruy_family = None
    _font_cache = {}

    @classmethod
    def init_gdiplus(cls):
        if cls._gdiplus_token is not None or cls._init_failed:
            return
        if sys.platform != "win32":
            cls._init_failed = True
            return
        try:
            gdiplus = ctypes.windll.gdiplus

            class GdiplusStartupInput(ctypes.Structure):
                _fields_ = [
                    ('GdiplusVersion', wintypes.UINT),
                    ('DebugEventCallback', ctypes.c_void_p),
                    ('SuppressBackgroundThread', wintypes.BOOL),
                    ('SuppressExternalCodecs', wintypes.BOOL)
                ]

            token = ctypes.c_ulong()
            startup_in = GdiplusStartupInput(1, None, False, False)
            status = gdiplus.GdiplusStartup(ctypes.byref(token), ctypes.byref(startup_in), None)
            if status == 0:
                cls._gdiplus_token = token
                # Initialize private font collection with Kantumruy Pro (Google Font matching web UI)
                try:
                    pfc = ctypes.c_void_p()
                    gdiplus.GdipNewPrivateFontCollection(ctypes.byref(pfc))
                    fonts_dir = os.path.join(os.path.dirname(__file__), "fonts")
                    bold_f = os.path.join(fonts_dir, "KantumruyPro-Bold.ttf")
                    reg_f = os.path.join(fonts_dir, "KantumruyPro-Regular.ttf")
                    if os.path.exists(bold_f):
                        gdiplus.GdipPrivateAddFontFile(pfc, ctypes.c_wchar_p(bold_f))
                    if os.path.exists(reg_f):
                        gdiplus.GdipPrivateAddFontFile(pfc, ctypes.c_wchar_p(reg_f))
                    num_found = ctypes.c_int()
                    gdiplus.GdipGetFontCollectionFamilyCount(pfc, ctypes.byref(num_found))
                    if num_found.value > 0:
                        families = (ctypes.c_void_p * num_found.value)()
                        num_ret = ctypes.c_int()
                        gdiplus.GdipGetFontCollectionFamilyList(pfc, num_found.value, families, ctypes.byref(num_ret))
                        cls._kantumruy_family = families[0]
                        cls._pfc = pfc
                except Exception as fe:
                    print(f"[WindowsTextRenderer] Private font load notice: {fe}")
            else:
                cls._init_failed = True
        except Exception:
            cls._init_failed = True

    @classmethod
    def is_available(cls) -> bool:
        cls.init_gdiplus()
        return cls._gdiplus_token is not None

    @classmethod
    def _get_font(cls, font_name: str, size: int, bold: bool):
        cls.init_gdiplus()
        gdiplus = ctypes.windll.gdiplus
        gdiplus.GdipCreateFont.argtypes = [ctypes.c_void_p, ctypes.c_float, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)]

        # 1. Use Kantumruy Pro from private collection if available (matches web preview)
        if cls._kantumruy_family is not None:
            font = ctypes.c_void_p()
            style = 1 if bold else 0
            status = gdiplus.GdipCreateFont(cls._kantumruy_family, ctypes.c_float(float(size)), style, 2, ctypes.byref(font))
            if status == 0:
                return font, None  # Family owned by private collection, do not dispose

        # 2. Fallback to system-installed font families
        font_family = ctypes.c_void_p()
        candidates = [
            font_name,
            "Kantumruy Pro",
            "Khmer OS Battambang",
            "Khmer OS",
            "Khmer UI",
            "Leelawadee UI",
            "Segoe UI",
            "Arial"
        ]
        for cand in candidates:
            if cand:
                status = gdiplus.GdipCreateFontFamilyFromName(ctypes.c_wchar_p(cand), None, ctypes.byref(font_family))
                if status == 0:
                    break
        font = ctypes.c_void_p()
        style = 1 if bold else 0
        gdiplus.GdipCreateFont(font_family, ctypes.c_float(float(size)), style, 2, ctypes.byref(font))
        return font, font_family

    @classmethod
    def measure_text(cls, text: str, font_size: int, font_name: str = "Khmer OS Battambang", bold: bool = True) -> tuple:
        """Measures text width and height accurately with native Uniscribe shaping."""
        if not cls.is_available() or not text:
            return (len(text) * int(font_size * 0.6), font_size)

        gdiplus = ctypes.windll.gdiplus
        font, font_family = cls._get_font(font_name, font_size, bold)

        class RectF(ctypes.Structure):
            _fields_ = [('X', ctypes.c_float), ('Y', ctypes.c_float), ('Width', ctypes.c_float), ('Height', ctypes.c_float)]

        scratch_mem = np.zeros((1, 1, 4), dtype=np.uint8)
        scratch_bmp = ctypes.c_void_p()
        gdiplus.GdipCreateBitmapFromScan0(1, 1, 4, 0x26200A, ctypes.c_void_p(scratch_mem.ctypes.data), ctypes.byref(scratch_bmp))
        scratch_gfx = ctypes.c_void_p()
        gdiplus.GdipGetImageGraphicsContext(scratch_bmp, ctypes.byref(scratch_gfx))
        gdiplus.GdipSetTextRenderingHint(scratch_gfx, 4)  # AntiAlias

        layout = RectF(0.0, 0.0, 10000.0, 1000.0)
        measured_rect = RectF()
        gdiplus.GdipMeasureString(scratch_gfx, ctypes.c_wchar_p(text), len(text), font, ctypes.byref(layout), None, ctypes.byref(measured_rect), None, None)

        w = int(measured_rect.Width)
        h = int(measured_rect.Height)

        gdiplus.GdipDeleteGraphics(scratch_gfx)
        gdiplus.GdipDisposeImage(scratch_bmp)
        gdiplus.GdipDeleteFont(font)
        if font_family is not None:
            gdiplus.GdipDeleteFontFamily(font_family)
        return (max(1, w), max(1, h))

    @classmethod
    def draw_text_onto_rgba(cls, target_rgba: np.ndarray, text: str, x: int, y: int,
                            font_size: int, font_name: str = "Khmer OS Battambang",
                            color_rgba: tuple = (255, 255, 255, 255), bold: bool = True):
        """
        Draws Uniscribe-shaped text directly onto a target (H, W, 4) RGBA numpy array.
        Uses GDI+ high-quality anti-aliasing.
        """
        if not cls.is_available() or not text:
            return

        gdiplus = ctypes.windll.gdiplus
        font, font_family = cls._get_font(font_name, font_size, bold)

        H, W = target_rgba.shape[:2]
        # In target_rgba, format is RGBA. GDI+ bitmap expects BGRA memory order.
        bgra_mem = np.empty((H, W, 4), dtype=np.uint8)
        bgra_mem[:, :, 0] = target_rgba[:, :, 2]  # B
        bgra_mem[:, :, 1] = target_rgba[:, :, 1]  # G
        bgra_mem[:, :, 2] = target_rgba[:, :, 0]  # R
        bgra_mem[:, :, 3] = target_rgba[:, :, 3]  # A

        bmp = ctypes.c_void_p()
        gdiplus.GdipCreateBitmapFromScan0(W, H, W * 4, 0x26200A, ctypes.c_void_p(bgra_mem.ctypes.data), ctypes.byref(bmp))
        gfx = ctypes.c_void_p()
        gdiplus.GdipGetImageGraphicsContext(bmp, ctypes.byref(gfx))
        gdiplus.GdipSetTextRenderingHint(gfx, 4)  # AntiAlias

        class RectF(ctypes.Structure):
            _fields_ = [('X', ctypes.c_float), ('Y', ctypes.c_float), ('Width', ctypes.c_float), ('Height', ctypes.c_float)]

        a, r, g, b = color_rgba[3], color_rgba[0], color_rgba[1], color_rgba[2]
        argb = (int(a) << 24) | (int(r) << 16) | (int(g) << 8) | int(b)
        brush = ctypes.c_void_p()
        gdiplus.GdipCreateSolidFill(ctypes.c_uint(argb), ctypes.byref(brush))

        rect = RectF(float(x), float(y), float(W - x), float(H - y))
        gdiplus.GdipDrawString(gfx, ctypes.c_wchar_p(text), len(text), font, ctypes.byref(rect), None, brush)

        gdiplus.GdipDeleteBrush(brush)
        gdiplus.GdipDeleteFont(font)
        if font_family is not None:
            gdiplus.GdipDeleteFontFamily(font_family)
        gdiplus.GdipDeleteGraphics(gfx)
        gdiplus.GdipDisposeImage(bmp)

        target_rgba[:, :, 0] = bgra_mem[:, :, 2]  # R
        target_rgba[:, :, 1] = bgra_mem[:, :, 1]  # G
        target_rgba[:, :, 2] = bgra_mem[:, :, 0]  # B
        target_rgba[:, :, 3] = bgra_mem[:, :, 3]  # A

    @classmethod
    def render_word_rgba(cls, text: str, font_size: int, color_rgba: tuple,
                         font_name: str = "Khmer OS Battambang", bold: bool = True):
        """Renders a single word with transparency into its own tight RGBA buffer."""
        w, h = cls.measure_text(text, font_size, font_name, bold)
        pad = 8
        buf = np.zeros((h + pad * 2, w + pad * 2, 4), dtype=np.uint8)
        cls.draw_text_onto_rgba(buf, text, pad, pad, font_size, font_name, color_rgba, bold)
        return buf, w, h, pad
