//! Disk I/O backend: `iostat -Id` (issue #5).
//!
//! `iostat -Id` prints a header column line, a units line, then one cumulative
//! row per disk followed by per-interval rows. Only the first data row carries
//! cumulative totals (measured: `xfrs` 28 080 867 in the first row against
//! 1 107 in the next), so it is the only row that can be diffed.
//!
//! macOS reports reads and writes together, and exposes no utilisation,
//! latency or queue counters, so those legacy fields stay unavailable instead
//! of being filled with a fabricated zero.

use std::collections::BTreeMap;

use crate::metric::{Metric, MetricValues};
use crate::sample::Window;

/// Cumulative per-disk counters from the first data row.
#[derive(Debug, Clone, Copy, Default, PartialEq)]
pub struct Counters {
    /// `xfrs`: completed transfers.
    pub transfers: u64,
    /// `MB`: megabytes transferred.
    pub megabytes: f64,
}

/// Parse the **first** data row of `iostat -Id`.
///
/// The header line names the disks; the units line starts with `KB/t`; the row
/// after it holds the cumulative values, three columns per disk. Later rows are
/// interval values and must not be used, because diffing them would mix a
/// cumulative reading with an interval one.
pub fn parse_iostat(text: &str) -> BTreeMap<String, Counters> {
    let mut lines = text.lines();
    let Some(names_line) = lines.next() else {
        return BTreeMap::new();
    };
    let names: Vec<&str> = names_line.split_whitespace().collect();
    if names.is_empty() {
        return BTreeMap::new();
    }

    // Skip the units line, then read exactly one data row.
    let Some(values_line) = lines.nth(1) else {
        return BTreeMap::new();
    };
    let values: Vec<&str> = values_line.split_whitespace().collect();

    let mut disks = BTreeMap::new();
    for (index, name) in names.iter().enumerate() {
        let base = index * 3;
        let (Some(transfers), Some(megabytes)) = (
            values
                .get(base + 1)
                .and_then(|field| field.parse::<u64>().ok()),
            values
                .get(base + 2)
                .and_then(|field| field.parse::<f64>().ok()),
        ) else {
            continue;
        };
        disks.insert(
            (*name).to_owned(),
            Counters {
                transfers,
                megabytes,
            },
        );
    }
    disks
}

pub struct Io;

/// Megabyte rate between two float counters.
///
/// Returns `None` for a backwards step (a reset) or a zero window, matching
/// [`crate::sample::rate`] without changing its integer-only signature.
fn megabytes_per_second(previous: f64, current: f64, window_secs: f64) -> Option<f64> {
    if window_secs <= 0.0 || current < previous || current == previous {
        return None;
    }
    let rate = (current - previous) / window_secs;
    rate.is_finite().then_some(rate)
}

impl Io {
    /// Build the reported field set for one disk from two samples.
    ///
    /// `xfrs` and `MB` are the only cumulative counters, so they map to the
    /// transfer rate and the throughput. Reads and writes are not separable on
    /// macOS, so `rs`/`ws` and `rkBs`/`wkBs` both carry the combined rate;
    /// the remaining legacy fields are unavailable.
    fn values(previous: &Counters, current: &Counters, window_secs: f64) -> MetricValues {
        let mut values = MetricValues::new();
        let duration = std::time::Duration::from_secs_f64(window_secs);

        let transfers = crate::sample::rate(previous.transfers, current.transfers, duration);
        // MB is a float counter, so the shared integer `rate` cannot be reused.
        let megabytes = megabytes_per_second(previous.megabytes, current.megabytes, window_secs);
        // MB/s to KiB/s: 1024 KiB in a MiB.
        let throughput = megabytes.map(|value| value * 1024.0);

        for field in ["rs", "ws"] {
            values.insert(field.to_owned(), transfers);
        }
        for field in ["rkBs", "wkBs"] {
            values.insert(field.to_owned(), throughput);
        }
        // No cumulative source for these, so they must not claim a zero.
        for field in [
            "rrqms", "wrqms", "rsecs", "wsecs", "avgrq-sz", "avgqu-sz", "r_await", "w_await",
            "await", "svctm", "util",
        ] {
            values.insert(field.to_owned(), None);
        }
        values
    }
}

