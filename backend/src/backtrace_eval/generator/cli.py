import argparse
import json
from pathlib import Path

import yaml

from backtrace_eval.generator.tiny import TinyWorldConfig, generate_tiny_world


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["generate"])
    parser.add_argument("--world-config", default="../configs/worlds/tiny.yaml")
    parser.add_argument("--out", default="../fixtures/tiny")
    args = parser.parse_args()

    with open(args.world_config) as f:
        raw = yaml.safe_load(f)
    config = TinyWorldConfig(**raw)
    world = generate_tiny_world(config)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "customers.json").write_text(json.dumps(world.customers, indent=2))
    (out_dir / "events.json").write_text(json.dumps(world.events, indent=2))
    (out_dir / "complaints.json").write_text(json.dumps(world.complaints, indent=2))
    print(f"Wrote {len(world.customers)} customers, {len(world.events)} events, {len(world.complaints)} complaints to {out_dir}")


if __name__ == "__main__":
    main()
