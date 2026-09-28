"""canonical 语料构建的【权威】身份导出（builder-owned）。

本模块属于语料构建实现（ingest/build_corpus.py 及其 Phase B 构建路径），不属于契约层。
下游（GoldChunkMap resolver 等）只能 import 这里的导出，不得手写 builder 名、
手写 chunker_config 字符串、复制参数列表或从无关常量推断。

导出:
  CORPUS_BUILDER_NAME              构建语义实现族的名字（含版本号，见下方版本规则）
  effective_chunker_config_identity()  构建实际消费的【数值型】分块参数，按契约规定的格式序列化
  construction_rules_identity()    构建实际消费的【全部静态构建规则】（数值 + 正则 + 抽取参数 +
                                   准入集合 …）的值指纹
  construction_rules_manifest()    上一项的明文清单（审计用）

依赖分类的单一来源是 CONSTRUCTION_DEPENDENCY_REGISTRY。tests/test_builder_identity.py 用 AST
从 build_corpus.main / build 出发，找出构建代码可达地读取的每一个模块级常量，并要求它们
【全部】在本登记表中被分类 —— 构建代码新读一个常量而没有登记，测试失败（防静默漏登）。

⚠️ 本模块【不】绑定的东西（已知盲区，不是遗漏）:
  - 构建运行时输入: 原始 PDF、accepted OCR artifact 集合、--doc-lang 实参、
    pdftotext / pdfinfo 可执行文件的版本。它们因构建而异，不是静态身份；
    其结果由 corpus_chunks_sha256 锁定。
  - 函数体内的逻辑与字面量（如块拼接用的 "\\n\\n"、合并短块的方向）。
    它们只由 CORPUS_BUILDER_NAME 的版本规则覆盖，依赖人按规则递增版本。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import contracts  # noqa: E402
from components.parsers import citation_gate, kaiva_pdf, ocr_artifact, page_states, phase_b_ingest  # noqa: E402
from ingest import build_corpus  # noqa: E402

# ==============================================================================
# 构建器名与版本规则
# ==============================================================================

# 版本递增规则（BUILDER_NAME_VERSIONING）:
#   【必须】递增: canonical 构建语义改变，且可能改变以下任一项 ——
#       页准入 / primary body 选择 / body 字节 / chunk 边界 / chunk 顺序 / chunk id 语义。
#     包括只改函数体逻辑、而本模块登记值不变的情形（construction_rules_identity 看不到这种改动）。
#   【不得】递增: 纯重构 / 改名 / 注释与 docstring / 测试 / 日志 / 只影响审计字段（page_quality
#     的诊断列、ingest_report）/ 本身份导出 API 的改动 / 不改变构建语义的实现清理。
#   版本号不是语料相等性证明：语料身份永远由 corpus_chunks_sha256 锁定。
#   名字只允许文件名安全字符（它会进入 GoldChunkMap.filename()），不含 commit、时间、路径、语料哈希。
CORPUS_BUILDER_NAME: str = "kaiva_phase_b_builder_v1"

# ==============================================================================
# 构建路径依赖登记表（单一来源）
# ==============================================================================

# 分类:
#   CHUNKER_CONFIG        数值型分块参数；进入 effective_chunker_config_identity() 与规则指纹
#   CONSTRUCTION_RULE     静态构建规则；进入 construction_rules_identity()
#   RUNTIME_INPUT_DEFAULT 运行时输入的默认值；实际取值按构建而异，不进静态身份（见模块 docstring）
#   AUDIT_ONLY            只影响审计输出（page_quality 诊断列），不影响 chunk
#   OPERATIONAL           超时、文件名、哈希块大小、store 布局等，不改变任何输出字节
#   VOCABULARY            内部状态/动作/通道标签；只在代码内部做同名比较，取值本身不改变行为
#   DOWNSTREAM_ONLY       AST 可达性分析保守到达、但构建并不调用的契约常量（检索/打包侧）
CHUNKER_CONFIG = "CHUNKER_CONFIG"
CONSTRUCTION_RULE = "CONSTRUCTION_RULE"
RUNTIME_INPUT_DEFAULT = "RUNTIME_INPUT_DEFAULT"
AUDIT_ONLY = "AUDIT_ONLY"
OPERATIONAL = "OPERATIONAL"
VOCABULARY = "VOCABULARY"
DOWNSTREAM_ONLY = "DOWNSTREAM_ONLY"
IDENTITY_CATEGORIES: frozenset[str] = frozenset({CHUNKER_CONFIG, CONSTRUCTION_RULE})

_MODULES: dict[str, Any] = {
    "contracts": contracts,
    "kaiva_pdf": kaiva_pdf,
    "citation_gate": citation_gate,
    "page_states": page_states,
    "phase_b_ingest": phase_b_ingest,
    "ocr_artifact": ocr_artifact,
    "build_corpus": build_corpus,
}

CONSTRUCTION_DEPENDENCY_REGISTRY: dict[str, str] = {
    # ---- contracts ----
    "contracts.CHARS_PER_TOKEN_EST": CHUNKER_CONFIG,          # kaiva_pdf._est_tokens
    "contracts.CHUNK_MIN_CHARS": CHUNKER_CONFIG,              # 合并短块 + 页准入
    "contracts.CHUNK_TARGET_TOKENS": CHUNKER_CONFIG,          # _split_page_body / _split_by_lines
    "contracts.CORPUS_LANG_DEFAULT": RUNTIME_INPUT_DEFAULT,   # build_corpus --doc-lang 默认值
    "contracts.CITATION_HEADER_EST_TOKENS": DOWNSTREAM_ONLY,  # 只经 Chunk.est_prompt_tokens，构建不调用
    "contracts.TOP_K_RETRIEVE": DOWNSTREAM_ONLY,              # 只经 Retriever.search 默认参数
    "contracts.HitOrigin": DOWNSTREAM_ONLY,                   # Hit 的类型标注
    # ---- kaiva_pdf：抽取、页眉页脚剥离、元数据、分块规则 ----
    "kaiva_pdf.PDFTOTEXT_ARGS": CONSTRUCTION_RULE,
    "kaiva_pdf.PAGE_SEPARATOR": CONSTRUCTION_RULE,
    "kaiva_pdf.HEADER_SCAN_LINES": CONSTRUCTION_RULE,
    "kaiva_pdf.OCR_FOOTER_SCAN_LINES": CONSTRUCTION_RULE,
    "kaiva_pdf.OCR_LABEL_LINE_MAX_CHARS": CONSTRUCTION_RULE,
    "kaiva_pdf.UNKNOWN_SECTION": CONSTRUCTION_RULE,            # 写入 Chunk.section
    "kaiva_pdf.FILENAME_DOC_ID_MAP": CONSTRUCTION_RULE,        # 决定 doc_id → chunk id
    "kaiva_pdf.KNOWN_DOC_IDS": CONSTRUCTION_RULE,
    "kaiva_pdf._LABEL_ALTERNATION": CONSTRUCTION_RULE,
    "kaiva_pdf._LABEL_KEY_ALIASES": CONSTRUCTION_RULE,
    "kaiva_pdf._LABEL_RE": CONSTRUCTION_RULE,
    "kaiva_pdf._LABEL_VALUE_GAP_RE": CONSTRUCTION_RULE,
    "kaiva_pdf._PRINTED_PAGE_RE": CONSTRUCTION_RULE,
    "kaiva_pdf._NOISE_RES": CONSTRUCTION_RULE,
    "kaiva_pdf._DASHES": CONSTRUCTION_RULE,
    "kaiva_pdf._CHAPTER_RE": CONSTRUCTION_RULE,
    "kaiva_pdf._NUMBERED_TITLE_RE": CONSTRUCTION_RULE,
    "kaiva_pdf._PARA_SPLIT_RE": CONSTRUCTION_RULE,
    "kaiva_pdf.PDFTOTEXT_TIMEOUT_S": OPERATIONAL,
    "kaiva_pdf.PDFINFO_TIMEOUT_S": OPERATIONAL,
    # ---- citation_gate：section 元数据门（决定隔离与 Chunk.section）----
    "citation_gate.SECTION_MAX_CHARS": CONSTRUCTION_RULE,
    "citation_gate._OCR_SECTION_LABEL_RE": CONSTRUCTION_RULE,
    "citation_gate.CHANNEL_NATIVE": VOCABULARY,
    "citation_gate.CHANNEL_OCR": VOCABULARY,
    "citation_gate.CHANNEL_NONE": VOCABULARY,
    "citation_gate.EXPLICIT_SUPPORTED": VOCABULARY,
    "citation_gate.UNCERTAIN": VOCABULARY,
    "citation_gate.FAILED": VOCABULARY,
    "citation_gate.KIND_EXPLICIT_LABEL": VOCABULARY,
    "citation_gate.KIND_INHERITED": VOCABULARY,
    "citation_gate.KIND_NONE": VOCABULARY,
    # ---- page_states：正文状态判定（决定 OCR 与准入）----
    "page_states.LATIN_SCRIPT_LANGS": CONSTRUCTION_RULE,
    "page_states.GARBLING_CODEPOINT": CONSTRUCTION_RULE,
    "page_states._ALPHA_TOKEN_RE": CONSTRUCTION_RULE,
    "page_states._NON_CONTROL_C0": CONSTRUCTION_RULE,
    "page_states.NATIVE_USABLE": VOCABULARY,
    "page_states.NATIVE_UNUSABLE": VOCABULARY,
    "page_states.NATIVE_INSUFFICIENT": VOCABULARY,
    "page_states.NATIVE_UNCERTAIN": VOCABULARY,
    "page_states.OCR_NOT_ATTEMPTED": VOCABULARY,
    "page_states.OCR_USABLE": VOCABULARY,
    "page_states.OCR_DEGRADED": VOCABULARY,
    "page_states.OCR_FAILED": VOCABULARY,
    "page_states.OCR_REASON_NOT_ATTEMPTED": VOCABULARY,
    "page_states.OCR_REASON_ENGINE_FAILED": VOCABULARY,
    "page_states.OCR_REASON_TEXT_EMPTY_RAW": VOCABULARY,
    "page_states.OCR_REASON_EMPTY_AFTER_STRIP": VOCABULARY,
    "page_states.POLICY_ADMIT": VOCABULARY,
    "page_states.POLICY_HOLD": VOCABULARY,
    "page_states.POLICY_REJECT": VOCABULARY,
    "page_states.COMPLETENESS_PRESUMED": AUDIT_ONLY,
    "page_states.COMPLETENESS_SUSPECTED": AUDIT_ONLY,
    "page_states.COMPLETENESS_NOT_ASSESSED": AUDIT_ONLY,
    # ---- phase_b_ingest：body 选择与动作 ----
    "phase_b_ingest.OCR_ATTEMPT_STATES": CONSTRUCTION_RULE,    # 哪些正文状态走 OCR
    "phase_b_ingest.ACTION_ADMITTED_NATIVE": VOCABULARY,
    "phase_b_ingest.ACTION_ADMITTED_OCR": VOCABULARY,
    "phase_b_ingest.ACTION_QUARANTINED": VOCABULARY,
    "phase_b_ingest.ACTION_SKIPPED_NONCONTENT": VOCABULARY,
    "phase_b_ingest.TERMINAL_ACTIONS": VOCABULARY,
    "phase_b_ingest.BODY_CHANNEL_NATIVE": VOCABULARY,
    "phase_b_ingest.BODY_CHANNEL_OCR": VOCABULARY,
    "phase_b_ingest.BODY_CHANNEL_NONE": VOCABULARY,
    # ---- ocr_artifact：只读 store 的布局与校验（artifact 内容是运行时输入）----
    "ocr_artifact.ACCEPTED_DIRNAME": OPERATIONAL,
    "ocr_artifact.ACCEPTED_INDEX_FILENAME": OPERATIONAL,
    "ocr_artifact.CANDIDATE_DIRNAME": OPERATIONAL,
    "ocr_artifact.REPRODUCIBILITY_LOG_FILENAME": OPERATIONAL,
    "ocr_artifact.ARTIFACT_REQUIRED_FIELDS": OPERATIONAL,
    "ocr_artifact._JSON_KW": OPERATIONAL,
    # ---- build_corpus：入口 ----
    "build_corpus.PDF_SUFFIX": CONSTRUCTION_RULE,              # 决定哪些源文件进入构建
    "build_corpus.CHUNKS_FILENAME": OPERATIONAL,
    "build_corpus.PAGE_QUALITY_FILENAME": OPERATIONAL,
    "build_corpus.REPORT_FILENAME": OPERATIONAL,
    "build_corpus.REPORT_COLUMNS": OPERATIONAL,
    "build_corpus.HASH_READ_BLOCK_BYTES": OPERATIONAL,
    "build_corpus.CORPUS_HASH_PREFIX_LEN": OPERATIONAL,
    "build_corpus.VISUAL_FEATURE_COLUMN": AUDIT_ONLY,
    "build_corpus.VISUAL_LABEL_POS": AUDIT_ONLY,
    "build_corpus.VISUAL_LABEL_NEG": AUDIT_ONLY,
}


def _resolve(key: str) -> Any:
    """登记表键 → 当前运行时的值（调用时读取，不缓存）。键不存在即 KeyError / AttributeError。"""
    module_name, attr = key.split(".", 1)
    return getattr(_MODULES[module_name], attr)


def _canonical(value: Any) -> Any:
    """把登记值转成确定性的 JSON 可序列化形式。无法规范化的类型抛 TypeError，不猜。"""
    if isinstance(value, re.Pattern):
        return {"re": value.pattern, "flags": int(value.flags)}
    if isinstance(value, dict):
        return [[str(k), _canonical(v)] for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))]
    if isinstance(value, (tuple, list)):
        return [_canonical(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_canonical(v) for v in value), key=lambda v: json.dumps(v, ensure_ascii=False))
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"无法规范化的构建依赖值类型: {type(value).__name__}")


def effective_chunker_config_identity() -> str:
    """构建实际消费的数值型分块参数的确定性序列化。

    契约:
      - 参数集合 = CONSTRUCTION_DEPENDENCY_REGISTRY 中分类为 CHUNKER_CONFIG 的条目，
        不是另一份手抄列表；值在调用时从其所属模块读取
      - 序列化按 core.contracts 对 chunker_config 的格式要求:
        键 = 常量名小写，按字典序排列，`key=value`，以 ";" 连接
      - 确定、与语料无关；不含时间、路径、commit
    """
    params = {key.split(".", 1)[1].lower(): _resolve(key)
              for key, category in CONSTRUCTION_DEPENDENCY_REGISTRY.items() if category == CHUNKER_CONFIG}
    return ";".join(f"{name}={params[name]}" for name in sorted(params))


def construction_rules_manifest() -> list[list[Any]]:
    """全部身份相关静态构建依赖的明文清单: [[登记键, 分类, 规范化值], ...]，按登记键排序。

    包含 CHUNKER_CONFIG 与 CONSTRUCTION_RULE 两类；其余分类不进入身份。
    """
    return [[key, category, _canonical(_resolve(key))]
            for key, category in sorted(CONSTRUCTION_DEPENDENCY_REGISTRY.items())
            if category in IDENTITY_CATEGORIES]


def construction_rules_identity() -> str:
    """construction_rules_manifest() 的 SHA-256（64 位小写十六进制）。

    任一身份相关静态构建依赖的值改变，本值即改变；非身份分类的值改变，本值不变。
    """
    payload = json.dumps(construction_rules_manifest(), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
