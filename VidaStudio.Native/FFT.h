#pragma once
#include <vector>
#include <complex>

class FFTAnalyzer
{
public:
    FFTAnalyzer(int numSamples = 2048);
    ~FFTAnalyzer();

    // Process PCM audio and get magnitude spectrum
    void Process(const float* pcmData, int count, std::vector<float>& outMagnitudes);

private:
    int m_numSamples;
    std::vector<std::complex<float>> m_complexBuffer;
    std::vector<float> m_window;

    void ApplyHannWindow(const float* input);
    void PerformFFT(std::vector<std::complex<float>>& data);
};
