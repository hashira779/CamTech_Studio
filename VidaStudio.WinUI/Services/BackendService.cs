using System.Diagnostics;
using System.IO;
using System.Net.Http;

namespace VidaStudio.Services;

public class BackendService : IDisposable
{
    private static BackendService? _instance;
    public static BackendService Instance => _instance ??= new BackendService();

    private Process? _process;
    private readonly HttpClient _httpClient;
    private readonly List<string> _logBuffer = new();
    private readonly object _lock = new();

    public int Port { get; private set; } = 8000;
    public string BaseUrl => $"http://127.0.0.1:{Port}";
    public bool IsRunning { get; private set; }
    public bool IsReady { get; private set; }
    public string PythonPath { get; private set; } = string.Empty;

    public event Action<string>? LogReceived;
    public event Action? StatusChanged;

    public BackendService()
    {
        _httpClient = new HttpClient { Timeout = TimeSpan.FromSeconds(2) };
        FindPythonExecutable();
    }

    public string FindPythonExecutable()
    {
        string baseDir = AppContext.BaseDirectory;
        // Check for workspace root by walking up
        string current = baseDir;
        string? projectRoot = null;

        for (int i = 0; i < 6; i++)
        {
            if (File.Exists(Path.Combine(current, "backend", "app.py")))
            {
                projectRoot = current;
                break;
            }
            string? parent = Directory.GetParent(current)?.FullName;
            if (parent == null || parent == current) break;
            current = parent;
        }

        if (projectRoot == null)
        {
            projectRoot = @"D:\Project\VIDA";
        }

        string venvPython = Path.Combine(projectRoot, "venv", "Scripts", "python.exe");
        if (File.Exists(venvPython))
        {
            PythonPath = venvPython;
            return PythonPath;
        }

        PythonPath = "python.exe";
        return PythonPath;
    }

    public string GetProjectRoot()
    {
        string baseDir = AppContext.BaseDirectory;
        string current = baseDir;
        for (int i = 0; i < 6; i++)
        {
            if (File.Exists(Path.Combine(current, "backend", "app.py")))
            {
                return current;
            }
            string? parent = Directory.GetParent(current)?.FullName;
            if (parent == null || parent == current) break;
            current = parent;
        }
        return @"D:\Project\VIDA";
    }

    public async Task<bool> StartAsync()
    {
        if (IsRunning && IsReady) return true;

        // First check if a backend instance is already running on the port
        if (await CheckHealthAsync())
        {
            IsRunning = true;
            IsReady = true;
            AppendLog($"[VIDA C# Engine] Connected to already running backend on {BaseUrl}");
            StatusChanged?.Invoke();
            return true;
        }

        string projectRoot = GetProjectRoot();
        FindPythonExecutable();

        AppendLog($"[VIDA C# Engine] Starting AI Backend service from: {projectRoot}");
        AppendLog($"[VIDA C# Engine] Using Python runtime: {PythonPath}");

        var psi = new ProcessStartInfo
        {
            FileName = PythonPath,
            Arguments = $"-m uvicorn backend.app:app --host 127.0.0.1 --port {Port}",
            WorkingDirectory = projectRoot,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            CreateNoWindow = true
        };

        psi.Environment["KMP_DUPLICATE_LIB_OK"] = "TRUE";
        psi.Environment["OMP_NUM_THREADS"] = "4";
        psi.Environment["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1";

        try
        {
            _process = new Process { StartInfo = psi, EnableRaisingEvents = true };

            _process.OutputDataReceived += (_, e) =>
            {
                if (!string.IsNullOrEmpty(e.Data))
                {
                    AppendLog(e.Data);
                }
            };

            _process.ErrorDataReceived += (_, e) =>
            {
                if (!string.IsNullOrEmpty(e.Data))
                {
                    AppendLog($"[stderr] {e.Data}");
                }
            };

            _process.Exited += (_, _) =>
            {
                IsRunning = false;
                IsReady = false;
                AppendLog("[VIDA C# Engine] Backend process terminated.");
                StatusChanged?.Invoke();
            };

            _process.Start();
            _process.BeginOutputReadLine();
            _process.BeginErrorReadLine();
            IsRunning = true;
            StatusChanged?.Invoke();

            // Wait for backend to respond to health checks
            var startTime = DateTime.UtcNow;
            while (DateTime.UtcNow - startTime < TimeSpan.FromSeconds(25))
            {
                if (await CheckHealthAsync())
                {
                    IsReady = true;
                    AppendLog($"[VIDA C# Engine] Backend verified online at {BaseUrl}");
                    StatusChanged?.Invoke();
                    return true;
                }
                await Task.Delay(500);
            }

            AppendLog("[VIDA C# Engine] Backend started but health check timed out. Retrying in background...");
            return false;
        }
        catch (Exception ex)
        {
            AppendLog($"[VIDA C# Engine] Failed to launch backend: {ex.Message}");
            IsRunning = false;
            IsReady = false;
            StatusChanged?.Invoke();
            return false;
        }
    }

    public async Task<bool> CheckHealthAsync()
    {
        try
        {
            var response = await _httpClient.GetAsync($"{BaseUrl}/health");
            if (response.IsSuccessStatusCode)
            {
                return true;
            }
            // Fallback check root
            var rootResp = await _httpClient.GetAsync(BaseUrl);
            return rootResp.IsSuccessStatusCode;
        }
        catch
        {
            return false;
        }
    }

    public void Stop()
    {
        if (_process != null && !_process.HasExited)
        {
            try
            {
                AppendLog("[VIDA C# Engine] Gracefully stopping backend process tree...");
                _process.Kill(entireProcessTree: true);
                _process.Dispose();
            }
            catch (Exception ex)
            {
                AppendLog($"[VIDA C# Engine] Process stop error: {ex.Message}");
            }
            finally
            {
                _process = null;
                IsRunning = false;
                IsReady = false;
                StatusChanged?.Invoke();
            }
        }
    }

    public void AppendLog(string message)
    {
        string timestamp = DateTime.Now.ToString("HH:mm:ss");
        string formatted = $"[{timestamp}] {message}";

        lock (_lock)
        {
            _logBuffer.Add(formatted);
            if (_logBuffer.Count > 1000)
            {
                _logBuffer.RemoveAt(0);
            }
        }

        try
        {
            File.AppendAllText(@"d:\Project\VIDA\backend.log", formatted + Environment.NewLine);
        }
        catch { }

        LogReceived?.Invoke(formatted);
    }

    public IReadOnlyList<string> GetLogs()
    {
        lock (_lock)
        {
            return _logBuffer.ToList();
        }
    }

    public void Dispose()
    {
        Stop();
        _httpClient.Dispose();
    }
}
