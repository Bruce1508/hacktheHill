import datetime as dt
import random
from dataclasses import dataclass, field


@dataclass
class TinyWorldConfig:
    seed: int
    num_customers: int
    num_events: int
    num_complaints: int
    regions: list[str]
    plans: list[str]
    channels: list[str]
    event_sources: list[str]
    window_days: int


@dataclass
class TinyWorld:
    customers: list[dict] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    complaints: list[dict] = field(default_factory=list)


_SEGMENT_BY_PLAN = {
    "fiber_basic": "residential",
    "fiber_pro": "residential",
    "tv_bundle": "residential",
    "business_ethernet": "business",
}

_TEXT_TEMPLATES = [
    "My {product} has been having issues since {day}.",
    "I'm writing about a problem with my {product} account.",
    "This is my second time reporting a {product} issue.",
    "Something is wrong with my {product} service in {region}.",
]


def generate_tiny_world(config: TinyWorldConfig) -> TinyWorld:
    rng = random.Random(config.seed)
    world_start = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)

    customers = []
    for i in range(config.num_customers):
        region = rng.choice(config.regions)
        plan = rng.choice(config.plans)
        customers.append(
            {
                "id": f"cust_{i:04d}",
                "region": region,
                "plan": plan,
                "segment": _SEGMENT_BY_PLAN[plan],
                "node_id": f"node-{region}-{rng.randint(1, 5)}",
            }
        )

    events = []
    for i in range(config.num_events):
        start_offset = rng.randint(0, config.window_days - 1)
        start_at = world_start + dt.timedelta(days=start_offset, hours=rng.randint(0, 23))
        end_at = start_at + dt.timedelta(hours=rng.randint(1, 12))
        region = rng.choice(config.regions)
        source = rng.choice(config.event_sources)
        events.append(
            {
                "id": f"event_{i:03d}",
                "source": source,
                "start_at": start_at.isoformat(),
                "end_at": end_at.isoformat(),
                "scope": {"region": region},
                "search_text": f"{source} affecting {region}",
            }
        )

    complaints = []
    for i in range(config.num_complaints):
        customer = rng.choice(customers)
        day_offset = rng.randint(0, config.window_days - 1)
        received_at = world_start + dt.timedelta(days=day_offset, hours=rng.randint(0, 23), minutes=rng.randint(0, 59))
        template = rng.choice(_TEXT_TEMPLATES)
        complaints.append(
            {
                "complaint_id": f"complaint_{i:04d}",
                "customer_id": customer["id"],
                "received_at": received_at.isoformat(),
                "channel": rng.choice(config.channels),
                "text": template.format(product=customer["plan"], region=customer["region"], day=received_at.date()),
                "product": customer["plan"],
                "region": customer["region"],
                "node_id": customer["node_id"],
            }
        )

    return TinyWorld(customers=customers, events=events, complaints=complaints)
