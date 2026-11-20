"""Black-box acceptance for the initial Rust CLI; requires Python 3.11+."""

import os
from pathlib import Path
import re
import subprocess
import sys
import tomllib
import unittest
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
BINARY = Path(sys.argv.pop(1)).resolve() if len(sys.argv) > 1 else ROOT / "target/debug/msar"
VERSION = tomllib.loads((ROOT / "Cargo.toml").read_text())["package"]["version"]


class CliSmoke(unittest.TestCase):
    def invoke(self, *args):
        return subprocess.run([BINARY, *args], capture_output=True, timeout=10)

    def test_help(self):
        expected = self.invoke().stdout
        for args in [(), ("-h",), ("--help",)]:
            with self.subTest(args=args):
                result = self.invoke(*args)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stderr, b"")
                self.assertEqual(result.stdout, expected)
                for text in [b"Usage: msar", b"--help", b"--version", b"monitoring is planned"]:
                    self.assertIn(text, result.stdout)

    def test_version(self):
        for arg in ["-V", "--version"]:
            with self.subTest(arg=arg):
                result = self.invoke(arg)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stdout, f"msar {VERSION}\n".encode())
                self.assertEqual(result.stderr, b"")

    def test_invalid_arguments(self):
        cases = [(arg,) for arg in [
            "--unknown", "file.txt", "未知参数", "--cpu", "--mem", "--load",
            "--io", "--traffic", "-a", "--all", "-n", "--interval", "-o", "--output",
        ]]
        cases += [("--help", "extra"), ("--version", "--help"), ("--help", "--unknown")]
        for args in cases:
            with self.subTest(args=args):
                result = self.invoke(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, b"")
                self.assertIn(os.fsencode(args[-1]), result.stderr)
                self.assertIn(b"msar:", result.stderr)
                self.assertIn(b"--help", result.stderr)
                self.assertNotIn(b"panicked", result.stderr)

    @unittest.skipUnless(os.name == "posix", "Unix OS arguments required")
    def test_non_utf8_argument(self):
        result = self.invoke(b"--invalid-\xff")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")
        self.assertIn(b"--invalid-", result.stderr)
        self.assertIn(b"--help", result.stderr)
        self.assertNotIn(b"panicked", result.stderr)

    def test_stdout_failure(self):
        with open(os.devnull, "rb") as read_only:
            result = subprocess.run(
                [BINARY, "--help"], stdout=read_only, stderr=subprocess.PIPE, timeout=10
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"cannot write stdout", result.stderr)
        self.assertNotIn(b"panicked", result.stderr)

    @unittest.skipUnless(os.name == "posix", "Unix pipe required")
    def test_broken_pipe(self):
        reader, writer = os.pipe()
        os.close(reader)
        try:
            result = subprocess.run(
                [BINARY, "--help"], stdout=writer, stderr=subprocess.PIPE, timeout=10
            )
        finally:
            os.close(writer)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, b"")

    def test_document_links(self):
        for document in ROOT.glob("*.md"):
            for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", document.read_text()):
                link = urlsplit(target)
                if link.scheme or link.netloc or not link.path:
                    continue
                with self.subTest(document=document.name, link=target):
                    self.assertTrue((document.parent / unquote(link.path)).exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
