using System.IO;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using VidaStudio.Models;

namespace VidaStudio.Services;

public class VidaApiClient
{
    private static VidaApiClient? _instance;
    public static VidaApiClient Instance => _instance ??= new VidaApiClient();

    private readonly HttpClient _http;
    private readonly JsonSerializerOptions _jsonOptions;

    public VidaApiClient()
    {
        _http = new HttpClient { Timeout = TimeSpan.FromMinutes(10) };
        _jsonOptions = new JsonSerializerOptions { PropertyNameCaseInsensitive = true };
    }

    public string BaseUrl => BackendService.Instance.BaseUrl;

    public async Task<List<MediaItem>> GetLibraryAsync()
    {
        var items = new List<MediaItem>();
        try
        {
            var response = await _http.GetAsync($"{BaseUrl}/api/library");
            if (response.IsSuccessStatusCode)
            {
                var json = await response.Content.ReadAsStringAsync();
                using var doc = JsonDocument.Parse(json);
                if (doc.RootElement.TryGetProperty("files", out var filesProp) && filesProp.ValueKind == JsonValueKind.Array)
                {
                    foreach (var f in filesProp.EnumerateArray())
                    {
                        string name = f.GetProperty("name").GetString() ?? "";
                        string path = f.GetProperty("path").GetString() ?? "";
                        string type = f.GetProperty("type").GetString() ?? "audio";
                        string url = f.GetProperty("url").GetString() ?? "";
                        items.Add(new MediaItem { Name = name, Path = path.Replace('/', '\\'), Type = type, Url = url });
                    }
                }
            }
        }
        catch (Exception ex)
        {
            BackendService.Instance.AppendLog($"[VidaApiClient] GetLibrary error: {ex.Message}");
        }

        // Fallback: local scan if backend is starting
        if (items.Count == 0)
        {
            string audioDir = Path.Combine(BackendService.Instance.GetProjectRoot(), "uploads", "audio");
            if (Directory.Exists(audioDir))
            {
                foreach (var file in Directory.GetFiles(audioDir, "*.*"))
                {
                    string ext = Path.GetExtension(file).ToLowerInvariant();
                    if (ext is ".mp3" or ".wav" or ".m4a" or ".flac")
                    {
                        items.Add(new MediaItem
                        {
                            Name = Path.GetFileName(file),
                            Path = file,
                            Type = "audio",
                            Url = $"/uploads/audio/{Path.GetFileName(file)}"
                        });
                    }
                }
            }
        }

        return items;
    }

    public async Task<string?> UploadAudioFileAsync(string filePath)
    {
        if (!File.Exists(filePath)) return null;

        using var content = new MultipartFormDataContent();
        using var fileStream = File.OpenRead(filePath);
        using var streamContent = new StreamContent(fileStream);

        string ext = Path.GetExtension(filePath).ToLowerInvariant();
        string mediaType = ext switch
        {
            ".wav" => "audio/wav",
            ".mp3" => "audio/mpeg",
            ".m4a" => "audio/mp4",
            ".flac" => "audio/flac",
            ".mp4" => "video/mp4",
            _ => "application/octet-stream"
        };
        streamContent.Headers.ContentType = new MediaTypeHeaderValue(mediaType);
        content.Add(streamContent, "file", Path.GetFileName(filePath));

        try
        {
            var response = await _http.PostAsync($"{BaseUrl}/api/upload", content);
            if (response.IsSuccessStatusCode)
            {
                var json = await response.Content.ReadAsStringAsync();
                using var doc = JsonDocument.Parse(json);
                if (doc.RootElement.TryGetProperty("saved_path", out var pathProp))
                {
                    return pathProp.GetString();
                }
            }
        }
        catch (Exception ex)
        {
            BackendService.Instance.AppendLog($"[VidaApiClient] Upload error: {ex.Message}");
        }

        return filePath;
    }

    public async Task<JsonElement?> AnalyzeAudioAsync(string audioPath)
    {
        try
        {
            var payload = new { audio_path = audioPath.Replace('\\', '/') };
            var content = new StringContent(JsonSerializer.Serialize(payload), Encoding.UTF8, "application/json");
            var response = await _http.PostAsync($"{BaseUrl}/api/analyze", content);
            if (response.IsSuccessStatusCode)
            {
                var json = await response.Content.ReadAsStringAsync();
                return JsonDocument.Parse(json).RootElement.Clone();
            }
        }
        catch (Exception ex)
        {
            BackendService.Instance.AppendLog($"[VidaApiClient] Analyze error: {ex.Message}");
        }
        return null;
    }

