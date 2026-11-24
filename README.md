# msar

面向 Linux/Unix 的 all-in-one 系统 CLI，正在从 Python 重写为 Rust。首期目标平台为 Linux 和 macOS，先迁移系统监控，再通过独立 Issue 扩展工具能力。其他 Unix 平台尚未承诺支持。

## 当前可用

Rust CLI 已支持模块选择、单次/周期采样、信号退出，以及终端和 JSONL 文件输出。平台指标读取尚未实现（Linux 见 #4，macOS 见 #5），因此每个模块当前以 `unavailable` / `null` 报告字段，不返回模拟指标。当前验证环境为 macOS，Linux 行为由后续任务验证。

```sh
cargo build --locked
cargo run --locked -- --help          # 无参数同样打印帮助
cargo run --locked -- --cpu           # 单次采样，终端输出
cargo run --locked -- -a -n 2 -o out.jsonl   # 每 2 秒一轮，追加 JSON 行
```

选项：`--cpu` `--mem` `--load` `--io` `--traffic` 选择模块，`-a/--all` 全选，`-n/--interval` 指定周期（省略值为 1 秒），`-o/--output` 追加本地 JSONL 文件，`-h/--help`、`-V/--version`。

错误均可观察：无效间隔退出码 2；`-o` 指向 `http://` 或 `https://` 时明确拒绝（退出码 2），不会静默丢数据；输出文件不可写时退出码 1 并报告路径与原因。`SIGINT`/`SIGTERM` 在当前轮次结束后优雅退出。

需要 Rust/Cargo 1.85 或更新版本。1.85 是工程声明的最低版本；目前尚未验证最低版本兼容性。构建不需要 Python 或第三方 Rust 库。

## 重写路线

| Issue | 交付范围 | 依赖 |
| --- | --- | --- |
| [#1](https://github.com/askdaddy/msar/issues/1) | 重写总览、旧版完整阅读与迁移矩阵 | 总览 |
| [#2](https://github.com/askdaddy/msar/issues/2) | Rust CLI 基础与 Agentic 项目文档 | #1 |
| [#3](https://github.com/askdaddy/msar/issues/3) | 统一采样、模块选择、终端和 JSON 输出 | #2 |
| [#4](https://github.com/askdaddy/msar/issues/4) | Linux 五类核心监控 | #3 |
| [#5](https://github.com/askdaddy/msar/issues/5) | macOS 五类核心监控 | #3 |
| [#6](https://github.com/askdaddy/msar/issues/6) | 跨平台验证、安装和迁移交付 | #3、#4、#5 |

监控范围包括 CPU、内存、负载、磁盘 I/O、网络流量。具体参数和数据契约在对应 Issue 中冻结，本表不代表它们已经实现。

## 项目文档

- [Agent 协作约束](AGENTS.md)与[项目上下文入口](AGENTIC.md)
- [架构与模块边界](ARCHITECTURE.md)
- [开发流程与命令](DEVELOPMENT.md)
- [验收方法与证据限制](VERIFICATION.md)
- [Python 版本及迁移说明](MIGRATION.md)

旧 Python 默认分支快照保存在远端 [`python-legacy`](https://github.com/askdaddy/msar/tree/python-legacy)。当前目录中的旧源码仍保留供对照；Rust 首批交付不表示全量重写完成。仓库尚未确定许可证，本次不新增授权声明。
