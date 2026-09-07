# ENVIRONMENT

环境快照：软件版本、模型 digest。
存在的理由是可归因——升级导致的结果漂移，要能对上是哪一次环境变化引起的。

**统一为本 `.md` 单文件**（v0.7 §19 写 `.md`、§18.3 写 `.txt`，取 `.md`）；
原始 `pip freeze` 输出以代码块嵌在本文件内，不另存 `ENVIRONMENT.txt`。

> ⚠️ 本文件描述的是**岸端本机（Mac Studio）**的环境。
> 下列字段在本轮全部为 `Not captured yet`：`.venv` 尚未建立、`ollama` 不可用，
> 且本轮工作在 Linux 远程容器中进行——在该容器采集会记录到错误的机器。
> 首次 baseline 须在岸端本机上采集，已记入 `BACKLOG.md`。

## 采集元信息

| 字段 | 值 |
|---|---|
| 采集时间 | Not captured yet |
| 采集机器 | Not captured yet |
| 采集命令 | Not captured yet |

## 硬件与系统

| 字段 | 值 |
|---|---|
| 机型 / 芯片 | Not captured yet |
| 内存 | Not captured yet |
| 操作系统版本 | Not captured yet |

## Python 环境

| 字段 | 值 |
|---|---|
| Python 版本 | Not captured yet |
| 虚拟环境路径 | Not captured yet |

原始 `pip freeze` 输出：

```text
Not captured yet
```

## 推理运行时

| 字段 | 版本 / commit |
|---|---|
| Ollama | Not captured yet |
| llama.cpp | Not captured yet |

## 模型与 digest

模型必须记 digest，不能只记名字——同名 tag 会被上游重推。

| 用途 | 模型 | digest | 量化 |
|---|---|---|---|
| 主模型 | Not captured yet | Not captured yet | Not captured yet |
| Teacher | Not captured yet | Not captured yet | Not captured yet |
| Embedder | Not captured yet | Not captured yet | Not captured yet |
| Reranker | Not captured yet | Not captured yet | Not captured yet |

原始 `ollama list` 输出：

```text
Not captured yet
```
