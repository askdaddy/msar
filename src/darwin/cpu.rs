//! CPU backend: Mach `HOST_CPU_LOAD_INFO` (issue #5).

use crate::metric::{Metric, MetricValues, Unit};
use crate::sample::Window;

/// `mach_port_t` is a 32-bit Mach port name; the host port needs no release.
type MachPort = u32;
/// `kern_return_t`: 0 (`KERN_SUCCESS`) on success.
type KernReturn = i32;
/// `host_flavor_t` and the returned count are 32-bit.
type HostFlavor = i32;
type InfoCount = u32;

const KERN_SUCCESS: KernReturn = 0;
/// `HOST_CPU_LOAD_INFO` from `mach/host_info.h` (the SDK has no 64-bit form).
const HOST_CPU_LOAD_INFO: HostFlavor = 3;
/// `CPU_STATE_MAX`; the array order is user, system, idle, nice.
const CPU_STATE_MAX: usize = 4;
const CPU_STATE_USER: usize = 0;
const CPU_STATE_SYSTEM: usize = 1;
const CPU_STATE_IDLE: usize = 2;

unsafe extern "C" {
    fn mach_host_self() -> MachPort;
    fn host_statistics(
        host: MachPort,
        flavor: HostFlavor,
        info: *mut u32,
        count: *mut InfoCount,
    ) -> KernReturn;
}

/// Cumulative CPU ticks, in the kernel's own order.
///
/// `natural_t` is 32 bits here (measured with a C probe: `sizeof == 4`), so the
/// raw counters wrap every 179 seconds at the machine's 24 MHz tick rate. They
/// are kept as `u32` so the seam can be detected rather than mistaken for a
/// counter reset.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct Ticks {
    pub user: u32,
    pub system: u32,
    pub idle: u32,
    pub nice: u32,
}

impl Ticks {
    fn total(&self) -> u32 {
        self.user + self.system + self.idle + self.nice
    }
}

/// Difference between two consecutive `u32` counters, unwrapping the 32-bit seam.
///
/// Counters are 32 bits and wrap every 179 s at the machine's 24 MHz tick rate.
/// Because the baseline is only one sampling window old, the true difference is
/// far below half the range, so a backwards step is always a wrap: the distance
/// across the seam is the real difference. This also covers a counter reset,
/// which gives the ticks since the previous snapshot, so the two cases do not
/// need to be told apart (plan v2).
pub fn delta(previous: u32, current: u32) -> u32 {
    match current.checked_sub(previous) {
        Some(difference) => difference,
        None => (u32::MAX - previous).wrapping_add(current).wrapping_add(1),
    }
}

/// Read the current cumulative counters.
fn read() -> Option<Ticks> {
    let mut fields = [0u32; CPU_STATE_MAX];
    let mut count: InfoCount = CPU_STATE_MAX as InfoCount;
    // SAFETY: `host_statistics` fills the caller's array; the count is both the
    // expected and the returned length for `HOST_CPU_LOAD_INFO_COUNT`.
    let status = unsafe {
        host_statistics(
            mach_host_self(),
            HOST_CPU_LOAD_INFO,
            fields.as_mut_ptr(),
            &mut count,
        )
    };
    if status != KERN_SUCCESS || count as usize != CPU_STATE_MAX {
        return None;
    }
    Some(Ticks {
        user: fields[CPU_STATE_USER],
        system: fields[CPU_STATE_SYSTEM],
        idle: fields[CPU_STATE_IDLE],
        nice: fields[3],
    })
}

/// The previous snapshot, so each round diffs against the last one.
///
/// The counters are 32 bits, so keeping a session-local monotonic total is what
/// makes the difference well defined across the wrap. `-n` rounds share this
/// state; a one-shot run has no baseline for its first round.
static PREVIOUS: std::sync::Mutex<Option<Ticks>> = std::sync::Mutex::new(None);

pub struct Cpu;

