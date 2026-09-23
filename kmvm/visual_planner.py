"""
AI Visual Planner & Scene Director for KMVM
Implements:
- 18 Visual Styles:
  1. Khmer Cinematic
  2. Romantic
  3. Sad
  4. Emotional
  5. Love
  6. Traditional Khmer
  7. Cambodian Countryside
  8. Phnom Penh
  9. Night City
  10. Luxury
  11. Travel
  12. Nature
  13. Wedding
  14. Festival
  15. Dark Cinematic
  16. Dreamy
  17. Anime-inspired
  18. Abstract
  19. Music Performance
- Custom Natural Language Description Director
- User Media Mode (Ingests 20+ photos, video clips, album art)
- Beat-Synchronized Cuts & Camera Motion (Ken Burns, Punch Zoom, Pan)
- 🔒 Keep This Lock System for Granular Regeneration
"""

import os
import random
from typing import List, Dict, Any, Optional

STYLE_CONFIGS = {
    "Khmer Cinematic": {
        "palette": [(18, 22, 34), (218, 165, 32), (80, 20, 30)],  # Gold & Royal Khmer Crimson
        "contrast": 1.25,
        "motion_intensity": 1.0,
        "preferred_transitions": ["crossfade", "cinematic_zoom", "smooth_cut"]
    },
    "Romantic": {
        "palette": [(35, 15, 25), (255, 180, 195), (255, 215, 0)], # Soft Rose & Warm Gold
        "contrast": 1.05,
        "motion_intensity": 0.7,
        "preferred_transitions": ["crossfade", "slow_dissolve"]
    },
    "Sad": {
        "palette": [(10, 14, 22), (90, 110, 140), (160, 180, 200)], # Melancholic Slate & Deep Indigo
        "contrast": 0.95,
        "motion_intensity": 0.5,
        "preferred_transitions": ["slow_dissolve", "fade_to_black"]
    },
    "Emotional": {
        "palette": [(20, 16, 28), (140, 120, 180), (220, 200, 230)], # Mood Violet & Ethereal Mauve
        "contrast": 1.08,
        "motion_intensity": 0.75,
        "preferred_transitions": ["crossfade", "slow_dissolve"]
    },
    "Love": {
        "palette": [(40, 18, 26), (255, 120, 160), (255, 230, 180)], # Passionate Coral & Champagne
        "contrast": 1.15,
        "motion_intensity": 0.85,
        "preferred_transitions": ["crossfade", "smooth_cut"]
    },
    "Traditional Khmer": {
        "palette": [(30, 20, 10), (220, 170, 50), (140, 30, 30)],  # Angkor Sandstone & Apsara Gold
        "contrast": 1.20,
        "motion_intensity": 0.8,
        "preferred_transitions": ["crossfade", "gentle_slide"]
    },
    "Cambodian Countryside": {
        "palette": [(20, 30, 15), (70, 140, 60), (240, 210, 120)], # Lush Paddy Green & Sunrise Gold
        "contrast": 1.10,
        "motion_intensity": 0.9,
        "preferred_transitions": ["crossfade", "smooth_cut"]
    },
    "Phnom Penh": {
        "palette": [(12, 16, 24), (0, 210, 255), (255, 180, 60)],   # Riverside Cityscape & Warm Streetlights
        "contrast": 1.28,
        "motion_intensity": 1.2,
        "preferred_transitions": ["beat_cut", "cinematic_zoom"]
    },
    "Night City": {
        "palette": [(8, 10, 18), (0, 240, 255), (255, 0, 128)],     # Cyber Neon Glow & Deep Midnight
        "contrast": 1.35,
        "motion_intensity": 1.4,
        "preferred_transitions": ["beat_cut", "flash_zoom", "whip_pan"]
    },
    "Luxury": {
        "palette": [(16, 16, 20), (220, 190, 110), (245, 245, 250)], # Onyx, Platinum, & Polished Gold
        "contrast": 1.30,
        "motion_intensity": 0.85,
        "preferred_transitions": ["slow_dissolve", "crossfade"]
    },
    "Travel": {
        "palette": [(15, 25, 35), (40, 180, 210), (240, 170, 70)],  # Coastal Azure & Desert Amber
        "contrast": 1.18,
        "motion_intensity": 1.15,
        "preferred_transitions": ["whip_pan", "crossfade", "smooth_cut"]
    },
    "Nature": {
        "palette": [(18, 28, 18), (80, 160, 90), (180, 220, 140)],  # Cardamom Rainforest & Sunlight
        "contrast": 1.12,
        "motion_intensity": 0.8,
        "preferred_transitions": ["slow_dissolve", "crossfade"]
    },
    "Wedding": {
        "palette": [(30, 20, 24), (255, 215, 0), (255, 240, 245)],  # Traditional Wedding Gold & Pearl Ivory
        "contrast": 1.08,
        "motion_intensity": 0.7,
        "preferred_transitions": ["crossfade", "soft_blur_dissolve"]
    },
    "Festival": {
        "palette": [(30, 10, 25), (255, 60, 120), (255, 220, 0)],   # Water Festival Colors & Fireworks
        "contrast": 1.35,
        "motion_intensity": 1.5,
        "preferred_transitions": ["beat_cut", "flash_zoom"]
    },
    "Dark Cinematic": {
        "palette": [(6, 8, 12), (70, 80, 100), (140, 160, 190)],    # Moody Noir & Desaturated Cyan
        "contrast": 1.40,
        "motion_intensity": 0.9,
        "preferred_transitions": ["fade_to_black", "crossfade"]
    },
    "Dreamy": {
        "palette": [(25, 20, 35), (180, 160, 230), (255, 210, 230)],# Pastel Lavender & Soft Cloud Pink
        "contrast": 0.98,
        "motion_intensity": 0.6,
        "preferred_transitions": ["soft_blur_dissolve", "slow_dissolve"]
    },
    "Anime-inspired": {
        "palette": [(15, 18, 32), (90, 190, 255), (255, 110, 160)], # Vibrant Makoto Shinkai Sky & Cherry Blossom
        "contrast": 1.25,
        "motion_intensity": 1.2,
        "preferred_transitions": ["crossfade", "cinematic_zoom"]
    },
    "Abstract": {
        "palette": [(12, 10, 20), (120, 0, 255), (0, 255, 180)],    # Morphing Geometry & Neon Flux
        "contrast": 1.30,
        "motion_intensity": 1.3,
        "preferred_transitions": ["beat_cut", "flash_zoom"]
    },
    "Music Performance": {
        "palette": [(10, 12, 18), (255, 200, 40), (255, 30, 80)],   # Stage Spotlights & Live Concert Fog
        "contrast": 1.32,
        "motion_intensity": 1.35,
        "preferred_transitions": ["beat_cut", "whip_pan"]
    }
}

