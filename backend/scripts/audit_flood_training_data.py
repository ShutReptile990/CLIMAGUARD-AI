"""Fail-closed audit of verified flood labels before any model training."""

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.import_verified_flood_labels import validate_labels

ROOT = Path(__file__).resolve().parents[2]


def audit(raw_dir: Path) -> dict:
    files = sorted(raw_dir.glob("*flood*label*.csv"))
    positive = negative = 0
    periods = set()
    rejected = []
    for path in files:
        try:
            result = validate_labels(path)
            positive += result["positive_labels"]
            negative += result["verified_negative_labels"]
            periods.update(item["observed_at"][:7] for item in result["valid_records"])
            rejected.extend({"file": path.name, **item} for item in result["failed_records"])
        except (OSError, ValueError) as exc:
            rejected.append({"file": path.name, "reason": str(exc)})
    # These are gates, not claims that meeting them alone validates a model.
    count_gate = positive >= 100 and negative >= 100 and len(periods) >= 6 and not rejected
    return {"label_files": [path.name for path in files], "verified_positive_labels": positive,
            "verified_negative_labels": negative, "distinct_event_months": len(periods),
            "invalid_records": rejected, "label_count_gate_passed": count_gate, "training_gate_passed": False,
            "training_performed": False, "xgboost_model_artifact": None, "evaluation_metrics": None,
            "shap_explanations": False,
            "reason": "No sufficient verified, timestamped positive and negative labels with linked pre-event features. Incident reports are not labels." if not count_gate else "Label count gate passed; pre-event feature linkage, leakage audit and time-aware split are still required before training.",
            "active_method": "flood-rainfall-index-v1 deterministic heuristic"}


if __name__ == "__main__":
    result = audit(ROOT / "data/raw")
    target = ROOT / "ml/dataset_audit.json"
    target.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("label_files", "verified_positive_labels", "verified_negative_labels", "training_gate_passed", "training_performed")}))
