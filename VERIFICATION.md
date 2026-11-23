# 验收指南

## 当前 CLI 行为

| 输入或场景 | 预期行为 |
| --- | --- |
| 无参数、`-h`、`--help` | stdout 帮助包含用法、选项与后端尚未实现的说明；stderr 空；退出 0 |
| `-V`、`--version` | stdout 为 `msar <Cargo 包版本>` 加换行；stderr 空；退出 0 |
| `--cpu`/`--mem`/`--load`/`--io`/`--traffic`/`-a` | 采样一轮并输出；退出 0 |
| 未知参数 | stdout 空；stderr 定位参数并提示帮助；退出 2 |
| `-n` 负数、`0`、非整数 | stderr 报告无效间隔；退出 2 |
| `-n` 无值 | 视为 1 秒周期（不吞掉后续选项） |
| `-o http://…` 或 `https://…` | stderr 明确说明 HTTP 未实现；退出 2；不创建文件 |
| `-o` 指向不可写路径 | stderr 含路径与原因；退出 1 |
| 终端输出 | 含模块标题，不可用字段打印 `unavailable` |
| `-o <file>` | 追加一行合法 JSON，含 `hostname`、`timestamp` 与模块字段；不可用为 `null` |
| `SIGINT` / `SIGTERM` | 当前轮次结束后优雅退出 |
| 非 UTF-8 参数 | 可观察的参数错误，不 panic |
| stdout 写失败 | stderr 报错并非零退出 |
| 下游关闭导致 BrokenPipe | 正常退出，不 panic |

## 执行方式

```sh
cargo build --locked
cargo fmt --check
cargo clippy --locked -- -D warnings
cargo test --locked
```

QA 在 `test/cli_smoke.py` 提供进程级黑盒验收后，运行：

```sh
python3 test/cli_smoke.py target/debug/msar
```

脚本应检查 stdout、stderr、退出状态、无效及非 UTF-8 参数、输出失败和 BrokenPipe，并校验项目文档的本地相对链接。文档需人工复核目标/现状区分、平台边界、角色流程和迁移信息；链接有效不能证明内容正确。

## 证据边界

当前验证环境为 macOS arm64 和 Rust/Cargo 1.97.1。没有 Linux 行为、Rust 1.85 MSRV、核心指标正确性或跨平台 CI 的通过证据。它们属于后续任务；本期 CLI 验收不能替代监控验收（#4/#5）。`cargo test` 覆盖窗口差分保护、参数解析、JSON 渲染与文件追加的单元级断言，不能当作进程级黑盒验证。

未来监控验收需要固定样本验证计数差分和单位、设备增删/重置、不可用指标、信号退出、输出失败，以及对应平台的实机或 CI 行为证据。具体标准在对应 Issue 中冻结，不追溯添加为当前基础 Issue 的通过门槛。

QA 将逐项 PASS/FAIL/无法验证、环境、实际命令和已验收 SHA 写回 Issue。当前会话可切换开发/QA 角色进行复核，但不宣称是真实独立 Agent E2E 测试。验收 PASS 仍需推送并核验 PR 才算交付；PR 交付不代表已合并或发布。
