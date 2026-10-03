#include "SpectrumSmoother.h"
#include <cmath>
#include <algorithm>

SpectrumSmoother::SpectrumSmoother(int numBands, float smoothUp, float smoothDown)
    : m_numBands(numBands), m_smoothUp(smoothUp), m_smoothDown(smoothDown)
{
    m_previousBands.resize(numBands, 0.0f);
}

SpectrumSmoother::~SpectrumSmoother() {}

float SpectrumSmoother::LogSpaceMapping(int band, int numBands, int fftSize)
{
    // Logarithmic distribution to map bands to frequency bins
    float minLog = std::log10(1.0f);
    float maxLog = std::log10((float)fftSize);
    
    float ratio = (float)band / (float)numBands;
    float currentLog = minLog + ratio * (maxLog - minLog);
    
    return std::pow(10.0f, currentLog);
}

void SpectrumSmoother::ProcessBands(const std::vector<float>& fftMagnitudes, std::vector<float>& outBands)
{
    if (outBands.size() != m_numBands)
        outBands.resize(m_numBands, 0.0f);

    int fftSize = fftMagnitudes.size();
    if (fftSize == 0) return;

    for (int i = 0; i < m_numBands; ++i)
    {
        // Compute frequency range for this band logarithmically
        float startBinF = LogSpaceMapping(i, m_numBands, fftSize);
        float endBinF = LogSpaceMapping(i + 1, m_numBands, fftSize);
        
        int startBin = std::max(0, (int)std::floor(startBinF));
        int endBin = std::min(fftSize - 1, (int)std::ceil(endBinF));
        
        if (startBin == endBin && endBin < fftSize - 1)
            endBin++;
            
        float maxValue = 0.0f;
        for (int j = startBin; j <= endBin; ++j)
        {
            maxValue = std::max(maxValue, fftMagnitudes[j]);
        }
        
        // Scale and add gain 
        float targetVal = maxValue * 100.0f; // Arbitrary gain factor
        targetVal = std::min(1.0f, targetVal); // Clamp to [0,1]
        
        // Apply temporal smoothing (attack/decay)
        float prev = m_previousBands[i];
        if (targetVal > prev)
        {
            outBands[i] = prev + (targetVal - prev) * m_smoothUp;
        }
        else
        {
            outBands[i] = prev + (targetVal - prev) * m_smoothDown;
        }
        
        m_previousBands[i] = outBands[i];
    }
}
