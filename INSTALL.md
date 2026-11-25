# 安装与使用

`msar` 是 Linux/macOS 的 all-in-one 系统 CLI，正从 Python 重写为 Rust。本文件说明如何从源码构建与使用、哪些平台已经验证过、以及和旧 Python 版有哪些差异。

## 前置

- Rust/Cargo 1.85 或更新版本（`Cargo.toml` 的 `rust-version`）。**MSRV 1.85 本身未验证**，开发与验证用的是 1.97.1。
- 不需要 Python，也不需要任何第三方 Rust 库（`Cargo.toml` 没有 `[dependencies]`）。

## 安装

从源码安装到 `PATH` 里的目录：

```sh
git clone https://github.com/askdaddy/msar.git
cd msar
cargo install --path . --locked
msar -V
```

`--locked` 使用仓库里的 `Cargo.lock`，保证依赖一致。不想安装到 `~/.cargo/bin` 时，直接构建并拷贝：

```sh
cargo build --release --locked
install -m 0755 target/release/msar ~/.local/bin/msar
```

## 使用

```sh
msar --help              # 无参数同样打印帮助
msar -V                  # 版本
msar --cpu               # 单次采样，终端输出
msar -a                  # 全部模块：CPU、内存、负载、磁盘 I/O、网络流量
msar -a -n 5 -o out.jsonl   # 每 5 秒一轮，追加 JSON 行
```

选项：`--cpu` `--mem` `--load` `--io` `--traffic` 选择模块，`-a/--all` 全选，`-n/--interval` 指定周期（省略值为 1 秒），`-o/--output` 追加本地 JSONL 文件，`-h/--help`、`-V/--version`。

无效间隔退出码 2；`-o` 指向 `http://` 或 `https://` 时明确拒绝（退出码 2），不会静默丢数据；输出文件不可写时退出码 1 并报告路径与原因。`SIGINT`/`SIGTERM` 在当前轮次结束后退出。

输出是每轮一行 JSON，模块为顶层键，不可用的指标为 `null`（不是缺失、也不是 0）：

```json
{"hostname":"Mac-mini.local","timestamp":1795517069.087,"Cpu":{"us":11.54,"sy":1.54,"id":86.92,"wa":null}}
```

## 支持矩阵

| 平台 | 架构 | 状态 | 证据 |
|---|---|---|---|
| Linux | x86_64 | **已验证** | 交叉编译 + `debian:13` 容器实跑，`--cpu`/`-a` 输出真实值 |
| Linux | aarch64 | **已验证** | 交叉编译 + `debian:13` 容器实跑，`--cpu`/`-a` 输出真实值 |
| macOS | arm64 | **已验证** | 本机实跑，五模块与 `sysctl`/`vm_stat`/`iostat`/`netstat` 对照 |
| Windows | x86_64 | **未验证** | 目标 `x86_64-pc-windows-msvc` 未在本机编译，未 CI 验证 |
| 其它 Unix | — | **不支持** | 未实现、未验证 |
| Rust 1.85（MSRV） | — | **未验证** | 只在 1.97.1 上验证过 |

平台差异是设计的一部分，不是缺陷：Linux 的 `wa`（iowait）有值，macOS 没有这个状态，因此 macOS 上 `Cpu.wa` 为 `null` 而不是 0。同理 macOS 的 `Mem.buffers`、`IO.util`/`await`/`svctm` 也是 `null`——平台真的没有这些计数器时，报 0 会伪装成一个从未做过的测量。

## 兼容差异

与旧 Python 版的差异，逐条都是刻意的修正或明确的兼容决策：

- **字段名沿用**旧版（`us`/`sy`/`id`/`wa`、`load1`/`load5`/`load15`、`total`/`free`/`buffers`/`cached`/`available`、`rrqms`/`wrqms`/`rs`/`ws`/`rsecs`/`wsecs`/`rkBs`/`wkBs`/`avgrq-sz`/`avgqu-sz`/`await`/`svctm`/`util`、`inbytes`/`outbytes`），历史消费方只需适配数值类型。
- **数值类型改为 JSON number**，旧版是 `"%.2f"` 字符串；不可用为 `null`，旧版会静默吞掉文件错误。
- **旧版已知计算缺陷已修正**：CPU `total` 不再重复计入 `guest`；内存按精确 key 匹配而不是子串；`svctm` 除以全部已完成 I/O 而不是只除读增量；设备用 `/sys/block` 分类而不是 `^\w*\d+`。
- **`-o http://…` 明确报错**，旧版的 HTTP 分支是空实现（静默不输出）。
- **未迁移**：后台 daemon、PID 文件、动态 Python 插件、`/proc/vmstat` 与 `/proc/net/snmp`，以及 HTTP 上传。这些在旧版也不可达或只是占位，确有需求再独立立项。

迁移的历史、完整阅读记录与已知问题见[总览 #1](https://github.com/askdaddy/msar/issues/1)与 [MIGRATION.md](MIGRATION.md)。

## 从旧 Python 版迁移

旧版运行 `python msar.py -a -n 5 -o out.jsonl`；Rust 版是 `msar -a -n 5 -o out.jsonl`，选项名与语义一致。消费方若要读数值，注意输出已是 JSON number 而不是字符串。旧的 `plugins/` 目录不再参与运行。

## 验证你自己的构建

本机一条命令跑齐本机能验证的部分（macOS 直跑 + 两个 Linux 目标交叉编译 + 容器实跑 + 黑盒套件）：

```sh
scripts/verify-local.sh              # 需要 cargo-zigbuild、zig 与 docker
scripts/verify-local.sh --no-container   # 跳过容器，Linux 运行时记为未验证
```

CI 在三个平台上跑同一套检查：`.github/workflows/verify.yml`。CI 只构建与验证，**不发布二进制、不打 tag、不自动合并**。

## 未验证的限制

以下都没有验证证据，不要当成已支持：Windows（含 `x86_64-pc-windows-msvc` 目标）、其它 Unix、Rust 1.85 MSRV、CI 中的 `ubuntu-24.04-arm` runner（首次运行时确认）、以及 macOS 上 CPU 的 1000 ms 采样窗口在其他机型上的普适性（只在 10 核 arm64 上测过）。
