"""
CUDA GPU-Accelerated Renderer for VIDA
Uses CuPy (CUDA) for GPU-accelerated frame rendering.
Runs particle systems, spectrum visualizers, and compositing on NVIDIA GPU.

Falls back gracefully to CPU renderer if CuPy/CUDA is unavailable.

Requires: pip install cupy-cuda12x (for CUDA 12.x) or cupy-cuda11x (for CUDA 11.x)
GPU: NVIDIA with compute capability >= 5.0
"""

import os
import math
import time
import numpy as np

try:
    import cupy as cp
    from cupy import RawKernel
    HAS_CUPY = True
except ImportError:
    HAS_CUPY = False
    cp = None
    RawKernel = None

# ─────────────────────────────────────────────────────────────────────
# CUDA Kernels (run directly on GPU cores)
# ─────────────────────────────────────────────────────────────────────

# Particle rendering kernel: draws all 80 particles in parallel on GPU
PARTICLE_KERNEL_CODE = r"""
__device__ float smoothstep(float edge0, float edge1, float x) {
    float t = fminf(fmaxf((x - edge0) / (edge1 - edge0), 0.0f), 1.0f);
    return t * t * (3.0f - 2.0f * t);
}

extern "C" __global__
void render_particles(
    unsigned char* frame,     // BGR frame buffer (H × W × 3)
    const float* px,          // particle X positions (normalized 0..1)
    const float* py,          // particle Y positions
    const float* radii,       // particle radii in pixels
    const float* alphas,      // particle alpha values
    float color_b, float color_g, float color_r,
    int width, int height, int n_particles
) {
    int tid = blockIdx.x * blockDim.x + threadIdx.x;
    int total_pixels = width * height;
    if (tid >= total_pixels) return;

    int pixel_y = tid / width;
    int pixel_x = tid % width;

    float acc_b = 0.0f, acc_g = 0.0f, acc_r = 0.0f;

    for (int i = 0; i < n_particles; i++) {
        float cx = px[i] * width;
        float cy = py[i] * height;
        float r = radii[i];
        float alpha = alphas[i];

        float dx = pixel_x - cx;
        float dy = pixel_y - cy;
        float dist = sqrtf(dx * dx + dy * dy);

        if (dist < r) {
            // Soft circular falloff
            float soft = 1.0f - smoothstep(r * 0.6f, r, dist);
            float intensity = alpha * soft;
            acc_b += color_b * intensity;
            acc_g += color_g * intensity;
            acc_r += color_r * intensity;
        }
    }

    // Additive blend onto existing frame
    int idx = (pixel_y * width + pixel_x) * 3;
    frame[idx + 0] = min(255, (int)(frame[idx + 0] + acc_b * 255.0f));
    frame[idx + 1] = min(255, (int)(frame[idx + 1] + acc_g * 255.0f));
    frame[idx + 2] = min(255, (int)(frame[idx + 2] + acc_r * 255.0f));
}
"""

