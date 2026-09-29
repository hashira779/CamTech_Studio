"""
Advanced Theme Renderers for VIDA Export Engine
Ports all frontend JS themes to Python/OpenCV for pixel-perfect export matching.
"""

import math
import random
import numpy as np
import cv2


class AdvancedThemeRenderer:
    """Manages state and rendering for all advanced themes (quantum_vortex, neural_synapse, etc.)."""

    def __init__(self, width, height):
        self.width = width
        self.height = height
        random.seed(42)
        np.random.seed(42)

        # quantum_vortex state
        self._vortex_angle = 0.0
        self._vortex_particles = [
            {'radius': random.random() * 650 + 60, 'angle': random.random() * math.pi * 2,
             'speed': random.random() * 0.02 + 0.008, 'size': random.random() * 3.5 + 1.2}
            for _ in range(140)
        ]

        # neural_synapse state
        self._neural_nodes = [
            {'x': random.random() * width, 'y': random.random() * height,
             'vx': (random.random() - 0.5) * 1.2, 'vy': (random.random() - 0.5) * 1.2,
             'baseR': random.random() * 4 + 2, 'bin': random.randint(0, 63), 'energy': 0.0}
            for _ in range(48)
        ]

        # hyper_liquid state
        self._liquid_phase = 0.0
        self._liquid_droplets = [
            {'x': random.random() * width, 'y': random.random() * height,
             'vy': -(random.random() * 1.5 + 0.5), 'r': random.random() * 8 + 3,
             'phase': random.random() * math.pi * 2, 'bin': random.randint(0, 63)}
            for _ in range(40)
        ]

        # angkor_mandala state
        self._mandala_rotation = 0.0

        # hologram_hud state
        self._radar_angle = 0.0

        # aurora_borealis state
        self._aurora_time = 0.0
        self._aurora_ribbons = [
            {'phase': random.random() * math.pi * 2, 'speed': 0.003 + random.random() * 0.005,
             'amplitude': 0.15 + random.random() * 0.25, 'yOffset': 0.2 + (i / 7) * 0.55}
            for i in range(7)
        ]

        # dna_helix state
        self._helix_time = 0.0

        # sonic_nebula state
        self._nebula_time = 0.0
        self._nebula_prev_bass = 0.0
        self._nebula_explosions = []
        self._nebula_points = [
            {'angle': random.random() * math.pi * 2, 'dist': random.random() * 0.4 + 0.05,
             'baseSize': random.random() * 40 + 10, 'speed': (random.random() - 0.5) * 0.003,
             'colorMix': random.random(), 'opacity': random.random() * 0.3 + 0.05,
             'layer': random.randint(0, 2)}
            for _ in range(200)
        ]

        # Shared overlay buffer
        self._overlay = np.zeros((height, width, 3), dtype=np.uint8)

    def _pal_bgr(self, palette, key):
        c = palette[key]
        return (int(c[2]), int(c[1]), int(c[0]))

    def _interp_bgr(self, palette, t):
        p, s = palette["primary"], palette["secondary"]
        r = int(p[0] * (1 - t) + s[0] * t)
        g = int(p[1] * (1 - t) + s[1] * t)
        b = int(p[2] * (1 - t) + s[2] * t)
        return (b, g, r)

    def _draw_center_emblem(self, frame, cx, cy, radius, palette, logo_circle, logo_cache, bg_color=(10, 14, 24)):
        """Draws center dark circle + glowing ring + logo (shared across all themes)."""
        cv2.circle(frame, (cx, cy), radius, bg_color, -1, cv2.LINE_AA)
        pri_bgr = self._pal_bgr(palette, "primary")
        cv2.circle(frame, (cx, cy), radius, pri_bgr, 3, cv2.LINE_AA)
        # Outer glow ring
        glow_bgr = self._pal_bgr(palette, "glow") if "glow" in palette and isinstance(palette.get("glow"), (list, tuple)) else pri_bgr
        cv2.circle(frame, (cx, cy), radius + 2, glow_bgr, 1, cv2.LINE_AA)

        # Draw logo if available
        if logo_circle is not None:
            r_q = int(radius // 2 * 2)
            if r_q not in logo_cache:
                target_d = int(r_q * 2.0 * 0.92)
                if target_d > 10:
                    resized = cv2.resize(logo_circle, (target_d, target_d), interpolation=cv2.INTER_LINEAR)
                    a = resized[:, :, 3:4].astype(np.float32) / 255.0
                    logo_cache[r_q] = (target_d, target_d, 1.0 - a, resized[:, :, :3].astype(np.float32) * a)
                else:
                    logo_cache[r_q] = None
            cached = logo_cache.get(r_q)
            if cached is not None:
                sw, sh, inv_a, premul = cached
                lx1, ly1 = cx - sw // 2, cy - sh // 2
                lx2, ly2 = lx1 + sw, ly1 + sh
                if lx1 >= 0 and ly1 >= 0 and lx2 <= self.width and ly2 <= self.height:
                    frame[ly1:ly2, lx1:lx2] = (frame[ly1:ly2, lx1:lx2] * inv_a + premul).astype(np.uint8)

    # ═══════════════════════════════════════════════════════════════
    # 1. QUANTUM VORTEX
    # ═══════════════════════════════════════════════════════════════
    def render_quantum_vortex(self, frame, spectrum, bass, onset, anim_time, palette, logo_circle, logo_cache):
        w, h = self.width, self.height
        cx, cy = w // 2, h // 2
        base_r = int(min(w, h) * 0.11)
        event_horizon = int(base_r * (1 + bass * 0.45))
        pri_bgr = self._pal_bgr(palette, "primary")
        sec_bgr = self._pal_bgr(palette, "secondary")

        self._vortex_angle += 0.012 + bass * 0.04

        # 1. Gravitational lensing rings
        for r in range(14):
            ring_r = event_horizon + (r + 1) * 32 + int((spectrum[r % len(spectrum)]) * 85)
            alpha = max(0.05, 0.4 - r * 0.028 + bass * 0.2)
            col = pri_bgr if r % 2 == 0 else sec_bgr
            dim_col = tuple(int(c * alpha) for c in col)
            thickness = max(1, int(1.5 + (3 * bass if r == 0 else 0)))
            cv2.circle(frame, (cx, cy), ring_r, dim_col, thickness, cv2.LINE_AA)

        # 2. Spiral arms
        count = len(spectrum)
        for a in range(6):
            arm_offset = (a * (math.pi * 2 / 6)) + self._vortex_angle
            pts = []
            for p in range(48):
                prog = p / 48.0
                bar_val = spectrum[int(prog * (count - 1))]
                spiral_dist = event_horizon * 0.9 + prog * (min(w, h) * 0.65) + bar_val * 40
                theta = arm_offset + prog * 4.2 + bass * 0.3 * math.sin(prog * 10)
                pts.append([int(cx + math.cos(theta) * spiral_dist), int(cy + math.sin(theta) * spiral_dist)])
            if len(pts) > 1:
                arm_col = self._interp_bgr(palette, a / 6.0)
                dim = tuple(int(c * (0.6 + bass * 0.3)) for c in arm_col)
                cv2.polylines(frame, [np.array(pts, np.int32)], False, dim, max(1, int(2.2 + bass * 2)), cv2.LINE_AA)

        # 3. Inward particles
        for pt in self._vortex_particles:
            pt['angle'] += pt['speed'] * (1 + bass * 2.5)
            pt['radius'] -= 0.4 + bass * 1.8
            if pt['radius'] < event_horizon * 0.8:
                pt['radius'] = min(w, h) * 0.55 + random.random() * 200
                pt['angle'] = random.random() * math.pi * 2
            px = int(cx + math.cos(pt['angle']) * pt['radius'])
            py = int(cy + math.sin(pt['angle']) * pt['radius'])
            bar_idx = int((pt['radius'] / 600) * count) % count
            p_size = max(1, int(pt['size'] * (1 + spectrum[bar_idx] * 2.2)))
            col = pri_bgr if random.random() > 0.5 else sec_bgr
            cv2.circle(frame, (px, py), p_size, col, -1, cv2.LINE_AA)

        # 4. Center black hole
        self._draw_center_emblem(frame, cx, cy, event_horizon, palette, logo_circle, logo_cache, (2, 3, 8))

    # ═══════════════════════════════════════════════════════════════
    # 2. NEURAL SYNAPSE
    # ═══════════════════════════════════════════════════════════════
    def render_neural_synapse(self, frame, spectrum, bass, onset, anim_time, palette, logo_circle, logo_cache):
        w, h = self.width, self.height
        cx, cy = w // 2, h // 2
        core_r = int(min(w, h) * 0.1)
        pri_bgr = self._pal_bgr(palette, "primary")
        sec_bgr = self._pal_bgr(palette, "secondary")
        count = len(spectrum)

        # Update nodes
        for node in self._neural_nodes:
            bar_val = spectrum[node['bin'] % count]
            node['x'] += node['vx'] * (1 + bass * 2)
            node['y'] += node['vy'] * (1 + bass * 2)
            if node['x'] < 50 or node['x'] > w - 50: node['vx'] *= -1
            if node['y'] < 50 or node['y'] > h - 50: node['vy'] *= -1
            node['energy'] = node['energy'] * 0.85 + bar_val * 0.45

            cur_r = max(1, int(node['baseR'] * (1 + node['energy'] * 3 + bass * 1.5)))
            col = sec_bgr if node['energy'] > 0.4 else pri_bgr
            cv2.circle(frame, (int(node['x']), int(node['y'])), cur_r, col, -1, cv2.LINE_AA)

        # Draw connections
        for i in range(len(self._neural_nodes)):
            n1 = self._neural_nodes[i]
            for j in range(i + 1, len(self._neural_nodes)):
                n2 = self._neural_nodes[j]
                dx, dy = n2['x'] - n1['x'], n2['y'] - n1['y']
                dist = math.sqrt(dx * dx + dy * dy)
                max_dist = 180 + bass * 80
                if dist < max_dist:
                    prox = 1 - dist / max_dist
                    power = (n1['energy'] + n2['energy']) * 0.5
                    col = sec_bgr if power > 0.35 else pri_bgr
                    alpha = prox * (0.6 if power > 0.35 else 0.35)
                    dim_col = tuple(int(c * alpha) for c in col)
                    thick = max(1, int(1.2 + (power * 2 if power > 0.35 else 0)))
                    cv2.line(frame, (int(n1['x']), int(n1['y'])), (int(n2['x']), int(n2['y'])), dim_col, thick, cv2.LINE_AA)

        # Center core
        pulse_r = int(core_r * (1 + bass * 0.35))
        self._draw_center_emblem(frame, cx, cy, pulse_r, palette, logo_circle, logo_cache, (10, 15, 28))

    # ═══════════════════════════════════════════════════════════════
    # 3. HYPER LIQUID
    # ═══════════════════════════════════════════════════════════════
    def render_hyper_liquid(self, frame, spectrum, bass, onset, anim_time, palette, logo_circle, logo_cache):
        w, h = self.width, self.height
        cx, cy = w // 2, h // 2
        core_r = int(min(w, h) * 0.11)
        count = len(spectrum)

        self._liquid_phase += 0.02 + bass * 0.05
        overlay = self._overlay

        # 1. Multi-layer liquid ribbons
        n_pts = 60
        x_coords = np.linspace(0, w, n_pts, dtype=np.float32)
        interp_spec = np.interp(np.linspace(0, count - 1, n_pts), np.arange(count), spectrum).astype(np.float32)

        for layer in range(5):
            base_y = cy + (layer - 2) * 55
            amp = (60 + layer * 25) * (1 + bass * 1.6)
            wave1 = np.sin(self._liquid_phase * 1.5 + np.arange(n_pts) * 0.15 + layer) * amp * 0.4
            wave2 = np.cos(self._liquid_phase * 0.8 + np.arange(n_pts) * 0.3 - layer) * amp * 0.25
            sound = interp_spec * amp * 1.2
            wave_y = base_y + wave1 + wave2 - sound

            pts_top = np.stack([x_coords, wave_y], axis=1)
            pts_bottom = np.array([[w, h], [0, h]], dtype=np.float32)
            poly = np.vstack([pts_top, pts_bottom]).astype(np.int32)

            col = self._interp_bgr(palette, layer / 5.0)
            opacity = 0.18 + layer * 0.06
            overlay.fill(0)
            cv2.fillPoly(overlay, [poly], col)
            cv2.addWeighted(overlay, float(opacity), frame, 1.0, 0, frame)

            # Crest stroke
            crest_pts = pts_top.astype(np.int32).reshape((-1, 1, 2))
            cv2.polylines(frame, [crest_pts], False, (255, 255, 255), max(1, 2 - (layer > 0)), cv2.LINE_AA)

        # 2. Floating droplets
        pri_bgr = self._pal_bgr(palette, "primary")
        for d in self._liquid_droplets:
            bar_amp = spectrum[d['bin'] % count]
            d['y'] += d['vy'] * (1 + bass * 3)
            d['x'] += math.sin(self._liquid_phase + d['phase']) * 1.2
            if d['y'] < -30: d['y'] = h + 20; d['x'] = random.random() * w
            dr = max(1, int(d['r'] * (1 + bar_amp * 2.5 + bass)))
            cv2.circle(frame, (int(d['x']), int(d['y'])), dr, pri_bgr, -1, cv2.LINE_AA)
            # Specular highlight
            cv2.circle(frame, (int(d['x'] - dr * 0.3), int(d['y'] - dr * 0.3)), max(1, int(dr * 0.3)), (255, 255, 255), -1, cv2.LINE_AA)

        # 3. Wobbly center
        pulse_r = int(core_r * (1 + bass * 0.3))
        pts_wobble = []
        for a_step in np.arange(0, math.pi * 2, 0.05):
            wobble = math.sin(a_step * 4 + self._liquid_phase * 2) * (6 + bass * 14)
            r = pulse_r + wobble
            pts_wobble.append([int(cx + math.cos(a_step) * r), int(cy + math.sin(a_step) * r)])
        if pts_wobble:
            pts_arr = np.array(pts_wobble, np.int32)
            cv2.fillPoly(frame, [pts_arr], (22, 12, 9))
            cv2.polylines(frame, [pts_arr], True, pri_bgr, max(1, int(3 + bass * 3)), cv2.LINE_AA)
        # Logo inside
        if logo_circle is not None:
            self._draw_center_emblem(frame, cx, cy, int(pulse_r * 0.85), palette, logo_circle, logo_cache, (22, 12, 9))

    # ═══════════════════════════════════════════════════════════════
    # 4. ANGKOR MANDALA
    # ═══════════════════════════════════════════════════════════════
    def render_angkor_mandala(self, frame, spectrum, bass, onset, anim_time, palette, logo_circle, logo_cache):
        w, h = self.width, self.height
        cx, cy = w // 2, h // 2
        base_r = int(min(w, h) * 0.12)
        pri_bgr = self._pal_bgr(palette, "primary")
        sec_bgr = self._pal_bgr(palette, "secondary")
        count = len(spectrum)

        self._mandala_rotation += 0.008 + bass * 0.02

        # 1. Sacred radiance rays
        for i in range(48):
            angle = (i * (math.pi * 2 / 48)) + self._mandala_rotation * 0.5
            bar_amp = spectrum[int((i / 48) * count) % count]
            inner_r = int(base_r * 1.8 + bass * 20)
            outer_r = int(inner_r + 60 + bar_amp * 240)
            x1 = int(cx + math.cos(angle) * inner_r)
            y1 = int(cy + math.sin(angle) * inner_r)
            x2 = int(cx + math.cos(angle) * outer_r)
            y2 = int(cy + math.sin(angle) * outer_r)
            col = pri_bgr if i % 2 == 0 else sec_bgr
            alpha = 0.5 + bar_amp * 0.5
            dim_col = tuple(int(c * alpha) for c in col)
            cv2.line(frame, (x1, y1), (x2, y2), dim_col, max(1, int(1.8 + bar_amp * 3)), cv2.LINE_AA)

        # 2. Lotus petal gears
        gear_tiers = [
            {'petals': 12, 'radius': base_r * 1.6, 'speed': -1},
            {'petals': 16, 'radius': base_r * 1.3, 'speed': 1.4},
            {'petals': 8, 'radius': base_r * 1.05, 'speed': -1.8}
        ]
        for g in gear_tiers:
            gear_angle = self._mandala_rotation * g['speed']
            pts = []
            for p in range(g['petals']):
                pa = (p * (math.pi * 2 / g['petals'])) + gear_angle
                petal_amp = (spectrum[p % count]) * 35
                r_outer = g['radius'] + 18 + petal_amp + bass * 15
                r_inner = g['radius'] - 8
                px1 = int(cx + math.cos(pa - 0.15) * r_inner)
                py1 = int(cy + math.sin(pa - 0.15) * r_inner)
                px_tip = int(cx + math.cos(pa) * r_outer)
                py_tip = int(cy + math.sin(pa) * r_outer)
                px2 = int(cx + math.cos(pa + 0.15) * r_inner)
                py2 = int(cy + math.sin(pa + 0.15) * r_inner)
                pts.extend([[px1, py1], [px_tip, py_tip], [px2, py2]])
            if pts:
                alpha = 0.75 + bass * 0.25
                col = tuple(int(c * alpha) for c in pri_bgr)
                cv2.polylines(frame, [np.array(pts, np.int32)], True, col, max(1, int(2 + bass * 1.5)), cv2.LINE_AA)

        # 3. Center emblem
        emblem_r = int(base_r * (1 + bass * 0.25))
        self._draw_center_emblem(frame, cx, cy, emblem_r, palette, logo_circle, logo_cache, (8, 14, 18))

    # ═══════════════════════════════════════════════════════════════
    # 5. HOLOGRAM HUD
    # ═══════════════════════════════════════════════════════════════
    def render_hologram_hud(self, frame, spectrum, bass, onset, anim_time, palette, logo_circle, logo_cache):
        w, h = self.width, self.height
        cx, cy = w // 2, h // 2
        base_r = int(min(w, h) * 0.12)
        outer_r = int(min(w, h) * 0.42)
        pri_bgr = self._pal_bgr(palette, "primary")
        sec_bgr = self._pal_bgr(palette, "secondary")
        count = len(spectrum)

        self._radar_angle += 0.025 + bass * 0.05

        # 1. Outer ring
        cv2.circle(frame, (cx, cy), outer_r, tuple(int(c * 0.2) for c in pri_bgr), 1, cv2.LINE_AA)

        # 2. Compass ticks
        for t in range(72):
            angle = t * (math.pi * 2 / 72)
            is_major = t % 6 == 0
            tick_len = 14 if is_major else 6
            r1 = outer_r - tick_len
            x1 = int(cx + math.cos(angle) * r1)
            y1 = int(cy + math.sin(angle) * r1)
            x2 = int(cx + math.cos(angle) * outer_r)
            y2 = int(cy + math.sin(angle) * outer_r)
            col = sec_bgr if is_major else tuple(int(c * 0.3) for c in pri_bgr)
            thick = 2 if is_major else 1
            cv2.line(frame, (x1, y1), (x2, y2), col, thick, cv2.LINE_AA)

        # 3. Circular meter arcs
        meter_r = outer_r - 35
        for s in range(36):
            bar_val = spectrum[int((s / 36) * count) % count]
            for side in (-1, 1):
                angle = (math.pi / 2) + side * (s * 0.075 + 0.1)
                seg_len = int(6 + bar_val * 45)
                p1x = int(cx + math.cos(angle) * meter_r)
                p1y = int(cy + math.sin(angle) * meter_r)
                p2x = int(cx + math.cos(angle) * (meter_r + seg_len))
                p2y = int(cy + math.sin(angle) * (meter_r + seg_len))
                col = sec_bgr if bar_val > 0.6 else pri_bgr
                cv2.line(frame, (p1x, p1y), (p2x, p2y), col, 3, cv2.LINE_AA)

        # 4. Radar sweep line
        rx = int(cx + math.cos(self._radar_angle) * (outer_r * 0.95))
        ry = int(cy + math.sin(self._radar_angle) * (outer_r * 0.95))
        cv2.line(frame, (cx, cy), (rx, ry), sec_bgr, max(1, int(2 + bass * 2)), cv2.LINE_AA)

        # 5. HUD brackets
        bd = int(base_r * 1.5 + bass * 15)
        bl = 22
        for bx, by, dx, dy in [(0, -bd, bl, 0), (0, bd, bl, 0), (-bd, 0, 0, bl), (bd, 0, 0, bl)]:
            cv2.line(frame, (cx + bx - dx, cy + by - dy), (cx + bx + dx, cy + by + dy), sec_bgr, 2, cv2.LINE_AA)

        # 6. Center core
        pulse_r = int(base_r * (1 + bass * 0.25))
        self._draw_center_emblem(frame, cx, cy, pulse_r, palette, logo_circle, logo_cache, (18, 9, 4))

    # ═══════════════════════════════════════════════════════════════
    # 6. AURORA BOREALIS
    # ═══════════════════════════════════════════════════════════════
    def render_aurora_borealis(self, frame, spectrum, bass, onset, anim_time, palette, logo_circle, logo_cache):
        w, h = self.width, self.height
        count = len(spectrum)
        pri_bgr = self._pal_bgr(palette, "primary")
        sec_bgr = self._pal_bgr(palette, "secondary")
        overlay = self._overlay

        self._aurora_time += 0.018

        # 1. Starfield
        for i in range(60):
            sx = int((math.sin(i * 127.1 + self._aurora_time * 0.1) * 0.5 + 0.5) * w)
            sy = int((math.cos(i * 311.7 + self._aurora_time * 0.05) * 0.5 + 0.5) * h * 0.6)
            twinkle = math.sin(self._aurora_time * 2 + i) * 0.5 + 0.5
            brightness = int((0.15 + twinkle * 0.5) * 255)
            cv2.circle(frame, (sx, sy), max(1, int(0.5 + twinkle * 1.2)), (brightness, brightness, brightness), -1, cv2.LINE_AA)

        # 2. Aurora silk ribbons
        n_pts = 80
        x_coords = np.linspace(0, w, n_pts, dtype=np.float32)

        for r_idx, ribbon in enumerate(self._aurora_ribbons):
            ribbon['phase'] += ribbon['speed'] + bass * 0.02
            # Calculate band energy
            band_start = int((r_idx / 7) * count)
            band_end = int(((r_idx + 1) / 7) * count)
            band_energy = np.mean(spectrum[band_start:band_end]) if band_end > band_start else 0

            base_y = ribbon['yOffset'] * h
            t_arr = np.linspace(0, 1, n_pts)
            wave1 = np.sin(t_arr * math.pi * 3 + ribbon['phase']) * ribbon['amplitude'] * h
            wave2 = np.sin(t_arr * math.pi * 5 - ribbon['phase'] * 1.3) * ribbon['amplitude'] * h * 0.4
            wave3 = np.cos(t_arr * math.pi * 2 + ribbon['phase'] * 0.7) * ribbon['amplitude'] * h * 0.2
            bass_wave = np.sin(t_arr * math.pi * 1.5 + self._aurora_time) * bass * h * 0.12
            freq_react = band_energy * np.sin(t_arr * math.pi * 4 + ribbon['phase'] * 2) * h * 0.15
            wave_y = base_y + wave1 + wave2 + wave3 + bass_wave + freq_react

            col = self._interp_bgr(palette, r_idx / 7.0)
            intensity = 0.08 + band_energy * 0.15 + bass * 0.08

            # Fill ribbon
            pts_top = np.stack([x_coords, wave_y.astype(np.float32)], axis=1)
            pts_bottom = np.array([[w, h], [0, h]], dtype=np.float32)
            poly = np.vstack([pts_top, pts_bottom]).astype(np.int32)
            overlay.fill(0)
            cv2.fillPoly(overlay, [poly], col)
            cv2.addWeighted(overlay, float(min(0.5, intensity * 1.8)), frame, 1.0, 0, frame)

            # Crest stroke
            crest_pts = pts_top.astype(np.int32).reshape((-1, 1, 2))
            stroke_alpha = 0.4 + band_energy * 0.5
            stroke_col = tuple(int(c * stroke_alpha) for c in col)
            cv2.polylines(frame, [crest_pts], False, stroke_col, max(1, int(1.5 + bass * 2)), cv2.LINE_AA)

        # 3. Horizon line
        horizon_y = int(h * 0.82)
        cv2.line(frame, (0, horizon_y), (w, horizon_y), tuple(int(c * (0.2 + bass * 0.4)) for c in pri_bgr), 2, cv2.LINE_AA)

        # 4. Frequency orbs
        orb_count = min(count, 32)
        for i in range(orb_count):
            val = spectrum[i * (count // orb_count) % count]
            if val < 0.05: continue
            ox = int((i / orb_count) * w + w / orb_count / 2)
            oy = int(horizon_y - val * h * 0.15 - 10)
            orb_r = max(1, int(2 + val * 8 + bass * 3))
            col = self._interp_bgr(palette, i / orb_count)
            cv2.circle(frame, (ox, oy), orb_r, col, -1, cv2.LINE_AA)

    # ═══════════════════════════════════════════════════════════════
    # 7. DNA HELIX
    # ═══════════════════════════════════════════════════════════════
    def render_dna_helix(self, frame, spectrum, bass, onset, anim_time, palette, logo_circle, logo_cache):
        w, h = self.width, self.height
        cx, cy = w // 2, h // 2
        pri_bgr = self._pal_bgr(palette, "primary")
        sec_bgr = self._pal_bgr(palette, "secondary")
        count = len(spectrum)

        self._helix_time += 0.022 + bass * 0.015
        helix_r = int(min(w, h) * 0.12)
        helix_len = int(h * 0.8)
        start_y = (h - helix_len) // 2
        segments = 120
        twist = 3.5

        # 1. DNA rungs
        for i in range(0, segments, 4):
            t = i / segments
            y = int(start_y + t * helix_len)
            bar_val = spectrum[int(t * count) % count]
            angle = t * math.pi * twist + self._helix_time
            dynamic_r = helix_r + bar_val * helix_r * 1.5
            x1 = int(cx + math.sin(angle) * dynamic_r)
            x2 = int(cx + math.sin(angle + math.pi) * dynamic_r)
            alpha = 0.15 + bar_val * 0.4 + bass * 0.1
            col = self._interp_bgr(palette, t)
            dim_col = tuple(int(c * alpha) for c in col)
            cv2.line(frame, (x1, y), (x2, y), dim_col, max(1, int(2 + bar_val * 3 + bass * 2)), cv2.LINE_AA)
            # Nucleotide nodes
            node_r = max(1, int(2.5 + bar_val * 4))
            cv2.circle(frame, (x1, y), node_r, pri_bgr, -1, cv2.LINE_AA)
            cv2.circle(frame, (x2, y), node_r, sec_bgr, -1, cv2.LINE_AA)

        # 2. Helix strands
        for strand_offset in (0, math.pi):
            pts = []
            for i in range(segments + 1):
                t = i / segments
                y = int(start_y + t * helix_len)
                bar_val = spectrum[int(t * count) % count]
                angle = t * math.pi * twist + self._helix_time + strand_offset
                dynamic_r = helix_r + bar_val * helix_r * 1.5 + bass * helix_r * 0.3
                x = int(cx + math.sin(angle) * dynamic_r)
                pts.append([x, y])
            col = pri_bgr if strand_offset == 0 else sec_bgr
            cv2.polylines(frame, [np.array(pts, np.int32)], False, col, max(1, int(3 + bass * 2)), cv2.LINE_AA)

        # 3. Phosphor particles
        for i in range(40):
            pt_t = (i / 40 + self._helix_time * 0.05) % 1
            py = int(start_y + pt_t * helix_len)
            bar_val = spectrum[int(pt_t * count) % count]
            angle = pt_t * math.pi * twist + self._helix_time
            spread = helix_r * 2.5 + bar_val * helix_r
            px = int(cx + math.sin(angle + i * 0.5) * spread * (0.3 + random.random() * 0.7))
            p_size = max(1, int(1 + bar_val * 3))
            col = self._interp_bgr(palette, i / 40)
            alpha = 0.1 + bar_val * 0.5 + bass * 0.2
            dim_col = tuple(int(c * alpha) for c in col)
            cv2.circle(frame, (px, py), p_size, dim_col, -1, cv2.LINE_AA)

        # 4. Center energy core
        core_r = max(5, int(15 + bass * 25))
        cv2.circle(frame, (cx, cy), core_r, (255, 255, 255), -1, cv2.LINE_AA)
        cv2.circle(frame, (cx, cy), core_r + 3, pri_bgr, 2, cv2.LINE_AA)

    # ═══════════════════════════════════════════════════════════════
    # 8. SONIC NEBULA
    # ═══════════════════════════════════════════════════════════════
    def render_sonic_nebula(self, frame, spectrum, bass, onset, anim_time, palette, logo_circle, logo_cache):
        w, h = self.width, self.height
        cx, cy = w // 2, h // 2
        max_r = int(min(w, h) * 0.45)
        pri_bgr = self._pal_bgr(palette, "primary")
        sec_bgr = self._pal_bgr(palette, "secondary")
        count = len(spectrum)
        overlay = self._overlay

        self._nebula_time += 0.012

        # 1. Bass-triggered explosions
        if bass > 0.6 and bass > self._nebula_prev_bass + 0.1:
            for _ in range(12):
                angle = random.random() * math.pi * 2
                speed = 2 + random.random() * 6
                self._nebula_explosions.append({
                    'x': cx + (random.random() - 0.5) * max_r * 0.3,
                    'y': cy + (random.random() - 0.5) * max_r * 0.3,
                    'vx': math.cos(angle) * speed, 'vy': math.sin(angle) * speed,
                    'life': 1.0, 'size': 2 + random.random() * 4,
                    'pri': random.random() > 0.5
                })
        self._nebula_prev_bass = bass

        # Update & render explosions
        for i in range(len(self._nebula_explosions) - 1, -1, -1):
            e = self._nebula_explosions[i]
            e['x'] += e['vx']; e['y'] += e['vy']
            e['vx'] *= 0.97; e['vy'] *= 0.97; e['life'] -= 0.02
            if e['life'] <= 0:
                self._nebula_explosions.pop(i)
                continue
            col = pri_bgr if e['pri'] else sec_bgr
            dim_col = tuple(int(c * e['life'] * 0.8) for c in col)
            cv2.circle(frame, (int(e['x']), int(e['y'])), max(1, int(e['size'] * e['life'])), dim_col, -1, cv2.LINE_AA)

        # 2. Nebula clouds (simplified - use overlay circles)
        for layer in range(3):
            for p in self._nebula_points:
                if p['layer'] != layer: continue
                p['angle'] += p['speed'] + bass * 0.005
                bar_idx = int(((p['angle'] / (math.pi * 2)) % 1) * count)
                val = spectrum[abs(bar_idx) % count]
                dynamic_dist = p['dist'] + val * 0.15 + bass * 0.05
                x = int(cx + math.cos(p['angle'] + self._nebula_time * (0.3 + layer * 0.1)) * dynamic_dist * max_r)
                y = int(cy + math.sin(p['angle'] + self._nebula_time * (0.3 + layer * 0.1)) * dynamic_dist * max_r * 0.7)
                size = max(2, int(p['baseSize'] * 0.15 + val * 6 + bass * 3))
                col = self._interp_bgr(palette, p['colorMix'])
                alpha = p['opacity'] + val * 0.15 + bass * 0.08
                dim_col = tuple(int(c * min(1.0, alpha)) for c in col)
                cv2.circle(frame, (x, y), size, dim_col, -1, cv2.LINE_AA)

        # 3. Spiral arms
        for arm in range(3):
            arm_offset = (arm / 3) * math.pi * 2
            pts = []
            for i in range(80):
                t = i / 80
                spiral_angle = arm_offset + t * math.pi * 2.5 + self._nebula_time * 0.5
                val = spectrum[int(t * count) % count]
                spiral_r = t * max_r * 0.85 + val * max_r * 0.2
                x = int(cx + math.cos(spiral_angle) * spiral_r)
                y = int(cy + math.sin(spiral_angle) * spiral_r * 0.65)
                pts.append([x, y])
            arm_col = [pri_bgr, sec_bgr, self._interp_bgr(palette, 0.7)][arm]
            alpha = 0.2 + bass * 0.3
            dim_col = tuple(int(c * alpha) for c in arm_col)
            cv2.polylines(frame, [np.array(pts, np.int32)], False, dim_col, max(1, int(1.5 + bass * 2)), cv2.LINE_AA)

        # 4. Center dark core
        core_r = max(5, int(20 + bass * 35))
        cv2.circle(frame, (cx, cy), core_r, (0, 0, 0), -1, cv2.LINE_AA)
        cv2.circle(frame, (cx, cy), core_r + 3, pri_bgr, max(1, int(2 + bass * 3)), cv2.LINE_AA)

        # 5. Cosmic dust stars
        for i in range(50):
            sx = int((math.sin(i * 173.1 + self._nebula_time * 0.15) * 0.5 + 0.5) * w)
            sy = int((math.cos(i * 257.7 + self._nebula_time * 0.08) * 0.5 + 0.5) * h)
            twinkle = math.sin(self._nebula_time * 3 + i * 2.1) * 0.5 + 0.5
            brightness = int((0.1 + twinkle * 0.4) * 255)
            cv2.circle(frame, (sx, sy), max(1, int(0.5 + twinkle * 1.5)), (brightness, brightness, brightness), -1)
