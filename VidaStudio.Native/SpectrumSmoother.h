#pragma once
#include <vector>

class SpectrumSmoother
{
public:
    SpectrumSmoother(int numBands, float smoothUp = 0.8f, float smoothDown = 0.2f);
    ~SpectrumSmoother();

    // Converts raw FFT magnitudes into smoothed frequency bands
    void ProcessBands(const std::vector<float>& fftMagnitudes, std::vector<float>& outBands);

private:
    int m_numBands;
    float m_smoothUp;
    float m_smoothDown;
    std::vector<float> m_previousBands;

    float LogSpaceMapping(int band, int numBands, int fftSize);
};
