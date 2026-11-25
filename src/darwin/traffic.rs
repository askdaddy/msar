//! Network traffic backend: `netstat -ib` (issue #5).
//!
//! `netstat -ib` prints one row per address, so an interface appears several
//! times with identical counters (measured: `en1` appears 3 times). Rows are
//! keyed by interface name, so the duplicates collapse to a single entry.

use std::collections::BTreeMap;

use crate::metric::{Metric, MetricValues, Unit};
use crate::sample::Window;

/// Cumulative byte counters for one interface.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Counters {
    pub receive_bytes: u64,
    pub transmit_bytes: u64,
}

/// Parse one `netstat -ib` row.
///
/// Columns: `Name Mtu Network Address Ipkts Ierrs Ibytes Opkts Oerrs Obytes
/// Coll`. `netstat` collapses an empty column, so a `<Link#1>` row without an
/// address has 10 fields instead of 11 (measured on `lo0`): the byte counters
/// then sit at 5 and 8 rather than 6 and 9. Selecting by field count keeps
/// both shapes correct, where a fixed index would read `Ipkts` as `Ibytes`.
///
/// Rows with any other field count, a non-numeric counter, or a `*` suffix (a
/// down unit with no counters) are skipped.
pub fn parse_netstat_line(line: &str) -> Option<(String, Counters)> {
    let fields: Vec<&str> = line.split_whitespace().collect();
    let name = fields.first()?;
    if *name == "Name" || name.ends_with('*') {
        return None;
    }
    let (receive, transmit) = match fields.len() {
        11 => (6, 9),
        10 => (5, 8),
        _ => return None,
    };
    let number = |index: usize| {
        fields
            .get(index)
            .and_then(|field| field.parse::<u64>().ok())
    };
    Some((
        (*name).to_owned(),
        Counters {
            receive_bytes: number(receive)?,
            transmit_bytes: number(transmit)?,
        },
    ))
}

/// Parse `netstat -ib`, keeping the first row for each interface.
pub fn parse_netstat(text: &str) -> BTreeMap<String, Counters> {
    let mut interfaces = BTreeMap::new();
    for line in text.lines() {
        if let Some((name, counters)) = parse_netstat_line(line) {
            // Later rows repeat the same counters, so the first row wins.
            interfaces.entry(name).or_insert(counters);
        }
    }
    interfaces
}

pub struct Traffic;

impl Metric for Traffic {
    fn name(&self) -> &'static str {
        "Traffic"
    }

    fn sample(&self, window: &Window) -> MetricValues {
        let mut values = MetricValues::new();

        // `-n` skips the reverse DNS lookup, which costs about five seconds on
        // this machine and would be paid twice per round. The counters and the
        // row layout are the same either way (measured on `en1` and `lo0`).
        let read = || super::command("netstat", &["-ib", "-n"]).map(|text| parse_netstat(&text));
        let Some(before) = read() else {
            return values;
        };
        // The caller passes a fresh window for this module (issue #4 v3).
        window.fill(crate::sample::DEFAULT_WINDOW);
        let window_secs = window.elapsed().as_secs_f64();
        let Some(after) = read() else {
            return values;
        };

        let duration = std::time::Duration::from_secs_f64(window_secs);
        for (interface, current) in &after {
            // An interface that appeared between the two reads has no baseline.
            let Some(previous) = before.get(interface) else {
                continue;
            };
            let received =
                crate::sample::rate(previous.receive_bytes, current.receive_bytes, duration);
            let transmitted =
                crate::sample::rate(previous.transmit_bytes, current.transmit_bytes, duration);
            if received.is_none() && transmitted.is_none() {
                continue;
            }
            values.insert(
                format!("{interface}.inbytes"),
                received
                    .map(|value| crate::metric::Quantity::new(value, Unit::BytesPerSecond).value),
            );
            values.insert(
                format!("{interface}.outbytes"),
                transmitted
                    .map(|value| crate::metric::Quantity::new(value, Unit::BytesPerSecond).value),
            );
        }
        values
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const REAL: &str = "Name       Mtu   Network       Address            Ipkts Ierrs    Ibytes    Opkts Oerrs    Obytes  Coll\n\
lo0        16384 <Link#1>                       3633523     0 7410197126  3633523     0 7410197126     0
n\
lo0        16384 127           localhost       3633523     - 7410197126  3633523     - 7410197126     -\n\
en1         1500 <Link#16>      82:7f:5d:3e:e9:7b 8267507833 0 8396053830 1735746313 0 1735746313 0\n\
en1         1500 mac-mini.local fe80:10::8f1:8ad6 8267507833 - 8396053830 1735746313 - 1735746313 -\n\
en1         1500 172.18         gitea             8267507833 - 8396053830 1735746313 - 1735746313 -\n\
gif0*       1280 <Link#2>                          0     0          0        0     0          0     0\n";

    #[test]
    fn parses_real_sample() {
        let interfaces = parse_netstat(REAL);
        assert_eq!(interfaces["en1"].receive_bytes, 8_396_053_830);
        assert_eq!(interfaces["en1"].transmit_bytes, 1_735_746_313);
        assert_eq!(interfaces["lo0"].receive_bytes, 7_410_197_126);
    }

    #[test]
    fn duplicate_rows_collapse_to_one_interface() {
        // The raw text has en1 three times; the map has it once.
        let raw_rows = REAL.lines().filter(|line| line.starts_with("en1 ")).count();
        assert_eq!(raw_rows, 3);
        let interfaces = parse_netstat(REAL);
        assert_eq!(interfaces.keys().filter(|name| *name == "en1").count(), 1);
    }

    #[test]
    fn header_and_down_units_are_skipped() {
        let interfaces = parse_netstat(REAL);
        assert!(!interfaces.contains_key("Name"));
        assert!(!interfaces.contains_key("gif0*"));
        assert!(!interfaces.contains_key("gif0"));
    }

    #[test]
    fn short_and_malformed_rows_are_skipped() {
        assert!(parse_netstat_line("en0 1500 <Link#7>").is_none());
        assert!(parse_netstat_line("").is_none());
        assert!(parse_netstat_line("en0 1500 net mac 0 0 abc 0 0 0 0").is_none());
    }
}
