//! Output contract (issue #3).
//!
//! One round becomes one JSON object shared verbatim by both sinks:
//!
//! ```json
//! {"hostname":"…","timestamp":1700000000.5,"Cpu":{"us":12.5,"sy":3.0}}
//! ```
//!
//! Values are JSON numbers (not the legacy `"%.2f"` strings), so consumers no
//! longer re-parse. A metric without data is `null`, never an omitted key and
//! never a silent drop. JSON is written by hand to keep the zero-dependency
//! constraint (`Cargo.toml` has no `[dependencies]`).

use std::collections::BTreeMap;
use std::fmt::Write as _;
use std::fs::OpenOptions;
use std::io::Write;
use std::path::Path;

use crate::metric::{MetricValues, UNAVAILABLE_LABEL, Value};

/// One rendered round: module name to its field values.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct Report {
    pub hostname: String,
    /// Unix seconds with sub-second precision. Output only; never differs on.
    pub timestamp: f64,
    pub modules: BTreeMap<&'static str, MetricValues>,
}

impl Report {
    pub fn new(hostname: impl Into<String>, timestamp: f64) -> Self {
        Self {
            hostname: hostname.into(),
            timestamp,
            modules: BTreeMap::new(),
        }
    }

    pub fn insert(&mut self, name: &'static str, values: MetricValues) {
        self.modules.insert(name, values);
    }

    /// Serialise to a single-line JSON object.
    pub fn to_json(&self) -> String {
        let mut out = String::with_capacity(128);
        out.push_str("{\"hostname\":");
        push_string(&mut out, &self.hostname);
        let _ = write!(
            out,
            ",\"timestamp\":{}",
            number_or_null(Some(self.timestamp))
        );
        for (name, values) in &self.modules {
            out.push(',');
            push_string(&mut out, name);
            out.push_str(":{");
            for (index, (field, value)) in values.iter().enumerate() {
                if index > 0 {
                    out.push(',');
                }
                push_string(&mut out, field);
                out.push(':');
                out.push_str(&number_or_null(*value));
            }
            out.push('}');
        }
        out.push('}');
        out
    }

    /// Human-readable terminal rendering, keeping the legacy heading style.
    pub fn to_terminal(&self) -> String {
        let mut out = String::new();
        for (name, values) in &self.modules {
            let _ = writeln!(out, "{name:^20}");
            for (field, value) in values {
                match value {
                    Some(value) => {
                        let _ = writeln!(out, "{field}: {value}");
                    }
                    None => {
                        let _ = writeln!(out, "{field}: {UNAVAILABLE_LABEL}");
                    }
                }
            }
        }
        out
    }
}

/// JSON `null` for `None`; a plain number otherwise. `NaN`/`Inf` are not valid
/// JSON, so they degrade to `null` instead of emitting invalid output.
fn number_or_null(value: Value) -> String {
    match value {
        Some(value) if value.is_finite() => format!("{value}"),
        _ => "null".to_owned(),
    }
}

fn push_string(out: &mut String, text: &str) {
    out.push('"');
    for character in text.chars() {
        match character {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            character if (character as u32) < 0x20 => {
                let _ = write!(out, "\\u{:04x}", character as u32);
            }
            character => out.push(character),
        }
    }
    out.push('"');
}

/// Append one JSON line to `path`, creating it if needed.
///
/// Every failure is returned to the caller: the legacy `except: pass` silently
/// discarded data, which this contract forbids.
pub fn append_line(path: &Path, line: &str) -> std::io::Result<()> {
    let mut file = OpenOptions::new().create(true).append(true).open(path)?;
    file.write_all(line.as_bytes())?;
    file.write_all(b"\n")?;
    file.flush()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn report() -> Report {
        let mut report = Report::new("host", 1.5);
        let mut cpu = MetricValues::new();
        cpu.insert("us".to_owned(), Some(12.5));
        cpu.insert("sy".to_owned(), None);
        report.insert("Cpu", cpu);
        report
    }

    #[test]
    fn json_has_hostname_and_timestamp() {
        let json = report().to_json();
        assert!(
            json.starts_with(r#"{"hostname":"host","timestamp":1.5,"#),
            "{json}"
        );
    }

    #[test]
    fn unavailable_becomes_null_not_a_missing_key() {
        let json = report().to_json();
        assert!(json.contains(r#""sy":null"#), "{json}");
    }

    #[test]
    fn values_are_numbers_not_strings() {
        let json = report().to_json();
        assert!(json.contains(r#""us":12.5"#), "{json}");
        assert!(!json.contains(r#""us":"12.5""#), "{json}");
    }

    #[test]
    fn special_characters_are_escaped() {
        let mut out = String::new();
        push_string(&mut out, "a\"b\\c\nd");
        assert_eq!(out, r#""a\"b\\c\nd""#);
    }

    #[test]
    fn non_finite_becomes_null() {
        assert_eq!(number_or_null(Some(f64::NAN)), "null");
        assert_eq!(number_or_null(Some(f64::INFINITY)), "null");
        assert_eq!(number_or_null(Some(1.25)), "1.25");
    }

    #[test]
    fn terminal_marks_unavailable() {
        let terminal = report().to_terminal();
        assert!(terminal.contains("sy: unavailable"), "{terminal}");
        assert!(terminal.contains("us: 12.5"), "{terminal}");
    }

    #[test]
    fn append_creates_and_extends() {
        let directory = std::env::temp_dir().join("msar-output-test");
        let _ = std::fs::create_dir_all(&directory);
        let path = directory.join("out.jsonl");
        let _ = std::fs::remove_file(&path);
        append_line(&path, "{\"a\":1}").unwrap();
        append_line(&path, "{\"a\":2}").unwrap();
        let content = std::fs::read_to_string(&path).unwrap();
        assert_eq!(content, "{\"a\":1}\n{\"a\":2}\n");
        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn append_to_unknown_directory_fails_loudly() {
        let path = std::env::temp_dir()
            .join("msar-no-such-dir-xyz")
            .join("out.jsonl");
        assert!(append_line(&path, "{}").is_err());
    }
}
