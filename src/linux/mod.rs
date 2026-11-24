//! Linux `/proc` backends (issue #4).
//!
//! Every reader follows the same shape: parse a pure function, then have a thin
//! `Metric` implementation read the file and diff against the shared
//! [`crate::sample::Window`]. Keeping parsing pure is what lets the real
//! samples from issue #4 be tested without a Linux host.

mod cpu;
mod io;
mod load;
mod mem;
mod traffic;

pub use cpu::Cpu;
pub use io::Io;
pub use load::Load;
pub use mem::Mem;
pub use traffic::Traffic;

/// Whether `/proc` exists at all, used to keep the macOS path cheap.
pub fn available() -> bool {
    std::path::Path::new("/proc/stat").exists()
}

/// Difference between two classification counters.
///
/// This is deliberately **not** [`crate::sample::delta`]: for a share-type
/// counter a repeated reading is a legitimate `0`, whereas `sample::delta`
/// reports `None` to protect rate division. Only a lost update (counter reset,
/// device hot-plug) is unavailable here.
///
/// Plan v2 step 4a: rates keep using `sample::delta`, shares use this.
pub fn count_delta(previous: u64, current: u64) -> Option<u64> {
    current.checked_sub(previous)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn zero_increment_is_a_reading_not_unavailable() {
        assert_eq!(count_delta(1116, 1116), Some(0));
    }

    #[test]
    fn forward_increment_is_the_difference() {
        assert_eq!(count_delta(239_122, 239_124), Some(2));
    }

    #[test]
    fn backwards_counter_is_unavailable() {
        assert_eq!(count_delta(100, 50), None);
    }
}
