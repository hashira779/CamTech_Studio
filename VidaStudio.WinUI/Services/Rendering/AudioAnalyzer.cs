using System.Diagnostics;
using MathNet.Numerics;
using MathNet.Numerics.IntegralTransforms;

namespace VidaStudio.Services.Rendering;

/// <summary>
/// High-performance audio spectrum analyzer for the native C# video renderer.
/// Extracts per-frame FFT spectrum bars, bass energy, and onset/beat detection.
/// Port of Python backend/audio_analyzer.py — fully vectorized, no Python overhead.
/// </summary>
public sealed class AudioAnalyzer
{
    public float[] AudioData { get; }
    public int SampleRate { get; }
    public double Duration { get; }
    public int Fps { get; }
    public int NumBars { get; }
    public int TotalFrames { get; }

    public AudioAnalyzer(float[] audioData, int sampleRate, int fps = 60, int numBars = 64)
    {
        AudioData = audioData;
        SampleRate = sampleRate;
        Duration = (double)audioData.Length / sampleRate;
        Fps = fps;
        NumBars = numBars;
        TotalFrames = (int)Math.Ceiling(Duration * fps);
    }

    /// <summary>
    /// Decodes audio file to mono float32 array using FFmpeg pipe (supports MP3, WAV, FLAC, M4A, OGG).
    /// </summary>
    public static (float[] data, int sampleRate, double duration) DecodeAudio(string audioPath, int targetSr = 22050)
    {
        if (!File.Exists(audioPath))
            throw new FileNotFoundException($"Audio file not found: {audioPath}");

        string ffmpegPath = FindFfmpeg();
        var psi = new ProcessStartInfo
        {
            FileName = ffmpegPath,
            Arguments = $"-i \"{audioPath}\" -vn -ac 1 -ar {targetSr} -f f32le -",
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            CreateNoWindow = true
        };

        using var proc = Process.Start(psi) ?? throw new InvalidOperationException("Failed to start FFmpeg");
        using var ms = new MemoryStream();
        proc.StandardOutput.BaseStream.CopyTo(ms);
        proc.WaitForExit();

        if (proc.ExitCode != 0 || ms.Length == 0)
            throw new InvalidOperationException($"FFmpeg failed to decode: {audioPath}");

        byte[] raw = ms.ToArray();
        float[] data = new float[raw.Length / 4];
        Buffer.BlockCopy(raw, 0, data, 0, raw.Length);

        double duration = (double)data.Length / targetSr;
        return (data, targetSr, duration);
    }

