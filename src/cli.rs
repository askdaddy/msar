//! Command-line parsing (issue #3).
//!
//! Keeps the legacy option intent: `--cpu/--mem/--load/--io/--traffic`, `-a`,
//! `-n`, `-o`, `-h`, `-V`. Unlike the legacy parser, invalid intervals and
//! unimplemented HTTP output are reported instead of silently misbehaving.

use std::ffi::OsString;

/// Which modules to sample this run.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub struct Modules {
    pub cpu: bool,
    pub mem: bool,
    pub load: bool,
    pub io: bool,
    pub traffic: bool,
}

impl Modules {
    pub fn any(&self) -> bool {
        self.cpu || self.mem || self.load || self.io || self.traffic
    }

    pub fn all() -> Self {
        Self {
            cpu: true,
            mem: true,
            load: true,
            io: true,
            traffic: true,
        }
    }
}

/// How often to sample.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Mode {
    /// `-n` absent: sample once.
    Once,
    /// `-n` present: repeat every `period` seconds.
    Repeat { period: u64 },
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Args {
    pub modules: Modules,
    pub mode: Mode,
    /// Local output path; `None` means terminal.
    pub output: Option<String>,
}

/// What the CLI asks the program to do.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Action {
    Help,
    Version,
    Run(Args),
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct UsageError(pub String);

/// Parse program arguments (without the program name).
///
/// An empty argument list prints help, matching the legacy behaviour.
pub fn parse(arguments: &[OsString]) -> Result<Action, UsageError> {
    // The legacy CLI printed help when called without arguments; keep that.
    if arguments.is_empty() {
        return Ok(Action::Help);
    }

    let mut modules = Modules::default();
    let mut mode = Mode::Once;
    let mut output = None;
    let mut index = 0;

    while let Some(argument) = arguments.get(index) {
        let text = argument
            .to_str()
            .ok_or_else(|| UsageError(format!("invalid UTF-8 argument: {argument:?}")))?;
        match text {
            "-h" | "--help" => return Ok(Action::Help),
            "-V" | "--version" => return Ok(Action::Version),
            "-a" | "--all" => modules = Modules::all(),
            "--cpu" => modules.cpu = true,
            "--mem" => modules.mem = true,
            "--load" => modules.load = true,
            "--io" => modules.io = true,
            "--traffic" => modules.traffic = true,
            "-n" | "--interval" => {
                // `nargs='?'` semantics: a following option is not a value.
                index += 1;
                let value = arguments
                    .get(index)
                    .and_then(|value| value.to_str())
                    .filter(|text| !text.starts_with('-') || is_negative_number(text));
                mode = Mode::Repeat {
                    period: parse_period(value)?,
                };
                if value.is_none() {
                    index -= 1;
                }
            }
            "-o" | "--output" => {
                index += 1;
                let value = arguments.get(index).and_then(|value| value.to_str());
                let path = value.ok_or_else(|| UsageError("-o requires a path".to_owned()))?;
                reject_http(path)?;
                output = Some(path.to_owned());
            }
            other => {
                return Err(UsageError(format!("unsupported argument: {other}")));
            }
        }
        index += 1;
    }

    if !modules.any() {
        return Err(UsageError(
            "no module selected; use --cpu, --mem, --load, --io, --traffic or -a".to_owned(),
        ));
    }

    Ok(Action::Run(Args {
        modules,
        mode,
        output,
    }))
}

/// `-n` without a value means one second; `-n N` must be a positive integer.
fn parse_period(value: Option<&str>) -> Result<u64, UsageError> {
    match value {
        None => Ok(1),
        Some(text) => {
            // `-n -1` arrives as the token `-1`; report it as a bad interval
            // rather than as an unknown option.
            if is_negative(text) {
                return Err(UsageError(format!(
                    "invalid interval: {text}; expected a positive integer"
                )));
            }
            match text.parse::<u64>() {
                Ok(0) => Err(UsageError(
                    "invalid interval: 0; expected a positive number of seconds".to_owned(),
                )),
                Ok(period) => Ok(period),
                Err(_) => Err(UsageError(format!(
                    "invalid interval: {text}; expected a positive integer"
                ))),
            }
        }
    }
}

