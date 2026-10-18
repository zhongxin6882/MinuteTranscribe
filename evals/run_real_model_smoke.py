from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evals.judge_core_recall import evaluate_minutes, get_case_spec, load_manifest
from src.pipeline import run_transcript
from src.validate import load_transcript

DATASETS = [
    "project_sync_001.json",
    "decision_review_001.json",
    "brainstorming_001.json",
    "interview_research_001.json",
    "general_meeting_001.json",
    "brainstorming_002.json",
    "general_no_conclusion_001.json",
    "interleaved_topics_003.json",
    "speaker_missing_all_001.json",
]

RUNS_PER_CASE = 3


def main() -> None:
    out_dir = Path("evals/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_path = out_dir / f"real-model-smoke-{timestamp}.md"
    raw_path = out_dir / f"real-model-smoke-{timestamp}.json"
    manifest = load_manifest()
    case_specs = {case["dataset"]: case for case in manifest.get("cases", []) if case.get("dataset")}

    rows: list[dict] = []
    lines = [
        "# 真实模型稳定性测试",
        "",
        f"- 时间：`{timestamp}`",
        f"- case 数量：`{len(DATASETS)}`",
        f"- 每个 case 运行次数：`{RUNS_PER_CASE}`",
        "",
        "| case | 成功次数 | 失败次数 | 类型是否稳定 | 核心召回 | 观察 |",
        "|---|---:|---:|---|---:|---|",
    ]

    for dataset in DATASETS:
        print(f"[START] {dataset}", flush=True)
        case_path = Path("evals/dataset") / dataset
        run_results = []
        types: list[str] = []
        failures: list[str] = []
        judge_scores: list[float] = []
        judge_findings: list[str] = []

        for run_index in range(RUNS_PER_CASE):
            print(f"  - run {run_index + 1}/{RUNS_PER_CASE}", flush=True)
            try:
                transcript = load_transcript(case_path)
                minutes = run_transcript(transcript)
                meeting_type = minutes.get("meeting_type", "")
                types.append(meeting_type)
                case_spec = case_specs.get(dataset)
                judge_result = evaluate_minutes(case_spec, minutes) if case_spec else None
                if judge_result:
                    judge_scores.append(float(judge_result["score"]))
                    if not judge_result["ok"]:
                        judge_findings.extend(judge_result["findings"])
                run_results.append(
                    {
                        "run": run_index + 1,
                        "ok": True,
                        "meeting_type": meeting_type,
                        "summary": minutes.get("summary", ""),
                        "todos": len(minutes.get("todos") or []),
                        "judge": judge_result,
                    }
                )
                print(
                    f"    ok: type={meeting_type}, todos={len(minutes.get('todos') or [])}, "
                    f"core_recall={judge_result['score'] if judge_result else 'n/a'}",
                    flush=True,
                )
            except Exception as exc:  # noqa: BLE001
                failures.append(str(exc))
                run_results.append(
                    {
                        "run": run_index + 1,
                        "ok": False,
                        "error": str(exc),
                    }
                )
                print(f"    failed: {exc}", flush=True)

        type_counter = Counter(types)
        type_stable = len(type_counter) <= 1 and bool(types)
        success_count = sum(1 for item in run_results if item["ok"])
        failure_count = RUNS_PER_CASE - success_count
        avg_judge_score = round(sum(judge_scores) / len(judge_scores), 3) if judge_scores else 0.0

        if failure_count == RUNS_PER_CASE:
            note = "全部失败"
        elif failure_count > 0:
            note = "部分失败"
        elif judge_scores and avg_judge_score < 0.7:
            note = "核心召回偏低"
        elif not type_stable:
            note = "类型漂移"
        else:
            note = f"稳定输出 {next(iter(type_counter))}"

        lines.append(
            f"| `{dataset}` | {success_count} | {failure_count} | "
            f"{'是' if type_stable else '否'} | {avg_judge_score:.2f} | {note} |"
        )
        print(f"[DONE] {dataset} success={success_count} failure={failure_count} stable={type_stable}", flush=True)

        rows.append(
            {
                "dataset": dataset,
                "success_count": success_count,
                "failure_count": failure_count,
                "type_counter": dict(type_counter),
                "average_core_recall": avg_judge_score,
                "judge_findings": judge_findings,
                "failures": failures,
                "runs": run_results,
            }
        )

    lines.extend(
        [
            "",
            "## 判分建议",
            "",
            "- `5分`：全部 case 全部成功，核心召回高，类型无明显漂移。",
            "- `4分`：少量 case 偶发失败，但大部分成功且核心信息稳定召回。",
            "- `3分`：成功率一般，或存在明显类型漂移/核心召回偏低。",
            "- `2分`：多 case 失败，模型格式问题频繁。",
            "- `1分`：大面积失败，基本不可用。",
            "",
            "## 核心召回缺口",
            "",
        ]
    )

    for row in rows:
        if not row["judge_findings"]:
            continue
        lines.append(f"### `{row['dataset']}`")
        for finding in row["judge_findings"]:
            lines.append(f"- {finding}")
        lines.append("")

    lines.extend(
        [
            "",
            "## 原始失败信息",
            "",
        ]
    )

    for row in rows:
        if not row["failures"]:
            continue
        lines.append(f"### `{row['dataset']}`")
        for failure in row["failures"]:
            lines.append(f"- `{failure}`")
        lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    raw_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    print("[FINISH] report written", flush=True)
    print(json.dumps({"report": str(report_path), "raw": str(raw_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