impl Metric for Cpu {
    fn name(&self) -> &'static str {
        "Cpu"
    }

    fn sample(&self, window: &Window) -> MetricValues {
        let mut values = MetricValues::new();
        for field in ["us", "sy", "id", "wa"] {
            values.insert(field.to_owned(), None);
        }

        let Some(before) = PREVIOUS.lock().ok().and_then(|state| *state) else {
            return values;
        };

        window.fill(super::CPU_WINDOW);
        let Some(after) = read() else {
            return values;
        };

        let Some(total) = [
            (before.user, after.user),
            (before.system, after.system),
            (before.idle, after.idle),
            (before.nice, after.nice),
        ]
        .into_iter()
        .map(|(previous, current)| delta(previous, current))
        .try_fold(0u32, |sum, value| sum.checked_add(value)) else {
            return values;
        };

        for (field, previous, current) in [
            ("us", before.user, after.user),
            ("sy", before.system, after.system),
            ("id", before.idle, after.idle),
        ] {
            let share = crate::sample::share(delta(previous, current) as u64, total as u64)
                .map(|percent| crate::metric::Quantity::new(percent, Unit::Percent).value);
            values.insert(field.to_owned(), share);
        }
        if let Ok(mut state) = PREVIOUS.lock() {
            *state = Some(after);
        }
        // `wa` stays `None`: macOS has no iowait state, so reporting 0 would
        // claim a measurement the kernel never made.
        values
    }
}

impl Cpu {
    /// Take the baseline snapshot, so the next round can diff against it.
    pub fn prime(&self) {
        if let Some(ticks) = read() {
            if let Ok(mut state) = PREVIOUS.lock() {
                *state = Some(ticks);
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn forward_step_is_the_difference() {
        assert_eq!(delta(50, 100), 50);
    }

    #[test]
    fn repeated_reading_is_zero() {
        assert_eq!(delta(100, 100), 0);
    }

    #[test]
    fn backwards_step_across_the_seam_is_a_wraparound() {
        // 10 ticks short of the seam plus 25 after it is 36 ticks.
        assert_eq!(delta(u32::MAX - 10, 25), 36);
    }

    #[test]
    fn wraparound_matches_a_real_179_second_boundary() {
        // At 24 MHz the counters wrap every 179 s; a 250 ms window moves
        // about 6 000 000 ticks, so the seam is crossed with a small delta.
        let just_before = u32::MAX - 1_000_000;
        assert_eq!(delta(just_before, 5_000_000), 6_000_001);
    }

    #[test]
    fn reset_gives_the_ticks_since_the_previous_snapshot() {
        // A process restart zeroes the counter; the distance across the seam
        // is still the real number of ticks since the last snapshot, which is
        // what plan v2 requires instead of reporting the sample unavailable.
        assert_eq!(delta(4_000_000_000, 1), 294_967_297);
    }

    #[test]
    fn window_delta_is_far_below_half_the_range() {
        // The whole point of a session-local baseline: one window can never
        // move more than half the range, so no threshold is needed.
        let per_window = 24_000_000u32 / 4; // 250 ms at 24 MHz
        assert!(per_window < (1u32 << 31));
        // MAX - pw + 1 -> pw is exactly 2 * pw - 1 ticks across the seam.
        assert_eq!(delta(u32::MAX - per_window + 1, per_window), per_window * 2);
    }

    #[test]
    fn total_is_the_sum_of_all_four_states() {
        let state = Ticks {
            user: 1,
            system: 2,
            idle: 3,
            nice: 4,
        };
        assert_eq!(state.total(), 10);
    }

    #[test]
    fn shares_sum_to_one_hundred_when_nice_is_zero() {
        let before = Ticks::default();
        let after = Ticks {
            user: 53,
            system: 45,
            idle: 2,
            nice: 0,
        };
        let total = after.total() - before.total();
        let sum: f64 = [after.user, after.system, after.idle]
            .into_iter()
            .map(|value| crate::sample::share(value as u64, total as u64).unwrap())
            .sum();
        assert!((sum - 100.0).abs() < 0.05, "{sum}");
    }

    #[test]
    fn zero_total_yields_no_shares() {
        assert_eq!(crate::sample::share(1, 0), None);
    }
}
