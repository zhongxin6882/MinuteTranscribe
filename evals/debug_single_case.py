from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evals.judge_core_recall import evaluate_minutes, load_manifest
from src.pipeline import run_transcript_debug
from src.validate import load_transcript


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python3 evals/debug_single_case.py <dataset_filename>")

    dataset = sys.argv[1]
    case_path = Path("evals/dataset") / dataset
    if not case_path.exists():
        raise SystemExit(f"Dataset not found: {case_path}")

    transcript = load_transcript(case_path)
    result = run_transcript_debug(transcript)

    manifest = load_manifest()
    case_specs = {case["dataset"]: case for case in manifest.get("cases", []) if case.get("dataset")}
    judge = None
    if dataset in case_specs:
        judge = evaluate_minutes(case_specs[dataset], result["verified_minutes"])

    out_dir = Path("evals/results/debug")
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = out_dir / f"{case_path.stem}-{timestamp}.json"
    out_payload = {
        "dataset": dataset,
        "classification": result["classification"],
        "error": result["error"],
        "judge": judge,
        "raw_minutes": result["raw_minutes"],
        "verified_minutes": result["verified_minutes"],
        "transcript": transcript.to_dict(),
    }
    out_path.write_text(json.dumps(out_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"debug_path": str(out_path), "error": result["error"], "judge": judge}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
