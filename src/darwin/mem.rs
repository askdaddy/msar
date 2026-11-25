//! Memory backend: `sysctl hw.memsize` and `vm_stat` (issue #5).
//!
//! `vm_stat` reports page counts, so every value is scaled by
//! `hw.pagesize`. macOS has no `Buffers` and no `MemAvailable`, so those
//! legacy fields stay unavailable rather than reporting a fabricated zero.

use crate::metric::{Metric, MetricValues, Unit};
use crate::sample::Window;

/// Page counts from `vm_stat`, in pages.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct Pages {
    pub free: u64,
    pub active: u64,
    pub inactive: u64,
    pub wired: u64,
}

/// Parse the `Pages free: 7041.` style lines of `vm_stat`.
///
/// The key is everything before the first `:`, matched exactly, so
/// `Pages free` cannot be confused with a longer key.
pub fn parse_pages(text: &str) -> Pages {
    let mut pages = Pages::default();
    for line in text.lines() {
        let Some((key, rest)) = line.split_once(':') else {
            continue;
        };
        let Some(value) = rest.trim().trim_end_matches('.').parse::<u64>().ok() else {
            continue;
        };
        match key.trim() {
            "Pages free" => pages.free = value,
            "Pages active" => pages.active = value,
            "Pages inactive" => pages.inactive = value,
            "Pages wired down" => pages.wired = value,
            _ => {}
        }
    }
    pages
}

pub struct Mem;

impl Mem {
    /// Convert a page count to KiB using the reported page size.
    fn kib(pages: u64, page_size: u64) -> u64 {
        pages.saturating_mul(page_size) / 1024
    }
}

impl Metric for Mem {
    fn name(&self) -> &'static str {
        "Mem"
    }

    fn sample(&self, _window: &Window) -> MetricValues {
        let mut values = MetricValues::new();
        for field in ["total", "free", "buffers", "cached", "available"] {
            values.insert(field.to_owned(), None);
        }

        // Memory is a snapshot; no sampling window is needed.
        let Some(page_size) = super::command("sysctl", &["-n", "hw.pagesize"])
            .and_then(|text| text.trim().parse::<u64>().ok())
            .filter(|size| *size > 0)
        else {
            return values;
        };
        let Some(total_bytes) = super::command("sysctl", &["-n", "hw.memsize"])
            .and_then(|text| text.trim().parse::<u64>().ok())
        else {
            return values;
        };
        let Some(stats) = super::command("vm_stat", &[]) else {
            return values;
        };
        let pages = parse_pages(&stats);

        // `cached` is reusable memory (active + inactive); `available` is what
        // a new allocation can take without paging (free + inactive).
        let kib = |pages: u64| Self::kib(pages, page_size);
        for (field, value) in [
            ("total", total_bytes / 1024),
            ("free", kib(pages.free)),
            ("cached", kib(pages.active) + kib(pages.inactive)),
            ("available", kib(pages.free) + kib(pages.inactive)),
        ] {
            let quantity = crate::metric::Quantity::new(value as f64, Unit::KiB);
            values.insert(field.to_owned(), Some(quantity.value));
        }
        // `buffers` stays None: macOS has no such counter.
        values
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const REAL: &str = "Mach Virtual Memory Statistics: (page size of 16384 bytes)\n\
Pages free:                                    7041.\n\
Pages active:                                185433.\n\
Pages inactive:                              183980.\n\
Pages speculative:                              639.\n\
Pages wired down:                            253180.\n\
Pages purgeable:                                  4.\n";

    #[test]
    fn parses_real_sample() {
        let pages = parse_pages(REAL);
        assert_eq!(pages.free, 7_041);
        assert_eq!(pages.active, 185_433);
        assert_eq!(pages.inactive, 183_980);
        assert_eq!(pages.wired, 253_180);
    }

    #[test]
    fn trailing_period_is_stripped() {
        assert_eq!(parse_pages("Pages free: 1.\n").free, 1);
    }

    #[test]
    fn unknown_and_malformed_lines_are_ignored() {
        let pages = parse_pages("Pages speculative: 639.\nBogus\nPages free: x\n");
        assert_eq!(pages, Pages::default());
    }

    #[test]
    fn page_counts_scale_to_kib() {
        // 7041 pages of 16 KiB is 112656 KiB, not 7041.
        assert_eq!(Mem::kib(7_041, 16_384), 112_656);
    }

    #[test]
    fn zero_page_size_does_not_panic() {
        assert_eq!(Mem::kib(7_041, 0), 0);
    }
}
