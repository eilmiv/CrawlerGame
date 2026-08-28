# CrawlerGame

A small Flask web game for web crawlers. Each page advances a tracked crawl path using URL parameters (`started`, `id`, `counter`, `choices`) and logs all requests for statistics.

## Features

- Link chain mechanic that preserves `id` and `started` and increments `counter`.
- Decision nodes at powers of 8 (8, 64, 512, ...) with red/blue branches appended to `choices`.
- Dark-mode game-like pages with JSON-LD metadata.
- Statistics page with top 10 crawler highscores and a timeline slider replay for the top crawler.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Then open <http://127.0.0.1:5000>.