    public async Task<List<LyricLine>> TranscribeAudioAsync(string audioPath, string lang = "km", string model = "gemini-fast", bool useDemucs = false)
    {
        var result = new List<LyricLine>();
        try
        {
            var payload = new
            {
                audio_path = audioPath.Replace('\\', '/'),
                language = lang,
                model_size = model,
                use_demucs = useDemucs,
                force_ai = false
            };
            var content = new StringContent(JsonSerializer.Serialize(payload), Encoding.UTF8, "application/json");
            var response = await _http.PostAsync($"{BaseUrl}/api/transcribe", content);
            if (response.IsSuccessStatusCode)
            {
                var json = await response.Content.ReadAsStringAsync();
                using var doc = JsonDocument.Parse(json);
                if (doc.RootElement.TryGetProperty("lyrics", out var lyricsProp) && lyricsProp.ValueKind == JsonValueKind.Array)
                {
                    int lineIdx = 0;
                    foreach (var item in lyricsProp.EnumerateArray())
                    {
                        double start = item.TryGetProperty("start", out var s) ? s.GetDouble() : 0;
                        double end = item.TryGetProperty("end", out var e) ? e.GetDouble() : start + 3;
                        string text = item.TryGetProperty("text", out var t) ? t.GetString() ?? "" : "";
                        double conf = item.TryGetProperty("confidence", out var c) ? c.GetDouble() : 0.95;

                        if (!string.IsNullOrWhiteSpace(text))
                        {
                            result.Add(new LyricLine
                            {
                                LineId = lineIdx++,
                                StartTime = TimeSpan.FromSeconds(start),
                                EndTime = TimeSpan.FromSeconds(end),
                                Text = text,
                                Confidence = conf
                            });
                        }
                    }
                }
            }
        }
        catch (Exception ex)
        {
            BackendService.Instance.AppendLog($"[VidaApiClient] Transcribe error: {ex.Message}");
        }

        return result;
    }

    public string? LastYouTubeError { get; private set; }

    public async Task<JsonElement?> DownloadYouTubeAsync(string url)
    {
        LastYouTubeError = null;
        try
        {
            var payload = new { url = url.Trim() };
            var content = new StringContent(JsonSerializer.Serialize(payload), Encoding.UTF8, "application/json");
            var response = await _http.PostAsync($"{BaseUrl}/api/youtube", content);
            if (response.IsSuccessStatusCode)
            {
                var json = await response.Content.ReadAsStringAsync();
                return JsonDocument.Parse(json).RootElement.Clone();
            }
            else
            {
                var errJson = await response.Content.ReadAsStringAsync();
                BackendService.Instance.AppendLog($"[VidaApiClient] YouTube Download HTTP {response.StatusCode}: {errJson}");
                try
                {
                    using var doc = JsonDocument.Parse(errJson);
                    if (doc.RootElement.TryGetProperty("detail", out var dProp))
                    {
                        LastYouTubeError = dProp.GetString();
                    }
                }
                catch
                {
                    LastYouTubeError = $"HTTP {response.StatusCode}";
                }
            }
        }
        catch (Exception ex)
        {
            LastYouTubeError = ex.Message;
            BackendService.Instance.AppendLog($"[VidaApiClient] YouTube Download error: {ex.Message}");
        }
        return null;
    }

    public async Task<(int percent, string stage)> GetYouTubeProgressAsync()
    {
        try
        {
            var response = await _http.GetAsync($"{BaseUrl}/api/youtube/progress");
            if (response.IsSuccessStatusCode)
            {
                var json = await response.Content.ReadAsStringAsync();
                using var doc = JsonDocument.Parse(json);
                int pct = doc.RootElement.TryGetProperty("percent", out var p) ? p.GetInt32() : 0;
                string stage = doc.RootElement.TryGetProperty("stage", out var s) ? s.GetString() ?? "" : "";
                return (pct, stage);
            }
        }
        catch { }
        return (0, "");
    }

    public async Task<JsonElement?> LoadSynthDemoAsync()
    {
        try
        {
            var response = await _http.GetAsync($"{BaseUrl}/api/demo");
            if (response.IsSuccessStatusCode)
            {
                var json = await response.Content.ReadAsStringAsync();
                return JsonDocument.Parse(json).RootElement.Clone();
            }
        }
        catch (Exception ex)
        {
            BackendService.Instance.AppendLog($"[VidaApiClient] LoadSynthDemo error: {ex.Message}");
        }
        return null;
    }

    public async Task<JsonElement?> LoadSinisamutDemoAsync()
    {
        try
        {
            var response = await _http.GetAsync($"{BaseUrl}/api/demo/sinisamut");
            if (response.IsSuccessStatusCode)
            {
                var json = await response.Content.ReadAsStringAsync();
                return JsonDocument.Parse(json).RootElement.Clone();
            }
        }
        catch (Exception ex)
        {
            BackendService.Instance.AppendLog($"[VidaApiClient] LoadSinisamutDemo error: {ex.Message}");
        }
        return null;
    }

