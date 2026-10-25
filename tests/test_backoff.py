"""Unit tests for exponential backoff, jitter, and retry calculations."""

import pytest
from main import BackoffManager


def test_initial_backoff():
    manager = BackoffManager(
        initial_seconds=60,
        max_seconds=900,
        factor=2.0,
        jitter_max_seconds=10,
    )
    assert manager.failure_count == 0
    delay = manager.next_delay(apply_jitter=False)
    assert delay == 60


def test_exponential_growth():
    manager = BackoffManager(
        initial_seconds=60,
        max_seconds=900,
        factor=2.0,
        jitter_max_seconds=0,
    )
    # 1st failure: 60
    assert manager.next_delay(apply_jitter=False) == 60
    manager.record_failure()

    # 2nd failure: 120
    assert manager.next_delay(apply_jitter=False) == 120
    manager.record_failure()

    # 3rd failure: 240
    assert manager.next_delay(apply_jitter=False) == 240
    manager.record_failure()

    # 4th failure: 480
    assert manager.next_delay(apply_jitter=False) == 480
    manager.record_failure()

    # 5th failure: capped at max 900 (15 min)
    assert manager.next_delay(apply_jitter=False) == 900


def test_backoff_reset_on_success():
    manager = BackoffManager(initial_seconds=60, max_seconds=900)
    manager.record_failure()
    manager.record_failure()
    assert manager.failure_count == 2

    manager.record_success()
    assert manager.failure_count == 0
    assert manager.next_delay(apply_jitter=False) == 60


def test_backoff_jitter():
    manager = BackoffManager(
        initial_seconds=60,
        max_seconds=900,
        jitter_max_seconds=10,
    )
    delays = [manager.next_delay(apply_jitter=True) for _ in range(50)]
    for d in delays:
        assert 60 <= d <= 70
