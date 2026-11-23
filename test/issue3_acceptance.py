"""Black-box acceptance for issue #3; requires Python 3.11+.

Run: python3 test/issue3_acceptance.py target/debug/msar

Covers every frozen acceptance criterion from Plan v1 (issue #3) that is
observable from outside the process. Deliberately does not import the crate.
"""

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
BINARY = Path(sys.argv.pop(1)).resolve() if len(sys.argv) > 1 else ROOT / "target/debug/msar"
VERSION = tomllib.loads((ROOT / "Cargo.toml").read_text())["package"]["version"]

MODULE_FLAGS = ["--cpu", "--mem", "--load", "--io", "--traffic", "-a"]


class Issue3(unittest.TestCase):
    def invoke(self, *args, timeout=20):
        return subprocess.run([BINARY, *args], capture_output=True, timeout=timeout)

    # ---- step 2: argument parsing -------------------------------------
    def test_module_flags_are_accepted(self):
        for flag in MODULE_FLAGS:
            with self.subTest(flag=flag):
                result = self.invoke(flag)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn(b"panicked", result.stderr)

    def test_help_lists_every_option(self):
        result = self.invoke("--help")
        self.assertEqual(result.returncode, 0)
        for flag in MODULE_FLAGS + ["-n", "--interval", "-o", "--output", "-h", "--help", "-V", "--version"]:
            with self.subTest(flag=flag):
                self.assertIn(flag.encode(), result.stdout)

    def test_version_is_unchanged(self):
        for arg in ["-V", "--version"]:
            with self.subTest(arg=arg):
                result = self.invoke(arg)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stdout, f"msar {VERSION}\n".encode())

    def test_unknown_option_still_fails(self):
        result = self.invoke("--nope")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")
        self.assertIn(b"msar:", result.stderr)
        self.assertIn(b"--help", result.stderr)

    def test_no_arguments_prints_help(self):
        result = self.invoke()
        self.assertEqual(result.returncode, 0)
        self.assertIn(b"Usage: msar", result.stdout)

    # ---- step 3: invalid intervals ------------------------------------
    def test_invalid_intervals_are_rejected(self):
        for value in ["-1", "0", "abc"]:
            with self.subTest(value=value):
                result = self.invoke("--cpu", "-n", value)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertNotEqual(result.stderr, b"")
                self.assertNotIn(b"panicked", result.stderr)

    def test_interval_without_value_does_not_swallow_flag(self):
        # `-n --cpu` means "1 second, CPU", not "value --cpu". A periodic run
        # never exits on its own, so bound it with a timeout and check it was
        # accepted (i.e. it started sampling rather than failing on input).
        try:
            result = subprocess.run(
                [BINARY, "-n", "--cpu"],
                capture_output=True,
                timeout=2,
            )
        except subprocess.TimeoutExpired:
            return  # still running: input accepted, which is the point
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_explicit_interval_runs_repeatedly(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "out.jsonl"
            try:
                subprocess.run(
                    [BINARY, "-a", "-n", "1", "-o", str(path)],
                    capture_output=True,
                    timeout=5,
                )
            except subprocess.TimeoutExpired:
                pass
            self.assertGreaterEqual(len(path.read_text().splitlines()), 2)

    # ---- step 6: output contract --------------------------------------
    def test_terminal_output_has_module_heading(self):
        result = self.invoke("--cpu")
        self.assertEqual(result.returncode, 0)
        self.assertIn(b"Cpu", result.stdout)
        self.assertIn(b"unavailable", result.stdout)

    def test_jsonl_lines_are_valid_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "out.jsonl"
            result = self.invoke("-a", "-o", str(path))
            self.assertEqual(result.returncode, 0, result.stderr)
            lines = path.read_text().splitlines()
            self.assertGreaterEqual(len(lines), 1)
            for line in lines:
                with self.subTest(line=line):
                    payload = json.loads(line)
                    self.assertIsInstance(payload, dict)
                    self.assertIn("hostname", payload)
                    self.assertIn("timestamp", payload)
                    self.assertTrue(payload["hostname"])
                    self.assertIsInstance(payload["timestamp"], (int, float))

    def test_all_selected_modules_are_present_as_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "out.jsonl"
            result = self.invoke("-a", "-o", str(path))
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(path.read_text().splitlines()[-1])
            for key in ["Cpu", "Mem", "Load", "IO", "Traffic"]:
                with self.subTest(key=key):
                    self.assertIn(key, payload)

    def test_values_are_numbers_or_null_not_strings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "out.jsonl"
            self.invoke("--cpu", "-o", str(path))
            payload = json.loads(path.read_text().splitlines()[-1])
            for field, value in payload["Cpu"].items():
                with self.subTest(field=field):
                    self.assertTrue(
                        value is None or isinstance(value, (int, float)),
                        f"{field}={value!r}",
                    )

    def test_output_appends_rather_than_truncates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "out.jsonl"
            self.invoke("--cpu", "-o", str(path))
            first = len(path.read_text().splitlines())
            self.invoke("--cpu", "-o", str(path))
            self.assertEqual(len(path.read_text().splitlines()), first + 1)

    # ---- step 7: file errors are observable ---------------------------
    def test_unwritable_path_is_reported(self):
        target = "/nonexistent-msar-dir/out.jsonl"
        result = self.invoke("--cpu", "-o", target)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"cannot write", result.stderr)
        self.assertIn(b"out.jsonl", result.stderr)
        self.assertNotIn(b"panicked", result.stderr)

    # ---- step 8: HTTP is refused, not silently dropped ----------------
    def test_http_output_is_refused(self):
        for url in ["http://example.com/x", "https://example.com/x"]:
            with self.subTest(url=url):
                result = self.invoke("--cpu", "-o", url)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn(b"HTTP", result.stderr)
                self.assertFalse(Path("x").exists())

    # ---- step 9: signal shutdown --------------------------------------
    def test_sigterm_exits_promptly(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "out.jsonl"
            process = subprocess.Popen(
                [BINARY, "-a", "-n", "1", "-o", str(path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            try:
                time.sleep(1.5)
                started = time.monotonic()
                process.send_signal(signal.SIGTERM)
                process.wait(timeout=5)
                elapsed = time.monotonic() - started
            finally:
                if process.poll() is None:
                    process.kill()
            self.assertEqual(process.returncode, 0, process.stderr.read())
            self.assertLess(elapsed, 2.0)
            self.assertGreaterEqual(len(path.read_text().splitlines()), 1)

    def test_sigint_exits_promptly(self):
        process = subprocess.Popen(
            [BINARY, "-a", "-n", "1"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            time.sleep(1.0)
            process.send_signal(signal.SIGINT)
            process.wait(timeout=5)
        finally:
            if process.poll() is None:
                process.kill()
        self.assertEqual(process.returncode, 0, process.stderr.read())

    # ---- step 10: no panic or negative values -------------------------
    def test_run_produces_no_panic_or_negative_percent(self):
        result = self.invoke("-a")
        self.assertEqual(result.returncode, 0)
        self.assertNotIn(b"panicked", result.stderr)
        for line in result.stdout.decode(errors="replace").splitlines():
            stripped = line.strip()
            if ":" in stripped:
                value = stripped.rsplit(":", 1)[-1].strip()
                if value.replace(".", "", 1).replace("-", "", 1).isdigit():
                    with self.subTest(line=line):
                        self.assertGreaterEqual(float(value), 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
