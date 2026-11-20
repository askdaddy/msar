use std::env;
use std::fs::File;
use std::io::{self, Write};
use std::os::fd::AsFd;
use std::process::ExitCode;

const HELP: &str = "msar - an all-in-one system CLI for Linux and macOS

Usage: msar [OPTION]

Options:
  -h, --help       Print help
  -V, --version    Print version

Status: Rust rewrite in progress. System monitoring is planned and is not
available yet. See README.md and https://github.com/askdaddy/msar/issues/1.
";

fn main() -> ExitCode {
    let args: Vec<_> = env::args_os().skip(1).collect();
    let output = match args.as_slice() {
        [] => HELP.to_owned(),
        [arg] if arg == "-h" || arg == "--help" => HELP.to_owned(),
        [arg] if arg == "-V" || arg == "--version" => {
            format!("msar {}\n", env!("CARGO_PKG_VERSION"))
        }
        _ => {
            let _ = writeln!(
                io::stderr().lock(),
                "msar: unsupported arguments: {args:?}\nTry 'msar --help' for usage."
            );
            return ExitCode::from(2);
        }
    };

    // Stdout suppresses EBADF; File preserves write errors without owning fd 1.
    let result = io::stdout()
        .as_fd()
        .try_clone_to_owned()
        .and_then(|fd| File::from(fd).write_all(output.as_bytes()));
    match result {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) if error.kind() == io::ErrorKind::BrokenPipe => ExitCode::SUCCESS,
        Err(error) => {
            let _ = writeln!(io::stderr().lock(), "msar: cannot write stdout: {error}");
            ExitCode::FAILURE
        }
    }
}
