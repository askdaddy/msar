//! Disk I/O backend: `/proc/diskstats` + `/sys/block/<name>/partition`
//! (issue #4).

use std::collections::BTreeMap;
use std::fs;

use crate::metric::{DeviceClass, Metric, MetricValues};
use crate::sample::Window;

/// One device's cumulative counters from `/proc/diskstats`.
///
/// Field layout follows `Documentation/iostats.txt`: reads, read merges, sectors
/// read, read ticks, writes, write merges, sectors written, write ticks, in
/// flight, I/O ticks, weighted I/O ticks.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct Counters {
    pub reads: u64,
    pub read_merges: u64,
    pub sectors_read: u64,
    pub read_ticks: u64,
    pub writes: u64,
    pub write_merges: u64,
    pub sectors_written: u64,
    pub write_ticks: u64,
    pub io_in_flight: u64,
    pub io_ticks: u64,
    pub weighted_io_ticks: u64,
}

/// A whole disk or partition plus its counters.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Device {
    pub name: String,
    pub class: DeviceClass,
    pub counters: Counters,
}

/// Whether a device should be reported at all.
///
/// `ram`/`loop`/`nbd` are kernel-internal and never useful to a user. LVM
/// (`dm-`) and software RAID (`md`) are kept because they are what people
/// actually run on, which the legacy `^\w*\d+` regex also excluded.
fn is_noise(name: &str) -> bool {
    name.starts_with("ram") || name.starts_with("loop") || name.starts_with("nbd")
}

/// Classify a device using `/sys/block/<name>/partition`.
///
/// A partition has that file (it contains its partition number); a whole disk
/// does not. This replaces the legacy `^\w*\d+` guess, which excluded whole
/// disks like `nvme0n1` and `mmcblk0`. An unreadable path means "whole disk",
/// which is the correct reading for every name without the file.
pub fn classify(name: &str) -> DeviceClass {
    let path = format!("/sys/block/{name}/partition");
    if fs::metadata(path).is_ok() {
        DeviceClass::Partition
    } else {
        DeviceClass::Disk
    }
}

/// Parse one `/proc/diskstats` line.
///
/// Returns `None` for noise devices and for lines with too few fields to carry
/// the counters, rather than indexing out of bounds.
pub fn parse_diskstats_line(line: &str) -> Option<Device> {
    let fields: Vec<&str> = line.split_whitespace().collect();
    let name = fields.get(2)?;
    if is_noise(name) {
        return None;
    }
    let numbers: Vec<u64> = fields
        .get(3..)
        .unwrap_or_default()
        .iter()
        .map(|field| field.parse::<u64>().ok())
        .collect::<Option<Vec<u64>>>()?;
    let at = |index: usize| numbers.get(index).copied().unwrap_or(0);
    Some(Device {
        name: (*name).to_owned(),
        class: classify(name),
        counters: Counters {
            reads: at(0),
            read_merges: at(1),
            sectors_read: at(2),
            read_ticks: at(3),
            writes: at(4),
            write_merges: at(5),
            sectors_written: at(6),
            write_ticks: at(7),
            io_in_flight: at(8),
            io_ticks: at(9),
            weighted_io_ticks: at(10),
        },
    })
}

/// Parse every relevant line of a `/proc/diskstats` text, keyed by name.
pub fn parse_diskstats(text: &str) -> BTreeMap<String, Device> {
    text.lines()
        .filter_map(parse_diskstats_line)
        .map(|device| (device.name.clone(), device))
        .collect()
}

/// Format a rate, keeping the legacy two-decimal text form as a number.
fn two_decimals(value: f64) -> Option<f64> {
    let rounded = (value * 100.0).round() / 100.0;
    rounded.is_finite().then_some(rounded)
}

