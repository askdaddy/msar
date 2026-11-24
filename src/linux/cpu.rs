//! CPU backend: `/proc/stat` (issue #4).

use std::collections::BTreeMap;
use std::fs;

use crate::metric::{Metric, MetricValues, Unit};
use crate::sample::Window;

/// One `cpu`/`cpuN` counter set from `/proc/stat`.
///
/// Field order is fixed by the kernel: user, nice, system, idle, iowait, irq,
/// softirq, steal, guest, guest_nice. Kernels without virtualisation support
/// stop before `guest`, so missing fields are zero.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct Counters {
    pub user: u64,
    pub nice: u64,
    pub system: u64,
    pub idle: u64,
    pub iowait: u64,
    pub irq: u64,
    pub softirq: u64,
    pub steal: u64,
    pub guest: u64,
    pub guest_nice: u64,
}

impl Counters {
    /// Total busy/idle time, **excluding** `guest` and `guest_nice`.
    ///
    /// The kernel already accounts guest time inside `user`/`nice`
    /// (`fs/proc/stat.c`), so adding it again double-counts and skews every
    /// percentage. This is the fix for the legacy `total` computation.
    pub fn total(&self) -> u64 {
        self.user
            + self.nice
            + self.system
            + self.idle
            + self.iowait
            + self.irq
            + self.softirq
            + self.steal
    }

    fn from_fields(fields: &[u64]) -> Self {
        let at = |index: usize| fields.get(index).copied().unwrap_or(0);
        Self {
            user: at(0),
            nice: at(1),
            system: at(2),
            idle: at(3),
            iowait: at(4),
            irq: at(5),
            softirq: at(6),
            steal: at(7),
            guest: at(8),
            guest_nice: at(9),
        }
    }
}

/// Parse one `/proc/stat` line into `(label, counters)`.
///
/// Returns `None` for non-CPU lines (`intr`, `ctxt`, `btime`, ...) and for CPU
/// lines whose counters are not all numeric.
pub fn parse_stat_line(line: &str) -> Option<(String, Counters)> {
    let mut fields = line.split_whitespace();
    let label = fields.next()?;
    if !label.starts_with("cpu") {
        return None;
    }
    let mut values = Vec::new();
    for field in fields {
        // A malformed counter means the whole line cannot be trusted.
        values.push(field.parse::<u64>().ok()?);
    }
    Some((label.to_owned(), Counters::from_fields(&values)))
}

/// Parse every CPU line in a `/proc/stat` text.
pub fn parse_stat(text: &str) -> BTreeMap<String, Counters> {
    text.lines().filter_map(parse_stat_line).collect()
}

pub struct Cpu;

