"""
Send to CapCut: a new CapCut desktop project made from one of the user's own CapCut projects used as
a template (background, photos, stickers, effects, credit lines all kept), with VIDA's song in it:
the audio, the title, the singer, the lyric lines as captions (original, and the translation as the
second caption track) timed exactly as in VIDA, and everything that runs to the end of the template
song stretched or cut to the new song's length.

CapCut has no import API, but keeps every project as JSON in its drafts folder. That format is not
documented and changes between versions, so the template is copied as CapCut wrote it and only the
pieces above are rewritten. Existing projects are never modified. The new project is added to
CapCut's project list (root_meta_info.json, backed up first). CapCut keeps that list in memory and
writes it back when it closes, so while CapCut is open the project is built at once and added to
the list as soon as CapCut closes (remembered across VIDA restarts until then).
"""
import copy
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

US = 1_000_000  # CapCut times are microseconds
# A template part ending this close to the template song's end "runs to the end" and follows the new length.
RUNS_TO_END_US = 3 * US
# Audio extras computed from the template song itself; they would apply to the wrong audio.
AUDIO_REFS_DROPPED = ("loudnesses", "vocal_beautifys")
# Copied with the project but not part of it: locks, CapCut's own backups and temp files.
NOT_COPIED = shutil.ignore_patterns(".locked", "*.bak", "*.tmp", "*.vida-tmp")
CREDIT_WORDS = re.compile(r"\b(by|lyric|lyrics|cover|credit)\b", re.I)


class CapCutError(Exception):
    """A reason the project could not be made, in words the studio can show."""


def drafts_root() -> Optional[str]:
    root = os.path.join(os.environ.get("LOCALAPPDATA", ""), "CapCut", "User Data", "Projects", "com.lveditor.draft")
    return root if os.path.isfile(os.path.join(root, "root_meta_info.json")) else None


def capcut_running() -> bool:
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq CapCut.exe", "/NH"], capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return False
    return "capcut.exe" in out.lower()


# Projects made while CapCut was open, waiting to be added to its list once it closes.
PENDING_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads", "capcut_pending.json")
_PENDING_LOCK = threading.Lock()
_waiter: Optional[threading.Thread] = None
# CapCut writes its list as it exits; give it this long after the process is gone.
SETTLE_S = 2.0
POLL_S = 3.0


def _add_to_listing(root: str, entry: Dict[str, Any]) -> None:
    """Puts the project first in CapCut's list, read fresh from disk, keeping a backup of the list."""
    listing_path = os.path.join(root, "root_meta_info.json")
    listing = _read(listing_path)
    if any(e.get("draft_id") == entry.get("draft_id") for e in listing.get("all_draft_store") or []):
        return
    shutil.copy2(listing_path, listing_path + ".vida-backup")
    listing["all_draft_store"] = [entry] + list(listing.get("all_draft_store") or [])
    if isinstance(listing.get("draft_ids"), int):
        listing["draft_ids"] += 1
    _write(listing_path, listing)


def _pending() -> List[Dict[str, Any]]:
    try:
        return _read(PENDING_FILE)
    except Exception:
        return []


def register_pending() -> int:
    """Adds every waiting project to CapCut's list if CapCut is closed; returns how many were added."""
    root = drafts_root()
    if not root or capcut_running():
        return 0
    with _PENDING_LOCK:
        waiting = _pending()
        if not waiting:
            return 0
        added = 0
        for entry in waiting:
            if os.path.isdir(entry.get("draft_fold_path", "")):
                _add_to_listing(root, entry)
                added += 1
        os.remove(PENDING_FILE)
    return added


def _wait_for_close() -> None:
    while _pending():
        time.sleep(POLL_S)
        if not capcut_running():
            time.sleep(SETTLE_S)
            if not capcut_running():
                register_pending()


def watch_pending() -> None:
    """Starts (once) the background wait that lists waiting projects when CapCut closes."""
    global _waiter
    if _pending() and not (_waiter and _waiter.is_alive()):
        _waiter = threading.Thread(target=_wait_for_close, name="capcut-pending", daemon=True)
        _waiter.start()


