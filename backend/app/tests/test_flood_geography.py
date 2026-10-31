"""DEMO fixtures verify flood geography; they are not training observations."""

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from types import SimpleNamespace

from app.services.local_waterways import local_waterway_context
from app.services.analysis import AnalysisService, _feature_availability, _local_context
from app.services.vulnerability import evaluate_vulnerability
from app.services.zones import grid_zones
from scripts.audit_flood_training_data import audit
from scripts.import_pune_waterways import import_database, parse_file, zone_indicators
from scripts.import_verified_flood_labels import validate_labels


ROOT = Path(__file__).resolve().parents[3]


def test_real_waterways_are_validated_and_have_sourced_proximity():
    batch = parse_file(ROOT / "data/raw/pune_waterways.geojson")
    assert batch["feature_count"] == len(batch["records"]) == 213
    assert not batch["failures"] and not batch["duplicate_ids"]
    assert batch["counts"]["drain"] == 30 and batch["culvert_count"] == 46
    indicators = zone_indicators(batch["records"])
    assert len(indicators) == 9
    assert all(item["mapped_waterway_distance_m"] is not None for item in indicators)
    assert len(local_waterway_context()) == 9


def test_waterway_duplicate_and_municipal_metadata_validation(tmp_path):
    feature = {"type": "Feature", "properties": {"@id": "way/123", "waterway": "drain"},
               "geometry": {"type": "LineString", "coordinates": [[73.84, 18.52], [73.85, 18.53]]}}
    path = tmp_path / "DEMO_waterways.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": [feature, feature]}), encoding="utf-8")
    result = parse_file(path)
    assert len(result["records"]) == 1 and result["duplicate_ids"] == ["way/123"]
    metadata = {"authority": "DEMO authority", "dataset_id": "DEMO-drains", "licence": "DEMO licence",
                "capture_date": "2025-01-01", "source_url": "https://example.invalid/demo"}
    feature["properties"] = {"external_id": "DEMO-1", "waterway_class": "storm_drain"}
    path.write_text(json.dumps({"type": "FeatureCollection", "features": [feature]}), encoding="utf-8")
    municipal = parse_file(path, municipal_metadata=metadata)
    assert municipal["records"][0]["source_dataset"] == "municipal:DEMO-drains"


def test_verified_label_validator_requires_evidence_and_explicit_negative(tmp_path):
    csv_path = tmp_path / "DEMO_flood_labels.csv"
    date = datetime(2025, 8, 1, 12, tzinfo=timezone.utc).isoformat()
    header = "event_id,event_date,latitude,longitude,source,temporal_resolution_hours,observed_flood_status,verification_reference,observation_method\n"
    csv_path.write_text(header + f"DEMO-1,{date},18.525,73.865,DEMO source,24,true,DEMO reference,field survey\n"
                        + f"DEMO-2,{date},18.525,73.865,DEMO source,24,false,DEMO reference,field survey\n"
                        + f"DEMO-3,{date},18.525,73.865,DEMO source,24,unknown,DEMO reference,field survey\n", encoding="utf-8")
    result = validate_labels(csv_path)
    assert result["positive_labels"] == result["verified_negative_labels"] == 1
    assert len(result["failed_records"]) == 1


def test_vulnerability_requires_multiple_independent_domains():
    zone = grid_zones()[0]
    partial = evaluate_vulnerability(zone.geometry, {"population_estimate": 1000})
    assert partial["status"] == "unavailable" and partial["index"] is None
    sourced = evaluate_vulnerability(zone.geometry, {"population_estimate": 1000, "slope_mean_degrees": 2,
                                                   "mapped_hospitals": 1, "mapped_schools": 2,
                                                   "mapped_emergency_services": 1})
    assert sourced["status"] == "provisional" and 0 <= sourced["index"] <= 1
    assert any("historical" in warning for warning in sourced["warnings"])


def test_no_verified_labels_means_no_training(tmp_path):
    result = audit(tmp_path)
    assert result["verified_positive_labels"] == result["verified_negative_labels"] == 0
    assert result["training_gate_passed"] is False
    assert result["xgboost_model_artifact"] is None


def test_dashboard_context_exposes_provenance_without_capacity_claim():
    context = _local_context()
    assert len(context) == 9
    metrics = AnalysisService.metrics_from_context(context[grid_zones()[0].slug])
    assert metrics is not None and metrics.mapped_drain_distance_m is not None
    features = {item.name: item for item in _feature_availability(None, metrics)}
    assert features["Mapped drainage proximity"].status == "partial"
    assert "capacity" in features["Mapped drainage proximity"].limitation
    assert features["Calibrated flood model"].status == "unavailable"


def test_grid_metrics_and_city_scope_do_not_overstate_coverage():
    context = _local_context()
    slug = grid_zones()[0].slug
    metrics = AnalysisService.metrics_from_context(context[slug])
    assert metrics and metrics.population_estimate is not None
    assert AnalysisService.metrics_from_context({"mapped_drain_distance_m": 250,
        "provenance": {"mapped_waterways": {"source": "OpenStreetMap", "storage": "local_geojson_preview"}}}) is not None
    assert AnalysisService.metrics_from_context({"historical_flood_exposure": .8,
        "provenance": {}}) is None
    grid_features = {item.name: item for item in _feature_availability(None, metrics, slug)}
    assert grid_features["Zone population"].status == "partial"
    assert grid_features["Mapped drainage proximity"].status == "partial"
    city_features = {item.name: item for item in _feature_availability(None, None, "pune",
        {"slope": 9, "drainage": 9, "population": 9})}
    assert city_features["Terrain slope"].status == "partial"
    assert city_features["Zone population"].status == "partial"
    assert city_features["Mapped drainage proximity"].status == "partial"
    assert "Select a Pune analysis cell" in city_features["Zone population"].limitation
    assert city_features["Historical flood exposure"].status == "unavailable"


def test_waterway_import_skips_existing_source_ids(tmp_path, monkeypatch):
    feature = {"type": "Feature", "properties": {"@id": "way/123", "waterway": "drain"},
               "geometry": {"type": "LineString", "coordinates": [[73.84, 18.52], [73.85, 18.53]]}}
    path = tmp_path / "DEMO_waterways.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": [feature]}), encoding="utf-8")
    batch = parse_file(path)
    seen = set()
    statements = []
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def execute(self, sql, params=None):
            statements.append(sql.lower())
            if "to_regclass" in sql:
                self.result = ("waterways",)
            elif "insert into public.waterways" in sql:
                key = (params[1], params[2]); self.result = None if key in seen else ("new",); seen.add(key)
            return self
        def fetchone(self): return self.result
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def cursor(self): return Cursor()
        def commit(self): pass
    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=lambda _: Connection()))
    indicators = zone_indicators(batch["records"])
    first = import_database(batch, indicators, "DEMO database URL")
    second = import_database(batch, indicators, "DEMO database URL")
    assert first["database_inserted_waterways"] == 1 and second["database_inserted_waterways"] == 0
    assert all("do nothing" in sql for sql in statements if "insert into public.waterways" in sql)
