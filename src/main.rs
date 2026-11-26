//! msar — an all-in-one system CLI for Linux and macOS.
//!
//! Issue #3 delivers the shared sampling and output flow: module selection,
//! one-shot and periodic runs, signal-driven shutdown, and terminal or
//! JSONL output. Platform metric reads live in #4 (Linux) and #5 (macOS).

mod cli;
mod darwin;
mod linux;
mod metric;
mod output;
mod sample;

use std::env;
use std::fs::File;
use std::io::{self, Write};
use std::os::fd::AsFd;
use std::path::Path;
use std::process::ExitCode;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use cli::{Action, Args, Mode};
use metric::Metric;
use metric::MetricValues;
use output::Report;
use sample::Window;

const HELP: &str = "msar - an all-in-one system CLI for Linux and macOS

Usage: msar [OPTION]

Options:
  --cpu            CPU share (user, system, interrupt, nice, & idle)
  --mem            Physical memory share
  --load           System run queue and load average
  --io             Disk I/O performance
  --traffic        Network traffic statistics
  -a, --all        Load every module
  -n, --interval   Seconds between updates (omit the value for 1)
  -o, --output     Append JSON lines to a local file
  -h, --help       Print help
  -V, --version    Print version

Without -n a single round is sampled. Platform metric reads are delivered by
https://github.com/askdaddy/msar/issues/4 (Linux) and /5 (macOS); modules
without a backend report every field as \"unavailable\".
";

/// Watchdog period for checking the shutdown flag while sampling.
const SHUTDOWN_POLL: Duration = Duration::from_millis(25);

static SHUTDOWN: AtomicBool = AtomicBool::new(false);

fn main() -> ExitCode {
    let arguments: Vec<_> = env::args_os().skip(1).collect();
    let action = match cli::parse(&arguments) {
        Ok(action) => action,
        Err(error) => {
            let _ = writeln!(
                io::stderr().lock(),
                "msar: {}\nTry 'msar --help' for usage.",
                error.0
            );
            return ExitCode::from(2);
        }
    };

    match action {
        Action::Help => write_stdout(HELP),
        Action::Version => write_stdout(&format!("msar {}\n", env!("CARGO_PKG_VERSION"))),
        Action::Run(args) => run(args),
    }
}

/// Write to stdout, preserving write errors while tolerating `BrokenPipe`.
fn write_stdout(text: &str) -> ExitCode {
    // Stdout suppresses EBADF; File preserves write errors without owning fd 1.
    let result = io::stdout()
        .as_fd()
        .try_clone_to_owned()
        .and_then(|fd| File::from(fd).write_all(text.as_bytes()));
    match result {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) if error.kind() == io::ErrorKind::BrokenPipe => ExitCode::SUCCESS,
        Err(error) => {
            let _ = writeln!(io::stderr().lock(), "msar: cannot write stdout: {error}");
            ExitCode::FAILURE
        }
    }
}

fn run(args: Args) -> ExitCode {
    install_signal_handlers();

    // CPU counters are 32 bits and the baseline must be one window old, so take
    // it once here, before the first round; re-priming per round would reset
    // the baseline right before sample() reads it again and yield a zero delta
    // (plan v2 step 9).
    if args.modules.cpu && Platform::detect() == Platform::Darwin {
        darwin::Cpu.prime();
    }

    let period = match args.mode {
        Mode::Once => None,
        Mode::Repeat { period } => Some(Duration::from_secs(period.max(1))),
    };

    let mut remaining = match args.mode {
        Mode::Once => Some(1),
        Mode::Repeat { .. } => None,
    };

    loop {
        if SHUTDOWN.load(Ordering::Relaxed) {
            return ExitCode::SUCCESS;
        }

        match emit_round(&args) {
            Ok(()) => {}
            Err(error) => {
                let _ = writeln!(io::stderr().lock(), "msar: {error}");
                return ExitCode::FAILURE;
            }
        }

        if let Some(left) = remaining.as_mut() {
            *left -= 1;
            if *left == 0 {
                return ExitCode::SUCCESS;
            }
        }

        let Some(period) = period else {
            return ExitCode::SUCCESS;
        };
        wait_or_shutdown(period);
    }
}

/// Sleep up to `period`, returning early once shutdown was requested.
fn wait_or_shutdown(period: Duration) {
    let deadline = Instant::now() + period;
    while Instant::now() < deadline {
        if SHUTDOWN.load(Ordering::Relaxed) {
            return;
        }
        std::thread::sleep(SHUTDOWN_POLL.min(deadline.saturating_duration_since(Instant::now())));
    }
}

/// Sample every selected module in one shared window and write one report.
///
/// On Linux each module reads `/proc`; elsewhere every module reports
/// unavailable fields so the keys stay present with `null` values.
fn emit_round(args: &Args) -> Result<(), String> {
    let window = Window::start();
    let mut report = Report::new(hostname(), unix_timestamp());
    let platform = Platform::detect();

    if args.modules.cpu {
        report.insert(
            "Cpu",
            sample_cpu(platform, &window, &["us", "sy", "id", "wa"]),
        );
    }
    if args.modules.mem {
        report.insert(
            "Mem",
            sample_mem(
                platform,
                &window,
                &["total", "free", "buffers", "cached", "available"],
            ),
        );
    }
    if args.modules.load {
        report.insert(
            "Load",
            sample_load(platform, &window, &["load1", "load5", "load15"]),
        );
    }
    // Io/Traffic must diff two snapshots, so each starts its own window: the
    // shared one is idempotent and is already spent by the time Cpu finishes.
    if args.modules.io {
        let io_window = Window::start();
        report.insert("IO", sample_io(platform, &io_window));
    }
    if args.modules.traffic {
        let traffic_window = Window::start();
        report.insert("Traffic", sample_traffic(platform, &traffic_window));
    }

    match &args.output {
        Some(path) => output::append_line(Path::new(path), &report.to_json())
            .map_err(|error| format!("cannot write {path}: {error}")),
        None => {
            let text = report.to_terminal();
            write_stdout_result(&text)
        }
    }
}

