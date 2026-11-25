#![allow(dead_code)] // exported backends are selected by main.rs per platform
//! macOS backends (issue #5).
//!
//! macOS has no `/proc` and no `kern.cp_time`. CPU load is read from the Mach
//! `HOST_CPU_LOAD_INFO` host statistic, which returns cumulative
//! `natural_t` ticks — the same shape as `/proc/stat`, so the shared window
//! and `count_delta` semantics carry over unchanged.
//!
//! Only four CPU states exist (`user/system/idle/nice`), so `wa` is reported as
//! unavailable rather than as a fabricated zero.

mod cpu;
mod io;
mod load;
mod mem;
mod traffic;

pub use cpu::Cpu;
pub use io::Io;
pub use load::Load;
pub use mem::Mem;
pub use traffic::Traffic;

/// Sampling window for CPU percentages on macOS (plan v4).
///
/// The Mach tick is much coarser than Linux jiffies, so a short window can see
/// no counter movement at all and every share becomes unavailable. A C probe
/// measured 0 of 30 zero rounds from 1000 ms on (750 ms still gave 1 of 30 and
/// 2 of 40), which is the shortest window that always moves here.
pub const CPU_WINDOW: std::time::Duration = std::time::Duration::from_millis(1000);

/// Whether this platform's data sources are available.
pub fn available() -> bool {
    cfg!(target_os = "macos")
}

/// Run a system command and return its stdout, treating any failure as absent.
pub fn command(program: &str, arguments: &[&str]) -> Option<String> {
    let output = std::process::Command::new(program)
        .args(arguments)
        .output()
        .ok()?;
    if !output.status.success() {
        return None;
    }
    String::from_utf8(output.stdout).ok()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn missing_command_is_none_not_panic() {
        assert_eq!(command("msar-definitely-not-a-command", &[]), None);
    }

    #[test]
    fn failing_command_is_none() {
        // `false` always exits non-zero.
        assert_eq!(command("false", &[]), None);
    }
}
