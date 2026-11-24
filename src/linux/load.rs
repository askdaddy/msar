//! Load average backend: `/proc/loadavg` (issue #4).

use std::fs;

use crate::metric::{Metric, MetricValues, Unit};
use crate::sample::Window;

/// The three load averages, dimensionless.
#[derive(Debug, Clone, Copy, Default, PartialEq)]
pub struct LoadAverage {
    pub load1: Option<f64>,
    pub load5: Option<f64>,
    pub load15: Option<f64>,
}

/// Parse `/proc/loadavg`: `0.21 0.21 0.19 3/600 1648`.
///
/// Only the first three fields are used; the run-queue pair and last PID are
/// ignored, matching the legacy behaviour.
pub fn parse_loadavg(text: &str) -> LoadAverage {
    let mut values = text.split_whitespace();
    let mut next = || values.next().and_then(|field| field.parse::<f64>().ok());
    LoadAverage {
        load1: next(),
        load5: next(),
        load15: next(),
    }
}

pub struct Load;

impl Metric for Load {
    fn name(&self) -> &'static str {
        "Load"
    }

    fn sample(&self, _window: &Window) -> MetricValues {
        let mut values = MetricValues::new();
        for field in ["load1", "load5", "load15"] {
            values.insert(field.to_owned(), None);
        }

        let Some(text) = fs::read_to_string("/proc/loadavg").ok() else {
            return values;
        };
        let average = parse_loadavg(&text);

        for (field, value) in [
            ("load1", average.load1),
            ("load5", average.load5),
            ("load15", average.load15),
        ] {
            let quantity = value.map(|load| crate::metric::Quantity::new(load, Unit::Count));
            values.insert(field.to_owned(), quantity.map(|quantity| quantity.value));
        }
        values
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_real_sample() {
        let average = parse_loadavg("0.21 0.21 0.19 3/600 1648\n");
        assert_eq!(average.load1, Some(0.21));
        assert_eq!(average.load5, Some(0.21));
        assert_eq!(average.load15, Some(0.19));
    }

    #[test]
    fn truncated_input_leaves_missing_fields_none() {
        let average = parse_loadavg("0.21 0.5\n");
        assert_eq!(average.load1, Some(0.21));
        assert_eq!(average.load5, Some(0.5));
        assert_eq!(average.load15, None);
    }

    #[test]
    fn malformed_input_yields_none_without_panic() {
        let average = parse_loadavg("garbage\n");
        assert_eq!(average, LoadAverage::default());
    }
}
