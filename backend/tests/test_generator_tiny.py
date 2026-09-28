from backtrace_eval.generator.tiny import TinyWorldConfig, generate_tiny_world


def test_generate_tiny_world_is_deterministic_and_sized():
    config = TinyWorldConfig(
        seed=42,
        num_customers=100,
        num_events=3,
        num_complaints=100,
        regions=["north", "south", "east", "west"],
        plans=["fiber_basic", "fiber_pro", "business_ethernet", "tv_bundle"],
        channels=["phone", "email", "chat", "web"],
        event_sources=["network_alarm", "billing_run", "deploy", "policy_change"],
        window_days=14,
    )

    world_a = generate_tiny_world(config)
    world_b = generate_tiny_world(config)

    assert len(world_a.customers) == 100
    assert len(world_a.events) == 3
    assert len(world_a.complaints) == 100
    assert world_a.customers == world_b.customers  # same seed → same output
    assert all(c["customer_id"] in {cust["id"] for cust in world_a.customers} for c in world_a.complaints)
