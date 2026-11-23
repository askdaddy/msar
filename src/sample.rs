#![allow(dead_code)] // contract for #4/#5; this binary does not consume it yet
//! Shared sampling window (issue #3).
//!
//! One round of sampling takes a single monotonic baseline; every module diffs
//! against it. Wall-clock time is never used for arithmetic, only for output.

use std::thread;
use std::time::{Duration, Instant};

/// Default self-sampling window for a single-shot CPU round.
///
/// The legacy 50 ms window quantised too coarsely on an idle machine; 250 ms is
/// still below human perception while giving counters time to move.
pub const DEFAULT_WINDOW: Duration = Duration::from_millis(250);

/// Monotonic baseline of one sampling round.
#[derive(Debug, Clone, Copy)]
pub struct Window {
    start: Instant,
}

impl Window {
    pub fn start() -> Self {
        Self {
            start: Instant::now(),
        }
    }

    /// Elapsed time since the round began.
    pub fn elapsed(&self) -> Duration {
        self.start.elapsed()
    }

    /// Wait until the shared window has been open for `duration`.
    ///
    /// Only the first caller sleeps in practice; later callers see the window
    /// already elapsed and return immediately, so modules cannot drift apart by
    /// each sleeping on their own.
    pub fn fill(&self, duration: Duration) {
        if let Some(remaining) = duration.checked_sub(self.start.elapsed()) {
            thread::sleep(remaining);
        }
    }
}

/// Counter difference between two samples.
///
/// Returns `None` when the counter went backwards (device hot-plug, counter
/// reset) or did not move at all. Callers must render `None` as unavailable
/// rather than dividing by zero or emitting a negative value.
pub fn delta(previous: u64, current: u64) -> Option<u64> {
    let difference = current.checked_sub(previous)?;
    if difference == 0 {
        None
    } else {
        Some(difference)
    }
}

/// Rate of `delta` over `window`; `None` propagates and never yields NaN/Inf.
pub fn rate(previous: u64, current: u64, window: Duration) -> Option<f64> {
    let steps = delta(previous, current)?;
    let seconds = window.as_secs_f64();
    if seconds > 0.0 {
        Some(steps as f64 / seconds)
    } else {
        None
    }
}

/// Percentage share of `part` within `total` counters; `None` when total is zero.
pub fn share(part: u64, total: u64) -> Option<f64> {
    if total == 0 {
        None
    } else {
        Some(part as f64 / total as f64 * 100.0)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn delta_rejects_backwards_counter() {
        assert_eq!(delta(10, 5), None);
    }

    #[test]
    fn delta_rejects_no_movement() {
        assert_eq!(delta(5, 5), None);
    }

    #[test]
    fn delta_accepts_forward_movement() {
        assert_eq!(delta(5, 10), Some(5));
    }

    #[test]
    fn rate_propagates_unavailable() {
        assert_eq!(rate(10, 5, Duration::from_secs(1)), None);
        assert_eq!(rate(0, 10, Duration::from_secs(2)), Some(5.0));
    }

    #[test]
    fn rate_rejects_zero_window() {
        assert_eq!(rate(0, 10, Duration::ZERO), None);
    }

    #[test]
    fn share_rejects_zero_total() {
        assert_eq!(share(1, 0), None);
        assert_eq!(share(1, 4), Some(25.0));
    }
}
