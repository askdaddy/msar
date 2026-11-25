"""Black-box acceptance for issue #5; requires Python 3.11+.

Run: python3 test/issue5_acceptance.py [binary]

Each check runs the built binary and compares its observable output against the
platform's own sources (sysctl, vm_stat, iostat, netstat), so it does not reuse
the developer's unit tests. It runs on macOS only; elsewhere every check skips.
"""

import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time
import tomllib
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
BINARY = Path(sys.argv.pop(1)).resolve() if len(sys.argv) > 1 else ROOT / "target/debug/msar"
VERSION = tomllib.loads((ROOT / "Cargo.toml").read_text())["package"]["version"]
ON_MACOS = sys.platform == "darwin"
MAC_ONLY = unittest.skipUnless(ON_MACOS, "macOS data sources required")

# Measured with a C probe on this machine: 30 one-shot rounds at these windows.
CPU_WINDOW_MS = 1000


def run(*args, timeout=60):
    return subprocess.run([BINARY, *args], capture_output=True, timeout=timeout)


def output_path():
    return Path(tempfile.mkdtemp()) / f"out-{uuid.uuid4().hex}.jsonl"


def sample(*args, timeout=60):
    """One round as JSON, so values keep their types."""
    path = output_path()
    result = run(*args, "-o", str(path), timeout=timeout)
    if result.returncode != 0:
        raise AssertionError(result.stderr.decode(errors="replace"))
    return json.loads(path.read_text().splitlines()[-1])


