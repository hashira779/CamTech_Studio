import os
import re
import pytest
from backend import capcut_export

def test_describe_template_robust_fallback():
    # Synthetic template with title, singer, credit, and corner watermark
    synthetic_content = {
        "id": "TEST-TIMELINE-123",
        "tracks": [
            {
                "type": "audio",
                "segments": [
                    {
                        "material_id": "audio_mat_1",
                        "target_timerange": {"start": 0, "duration": 60000000}
                    }
                ]
            },
            {
                "type": "text",
                "segments": [
                    {"material_id": "mat_title", "clip": {"transform": {"x": 0.3, "y": 0.45}}}
                ]
            },
            {
                "type": "text",
                "segments": [
                    {"material_id": "mat_singer", "clip": {"transform": {"x": 0.3, "y": 0.22}}}
                ]
            },
            {
                "type": "text",
                "segments": [
                    {"material_id": "mat_credit", "clip": {"transform": {"x": 0.28, "y": 0.10}}}
                ]
            },
            {
                "type": "text",
                "segments": [
                    {"material_id": "mat_watermark", "clip": {"transform": {"x": 0.85, "y": -0.90}}}
                ]
            },
            {
                "type": "text",
                "segments": [
                    {"material_id": f"mat_cap_{i}", "target_timerange": {"start": i * 1000000, "duration": 1000000}}
                    for i in range(5)
                ]
            }
        ],
        "materials": {
            "audios": [
                {"id": "audio_mat_1", "path": "D:/some/path/completely_unrelated_audio.mp3", "name": "completely_unrelated_audio"}
            ],
            "texts": [
                {"id": "mat_title", "content": '{"text":"បួសនាគ","styles":[{"size":18}]}'},
                {"id": "mat_singer", "content": '{"text":"ស៊ីន ស៊ីសាមុត និង រស់ សេរីសុទ្ធា","styles":[{"size":12}]}'},
                {"id": "mat_credit", "content": '{"text":"Cover Lyric by : VibeTune","styles":[{"size":10}]}'},
                {"id": "mat_watermark", "content": '{"text":"VibeTune","styles":[{"size":8}]}'},
                *[
                    {"id": f"mat_cap_{i}", "content": f'{{"text":"Caption line {i}","styles":[]}}'}
                    for i in range(5)
                ]
            ]
        }
    }

    parts = capcut_export.describe_template(synthetic_content)
    assert parts["title"] is not None
    assert parts["title"]["text"] == "បួសនាគ"
    assert parts["singer"] is not None
    assert parts["singer"]["text"] == "ស៊ីន ស៊ីសាមុត និង រស់ សេរីសុទ្ធា"
    assert len(parts["captions"]) == 1

def test_describe_template_matching_audio():
    # If audio name matches, it directly binds
    synthetic_content = {
        "id": "TEST-TIMELINE-456",
        "tracks": [
            {
                "type": "audio",
                "segments": [
                    {
                        "material_id": "audio_mat_1",
                        "target_timerange": {"start": 0, "duration": 60000000}
                    }
                ]
            },
            {
                "type": "text",
                "segments": [
                    {"material_id": "mat_title", "clip": {"transform": {"x": 0.0, "y": 0.4}}}
                ]
            },
            {
                "type": "text",
                "segments": [
                    {"material_id": "mat_singer", "clip": {"transform": {"x": 0.0, "y": 0.2}}}
                ]
            },
            {
                "type": "text",
                "segments": [
                    {"material_id": f"mat_cap_{i}", "target_timerange": {"start": i * 1000000, "duration": 1000000}}
                    for i in range(3)
                ]
            }
        ],
        "materials": {
            "audios": [
                {"id": "audio_mat_1", "path": "D:/uploads/ស្រណោះផ្កាក្ទម្ព - ស៊ិន ស៊ីសាមុត.mp3", "name": "ស្រណោះផ្កាក្ទម្ព"}
            ],
            "texts": [
                {"id": "mat_title", "content": '{"text":"ស្រណោះផ្កាក្ទម្ព","styles":[{"size":20}]}'},
                {"id": "mat_singer", "content": '{"text":"ស៊ិន ស៊ីសាមុត","styles":[{"size":14}]}'},
                *[
                    {"id": f"mat_cap_{i}", "content": f'{{"text":"Caption {i}","styles":[]}}'}
                    for i in range(3)
                ]
            ]
        }
    }

    parts = capcut_export.describe_template(synthetic_content)
    assert parts["title"] is not None
    assert parts["title"]["text"] == "ស្រណោះផ្កាក្ទម្ព"
    assert parts["singer"] is not None
    assert parts["singer"]["text"] == "ស៊ិន ស៊ីសាមុត"


def test_describe_template_real_drafts_if_present():
    root = capcut_export.drafts_root()
    if not root:
        pytest.skip("CapCut not installed on this system")
    templates = capcut_export.list_templates()
    if not templates:
        pytest.skip("No CapCut templates found")
    for tpl in templates:
        p = os.path.join(tpl["folder"], "draft_content.json")
        if os.path.exists(p):
            content = capcut_export._read(p)
            parts = capcut_export.describe_template(content)
            # Both title and singer should be detected (not None) on valid templates
            assert parts["title"] is not None, f"Failed to detect title in template {tpl['name']}"
            assert parts["title"]["text"], f"Empty title detected in template {tpl['name']}"

