from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import TypedDict, cast
from uuid import uuid4

from flask import Flask, g, render_template, request, url_for

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "crawler_game.db"

app = Flask(__name__)


SCHEMA = """
CREATE TABLE IF NOT EXISTS request_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    method TEXT NOT NULL,
    path TEXT NOT NULL,
    query_string TEXT NOT NULL,
    crawler_id TEXT,
    started_on TEXT,
    counter INTEGER,
    choices TEXT,
    user_agent TEXT
);
"""


class CrawlParams(TypedDict):
    id: str
    started: str
    counter: int
    choices: str


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return cast(sqlite3.Connection, g.db)


@app.teardown_appcontext
def close_db(_exception: BaseException | None = None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as db:
        db.executescript(SCHEMA)


_db_initialized = False
_db_init_lock = Lock()


def ensure_db_initialized() -> None:
    global _db_initialized
    if _db_initialized:
        return
    with _db_init_lock:
        if _db_initialized:
            return
        init_db()
        _db_initialized = True


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def today_iso_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def is_power_of_eight(value: int) -> bool:
    if value < 1:
        return False
    while value % 8 == 0:
        value //= 8
    return value == 1


def normalize_params() -> CrawlParams:
    crawler_id = request.args.get("id") or str(uuid4())
    started_on = request.args.get("started") or today_iso_date()
    raw_counter = request.args.get("counter", "0")
    try:
        counter = max(0, int(raw_counter))
    except ValueError:
        counter = 0
    choices = request.args.get("choices", "")
    return {
        "id": crawler_id,
        "started": started_on,
        "counter": counter,
        "choices": choices,
    }


@app.before_request
def log_request() -> None:
    ensure_db_initialized()
    params = normalize_params()
    g.crawler_params = params
    db = get_db()
    db.execute(
        """
        INSERT INTO request_log (
            created_at, method, path, query_string, crawler_id, started_on, counter, choices, user_agent
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            now_iso(),
            request.method,
            request.path,
            request.query_string.decode("utf-8", errors="ignore"),
            params["id"],
            params["started"],
            params["counter"],
            params["choices"],
            request.headers.get("User-Agent", "unknown"),
        ),
    )
    db.commit()


@app.route("/")
def home() -> str:
    crawler_id = str(uuid4())
    started_on = today_iso_date()
    start_link = url_for("play", id=crawler_id, started=started_on, counter=0)
    return render_template(
        "home.html",
        start_link=start_link,
        crawler_id=crawler_id,
        started_on=started_on,
        metadata={
            "@context": "https://schema.org",
            "@type": "VideoGame",
            "name": "Crawler Game",
            "description": "A web game where crawlers explore branching links.",
            "genre": "Puzzle",
        },
    )


@app.route("/play")
def play() -> str:
    params = getattr(g, "crawler_params", normalize_params())
    counter = int(params["counter"])
    choices = str(params["choices"])
    next_counter = counter + 1

    choice_list = [c for c in choices.split("-") if c]
    is_decision = counter >= 8 and is_power_of_eight(counter)

    next_links: list[dict[str, str]] = []
    if is_decision:
        next_links.append(
            {
                "label": "Take the Red Portal",
                "url": url_for(
                    "play",
                    id=params["id"],
                    started=params["started"],
                    counter=next_counter,
                    choices="-".join(choice_list + ["red"]),
                ),
            }
        )
        next_links.append(
            {
                "label": "Take the Blue Portal",
                "url": url_for(
                    "play",
                    id=params["id"],
                    started=params["started"],
                    counter=next_counter,
                    choices="-".join(choice_list + ["blue"]),
                ),
            }
        )
    else:
        next_links.append(
            {
                "label": "Continue deeper",
                "url": url_for(
                    "play",
                    id=params["id"],
                    started=params["started"],
                    counter=next_counter,
                    choices=choices,
                ),
            }
        )

    return render_template(
        "play.html",
        crawler_id=params["id"],
        started_on=params["started"],
        counter=counter,
        choices=choice_list,
        is_decision=is_decision,
        next_links=next_links,
        metadata={
            "@context": "https://schema.org",
            "@type": "WebPage",
            "name": "Crawler Game Run",
            "description": "A crawler challenge page with branching paths.",
        },
    )


@app.route("/stats")
def stats() -> str:
    db = get_db()
    scores = db.execute(
        """
        SELECT
            crawler_id,
            MIN(started_on) AS started_on,
            COUNT(*) AS explored_nodes,
            MAX(COALESCE(counter, 0)) AS deepest_path,
            MAX(created_at) AS last_request_at
        FROM request_log
        WHERE path = '/play' AND crawler_id IS NOT NULL
        GROUP BY crawler_id
        ORDER BY explored_nodes DESC, deepest_path DESC, last_request_at DESC
        LIMIT 10
        """
    ).fetchall()

    top_timeline: list[dict[str, object]] = []
    if scores:
        top_id = scores[0]["crawler_id"]
        rows = db.execute(
            """
            SELECT created_at, counter, COALESCE(choices, '') AS choices
            FROM request_log
            WHERE path = '/play' AND crawler_id = ?
            ORDER BY id ASC
            """,
            (top_id,),
        ).fetchall()
        for idx, row in enumerate(rows, start=1):
            choices = [c for c in row["choices"].split("-") if c]
            top_timeline.append(
                {
                    "index": idx,
                    "created_at": row["created_at"],
                    "counter": row["counter"],
                    "choices": choices,
                }
            )

    formatted_scores: list[dict[str, object]] = []
    for row in scores:
        agent_rows = db.execute(
            """
            SELECT user_agent
            FROM request_log
            WHERE path = '/play' AND crawler_id = ? AND user_agent IS NOT NULL
            ORDER BY id DESC
            LIMIT 20
            """,
            (row["crawler_id"],),
        ).fetchall()
        seen = set()
        agents = []
        for agent_row in agent_rows:
            user_agent = agent_row["user_agent"]
            if user_agent not in seen:
                seen.add(user_agent)
                agents.append(user_agent)
            if len(agents) >= 3:
                break
        formatted_scores.append(
            {
                "crawler_id": row["crawler_id"],
                "started_on": row["started_on"],
                "explored_nodes": row["explored_nodes"],
                "deepest_path": row["deepest_path"],
                "last_request_at": row["last_request_at"],
                "user_agents": agents,
            }
        )

    today = today_iso_date()
    global_stats_row = db.execute(
        """
        SELECT
            COUNT(*) AS total_requests,
            COUNT(DISTINCT CASE WHEN path = '/play' THEN crawler_id END) AS total_crawl_trees,
            COALESCE(SUM(CASE WHEN substr(created_at, 1, 10) = ? THEN 1 ELSE 0 END), 0) AS today_requests,
            COUNT(DISTINCT CASE WHEN path = '/play' AND substr(created_at, 1, 10) = ? THEN crawler_id END) AS today_crawl_trees
        FROM request_log
        """,
        (today, today),
    ).fetchone()
    global_stats = {
        "total_requests": global_stats_row["total_requests"] if global_stats_row else 0,
        "total_crawl_trees": global_stats_row["total_crawl_trees"] if global_stats_row else 0,
        "today_requests": global_stats_row["today_requests"] if global_stats_row else 0,
        "today_crawl_trees": global_stats_row["today_crawl_trees"] if global_stats_row else 0,
    }

    return render_template(
        "stats.html",
        scores=formatted_scores,
        top_timeline=top_timeline,
        top_timeline_json=json.dumps(top_timeline),
        global_stats=global_stats,
    )


if __name__ == "__main__":
    ensure_db_initialized()
    app.run(host="127.0.0.1", port=5000, debug=False)