/// Compute the legacy I/O field set from two samples.
///
/// `window` is the shared sampling duration, so every rate uses one timing
/// source (the legacy used two wall-clock reads per plugin).
pub fn compute(previous: &Counters, current: &Counters, window_secs: f64) -> MetricValues {
    let mut values = MetricValues::new();
    let rate = |previous: u64, current: u64| {
        crate::sample::rate(
            previous,
            current,
            std::time::Duration::from_secs_f64(window_secs),
        )
    };
    // Averages and latencies are shares: a counter that did not move in the
    // window is a real `0`, not "unavailable" (plan v2 step 7). Only a reset
    // sample (counter went backwards) makes them absent.
    let sectors = |previous: u64, current: u64| crate::linux::count_delta(previous, current);

    let reads = crate::sample::delta(previous.reads, current.reads);
    let writes = crate::sample::delta(previous.writes, current.writes);
    let read_io = reads.unwrap_or(0);
    let write_io = writes.unwrap_or(0);
    let total_io = read_io + write_io;

    let reads_per_sec = rate(previous.reads, current.reads);
    let writes_per_sec = rate(previous.writes, current.writes);
    let sectors_read_per_sec = rate(previous.sectors_read, current.sectors_read);
    let sectors_written_per_sec = rate(previous.sectors_written, current.sectors_written);

    values.insert(
        "rrqms".to_owned(),
        rate(previous.read_merges, current.read_merges),
    );
    values.insert(
        "wrqms".to_owned(),
        rate(previous.write_merges, current.write_merges),
    );
    values.insert("rs".to_owned(), reads_per_sec);
    values.insert("ws".to_owned(), writes_per_sec);
    values.insert("rsecs".to_owned(), sectors_read_per_sec);
    values.insert("wsecs".to_owned(), sectors_written_per_sec);
    values.insert(
        "rkBs".to_owned(),
        sectors_read_per_sec.and_then(|value| two_decimals(value / 2.0)),
    );
    values.insert(
        "wkBs".to_owned(),
        sectors_written_per_sec.and_then(|value| two_decimals(value / 2.0)),
    );

    // avgrq-sz: average sectors per I/O.
    let average_size = match (
        sectors(previous.sectors_read, current.sectors_read),
        sectors(previous.sectors_written, current.sectors_written),
    ) {
        (Some(read), Some(written)) if total_io > 0 => {
            Some((read + written) as f64 / total_io as f64)
        }
        _ if total_io > 0 => None,
        _ => None,
    };
    values.insert("avgrq-sz".to_owned(), average_size);

    // avgqu-sz: weighted I/O ticks per second, in thousands.
    values.insert(
        "avgqu-sz".to_owned(),
        rate(previous.weighted_io_ticks, current.weighted_io_ticks).map(|value| value / 1000.0),
    );

    let await_for = |ticks: u64, io: u64| match io {
        0 => None,
        _ => Some(ticks as f64 / io as f64),
    };
    values.insert(
        "r_await".to_owned(),
        await_for(
            sectors(previous.read_ticks, current.read_ticks).unwrap_or(0),
            read_io,
        )
        .and_then(two_decimals),
    );
    values.insert(
        "w_await".to_owned(),
        await_for(
            sectors(previous.write_ticks, current.write_ticks).unwrap_or(0),
            write_io,
        )
        .and_then(two_decimals),
    );
    let total_ticks = sectors(previous.read_ticks, current.read_ticks)
        .zip(sectors(previous.write_ticks, current.write_ticks))
        .map(|(read, written)| read + written);
    values.insert(
        "await".to_owned(),
        total_ticks
            .and_then(|ticks| await_for(ticks, total_io))
            .and_then(two_decimals),
    );

    // svctm: service time per completed I/O. The legacy divided by the read
    // delta only, overstating it up to threefold when writes dominate; the
    // denominator here is every completed I/O.
    let io_ticks = sectors(previous.io_ticks, current.io_ticks);
    values.insert(
        "svctm".to_owned(),
        io_ticks
            .and_then(|ticks| await_for(ticks, total_io))
            .and_then(two_decimals),
    );

    // %util: share of the window the device had I/O in flight, in percent.
    values.insert(
        "util".to_owned(),
        io_ticks
            .map(|ticks| ticks as f64 / (window_secs * 1000.0) * 100.0)
            .and_then(two_decimals),
    );

    values
}

pub struct Io;