    public async Task<List<LyricLine>> AutoFixLyricsAsync(List<LyricLine> lyrics)
    {
        try
        {
            var lyricsPayload = lyrics.Select(l => new
            {
                line_id = l.LineId,
                start = l.StartTime.TotalSeconds,
                end = l.EndTime.TotalSeconds,
                text = l.Text
            }).ToList();

            var payload = new { lyrics_data = lyricsPayload };
            var content = new StringContent(JsonSerializer.Serialize(payload), Encoding.UTF8, "application/json");
            var response = await _http.PostAsync($"{BaseUrl}/api/lyrics/auto_fix", content);
            if (response.IsSuccessStatusCode)
            {
                var json = await response.Content.ReadAsStringAsync();
                using var doc = JsonDocument.Parse(json);
                if (doc.RootElement.TryGetProperty("lyrics", out var lyrProp) && lyrProp.ValueKind == JsonValueKind.Array)
                {
                    var updated = new List<LyricLine>();
                    int idx = 0;
                    foreach (var item in lyrProp.EnumerateArray())
                    {
                        double s = item.TryGetProperty("start", out var sp) ? sp.GetDouble() : 0;
                        double e = item.TryGetProperty("end", out var ep) ? ep.GetDouble() : s + 3;
                        string t = item.TryGetProperty("text", out var tp) ? tp.GetString() ?? "" : "";
                        updated.Add(new LyricLine
                        {
                            LineId = idx++,
                            StartTime = TimeSpan.FromSeconds(s),
                            EndTime = TimeSpan.FromSeconds(e),
                            Text = t,
                            Confidence = 1.0
                        });
                    }
                    return updated;
                }
            }
        }
        catch (Exception ex)
        {
            BackendService.Instance.AppendLog($"[VidaApiClient] AutoFixLyrics error: {ex.Message}");
        }
        return lyrics;
    }

    public async Task<List<LyricLine>> AlignLyricsWithReferenceAsync(List<LyricLine> lyrics, string referenceText)
    {
        try
        {
            var lyricsPayload = lyrics.Select(l => new
            {
                line_id = l.LineId,
                start = l.StartTime.TotalSeconds,
                end = l.EndTime.TotalSeconds,
                text = l.Text
            }).ToList();

            var payload = new
            {
                lyrics_data = lyricsPayload,
                reference_text = referenceText
            };
            var content = new StringContent(JsonSerializer.Serialize(payload), Encoding.UTF8, "application/json");
            var response = await _http.PostAsync($"{BaseUrl}/api/lyrics/correct-with-reference", content);
            if (response.IsSuccessStatusCode)
            {
                var json = await response.Content.ReadAsStringAsync();
                using var doc = JsonDocument.Parse(json);
                if (doc.RootElement.TryGetProperty("lyrics", out var lyrProp) && lyrProp.ValueKind == JsonValueKind.Array)
                {
                    var updated = new List<LyricLine>();
                    int idx = 0;
                    foreach (var item in lyrProp.EnumerateArray())
                    {
                        double s = item.TryGetProperty("start", out var sp) ? sp.GetDouble() : 0;
                        double e = item.TryGetProperty("end", out var ep) ? ep.GetDouble() : s + 3;
                        string t = item.TryGetProperty("text", out var tp) ? tp.GetString() ?? "" : "";
                        updated.Add(new LyricLine
                        {
                            LineId = idx++,
                            StartTime = TimeSpan.FromSeconds(s),
                            EndTime = TimeSpan.FromSeconds(e),
                            Text = t,
                            Confidence = 1.0
                        });
                    }
                    return updated;
                }
            }
        }
        catch (Exception ex)
        {
            BackendService.Instance.AppendLog($"[VidaApiClient] AlignLyrics error: {ex.Message}");
        }
        return lyrics;
    }

    public async Task<List<LyricLine>> ImportSubtitleFileAsync(string filePath)
    {
        var result = new List<LyricLine>();
        if (!File.Exists(filePath)) return result;

        using var content = new MultipartFormDataContent();
        using var fileStream = File.OpenRead(filePath);
        using var streamContent = new StreamContent(fileStream);
        streamContent.Headers.ContentType = new MediaTypeHeaderValue("text/plain");
        content.Add(streamContent, "file", Path.GetFileName(filePath));

        try
        {
            var response = await _http.PostAsync($"{BaseUrl}/api/lyrics/upload", content);
            if (response.IsSuccessStatusCode)
            {
                var json = await response.Content.ReadAsStringAsync();
                using var doc = JsonDocument.Parse(json);
                if (doc.RootElement.TryGetProperty("lyrics", out var lyrProp) && lyrProp.ValueKind == JsonValueKind.Array)
                {
                    int idx = 0;
                    foreach (var item in lyrProp.EnumerateArray())
                    {
                        double s = item.TryGetProperty("start", out var sp) ? sp.GetDouble() : 0;
                        double e = item.TryGetProperty("end", out var ep) ? ep.GetDouble() : s + 3;
                        string t = item.TryGetProperty("text", out var tp) ? tp.GetString() ?? "" : "";
                        result.Add(new LyricLine
                        {
                            LineId = idx++,
                            StartTime = TimeSpan.FromSeconds(s),
                            EndTime = TimeSpan.FromSeconds(e),
                            Text = t,
                            Confidence = 1.0
                        });
                    }
                }
            }
        }
        catch (Exception ex)
        {
            BackendService.Instance.AppendLog($"[VidaApiClient] ImportSubtitle error: {ex.Message}");
        }

        return result;
    }

