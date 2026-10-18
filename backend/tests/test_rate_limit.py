from backtrace.llm.rate_limit import RateLimiter


class _FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def test_allows_up_to_max_calls_without_waiting():
    clock = _FakeClock()
    limiter = RateLimiter(max_calls=3, window_seconds=60.0, clock=clock, sleep=clock.sleep)

    for _ in range(3):
        limiter.acquire()

    assert clock.now == 0.0  # no waiting needed within the limit


def test_blocks_until_the_window_clears():
    clock = _FakeClock()
    limiter = RateLimiter(max_calls=2, window_seconds=60.0, clock=clock, sleep=clock.sleep)

    limiter.acquire()  # t=0
    clock.now = 10.0
    limiter.acquire()  # t=10, second slot used

    limiter.acquire()  # must wait until t=60 (first call's window clears)

    assert clock.now >= 60.0
