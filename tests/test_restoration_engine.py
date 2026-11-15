"""
Unit tests for Khmer Oldies AI Restoration Studio:
- Audio analysis diagnostics (Stage 1)
- Restoration presets & parameter overrides
- Database persistence for tracks, jobs, and outputs
"""
import os
import pytest
from backend.services import khmer_restoration_engine as engine
from backend.services import restoration_db


def test_presets_exist():
    presets = engine.PRESETS
    assert "archival_preservation" in presets
    assert "gentle_cleanup" in presets
    assert "vintage_studio" in presets
    assert "advanced_ai" in presets
    assert "modern_broadcast" in presets
    assert presets["vintage_studio"]["vocal_presence_db"] > 0


def test_restoration_db_lifecycle():
    import uuid
    uid = uuid.uuid4().hex[:8]
    track_id = f"test_track_{uid}"
    track_data = {
        "id": track_id,
        "filename": "test_song.mp3",
        "original_path": "d:/fake/path.mp3",
        "file_size_bytes": 1024,
        "duration_seconds": 120.0,
        "sample_rate": 44100,
        "channels": 2,
        "bit_depth": 16,
        "peak_dbfs": -1.5,
        "rms_dbfs": -16.0,
        "loudness_lufs": -14.5,
        "dc_offset": 0.0001,
        "clipping_samples": 0,
        "noise_floor_dbfs": -35.0,
        "waveform_data": [0.1, 0.5, 0.8, 0.2],
    }
    saved_id = restoration_db.save_track(track_data)
    assert saved_id == track_id

    fetched = restoration_db.get_track(track_id)
    assert fetched is not None
    assert fetched["filename"] == "test_song.mp3"
    assert len(fetched["waveform_data"]) == 4

    job_id = f"test_job_{uid}"
    created_job_id = restoration_db.create_job(
        job_id, track_id, "vintage_studio", bypass_ai=False, params={"warmth_db": 1.5}
    )
    assert created_job_id == job_id

    restoration_db.update_job_status(
        job_id, "completed", 100.0,
        output_path="d:/fake/restored.mp3",
        metrics_after={"noise_floor_dbfs": -40.0},
        elapsed=12.5
    )

    job = restoration_db.get_job(job_id)
    assert job is not None
    assert job["status"] == "completed"
    assert job["progress_percent"] == 100.0
    assert job["metrics_after"]["noise_floor_dbfs"] == -40.0