# Radial spectrum bar kernel: renders all bars in parallel
RADIAL_BARS_KERNEL_CODE = r"""
extern "C" __global__
void render_radial_bars(
    unsigned char* frame,
    const float* spectrum,         // bar values (0..1)
    int n_bars,
    float cx, float cy,            // center in pixels
    float inner_radius,            // dynamic inner radius in pixels
    float max_bar_length,          // max bar extension in pixels
    float pri_r, float pri_g, float pri_b,
    float sec_r, float sec_g, float sec_b,
    int width, int height
) {
    int tid = blockIdx.x * blockDim.x + threadIdx.x;
    int total_pixels = width * height;
    if (tid >= total_pixels) return;

    int pixel_y = tid / width;
    int pixel_x = tid % width;

    float dx = pixel_x - cx;
    float dy = pixel_y - cy;
    float dist = sqrtf(dx * dx + dy * dy);

    // Skip pixels far from the circle area
    float max_outer = inner_radius + max_bar_length + 5.0f;
    if (dist < inner_radius - 2.0f || dist > max_outer) return;

    // Compute angle of this pixel
    float angle = atan2f(dy, dx);  // -PI to PI
    // Normalize to 0..1 range
    float norm_angle = (angle + 3.14159265f) / (2.0f * 3.14159265f);

    // Mirrored: total_angles = n_bars * 2
    int total_angles = n_bars * 2;
    float bar_angular_width = 1.0f / (float)total_angles;

    // Which bar does this pixel belong to?
    int bar_idx = (int)(norm_angle * total_angles) % total_angles;
    
    // Map mirrored index to spectrum value
    int spec_idx = bar_idx < n_bars ? bar_idx : (total_angles - 1 - bar_idx);
    float val = spectrum[spec_idx % n_bars];
    float bar_len = fmaxf(3.0f, val * max_bar_length);

    float outer_radius = inner_radius + 4.0f + bar_len;

    // Is pixel within this bar's radial range?
    if (dist >= inner_radius + 2.0f && dist <= outer_radius) {
        // Check angular fit (within bar width, not in gap)
        float bar_center = (bar_idx + 0.5f) / (float)total_angles;
        float angular_dist = fabsf(norm_angle - bar_center);
        if (angular_dist > 0.5f) angular_dist = 1.0f - angular_dist;
        
        if (angular_dist < bar_angular_width * 0.4f) {
            // Color gradient based on bar index
            float ratio = (float)bar_idx / (float)total_angles;
            float cr = pri_r * (1.0f - ratio) + sec_r * ratio;
            float cg = pri_g * (1.0f - ratio) + sec_g * ratio;
            float cb = pri_b * (1.0f - ratio) + sec_b * ratio;

            int idx = (pixel_y * width + pixel_x) * 3;
            frame[idx + 0] = min(255, (int)(cb * 255.0f));
            frame[idx + 1] = min(255, (int)(cg * 255.0f));
            frame[idx + 2] = min(255, (int)(cr * 255.0f));
        }
    }
}
"""

# Glow ring kernel
GLOW_RING_KERNEL_CODE = r"""
extern "C" __global__
void render_glow_ring(
    unsigned char* frame,
    float cx, float cy,
    float radius, float thickness,
    float glow_r, float glow_g, float glow_b,
    int width, int height
) {
    int tid = blockIdx.x * blockDim.x + threadIdx.x;
    int total_pixels = width * height;
    if (tid >= total_pixels) return;

    int pixel_y = tid / width;
    int pixel_x = tid % width;

    float dx = pixel_x - cx;
    float dy = pixel_y - cy;
    float dist = sqrtf(dx * dx + dy * dy);

    // Quick reject
    if (fabsf(dist - radius) > thickness * 6.0f) return;

    // Ring edge
    float ring_alpha = expf(-fabsf(dist - radius) / thickness * 2.0f);
    
    if (ring_alpha > 0.01f) {
        int idx = (pixel_y * width + pixel_x) * 3;
        // Additive blending
        frame[idx + 0] = min(255, (int)(frame[idx + 0] + glow_b * ring_alpha * 255.0f));
        frame[idx + 1] = min(255, (int)(frame[idx + 1] + glow_g * ring_alpha * 255.0f));
        frame[idx + 2] = min(255, (int)(frame[idx + 2] + glow_r * ring_alpha * 255.0f));
    }
}
"""

# Vignette + darken kernel
VIGNETTE_KERNEL_CODE = r"""
extern "C" __global__
void apply_vignette(
    unsigned char* frame,
    float darken, float vignette_strength,
    int width, int height
) {
    int tid = blockIdx.x * blockDim.x + threadIdx.x;
    int total_pixels = width * height;
    if (tid >= total_pixels) return;

    int y = tid / width;
    int x = tid % width;
    int idx = (y * width + x) * 3;

    float cx = (float)x / (float)width - 0.5f;
    float cy = (float)y / (float)height - 0.5f;
    float dist = sqrtf(cx * cx + cy * cy) * 1.414f;
    float vig = fmaxf(0.2f, 1.0f - vignette_strength * dist * dist);
    float factor = darken * vig;

    frame[idx + 0] = (unsigned char)(frame[idx + 0] * factor);
    frame[idx + 1] = (unsigned char)(frame[idx + 1] * factor);
    frame[idx + 2] = (unsigned char)(frame[idx + 2] * factor);
}
"""

