"""Unit and integration tests for Daily Follower Tracker."""

import pytest
from datetime import datetime, time
from config import FollowerTrackerConfig, load_config
from storage import StorageEngine
from follower_tracker import (
    FollowerUser,
    FollowerDiff,
    FollowerTrackerEngine,
    format_follower_digest,
    calculate_prep_start_time,
)


@pytest.fixture
def temp_storage(tmp_path):
    db_file = tmp_path / "test_follower.db"
    storage = StorageEngine(str(db_file))
    return storage


def test_follower_tracker_config_loading(tmp_path):
    config_file = tmp_path / "config.yaml"
    env_file = tmp_path / ".env"

    config_content = """
follower_tracker:
  enabled: true
  target_handle: "vaaisshnav"
  schedule_time: "09:00"
  prep_lead_minutes: 40
  min_request_delay_seconds: 10
  max_request_delay_seconds: 20
  send_telegram_digest: true
"""
    config_file.write_text(config_content, encoding="utf-8")
    env_file.write_text("", encoding="utf-8")

    cfg = load_config(config_path=str(config_file), env_file=str(env_file))
    assert cfg.follower_tracker.enabled is True
    assert cfg.follower_tracker.target_handle == "vaaisshnav"
    assert cfg.follower_tracker.schedule_time == "09:00"
    assert cfg.follower_tracker.prep_lead_minutes == 40
    assert cfg.follower_tracker.min_request_delay_seconds == 10
    assert cfg.follower_tracker.max_request_delay_seconds == 20
    assert cfg.follower_tracker.send_telegram_digest is True


def test_calculate_prep_start_time():
    # Schedule time 09:00 with 40 mins lead -> 08:20
    schedule_t = time(9, 0)
    prep_t = calculate_prep_start_time(schedule_t, lead_minutes=40)
    assert prep_t == time(8, 20)

    # Edge case across midnight: 00:20 with 30 mins lead -> 23:50
    schedule_mid = time(0, 20)
    prep_mid = calculate_prep_start_time(schedule_mid, lead_minutes=30)
    assert prep_mid == time(23, 50)


def test_follower_diff_calculation():
    # Previous day state
    prev_followers = {
        101: FollowerUser(id=101, screen_name="alice", name="Alice"),
        102: FollowerUser(id=102, screen_name="bob", name="Bob"),
        103: FollowerUser(id=103, screen_name="carol", name="Carol"),
    }
    prev_following = {
        102: FollowerUser(id=102, screen_name="bob", name="Bob"),
        104: FollowerUser(id=104, screen_name="dave", name="Dave"),
    }

    # Current day state
    # Changes:
    # - carol unfollowed (in prev_followers, not in curr_followers)
    # - eve followed (not in prev_followers, now in curr_followers)
    # - you followed frank (now in curr_following)
    curr_followers = {
        101: FollowerUser(id=101, screen_name="alice", name="Alice"),
        102: FollowerUser(id=102, screen_name="bob", name="Bob"),
        105: FollowerUser(id=105, screen_name="eve", name="Eve"),
    }
    curr_following = {
        102: FollowerUser(id=102, screen_name="bob", name="Bob"),
        104: FollowerUser(id=104, screen_name="dave", name="Dave"),
        106: FollowerUser(id=106, screen_name="frank", name="Frank"),
    }

    diff = FollowerTrackerEngine.compute_diff(
        prev_followers=prev_followers,
        prev_following=prev_following,
        curr_followers=curr_followers,
        curr_following=curr_following,
    )

    # New followers: Eve
    assert len(diff.new_followers) == 1
    assert diff.new_followers[0].screen_name == "eve"

    # Unfollowers: Carol
    assert len(diff.unfollowers) == 1
    assert diff.unfollowers[0].screen_name == "carol"

    # Mutual follows: Bob (102) is in both curr_followers and curr_following
    assert len(diff.mutuals) == 1
    assert diff.mutuals[0].screen_name == "bob"

    # Not following back: Dave (104) and Frank (106)
    not_back_handles = [u.screen_name for u in diff.not_following_back]
    assert "dave" in not_back_handles
    assert "frank" in not_back_handles
    assert "bob" not in not_back_handles

    # Net change: 3 - 3 = 0
    assert diff.net_follower_change == 0


