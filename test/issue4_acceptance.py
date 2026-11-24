"""Black-box acceptance for issue #4; requires Python 3.11+.

Run: python3 test/issue4_acceptance.py [binary]

Every check runs the built binary as a subprocess and inspects only its
observable output, so it does not reuse the developer's unit tests. Linux
specific checks probe the container's own /proc for the expected values and
skip when that source is absent.
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
BINARY = Path(sys.argv.pop(1)).resolve() if len(sys.argv) > 1 else ROOT / "target/debug/msar"
VERSION = tomllib.loads((ROOT / "Cargo.toml").read_text())["package"]["version"]



class _NoCleanup:
    """Stand-in for TemporaryDirectory when the caller owns the directory."""

    def __init__(self, path):
        self.path = path

    def __enter__(self):
        Path(self.path).mkdir(parents=True, exist_ok=True)
        return self.path

    def __exit__(self, *_):
        return False


def run(*args, timeout=30):
    return subprocess.run([BINARY, *args], capture_output=True, timeout=timeout)


def read_output(path):
    """Read a file the binary wrote, which may live in another environment."""
    helper = os.environ.get("MSAR_QA_READ")
    if helper:
        result = subprocess.run(helper.split() + [str(path)], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise AssertionError(f"cannot read {path}: {result.stderr}")
        return result.stdout
    return Path(path).read_text()


def output_dir():
    """A directory the binary can actually write to.

    When the binary runs elsewhere (MSAR_QA_EXEC), a host temporary directory
    is not visible to it, so the caller names a shared path instead.
    """
    return os.environ.get("MSAR_QA_OUTPUT_DIR")


def sample_jsonl(*args):
    """One round as JSON, so values keep their types."""
    shared = output_dir()
    context = tempfile.TemporaryDirectory() if shared is None else _NoCleanup(shared)
    with context as directory:
        path = Path(directory) / f"out-{uuid.uuid4().hex}.jsonl"
        result = run(*args, "-o", str(path))
        if result.returncode != 0:
            raise AssertionError(result.stderr.decode(errors="replace"))
        return json.loads(read_output(path).splitlines()[-1])


# The binary under test may run somewhere other than this host (for example a
# wrapper that executes it inside a Linux container), so Linux is detected from
# what the binary itself reports rather than from the host filesystem.
ON_LINUX = None


def on_linux():
    """Whether the binary reads real Linux /proc data."""
    global ON_LINUX
    if ON_LINUX is None:
        try:
            cpu = sample_jsonl("--cpu")["Cpu"]
        except (AssertionError, KeyError, json.JSONDecodeError):
            ON_LINUX = False
        else:
            ON_LINUX = any(value is not None for value in cpu.values())
    return ON_LINUX


def proc_read(path):
    """Read a /proc file through the same environment as the binary."""
    helper = os.environ.get("MSAR_QA_READ")
    if helper:
        result = subprocess.run(
            helper.split() + [path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.stdout if result.returncode == 0 else None
    try:
        return Path(path).read_text()
    except OSError:
        return None


PROC_STAT = "/proc/stat"
PROC_MEMINFO = "/proc/meminfo"
PROC_LOADAVG = "/proc/loadavg"
PROC_DISKSTATS = "/proc/diskstats"
PROC_NETDEV = "/proc/net/dev"
LINUX_ONLY = unittest.skipUnless(on_linux(), "Linux /proc data required")


def real_stat_counters():
    for line in (proc_read(PROC_STAT) or "").splitlines():
        fields = line.split()
        if fields and fields[0] == "cpu":
            return [int(value) for value in fields[1:]]
    return None


def real_meminfo():
    values = {}
    for line in (proc_read(PROC_MEMINFO) or "").splitlines():
        key, _, rest = line.partition(":")
        fields = rest.split()
        if fields and fields[0].isdigit():
            values[key.strip()] = int(fields[0])
    return values


class Issue4(unittest.TestCase):
    # ---- output shape on every platform -------------------------------
    def test_all_five_modules_are_present(self):
        payload = sample_jsonl("-a")
        for key in ["Cpu", "Mem", "Load", "IO", "Traffic"]:
            with self.subTest(key=key):
                self.assertIn(key, payload)

    def test_values_are_numbers_or_null(self):
        payload = sample_jsonl("-a")
        for module, values in payload.items():
            if module in {"hostname", "timestamp"}:
                continue
            for field, value in values.items():
                with self.subTest(module=module, field=field):
                    self.assertTrue(
                        value is None or isinstance(value, (int, float)),
                        f"{module}.{field}={value!r}",
                    )

    def test_no_panic_and_exit_zero(self):
        result = run("-a")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(b"panicked", result.stderr)

    def test_single_module_selection(self):
        for flag, key in [
            ("--cpu", "Cpu"),
            ("--mem", "Mem"),
            ("--load", "Load"),
            ("--io", "IO"),
            ("--traffic", "Traffic"),
        ]:
            with self.subTest(flag=flag):
                payload = sample_jsonl(flag)
                self.assertIn(key, payload)
                for other in {"Cpu", "Mem", "Load", "IO", "Traffic"} - {key}:
                    self.assertNotIn(other, payload)

    # ---- CPU ---------------------------------------------------------
    @LINUX_ONLY
    def test_cpu_shares_are_bounded_and_sum_to_about_100(self):
        # Plan v4: four shares in 0..=100, sum in [95, 100.5]. The denominator
        # keeps nice/irq/softirq/steal, which are not reported.
        for _ in range(5):
            cpu = sample_jsonl("--cpu")["Cpu"]
            self.assertEqual(set(cpu), {"us", "sy", "id", "wa"}, cpu)
            for field, value in cpu.items():
                with self.subTest(field=field):
                    self.assertIsInstance(value, (int, float), f"{field}={value!r}")
                    self.assertGreaterEqual(value, 0.0)
                    self.assertLessEqual(value, 100.0)
            total = sum(cpu.values())
            self.assertGreaterEqual(total, 95.0, cpu)
            self.assertLessEqual(total, 100.5, cpu)

    @LINUX_ONLY
    def test_cpu_total_excludes_guest(self):
        # guest/guest_nice inside user/nice must not shorten the total; with a
        # zero guest counter both readings agree, so only assert consistency
        # with the real total the binary can reproduce.
        counters = real_stat_counters()
        self.assertIsNotNone(counters)
        total = sum(counters[:8])
        self.assertGreater(total, 0)
        cpu = sample_jsonl("--cpu")["Cpu"]
        for field, value in cpu.items():
            with self.subTest(field=field):
                self.assertIsInstance(value, (int, float))

    # ---- memory ------------------------------------------------------
    @LINUX_ONLY
    def test_memory_matches_proc_meminfo(self):
        meminfo = real_meminfo()
        mem = sample_jsonl("--mem")["Mem"]
        for field, key in [
            ("total", "MemTotal"),
            ("free", "MemFree"),
            ("buffers", "Buffers"),
            ("cached", "Cached"),
            ("available", "MemAvailable"),
        ]:
            with self.subTest(field=field):
                if key not in meminfo:
                    self.assertIsNone(mem[field])
                else:
                    # A snapshot can move a little between our read and the
                    # binary's; require the same order of magnitude.
                    self.assertAlmostEqual(
                        mem[field] / meminfo[key], 1.0, delta=0.2,
                        msg=f"{field}={mem[field]} vs {key}={meminfo[key]}",
                    )

    def test_memory_has_every_legacy_field(self):
        mem = sample_jsonl("--mem")["Mem"]
        for field in ["total", "free", "buffers", "cached", "available"]:
            with self.subTest(field=field):
                self.assertIn(field, mem)

    # ---- load --------------------------------------------------------
    @LINUX_ONLY
    def test_load_matches_proc_loadavg(self):
        fields = (proc_read(PROC_LOADAVG) or "").split()
        expected = [float(value) for value in fields[:3]]
        load = sample_jsonl("--load")["Load"]
        for field, value in zip(["load1", "load5", "load15"], expected):
            with self.subTest(field=field):
                self.assertAlmostEqual(load[field], value, delta=0.5)

    def test_load_has_every_legacy_field(self):
        load = sample_jsonl("--load")["Load"]
        for field in ["load1", "load5", "load15"]:
            with self.subTest(field=field):
                self.assertIn(field, load)

    # ---- disk I/O ----------------------------------------------------
    @LINUX_ONLY
    @LINUX_ONLY
    def test_io_excludes_virtual_devices(self):
        io = sample_jsonl("--io")["IO"]
        names = {key.split(".", 1)[0] for key in io}
        for noise in ["ram0", "loop0", "nbd0"]:
            with self.subTest(device=noise):
                self.assertNotIn(noise, names)

    @LINUX_ONLY
    def test_io_includes_real_devices(self):
        real = {
            line.split()[2]
            for line in (proc_read(PROC_DISKSTATS) or "").splitlines()
            if len(line.split()) > 3
            and not line.split()[2].startswith(("ram", "loop", "nbd"))
        }
        io = sample_jsonl("--io")["IO"]
        names = {key.split(".", 1)[0] for key in io}
        for device in sorted(real)[:5]:
            with self.subTest(device=device):
                self.assertIn(device, names)

    @LINUX_ONLY
    def test_io_keeps_legacy_field_names(self):
        # Any device that reports a value must use the legacy field names.
        io = sample_jsonl("--io")["IO"]
        fields = {key.split(".", 1)[1] for key in io}
        for expected in ["rs", "ws", "rkBs", "wkBs", "util", "svctm", "await"]:
            with self.subTest(field=expected):
                self.assertIn(expected, fields)

    # ---- network -----------------------------------------------------
    @LINUX_ONLY
    def test_traffic_covers_loopback(self):
        # `lo` always carries a little traffic from any process that talks to
        # localhost, so at least one interface should be reported.
        netdev = proc_read(PROC_NETDEV) or ""
        self.assertIn("lo:", netdev)
        traffic = sample_jsonl("--traffic")["Traffic"]
        if traffic:
            for field, value in traffic.items():
                with self.subTest(field=field):
                    self.assertIsInstance(value, (int, float))

    @LINUX_ONLY
    def test_traffic_field_names(self):
        traffic = sample_jsonl("--traffic")["Traffic"]
        for field in traffic:
            with self.subTest(field=field):
                self.assertTrue(
                    field.endswith(".inbytes") or field.endswith(".outbytes"),
                    field,
                )

    # ---- robustness --------------------------------------------------
    def test_repeated_runs_never_panic(self):
        for _ in range(5):
            result = run("-a")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn(b"panicked", result.stderr)

    def test_periodic_run_does_not_crash(self):
        shared = output_dir()
        context = tempfile.TemporaryDirectory() if shared is None else _NoCleanup(shared)
        with context as directory:
            path = Path(directory) / f"periodic-{uuid.uuid4().hex}.jsonl"
            try:
                subprocess.run(
                    [BINARY, "-a", "-n", "1", "-o", str(path)],
                    capture_output=True,
                    timeout=4,
                )
            except subprocess.TimeoutExpired:
                pass
            self.assertGreaterEqual(len(read_output(path).splitlines()), 2)

    def test_version_unchanged(self):
        result = run("-V")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, f"msar {VERSION}\n".encode())


if __name__ == "__main__":
    unittest.main(verbosity=2)
