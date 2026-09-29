import hashlib
import json
from pathlib import Path

import yaml

from backtrace_eval.generator.dev import DevWorldConfig, generate_dev_world, write_dev_world


CONFIG_PATH = Path(__file__).resolve().parents[2] / "configs/worlds/dev.yaml"


def smoke_config() -> DevWorldConfig:
    raw = yaml.safe_load(CONFIG_PATH.read_text())
    raw.update(num_customers=120, num_complaints=100, window_days=4)
    return DevWorldConfig.from_dict(raw)


def test_dev_world_contract_and_separation():
    config = smoke_config()
    world = generate_dev_world(config)

    assert len(world.customers) == 120
    assert len(world.complaints) == 100
    assert len(world.gold_events) == 8
    assert len(world.network_nodes) == len(config.regions) * config.nodes_per_region
    assert len(world.telemetry) == config.window_days * 24 * 12 * (len(world.network_nodes) + len(world.network_links))
    assert sum(label["one_off"] for label in world.gold_complaint_labels) == 20
    assert sum(label["misattributed"] for label in world.gold_complaint_labels) == 15
    assert sum(label["multi_issue"] for label in world.gold_complaint_labels) == 8
    assert any(row["is_repeat"] for row in world.complaints)
    assert any(label["secondary_cause_id"] for label in world.gold_complaint_labels)
    assert any(row["id"] == "dev-trace-decoy" for row in world.events)
    assert any(row["alarm"] for row in world.telemetry)
    assert world.gold_events[0]["region"] == world.gold_events[1]["region"]
    assert world.gold_events[0]["start_at"] < world.gold_events[1]["end_at"]
    assert {c["kind"] for c in world.gold_events} >= {"fiber_cut", "billing_double_charge"}
    assert not any("root_cause_id" in row or "gold_remedy" in row for row in world.complaints)
    assert not any("vulnerability_flag" in row for row in world.customers)
    assert not any("cause_id" in row for row in world.events)
    assert not any("dev-cause-" in row["text"] for row in world.complaints)
    received_by_id = {row["complaint_id"]: row["received_at"] for row in world.complaints}
    assert all(all(received_by_id[prior] < row["received_at"] for prior in row["prior_complaint_ids"]) for row in world.complaints)


def test_dev_output_is_byte_stable_and_hashes_cover_split_files(tmp_path):
    config = smoke_config()
    first = generate_dev_world(config)
    second = generate_dev_world(config)
    first_dir, second_dir = tmp_path / "first", tmp_path / "second"
    first_manifest = write_dev_world(first, config, first_dir)
    second_manifest = write_dev_world(second, config, second_dir)

    assert first_manifest == second_manifest
    for name, expected_hash in first_manifest["output_sha256"].items():
        payload = (first_dir / name).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == expected_hash
        assert payload == (second_dir / name).read_bytes()
    assert json.loads((first_dir / "app/complaints.json").read_text()) == first.complaints
    assert not (first_dir / "app/gold_events.json").exists()
    assert first_manifest["generation_model"] == "fake-deterministic-v1"
    assert first_manifest["seed"] == config.seed
