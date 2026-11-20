# 开发指南

## 环境

需要能从 PATH 执行的 Rust/Cargo 1.85 或更新版本，检查格式和 lint 还需要 rustfmt、Clippy。`Cargo.toml` 声明 1.85，最低版本兼容性尚未验证。首次开发在 macOS arm64、Rust/Cargo 1.97.1 上验证；Linux 和跨平台矩阵属于 #6。

Python 不是 Rust 构建依赖。QA 的标准库黑盒脚本使用 Python 3.11 或更新版本，放在 `test/`。旧版 Python 的 `requirements` 只属于历史实现。

## 本地构建与运行

```sh
rustc --version
cargo --version
cargo build --locked
cargo run --locked -- --help
cargo run --locked -- --version
```

Cargo.lock 随 binary 提交；新增依赖必须有计划依据并同步锁文件。目前无需下载第三方库。

```sh
cargo fmt --check
cargo clippy --locked -- -D warnings
cargo test --locked
```

当前没有 Rust 单元测试，`cargo test` 只证明测试目标能构建，不代表 CLI 行为通过。QA 黑盒验证见[验收指南](VERIFICATION.md)。

## 从 Issue 到交付

先阅读 [AGENTS.md](AGENTS.md) 和当前 Issue。默认分支是 `ng`；一 Issue 一独立 worktree 和 `riper/<N>` 分支，按 iloop 先认领、研究、比较方案并冻结计划，再由开发实现。项目文档描述维护知识，Spec/Design/Plan/验收报告留在 Issue 评论。

本机装有 iloop 时，可从项目目录调用安装目录中的 `scripts/git-ops.sh`；路径取实际安装位置，例如：

```sh
bash "$HOME/.agents/skills/iloop/scripts/git-ops.sh" doctor
bash "$HOME/.agents/skills/iloop/scripts/git-ops.sh" workspace start <N>
```

`<N>` 是占位符，替换成实际 Issue 编号；不要直接执行含占位符的示例。进入脚本输出的独立工作区后，所有命令显式指定该目录。提交前用当前角色执行 guard，例如开发提交前运行 `git-ops.sh --role developer guard developer <N>`。

开发自查后记录提交 SHA、计划完成项和未验证项，交 QA 独立验收。QA 按协议推送并创建 PR；默认不自动合并、发布或打 tag。后续安装与平台支持证据由 #6 补齐。