def test_first_run_baseline_handling():
    curr_followers = {
        101: FollowerUser(id=101, screen_name="alice", name="Alice"),
        102: FollowerUser(id=102, screen_name="bob", name="Bob"),
    }
    curr_following = {
        102: FollowerUser(id=102, screen_name="bob", name="Bob"),
        103: FollowerUser(id=103, screen_name="charlie", name="Charlie"),
    }

    # On first run, prev_followers and prev_following are empty dicts
    diff = FollowerTrackerEngine.compute_diff(
        prev_followers={},
        prev_following={},
        curr_followers=curr_followers,
        curr_following=curr_following,
        is_first_run=True,
    )

    assert diff.is_baseline is True
    assert len(diff.new_followers) == 0
    assert len(diff.unfollowers) == 0
    assert len(diff.mutuals) == 1  # Bob
    assert len(diff.not_following_back) == 1  # Charlie


def test_storage_save_and_retrieve_snapshots(temp_storage):
    target = "vaaisshnav"

    followers_1 = [
        FollowerUser(id=1, screen_name="user1", name="User One"),
        FollowerUser(id=2, screen_name="user2", name="User Two"),
    ]
    following_1 = [
        FollowerUser(id=2, screen_name="user2", name="User Two"),
        FollowerUser(id=3, screen_name="user3", name="User Three"),
    ]

    snap_id_1 = temp_storage.save_follower_snapshot(
        target_handle=target,
        followers=followers_1,
        following=following_1,
        recorded_at=datetime(2026, 10, 24, 9, 0),
    )
    assert snap_id_1 > 0

    # Retrieve latest snapshot
    latest = temp_storage.get_latest_follower_snapshot(target)
    assert latest is not None
    assert latest["total_followers"] == 2
    assert latest["total_following"] == 2

    # Save next day snapshot
    followers_2 = [
        FollowerUser(id=1, screen_name="user1", name="User One"),
        FollowerUser(id=4, screen_name="user4", name="User Four"),  # new follower
    ]
    following_2 = following_1

    snap_id_2 = temp_storage.save_follower_snapshot(
        target_handle=target,
        followers=followers_2,
        following=following_2,
        recorded_at=datetime(2026, 10, 25, 9, 0),
    )

    # Now get the two most recent snapshots
    snaps = temp_storage.get_recent_follower_snapshots(target, limit=2)
    assert len(snaps) == 2
    assert snaps[0]["id"] == snap_id_2
    assert snaps[1]["id"] == snap_id_1

    # Check non-reciprocal following query
    not_back = temp_storage.get_not_following_back(target)
    not_back_handles = [u["screen_name"] for u in not_back]
    assert "user3" in not_back_handles


def test_format_follower_digest():
    diff = FollowerDiff(
        target_handle="vaaisshnav",
        total_followers=325,
        total_following=661,
        net_follower_change=2,
        new_followers=[
            FollowerUser(id=1, screen_name="alex_dev", name="Alex Dev"),
            FollowerUser(id=2, screen_name="sarah_tech", name="Sarah Tech"),
        ],
        unfollowers=[
            FollowerUser(id=3, screen_name="quitter", name="Quitter Guy"),
        ],
        mutuals=[
            FollowerUser(id=2, screen_name="sarah_tech", name="Sarah Tech"),
        ],
        not_following_back=[
            FollowerUser(id=3, screen_name="quitter", name="Quitter Guy"),
            FollowerUser(id=4, screen_name="vip", name="VIP Account"),
        ],
        is_baseline=False,
    )

    message = format_follower_digest(diff)

    assert "Daily Follower Report" in message
    assert "@vaaisshnav" in message
    assert "Total Followers: <b>325</b> (+2)" in message
    assert "Total Following: <b>661</b>" in message
    assert "@alex_dev" in message
    assert "@quitter" in message
    assert "https://x.com/quitter" in message
    assert len(message) < 4096