# Neon vertical bars kernel
NEON_BARS_KERNEL_CODE = r"""
extern "C" __global__
void render_neon_bars(
    unsigned char* frame,
    const float* spectrum,
    const float* peak_caps,
    int n_bars,
    float margin, float bar_width, float gap,
    float base_y, float max_h,
    float pri_r, float pri_g, float pri_b,
    float sec_r, float sec_g, float sec_b,
    int width, int height
) {
    int tid = blockIdx.x * blockDim.x + threadIdx.x;
    int total_pixels = width * height;
    if (tid >= total_pixels) return;

    int pixel_y = tid / width;
    int pixel_x = tid % width;

    float fx = (float)pixel_x;
    float fy = (float)pixel_y;
    float base_y_px = base_y * height;
    float margin_px = margin * width;

    // Which bar column?
    float rel_x = fx - margin_px;
    if (rel_x < 0) return;
    
    float slot_w = bar_width * width + gap * width;
    int bar_i = (int)(rel_x / slot_w);
    if (bar_i >= n_bars) return;

    float bar_x_start = margin_px + bar_i * slot_w;
    float bar_x_end = bar_x_start + bar_width * width;
    
    if (fx < bar_x_start || fx > bar_x_end) return;

    float val = spectrum[bar_i];
    float bar_h = fmaxf(4.0f, val * max_h * height);
    float y_top = base_y_px - bar_h;

    // Color gradient
    float ratio = (float)bar_i / (float)n_bars;
    float cr = pri_r * (1.0f - ratio) + sec_r * ratio;
    float cg = pri_g * (1.0f - ratio) + sec_g * ratio;
    float cb = pri_b * (1.0f - ratio) + sec_b * ratio;

    int idx = (pixel_y * width + pixel_x) * 3;

    // Main bar
    if (fy >= y_top && fy <= base_y_px) {
        frame[idx + 0] = (unsigned char)(cb * 255.0f);
        frame[idx + 1] = (unsigned char)(cg * 255.0f);
        frame[idx + 2] = (unsigned char)(cr * 255.0f);
        return;
    }

    // Peak cap (white)
    float cap_y = base_y_px - peak_caps[bar_i] * max_h * height - 4.0f;
    if (fy >= cap_y && fy <= cap_y + 3.0f) {
        frame[idx + 0] = 255;
        frame[idx + 1] = 255;
        frame[idx + 2] = 255;
        return;
    }

    // Reflection
    float ref_h = bar_h * 0.35f;
    if (fy > base_y_px + 3.0f && fy < base_y_px + 3.0f + ref_h) {
        frame[idx + 0] = (unsigned char)(cb * 64.0f);
        frame[idx + 1] = (unsigned char)(cg * 64.0f);
        frame[idx + 2] = (unsigned char)(cr * 64.0f);
    }
}
"""


class CUDAParticleSystem:
    """CUDA-accelerated particle system — renders all particles in parallel on GPU."""

    def __init__(self, count: int, width: int, height: int):
        self.count = count
        self.width = width
        self.height = height

        np.random.seed(42)
        self.x = cp.array(np.random.uniform(0, 1, count).astype(np.float32))
        self.y = cp.array(np.random.uniform(0, 1, count).astype(np.float32))
        self.vx = cp.array((np.random.uniform(-0.5, 0.5, count) / width).astype(np.float32))
        self.vy = cp.array((np.random.uniform(-1.2, -0.2, count) / height).astype(np.float32))
        self.radius = cp.array(np.random.uniform(1.5, 4.0, count).astype(np.float32))
        self.base_alpha = cp.array(np.random.uniform(0.3, 0.8, count).astype(np.float32))

        self.kernel = RawKernel(PARTICLE_KERNEL_CODE, 'render_particles')

    def update_and_render(self, frame_gpu: 'cp.ndarray', bass: float, onset: float, color_bgr: tuple):
        """Updates particles and renders all of them in parallel on GPU."""
        boost = 1.0 + bass * 2.5 + onset * 1.5
        self.x += self.vx * boost
        self.y += self.vy * boost
        self.x = cp.mod(self.x, 1.0)
        self.y = cp.mod(self.y, 1.0)

        cur_radii = self.radius * (1.0 + bass * 0.8)
        alphas = cp.clip(self.base_alpha + bass * 0.4, 0.0, 1.0)

        total_pixels = self.width * self.height
        block = 256
        grid = (total_pixels + block - 1) // block

        self.kernel(
            (grid,), (block,),
            (frame_gpu, self.x, self.y, cur_radii, alphas,
             np.float32(color_bgr[0] / 255.0),  # B
             np.float32(color_bgr[1] / 255.0),  # G
             np.float32(color_bgr[2] / 255.0),  # R
             np.int32(self.width), np.int32(self.height), np.int32(self.count))
        )


