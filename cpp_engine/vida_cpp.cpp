#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <cmath>
#include <algorithm>

namespace py = pybind11;

// Extremely fast custom circle drawing directly into the raw byte array
void draw_particles(py::array_t<uint8_t> frame, 
                    py::array_t<int> px, 
                    py::array_t<int> py, 
                    py::array_t<int> pr, 
                    py::array_t<float> palpha, 
                    int b, int g, int r_col) {
                    
    auto buf_frame = frame.request();
    auto buf_x = px.request();
    auto buf_y = py.request();
    auto buf_r = pr.request();
    auto buf_alpha = palpha.request();
    
    int height = buf_frame.shape[0];
    int width = buf_frame.shape[1];
    int channels = buf_frame.shape[2]; // Should be 3 (BGR)
    
    uint8_t *ptr = (uint8_t *)buf_frame.ptr;
    int *x = (int *)buf_x.ptr;
    int *y = (int *)buf_y.ptr;
    int *r = (int *)buf_r.ptr;
    float *alpha = (float *)buf_alpha.ptr;
    
    int num_particles = buf_x.shape[0];
    
    for (int i = 0; i < num_particles; i++) {
        int cx = x[i];
        int cy = y[i];
        int rad = r[i];
        float a = std::min(1.0f, std::max(0.0f, alpha[i]));
        
        int r2 = rad * rad;
        
        int min_x = std::max(0, cx - rad);
        int max_x = std::min(width - 1, cx + rad);
        int min_y = std::max(0, cy - rad);
        int max_y = std::min(height - 1, cy + rad);
        
        float inv_a = 1.0f - a;
        uint8_t cb = (uint8_t)(b * a);
        uint8_t cg = (uint8_t)(g * a);
        uint8_t cr = (uint8_t)(r_col * a);
        
        for (int yy = min_y; yy <= max_y; yy++) {
            int dy = yy - cy;
            for (int xx = min_x; xx <= max_x; xx++) {
                int dx = xx - cx;
                if (dx*dx + dy*dy <= r2) {
                    int idx = (yy * width + xx) * channels;
                    // Alpha blending directly in memory
                    ptr[idx] = (uint8_t)((ptr[idx] * inv_a) + cb);
                    ptr[idx+1] = (uint8_t)((ptr[idx+1] * inv_a) + cg);
                    ptr[idx+2] = (uint8_t)((ptr[idx+2] * inv_a) + cr);
                }
            }
        }
    }
}

PYBIND11_MODULE(vida_cpp, m) {
    m.doc() = "VIDA Ultra-Fast C++ Rendering Engine";
    m.def("draw_particles", &draw_particles, "Draw audio-reactive particles directly into a NumPy buffer");
}
