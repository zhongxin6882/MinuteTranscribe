from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import classify as classify_mod
from src import llm as llm_mod
from src import pipeline as pipeline_mod


@contextmanager
def patched_media_pipeline():
    original_transcribe_audio = llm_mod.LLMClient.transcribe_audio
    original_complete_json = llm_mod.LLMClient.complete_json
    original_classify = classify_mod.classify_transcript
    original_pipeline_classify = pipeline_mod.classify_transcript

    def fake_transcribe_audio(self, audio_path, response_format="verbose_json"):
        return {
            "text": "我们今天验证音频转写链路，并确认它能进入现有纪要分析流程。",
            "segments": [
                {"start": 0.0, "speaker": "说话人1", "text": "我们今天验证音频转写链路。"},
                {"start": 2.5, "speaker": "说话人2", "text": "并确认它能进入现有纪要分析流程。"},
            ],
        }

    def fake_complete_json(self, system_prompt, user_prompt):
        if "结构化抽取器" in system_prompt:
            return {
                "summary": "音频转写后可进入纪要分析。",
                "core": {
                    "topics": [
                        {"title": "音频转写验证", "detail": "完成音频输入与转写链路验证", "evidence": ["s001"]},
                        {"title": "后续推进", "detail": "等待真实 ASR 联调并补视频链路与页面上传", "evidence": ["s002"]},
                    ],
                    "conclusions": [
                        {"text": "音频转写链路可用，已跑通到纪要输出", "status": "confirmed", "evidence": ["s002"]},
                    ],
                    "decisions": [],
                    "risks": [
                        {"text": "外网 ASR 不可达时无法真实转写", "level": "中", "evidence": ["s002"]},
                    ],
                    "open_questions": [],
                },
                "todos": [
                    {
                        "task": "验证视频转写",
                        "owner": "说话人2",
                        "due": "待定",
                        "extra": "先补 ffmpeg 环境",
                        "evidence": ["s002"],
                    }
                ],
            }
        return {"ok": True, "message": "connected"}

    def fake_classify_transcript(transcript):
        return classify_mod.Classification(
            meeting_type="project_sync",
            confidence=0.99,
            reason="smoke test",
            risk_tags=[],
            template="extract_project_sync",
        )

    try:
        llm_mod.LLMClient.transcribe_audio = fake_transcribe_audio
        llm_mod.LLMClient.complete_json = fake_complete_json
        classify_mod.classify_transcript = fake_classify_transcript
        pipeline_mod.classify_transcript = fake_classify_transcript
        yield
    finally:
        llm_mod.LLMClient.transcribe_audio = original_transcribe_audio
        llm_mod.LLMClient.complete_json = original_complete_json
        classify_mod.classify_transcript = original_classify
        pipeline_mod.classify_transcript = original_pipeline_classify


def make_sample_audio(output_path: Path) -> Path:
    aiff_path = output_path.with_suffix(".aiff")
    subprocess.run(["say", "我们今天验证音频转写链路，并确认它能进入现有纪要分析流程。", "-o", str(aiff_path)], check=True)
    subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16", str(aiff_path), str(output_path)], check=True)
    return output_path


def main() -> None:
    out_dir = Path("evals/results/media-smoke")
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    audio_path = make_sample_audio(Path(tempfile.gettempdir()) / f"minutes-media-smoke-{timestamp}.wav")
    with patched_media_pipeline():
        paths = pipeline_mod.run(audio_path, out_dir)
    print(json.dumps({key: str(path) for key, path in paths.items()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
