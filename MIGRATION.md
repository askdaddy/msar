# Python 到 Rust 的迁移

## 历史基线

原默认主分支为 `ng`，并非 `master`。Python 快照已推送到远端 [`python-legacy`](https://github.com/askdaddy/msar/tree/python-legacy)，基线提交为 `b280ad7703277191ac13f0bb01782814e6576ebf`。可只读检查：

```sh
git show python-legacy:msar.py
git ls-remote origin refs/heads/python-legacy
```

新克隆若无本地 `python-legacy` 分支，先 `git fetch origin python-legacy`，再用 `git show origin/python-legacy:msar.py`。当前工作区仍保留所有旧 Python 源码和 `requirements`，供迁移对照。

## 旧版完整功能清单

| 旧路径 | 实际职责 | Rust 处理 |
| --- | --- | --- |
| `msar.py` | 参数、动态插件、一次/周期运行 | #2 基础入口，#3 迁移运行流程 |
| `ICop.py` / `IPlugin.py` | 参数/输出与插件抽象 | 按实际 Rust 模块边界替换，不照搬动态 ABI |
| `output.py` | 终端、文件 JSON 追加 | #3；HTTP POST 原本只是占位 |
| `plugins/cpu.py` | CPU 总体和分核百分比 | #4 Linux，#5 macOS |
| `plugins/mem.py` | 内存快照 | #4 / #5 |
| `plugins/load.py` | 1/5/15 分钟负载 | #4 / #5 |
| `plugins/io.py` | 磁盘 I/O 差分和速率 | #4 / #5 |
| `plugins/traffic.py` | 接口收发字节速率 | #4 / #5 |
| `define.py` | Linux 路径及未用常量 | 拆入实际平台后端，不在 macOS 读 `/proc` |
| `framework.py` | Console 信号及未接入的 PID/daemon/Singleton | 信号由 #3 承接；未用能力延期 |
| 两个 `__init__.py` | 包标记 | 不需要迁移 |
| `requirements` | straight.plugin、six | 仅历史 Python 依赖 |

完整逐文件阅读证据见[总览 #1](https://github.com/askdaddy/msar/issues/1)。

## 兼容与修正

旧版 `--cpu`、`--mem`、`--load`、`--io`、`--traffic`、`-a` / `--all`、`-n` / `--interval`、`-o` / `--output` 的核心使用意图纳入 #3。当前 Rust 只接受帮助和版本；不能直接替换旧版监控调用。结构化输出的字段、数值类型、单位和兼容策略待 #3 冻结，不承诺 JSON 字节兼容。

迁移时修正已观察到的问题：CPU guest 重复计数和零差分；内存字段子串误匹配；磁盘行位置配对、现代设备名过滤和 tput 计算；网络接口名称、增删和计数回退；串行 sleep 导致窗口不一致；文件错误吞掉和资源未可靠关闭。旧 daemon/PID 辅助包含 Python 2 和无效调用，不作为可用功能照搬。

旧版只实现 Linux 监控。macOS 是新增后端；不可用指标需明确呈现。HTTP 传输、后台 daemon、动态第三方插件及其他系统工具不在首期迁移范围，确有需求再独立立项。

## 替换条件

待 #3–#6 的输出契约、两平台指标和安装验证完成，再决定切换旧调用及清理旧源码。本期 CLI 基础和文档交付不等于迁移完成；不自动修改默认分支、合并 PR 或发布版本。仓库未确定许可证，本次不新增授权条款。
