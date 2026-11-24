//! Memory backend: `/proc/meminfo` (issue #4).

use std::collections::BTreeMap;
use std::fs;

use crate::metric::{Metric, MetricValues, Unit};
use crate::sample::Window;

/// Memory values in KiB, matching the kernel's native unit.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct Memory {
    pub total: Option<u64>,
    pub free: Option<u64>,
    pub buffers: Option<u64>,
    pub cached: Option<u64>,
    /// Present only on kernels with `MemAvailable` (2.6.27+ in practice).
    pub available: Option<u64>,
}

/// Parse `/proc/meminfo` by **exact key**, never by substring.
///
/// Substring matching is what bound `Cached` to `SwapCached` and `Active` to
/// `Active(anon)`; the keys here are the text before the first `:`.
pub fn parse_meminfo(text: &str) -> Memory {
    let mut map: BTreeMap<&str, u64> = BTreeMap::new();
    for line in text.lines() {
        let Some((key, rest)) = line.split_once(':') else {
            continue;
        };
        let Some(value) = rest
            .split_whitespace()
            .next()
            .and_then(|v| v.parse::<u64>().ok())
        else {
            continue;
        };
        map.insert(key.trim(), value);
    }
    Memory {
        total: map.get("MemTotal").copied(),
        free: map.get("MemFree").copied(),
        buffers: map.get("Buffers").copied(),
        cached: map.get("Cached").copied(),
        available: map.get("MemAvailable").copied(),
    }
}

pub struct Mem;

impl Metric for Mem {
    fn name(&self) -> &'static str {
        "Mem"
    }

    fn sample(&self, _window: &Window) -> MetricValues {
        let mut values = MetricValues::new();
        for field in ["total", "free", "buffers", "cached", "available"] {
            values.insert(field.to_owned(), None);
        }

        // Memory is a snapshot, not a rate, so no window is needed.
        let Some(text) = fs::read_to_string("/proc/meminfo").ok() else {
            return values;
        };
        let memory = parse_meminfo(&text);

        for (field, value) in [
            ("total", memory.total),
            ("free", memory.free),
            ("buffers", memory.buffers),
            ("cached", memory.cached),
            ("available", memory.available),
        ] {
            let quantity = value.map(|kib| crate::metric::Quantity::new(kib as f64, Unit::KiB));
            values.insert(field.to_owned(), quantity.map(|quantity| quantity.value));
        }
        values
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const REAL: &str = "MemTotal:        6064952 kB\n\
MemFree:          160028 kB\n\
MemAvailable:    2593484 kB\n\
Buffers:          244292 kB\n\
Cached:          1955860 kB\n\
SwapCached:            0 kB\n\
Active:          4186832 kB\n\
Inactive:        1082000 kB\n\
Active(anon):    2943016 kB\n\
Inactive(anon):   153724 kB\n";

    #[test]
    fn parses_real_sample() {
        let memory = parse_meminfo(REAL);
        assert_eq!(memory.total, Some(6_064_952));
        assert_eq!(memory.free, Some(160_028));
        assert_eq!(memory.buffers, Some(244_292));
        assert_eq!(memory.cached, Some(1_955_860));
        assert_eq!(memory.available, Some(2_593_484));
    }

    #[test]
    fn exact_key_beats_substring_when_swapcached_comes_first() {
        // This ordering is what makes the criterion able to tell the two
        // implementations apart: substring matching would return SwapCached.
        let text = "MemTotal: 100 kB\nSwapCached: 7 kB\nCached: 50 kB\nActive(anon): 30 kB\nActive: 90 kB\n";
        let memory = parse_meminfo(text);
        assert_eq!(memory.cached, Some(50));
        assert_eq!(memory.total, Some(100));
    }

    #[test]
    fn missing_memavailable_is_none_but_others_work() {
        let text = "MemTotal: 100 kB\nMemFree: 40 kB\nBuffers: 10 kB\nCached: 20 kB\n";
        let memory = parse_meminfo(text);
        assert_eq!(memory.available, None);
        assert_eq!(memory.total, Some(100));
        assert_eq!(memory.cached, Some(20));
    }

    #[test]
    fn malformed_lines_are_skipped() {
        let text = "MemTotal: not-a-number kB\nMemFree: 40\nBogus line\n";
        let memory = parse_meminfo(text);
        assert_eq!(memory.total, None);
        assert_eq!(memory.free, Some(40));
    }
}
