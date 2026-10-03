#include <windows.h>
#include <windows.ui.xaml.media.dxinterop.h>
#include "FFT.h"
#include "SpectrumSmoother.h"
#include "D3D11Renderer.h"
#include <memory>

// Global instances for the DLL
std::unique_ptr<FFTAnalyzer> g_fft;
std::unique_ptr<SpectrumSmoother> g_smoother;
std::unique_ptr<D3D11Renderer> g_renderer;
std::vector<float> g_fftMagnitudes;
std::vector<float> g_smoothedBands;

extern "C" {

__declspec(dllexport) bool __stdcall InitVisualizer(IUnknown* swapChainPanelUnknown, int width, int height, int numBands)
{
    g_fft = std::make_unique<FFTAnalyzer>(2048);
    g_smoother = std::make_unique<SpectrumSmoother>(numBands, 0.6f, 0.15f);
    g_renderer = std::make_unique<D3D11Renderer>();

    if (swapChainPanelUnknown == nullptr) return false;

    // Get the native SwapChainPanel interface
    Microsoft::WRL::ComPtr<ISwapChainPanelNative> panelNative;
    HRESULT hr = swapChainPanelUnknown->QueryInterface(IID_PPV_ARGS(&panelNative));
    if (FAILED(hr)) return false;

    return g_renderer->Initialize(panelNative.Get(), width, height);
}

__declspec(dllexport) void __stdcall UpdateAudio(const float* pcmData, int sampleCount)
{
    if (g_fft && g_smoother)
    {
        g_fft->Process(pcmData, sampleCount, g_fftMagnitudes);
        g_smoother->ProcessBands(g_fftMagnitudes, g_smoothedBands);
    }
}

__declspec(dllexport) void __stdcall RenderFrame()
{
    if (g_renderer)
    {
        g_renderer->Render(g_smoothedBands);
    }
}

__declspec(dllexport) void __stdcall ResizeVisualizer(int width, int height)
{
    if (g_renderer)
    {
        g_renderer->Resize(width, height);
    }
}

__declspec(dllexport) void __stdcall CleanupVisualizer()
{
    g_renderer.reset();
    g_smoother.reset();
    g_fft.reset();
}

} // extern "C"

BOOL APIENTRY DllMain(HMODULE hModule, DWORD ul_reason_for_call, LPVOID lpReserved)
{
    return TRUE;
}
