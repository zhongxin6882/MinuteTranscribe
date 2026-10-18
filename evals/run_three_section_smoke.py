from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evals.judge_three_section_minutes import evaluate_minutes, get_case_spec, load_manifest
from src.pipeline import run_transcript
from src.validate import load_transcript


def main() -> None:
    out_dir = Path("evals/results/three-section-smoke")
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    manifest = load_manifest()
    case_specs = {case["dataset"]: case for case in manifest.get("cases", []) if case.get("dataset")}
    rows: list[dict] = []
    for dataset in [case["dataset"] for case in manifest.get("cases", []) if case.get("dataset")]:
        case_path = Path("evals/dataset") / dataset
        transcript = load_transcript(case_path)
        minutes = run_transcript(transcript)
        case_spec = case_specs.get(dataset)
        judge = evaluate_minutes(case_spec, minutes) if case_spec else None
        rows.append({"dataset": dataset, "judge": judge, "meeting_type": minutes.get("meeting_type")})
        print(json.dumps({"dataset": dataset, "judge": judge}, ensure_ascii=False))
    (out_dir / f"three-section-smoke-{timestamp}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