/// Which platform's data sources this build can use.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Platform {
    Linux,
    Darwin,
    Unsupported,
}

impl Platform {
    fn detect() -> Self {
        if linux::available() {
            Self::Linux
        } else if darwin::available() {
            Self::Darwin
        } else {
            Self::Unsupported
        }
    }
}

/// Run the selected backend, or report its fields as unavailable.
fn sample_cpu(platform: Platform, window: &Window, fields: &[&str]) -> MetricValues {
    match platform {
        Platform::Linux => linux::Cpu.sample(window),
        Platform::Darwin => darwin::Cpu.sample(window),
        Platform::Unsupported => unavailable_fields(fields),
    }
}

fn sample_mem(platform: Platform, window: &Window, fields: &[&str]) -> MetricValues {
    match platform {
        Platform::Linux => linux::Mem.sample(window),
        Platform::Darwin => darwin::Mem.sample(window),
        Platform::Unsupported => unavailable_fields(fields),
    }
}

fn sample_load(platform: Platform, window: &Window, fields: &[&str]) -> MetricValues {
    match platform {
        Platform::Linux => linux::Load.sample(window),
        Platform::Darwin => darwin::Load.sample(window),
        Platform::Unsupported => unavailable_fields(fields),
    }
}

fn sample_io(platform: Platform, window: &Window) -> MetricValues {
    match platform {
        Platform::Linux => linux::Io.sample(window),
        Platform::Darwin => darwin::Io.sample(window),
        Platform::Unsupported => MetricValues::new(),
    }
}

fn sample_traffic(platform: Platform, window: &Window) -> MetricValues {
    match platform {
        Platform::Linux => linux::Traffic.sample(window),
        Platform::Darwin => darwin::Traffic.sample(window),
        Platform::Unsupported => MetricValues::new(),
    }
}

/// Write to stdout from the run loop, mapping failures to a message.
fn write_stdout_result(text: &str) -> Result<(), String> {
    let result = io::stdout()
        .as_fd()
        .try_clone_to_owned()
        .and_then(|fd| File::from(fd).write_all(text.as_bytes()));
    match result {
        Ok(()) => Ok(()),
        Err(error) if error.kind() == io::ErrorKind::BrokenPipe => Ok(()),
        Err(error) => Err(format!("cannot write stdout: {error}")),
    }
}

fn unavailable_fields(names: &[&str]) -> MetricValues {
    names
        .iter()
        .map(|name| ((*name).to_owned(), None))
        .collect()
}

fn hostname() -> String {
    // `/proc` exists on Linux only; `uname -n` is the portable equivalent and
    // needs no dependency beyond the C `uname` already linked by the standard
    // library's process start-up.
    let from_proc = std::fs::read_to_string("/proc/sys/kernel/hostname")
        .ok()
        .map(|text| text.trim().to_owned())
        .filter(|text| !text.is_empty());
    if let Some(hostname) = from_proc {
        return hostname;
    }
    if let Some(hostname) = env::var("HOSTNAME").ok().filter(|text| !text.is_empty()) {
        return hostname;
    }
    uname_nodename().unwrap_or_else(|| "unknown".to_owned())
}

/// Portable `uname(2)` hostname lookup for macOS and other Unix targets.
fn uname_nodename() -> Option<String> {
    const UTS_LEN: usize = 256;

    #[repr(C)]
    struct Utsname {
        sysname: [u8; UTS_LEN],
        nodename: [u8; UTS_LEN],
        release: [u8; UTS_LEN],
        version: [u8; UTS_LEN],
        machine: [u8; UTS_LEN],
    }

    unsafe extern "C" {
        fn uname(buffer: *mut Utsname) -> i32;
    }

    let mut buffer = std::mem::MaybeUninit::<Utsname>::zeroed();
    // SAFETY: `uname` fills a caller-provided `struct utsname`; the buffer is
    // large enough for the platform's fixed-size fields.
    let status = unsafe { uname(buffer.as_mut_ptr()) };
    if status != 0 {
        return None;
    }
    let buffer = unsafe { buffer.assume_init() };
    let end = buffer
        .nodename
        .iter()
        .position(|byte| *byte == 0)
        .unwrap_or(UTS_LEN);
    let name = std::str::from_utf8(&buffer.nodename[..end])
        .ok()?
        .to_owned();
    if name.is_empty() { None } else { Some(name) }
}

fn unix_timestamp() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|elapsed| elapsed.as_secs_f64())
        .unwrap_or(0.0)
}

/// Signal handlers set a flag; the loop then finishes its current round.
///
/// `std::` has no signal API and the contract forbids new dependencies, so this
/// links the two stable C entry points directly — the same two the legacy
/// `framework.Console` installed.
fn install_signal_handlers() {
    const SIGINT: i32 = 2;
    const SIGTERM: i32 = 15;
    unsafe {
        signal(SIGINT, on_signal);
        signal(SIGTERM, on_signal);
    }
}

unsafe extern "C" {
    fn signal(number: i32, handler: extern "C" fn(i32)) -> usize;
}

extern "C" fn on_signal(_number: i32) {
    SHUTDOWN.store(true, Ordering::Relaxed);
}
