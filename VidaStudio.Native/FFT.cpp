#include "FFT.h"
#include <cmath>

const float PI = 3.14159265358979f;

FFTAnalyzer::FFTAnalyzer(int numSamples) : m_numSamples(numSamples)
{
    m_complexBuffer.resize(numSamples);
    m_window.resize(numSamples);

    // Precompute Hann window
    for (int i = 0; i < numSamples; ++i)
    {
        m_window[i] = 0.5f * (1.0f - std::cos(2.0f * PI * i / (numSamples - 1)));
    }
}

FFTAnalyzer::~FFTAnalyzer() {}

void FFTAnalyzer::ApplyHannWindow(const float* input)
{
    for (int i = 0; i < m_numSamples; ++i)
    {
        m_complexBuffer[i] = std::complex<float>(input[i] * m_window[i], 0.0f);
    }
}

void FFTAnalyzer::PerformFFT(std::vector<std::complex<float>>& data)
{
    int n = data.size();
    if (n <= 1) return;

    // Bit-reversal permutation
    for (int i = 1, j = 0; i < n; i++) {
        int bit = n >> 1;
        for (; j & bit; bit >>= 1)
            j ^= bit;
        j ^= bit;
        if (i < j)
            std::swap(data[i], data[j]);
    }

    // Cooley-Tukey decimation-in-time radix-2 FFT
    for (int len = 2; len <= n; len <<= 1) {
        float angle = -2.0f * PI / len;
        std::complex<float> wlen(std::cos(angle), std::sin(angle));
        for (int i = 0; i < n; i += len) {
            std::complex<float> w(1.0f, 0.0f);
            for (int j = 0; j < len / 2; j++) {
                std::complex<float> u = data[i + j];
                std::complex<float> v = data[i + j + len / 2] * w;
                data[i + j] = u + v;
                data[i + j + len / 2] = u - v;
                w *= wlen;
            }
        }
    }
}

void FFTAnalyzer::Process(const float* pcmData, int count, std::vector<float>& outMagnitudes)
{
    if (count != m_numSamples) return;

    ApplyHannWindow(pcmData);
    PerformFFT(m_complexBuffer);

    int halfSize = m_numSamples / 2;
    if (outMagnitudes.size() != halfSize)
    {
        outMagnitudes.resize(halfSize);
    }

    // Calculate magnitude
    for (int i = 0; i < halfSize; ++i)
    {
        outMagnitudes[i] = std::abs(m_complexBuffer[i]) / (float)halfSize;
    }
}
