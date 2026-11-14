"""
FastAPI REST routes for Khmer Oldies AI Restoration Studio.
Provides audio analysis diagnostics, 5 restoration presets, Demucs AI stem remixing,
fine-tuning controls, and multi-format master exporting.
"""
import os
import threading
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, UploadFile, File
from pydantic import BaseModel

try:
    from backend.paths import UPLOAD_DIR
    from backend.services import khmer_restoration_engine as engine
    from backend.services import restoration_db
except ImportError:
    from paths import UPLOAD_DIR
    from services import khmer_restoration_engine as engine
    from services import restoration_db

router = APIRouter(prefix="/api/restore", tags=["Khmer Restoration Studio"])


class AnalyzeRequest(BaseModel):
    audio_path: Optional[str] = None


class ProcessRequest(BaseModel):
    track_id: Optional[str] = None
    audio_path: Optional[str] = None
    preset: str = "vintage_studio"
    bypass_ai: bool = False
    overrides: Optional[Dict[str, Any]] = None
    export_format: str = "mp3_320"


class ExportRequest(BaseModel):
    audio_path: str
    format: str = "wav24"
    sample_rate: Optional[int] = None


def _resolve_audio_path(path: Optional[str]) -> str:
    if not path:
        raise HTTPException(status_code=400, detail="Missing audio path")
    clean = path.replace("file:///", "").replace("file://", "")
    if clean.startswith("/") and len(clean) > 2 and clean[2] == ":":
        clean = clean[1:]
    clean = os.path.normpath(clean)
    if not os.path.isabs(clean):
        clean = os.path.abspath(clean)
    if not os.path.isfile(clean):
        # Try finding in uploads/audio/
        alt = os.path.join(UPLOAD_DIR, "audio", os.path.basename(clean))
        if os.path.isfile(alt):
            return os.path.abspath(alt)
        raise HTTPException(status_code=404, detail=f"Audio file not found: {clean}")
    return os.path.abspath(clean)


def _to_web_url(filepath: str) -> str:
    """Converts local path to web accessible /uploads/ URL."""
    rel = os.path.relpath(filepath, UPLOAD_DIR).replace("\\", "/")
    return f"/uploads/{rel}"


@router.get("/presets")
def get_presets():
    """Lists the 5 restoration presets with descriptions and DSP targets."""
    return {"presets": list(engine.PRESETS.values())}


@router.post("/analyze")
def analyze_track_api(req: AnalyzeRequest):
    """Stage 1: Performs full physical and acoustic analysis on the vintage audio."""
    path = _resolve_audio_path(req.audio_path)
    try:
        data = engine.analyze_audio_file(path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

    track_id = f"trk_{uuid.uuid4().hex[:10]}"
    data["id"] = track_id
    restoration_db.save_track(data)
    data["url"] = _to_web_url(path)
    return {"status": "success", "track": data}


@router.post("/process")
def process_restoration_api(req: ProcessRequest, bg: BackgroundTasks):
    """Stages 2–5: Executes restoration pipeline with preset and optional AI stem separation."""
    audio_p = None
    track_id = req.track_id
    if track_id:
        track = restoration_db.get_track(track_id)
        if track:
            audio_p = track["original_path"]

    if not audio_p and req.audio_path:
        audio_p = _resolve_audio_path(req.audio_path)
        if not track_id:
            # Auto analyze and register
            diag = engine.analyze_audio_file(audio_p)
            track_id = f"trk_{uuid.uuid4().hex[:10]}"
            diag["id"] = track_id
            restoration_db.save_track(diag)

    if not audio_p or not os.path.isfile(audio_p):
        raise HTTPException(status_code=400, detail="Invalid track or audio path.")

    job_id = f"job_{uuid.uuid4().hex[:10]}"
    params = dict(engine.PRESETS.get(req.preset, engine.PRESETS["vintage_studio"]))
    if req.overrides:
        params.update(req.overrides)

    restoration_db.create_job(job_id, track_id, req.preset, req.bypass_ai, params)

    def run_job():
        try:
            engine.restore_track(
                audio_p,
                preset_key=req.preset,
                bypass_ai=req.bypass_ai,
                overrides=req.overrides,
                job_id=job_id,
            )
        except Exception as e:
            restoration_db.update_job_status(job_id, "failed", 0.0, error=str(e))

    bg.add_task(run_job)
    return {
        "status": "processing",
        "job_id": job_id,
        "track_id": track_id,
        "preset": req.preset,
    }


@router.get("/status/{job_id}")
def get_job_status_api(job_id: str):
    """Checks progress and retrieves completed master audio and metrics."""
    job = restoration_db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    res = dict(job)
    if job.get("output_path") and os.path.isfile(job["output_path"]):
        res["output_url"] = _to_web_url(job["output_path"])
    return res


@router.get("/jobs")
def list_jobs_api(limit: int = 20):
    """Lists recent restoration jobs."""
    jobs = restoration_db.list_recent_jobs(limit)
    for j in jobs:
        if j.get("output_path") and os.path.isfile(j["output_path"]):
            j["output_url"] = _to_web_url(j["output_path"])
    return {"jobs": jobs}


@router.post("/export")
def export_master_api(req: ExportRequest):
    """Stage 5: Exports restored audio into WAV 16/24/32-bit, MP3 320k, or FLAC."""
    audio_p = _resolve_audio_path(req.audio_path)
    try:
        exported = engine.export_restored_master(audio_p, req.format, req.sample_rate)
        return {
            "status": "success",
            "format": req.format,
            "file_path": exported,
            "download_url": _to_web_url(exported),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")
