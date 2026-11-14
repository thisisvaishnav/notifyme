from github_issue_monitor.storage import IssueStorage


def test_schema_version_and_wal_mode(tmp_path):
    db_file = str(tmp_path / "test_issues.db")
    storage = IssueStorage(db_file)

    # Check schema_version table exists
    with storage._connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT version FROM schema_version")
        version = cursor.fetchone()[0]
        assert version >= 1

        cursor.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0].lower()
        assert mode == "wal"

    storage.close()


def test_is_seen_and_mark_seen(tmp_path):
    db_file = str(tmp_path / "test_issues.db")
    storage = IssueStorage(db_file)

    repo = "open-telemetry/opentelemetry-collector-contrib"
    assert not storage.is_seen(repo, 100)

    storage.mark_seen(repo, 100, "Fix memory leak")
    assert storage.is_seen(repo, 100)
    assert not storage.is_seen(repo, 101)
    assert not storage.is_seen("other/repo", 100)

    # Close and reopen to verify persistence
    storage.close()

    reopened_storage = IssueStorage(db_file)
    assert reopened_storage.is_seen(repo, 100)
    reopened_storage.close()


def test_etag_tracking(tmp_path):
    db_file = str(tmp_path / "test_issues.db")
    storage = IssueStorage(db_file)

    repo = "open-telemetry/opentelemetry-collector-contrib"
    assert storage.get_etag(repo) is None

    storage.save_etag(repo, 'W/"abcdef123456"')
    assert storage.get_etag(repo) == 'W/"abcdef123456"'

    # Update etag
    storage.save_etag(repo, 'W/"newetag987654"')
    assert storage.get_etag(repo) == 'W/"newetag987654"'

    # Persistence check
    storage.close()
    reopened = IssueStorage(db_file)
    assert reopened.get_etag(repo) == 'W/"newetag987654"'
    reopened.close()


def test_is_baselined_and_set_baselined(tmp_path):
    db_file = str(tmp_path / "test_issues.db")
    storage = IssueStorage(db_file)

    repo = "open-telemetry/opentelemetry-collector-contrib"
    assert not storage.is_baselined(repo)

    storage.set_baselined(repo)
    assert storage.is_baselined(repo)

    # Persistence check
    storage.close()
    reopened = IssueStorage(db_file)
    assert reopened.is_baselined(repo)
    assert not reopened.is_baselined("another/repo")
    reopened.close()
