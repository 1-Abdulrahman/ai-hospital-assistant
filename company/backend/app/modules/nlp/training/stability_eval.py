from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from app.modules.nlp.inference import NlpService

STABILITY_FILE = Path(__file__).resolve()
TRAINING_DIR = STABILITY_FILE.parent
STABILITY_CASES_PATH = TRAINING_DIR / "stability_cases.jsonl"
OUTPUT_REPORT_PATH = TRAINING_DIR / "stability_report.json"


def read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_json(path: Path, payload: dict) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def main() -> None:
    if not STABILITY_CASES_PATH.exists():
        raise FileNotFoundError(f"Missing stability cases file: {STABILITY_CASES_PATH}")

    rows = read_jsonl(STABILITY_CASES_PATH)
    service = NlpService.load_from_disk()

    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[row["family_id"]].append(row)

    family_reports: list[dict] = []

    for family_id, cases in sorted(groups.items()):
        case_reports: list[dict] = []
        top1_matches = 0
        top2_matches = 0
        ambiguous_count = 0

        for case in cases:
            prediction = service.classify(case["text"])
            top1 = prediction.top_candidates[0].specialty_id if prediction.top_candidates else None
            top2 = [candidate.specialty_id for candidate in prediction.top_candidates[:2]]

            if top1 == case["label"]:
                top1_matches += 1
            if case["label"] in top2:
                top2_matches += 1
            if prediction.needs_clarification:
                ambiguous_count += 1

            case_reports.append(
                {
                    "text": case["text"],
                    "goldLabel": case["label"],
                    "predictedTop1": top1,
                    "predictedTop2": top2,
                    "needsClarification": prediction.needs_clarification,
                    "reasonCode": prediction.reason_code,
                }
            )

        total = len(cases)
        family_reports.append(
            {
                "familyId": family_id,
                "cases": case_reports,
                "totalCases": total,
                "top1Accuracy": round(top1_matches / total, 4),
                "top2Coverage": round(top2_matches / total, 4),
                "ambiguityRate": round(ambiguous_count / total, 4),
            }
        )

    summary = {
        "totalFamilies": len(family_reports),
        "families": family_reports,
    }

    write_json(OUTPUT_REPORT_PATH, summary)
    print(f"Wrote stability report -> {OUTPUT_REPORT_PATH}")


if __name__ == "__main__":
    main()