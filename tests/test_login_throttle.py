import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from login_throttle import LoginThrottle


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def make_throttle(**overrides):
    clock = FakeClock()
    options = {"free_attempts": 3, "base_delay": 10, "max_delay": 60, "window": 100, "max_entries": 4, "clock": clock}
    options.update(overrides)
    return LoginThrottle(**options), clock


def test_free_attempts_do_not_lock():
    throttle, _ = make_throttle()
    key = ("203.0.113.5", "tester")
    for _ in range(3):
        assert throttle.record_failure(key) == 0
        assert throttle.retry_after(key) == 0


def test_lock_grows_exponentially_and_is_capped():
    throttle, clock = make_throttle()
    key = ("203.0.113.5", "tester")
    for _ in range(3):
        throttle.record_failure(key)
    assert throttle.record_failure(key) == 10
    assert throttle.retry_after(key) == 10
    clock.advance(10)
    assert throttle.retry_after(key) == 0
    assert throttle.record_failure(key) == 20
    clock.advance(20)
    assert throttle.record_failure(key) == 40
    clock.advance(40)
    assert throttle.record_failure(key) == 60
    clock.advance(60)
    assert throttle.record_failure(key) == 60


def test_retry_after_rounds_partial_seconds_up():
    throttle, clock = make_throttle()
    key = ("203.0.113.5", "tester")
    for _ in range(4):
        throttle.record_failure(key)
    clock.advance(0.5)
    assert throttle.retry_after(key) == 10


def test_success_clears_the_key_and_keys_are_independent():
    throttle, _ = make_throttle()
    locked = ("203.0.113.5", "tester")
    other = ("198.51.100.9", "tester")
    for _ in range(4):
        throttle.record_failure(locked)
    assert throttle.retry_after(locked) > 0
    assert throttle.retry_after(other) == 0
    throttle.record_success(locked)
    assert throttle.retry_after(locked) == 0
    assert throttle.record_failure(locked) == 0


def test_inactivity_window_forgets_failures():
    throttle, clock = make_throttle()
    key = ("203.0.113.5", "tester")
    for _ in range(4):
        throttle.record_failure(key)
    clock.advance(101)
    assert throttle.retry_after(key) == 0
    assert throttle.record_failure(key) == 0


def test_entry_count_is_bounded():
    throttle, clock = make_throttle()
    for index in range(10):
        throttle.record_failure((f"203.0.113.{index}", "tester"))
        clock.advance(1)
    assert len(throttle._entries) <= 4
    assert throttle.retry_after(("203.0.113.0", "tester")) == 0
