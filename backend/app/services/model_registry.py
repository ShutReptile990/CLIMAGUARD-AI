"""Fail-closed XGBoost artifact loader. No flood model is bundled without labels."""

import json
import hashlib
from dataclasses import dataclass
from pathlib import Path

EXPECTED_FEATURES = ["rainfall_24h_mm", "peak_hour_mm", "prior_72h_mm", "slope_mean_degrees", "drainage_index", "historical_flood_exposure"]


@dataclass(frozen=True)
class ModelLoadResult:
    available: bool
    reason: str
    version: str | None = None
    model: object | None = None


def load_flood_model(artifact_dir: Path) -> ModelLoadResult:
    manifest_path = artifact_dir / "manifest.json"
    model_path = artifact_dir / "model.json"
    if not manifest_path.exists() or not model_path.exists():
        return ModelLoadResult(False, "No evaluated flood model artifact is installed.")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        evaluation = manifest.get("evaluation") or {}
        required_metrics = ("test_precision", "test_recall", "test_f1", "test_pr_auc", "test_brier")
        if (manifest.get("algorithm") != "XGBoost" or manifest.get("feature_names") != EXPECTED_FEATURES or not manifest.get("version") or not manifest.get("test_period")
                or not all(isinstance(evaluation.get(key), (int, float)) and 0 <= evaluation[key] <= 1 for key in required_metrics)
                or manifest.get("model_sha256") != hashlib.sha256(model_path.read_bytes()).hexdigest()):
            return ModelLoadResult(False, "Model manifest lacks the expected features or held-out evaluation.")
        import xgboost as xgb
        model = xgb.XGBClassifier()
        model.load_model(model_path)
        names = model.get_booster().feature_names
        if names is not None and names != EXPECTED_FEATURES:
            return ModelLoadResult(False, "Model feature names do not match the expected schema.")
        return ModelLoadResult(True, "Evaluated model loaded.", manifest.get("version"), model)
    except (ImportError, OSError, ValueError, TypeError, json.JSONDecodeError):
        return ModelLoadResult(False, "Model artifact could not be validated or loaded.")
