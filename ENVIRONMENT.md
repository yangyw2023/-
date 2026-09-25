# ENVIRONMENT

环境快照：软件版本、模型 digest。
存在的理由是可归因——升级导致的结果漂移，要能对上是哪一次环境变化引起的。

**统一为本 `.md` 单文件**（v0.7 §19 写 `.md`、§18.3 写 `.txt`，取 `.md`）；
原始 `pip freeze` 输出以代码块嵌在本文件内，不另存 `ENVIRONMENT.txt`。

> ⚠️ 本文件描述的是**岸端本机（Mac Studio）**的环境。
> 下列字段在本轮全部为 `Not captured yet`：`.venv` 尚未建立、`ollama` 不可用，
> 且本轮工作在 Linux 远程容器中进行——在该容器采集会记录到错误的机器。
> 首次 baseline 须在岸端本机上采集，已记入 `BACKLOG.md`。

采集时间：2026-09-07
采集机器：Mac Studio / Apple M3 Ultra
操作系统：macOS 15.6
Python：3.12.14
虚拟环境：/Users/developer/Documents/ship-rag/.venv
Ollama：0.23.1
llama.cpp：0.4.0
Poppler：26.09.0
MLX：0.32.2
MLX-LM：0.31.3
MLX device：Device(gpu, 0)

annotated-doc==0.0.5
annotated-types==0.8.0
anyio==4.15.1
certifi==2026.7.22
click==8.5.0
deprecation==2.1.0
filelock==3.32.5
fsspec==2026.7.0
h11==0.16.0
hf-xet==1.6.0
httpcore==1.0.9
httpx==0.28.1
huggingface_hub==1.30.0
idna==3.19
Jinja2==3.1.6
lance-namespace==0.12.0
lance-namespace-urllib3-client==0.12.0
lancedb==0.38.0
markdown-it-py==4.2.0
MarkupSafe==3.0.3
mdurl==0.1.2
mlx==0.32.2
mlx-lm==0.31.3
mlx-metal==0.32.2
numpy==2.5.3
packaging==26.3
protobuf==7.36.1
pyarrow==25.0.1
pydantic==2.13.5
pydantic_core==2.46.5
Pygments==2.21.0
python-dateutil==2.9.0.post0
PyYAML==6.0.3
regex==2026.9.3
rich==15.0.0
safetensors==0.8.0
sentencepiece==0.2.2
shellingham==1.5.4
six==1.17.0
tokenizers==0.23.2
tqdm==4.70.0
transformers==5.16.1
typer==0.27.2
typing-inspection==0.4.4
typing_extensions==4.16.0
urllib3==2.7.0

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
