# msar 项目上下文

## 目标与当前状态

msar 的长期目标是在 Linux/Unix 下提供 all-in-one 系统 CLI。Rust 重写的第一阶段以 Linux/macOS 为目标，覆盖原 Python 版本的 CPU、内存、负载、磁盘 I/O 和网络流量监控；后续系统工具需单独立项。

当前 Rust 只实现帮助、版本及参数/输出错误处理，没有监控后端、周期采样或指标输出。源码入口为 `src/main.rs`，构建元数据为 `Cargo.toml` / `Cargo.lock`，无第三方 Rust 依赖。

旧 Python 入口 `msar.py` 经 `ICop.py` / `IPlugin.py` 加载 `plugins/`，由 `output.py` 输出。完整阅读记录及已知问题在[总览 #1](https://github.com/askdaddy/msar/issues/1)。历史版本的运行问题不应转化为 Rust 的兼容要求。

## 建议阅读顺序

1. [AGENTS.md](AGENTS.md)：工作区、角色、计划与验证约束。
2. 当前 Issue 的全部正文、评论和标签：唯一有效的阶段事实与验收基线。
3. [ARCHITECTURE.md](ARCHITECTURE.md)：当前结构与计划中的模块边界。
4. [DEVELOPMENT.md](DEVELOPMENT.md)：开发命令、依赖和交付方法。
5. [VERIFICATION.md](VERIFICATION.md)：行为验证和平台证据限制。
6. [MIGRATION.md](MIGRATION.md)：旧版功能、备份与迁移差异。

## 接续工作

- [#2](https://github.com/askdaddy/msar/issues/2) 交付 CLI 基础和本文档体系，实际交付状态以 Issue/PR 为准。
- [#3](https://github.com/askdaddy/msar/issues/3) 冻结参数、共享采样窗口、输出数据结构和错误语义，再实现公共流程。
- [#4](https://github.com/askdaddy/msar/issues/4) / [#5](https://github.com/askdaddy/msar/issues/5) 实现 Linux/macOS 后端，不将 Linux `/proc` 读法用于 macOS。
- [#6](https://github.com/askdaddy/msar/issues/6) 补齐跨平台验证和安装交付。

本文只保留稳定上下文和导航。动态进度、阶段全文和验收 SHA 留在远端 Issue/PR，避免本地副本过期。