def command(*args):
    result = subprocess.run(list(args), capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise unittest.SkipTest(f"cannot run {args[0]}: {result.stderr}")
    return result.stdout


class Issue5(unittest.TestCase):
    # ---- module selection and shape ----------------------------------
    def test_all_five_modules_are_present(self):
        payload = sample("-a")
        for key in ["Cpu", "Mem", "Load", "IO", "Traffic"]:
            with self.subTest(key=key):
                self.assertIn(key, payload)

    def test_values_are_numbers_or_null_never_negative(self):
        payload = sample("-a")
        for module, values in payload.items():
            if module in {"hostname", "timestamp"}:
                continue
            for field, value in values.items():
                with self.subTest(module=module, field=field):
                    self.assertTrue(
                        value is None or isinstance(value, (int, float)),
                        f"{module}.{field}={value!r}",
                    )
                    if value is not None:
                        self.assertGreaterEqual(value, 0.0, f"{module}.{field}")

    def test_no_panic_and_exit_zero(self):
        result = run("-a")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(b"panicked", result.stderr)

    def test_module_flags_select_one_module(self):
        for flag, key in [
            ("--cpu", "Cpu"),
            ("--mem", "Mem"),
            ("--load", "Load"),
            ("--io", "IO"),
            ("--traffic", "Traffic"),
        ]:
            with self.subTest(flag=flag):
                payload = sample(flag)
                self.assertIn(key, payload)
                for other in {"Cpu", "Mem", "Load", "IO", "Traffic"} - {key}:
                    self.assertNotIn(other, payload)

    # ---- CPU ---------------------------------------------------------
    @MAC_ONLY
    def test_cpu_fields_and_shares(self):
        # Plan v4: us/sy/id are numbers summing to about 100, wa is null.
        for _ in range(30):
            cpu = sample("--cpu")["Cpu"]
            self.assertEqual(set(cpu), {"us", "sy", "id", "wa"}, cpu)
            self.assertIsNone(cpu["wa"], cpu)
            for field in ["us", "sy", "id"]:
                with self.subTest(field=field, cpu=cpu):
                    self.assertIsInstance(cpu[field], (int, float), cpu)
                    self.assertGreaterEqual(cpu[field], 0.0)
                    self.assertLessEqual(cpu[field], 100.0)
            total = cpu["us"] + cpu["sy"] + cpu["id"]
            self.assertGreaterEqual(total, 99.0, cpu)
            self.assertLessEqual(total, 100.5, cpu)

    @MAC_ONLY
    def test_cpu_is_never_null_in_periodic_mode(self):
        path = output_path()
        try:
            subprocess.run(
                [BINARY, "-a", "-n", "1", "-o", str(path)],
                capture_output=True,
                timeout=12,
            )
        except subprocess.TimeoutExpired:
            pass
        rounds = [json.loads(line) for line in path.read_text().splitlines()]
        self.assertGreaterEqual(len(rounds), 2, "no rounds were written")
        for index, payload in enumerate(rounds):
            cpu = payload["Cpu"]
            with self.subTest(round=index, cpu=cpu):
                self.assertIsNone(cpu["wa"])
                for field in ["us", "sy", "id"]:
                    self.assertIsInstance(cpu[field], (int, float), cpu)

    # ---- memory ------------------------------------------------------
    @MAC_ONLY
    def test_memory_matches_sysctl_and_vm_stat(self):
        memsize = int(command("sysctl", "-n", "hw.memsize").strip())
        pagesize = int(command("sysctl", "-n", "hw.pagesize").strip())
        mem = sample("--mem")["Mem"]

        self.assertEqual(set(mem), {"total", "free", "buffers", "cached", "available"})
        self.assertIsNone(mem["buffers"], "macOS has no Buffers counter")
        # total is a fixed quantity, so it must match exactly in KiB.
        self.assertEqual(mem["total"], memsize // 1024, mem)

        stats = command("vm_stat")
        pages = {}
        for line in stats.splitlines():
            key, _, rest = line.partition(":")
            field = rest.strip().rstrip(".").split()
            if field and field[0].isdigit():
                pages[key.strip()] = int(field[0])
        kib = lambda count: count * pagesize // 1024
        # Snapshots move a little between our read and the binary's, so allow 5%.
        for field, expected in [
            ("free", kib(pages.get("Pages free", 0))),
            ("cached", kib(pages.get("Pages active", 0) + pages.get("Pages inactive", 0))),
            ("available", kib(pages.get("Pages free", 0) + pages.get("Pages inactive", 0))),
        ]:
            with self.subTest(field=field, mem=mem):
                self.assertAlmostEqual(mem[field] / max(expected, 1), 1.0, delta=0.05)

    # ---- load --------------------------------------------------------
    @MAC_ONLY
    def test_load_matches_sysctl(self):
        raw = command("sysctl", "-n", "vm.loadavg").strip().strip("{}").split()
        expected = [float(value) for value in raw[:3]]
        load = sample("--load")["Load"]
        self.assertEqual(set(load), {"load1", "load5", "load15"})
        for field, value in zip(["load1", "load5", "load15"], expected):
            with self.subTest(field=field, load=load):
                # Load moves continuously, so compare with a tolerance.
                self.assertAlmostEqual(load[field], value, delta=1.0)

    # ---- disk I/O ----------------------------------------------------
    @MAC_ONLY
    def test_io_reports_real_disks_and_no_utilisation(self):
        # Only the header line names disks; the row after it is units
        # (`KB/t xfrs MB`) and the rest are numbers, so parse the header.
        header = command("iostat", "-Id", "-c", "1").splitlines()
        disks = {name for name in header[0].split() if not name.replace(".", "").isdigit()}
        io = sample("--io")["IO"]
        names = {key.split(".", 1)[0] for key in io}
        for disk in sorted(disks)[:4]:
            with self.subTest(disk=disk):
                self.assertIn(disk, names)

        fields = {key.split(".", 1)[1] for key in io}
        for field in ["rs", "ws", "rkBs", "wkBs"]:
            with self.subTest(field=field):
                self.assertIn(field, fields)
        # macOS exposes no utilisation, latency or queue counters, so these must
        # stay null rather than claiming a fabricated zero (plan v1 C4).
        for field in ["util", "await", "svctm", "avgrq-sz", "avgqu-sz"]:
            with self.subTest(field=field):
                values = [
                    value
                    for key, value in io.items()
                    if key.endswith(f".{field}")
                ]
                self.assertTrue(values, f"{field} is missing")
                self.assertTrue(all(value is None for value in values), f"{field}={values}")

    @MAC_ONLY
    def test_io_is_fast_enough_for_a_periodic_run(self):
        # A round must not be dominated by a data source; `netstat -ib` without
        # `-n` alone cost about five seconds per call before it was added.
        started = time.monotonic()
        sample("-a")
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 3.0, f"-a took {elapsed:.2f}s")

    # ---- network -----------------------------------------------------
    @MAC_ONLY
    def test_traffic_field_names_and_interfaces(self):
        traffic = sample("--traffic")["Traffic"]
        for field in traffic:
            with self.subTest(field=field):
                self.assertTrue(
                    field.endswith(".inbytes") or field.endswith(".outbytes"),
                    field,
                )
        # Loopback always carries traffic from any process talking to localhost.
        self.assertIn("lo0.inbytes", traffic, "loopback is missing")
        self.assertIsInstance(traffic["lo0.inbytes"], (int, float))
        # Each interface must appear once, even though netstat repeats it per
        # address; without de-duplication en1 appeared three times.
        names = [field.rsplit(".", 1)[0] for field in traffic]
        for name in set(names):
            with self.subTest(interface=name):
                self.assertEqual(names.count(name), 2, f"{name} appears {names.count(name)} times")

    # ---- contract kept from earlier issues ----------------------------
    def test_version_unchanged(self):
        result = run("-V")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, f"msar {VERSION}\n".encode())

    def test_help_and_no_arguments(self):
        for args in [(), ("-h",), ("--help",)]:
            with self.subTest(args=args):
                result = run(*args)
                self.assertEqual(result.returncode, 0)
                self.assertIn(b"Usage: msar", result.stdout)

    def test_unknown_option_is_rejected(self):
        result = run("--nope")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")


if __name__ == "__main__":
    unittest.main(verbosity=2)
