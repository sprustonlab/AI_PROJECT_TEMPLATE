import marimo

__generated_with = "0.19.6"
app = marimo.App(width="full")


@app.cell
def _():
    import marimo as mo
    import altair as alt
    import httpx
    import os
    from datetime import datetime

    # Color palette: teal/blue with good contrast
    COLORS = {
        "palette": [
            "#0d9488",
            "#0891b2",
            "#6366f1",
            "#8b5cf6",
            "#ec4899",
            "#f97316",
            "#eab308",
            "#22c55e",
        ],
        "diverging": [
            "#ef4444",
            "#f97316",
            "#22c55e",
            "#0d9488",
        ],  # red -> orange -> green -> teal
    }

    # Get local timezone offset
    local_tz = datetime.now().astimezone().tzinfo

    def to_local(utc_str: str) -> str:
        """Convert UTC timestamp string to local time string."""
        if not utc_str:
            return utc_str
        try:
            clean = utc_str.replace(" ", "T")
            if "+" not in clean and "Z" not in clean:
                clean += "+00:00"
            clean = clean.replace("Z", "+00:00")
            dt = datetime.fromisoformat(clean)
            local_dt = dt.astimezone(local_tz)
            return local_dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return utc_str

    return COLORS, alt, datetime, httpx, local_tz, mo, os, to_local