impl Metric for Io {
    fn name(&self) -> &'static str {
        "Io"
    }

    fn sample(&self, window: &Window) -> MetricValues {
        let mut values = MetricValues::new();

        let read = || super::command("iostat", &["-Id"]).map(|text| parse_iostat(&text));
        let Some(before) = read() else {
            return values;
        };
        window.fill(crate::sample::DEFAULT_WINDOW);
        let window_secs = window.elapsed().as_secs_f64();
        let Some(after) = read() else {
            return values;
        };

        // A disk missing from either read was added or removed between them.
        for (name, disk) in &after {
            let Some(previous) = before.get(name) else {
                continue;
            };
            let fields = Self::values(previous, disk, window_secs);
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

    const REAL: &str = "              disk0               disk4               disk7\n\
    KB/t xfrs   MB     KB/t xfrs   MB     KB/t xfrs   MB\n\
   23.10 26261525 592380.88    24.35 1484203 35292.64     4.31 2384 10.04\n\
   19.78 535 10.33     0.00   0  0.00     0.00   0  0.00\n";

    #[test]
    fn parses_the_first_cumulative_row() {
        let disks = parse_iostat(REAL);
        assert_eq!(disks["disk0"].transfers, 26_261_525);
        assert!((disks["disk0"].megabytes - 592_380.88).abs() < 0.01);
        assert_eq!(disks["disk4"].transfers, 1_484_203);
    }

    #[test]
    fn first_row_differs_from_the_interval_row() {
        // The point of reading only the first row: the second row is an
        // interval count (535) and mixing them would corrupt the delta.
        let disks = parse_iostat(REAL);
        assert!(disks["disk0"].transfers > 1_000_000);
        assert_ne!(disks["disk0"].transfers, 535);
    }

    #[test]
    fn header_only_input_is_empty() {
        assert!(parse_iostat("  disk0\ndisk4\n").is_empty());
        assert!(parse_iostat("").is_empty());
    }

    #[test]
    fn unavailable_fields_stay_none() {
        let previous = Counters {
            transfers: 100,
            megabytes: 50.0,
        };
        let current = Counters {
            transfers: 200,
            megabytes: 100.0,
        };
        let values = Io::values(&previous, &current, 1.0);
        for field in ["util", "await", "svctm", "avgrq-sz", "avgqu-sz", "rsecs"] {
            assert_eq!(values[field], None, "{field}");
        }
    }

    #[test]
    fn throughput_converts_megabytes_to_kib() {
        let previous = Counters {
            transfers: 0,
            megabytes: 0.0,
        };
        let current = Counters {
            transfers: 10,
            megabytes: 2.0,
        };
        let values = Io::values(&previous, &current, 1.0);
        assert_eq!(values["rs"], Some(10.0));
        assert_eq!(values["rkBs"], Some(2048.0));
    }

    #[test]
    fn counter_reset_yields_none_not_negative() {
        let previous = Counters {
            transfers: 500,
            megabytes: 900.0,
        };
        let current = Counters {
            transfers: 10,
            megabytes: 1.0,
        };
        let values = Io::values(&previous, &current, 1.0);
        for (field, value) in &values {
            assert!(
                value.is_none() || value.is_some_and(|value: f64| value >= 0.0),
                "{field}"
            );
        }
    }

    #[test]
    fn zero_window_does_not_panic() {
        let previous = Counters::default();
        let current = Counters {
            transfers: 10,
            megabytes: 1.0,
        };
        let values = Io::values(&previous, &current, 0.0);
        assert_eq!(values["rs"], None);
    }
}