/// HTTP output is not implemented; refusing is the fix for the legacy `pass`.
fn reject_http(path: &str) -> Result<(), UsageError> {
    let lower = path.to_ascii_lowercase();
    if lower.starts_with("http://") || lower.starts_with("https://") {
        return Err(UsageError(format!(
            "HTTP output is not implemented: {path}; use a local file path"
        )));
    }
    Ok(())
}

/// Negative intervals arrive as a separate `-N` argument; callers feed the raw
/// text through, so this normalises a leading minus before parsing.
pub fn is_negative(text: &str) -> bool {
    text.trim_start().starts_with('-')
}

/// A `-1`-style token: negative numeric text, not an option name.
///
/// Keeps `msar -n -1 --cpu` reporting a bad interval while `msar -n --cpu`
/// still treats `--cpu` as a module flag, matching `argparse` `nargs='?'`.
fn is_negative_number(text: &str) -> bool {
    text.starts_with('-')
        && text
            .trim_start_matches('-')
            .chars()
            .all(|character| character.is_ascii_digit())
        && text.trim_start_matches('-').len() < text.len()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn args(list: &[&str]) -> Vec<OsString> {
        list.iter().map(OsString::from).collect()
    }

    #[test]
    fn empty_list_prints_help() {
        assert_eq!(parse(&[]), Ok(Action::Help));
    }

    #[test]
    fn version_is_recognised() {
        assert_eq!(parse(&args(&["-V"])), Ok(Action::Version));
    }

    #[test]
    fn every_legacy_module_flag_is_accepted() {
        for flag in ["--cpu", "--mem", "--load", "--io", "--traffic", "-a"] {
            assert!(
                matches!(parse(&args(&[flag])), Ok(Action::Run(_))),
                "{flag}"
            );
        }
    }

    #[test]
    fn all_selects_every_module() {
        let Ok(Action::Run(run)) = parse(&args(&["-a"])) else {
            panic!("expected run");
        };
        assert_eq!(run.modules, Modules::all());
    }

    #[test]
    fn interval_defaults_to_one_second() {
        let Ok(Action::Run(run)) = parse(&args(&["--cpu", "-n"])) else {
            panic!("expected run");
        };
        assert_eq!(run.mode, Mode::Repeat { period: 1 });
    }

    #[test]
    fn explicit_interval_is_used() {
        let Ok(Action::Run(run)) = parse(&args(&["--cpu", "-n", "5"])) else {
            panic!("expected run");
        };
        assert_eq!(run.mode, Mode::Repeat { period: 5 });
    }

    #[test]
    fn zero_interval_is_rejected() {
        assert!(parse(&args(&["--cpu", "-n", "0"])).is_err());
    }

    #[test]
    fn non_numeric_interval_is_rejected() {
        assert!(parse(&args(&["--cpu", "-n", "abc"])).is_err());
    }

    #[test]
    fn unknown_option_is_rejected() {
        assert!(parse(&args(&["--nope"])).is_err());
    }

    #[test]
    fn no_module_is_rejected() {
        assert!(parse(&args(&["-n"])).is_err());
    }

    #[test]
    fn http_output_is_rejected() {
        assert!(parse(&args(&["--cpu", "-o", "http://example.com/x"])).is_err());
        assert!(parse(&args(&["--cpu", "-o", "https://example.com/x"])).is_err());
    }

    #[test]
    fn local_output_path_is_accepted() {
        let Ok(Action::Run(run)) = parse(&args(&["--cpu", "-o", "/tmp/x.jsonl"])) else {
            panic!("expected run");
        };
        assert_eq!(run.output.as_deref(), Some("/tmp/x.jsonl"));
    }

    #[test]
    fn missing_output_value_is_rejected() {
        assert!(parse(&args(&["--cpu", "-o"])).is_err());
    }

    #[test]
    fn interval_without_value_does_not_swallow_the_next_flag() {
        // `-n --cpu` must mean "1 second, CPU module", not "value --cpu".
        let Ok(Action::Run(run)) = parse(&args(&["-n", "--cpu"])) else {
            panic!("expected run");
        };
        assert_eq!(run.mode, Mode::Repeat { period: 1 });
        assert!(run.modules.cpu);
    }

    #[test]
    fn negative_interval_is_still_an_error_with_input() {
        assert!(parse(&args(&["-n", "-1", "--cpu"])).is_err());
    }

    #[test]
    fn negative_text_is_detected() {
        assert!(is_negative("-1"));
        assert!(!is_negative("1"));
    }
}