impl Metric for Io {
    fn name(&self) -> &'static str {
        "Io"
    }

    fn sample(&self, window: &Window) -> MetricValues {
        let mut values = MetricValues::new();
        let Some(before) = fs::read_to_string("/proc/diskstats")
            .ok()
            .map(|text| parse_diskstats(&text))
        else {
            return values;
        };
        // The caller passes a fresh window for this module (plan v3), so its
        // elapsed time is the real span between the two snapshots.
        window.fill(crate::sample::DEFAULT_WINDOW);
        let window_secs = window.elapsed().as_secs_f64();
        let Some(after) = fs::read_to_string("/proc/diskstats")
            .ok()
            .map(|text| parse_diskstats(&text))
        else {
            return values;
        };

        // A device missing from either sample is skipped: it was added or
        // removed between samples, so there is no valid delta to report.
        for (name, device) in &after {
            let Some(previous) = before.get(name) else {
                continue;
            };
            let fields = compute(&previous.counters, &device.counters, window_secs);
            for (field, value) in fields {
                values.insert(format!("{name}.{field}"), value);
            }
        }
        values
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const REAL: &str = "   1       0 ram0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0\n\
   7       0 loop0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0\n\
 254       0 vda 66903 29155 6843730 32505 14603 16259 269392 31583 0 13928 67039 452 0 242312 327 6666 2623\n\
 254       1 vda1 66832 29155 6841370 32499 14603 16259 269392 31583 0 47408 64411 452 0 242312 327 0 0\n\
 254      16 vdb 601 0 545864 423 0 0 0 0 0 182 423 0 0 0 0 0 0\n";

    #[test]
    fn filters_kernel_noise_devices() {
        let devices = parse_diskstats(REAL);
        assert!(!devices.contains_key("ram0"));
        assert!(!devices.contains_key("loop0"));
        assert!(devices.contains_key("vda"));
        assert!(devices.contains_key("vda1"));
        assert!(devices.contains_key("vdb"));
    }

    #[test]
    fn parses_real_counters() {
        let devices = parse_diskstats(REAL);
        let vda = devices["vda"].counters;
        assert_eq!(vda.reads, 66_903);
        assert_eq!(vda.sectors_read, 6_843_730);
        assert_eq!(vda.writes, 14_603);
        assert_eq!(vda.io_ticks, 13_928);
    }

    #[test]
    fn svctm_uses_total_io_not_reads_only() {
        // 20_000 ticks over 300 completed I/O is 66.67 ms; the legacy divided
        // by the 100 read delta and reported 200.00 ms.
        let previous = Counters {
            reads: 1_000,
            writes: 2_000,
            sectors_read: 100_000,
            sectors_written: 200_000,
            read_ticks: 500_000,
            write_ticks: 500_000,
            io_ticks: 500_000,
            weighted_io_ticks: 900_000,
            ..Counters::default()
        };
        let current = Counters {
            reads: 1_100,
            writes: 2_200,
            sectors_read: 120_000,
            sectors_written: 240_000,
            read_ticks: 510_000,
            write_ticks: 510_000,
            io_ticks: 520_000,
            weighted_io_ticks: 960_000,
            ..Counters::default()
        };
        let values = compute(&previous, &current, 1.0);
        assert_eq!(values["svctm"], Some(66.67));
        let legacy = (current.io_ticks - previous.io_ticks) as f64 / 100.0;
        assert!(legacy > 100.0, "legacy would have been {legacy}");
    }

    #[test]
    fn counter_reset_yields_none_not_negative() {
        let previous = Counters {
            reads: 100,
            io_ticks: 500,
            ..Counters::default()
        };
        let current = Counters {
            reads: 50,
            io_ticks: 10,
            ..Counters::default()
        };
        let values = compute(&previous, &current, 1.0);
        for (field, value) in &values {
            if let Some(value) = value {
                assert!(value.is_finite() && *value >= 0.0, "{field}={value}");
            }
        }
    }

    #[test]
    fn zero_window_does_not_panic_or_produce_nan() {
        let previous = Counters::default();
        let current = Counters {
            reads: 10,
            ..Counters::default()
        };
        let values = compute(&previous, &current, 0.0);
        assert_eq!(values["rs"], None);
        for (field, value) in &values {
            assert!(
                value.map(|value| value.is_finite()).unwrap_or(true),
                "{field}"
            );
        }
    }

    #[test]
    fn short_line_is_skipped_not_panicking() {
        assert!(parse_diskstats_line("254 0 vda 1 2").is_some());
        assert!(parse_diskstats_line("only-name").is_none());
        assert!(parse_diskstats_line("").is_none());
        assert!(parse_diskstats_line("254 0 vda 1 x 3").is_none());
    }
}
