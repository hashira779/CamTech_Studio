using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Windows.Media.Playback;

namespace VidaStudio.Pages;

/// <summary>
/// Playback: MediaPlayer, timer tick, play/pause/seek, volume, transport controls.
/// </summary>
public sealed partial class StudioPage
{
    private void PlaybackSession_PlaybackStateChanged(MediaPlaybackSession sender, object args)
    {
        DispatcherQueue.TryEnqueue(() =>
        {
            if (sender.PlaybackState == MediaPlaybackState.Playing)
            {
                PlayPauseGlyph.Glyph = "\uE769"; // Pause
            }
            else
            {
                PlayPauseGlyph.Glyph = "\uE768"; // Play
            }
        });
    }

    private void PlaybackTimer_Tick(object? sender, object e)
    {
        bool isPlaying = _player.PlaybackSession.PlaybackState == MediaPlaybackState.Playing;

        if (isPlaying)
        {
            var session = _player.PlaybackSession;
            var pos = session.Position;
            var dur = session.NaturalDuration;

            if (dur > TimeSpan.Zero)
            {
                TotalTimeText.Text = dur.ToString(@"mm\:ss\.ff");
                WaveformSlider.Maximum = dur.TotalSeconds;
            }

            CurrentTimeText.Text = pos.ToString(@"mm\:ss\.ff");
            WaveformSlider.Value = pos.TotalSeconds;

            // Rotate center vinyl disc in DirectX (playing speed)
            // VinylRotateTransform.Angle = (VinylRotateTransform.Angle + 2.0) % 360;

            // Synchronize Khmer Lyrics
            var activeLine = _lyricLines.FirstOrDefault(l => l.IsActive(pos));
            if (activeLine != null && !string.IsNullOrEmpty(activeLine.Text))
            {
                StageLyricsText.Text = activeLine.Text;
                LyricTimecodeText.Text = $"{activeLine.StartTime:mm\\:ss} → {activeLine.EndTime:mm\\:ss} ({(int)(activeLine.Confidence * 100)}% Confidence)";
            }
        }
        else
        {
            // Ambient subtle vinyl rotation when paused/idle
            // VinylRotateTransform.Angle = (VinylRotateTransform.Angle + 0.4) % 360;
        }

        // Animate spectrum bars dynamically matching active theme and palette on EVERY frame
        UpdateVisualizerFrame();
    }

    // ================= TRANSPORT CONTROLS =================
    private void PlayPause_Click(object sender, RoutedEventArgs e)
    {
        if (_player.PlaybackSession.PlaybackState == MediaPlaybackState.Playing)
        {
            _player.Pause();
        }
        else
        {
            _player.Play();
        }
    }

    private void Stop_Click(object sender, RoutedEventArgs e)
    {
        _player.Pause();
        _player.Position = TimeSpan.Zero;
        WaveformSlider.Value = 0;
        CurrentTimeText.Text = "00:00:00";
    }

    private void Prev_Click(object sender, RoutedEventArgs e)
    {
        var pos = _player.PlaybackSession.Position;
        _player.Position = pos > TimeSpan.FromSeconds(5) ? pos - TimeSpan.FromSeconds(5) : TimeSpan.Zero;
    }

    private void Next_Click(object sender, RoutedEventArgs e)
    {
        _player.Position = _player.PlaybackSession.Position + TimeSpan.FromSeconds(5);
    }

    private void WaveformSlider_ValueChanged(object sender, Microsoft.UI.Xaml.Controls.Primitives.RangeBaseValueChangedEventArgs e)
    {
        if (Math.Abs(_player.PlaybackSession.Position.TotalSeconds - e.NewValue) > 1.5)
        {
            _player.Position = TimeSpan.FromSeconds(e.NewValue);
        }
    }

    private void VolumeSlider_ValueChanged(object sender, Microsoft.UI.Xaml.Controls.Primitives.RangeBaseValueChangedEventArgs e)
    {
        _player.Volume = e.NewValue / 100.0;
    }
}
