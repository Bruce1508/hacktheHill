"""Deterministic synthetic dev world. The app/eval boundary is explicit here."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import random
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Mapping, Protocol


NETWORK_KINDS = frozenset({"fiber_cut", "optical_degradation", "maintenance_overrun", "dns_failure"})
SYMPTOMS = {
    "fiber_cut": "connection is completely down",
    "optical_degradation": "connection keeps dropping and videos buffer",
    "maintenance_overrun": "service did not return after the maintenance window",
    "dns_failure": "websites fail to load even though the router is online",
    "billing_double_charge": "the latest bill contains two charges for the same period",
    "unnotified_price_increase": "the monthly price rose without advance notice",
    "technician_no_show": "the technician missed the booked appointment",
    "cancellation_fee": "a cancellation fee appeared after the account was closed",
    "one_off": "an isolated account or service problem needs checking",
}
CLAIMS = ("the router", "the bill", "the local network", "the last service visit")


@dataclass(frozen=True)
class CauseConfig:
    kind: str
    region: str
    source: str


@dataclass(frozen=True)
class DevWorldConfig:
    profile: str
    seed: int
    start_date: str
    window_days: int
    num_customers: int
    num_complaints: int
    regions: tuple[str, ...]
    nodes_per_region: int
    telemetry_step_minutes: int
    one_off_fraction: float
    misattribution_fraction: float
    repeat_fraction: float
    multi_issue_fraction: float
    channels: tuple[str, ...]
    plans: Mapping[str, Mapping[str, object]]
    causes: tuple[CauseConfig, ...]

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> DevWorldConfig:
        config = cls(
            profile=str(raw["profile"]),
            seed=int(raw["seed"]),
            start_date=str(raw["start_date"]),
            window_days=int(raw["window_days"]),
            num_customers=int(raw["num_customers"]),
            num_complaints=int(raw["num_complaints"]),
            regions=tuple(raw["regions"]),
            nodes_per_region=int(raw["nodes_per_region"]),
            telemetry_step_minutes=int(raw["telemetry_step_minutes"]),
            one_off_fraction=float(raw["one_off_fraction"]),
            misattribution_fraction=float(raw["misattribution_fraction"]),
            repeat_fraction=float(raw["repeat_fraction"]),
            multi_issue_fraction=float(raw["multi_issue_fraction"]),
            channels=tuple(raw["channels"]),
            plans=raw["plans"],
            causes=tuple(CauseConfig(**item) for item in raw["causes"]),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if self.profile != "dev" or not 6 <= len(self.regions) <= 10:
            raise ValueError("dev profile requires 6–10 regions")
        if not 6 <= len(self.causes) <= 8 or not any(c.kind in NETWORK_KINDS for c in self.causes) or not any(c.kind not in NETWORK_KINDS for c in self.causes):
            raise ValueError("dev profile requires 6–8 mixed network and non-network causes")
        if len({c.kind for c in self.causes}) != len(self.causes):
            raise ValueError("cause kinds must be unique")
        if self.causes[0].region != self.causes[1].region:
            raise ValueError("the first two causes must share a region for the overlap case")
        if any(c.kind not in SYMPTOMS or c.region not in self.regions for c in self.causes):
            raise ValueError("unknown cause kind or region")
        if self.num_customers < 1 or self.num_complaints < 1 or self.nodes_per_region < 1 or self.window_days < 2:
            raise ValueError("world sizes must be positive")
        if self.telemetry_step_minutes not in (1, 2, 3, 4, 5):
            raise ValueError("telemetry step must be 1–5 minutes")
        for name in ("one_off_fraction", "misattribution_fraction", "repeat_fraction", "multi_issue_fraction"):
            if not 0 <= getattr(self, name) <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        if not self.plans or not self.channels:
            raise ValueError("plans and channels cannot be empty")
        dt.date.fromisoformat(self.start_date)


@dataclass(frozen=True)
class TextSeed:
    """Only observable complaint context may cross the text-provider boundary."""

    complaint_id: str
    product: str
    region: str
    channel: str
    persona: str
    symptom: str
    claimed_cause: str | None
    secondary_symptom: str | None
    is_repeat: bool
    vulnerability_mentioned: bool


class TextProvider(Protocol):
    model_id: str
    prompt_version: str

    def realize(self, seed: TextSeed) -> str: ...


@dataclass(frozen=True)
class FakeTextProvider:
    """Offline provider for CI and smoke data; real Gemini is a separate adapter."""

    model_id: str = "fake-deterministic-v1"
    prompt_version: str = "dev-text-v1"

    def realize(self, seed: TextSeed) -> str:
        variant = int(hashlib.sha256(seed.complaint_id.encode()).hexdigest()[:8], 16) % 4
        openings = (
            "Please look into this:",
            "I'm frustrated because",
            "Could someone check why",
            "This has been difficult to resolve:",
        )
        lead = openings[variant]
        text = f"{lead} my {seed.product} {seed.symptom} in {seed.region}."
        if seed.claimed_cause:
            text += f" I think it might be {seed.claimed_cause}."
        if seed.secondary_symptom:
            text += f" I also noticed {seed.secondary_symptom}."
        if seed.is_repeat:
            text += " I have already contacted support about this."
        if seed.vulnerability_mentioned:
            text += " I need priority help because of an accessibility need."
        if seed.persona == "terse":
            text += " Please fix it."
        elif seed.persona == "detailed":
            text += " Please explain the issue and any adjustment on my account."
        else:
            text += " This is really upsetting; I need an answer soon."
        return text


@dataclass
class DevWorld:
    customers: list[dict] = field(default_factory=list)
    network_nodes: list[dict] = field(default_factory=list)
    network_links: list[dict] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    telemetry: list[dict] = field(default_factory=list)
    complaints: list[dict] = field(default_factory=list)
    gold_events: list[dict] = field(default_factory=list)
    gold_complaint_labels: list[dict] = field(default_factory=list)


def _timestamp(value: dt.datetime) -> str:
    return value.isoformat()


def _affected_customers(cause: CauseConfig, customers: list[dict], nodes_per_region: int) -> list[str]:
    in_region = [c for c in customers if c["region"] == cause.region]
    if cause.kind == "fiber_cut":
        return [c["id"] for c in in_region if c["node_id"].endswith("-1")]
    if cause.kind == "optical_degradation":
        return [c["id"] for c in in_region]
    if cause.kind == "cancellation_fee":
        return [c["id"] for c in in_region if c["segment"] == "residential"]
    return [c["id"] for c in in_region]


def generate_dev_world(config: DevWorldConfig, text_provider: TextProvider | None = None) -> DevWorld:
    """Construct world and text in memory without database or network access."""
    config.validate()
    rng = random.Random(config.seed)
    provider = text_provider or FakeTextProvider()
    start = dt.datetime.combine(dt.date.fromisoformat(config.start_date), dt.time(), tzinfo=dt.timezone.utc)
    world = DevWorld()
    plan_names = tuple(config.plans)
    vulnerability_by_customer: dict[str, bool] = {}

    for region in config.regions:
        for index in range(1, config.nodes_per_region + 1):
            node_id = f"dev-node-{region}-{index}"
            world.network_nodes.append({"id": node_id, "region": region, "kind": "access_site"})
            next_index = index % config.nodes_per_region + 1
            world.network_links.append({"id": f"dev-link-{region}-{index}", "region": region, "from_node_id": node_id, "to_node_id": f"dev-node-{region}-{next_index}", "redundant": index == config.nodes_per_region})

    for index in range(config.num_customers):
        region = config.regions[index % len(config.regions)]
        plan = rng.choice(plan_names)
        attributes = config.plans[plan]
        customer_id = f"dev-cust-{index:05d}"
        vulnerability_by_customer[customer_id] = rng.random() < 0.08
        world.customers.append({
            "id": customer_id, "region": region, "plan": plan,
            "segment": attributes["segment"], "node_id": f"dev-node-{region}-{rng.randint(1, config.nodes_per_region)}",
            "tenure_months": rng.randint(1, 180),
        })
    customers_by_id = {c["id"]: c for c in world.customers}

    # The first two incidents deliberately overlap in the same region.
    causes = []
    last_start_day = max(1, config.window_days - 3)
    first_start_day = min(2, last_start_day)
    for index, spec in enumerate(config.causes):
        day = first_start_day if index < 2 else first_start_day + (index * (last_start_day - first_start_day)) // max(1, len(config.causes) - 1)
        hour = 8 if index == 0 else 9 if index == 1 else rng.randint(6, 18)
        begins = start + dt.timedelta(days=day, hours=hour)
        ends = begins + dt.timedelta(hours=4 if index < 2 else rng.randint(2, 8))
        affected = _affected_customers(spec, world.customers, config.nodes_per_region)
        cause_id = f"dev-cause-{index:02d}"
        gold = {
            "id": cause_id, "kind": spec.kind, "start_at": _timestamp(begins), "end_at": _timestamp(ends),
            "region": spec.region, "affected_customer_ids": affected,
            "severity": rng.choice(["medium", "high"]), "complaint_probability": 0.15,
        }
        world.gold_events.append(gold)
        causes.append((spec, gold, set(affected)))
        # Missing evidence is deliberate; observable IDs carry no answer-key relationship.
        if index not in (3, 6):
            world.events.append({
                "id": f"dev-trace-{index:02d}", "source": spec.source,
                "start_at": _timestamp(begins + dt.timedelta(minutes=rng.randint(0, 25))),
                "end_at": _timestamp(ends), "scope": {"region": spec.region},
                "search_text": f"{spec.source.replace('_', ' ')} record in {spec.region}",
            })
    decoy_region = config.regions[-1]
    world.events.append({
        "id": "dev-trace-decoy", "source": "network_alarm", "start_at": _timestamp(start + dt.timedelta(days=5)),
        "end_at": _timestamp(start + dt.timedelta(days=5, hours=1)),
        "scope": {"region": decoy_region}, "search_text": f"redundant path alarm in {decoy_region}",
    })

    # Regular 1–5 minute samples at every node and link, with incident anomalies.
    steps = config.window_days * 24 * 60 // config.telemetry_step_minutes
    for step in range(steps):
        when = start + dt.timedelta(minutes=step * config.telemetry_step_minutes)
        iso_when = _timestamp(when)
        for node in world.network_nodes:
            active = [spec.kind for spec, gold, _ in causes if spec.kind in NETWORK_KINDS and gold["region"] == node["region"] and gold["start_at"] <= iso_when <= gold["end_at"]]
            severe = any(kind in ("fiber_cut", "maintenance_overrun") for kind in active)
            weak = "dns_failure" in active
            world.telemetry.append({
                "node_id": node["id"], "link_id": None, "sampled_at": iso_when,
                "optical_power_dbm": -28.0 if severe else -20.0,
                "errored_seconds": 30 if severe else 2 if active and not weak else 0,
                "packet_loss_pct": 95.0 if severe else 8.0 if active and not weak else 0.1,
                "latency_ms": 220.0 if severe else 55.0 if active else 12.0,
                "alarm": severe,
            })
        for link in world.network_links:
            decoy = link["redundant"] and link["region"] == decoy_region and start + dt.timedelta(days=5) <= when < start + dt.timedelta(days=5, hours=1)
            world.telemetry.append({
                "node_id": None, "link_id": link["id"], "sampled_at": iso_when,
                "optical_power_dbm": -30.0 if decoy else -20.0,
                "errored_seconds": 20 if decoy else 0, "packet_loss_pct": 25.0 if decoy else 0.1,
                "latency_ms": 50.0 if decoy else 12.0, "alarm": decoy,
            })

    one_off_count = round(config.num_complaints * config.one_off_fraction)
    misattributed_count = round(config.num_complaints * config.misattribution_fraction)
    repeat_count = round(config.num_complaints * config.repeat_fraction)
    multi_count = round(config.num_complaints * config.multi_issue_fraction)
    complaint_kinds = [None] * one_off_count + [index % len(causes) for index in range(config.num_complaints - one_off_count)]
    rng.shuffle(complaint_kinds)
    if multi_count >= 2:
        for target, cause_index in enumerate((0, 1)):
            source = next(i for i in range(target, len(complaint_kinds)) if complaint_kinds[i] == cause_index)
            complaint_kinds[target], complaint_kinds[source] = complaint_kinds[source], complaint_kinds[target]
    previous_by_customer: dict[str, list[str]] = {}
    previous_by_cause: dict[int, list[str]] = {}
    last_received_by_customer: dict[str, dt.datetime] = {}
    used_customer_ids: set[str] = set()
    repeat_remaining = repeat_count
    misattribution_remaining = misattributed_count
    for index, cause_index in enumerate(complaint_kinds):
        if cause_index is None:
            fresh = [c for c in world.customers if c["id"] not in used_customer_ids]
            customer = rng.choice(fresh or world.customers)
            received = start + dt.timedelta(minutes=rng.randrange(config.window_days * 24 * 60))
            kind = "one_off"
            root_cause_id = None
        else:
            spec, gold, affected = causes[cause_index]
            eligible = sorted(affected)
            if index < multi_count and cause_index in (0, 1):
                overlap = affected & causes[1 - cause_index][2]
                eligible = sorted(overlap) if overlap else eligible
            if repeat_remaining and previous_by_cause.get(cause_index):
                customer = customers_by_id[rng.choice(previous_by_cause[cause_index])]
                repeat_remaining -= 1
            else:
                fresh = [customer_id for customer_id in eligible if customer_id not in used_customer_ids]
                customer = customers_by_id[rng.choice(fresh or eligible)]
            received = dt.datetime.fromisoformat(gold["start_at"]) + dt.timedelta(hours=rng.randint(0, 48), minutes=rng.randint(0, 59))
            kind = spec.kind
            root_cause_id = gold["id"]
        prior = previous_by_customer.get(customer["id"], [])
        is_repeat = bool(prior)
        if is_repeat:
            received = max(received, last_received_by_customer[customer["id"]] + dt.timedelta(hours=1))
        claimed_cause = rng.choice(CLAIMS) if root_cause_id and misattribution_remaining else None
        if claimed_cause:
            misattribution_remaining -= 1
        secondary_cause_id = None
        secondary_symptom = None
        is_multi_issue = index < multi_count
        if is_multi_issue and cause_index in (0, 1):
            other_index = 1 - cause_index
            secondary_cause_id = causes[other_index][1]["id"]
            secondary_symptom = SYMPTOMS[causes[other_index][0].kind]
        elif is_multi_issue:
            secondary_symptom = "the bill also looks confusing"
        complaint_id = f"dev-complaint-{index:05d}"
        channel = rng.choice(config.channels)
        mentioned = vulnerability_by_customer[customer["id"]] and rng.random() < 0.4
        text_seed = TextSeed(
            complaint_id=complaint_id, product=customer["plan"], region=customer["region"],
            channel=channel, persona=rng.choice(("terse", "detailed", "emotional")),
            symptom=SYMPTOMS[kind], claimed_cause=claimed_cause,
            secondary_symptom=secondary_symptom, is_repeat=is_repeat,
            vulnerability_mentioned=mentioned,
        )
        world.complaints.append({
            "complaint_id": complaint_id, "customer_id": customer["id"], "received_at": _timestamp(received),
            "channel": channel, "text": provider.realize(text_seed), "product": customer["plan"],
            "region": customer["region"], "node_id": customer["node_id"],
            "is_repeat": is_repeat, "prior_complaint_ids": prior[-3:],
            "escalation_status": "open", "escalated_at": None,
            "sla_deadline": _timestamp(received + dt.timedelta(days=5)),
        })
        price = Decimal(str(config.plans[customer["plan"]]["daily_price"]))
        if cause_index is not None and kind in NETWORK_KINDS:
            gold_event = causes[cause_index][1]
            duration_hours = (dt.datetime.fromisoformat(gold_event["end_at"]) - dt.datetime.fromisoformat(gold_event["start_at"])).total_seconds() / 3600
            financial_impact = price * Decimal(str(duration_hours)) / Decimal("24")
        elif kind == "billing_double_charge":
            financial_impact = price * 30
        elif kind == "unnotified_price_increase":
            financial_impact = price * Decimal("3")
        elif kind == "cancellation_fee":
            financial_impact = Decimal("75")
        else:
            financial_impact = Decimal("0")
        gold_remedy = "refund duplicate charge" if kind == "billing_double_charge" else "review fee" if kind == "cancellation_fee" else "service credit" if kind in NETWORK_KINDS else "investigate and correct"
        world.gold_complaint_labels.append({
            "complaint_id": complaint_id, "root_cause_id": root_cause_id,
            "secondary_cause_id": secondary_cause_id, "true_cause": kind,
            "customer_claimed_cause": claimed_cause, "misattributed": claimed_cause is not None,
            "one_off": cause_index is None, "multi_issue": is_multi_issue,
            "financial_impact": str(financial_impact.quantize(Decimal("0.01"))),
            "customer_impact_severity": "high" if kind in NETWORK_KINDS else "medium",
            "vulnerability_flag": vulnerability_by_customer[customer["id"]], "vulnerability_mentioned": mentioned,
            "gold_remedy": gold_remedy, "injected_defect": None,
        })
        previous_by_customer.setdefault(customer["id"], []).append(complaint_id)
        last_received_by_customer[customer["id"]] = received
        used_customer_ids.add(customer["id"])
        if cause_index is not None:
            previous_by_cause.setdefault(cause_index, []).append(customer["id"])
    return world


def _json_bytes(data: object) -> bytes:
    return (json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def write_dev_world(world: DevWorld, config: DevWorldConfig, out_dir: Path, text_provider: TextProvider | None = None) -> dict:
    """Write app observables and eval answers to disjoint paths with hashes."""
    provider = text_provider or FakeTextProvider()
    files = {
        "app/customers.json": world.customers,
        "app/network_nodes.json": world.network_nodes,
        "app/network_links.json": world.network_links,
        "app/events.json": world.events,
        "app/telemetry.json": world.telemetry,
        "app/complaints.json": world.complaints,
        "eval/gold_events.json": world.gold_events,
        "eval/gold_complaint_labels.json": world.gold_complaint_labels,
    }
    hashes = {}
    for relative_path, rows in files.items():
        path = out_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = _json_bytes(rows)
        path.write_bytes(payload)
        hashes[relative_path] = hashlib.sha256(payload).hexdigest()
    config_hash = hashlib.sha256(_json_bytes(asdict(config))).hexdigest()
    manifest = {
        "profile": config.profile, "seed": config.seed, "config_sha256": config_hash,
        "generation_model": provider.model_id, "prompt_version": provider.prompt_version,
        "counts": {name: len(getattr(world, name)) for name in world.__dataclass_fields__},
        "output_sha256": hashes,
    }
    (out_dir / "manifest.json").write_bytes(_json_bytes(manifest))
    return manifest
