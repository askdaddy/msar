//! Load average backend: `sysctl -n vm.loadavg` (issue #5).

use crate::metric::{Metric, MetricValues, Unit};
use crate::sample::Window;

/// The three load averages, dimensionless.
#[derive(Debug, Clone, Copy, Default, PartialEq)]
pub struct LoadAverage {
    pub load1: Option<f64>,
    pub load5: Option<f64>,
    pub load15: Option<f64>,
}

/// Parse `{ 17.18 10.95 7.96 }`, the shape `vm.loadavg` prints.
///
/// The braces are stripped before the values are read; anything that is not a
/// finite number leaves that field missing rather than guessing.
pub fn parse_loadavg(text: &str) -> LoadAverage {
    let cleaned = text.trim().trim_start_matches('{').trim_end_matches('}');
    let mut values = cleaned.split_whitespace();
    let mut next = || {
        values
            .next()
            .and_then(|field| field.parse::<f64>().ok())
            .filter(|value| value.is_finite())
    };
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

        let Some(text) = super::command("sysctl", &["-n", "vm.loadavg"]) else {
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
        let average = parse_loadavg("{ 17.18 10.95 7.96 }\n");
        assert_eq!(average.load1, Some(17.18));
        assert_eq!(average.load5, Some(10.95));
        assert_eq!(average.load15, Some(7.96));
    }

    #[test]
    fn braces_are_optional() {
        let average = parse_loadavg("0.21 0.21 0.19");
        assert_eq!(average.load1, Some(0.21));
        assert_eq!(average.load15, Some(0.19));
    }

    #[test]
    fn truncated_input_leaves_missing_fields_none() {
        let average = parse_loadavg("{ 1.5 }");
        assert_eq!(average.load1, Some(1.5));
        assert_eq!(average.load5, None);
        assert_eq!(average.load15, None);
    }

    #[test]
    fn malformed_input_is_all_none_without_panic() {
        assert_eq!(parse_loadavg("garbage"), LoadAverage::default());
        assert_eq!(parse_loadavg(""), LoadAverage::default());
    }
}
