from scripts.soak import pg_observer as ob


def test_parse_csv_handles_quoted_query_text():
    # psql --csv quotes fields with commas/newlines; the query column often has both.
    raw = '"SELECT a,\n b",10,1.5\n"UPDATE t SET x = 1, y = 2",4,2.0\n'
    rows = ob.parse_psql_csv(raw, ["query", "calls", "mean_ms"])
    assert rows[0]["query"] == "SELECT a,\n b"
    assert rows[1]["query"] == "UPDATE t SET x = 1, y = 2"
    assert rows[1]["calls"] == "4"


def test_activity_metrics():
    rows = [
        {"state": "active", "wait_event_type": "", "query_age": "2.0", "state_age": "2.0"},
        {"state": "active", "wait_event_type": "Lock", "query_age": "9.0", "state_age": "9.0"},
        {"state": "idle", "wait_event_type": "", "query_age": "", "state_age": "30.0"},
        {"state": "idle in transaction", "wait_event_type": "", "query_age": "", "state_age": "45.0"},  # noqa: E501
    ]
    m = ob.activity_metrics(rows)
    assert m["total"] == 4
    assert m["active"] == 2
    assert m["idle"] == 1
    assert m["idle_in_transaction"] == 1
    assert m["waiting"] == 1
    assert m["longest_query_age_s"] == 9.0
    assert m["longest_idle_in_txn_s"] == 45.0


def test_database_window_interval_ratio_and_run_deltas():
    # pg_stat_database counters are cumulative; the window must (a) compute cache hit
    # ratio over the interval since prev, and (b) report deadlocks/temp_bytes as deltas
    # since run start so pre-soak history doesn't count.
    start = {"numbackends": "5", "xact_commit": "1000", "xact_rollback": "0",
             "blks_read": "100", "blks_hit": "9900", "deadlocks": "3",
             "temp_files": "0", "temp_bytes": "2048"}
    prev = {"numbackends": "6", "xact_commit": "1500", "xact_rollback": "0",
            "blks_read": "110", "blks_hit": "9990", "deadlocks": "3",
            "temp_files": "0", "temp_bytes": "2048"}
    cur = {"numbackends": "7", "xact_commit": "2000", "xact_rollback": "0",
           "blks_read": "120", "blks_hit": "10080", "deadlocks": "4",
           "temp_files": "0", "temp_bytes": "6144"}
    m = ob.database_window(prev, cur, start)
    assert m["cache_hit_ratio"] == 0.9        # interval: d_hit=90, d_read=10 → 90/100
    assert m["deadlocks_run"] == 1            # 4 now vs 3 at start → one during the soak
    assert m["temp_bytes_run"] == 4096        # 6144 - 2048
    assert m["numbackends"] == 7              # gauge, current value


def test_database_window_zero_interval_is_safe():
    row = {"numbackends": "1", "xact_commit": "0", "xact_rollback": "0",
           "blks_read": "0", "blks_hit": "0", "deadlocks": "0",
           "temp_files": "0", "temp_bytes": "0"}
    assert ob.database_window(row, row, row)["cache_hit_ratio"] is None


def test_lock_metrics():
    rows = [
        {"mode": "AccessShareLock", "granted": "t"},
        {"mode": "AccessShareLock", "granted": "t"},
        {"mode": "ExclusiveLock", "granted": "f"},
    ]
    m = ob.lock_metrics(rows)
    assert m["total"] == 3
    assert m["not_granted"] == 1
    assert m["by_mode"]["AccessShareLock"] == 2


def test_statements_diff_flags_growth():
    start = [{"queryid": "1", "calls": "10", "mean_exec_time": "5.0", "max_exec_time": "8.0"}]
    end = [{"queryid": "1", "calls": "110", "mean_exec_time": "20.0", "max_exec_time": "40.0",
            "query": "SELECT ..."}]
    diff = ob.statements_diff(start, end)
    assert diff[0]["mean_ms_start"] == 5.0
    assert diff[0]["mean_ms_end"] == 20.0
    assert diff[0]["mean_ratio"] == 4.0
