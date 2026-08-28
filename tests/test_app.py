import importlib
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app as app_module


class CrawlerGameTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        app_module.DB_PATH = Path(self._tmpdir.name) / "test.db"
        app_module._db_initialized = False
        app_module.ensure_db_initialized()
        self.client = app_module.app.test_client()

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_db_path_can_be_configured_via_environment(self) -> None:
        configured_db_path = Path(self._tmpdir.name) / "configured.db"

        try:
            with patch.dict(os.environ, {"CRAWLER_GAME_DB_PATH": str(configured_db_path)}):
                importlib.reload(app_module)
                self.assertEqual(app_module.DB_PATH, configured_db_path)
        finally:
            importlib.reload(app_module)

    def test_decision_appears_at_power_of_eight(self) -> None:
        response = self.client.get("/play?id=test-tree&started=2026-08-28&counter=8")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Take the Red Portal", response.data)
        self.assertIn(b"Take the Blue Portal", response.data)

    def test_non_decision_uses_single_continue_link(self) -> None:
        response = self.client.get("/play?id=test-tree&started=2026-08-28&counter=7")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Continue deeper", response.data)
        self.assertNotIn(b"Take the Red Portal", response.data)

    def test_stats_page_shows_global_totals(self) -> None:
        self.client.get("/")
        self.client.get("/play?id=tree-a&started=2026-08-28&counter=0")
        self.client.get("/play?id=tree-b&started=2026-08-28&counter=0")
        response = self.client.get("/stats")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Total requests:</strong> 4", response.data)
        self.assertIn(b"Total crawl trees:</strong> 2", response.data)
        self.assertIn(b"Today's requests:</strong> 4", response.data)
        self.assertIn(b"Today's crawl trees:</strong> 2", response.data)

    def test_stats_page_shows_recrawled_nodes(self) -> None:
        self.client.get("/play?id=tree-r&started=2026-08-28&counter=3&choices=red")
        self.client.get("/play?id=tree-r&started=2026-08-28&counter=3&choices=red")
        response = self.client.get("/stats")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Recrawled Nodes", response.data)
        html = response.data.decode("utf-8")
        self.assertRegex(
            html,
            re.compile(
                r"<td>tree-r</td>\s*<td>2026-08-28</td>\s*<td>2</td>\s*<td>1</td>\s*<td>3</td>",
                re.MULTILINE,
            ),
        )


if __name__ == "__main__":
    unittest.main()