    /// <summary>
    /// Computes log-spaced frequency spectrum for every video frame,
    /// plus bass intensity and beat onsets. Fully vectorized — no Python loops.
    /// </summary>
    public AnalysisResult Analyze(float bassBoost = 1.3f, float smoothingAttack = 0.85f, float smoothingDecay = 0.70f)
    {
        int nFft = 2048;
        int hopSamples = SampleRate / Fps;

        // Pre-compute Hanning window
        float[] window = new float[nFft];
        for (int i = 0; i < nFft; i++)
            window[i] = (float)(0.5 * (1.0 - Math.Cos(2.0 * Math.PI * i / (nFft - 1))));

        // Pre-compute log frequency bin boundaries
        float minFreq = 30f, maxFreq = 12000f;
        float[] logFreqBins = new float[NumBars + 1];
        for (int i = 0; i <= NumBars; i++)
            logFreqBins[i] = (float)Math.Pow(10, Math.Log10(minFreq) + (Math.Log10(maxFreq) - Math.Log10(minFreq)) * i / NumBars);

        float freqStep = (SampleRate / 2.0f) / (nFft / 2);
        int fftHalfLen = nFft / 2 + 1;

        // Pre-compute bin index boundaries (vectorized — computed once, not per-frame)
        int[] binLows = new int[NumBars];
        int[] binHighs = new int[NumBars];
        float[] eqFactors = new float[NumBars];
        for (int b = 0; b < NumBars; b++)
        {
            binLows[b] = Math.Max(0, (int)(logFreqBins[b] / freqStep));
            binHighs[b] = Math.Min(fftHalfLen - 1, (int)(logFreqBins[b + 1] / freqStep));
            if (binHighs[b] <= binLows[b]) binHighs[b] = binLows[b] + 1;
            eqFactors[b] = 1.0f + (1.0f - (float)b / NumBars) * 0.5f;
        }

        // Bass frequency mask: 30-160 Hz
        int bassLow = Math.Max(0, (int)(30f / freqStep));
        int bassHigh = Math.Min(fftHalfLen - 1, (int)(160f / freqStep));

        // Allocate output arrays
        float[,] spectrumMatrix = new float[TotalFrames, NumBars];
        float[] bassCurve = new float[TotalFrames];
        float[] onsetCurve = new float[TotalFrames];

        // Pad audio
        int padLen = nFft / 2;
        float[] padded = new float[AudioData.Length + 2 * padLen];
        Array.Copy(AudioData, 0, padded, padLen, AudioData.Length);

        float[,] rawBarsMatrix = new float[TotalFrames, NumBars];
        float[,] rawFftMag = new float[TotalFrames, fftHalfLen];

        // PASS 1: Parallel FFT and Binning (Heavy lifting spread across all CPU cores)
        Parallel.For(0, TotalFrames, fIdx =>
        {
            int centerSample = fIdx * hopSamples + padLen;
            int start = centerSample - nFft / 2;
            int end = start + nFft;
            if (end > padded.Length) return;

            // Thread-local complex buffer
            var fftBuffer = new System.Numerics.Complex[nFft];
            
            // Window and load into complex buffer
            for (int i = 0; i < nFft; i++)
                fftBuffer[i] = new System.Numerics.Complex(padded[start + i] * window[i], 0);

            // In-place FFT
            Fourier.Forward(fftBuffer, FourierOptions.NoScaling);

            // Magnitude spectrum (half)
            for (int i = 0; i < fftHalfLen; i++)
                rawFftMag[fIdx, i] = (float)fftBuffer[i].Magnitude;

            // Bass energy
            float bassSum = 0;
            int bassCount = 0;
            for (int i = bassLow; i <= bassHigh && i < fftHalfLen; i++)
            {
                bassSum += rawFftMag[fIdx, i];
                bassCount++;
            }
            bassCurve[fIdx] = bassCount > 0 ? bassSum / bassCount : 0;

            // Bin FFT into musical frequency bars
            for (int b = 0; b < NumBars; b++)
            {
                float sum = 0;
                int count = 0;
                for (int i = binLows[b]; i <= binHighs[b] && i < fftHalfLen; i++)
                {
                    sum += rawFftMag[fIdx, i];
                    count++;
                }
                rawBarsMatrix[fIdx, b] = (count > 0 ? sum / count : 0) * eqFactors[b];
            }
        });

        // PASS 2: Sequential Smoothing and Onset Detection (Requires previous frame state)
        float[] prevSpectrum = new float[NumBars];
        
        for (int fIdx = 0; fIdx < TotalFrames; fIdx++)
        {
            // Onset detection: spectral flux
            if (fIdx > 0)
            {
                float flux = 0;
                for (int i = 0; i < fftHalfLen; i++)
                    flux += Math.Max(0, rawFftMag[fIdx, i] - rawFftMag[fIdx - 1, i]);
                onsetCurve[fIdx] = flux;
            }

            // Convert to dB, normalize, power curve
            for (int b = 0; b < NumBars; b++)
            {
                float rawBar = rawBarsMatrix[fIdx, b];
                float db = 20f * MathF.Log10(MathF.Max(rawBar, 1e-5f));
                float norm = Math.Clamp((db + 60f) / 60f, 0f, 1f);
                norm = MathF.Pow(norm, 1.8f) * bassBoost;

                // Attack/decay smoothing
                float smooth = norm > prevSpectrum[b]
                    ? prevSpectrum[b] * (1f - smoothingAttack) + norm * smoothingAttack
                    : prevSpectrum[b] * smoothingDecay;

                spectrumMatrix[fIdx, b] = Math.Clamp(smooth, 0f, 1f);
                prevSpectrum[b] = smooth;
            }
        }

        // Normalize bass and onset curves
        NormalizeCurve(bassCurve);
        NormalizeCurve(onsetCurve);

        // Smooth bass curve
        SmoothCurve(bassCurve, [0.1f, 0.2f, 0.4f, 0.2f, 0.1f]);

        return new AnalysisResult(spectrumMatrix, bassCurve, onsetCurve, TotalFrames, Fps, Duration);
    }

    private static void NormalizeCurve(float[] curve)
    {
        if (curve.Length == 0) return;
        float[] sorted = (float[])curve.Clone();
        Array.Sort(sorted);
        float p98 = sorted[Math.Min(sorted.Length - 1, (int)(sorted.Length * 0.98))];
        if (p98 <= 0) return;
        for (int i = 0; i < curve.Length; i++)
            curve[i] = Math.Clamp(curve[i] / p98, 0f, 1.5f);
    }

    private static void SmoothCurve(float[] curve, float[] kernel)
    {
        float[] tmp = new float[curve.Length];
        int half = kernel.Length / 2;
        for (int i = 0; i < curve.Length; i++)
        {
            float sum = 0;
            for (int k = 0; k < kernel.Length; k++)
            {
                int idx = i + k - half;
                if (idx >= 0 && idx < curve.Length)
                    sum += curve[idx] * kernel[k];
            }
            tmp[i] = sum;
        }
        Array.Copy(tmp, curve, curve.Length);
    }

    private static string FindFfmpeg()
    {
        string venvFfmpeg = Path.Combine(BackendService.Instance.GetProjectRoot(), "venv", "Scripts", "ffmpeg.exe");
        string[] candidates =
        [
            venvFfmpeg,
            Path.Combine(AppContext.BaseDirectory, "ffmpeg.exe"),
            @"C:\ffmpeg\bin\ffmpeg.exe",
            "ffmpeg" // system PATH
        ];
        foreach (var c in candidates)
            if (File.Exists(c)) return c;
        return "ffmpeg";
    }
}

public record AnalysisResult(
    float[,] Spectrum,
    float[] Bass,
    float[] Onsets,
    int TotalFrames,
    int Fps,
    double Duration
);