def _new_id() -> str:
    """CapCut's own id style: upper case except the version group (e.g. 'F2C7...-48d4-...')."""
    parts = str(uuid.uuid4()).upper().split("-")
    parts[2] = parts[2].lower()
    return "-".join(parts)


def _read(path: str) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write(path: str, data: Any) -> None:
    tmp = path + ".vida-tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


def _norm(t: str) -> str:
    return re.sub(r"[\s\W_]+", "", t or "").lower()


def _materials_by_id(content: Dict[str, Any]) -> Dict[str, Tuple[str, Dict[str, Any]]]:
    return {m["id"]: (kind, m) for kind, items in content.get("materials", {}).items() if isinstance(items, list)
            for m in items if isinstance(m, dict) and "id" in m}


def _text_of(mat: Dict[str, Any]) -> str:
    try:
        return json.loads(mat.get("content") or "{}").get("text", "")
    except ValueError:
        return ""


def _set_text(mat: Dict[str, Any], text: str) -> None:
    """Replaces the words, keeping the first style (font, size, colour) for all of them."""
    try:
        content = json.loads(mat.get("content") or "{}")
    except ValueError:
        content = {}
    style = copy.deepcopy((content.get("styles") or [{}])[0])
    style["range"] = [0, len(text.encode("utf-16-le")) // 2]
    mat["content"] = json.dumps({"text": text, "styles": [style]}, ensure_ascii=False, separators=(",", ":"))
    for key in ("recognize_text", "base_content"):
        if key in mat:
            mat[key] = ""


def _reset_cloud(d: Dict[str, Any]) -> None:
    """A new project is local only: clear what ties the template to its cloud copy."""
    for k, v in list(d.items()):
        if k.startswith(("tm_draft_cloud", "draft_cloud", "cloud_")):
            d[k] = (-1 if "parent" in k else 0) if isinstance(v, int) and not isinstance(v, bool) else type(v)()


def list_templates() -> List[Dict[str, Any]]:
    """CapCut projects that can serve as a template (they have captions and audio), newest first."""
    root = drafts_root()
    if not root:
        return []
    listing = _read(os.path.join(root, "root_meta_info.json"))
    out = []
    for entry in sorted(listing.get("all_draft_store") or [], key=lambda e: e.get("tm_draft_modified", 0), reverse=True):
        try:
            content = _read(os.path.join(entry.get("draft_fold_path", ""), "draft_content.json"))
        except Exception:
            continue  # cloud-only, encrypted or removed
        types = {t.get("type") for t in content.get("tracks", []) if t.get("segments")}
        if {"text", "audio"} <= types:
            out.append({"name": entry.get("draft_name", ""), "folder": entry.get("draft_fold_path", ""),
                        "modified": entry.get("tm_draft_modified", 0)})
    return out


def describe_template(content: Dict[str, Any]) -> Dict[str, Any]:
    """
    Finds the template's parts: the song (longest audio clip), the caption tracks (text tracks with
    several lines, longest first), the title (the one-line text matching the template song's name)
    and the singer (the one-line text just under the title that is not a credit line).
    """
    by_id = _materials_by_id(content)
    audio = max(((t, s) for t in content["tracks"] if t.get("type") == "audio" for s in t.get("segments", [])),
                key=lambda ts: ts[1]["target_timerange"]["duration"], default=(None, None))
    if audio[0] is None:
        raise CapCutError("The CapCut template has no audio clip.")
    captions = sorted((t for t in content["tracks"] if t.get("type") == "text" and len(t.get("segments", [])) >= 3),
                      key=lambda t: len(t["segments"]), reverse=True)
    singles = []
    for t in content["tracks"]:
        if t.get("type") == "text" and len(t.get("segments", [])) == 1:
            seg = t["segments"][0]
            kind, mat = by_id.get(seg["material_id"], (None, None))
            if kind == "texts":
                pos = (seg.get("clip") or {}).get("transform") or {}
                singles.append({"segment": seg, "material": mat, "text": _text_of(mat),
                                "x": float(pos.get("x", 0)), "y": float(pos.get("y", 0))})
    song_mat = by_id[audio[1]["material_id"]][1]
    song_name = os.path.splitext(os.path.basename(song_mat.get("path", "")))[0] or song_mat.get("name", "")
    song_title = _norm(song_name.split(" - ")[0])
    title = next((s for s in singles if song_title and _norm(s["text"]) and (_norm(s["text"]) in song_title or song_title in _norm(s["text"]))), None)
    singer = None
    if title:
        below = [s for s in singles if s is not title and s["y"] < title["y"] and abs(s["x"] - title["x"]) < 0.35
                 and not CREDIT_WORDS.search(s["text"])]
        singer = max(below, key=lambda s: s["y"], default=None)
    return {"audio_track": audio[0], "audio_segment": audio[1], "audio_material": song_mat,
            "captions": captions, "title": title, "singer": singer}


def _retime(content: Dict[str, Any], skip: set, old_end: int, new_end: int) -> None:
    """Parts that run to the template song's end follow the new length; nothing goes past it."""
    by_id = _materials_by_id(content)
    for track in content["tracks"]:
        if id(track) in skip:
            continue
        kept = []
        for seg in track.get("segments", []):
            tr = seg["target_timerange"]
            start, end = tr["start"], tr["start"] + tr["duration"]
            if start >= new_end:
                continue
            if end >= old_end - RUNS_TO_END_US:
                end = new_end - (old_end - end) if old_end > end else new_end
            end = min(end, new_end)
            mat = by_id.get(seg.get("material_id"), (None, {}))[1]
            src = seg.get("source_timerange")
            if isinstance(src, dict) and mat.get("type") == "video" and mat.get("duration"):
                end = min(end, start + mat["duration"] - src.get("start", 0))  # a real video cannot run longer than itself
            tr["duration"] = max(US // 10, end - start)
            if isinstance(src, dict):
                src["duration"] = tr["duration"]
            kept.append(seg)
        track["segments"] = kept


def _copy_project(src: str, dst: str, timeline_id: str) -> None:
    """
    What a project needs, not its caches: the files at the top, its timeline folder and the Resources
    folder layout. Left out: Resources/audioAlg (the template song's processed audio, 1.9 GB on the
    first template, useless for another song), ai_material and the {…} history folders (nothing in
    the timeline points at them).
    """
    os.makedirs(dst)
    for name in os.listdir(src):
        sp, dp = os.path.join(src, name), os.path.join(dst, name)
        if os.path.isfile(sp):
            if not NOT_COPIED(src, [name]):
                shutil.copy2(sp, dp)
        elif name == "Timelines":
            tl = os.path.join(sp, timeline_id)
            if os.path.isdir(tl):
                shutil.copytree(tl, os.path.join(dp, timeline_id), ignore=NOT_COPIED)
            # Timelines/project.json names the main timeline; without it CapCut lists the project
            # but cannot open it (measured: the first VIDA projects would not open).
            for f in os.listdir(sp):
                if os.path.isfile(os.path.join(sp, f)) and not NOT_COPIED(sp, [f]):
                    shutil.copy2(os.path.join(sp, f), os.path.join(dp, f))
        elif name == "Resources":
            for here, dirs, files in os.walk(sp):
                rel = os.path.relpath(here, sp)
                os.makedirs(os.path.join(dp, rel), exist_ok=True)
                if rel.split(os.sep)[0] == "audioAlg":
                    continue
                for f in files:
                    if not NOT_COPIED(here, [f]):
                        shutil.copy2(os.path.join(here, f), os.path.join(dp, rel, f))


def create_project(template_folder: Optional[str], audio_path: str, duration_s: float, title: str, singer: str,
                   caption_tracks: List[List[Dict[str, Any]]]) -> Dict[str, Any]:
    """
    Copies the template project into a new one with VIDA's song. caption_tracks: [original lines,
    translation lines?], each line {"start", "end", "text"} in seconds. Returns what was made and
    which template parts were replaced.
    """
    root = drafts_root()
    if not root:
        raise CapCutError("CapCut for Windows was not found on this computer.")
    if not audio_path or not os.path.isfile(audio_path):
        raise CapCutError("The song's audio file was not found.")
    templates = list_templates()
    tpl = next((t for t in templates if t["folder"] == template_folder or t["name"] == template_folder), None) if template_folder else None
    tpl = tpl or (templates[0] if templates else None)
    if not tpl:
        raise CapCutError("Make one CapCut project with your design, a song and its captions first; "
                          "VIDA uses it as the template for every song.")
    tpl_folder = tpl["folder"]
    content = _read(os.path.join(tpl_folder, "draft_content.json"))
    parts = describe_template(content)
    lines_in = [[l for l in t if str(l.get("text", "")).strip() and float(l["end"]) > float(l["start"])] for t in caption_tracks]
    lines_in = [t for t in lines_in if t]

    base = re.sub(r'[\\/:*?"<>|]+', " ", title or os.path.splitext(os.path.basename(audio_path))[0]).strip()[:60] or "VIDA lyrics"
    folder_name, n = f"{base} (VIDA)", 2
    while os.path.exists(os.path.join(root, folder_name)):
        folder_name, n = f"{base} (VIDA {n})", n + 1
    folder = os.path.join(root, folder_name).replace("\\", "/")
    root_fwd = root.replace("\\", "/")

    # The song: same clip, effects and volume, new file and length.
    audio_us = int(round(duration_s * US))
    old_end = parts["audio_segment"]["target_timerange"]["start"] + parts["audio_segment"]["target_timerange"]["duration"]
    new_end = parts["audio_segment"]["target_timerange"]["start"] + audio_us
    by_id = _materials_by_id(content)
    am = parts["audio_material"]
    am.update({"path": audio_path.replace("\\", "/"), "name": base, "duration": audio_us})
    for key, empty in (("music_id", None), ("wave_points", [])):
        if key in am:
            am[key] = str(uuid.uuid4()) if empty is None else empty
    seg = parts["audio_segment"]
    refs = []
    for ref in seg.get("extra_material_refs", []):
        kind, m = by_id.get(ref, (None, None))
        if kind in AUDIO_REFS_DROPPED:
            continue
        if isinstance(m, dict) and isinstance(m.get("time_range"), dict):
            m["time_range"] = {"start": 0, "duration": audio_us}
        refs.append(ref)
    seg["extra_material_refs"] = refs
    seg["source_timerange"] = {"start": 0, "duration": audio_us}
    seg["target_timerange"]["duration"] = audio_us

    # Title and singer, in the template's own font, size and place. A blank singer removes the
    # design's singer line: keeping it would credit the template song's singers on another song.
    replaced, removed = [], []
    for key, text in (("title", title), ("singer", singer)):
        part = parts[key]
        if not part:
            continue
        if str(text or "").strip():
            _set_text(part["material"], str(text).strip())
            replaced.append(key)
        elif key == "singer":
            for track in content["tracks"]:
                if part["segment"] in track.get("segments", []):
                    track["segments"] = [x for x in track["segments"] if x is not part["segment"]]
            gone = {part["segment"]["material_id"], *part["segment"].get("extra_material_refs", [])}
            for kind, items in content["materials"].items():
                if isinstance(items, list):
                    content["materials"][kind] = [m for m in items if not (isinstance(m, dict) and m.get("id") in gone)]
            removed.append(key)

    # Captions: each track keeps its look; its lines become VIDA's lines.
    mats = content["materials"]
    for track, lines in zip(parts["captions"], lines_in):
        seg_tpl = track["segments"][0]
        mat_tpl = by_id[seg_tpl["material_id"]][1]
        anim_tpl = next((by_id[r][1] for r in seg_tpl.get("extra_material_refs", []) if by_id.get(r, ("",))[0] == "material_animations"), None)
        old_ids = {s["material_id"] for s in track["segments"]} | {r for s in track["segments"] for r in s.get("extra_material_refs", [])}
        for kind in ("texts", "material_animations"):
            mats[kind] = [m for m in mats.get(kind, []) if m.get("id") not in old_ids]
        render_index = seg_tpl.get("render_index", 14000)
        new_segments = []
        for line in lines:
            mat = copy.deepcopy(mat_tpl)
            mat["id"] = _new_id()
            _set_text(mat, str(line["text"]).strip())
            mats["texts"].append(mat)
            refs = []
            if anim_tpl:
                anim = copy.deepcopy(anim_tpl)
                anim["id"] = _new_id()
                mats["material_animations"].append(anim)
                refs.append(anim["id"])
            s = copy.deepcopy(seg_tpl)
            start = int(round(float(line["start"]) * US))
            s.update({"id": _new_id(), "material_id": mat["id"], "extra_material_refs": refs, "render_index": render_index,
                      "target_timerange": {"start": start, "duration": max(1, int(round(float(line["end"]) * US)) - start)}})
            render_index += 1
            new_segments.append(s)
        track["segments"] = new_segments
    caption_tracks_used = parts["captions"][:len(lines_in)]
    # A template caption track VIDA has no lines for (no translation yet) is emptied, not left with the
    # old song's words, and those words leave the project file too.
    for track in parts["captions"][len(lines_in):]:
        old_ids = {x["material_id"] for x in track["segments"]} | {r for x in track["segments"] for r in x.get("extra_material_refs", [])}
        for kind in ("texts", "material_animations"):
            mats[kind] = [m for m in mats.get(kind, []) if m.get("id") not in old_ids]
        track["segments"] = []

    _retime(content, {id(t) for t in caption_tracks_used} | {id(parts["audio_track"])}, old_end, new_end)
    content["duration"] = max(new_end, max((s["target_timerange"]["start"] + s["target_timerange"]["duration"]
                                            for t in content["tracks"] for s in t.get("segments", [])), default=new_end))
    # The timeline keeps its id: timeline_layout.json and the Timelines/<id> folder are keyed on it.

    meta = _read(os.path.join(tpl_folder, "draft_meta_info.json"))
    _reset_cloud(meta)
    now_us = int(time.time() * US)
    meta.update({"draft_id": str(uuid.uuid4()).upper(), "draft_name": folder_name, "draft_fold_path": folder,
                 "draft_root_path": root_fwd, "tm_duration": content["duration"], "tm_draft_create": now_us, "tm_draft_modified": now_us})

    listing_path = os.path.join(root, "root_meta_info.json")
    listing = _read(listing_path)
    tpl_entry = next(e for e in listing.get("all_draft_store", []) if e.get("draft_fold_path") == tpl_folder)
    entry = copy.deepcopy(tpl_entry)
    _reset_cloud(entry)
    entry.update({"draft_id": meta["draft_id"], "draft_name": folder_name, "draft_fold_path": folder,
                  "draft_root_path": root_fwd, "draft_json_file": folder + "\\draft_content.json",
                  "draft_cover": folder + "\\draft_cover.jpg", "tm_duration": content["duration"],
                  "tm_draft_create": now_us, "tm_draft_modified": now_us})

    _copy_project(tpl_folder, folder, content["id"])
    try:
        _write(os.path.join(folder, "draft_content.json"), content)
        # CapCut 9.7 keeps the same timeline under Timelines/<id>/ too (identical in the template).
        timeline_copy = os.path.join(folder, "Timelines", content["id"], "draft_content.json")
        if os.path.isfile(timeline_copy):
            _write(timeline_copy, content)
        _write(os.path.join(folder, "draft_meta_info.json"), meta)
        # Other project files may name the template's folder; point them at the new one.
        for here, _, files in os.walk(folder):
            for name in files:
                if not name.endswith(".json") or name in ("draft_content.json", "draft_meta_info.json"):
                    continue
                p = os.path.join(here, name)
                try:
                    with open(p, encoding="utf-8") as f:
                        text = f.read()
                except UnicodeDecodeError:
                    continue
                if tpl_folder in text:
                    with open(p, "w", encoding="utf-8") as f:
                        f.write(text.replace(tpl_folder, folder))
        listed_now = not capcut_running()
        if listed_now:
            _add_to_listing(root, entry)
        else:
            with _PENDING_LOCK:
                waiting = _pending() + [entry]
                os.makedirs(os.path.dirname(PENDING_FILE), exist_ok=True)
                _write(PENDING_FILE, waiting)
            watch_pending()
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return {"name": folder_name, "folder": folder, "template": tpl["name"], "replaced": replaced, "removed": removed,
            "listed": listed_now,
            "title_found": bool(parts["title"]), "singer_found": bool(parts["singer"]),
            "caption_tracks": len(caption_tracks_used), "length_s": round(content["duration"] / US, 1)}