/// A reported field and the counter it is derived from.
type Field = (&'static str, fn(&Counters) -> u64);

impl Cpu {
    /// Expected field labels, matching the legacy `Cpu` module keys.
    fn fields() -> [Field; 4] {
        [
            ("us", |counters| counters.user),
            ("sy", |counters| counters.system),
            ("id", |counters| counters.idle),
            ("wa", |counters| counters.iowait),
        ]
    }
}

impl Metric for Cpu {
    fn name(&self) -> &'static str {
        "Cpu"
    }

    fn sample(&self, window: &Window) -> MetricValues {
        let mut values = MetricValues::new();
        for (field, _) in Self::fields() {
            values.insert(field.to_owned(), None);
        }

        let Some(before) = fs::read_to_string("/proc/stat")
            .ok()
            .map(|text| parse_stat(&text))
        else {
            return values;
        };

        window.fill(crate::sample::DEFAULT_WINDOW);

        let Some(after) = fs::read_to_string("/proc/stat")
            .ok()
            .map(|text| parse_stat(&text))
        else {
            return values;
        };

        // Prefer the aggregate line; fall back to the first CPU if absent.
        let label = if after.contains_key("cpu") {
            "cpu"
        } else {
            match after.keys().next() {
                Some(label) => label.as_str(),
                None => return values,
            }
        };
        let (Some(previous), Some(current)) = (before.get(label), after.get(label)) else {
            return values;
        };

        // Shares use `count_delta`, so a category that did not move in this
        // window reports 0% instead of becoming unavailable (plan v2 step 3).
        let Some(total) = crate::linux::count_delta(previous.total(), current.total()) else {
            return values;
        };

        for (field, pick) in Self::fields() {
            let share = crate::linux::count_delta(pick(previous), pick(current))
                .and_then(|part| crate::sample::share(part, total))
                .map(|percent| crate::metric::Quantity::new(percent, Unit::Percent))
                .map(|quantity| quantity.value);
            values.insert(field.to_owned(), share);
        }
        values
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const REAL: &str = "cpu  217758 0 123667 10297666 1067 0 50130 0 0 0\n\
cpu0 59325 0 32365 2564727 423 0 24049 0 0 0\n\
intr 57042057 0 888017\n\
ctxt 90766004\n\
btime 1795395044\n";

    #[test]
    fn parses_real_aggregate_line() {
        let counters = parse_stat(REAL);
        let aggregate = counters["cpu"];
        assert_eq!(aggregate.user, 217758);
        assert_eq!(aggregate.system, 123667);
        assert_eq!(aggregate.idle, 10297666);
        assert_eq!(aggregate.iowait, 1067);
        assert_eq!(aggregate.softirq, 50130);
    }

    #[test]
    fn ignores_non_cpu_lines() {
        let counters = parse_stat(REAL);
        assert_eq!(counters.len(), 2);
        assert!(counters.contains_key("cpu0"));
        assert!(!counters.contains_key("intr"));
    }

    #[test]
    fn missing_guest_fields_are_zero() {
        // Attempt to parse a short line: eight counters, no guest/guest_nice.
        let (label, counters) = parse_stat_line("cpu  100 0 50 1000 10 0 5 0").unwrap();
        assert_eq!(label, "cpu");
        assert_eq!(counters.steal, 0);
        assert_eq!(counters.guest, 0);
        assert_eq!(counters.total(), 1165);
    }

    #[test]
    fn malformed_counter_is_rejected() {
        assert!(parse_stat_line("cpu  1 2 x 4").is_none());
    }

    #[test]
    fn total_excludes_guest() {
        let counters =
            Counters::from_fields(&[100_000, 200, 30_000, 500_000, 1_000, 0, 500, 0, 40_000, 0]);
        // Legacy summed guest too and produced 671_700.
        assert_eq!(counters.total(), 631_700);
    }

    #[test]
    fn zero_increment_category_reports_zero_percent() {
        // A real 250 ms window often leaves `iowait` unchanged; that is a
        // legitimate 0%, not "unavailable" (plan v2 step 3).
        let previous = Counters::from_fields(&[100, 0, 50, 1000, 1116, 0, 5, 0]);
        let current = Counters::from_fields(&[102, 0, 53, 1098, 1116, 0, 5, 0]);
        let total = crate::linux::count_delta(previous.total(), current.total()).unwrap();
        let share = crate::linux::count_delta(previous.iowait, current.iowait)
            .and_then(|part| crate::sample::share(part, total));
        assert_eq!(share, Some(0.0));
    }

    #[test]
    fn reported_shares_are_bounded_even_with_unreported_categories() {
        // `nice`/`irq`/`softirq`/`steal` stay in the denominator but are not
        // reported, so the four shares sum to 100 or slightly less, never more
        // (plan v4 criterion: values in 0..=100, sum in 95..=100.5).
        // Realistic small increments for the unreported categories: measured
        // 15 samples under load stayed within 98.89..=100.00.
        let previous = Counters::from_fields(&[1000, 0, 500, 9000, 0, 0, 200, 100, 0, 0]);
        let current = Counters::from_fields(&[1100, 1, 560, 9200, 10, 1, 204, 101, 0, 0]);
        let total = crate::linux::count_delta(previous.total(), current.total()).unwrap();
        let shares: Vec<f64> = [current.user, current.system, current.idle, current.iowait]
            .into_iter()
            .zip([
                previous.user,
                previous.system,
                previous.idle,
                previous.iowait,
            ])
            .filter_map(|(current, previous)| {
                crate::linux::count_delta(previous, current)
                    .and_then(|part| crate::sample::share(part, total))
            })
            .collect();
        assert_eq!(shares.len(), 4);
        assert!(shares.iter().all(|value| (0.0..=100.0).contains(value)));
        let sum: f64 = shares.iter().sum();
        assert!((95.0..=100.5).contains(&sum), "{sum}");
    }

    #[test]
    fn total_uses_aggregate_not_guest_double_count() {
        // Guest is counted inside user by the kernel, so `us` must be
        // 100_000 / 631_700, not 100_000 / 671_700.
        let counters =
            Counters::from_fields(&[100_000, 200, 30_000, 500_000, 1_000, 0, 500, 0, 40_000, 0]);
        let percent = counters.user as f64 / counters.total() as f64 * 100.0;
        assert!((percent - 15.83).abs() < 0.01, "{percent}");
        let legacy = counters.user as f64 / (counters.total() + counters.guest) as f64 * 100.0;
        assert!(percent - legacy > 0.5, "criterion cannot distinguish");
    }
}