class CUDAVideoRenderer:
    """
    Drop-in GPU-accelerated renderer using CUDA via CuPy.
    Replaces CPU-based particle + spectrum rendering with massively parallel GPU kernels.
    Each kernel processes ALL pixels simultaneously instead of looping over shapes.
    
    Your RTX 3050 Ti has 2560 CUDA cores — all working at once!
    """

    def __init__(self, width: int, height: int):
        if not HAS_CUPY:
            raise ImportError("CuPy not installed. Run: pip install cupy-cuda12x")

        self.width = width
        self.height = height

        # Compile CUDA kernels
        self.particles = CUDAParticleSystem(80, width, height)
        self.vignette_kernel = RawKernel(VIGNETTE_KERNEL_CODE, 'apply_vignette')
        self.radial_kernel = RawKernel(RADIAL_BARS_KERNEL_CODE, 'render_radial_bars')
        self.ring_kernel = RawKernel(GLOW_RING_KERNEL_CODE, 'render_glow_ring')
        self.neon_bars_kernel = RawKernel(NEON_BARS_KERNEL_CODE, 'render_neon_bars')

        self.total_pixels = width * height
        self.block = 256
        self.grid = (self.total_pixels + self.block - 1) // self.block

        print(f"[VIDA CUDA] ⚡ CUDA renderer initialized ({width}x{height})")
        print(f"[VIDA CUDA] GPU: {cp.cuda.runtime.getDeviceProperties(0)['name'].decode()}")
        print(f"[VIDA CUDA] CUDA cores working for you: 2560+")

    def render_frame(self, bg_frame_bgr: np.ndarray, spectrum: np.ndarray,
                     bass: float, onset: float, palette: dict, theme: str,
                     peak_caps: np.ndarray) -> np.ndarray:
        """
        Renders one complete frame on GPU.
        Returns BGR numpy array for FFmpeg pipe.
        """
        # 1. Upload background frame to GPU
        frame_gpu = cp.asarray(bg_frame_bgr.copy())

        # 2. Apply vignette + darkening on GPU
        self.vignette_kernel(
            (self.grid,), (self.block,),
            (frame_gpu, np.float32(0.42), np.float32(0.45),
             np.int32(self.width), np.int32(self.height))
        )

        # 3. Particles on GPU (all 80 particles, all pixels in parallel)
        pri = palette["primary"]
        # Convert RGB to BGR for the frame buffer
        color_bgr = (pri[2], pri[1], pri[0])
        self.particles.update_and_render(frame_gpu, bass, onset, color_bgr)

        # 4. Spectrum visualizer on GPU
        sec = palette["secondary"]
        glow = palette["glow"]
        spectrum_gpu = cp.asarray(spectrum.astype(np.float32))

        cx = self.width / 2.0
        cy = self.height / 2.0

        if bass > 0.7:
            cx += float(np.random.uniform(-4, 4) * bass)
            cy += float(np.random.uniform(-4, 4) * bass)

        if theme == "trap_circle":
            base_r = min(self.width, self.height) * 0.16
            dynamic_r = base_r + bass * (base_r * 0.28)
            max_bar = min(self.width, self.height) * 0.22

            self.radial_kernel(
                (self.grid,), (self.block,),
                (frame_gpu, spectrum_gpu, np.int32(len(spectrum)),
                 np.float32(cx), np.float32(cy),
                 np.float32(dynamic_r), np.float32(max_bar),
                 np.float32(pri[0] / 255.0), np.float32(pri[1] / 255.0), np.float32(pri[2] / 255.0),
                 np.float32(sec[0] / 255.0), np.float32(sec[1] / 255.0), np.float32(sec[2] / 255.0),
                 np.int32(self.width), np.int32(self.height))
            )

            # Glow ring
            self.ring_kernel(
                (self.grid,), (self.block,),
                (frame_gpu, np.float32(cx), np.float32(cy),
                 np.float32(dynamic_r + 2), np.float32(3.0),
                 np.float32(glow[0] / 255.0), np.float32(glow[1] / 255.0), np.float32(glow[2] / 255.0),
                 np.int32(self.width), np.int32(self.height))
            )

        elif theme in ("neon_bars", "spectrum"):
            peak_gpu = cp.asarray(peak_caps.astype(np.float32))
            self.neon_bars_kernel(
                (self.grid,), (self.block,),
                (frame_gpu, spectrum_gpu, peak_gpu, np.int32(len(spectrum)),
                 np.float32(0.08),  # margin
                 np.float32(0.72 / len(spectrum)),  # bar_width (normalized)
                 np.float32(0.28 / len(spectrum)),   # gap (normalized)
                 np.float32(0.72),  # base_y
                 np.float32(0.42),  # max_h
                 np.float32(pri[0] / 255.0), np.float32(pri[1] / 255.0), np.float32(pri[2] / 255.0),
                 np.float32(sec[0] / 255.0), np.float32(sec[1] / 255.0), np.float32(sec[2] / 255.0),
                 np.int32(self.width), np.int32(self.height))
            )
        else:
            # Default: trap circle
            base_r = min(self.width, self.height) * 0.16
            dynamic_r = base_r + bass * (base_r * 0.28)
            max_bar = min(self.width, self.height) * 0.22
            self.radial_kernel(
                (self.grid,), (self.block,),
                (frame_gpu, spectrum_gpu, np.int32(len(spectrum)),
                 np.float32(cx), np.float32(cy),
                 np.float32(dynamic_r), np.float32(max_bar),
                 np.float32(pri[0] / 255.0), np.float32(pri[1] / 255.0), np.float32(pri[2] / 255.0),
                 np.float32(sec[0] / 255.0), np.float32(sec[1] / 255.0), np.float32(sec[2] / 255.0),
                 np.int32(self.width), np.int32(self.height))
            )
            self.ring_kernel(
                (self.grid,), (self.block,),
                (frame_gpu, np.float32(cx), np.float32(cy),
                 np.float32(dynamic_r + 2), np.float32(3.0),
                 np.float32(glow[0] / 255.0), np.float32(glow[1] / 255.0), np.float32(glow[2] / 255.0),
                 np.int32(self.width), np.int32(self.height))
            )

        # 5. Download result from GPU → CPU
        result = cp.asnumpy(frame_gpu)
        return result

    def release(self):
        """Releases GPU memory."""
        cp.get_default_memory_pool().free_all_blocks()
        print("[VIDA CUDA] GPU memory released")


def is_cuda_available() -> bool:
    """Checks if CUDA GPU rendering is available via CuPy."""
    if not HAS_CUPY or cp is None:
        return False
    try:
        device = cp.cuda.Device(0)
        # Test compiling a trivial kernel to verify CUDA headers are present
        test_kernel = RawKernel(r'extern "C" __global__ void test_k(int* x) { *x = 1; }', 'test_k')
        test_kernel.compile()
        props = cp.cuda.runtime.getDeviceProperties(0)
        name = props['name'].decode()
        print(f"[VIDA CUDA] ✅ GPU available: {name}")
        return True
    except Exception as e:
        print(f"[VIDA CUDA] ⚠️ CuPy CUDA compilation unavailable ({e}). Using ultra-fast SIMD pipeline.")
        return False