    public async Task<JsonElement?> GenerateKhmerLyricsAsync(string prompt, string genre = "romantic", int bpm = 85)
    {
        try
        {
            var payload = new { prompt, genre, bpm };
            var content = new StringContent(JsonSerializer.Serialize(payload), Encoding.UTF8, "application/json");
            var response = await _http.PostAsync($"{BaseUrl}/api/lyrics/generate", content);
            if (response.IsSuccessStatusCode)
            {
                var json = await response.Content.ReadAsStringAsync();
                return JsonDocument.Parse(json).RootElement.Clone();
            }
        }
        catch (Exception ex)
        {
            BackendService.Instance.AppendLog($"[VidaApiClient] GenerateKhmerLyrics error: {ex.Message}");
        }
        return null;
    }

    public async Task<string?> PolishKhmerLyricsAsync(string rawLyrics)
    {
        try
        {
            var payload = new { lyrics_text = rawLyrics };
            var content = new StringContent(JsonSerializer.Serialize(payload), Encoding.UTF8, "application/json");
            var response = await _http.PostAsync($"{BaseUrl}/api/lyrics/polish", content);
            if (response.IsSuccessStatusCode)
            {
                var json = await response.Content.ReadAsStringAsync();
                using var doc = JsonDocument.Parse(json);
                if (doc.RootElement.TryGetProperty("polished", out var pol))
                {
                    return pol.GetString();
                }
            }
        }
        catch (Exception ex)
        {
            BackendService.Instance.AppendLog($"[VidaApiClient] PolishLyrics error: {ex.Message}");
        }
        return null;
    }

    public async Task<string?> AskGeminiAssistantAsync(string prompt, List<LyricLine>? lyrics = null)
    {
        try
        {
            var lyricsPayload = lyrics?.Select(l => new
            {
                line_id = l.LineId,
                start = l.StartTime.TotalSeconds,
                end = l.EndTime.TotalSeconds,
                text = l.Text
            }).ToList();

            var payload = new
            {
                text = prompt,
                lyrics_data = lyricsPayload
            };
            var content = new StringContent(JsonSerializer.Serialize(payload), Encoding.UTF8, "application/json");
            var response = await _http.PostAsync($"{BaseUrl}/api/ai/llm/analyze", content);
            if (response.IsSuccessStatusCode)
            {
                var json = await response.Content.ReadAsStringAsync();
                using var doc = JsonDocument.Parse(json);
                if (doc.RootElement.TryGetProperty("analysis", out var an))
                {
                    return an.GetString();
                }
            }
        }
        catch (Exception ex)
        {
            BackendService.Instance.AppendLog($"[VidaApiClient] AskGemini error: {ex.Message}");
        }
        return null;
    }

    public async Task<string?> StartRenderJobAsync(object renderParams)
    {
        try
        {
            var content = new StringContent(JsonSerializer.Serialize(renderParams), Encoding.UTF8, "application/json");
            var response = await _http.PostAsync($"{BaseUrl}/api/render", content);
            if (response.IsSuccessStatusCode)
            {
                var json = await response.Content.ReadAsStringAsync();
                using var doc = JsonDocument.Parse(json);
                if (doc.RootElement.TryGetProperty("job_id", out var jobProp))
                {
                    return jobProp.GetString();
                }
            }
        }
        catch (Exception ex)
        {
            BackendService.Instance.AppendLog($"[VidaApiClient] Render trigger error: {ex.Message}");
        }
        return null;
    }

    public async Task<JsonElement?> GetRenderProgressAsync(string jobId)
    {
        try
        {
            var response = await _http.GetAsync($"{BaseUrl}/api/progress/{jobId}");
            if (response.IsSuccessStatusCode)
            {
                var json = await response.Content.ReadAsStringAsync();
                return JsonDocument.Parse(json).RootElement.Clone();
            }
        }
        catch
        {
            // Suppress polling error
        }
        return null;
    }
}

public class MediaItem
{
    public string Name { get; set; } = string.Empty;
    public string Path { get; set; } = string.Empty;
    public string Type { get; set; } = "audio";
    public string Url { get; set; } = string.Empty;
}
