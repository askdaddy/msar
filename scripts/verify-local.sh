#!/usr/bin/env bash
# Local cross-platform verification for issue #6.
#
# Runs the checks that CI runs, on this machine: the host target directly and
# both Linux targets through cargo-zigbuild, then executes the Linux binaries
# in a container. Linux data sources are real there, so the contract is checked
# against actual /proc rather than against a stub.
#
# Usage: scripts/verify-local.sh [--no-container]

set -euo pipefail
cd "$(dirname "$0")/.."

export PATH="$HOME/.cargo/bin:$HOME/.rustup/toolchains/stable-aarch64-apple-darwin/bin:$PATH"

CONTAINER_IMAGE="${CONTAINER_IMAGE:-debian:13}"
RUN_CONTAINER=1
[ "${1:-}" = "--no-container" ] && RUN_CONTAINER=0

step() { printf '\n== %s ==\n' "$*"; }

step "fmt, clippy and unit tests"
cargo fmt --check
cargo clippy --locked --all-targets -- -D warnings
cargo test --locked
# The black-box suites default to target/debug, so build it here as well.
cargo build --locked

step "build the host target (${HOSTTARGET:-aarch64-apple-darwin})"
cargo build --release --locked

step "host contract"
host="target/release/msar"
"$host" -V
"$host" --help >/dev/null
"$host" --cpu >/dev/null
round=$(mktemp -d)/round.jsonl
"$host" -a -o "$round"
python3 - "$round" <<'PY'
import json, sys
payload = json.loads(open(sys.argv[1]).read())
missing = [k for k in ("Cpu", "Mem", "Load", "IO", "Traffic") if k not in payload]
assert not missing, f"missing modules: {missing}"
for module, values in payload.items():
    if module in {"hostname", "timestamp"}:
        continue
    for field, value in values.items():
        assert value is None or isinstance(value, (int, float)), f"{module}.{field}={value!r}"
print("host JSON contract OK")
PY

step "cross-build the Linux targets"
for target in aarch64-unknown-linux-gnu x86_64-unknown-linux-gnu; do
  cargo zigbuild --release --locked --target "$target"
  file "target/$target/release/msar" | sed 's/^/  /'
done

if [ "$RUN_CONTAINER" = 1 ] && command -v docker >/dev/null 2>&1; then
  step "run the Linux binaries in $CONTAINER_IMAGE"
  for pair in "x86_64-unknown-linux-gnu:linux/amd64" "aarch64-unknown-linux-gnu:linux/arm64"; do
    target="${pair%%:*}"
    platform="${pair##*:}"
    binary="$PWD/target/$target/release/msar"
    echo "  -- $target ($platform)"
    docker run --rm --platform "$platform" -v "$binary:/tmp/msar:ro" "$CONTAINER_IMAGE" sh -c '
      chmod +x /tmp/msar
      /tmp/msar -V
      /tmp/msar --cpu
      /tmp/msar --mem --load --io --traffic >/dev/null
    ' | sed 's/^/    /'
  done
else
  step "container checks skipped"
  echo "  docker unavailable or --no-container was passed; Linux runtime is UNVERIFIED"
fi

step "black-box suites"
python3 test/issue3_acceptance.py target/debug/msar
python3 test/issue4_acceptance.py target/debug/msar

step "all local checks passed"
