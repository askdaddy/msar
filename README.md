# msar

面向 Linux/Unix 的 all-in-one 系统 CLI，正在从 Python 重写为 Rust。首期目标平台为 Linux 和 macOS，先迁移系统监控，再通过独立 Issue 扩展工具能力。其他 Unix 平台尚未承诺支持。

## 当前可用

本分支已建立 Rust CLI 基础，支持无参数帮助、`-h` / `--help` 和 `-V` / `--version`。当前监控模块尚未实现；旧版监控参数会报错退出，不会返回模拟指标。当前验证环境为 macOS，Linux 验证由后续任务完成。

```sh
cargo build --locked
cargo run --locked -- --help
cargo run --locked -- --version
```

需要 Rust/Cargo 1.85 或更新版本。1.85 是工程声明的最低版本；目前尚未验证最低版本兼容性。无需 Python 或第三方 Rust 库即可构建 Rust 入口。

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