@app.cell
def _(datetime, httpx, os):
    API_KEY = os.environ.get("POSTHOG_API_KEY")
    if not API_KEY:
        raise ValueError("Set POSTHOG_API_KEY environment variable")

    SINCE = "2026-01-23"

    # Full date range from SINCE to today, so all charts share the same x-axis
    from datetime import timedelta  # marimo cells are isolated; import here

    _start = datetime.strptime(SINCE, "%Y-%m-%d").date()
    _today = datetime.now().date()
    ALL_DATES = [
        (_start + timedelta(days=i)).isoformat()
        for i in range((_today - _start).days + 1)
    ]

    def hogql(query: str) -> list[dict]:
        # PostHog HogQL defaults to 100 rows — always raise the limit
        if "LIMIT" not in query.upper():
            query = query.rstrip().rstrip(";") + " LIMIT 10000"
        r = httpx.post(
            "https://us.i.posthog.com/api/projects/@current/query/",
            headers={"Authorization": f"Bearer {API_KEY}"},
            json={"query": {"kind": "HogQLQuery", "query": query}},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        columns = data["columns"]
        return [dict(zip(columns, row)) for row in data["results"]]

    return ALL_DATES, SINCE, hogql


@app.cell
def _(mo):
    mo.md("# Claudechic Analytics Dashboard")
    return


# --- Chart builders (return chart objects) ---


@app.cell
def _(ALL_DATES, COLORS, SINCE, alt, hogql):
    installs_raw = hogql(f"""
        SELECT toString(toDate(timestamp)) as install_date, distinct_id as user_id
        FROM events WHERE event = 'app_installed'
            AND timestamp >= '{SINCE}'
    """)
    # Lifetime message counts (no date filter) — we want total engagement per user
    message_counts = hogql("""
        SELECT distinct_id as user_id, count() as message_count
        FROM events WHERE event = 'message_sent' GROUP BY distinct_id
    """)
    msg_lookup = {r["user_id"]: r["message_count"] for r in message_counts}
    installs_data = [
        {
            "install_date": r["install_date"],
            "user_id": r["user_id"],
            "message_count": msg_lookup.get(r["user_id"], 0),
        }
        for r in installs_raw
    ]

    def _engagement_bin(count):
        if count == 0:
            return "Zero"
        elif count <= 10:
            return "Low (1-10)"
        elif count <= 100:
            return "Medium (11-100)"
        else:
            return "High (100+)"

    for _r in installs_data:
        _r["engagement"] = _engagement_bin(_r["message_count"])

    installs_chart = (
        alt.Chart(alt.Data(values=installs_data))
        .mark_bar()
        .encode(
            x=alt.X(
                "install_date:O",
                title="Install Date",
                scale=alt.Scale(domain=ALL_DATES),
            ),
            y=alt.Y("count():Q", title="New Installs"),
            color=alt.Color(
                "engagement:N",
                title="Engagement",
                sort=["Zero", "Low (1-10)", "Medium (11-100)", "High (100+)"],
                scale=alt.Scale(
                    domain=["Zero", "Low (1-10)", "Medium (11-100)", "High (100+)"],
                    range=COLORS["diverging"],
                ),
            ),
            order=alt.Order("engagement:N", sort="descending"),
        )
        .properties(width=450, height=250, title="New Installs by Engagement")
    )
    return (installs_chart,)


@app.cell
def _(ALL_DATES, COLORS, SINCE, alt, hogql):
    versions_data = hogql(f"""
        SELECT toString(toDate(timestamp)) as day, properties.claudechic_version as version,
               count(DISTINCT distinct_id) as users
        FROM events WHERE event = 'app_started' AND properties.claudechic_version IS NOT NULL
            AND timestamp >= '{SINCE}'
        GROUP BY day, version ORDER BY day, users DESC
    """)
    versions_sorted = sorted(set(r["version"] for r in versions_data), reverse=True)
    versions_chart = (
        alt.Chart(alt.Data(values=versions_data))
        .mark_bar()
        .encode(
            x=alt.X("day:O", title="Date", scale=alt.Scale(domain=ALL_DATES)),
            y=alt.Y("users:Q", title="Users", stack="zero"),
            color=alt.Color(
                "version:N",
                title="Version",
                sort=versions_sorted,
                scale=alt.Scale(range=COLORS["palette"]),
            ),
            order=alt.Order("version:N", sort="ascending"),
        )
        .properties(width=450, height=250, title="Versions in Use (Daily)")
    )
    return (versions_chart,)


@app.cell
def _(ALL_DATES, COLORS, SINCE, alt, hogql):
    terminal_data = hogql(f"""
        SELECT toString(toDate(timestamp)) as day, properties.term_program as terminal,
               count(DISTINCT distinct_id) as users
        FROM events WHERE event = 'app_started' AND properties.term_program IS NOT NULL
            AND timestamp >= '{SINCE}'
        GROUP BY day, terminal ORDER BY day
    """)
    terminal_chart = (
        alt.Chart(alt.Data(values=terminal_data))
        .mark_bar()
        .encode(
            x=alt.X("day:O", title="Date", scale=alt.Scale(domain=ALL_DATES)),
            y=alt.Y("users:Q", title="Users", stack="zero"),
            color=alt.Color(
                "terminal:N", title="Terminal", scale=alt.Scale(range=COLORS["palette"])
            ),
        )
        .properties(width=450, height=250, title="DAU by Terminal")
    )
    return (terminal_chart,)


@app.cell
def _(ALL_DATES, COLORS, SINCE, alt, hogql):
    os_data = hogql(f"""
        SELECT toString(toDate(timestamp)) as day, properties.os as os,
               count(DISTINCT distinct_id) as users
        FROM events WHERE event = 'app_started' AND properties.os IS NOT NULL
            AND timestamp >= '{SINCE}'
        GROUP BY day, os ORDER BY day
    """)
    os_chart = (
        alt.Chart(alt.Data(values=os_data))
        .mark_bar()
        .encode(
            x=alt.X("day:O", title="Date", scale=alt.Scale(domain=ALL_DATES)),
            y=alt.Y("users:Q", title="Users", stack="zero"),
            color=alt.Color(
                "os:N", title="OS", scale=alt.Scale(range=COLORS["palette"])
            ),
        )
        .properties(width=450, height=250, title="DAU by OS")
    )
    return (os_chart,)


@app.cell
def _(ALL_DATES, SINCE, alt, hogql):
    from collections import defaultdict as _defaultdict

    messages_per_user = hogql(f"""
        SELECT toString(toDate(timestamp)) as day, distinct_id as user_id, count() as messages
        FROM events WHERE event = 'message_sent' AND timestamp >= '{SINCE}'
        GROUP BY day, user_id ORDER BY day
    """)
    _by_day = _defaultdict(list)
    for _r in messages_per_user:
        _by_day[_r["day"]].append(_r["messages"])

    def _percentile(data, p):
        if not data:
            return 0
        s = sorted(data)
        k = (len(s) - 1) * p / 100
        f = int(k)
        c = f + 1 if f + 1 < len(s) else f
        return s[f] + (s[c] - s[f]) * (k - f)

    # Days with no message_sent events show as 0 (not gaps)
    _pdata = []
    for _day in ALL_DATES:
        _counts = _by_day.get(_day, [])
        _pdata.append(
            {"day": _day, "percentile": "p10", "messages": _percentile(_counts, 10)}
        )
        _pdata.append(
            {"day": _day, "percentile": "p50", "messages": _percentile(_counts, 50)}
        )
        _pdata.append(
            {"day": _day, "percentile": "p90", "messages": _percentile(_counts, 90)}
        )

    percentile_chart = (
        alt.Chart(alt.Data(values=_pdata))
        .mark_bar()
        .encode(
            x=alt.X("day:O", title="Date", scale=alt.Scale(domain=ALL_DATES)),
            y=alt.Y("messages:Q", title="Messages/User"),
            color=alt.Color(
                "percentile:N",
                title="Percentile",
                sort=["p10", "p50", "p90"],
                scale=alt.Scale(
                    domain=["p10", "p50", "p90"],
                    range=["#22c55e", "#0891b2", "#6366f1"],
                ),
            ),
            xOffset="percentile:N",
        )
        .properties(width=450, height=250, title="Messages per User (Percentiles)")
    )
    return (percentile_chart,)


@app.cell
def _(COLORS, SINCE, alt, hogql):
    _pkg_data = hogql(f"""
        SELECT distinct_id as user_id, any(properties.has_uv) as has_uv,
               any(properties.has_conda) as has_conda
        FROM events WHERE event = 'app_started'
            AND timestamp >= '{SINCE}'
            AND distinct_id NOT LIKE '%mrocklin%'
        GROUP BY distinct_id
    """)
    _cats = {"uv only": 0, "conda only": 0, "both": 0, "neither": 0}
    for _r in _pkg_data:
        _uv, _conda = bool(_r.get("has_uv")), bool(_r.get("has_conda"))
        if _uv and _conda:
            _cats["both"] += 1
        elif _uv:
            _cats["uv only"] += 1
        elif _conda:
            _cats["conda only"] += 1
        else:
            _cats["neither"] += 1

    pkg_chart = (
        alt.Chart(
            alt.Data(values=[{"category": k, "users": v} for k, v in _cats.items()])
        )
        .mark_bar()
        .encode(
            x=alt.X("users:Q", title="Users"),
            y=alt.Y("category:N", title="Package Manager", sort="-x"),
            color=alt.Color(
                "category:N", legend=None, scale=alt.Scale(range=COLORS["palette"])
            ),
        )
        .properties(width=450, height=180, title="Package Managers (uv vs conda)")
    )
    return (pkg_chart,)


@app.cell
def _(COLORS, SINCE, alt, hogql):
    _cmd_data = hogql(f"""
        SELECT properties.command as command, count() as uses
        FROM events WHERE event = 'command_used' AND properties.command IS NOT NULL
            AND distinct_id NOT LIKE '%mrocklin%'
            AND timestamp >= '{SINCE}'
        GROUP BY command ORDER BY uses DESC
    """)
    command_chart = (
        alt.Chart(alt.Data(values=_cmd_data))
        .mark_bar(color=COLORS["palette"][0])
        .encode(
            x=alt.X("uses:Q", title="Uses"),
            y=alt.Y("command:N", title="Command", sort="-x"),
        )
        .properties(width=450, height=300, title="Command Use Histogram")
    )
    return (command_chart,)


# --- Layout cells (combine charts side-by-side) ---


@app.cell
def _(installs_chart, mo, versions_chart):
    mo.hstack(
        [mo.ui.altair_chart(installs_chart), mo.ui.altair_chart(versions_chart)],
        justify="start",
    )
    return


@app.cell
def _(mo, os_chart, terminal_chart):
    mo.hstack(
        [mo.ui.altair_chart(terminal_chart), mo.ui.altair_chart(os_chart)],
        justify="start",
    )
    return


@app.cell
def _(mo, percentile_chart, pkg_chart):
    mo.hstack(
        [mo.ui.altair_chart(percentile_chart), mo.ui.altair_chart(pkg_chart)],
        justify="start",
    )
    return


@app.cell
def _(command_chart, mo):
    mo.ui.altair_chart(command_chart)
    return


# --- Tables (full width) ---


@app.cell
def _(mo):
    mo.md("## Recent Active Users (Last 6 Hours)")
    return


@app.cell
def _(hogql, mo):
    recent_users = hogql("""
        SELECT distinct_id as user_id, any(properties.$geoip_country_name) as country,
               any(properties.$geoip_subdivision_1_name) as state, any(properties.os) as os,
               countIf(event = 'agent_created') as agents,
               countIf(event = 'message_sent') as user_messages,
               sumIf(properties.message_count, event = 'agent_closed') as total_messages
        FROM events WHERE timestamp > now() - INTERVAL 6 HOUR
        GROUP BY distinct_id HAVING user_messages > 0 OR agents > 0 ORDER BY user_messages DESC
    """)
    mo.ui.table(recent_users)
    return


@app.cell
def _(mo):
    mo.md("## Errors (Last 24 Hours)")
    return


@app.cell
def _(hogql, mo, to_local):
    _errors = hogql("""
        SELECT toString(timestamp) as time, distinct_id as user_id,
               properties.error_type as error_type, properties.context as context,
               properties.error_subtype as subtype, properties.status_code as status_code
        FROM events WHERE event = 'error_occurred' AND timestamp > now() - INTERVAL 1 DAY
        ORDER BY timestamp DESC
    """)
    for _r in _errors:
        _r["time"] = to_local(_r["time"])
    mo.ui.table(_errors)
    return


@app.cell
def _(mo):
    mo.md("## Recent Installs (Last 12 Hours)")
    return


@app.cell
def _(hogql, mo, to_local):
    _raw = hogql("""
        SELECT distinct_id as user_id, toString(min(timestamp)) as install_time
        FROM events WHERE event = 'app_installed' AND timestamp > now() - INTERVAL 12 HOUR
        GROUP BY distinct_id
    """)
    _ids = [r["user_id"] for r in _raw]
    _lookup = {r["user_id"]: r["install_time"] for r in _raw}

    if _ids:
        _activity = hogql("""
            SELECT distinct_id as user_id, any(properties.$geoip_city_name) as city,
                   any(properties.$geoip_country_name) as country,
                   countIf(event = 'message_sent') as messages,
                   countIf(event = 'agent_created') as agents,
                   countIf(event = 'error_occurred') as errors
            FROM events GROUP BY distinct_id
        """)
        _act_lookup = {r["user_id"]: r for r in _activity}
        _installs = []
        for _uid in _ids:
            _a = _act_lookup.get(_uid, {})
            _installs.append(
                {
                    "install_time": to_local(_lookup[_uid]),
                    "city": _a.get("city", ""),
                    "country": _a.get("country", ""),
                    "messages": _a.get("messages", 0),
                    "agents": _a.get("agents", 0),
                    "errors": _a.get("errors", 0),
                }
            )
        _installs.sort(key=lambda x: x["install_time"], reverse=True)
    else:
        _installs = []

    mo.ui.table(_installs)
    return


if __name__ == "__main__":
    app.run()
