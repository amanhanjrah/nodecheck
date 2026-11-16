import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin" / "nodecheck"


class NodecheckCliTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(CLI), *args], check=True, capture_output=True, text=True)

    def test_demo_scan_is_stable_and_never_needs_host_queries(self):
        first = self.run_cli("scan", "--demo").stdout
        second = self.run_cli("scan", "--demo").stdout
        self.assertEqual(first, second)
        self.assertIn("WARN  /var is 91.0% full", first)
        self.assertIn("WARN  2 systemd services failed", first)
        self.assertIn("INFO  14 package updates available", first)

    def test_demo_shorthand(self):
        self.assertEqual(self.run_cli("--demo").stdout, self.run_cli("scan", "--demo").stdout)

    def test_demo_json_report(self):
        result = self.run_cli("report", "--demo", "--format", "json")
        data = json.loads(result.stdout)
        self.assertEqual(data["hostname"], "demo-linux-host")
        self.assertEqual(data["pending_updates"], 14)

    def test_demo_html_report(self):
        result = self.run_cli("report", "--demo", "--format", "html")
        self.assertIn("<!doctype html>", result.stdout)
        self.assertIn("nodecheck health report", result.stdout)


if __name__ == "__main__":
    unittest.main()
