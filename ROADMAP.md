# Rust 重写路线与 Python 迁移清单

msar 的长期目标是 Linux/Unix 下的 all-in-one 系统 CLI。首期聚焦 Linux 和 macOS 的 CPU、内存、负载、磁盘 I/O、网络流量监控。其他 Unix 平台尚未承诺支持，其他系统工具通过独立 Issue 扩展。

本文是维护用产品路线图。[#1](https://github.com/askdaddy/msar/issues/1) 的交付和关闭只表示规划完成，不表示 Rust 重写、平台适配、合并或发布完成。阶段规范、设计、执行计划与验收证据保留在各 Issue 评论中。

## 来源与当前进度

以下为 2026-11-20 核验快照；实时状态以链接中的 Issue/PR 和远端提交为准：

- Python 备份：远端 [`python-legacy`](https://github.com/askdaddy/msar/tree/python-legacy)，精确基线 `b280ad7703277191ac13f0bb01782814e6576ebf`。
- 默认分支 `ng` 仍在该 Python 基线，当前没有 Rust 构建入口。
- [#2](https://github.com/askdaddy/msar/issues/2) 已交付 [PR #7](https://github.com/askdaddy/msar/pull/7)，尚未合并。其已验收提交为 `b05ee931d6faecdae0bf447030b9f0c8d7cf7d97`，只提供 Rust CLI 基础、帮助/版本、输入/输出错误处理及项目指南，没有实现监控。
- Rust 项目上下文可从该提交的 [AGENTIC.md](https://github.com/askdaddy/msar/blob/b05ee931d6faecdae0bf447030b9f0c8d7cf7d97/AGENTIC.md) 阅读，不应假定这些文件已存在于默认分支。
- [#3](https://github.com/askdaddy/msar/issues/3) 至 [#6](https://github.com/askdaddy/msar/issues/6) 尚在研究阶段，监控迁移尚未实现。

可只读核对远端备份：

```sh
git ls-remote origin refs/heads/python-legacy
git show b280ad7703277191ac13f0bb01782814e6576ebf:msar.py
```

## 完整旧版清单

范围取自基线的 `git ls-tree`：13 个 Python 文件及 `requirements`。下面逐个对应职责与迁移归属，未接入主调用链的能力单独标明。

| 源路径 | 旧版职责 | Rust 迁移归属 |
| --- | --- | --- |
| `ICop.py` | CLI 参数注册、输出与参数访问抽象 | #3 按实际公共流程替换，不照搬 Python 抽象 |
| `IPlugin.py` | 插件 constructor/run 接口 | #3、#4、#5 采用明确模块边界，动态 ABI 延期 |
| `__init__.py` | 根包标记，无业务逻辑 | 无需迁移 |
| `define.py` | Linux `/proc` 路径、未使用的 SNMP/Traffic Server 常量 | #4 平台数据源；未使用常量不迁移，macOS 不沿用 `/proc` |
| `framework.py` | Console 信号处理；未接入 CLI 的 PID、daemon、Singleton | 信号由 #3 承接；其余延期，旧 Python 2/无效调用不照搬 |
| `msar.py` | 参数解析、插件装配、单次与周期运行 | #2 基础入口；#3 实现选择、调度及运行流程 |
| `output.py` | hostname 聚合、终端展示、JSON 文件追加；HTTP 方法占位 | #3 输出契约与错误处理；HTTP 首期明确拒绝 |
| `plugins/__init__.py` | 插件包标记，无业务逻辑 | 无需迁移 |
| `plugins/cpu.py` | 总体与分核 CPU 差分百分比 | #4 Linux、#5 macOS，修正 guest 重复累计及零差分边界 |
| `plugins/io.py` | 磁盘请求、扇区、吞吐、队列、延迟、利用率 | #4、#5；按设备身份匹配，不复刻行号配对和错误 tput 计算 |
| `plugins/load.py` | 1/5/15 分钟负载均值 | #4、#5；明确平台语义与数值类型 |
| `plugins/mem.py` | total/free/buffers/cached/act/inact 内存快照 | #4、#5；修正子串误匹配，统一单位与可用性 |
| `plugins/traffic.py` | 每接口收发字节速率 | #4、#5；处理接口名称、增删与计数回退 |
| `requirements` | straight.plugin==1.5.0、six==1.11.0 | 仅历史 Python 依赖；Rust 依赖按对应 Issue 设计决定 |

## 功能迁移与修正

兼容对象是旧版功能意图，已知错误不属于兼容要求。结构化字段、数值类型和单位须由 #3 冻结，不承诺旧 JSON 字节兼容。

| 功能 | 保留或新增的意图 | 修正或边界 | 归属 |
| --- | --- | --- | --- |
| 模块选择 | `--cpu`、`--mem`、`--load`、`--io`、`--traffic`、`-a` / `--all` | 未实现参数不能伪装成功 | #3 |
| 单次与周期采样 | `-n` / `--interval` 的核心意图及信号退出 | 校验间隔，以单调时钟协调共享窗口，避免各插件串行 sleep 造成窗口偏差 | #3 |
| 终端输出 | 可读的模块结果 | 平台不可用、权限不足、暖机不足与真实零值区分 | #3 |
| 文件输出 | `-o` / `--output`、JSON/JSONL 追加及主机/时间信息 | 错误可观察，可靠关闭资源，不重定向全局 stdout | #3 |
| CPU | 总体与分核使用情况 | 不重复计 guest；处理零差分、计数重置和 CPU 增删 | #4、#5 |
| 内存 | 系统内存快照 | 按字段准确识别，避免把 SwapCached 等写入 Cached；平台字段不能强行等同 | #4、#5 |
| 负载 | 1/5/15 分钟均值 | 明确单位与含义，不把未输出的队列数据称为已支持 | #4、#5 |
| 磁盘 I/O | 请求、吞吐和可提供的性能指标 | 稳定设备身份、现代设备名、增删和计数回退；重新确认延迟/利用率语义，旧 svctm 不直接照搬 | #4、#5 |
| 网络流量 | 接口收发速率 | 支持实际接口名称，按身份关联前后快照，处理新接口和计数回退 | #4、#5 |
| macOS 后端 | 新增 macOS 核心监控 | 不依赖 Linux `/proc`，缺少的指标明确不可用，不伪造数值 | #5 |
| HTTP 传输 | 延期，旧版并未实现 | 首期明确拒绝，不静默丢弃输出 | #3 定义拒绝行为，实际传输另行立项 |
| daemon/PID、动态第三方插件、未用常量 | 延期，不作为已可用能力迁移 | 需要时独立立项，不为未来需求预造框架 | 后续独立 Issue |

## 依赖、交付与集成顺序

| Issue | 交付物 | 依赖 |
| --- | --- | --- |
| [#1](https://github.com/askdaddy/msar/issues/1) | 重写路线、完整旧版清单与迁移矩阵 | 规划票，不代表整体实现完成 |
| [#2](https://github.com/askdaddy/msar/issues/2) | Rust CLI 基础与 Agentic 项目指南 | 已交付 PR #7；进入主分支需单独合并 |
| [#3](https://github.com/askdaddy/msar/issues/3) | 公共参数、统一采样、退出与输出流程 | #2 的代码进入所选集成基线 |
| [#4](https://github.com/askdaddy/msar/issues/4) | Linux 五类核心监控 | #3 的公共契约与代码基线 |
| [#5](https://github.com/askdaddy/msar/issues/5) | macOS 五类核心监控 | #3 的公共契约与代码基线 |
| [#6](https://github.com/askdaddy/msar/issues/6) | 跨平台验证、安装与迁移交付 | #3、#4、#5 |

依赖链为 **#2 → #3 → #4 / #5 → #6**。两个平台后端在公共契约稳定后可分别推进；这不表示已授权同时运行多个 Agent。

Issue 关闭表示已按工作流验收并交付 PR，不等于代码已合并。默认工作区从 `origin/ng` 建立，因此推进 #3 前先确认 PR #7 已进入目标基线；若采用其他集成分支，先明确授权、基线和计划，不能静默合并、cherry-pick 或把其他 Issue 的 worktree 当作本票工作区。

## 后续阶段的完成门槛

- **公共流程（#3）**：参数和模块选择可观察；单次/周期采样及信号退出行为可验证；输出 schema、数值、单位、时间与不可用语义明确；无效输入、文件失败、HTTP 拒绝不会静默成功。
- **Linux 后端（#4）**：五类指标有数据源和单位依据；固定样本覆盖正常差分、零窗口、重置和设备增删；Linux 实机或 CI 提供行为证据。
- **macOS 后端（#5）**：macOS 上实际采样并记录数据源、权限和架构；与公共语义一致；缺失项明确标注，不用 Linux 测试替代 macOS 验证。
- **验证交付（#6）**：两个平台构建与核心 CLI/输出行为有证据；源码安装、运行和迁移步骤可执行；列出兼容差异与尚未验证的范围。

以上是后续 Issue 的验收方向。具体字段、数值阈值、依赖库与实现接口在各自的 Spec/Design/Plan 中冻结，不能用本文跳过研究或在审查时临时添加通过门槛。

## 范围与授权

当前不清理旧 Python 源码，不新增许可证声明，不引入系统修改或提权行为，不自动合并 PR、打 tag 或发布版本。五类监控、平台适配和安装交付完成并验证后，再决定切换旧调用及清理旧代码。

这份路线图可以随已验证的新进展更新；动态验收结论和提交 SHA 仍以相应 Issue/PR 为准。
