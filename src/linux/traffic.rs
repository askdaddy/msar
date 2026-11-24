//! Network traffic backend: `/proc/net/dev` (issue #4).

use std::collections::BTreeMap;
use std::fs;

use crate::metric::{Metric, MetricValues, Unit};
use crate::sample::Window;

/// Cumulative byte counters for one interface.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Counters {
    pub receive_bytes: u64,
    pub transmit_bytes: u64,
}

/// Parse one `/proc/net/dev` interface line.
///
/// The interface name is whatever precedes the first `:`, so names containing
/// `.`, `-`, `@`, or `_` (`eth0.100`, `br-abc123`, `eno1.100@eno1`) parse
/// correctly. The legacy `\w*` regex silently matched none of those. Fields
/// after the colon are receive then transmit groups; a short line is skipped
/// rather than indexed out of bounds.
pub fn parse_netdev_line(line: &str) -> Option<(String, Counters)> {
    let (name, rest) = line.split_once(':')?;
    let name = name.trim();
    if name.is_empty() {
        return None;
    }
    let fields: Vec<&str> = rest.split_whitespace().collect();
    // Receive group: bytes packets errs drop fifo frame compressed multicast.
    // Transmit group starts at index 8 with its bytes.
    let receive_bytes = fields.first()?.parse::<u64>().ok()?;
    let transmit_bytes = fields.get(8)?.parse::<u64>().ok()?;
    Some((
        name.to_owned(),
        Counters {
            receive_bytes,
            transmit_bytes,
        },
    ))
}

/// Parse every interface line in a `/proc/net/dev` text.
pub fn parse_netdev(text: &str) -> BTreeMap<String, Counters> {
    text.lines().filter_map(parse_netdev_line).collect()
}

pub struct Traffic;

impl Metric for Traffic {
    fn name(&self) -> &'static str {
        "Traffic"
    }

    fn sample(&self, window: &Window) -> MetricValues {
        let mut values = MetricValues::new();

        // Reuse one sample for both sides when the first read fails.
        let read = || {
            fs::read_to_string("/proc/net/dev")
                .ok()
                .map(|text| parse_netdev(&text))
        };
        let Some(before) = read() else {
            return values;
        };
        // The caller passes a fresh window for this module (plan v3), so its
        // elapsed time is the real span between the two snapshots.
        window.fill(crate::sample::DEFAULT_WINDOW);
        let window_secs = window.elapsed().as_secs_f64();
        let Some(after) = read() else {
            return values;
        };

        for (interface, current) in &after {
            // A new interface has no baseline, so there is no rate yet.
            let Some(previous) = before.get(interface) else {
                continue;
            };
            let duration = std::time::Duration::from_secs_f64(window_secs);
            let received =
                crate::sample::rate(previous.receive_bytes, current.receive_bytes, duration);
            let transmitted =
                crate::sample::rate(previous.transmit_bytes, current.transmit_bytes, duration);
            let reported = received.is_none() && transmitted.is_none();
            if reported {
                continue;
            }
            let unit = Unit::BytesPerSecond;
            values.insert(
                format!("{interface}.inbytes"),
                received.map(|value| crate::metric::Quantity::new(value, unit).value),
            );
            values.insert(
                format!("{interface}.outbytes"),
                transmitted.map(|value| crate::metric::Quantity::new(value, unit).value),
            );
        }
        values
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const REAL: &str = "Inter-|   Receive                                                |  Transmit\n\
 face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed\n\
    lo:  149092    1868    0    0    0     0          0         0   149092    1868    0    0    0     0       0          0\n\
  eth0: 1234567    9000    0    0    0     0          0         0   7654321    8000    0    0    0     0       0          0\n";

    #[test]
    fn parses_real_sample() {
        let interfaces = parse_netdev(REAL);
        assert_eq!(interfaces["lo"].receive_bytes, 149_092);
        assert_eq!(interfaces["lo"].transmit_bytes, 149_092);
        assert_eq!(interfaces["eth0"].transmit_bytes, 7_654_321);
    }

    #[test]
    fn header_lines_are_skipped() {
        let interfaces = parse_netdev(REAL);
        assert_eq!(interfaces.len(), 2);
        assert!(!interfaces.contains_key(
            "Inter-|   Receive                                                |  Transmit"
        ));
    }

    #[test]
    fn names_with_dot_dash_and_at_are_parsed() {
        // The legacy `\w*` regex matched none of these names.
        let text = "eth0.100: 10 1 0 0 0 0 0 0 20 1 0 0 0 0 0 0\n\
br-abc123: 30 1 0 0 0 0 0 0 40 1 0 0 0 0 0 0\n\
eno1.100@eno1: 50 1 0 0 0 0 0 0 60 1 0 0 0 0 0 0\n";
        let interfaces = parse_netdev(text);
        assert_eq!(interfaces["eth0.100"].receive_bytes, 10);
        assert_eq!(interfaces["br-abc123"].transmit_bytes, 40);
        assert_eq!(interfaces["eno1.100@eno1"].transmit_bytes, 60);
    }

    #[test]
    fn short_line_is_skipped_not_panicking() {
        assert!(parse_netdev_line("eth0: 10 1").is_none());
        assert!(parse_netdev_line("no-colon-here").is_none());
        assert!(parse_netdev_line("").is_none());
    }

    #[test]
    fn malformed_bytes_are_skipped() {
        assert!(parse_netdev_line("eth0: abc 1 0 0 0 0 0 0 20 1").is_none());
    }
}