class VisualClip:
    """Represents a visual shot on the video track with Ken Burns and transitions."""

    def __init__(
        self,
        clip_id: int,
        start: float,
        end: float,
        section_name: str,
        media_path: Optional[str] = None,
        camera_motion: str = "zoom_in",   # zoom_in | zoom_out | pan_left | pan_right | punch_zoom | slow_zoom_in
        transition_in: str = "crossfade",
        transition_duration: float = 0.6,
        color_tint: tuple = (255, 255, 255)
    ):
        self.clip_id = clip_id
        self.start = start
        self.end = end
        self.section_name = section_name
        self.media_path = media_path
        self.camera_motion = camera_motion
        self.transition_in = transition_in
        self.transition_duration = transition_duration
        self.color_tint = color_tint
        self.locked = False               # 🔒 Keep This lock flag


class VisualPlanner:
    """Translates musical structure, 18 styles, custom prompts, and user media into cinematic shots."""

    def __init__(self, style_name: str = "Khmer Cinematic", custom_description: str = ""):
        self.style_name = style_name if style_name in STYLE_CONFIGS else "Khmer Cinematic"
        self.custom_description = custom_description
        self.config = self._resolve_style_config()
        self.clips: List[VisualClip] = []

    def _resolve_style_config(self) -> Dict[str, Any]:
        """Resolves config from preset or extracts parameters from custom prompt description."""
        base = dict(STYLE_CONFIGS.get(self.style_name, STYLE_CONFIGS["Khmer Cinematic"]))

        if self.custom_description:
            desc = self.custom_description.lower()
            # Dynamic prompt parser
            if "night" in desc or "phnom penh" in desc:
                base["palette"] = [(8, 10, 18), (0, 240, 255), (255, 180, 40)]
                base["motion_intensity"] = 1.3
            elif "sad" in desc or "miss" in desc or "cry" in desc:
                base["palette"] = [(12, 14, 22), (90, 110, 140), (180, 195, 220)]
                base["motion_intensity"] = 0.6
                base["preferred_transitions"] = ["slow_dissolve", "crossfade"]
            elif "traditional" in desc or "angkor" in desc or "temple" in desc:
                base["palette"] = [(30, 20, 10), (220, 170, 50), (140, 30, 30)]
            elif "countryside" in desc or "nature" in desc or "village" in desc:
                base["palette"] = [(18, 28, 16), (80, 160, 80), (240, 210, 120)]

        return base

    def plan_timeline(
        self,
        sections: list,
        beats: List[float],
        user_media_files: Optional[List[str]] = None,
        quality_level: str = "Cinematic"
    ) -> List[VisualClip]:
        """
        Plans all visual cuts, Ken Burns camera curves, and transitions matching song sections.
        """
        self.clips.clear()
        media_pool = list(user_media_files) if user_media_files else []
        random.shuffle(media_pool)
        media_idx = 0
        clip_counter = 0

        for sec in sections:
            sec_start = sec.start
            sec_end = sec.end
            sec_dur = sec_end - sec_start
            sec_name = sec.name.upper()

            # Pacing based on section energy and musical rules
            if "FINAL CHORUS" in sec_name:
                shot_target_dur = 2.0
                trans_type = "beat_cut"
                motions = ["punch_zoom", "pan_right", "zoom_in"]
            elif "CHORUS" in sec_name:
                shot_target_dur = 2.5
                trans_type = "beat_cut" if quality_level != "Quick" else "crossfade"
                motions = ["punch_zoom", "zoom_in", "pan_right"]
            elif "PRE-CHORUS" in sec_name:
                shot_target_dur = 3.0
                trans_type = "crossfade"
                motions = ["zoom_in", "pan_left"]
            elif "INTRO" in sec_name or "OUTRO" in sec_name:
                shot_target_dur = 6.5
                trans_type = "slow_dissolve"
                motions = ["slow_zoom_in", "pan_left"]
            elif "BRIDGE" in sec_name:
                shot_target_dur = 3.8
                trans_type = "crossfade"
                motions = ["zoom_out", "pan_right"]
            else: # VERSE
                shot_target_dur = 4.2
                trans_type = "crossfade"
                motions = ["zoom_in", "zoom_out", "pan_left"]

            num_shots = max(1, int(round(sec_dur / shot_target_dur)))
            actual_shot_dur = sec_dur / num_shots

            for s_idx in range(num_shots):
                c_start = sec_start + s_idx * actual_shot_dur
                c_end = c_start + actual_shot_dur

                # Snap to closest beat if within 0.25s
                for b in beats:
                    if abs(b - c_start) < 0.25 and c_start > 0.4:
                        c_start = b
                        break

                media_path = None
                if media_pool:
                    media_path = media_pool[media_idx % len(media_pool)]
                    media_idx += 1

                motion = random.choice(motions)
                color = random.choice(self.config["palette"])

                clip = VisualClip(
                    clip_id=clip_counter,
                    start=round(c_start, 2),
                    end=round(c_end, 2),
                    section_name=sec_name,
                    media_path=media_path,
                    camera_motion=motion,
                    transition_in=trans_type,
                    transition_duration=0.4 if "CHORUS" in sec_name else 0.8,
                    color_tint=color
                )
                self.clips.append(clip)
                clip_counter += 1

        return self.clips

    def regenerate_section(self, section_name: str, beats: List[float]) -> List[VisualClip]:
        """Regenerates a specific section while strictly respecting locked items (🔒 Keep This)."""
        for clip in self.clips:
            if clip.section_name == section_name and not clip.locked:
                motions = ["zoom_in", "zoom_out", "pan_left", "pan_right", "punch_zoom"]
                clip.camera_motion = random.choice(motions)
                clip.color_tint = random.choice(self.config["palette"])
        return self.clips

    def regenerate_all_unlocked(self) -> int:
        """Regenerates all clips that are not locked."""
        count = 0
        motions = ["zoom_in", "zoom_out", "pan_left", "pan_right", "punch_zoom"]
        for clip in self.clips:
            if not clip.locked:
                clip.camera_motion = random.choice(motions)
                clip.color_tint = random.choice(self.config["palette"])
                count += 1
        return count

    def set_lock_all(self, locked: bool = True):
        for clip in self.clips:
            clip.locked = locked
