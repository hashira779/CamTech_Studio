"""
SQLite persistence for Khmer Oldies AI Restoration Studio:
Stores projects, uploaded tracks, diagnostic metrics, restoration jobs, and exported master formats.
"""
import json
import os
import sqlite3
import time
from typing import Any, Dict, List, Optional

try:
    from backend.paths import UPLOAD_DIR
except ImportError:
    from paths import UPLOAD_DIR

DB_PATH = os.path.join(UPLOAD_DIR, "restoration.db")


def get_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS restoration_projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS restoration_tracks (
                id TEXT PRIMARY KEY,
                project_id TEXT,
                filename TEXT NOT NULL,
                original_path TEXT NOT NULL,
                file_size_bytes INTEGER,
                duration_seconds REAL,
                sample_rate INTEGER,
                channels INTEGER,
                bit_depth INTEGER,
                peak_dbfs REAL,
                rms_dbfs REAL,
                loudness_lufs REAL,
                dc_offset REAL,
                clipping_samples INTEGER,
                noise_floor_dbfs REAL,
                waveform_data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS restoration_jobs (
                id TEXT PRIMARY KEY,
                track_id TEXT NOT NULL,
                preset_name TEXT NOT NULL,
                bypass_ai INTEGER NOT NULL DEFAULT 0,
                parameters_json TEXT NOT NULL,
                status TEXT NOT NULL,
                progress_percent REAL NOT NULL DEFAULT 0.0,
                processing_time_seconds REAL,
                output_path TEXT,
                metrics_after_json TEXT,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS restoration_outputs (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                format TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_size_bytes INTEGER,
                sample_rate INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()


def save_track(track_data: Dict[str, Any]) -> str:
    init_db()
    track_id = track_data["id"]
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO restoration_tracks (
                id, project_id, filename, original_path, file_size_bytes,
                duration_seconds, sample_rate, channels, bit_depth,
                peak_dbfs, rms_dbfs, loudness_lufs, dc_offset,
                clipping_samples, noise_floor_dbfs, waveform_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            track_id,
            track_data.get("project_id"),
            track_data["filename"],
            track_data["original_path"],
            track_data.get("file_size_bytes", 0),
            track_data.get("duration_seconds", 0.0),
            track_data.get("sample_rate", 44100),
            track_data.get("channels", 2),
            track_data.get("bit_depth", 16),
            track_data.get("peak_dbfs", 0.0),
            track_data.get("rms_dbfs", 0.0),
            track_data.get("loudness_lufs", -14.0),
            track_data.get("dc_offset", 0.0),
            track_data.get("clipping_samples", 0),
            track_data.get("noise_floor_dbfs", -30.0),
            json.dumps(track_data.get("waveform_data", []))
        ))
        conn.commit()
    return track_id


def get_track(track_id: str) -> Optional[Dict[str, Any]]:
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM restoration_tracks WHERE id = ?", (track_id,))
        row = cursor.fetchone()
        if not row:
            return None
        res = dict(row)
        if res.get("waveform_data"):
            try:
                res["waveform_data"] = json.loads(res["waveform_data"])
            except Exception:
                res["waveform_data"] = []
        return res


def create_job(job_id: str, track_id: str, preset_name: str, bypass_ai: bool, params: Dict[str, Any]) -> str:
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO restoration_jobs (
                id, track_id, preset_name, bypass_ai, parameters_json, status, progress_percent
            ) VALUES (?, ?, ?, ?, ?, 'processing', 0.0)
        """, (
            job_id, track_id, preset_name, 1 if bypass_ai else 0, json.dumps(params)
        ))
        conn.commit()
    return job_id


def update_job_status(job_id: str, status: str, progress: float, output_path: Optional[str] = None,
                      metrics_after: Optional[Dict[str, Any]] = None, elapsed: Optional[float] = None,
                      error: Optional[str] = None):
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE restoration_jobs
            SET status = ?, progress_percent = ?, output_path = COALESCE(?, output_path),
                metrics_after_json = COALESCE(?, metrics_after_json),
                processing_time_seconds = COALESCE(?, processing_time_seconds),
                error_message = COALESCE(?, error_message),
                completed_at = CASE WHEN ? IN ('completed', 'failed') THEN CURRENT_TIMESTAMP ELSE completed_at END
            WHERE id = ?
        """, (
            status, progress, output_path,
            json.dumps(metrics_after) if metrics_after else None,
            elapsed, error, status, job_id
        ))
        conn.commit()


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM restoration_jobs WHERE id = ?", (job_id,))
        row = cursor.fetchone()
        if not row:
            return None
        res = dict(row)
        if res.get("parameters_json"):
            try:
                res["parameters"] = json.loads(res["parameters_json"])
            except Exception:
                res["parameters"] = {}
        if res.get("metrics_after_json"):
            try:
                res["metrics_after"] = json.loads(res["metrics_after_json"])
            except Exception:
                res["metrics_after"] = {}
        return res


def list_recent_jobs(limit: int = 20) -> List[Dict[str, Any]]:
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT j.*, t.filename, t.original_path
            FROM restoration_jobs j
            JOIN restoration_tracks t ON j.track_id = t.id
            ORDER BY j.created_at DESC LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        out = []
        for r in rows:
            d = dict(r)
            if d.get("parameters_json"):
                try:
                    d["parameters"] = json.loads(d["parameters_json"])
                except Exception:
                    d["parameters"] = {}
            if d.get("metrics_after_json"):
                try:
                    d["metrics_after"] = json.loads(d["metrics_after_json"])
                except Exception:
                    d["metrics_after"] = {}
            out.append(d)
        return out
