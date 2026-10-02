#!/usr/bin/env python3
"""Citation section metadata 的 ground-truth 审计（诊断实验，只读）。

不修改 parser / corpus / testset / contracts，不做 OCR。

用法:
    python3 scripts/audit_citation_sections.py \\
        --pdf-dir "raw/KAIVA - Manuals" \\
        --corpus corpus/chunks.jsonl \\
        --testset eval/testset_v5_3.jsonl \\
        --out-csv experiments/parser_audit/_citation_section_audit.csv \\
        --out-log experiments/parser_audit/_citation_section_audit.log

产出:
    --out-csv  记录类型 record_type ∈ {gold_citation, tacm_native_audit, anomaly_candidate}。
               同一页可同时属于多类：每类各出一行，并用 is_gold_citation_page /
               is_tacm_native_audit_page / is_anomaly_candidate 三个布尔列交叉标注，不去重。
    --out-log  环境指纹、所有判据（先写判据再给结果）、各节汇总。
    两者逐字节确定性：不含时间戳、耗时或其他运行期可变量；所有集合与列表稳定排序。

parser_section_source 是【re-derivation】:
    parser 不对外暴露它走了哪条代码路径。本脚本只读 import kaiva_pdf 的私有函数，
    按 kaiva_pdf.py 的行号逐分支重新推导（见 SOURCE_CODE_REFS），并做两道交叉核对：
      1. 推导出的本页 section 必须等于 kaiva_pdf._extract_page_metadata() 的真实返回值；
      2. 按 parse() 的继承逻辑得到的 effective section 必须等于 corpus 里该页全部 chunk 的 section，
         丢页判定必须与 corpus 是否有该页 chunk 一致。
    任一不一致 → 抛 AuditError。通过核对只说明"推导出的值与 parser 一致"，
    不保证"分支归类"与 parser 内部走的分支一致（两条分支可能产出同一个值）。

失败语义:
    - 输入缺失、corpus 与 PDF 对不上、re-derivation 与 corpus 不一致、证据字符串在 PDF 中找不到
      → 抛 AuditError（整轮审计的前提不成立）。
    - 单页 pdftotext -f p -l p 失败 → 记入该行 page_status，不跳过该行；
      写完产物后以退出码 1 结束。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Sequence

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from components.parsers import kaiva_pdf  # noqa: E402  只读复用，见模块 docstring
from core import contracts  # noqa: E402

# ==============================================================================
# 模块常量
# ==============================================================================

PDF_SUFFIX: str = ".pdf"
POPPLER_TIMEOUT_S: float = 120.0
HASH_READ_BLOCK_BYTES: int = 1 << 20

# 用户规格：页眉原文 / 正文前 200 字符；超长 section 阈值 40 字符。
TEXT_HEAD_CHARS: int = 200
OVERLONG_SECTION_CHARS: int = 40
# 决定性检验要求贴出的 pdftotext 原始行数。
DECISIVE_RAW_LINES: int = 30
# 决定性检验的页（用户规格第 2 节）。
DECISIVE_DOC_ID: str = "EMM"
DECISIVE_PAGES: tuple[int, ...] = (96, 131)
# 每份手册列出的 distinct section 样例上限（用户规格第 3 节）。
DISTINCT_SAMPLE_LIMIT: int = 20

# TACM native 可读区与乱码区（用户规格第 8 / 10 节）。
TACM_DOC_ID: str = "TACM"
TACM_NATIVE_AUDIT_PAGES: tuple[int, int] = (104, 120)
TACM_GARBLED_PAGES: tuple[int, int] = (38, 103)
# "p.100 附近" 的检查窗口（用户规格第 8 节最后一问）。
TACM_VALID_VALUE_CHECK_PAGES: tuple[int, int] = (95, 103)

RECORD_GOLD: str = "gold_citation"
RECORD_TACM: str = "tacm_native_audit"
RECORD_ANOMALY: str = "anomaly_candidate"
RECORD_ORDER: dict[str, int] = {RECORD_GOLD: 0, RECORD_TACM: 1, RECORD_ANOMALY: 2}

SOURCE_EXPLICIT: str = "explicit_header_label"
SOURCE_TITLE_CHAPTER: str = "title_line_fallback:chapter_regex"
SOURCE_TITLE_NUMBERED: str = "title_line_fallback:numbered_regex"
SOURCE_TITLE_RAW: str = "title_line_fallback:raw_line"
SOURCE_INHERITED: str = "inherited"
SOURCE_UNRESOLVED: str = "unresolved"
SOURCE_ORDER: tuple[str, ...] = (
    SOURCE_EXPLICIT, SOURCE_TITLE_CHAPTER, SOURCE_TITLE_NUMBERED, SOURCE_TITLE_RAW,
    SOURCE_INHERITED, SOURCE_UNRESOLVED,
)
# 每种 source 在 components/parsers/kaiva_pdf.py 中对应的代码行（推导依据）。
SOURCE_CODE_REFS: dict[str, str] = {
    SOURCE_EXPLICIT: "kaiva_pdf.py:304-323 (_iter_label_spans 命中 SECTION 标签, 首次出现者胜 L315)",
    SOURCE_TITLE_CHAPTER: "kaiva_pdf.py:326-331 -> 422-424 (_CHAPTER_RE group(1))",
    SOURCE_TITLE_NUMBERED: "kaiva_pdf.py:326-331 -> 425-427 (_NUMBERED_TITLE_RE group(1))",
    SOURCE_TITLE_RAW: "kaiva_pdf.py:326-331 -> 428 (首个非 doc_id 左栏行整行 strip)",
    SOURCE_INHERITED: "kaiva_pdf.py:161-164 (本页 section is None, 沿用 last_section)",
    SOURCE_UNRESOLVED: "kaiva_pdf.py:181 (无本页值也无可继承值 -> UNKNOWN_SECTION)",
}

SEMANTIC_YES: str = "yes"
SEMANTIC_NO: str = "no"
SEMANTIC_UNRESOLVED: str = "unresolved"

GOLD_CLASS_EXACT: str = "exact_match"
GOLD_CLASS_REPR: str = "representation_only_mismatch"
GOLD_CLASS_SEMANTIC: str = "semantic_location_mismatch"
GOLD_CLASS_MISSING: str = "missing_no_chunk_on_page"
GOLD_CLASS_UNRESOLVED: str = "exact_mismatch_semantic_unresolved"
GOLD_CLASS_ORDER: tuple[str, ...] = (
    GOLD_CLASS_EXACT, GOLD_CLASS_REPR, GOLD_CLASS_SEMANTIC, GOLD_CLASS_UNRESOLVED, GOLD_CLASS_MISSING,
)

TACM_SUPPORTED: str = "clearly_supported"
TACM_WRONG: str = "clearly_wrong"
TACM_AMBIGUOUS: str = "ambiguous"
TACM_VERDICT_ORDER: tuple[str, ...] = (TACM_SUPPORTED, TACM_WRONG, TACM_AMBIGUOUS)

CHAPTER_PREFIX: str = "Chapter "

# 问句启发式的疑问/助动词词表（R08）。
QUESTION_LEAD_WORDS: tuple[str, ...] = (
    "How", "What", "Which", "When", "Where", "Who", "Whom", "Whose", "Why",
    "Did", "Do", "Does", "Is", "Are", "Was", "Were", "Can", "Could", "Should",
    "Would", "Will", "Have", "Has", "Had", "May", "Might", "Must", "Shall",
)
_QUESTION_RE = re.compile(
    r"^\s*(?:\d{1,3}[.)]\s+)?(?:" + "|".join(QUESTION_LEAD_WORDS) + r")\b"
)
_PURE_DIGITS_RE = re.compile(r"^\d+$")

ANOMALY_RULES: tuple[tuple[str, str], ...] = (
    ("R01_empty", "section == ''"),
    ("R02_unknown", f"section == {kaiva_pdf.UNKNOWN_SECTION!r}"),
    ("R03_pure_punctuation", "section 非空，且每个字符都既非字母数字(str.isalnum)也非空白"),
    ("R04_single_char_non_alnum", "len(section.strip()) == 1 且该字符不是 ASCII 字母/数字"),
    ("R05_overlong", f"len(section) > {OVERLONG_SECTION_CHARS}"),
    ("R06_control_chars", "section 中存在 unicodedata.category == 'Cc' 的字符"),
    ("R07_contains_U+00FF", "section 中含 U+00FF (ÿ)"),
    ("R08_question_like", "section 含 '?'，或匹配 ^\\s*(\\d{1,3}[.)]\\s+)?(How|What|Which|When|Where|Who|Whom|Whose|Why|"
                          "Did|Do|Does|Is|Are|Was|Were|Can|Could|Should|Would|Will|Have|Has|Had|May|Might|Must|Shall)\\b"),
    ("R09_multiple_sections_on_page", "corpus 中同一 (doc_id, pdf_page) 的 chunk 带 >1 个不同 section"),
    ("R10_not_in_doc_header_vocab", "section 不属于该 doc 的 header 词表 V(doc)。V(doc) = 该 PDF 所有页（含被丢弃页）上 "
                                   "source ∈ {explicit_header_label, title_line_fallback:chapter_regex} 的本页 section 值集合"),
)

# ------------------------------------------------------------------------------
# TACM p.104-120 的章节证据（人工从 PDF 中定位，脚本运行时逐条回 PDF 核验存在性）
#
# 每条: (起页, 止页, 证据所指章节 S, 本页上必须出现的标题/首行子串,
#        [(引用页, 必须出现的子串), ...], [(引用页, 该页 SECTION 标签必须等于的值), ...], 说明)
# 子串核验口径: contracts.normalize_text(整页文本) 包含 normalize_text(子串)。
# ------------------------------------------------------------------------------
TACM_SECTION_EVIDENCE: tuple[tuple[int, int, str, str, tuple[tuple[int, str], ...], tuple[tuple[int, str], ...], str], ...] = (
    (104, 107, "11", "PCL E-Learning Matrix Dry",
     ((2, "11.0 APPENDICES"), (36, "11- Appendices"), (36, "11.5.1- PCL E-Learning Matrix Dry OLP")),
     ((36, "11"),),
     "页首行为 'PCL E-Learning Matrix Dry'；p.36（SECTION 11 页）的 11.5 小节列出 '11.5.1- PCL E-Learning Matrix Dry OLP'"),
    (108, 111, "11", "PCL E-Learning Matrix Tanker",
     ((2, "11.0 APPENDICES"), (36, "11- Appendices"), (36, "11.5.2- PCL E-Learning Matrix Tanker OLP")),
     ((36, "11"),),
     "页首行为 'PCL E-Learning Matrix Tanker'；p.36（SECTION 11 页）列出 '11.5.2- PCL E-Learning Matrix Tanker OLP'"),
    (112, 115, "11", "PCL E-Learning Matrix Gas",
     ((2, "11.0 APPENDICES"), (36, "11- Appendices"), (36, "11.5.3- PCL E-Learning Matrix Gas OLP")),
     ((36, "11"),),
     "页首行为 'PCL E-Learning Matrix Gas'；p.36（SECTION 11 页）列出 '11.5.3- PCL E-Learning Matrix Gas OLP'"),
    (116, 116, "11", "11.7.1 External Course/ Seminar/ Workshop Feedback",
     ((2, "11.7.1 External Course/ Seminar/ Workshop- Feedback"), (37, "Refer to a sample feedback form 11.7.1 in section 11")),
     ((37, "11"),),
     "页首行为表单 11.7.1 标题（含 Q1-6）；TOC p.2 列出 11.7.1；p.37（SECTION 11）写明 'form 11.7.1 in section 11'"),
    (117, 117, "11", "7. How satisfied are you with the knowledge you gained",
     ((116, "6. Date ended *"), (117, "11. Did the Course/ Seminar/ Workshop meet your expectation? *"),
      (37, "Refer to a sample feedback form 11.7.1 in section 11")),
     ((37, "11"),),
     "本页为 Q7-Q11，题号接续 p.116 表单 11.7.1 的 Q1-Q6（p.116 末题 '6. Date ended *'）"),
    (118, 118, "11", "12. How effective were the learning activities",
     ((117, "11. Did the Course/ Seminar/ Workshop meet your expectation? *"), (118, "13. Date of submitting the feedback *"),
      (37, "Refer to a sample feedback form 11.7.1 in section 11")),
     ((37, "11"),),
     "本页为 Q12-Q13，题号接续 p.117 的 Q7-Q11（表单 11.7.1）"),
    (119, 119, "11", "11.7.2 External Course/ Seminar/ Workshop- Effectiveness",
     ((2, "11.7.2 External Course/ Seminar/ Workshop- Effectiveness"),
      (37, "Refer to a sample effectiveness assessment form 11.7.2 in section 11")),
     ((37, "11"),),
     "页首行为表单 11.7.2 标题（含 Q1-6）；TOC p.2 列出 11.7.2；p.37（SECTION 11）写明 'form 11.7.2 in section 11'"),
    (120, 120, "11", "7. Did attending this Course/ Seminar/ Workshop help you",
     ((119, "6. Date ended *"), (120, "12. Date of submitting this form *"),
      (37, "Refer to a sample effectiveness assessment form 11.7.2 in section 11")),
     ((37, "11"),),
     "本页为 Q7-Q12，题号接续 p.119 表单 11.7.2 的 Q1-Q6"),
)

CSV_COLUMNS: tuple[str, ...] = (
    "record_type", "is_gold_citation_page", "is_tacm_native_audit_page", "is_anomaly_candidate",
    "question_id", "question_type", "citation_index",
    "doc_id", "pdf_page", "gold_section",
    "corpus_sections_on_page", "chunk_ids_on_page", "n_chunks_on_page",
    "parser_page_section", "parser_effective_section", "parser_section_source",
    "parser_section_source_is_rederivation", "parser_section_source_code_ref",
    "parser_section_source_line_index", "parser_section_source_raw_line",
    "source_line_removed_from_body",
    "prev_page_effective_section", "next_page_effective_section",
    "exact_section_match", "semantic_location_match", "semantic_evidence", "gold_class",
    "tacm_verdict", "tacm_evidence_section", "tacm_evidence",
    "anomaly_rules",
    "raw_header_text", "body_head_200",
    "per_page_equals_wholedoc_split", "page_status",
)


class AuditError(RuntimeError):
    """审计前提不成立（输入缺失、re-derivation 与 corpus 不一致、证据在 PDF 中不存在）。"""


# ==============================================================================
# 基础工具
# ==============================================================================

def run_cmd(argv: Sequence[str]) -> str:
    """跑命令返回 stdout（utf-8, errors=replace，与 parser 一致）。

    抛出: AuditError —— 命令不存在 / 非零返回 / 超时。
    """
    try:
        proc = subprocess.run(list(argv), capture_output=True, timeout=POPPLER_TIMEOUT_S)
    except FileNotFoundError as exc:
        raise AuditError(f"命令不可用: {argv[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise AuditError(f"超时 >{POPPLER_TIMEOUT_S}s: {' '.join(argv)}") from exc
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", errors="replace").strip()
        raise AuditError(f"{argv[0]} 返回 {proc.returncode}: {detail}")
    return proc.stdout.decode("utf-8", errors="replace")


def tool_version(tool: str) -> str:
    """poppler 工具的版本行（-v 打到 stderr，返回码因版本而异，故不看返回码）。

    抛出: AuditError —— 无输出。
    """
    proc = subprocess.run([tool, "-v"], capture_output=True, timeout=POPPLER_TIMEOUT_S)
    text = (proc.stdout + proc.stderr).decode("utf-8", errors="replace").strip()
    if not text:
        raise AuditError(f"{tool} -v 无输出")
    return text.splitlines()[0]


def file_sha256(path: str) -> str:
    """文件 sha256 十六进制串。抛出 OSError —— 文件不可读。"""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(HASH_READ_BLOCK_BYTES), b""):
            digest.update(block)
    return digest.hexdigest()


def esc(text: str | None) -> str:
    """任意字符串 → 纯 ASCII 的 JSON 字面量。空白原样保留，控制字符可见，不破坏 CSV/log 行结构。"""
    return json.dumps(text, ensure_ascii=True)


def page_count(path: str) -> int:
    """pdfinfo 页数。抛出 AuditError —— 无 Pages 行。"""
    for line in run_cmd(["pdfinfo", path]).splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":", 1)[1].strip())
    raise AuditError(f"pdfinfo 无 Pages 行: {path}")


def b(value: bool) -> str:
    return "true" if value else "false"


# ==============================================================================
# section 来源的 re-derivation
# ==============================================================================

@dataclass(frozen=True)
class PageDerivation:
    """一页的 section 推导结果。

    page_section: 本页 _extract_page_metadata 的 section（None = 本页抽不到）。
    source / line_index / raw_line: 本页值来自哪条分支、页内 0-based 哪一行、该行原文。
      line_index 对 explicit 为标签所在行；对 title fallback 为被采用的左栏行；本页无值时为 None。
    """
    page_section: str | None
    source: str | None
    line_index: int | None
    raw_line: str | None


def derive_page_section(page_text: str) -> PageDerivation:
    """按 kaiva_pdf.py:295-331 与 417-428 重新推导本页 section 与分支。

    输入假设: page_text 是整份 -layout 抽取按 \\f 切出的单页文本（parser 的真实输入）。
    抛出: AuditError —— 推导值与 kaiva_pdf._extract_page_metadata() 的返回值不一致。
    """
    lines = page_text.splitlines()
    header = lines[:kaiva_pdf.HEADER_SCAN_LINES]
    fields: dict[str, tuple[str, int]] = {}
    leftovers: list[tuple[int, str]] = []
    for index, line in enumerate(header):
        spans = kaiva_pdf._iter_label_spans(line)
        cursor = 0
        pieces: list[str] = []
        for position, (key, start, end) in enumerate(spans):
            pieces.append(line[cursor:start])
            stop = spans[position + 1][1] if position + 1 < len(spans) else len(line)
            value = line[end:stop].strip()
            if value and key not in fields:
                fields[key] = (value, index)
            cursor = stop
        pieces.append(line[cursor:])
        remainder = " ".join(piece.strip() for piece in pieces if piece.strip()).strip()
        if remainder and not kaiva_pdf._is_noise_line(remainder):
            leftovers.append((index, remainder))

    derived: PageDerivation
    if "section" in fields:
        value, index = fields["section"]
        derived = PageDerivation(value, SOURCE_EXPLICIT, index, header[index])
    else:
        derived = PageDerivation(None, None, None, None)
        for index, text in leftovers:
            if kaiva_pdf._is_doc_id_token(text):
                continue
            chapter = kaiva_pdf._CHAPTER_RE.match(text)
            if chapter:
                derived = PageDerivation(chapter.group(1).strip(), SOURCE_TITLE_CHAPTER, index, header[index])
            else:
                numbered = kaiva_pdf._NUMBERED_TITLE_RE.match(text)
                if numbered:
                    derived = PageDerivation(numbered.group(1).strip(), SOURCE_TITLE_NUMBERED, index, header[index])
                else:
                    derived = PageDerivation(text.strip(), SOURCE_TITLE_RAW, index, header[index])
            break

    actual = kaiva_pdf._extract_page_metadata(page_text)["section"]
    if derived.page_section != actual:
        raise AuditError(f"re-derivation 与 _extract_page_metadata 不一致: 推导={derived.page_section!r} 实际={actual!r}")
    return derived


@dataclass
class PageRecord:
    """一页的全部审计原料。"""
    doc_id: str
    filename: str
    pdf_page: int
    page_text: str
    derivation: PageDerivation
    effective_section: str
    source: str
    body: str
    chunk_ids: list[str]
    corpus_sections: list[str]
    per_page_text: str | None = None
    page_status: str = ""
    anomaly_rules: list[str] = field(default_factory=list)


# ==============================================================================
# 加载
# ==============================================================================

@dataclass
class Corpus:
    name_to_id: dict[str, str]
    page_chunks: dict[tuple[str, int], list[str]]
    page_sections: dict[tuple[str, int], set[str]]
    n_chunks: int


def load_corpus(path: str) -> Corpus:
    """读 chunks.jsonl。

    抛出: AuditError —— 文件不存在、某 doc_name 对应多个 doc_id、pdf_page 非 int。
    """
    if not os.path.isfile(path):
        raise AuditError(f"corpus 不存在: {path}")
    name_to_ids: dict[str, set[str]] = defaultdict(set)
    page_chunks: dict[tuple[str, int], list[str]] = defaultdict(list)
    page_sections: dict[tuple[str, int], set[str]] = defaultdict(set)
    n = 0
    with open(path, encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            chunk = json.loads(line)
            page = chunk["pdf_page"]
            if not isinstance(page, int) or isinstance(page, bool):
                raise AuditError(f"{path}:{line_no}: pdf_page 不是 int")
            key = (chunk["doc_id"], page)
            name_to_ids[chunk["doc_name"]].add(chunk["doc_id"])
            page_chunks[key].append(chunk["id"])
            page_sections[key].add(chunk["section"])
            n += 1
    name_to_id: dict[str, str] = {}
    for name, ids in name_to_ids.items():
        if len(ids) != 1:
            raise AuditError(f"corpus 中 {name} 对应多个 doc_id: {sorted(ids)}")
        name_to_id[name] = next(iter(ids))
    return Corpus(name_to_id, page_chunks, page_sections, n)


def load_gold_citations(path: str) -> list[tuple[str, str, int, dict]]:
    """读 testset，返回 [(question_id, type, citation_index, citation), ...]，保持文件顺序。

    抛出: AuditError —— 文件不存在、citation 缺字段、pdf_page 非 int。
    """
    if not os.path.isfile(path):
        raise AuditError(f"testset 不存在: {path}")
    out: list[tuple[str, str, int, dict]] = []
    with open(path, encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            q = json.loads(line)
            for index, citation in enumerate(q.get("citations") or []):
                for key in ("doc_id", "section", "pdf_page"):
                    if key not in citation:
                        raise AuditError(f"{path}:{line_no}: {q['id']} citation#{index} 缺 {key}")
                if not isinstance(citation["pdf_page"], int) or isinstance(citation["pdf_page"], bool):
                    raise AuditError(f"{path}:{line_no}: {q['id']} citation#{index} pdf_page 不是 int")
                out.append((q["id"], q["type"], index, citation))
    return out


def collect_pages(pdf_dir: str, corpus: Corpus) -> tuple[dict[tuple[str, int], PageRecord], dict[str, dict[str, object]]]:
    """逐 PDF 逐页复现 parser 的 section 与丢页判定，并与 corpus 交叉核对。

    抛出: AuditError —— 目录无 PDF、PDF 不在 corpus、分页数不一致、复现与 corpus 不一致。
    """
    if not os.path.isdir(pdf_dir):
        raise AuditError(f"PDF 目录不存在: {pdf_dir}")
    filenames = sorted(f for f in os.listdir(pdf_dir) if f.lower().endswith(PDF_SUFFIX))
    if not filenames:
        raise AuditError(f"目录下没有 PDF: {pdf_dir}")
    pages: dict[tuple[str, int], PageRecord] = {}
    files: dict[str, dict[str, object]] = {}
    for filename in filenames:
        if filename not in corpus.name_to_id:
            raise AuditError(f"PDF 不在 corpus 中: {filename}")
        doc_id = corpus.name_to_id[filename]
        path = os.path.join(pdf_dir, filename)
        n_pages = page_count(path)
        whole = run_cmd([*kaiva_pdf.PDFTOTEXT_ARGS, path, "-"]).split(kaiva_pdf.PAGE_SEPARATOR)
        if whole and not whole[-1].strip():
            whole.pop()
        if len(whole) != n_pages:
            raise AuditError(f"整份抽取分页数 {len(whole)} != pdfinfo {n_pages}: {filename}")
        files[filename] = {"doc_id": doc_id, "sha256": file_sha256(path), "pages": n_pages, "path": path}

        last_section: str | None = None
        for page_no, page_text in enumerate(whole, start=1):
            try:
                derivation = derive_page_section(page_text)
            except AuditError as exc:
                raise AuditError(f"{filename} p{page_no}: {exc}") from exc
            if derivation.page_section is not None:
                effective, source = derivation.page_section, str(derivation.source)
                last_section = derivation.page_section
            elif last_section is not None:
                effective, source = last_section, SOURCE_INHERITED
            else:
                effective, source = kaiva_pdf.UNKNOWN_SECTION, SOURCE_UNRESOLVED
            meta = kaiva_pdf._extract_page_metadata(page_text)
            body = kaiva_pdf._strip_noise(page_text, meta)
            key = (doc_id, page_no)
            chunk_ids = list(corpus.page_chunks.get(key, []))
            dropped = len(body) < contracts.CHUNK_MIN_CHARS
            if dropped != (not chunk_ids):
                raise AuditError(f"丢页判定复现与 corpus 不一致: {filename} p{page_no} body={len(body)} chunks={len(chunk_ids)}")
            corpus_sections = sorted(corpus.page_sections.get(key, set()))
            if chunk_ids and corpus_sections != [effective]:
                raise AuditError(f"section 复现与 corpus 不一致: {filename} p{page_no} 复现={effective!r} corpus={corpus_sections!r}")
            pages[key] = PageRecord(doc_id, filename, page_no, page_text, derivation, effective, source, body,
                                    chunk_ids, corpus_sections)
    return pages, files


def attach_per_page_text(record: PageRecord, pdf_path: str) -> None:
    """对需要输出的页单独跑 pdftotext -layout -f p -l p。单页失败记入 page_status，不抛。"""
    if record.per_page_text is not None or record.page_status:
        return
    try:
        text = run_cmd([*kaiva_pdf.PDFTOTEXT_ARGS, "-f", str(record.pdf_page), "-l", str(record.pdf_page), pdf_path, "-"])
    except AuditError as exc:
        record.page_status = f"error: {exc}"
        return
    record.per_page_text = text
    record.page_status = "ok"


# ==============================================================================
# 判定
# ==============================================================================

def header_text(page_text: str) -> str:
    return "\n".join(page_text.splitlines()[:kaiva_pdf.HEADER_SCAN_LINES])


def denotes_evidenced_section(identifier: str, record: PageRecord) -> bool | None:
    """identifier 是否指向本页 header 直接证据所标识的章节。None = 本页无直接 header 证据。

    判据（写入日志 §B.2）:
      explicit_header_label             → identifier == 本页 SECTION 标签值
      title_line_fallback:chapter_regex → identifier == N 或 identifier == 'Chapter ' + N，
                                          N 为本页标题行 'Chapter N – ...' 的编号
      其他 source                        → None
    """
    d = record.derivation
    if d.source == SOURCE_EXPLICIT:
        return identifier == d.page_section
    if d.source == SOURCE_TITLE_CHAPTER:
        return identifier in (d.page_section, f"{CHAPTER_PREFIX}{d.page_section}")
    return None


def gold_semantic(gold_section: str, record: PageRecord) -> tuple[str, str]:
    """返回 (semantic_location_match, evidence 描述)。判据见 denotes_evidenced_section。"""
    d = record.derivation
    g = denotes_evidenced_section(gold_section, record)
    p = denotes_evidenced_section(record.effective_section, record)
    if g is None or p is None:
        return SEMANTIC_UNRESOLVED, f"no direct header evidence on page (source={record.source})"
    evidence = f"{d.source} line {d.line_index}: {esc((d.raw_line or '').strip())}"
    return (SEMANTIC_YES if (g and p) else SEMANTIC_NO), evidence


def tacm_evidence_for(page: int) -> tuple[str, str, tuple[tuple[int, str], ...], tuple[tuple[int, str], ...], str] | None:
    for lo, hi, section, heading, refs, label_refs, note in TACM_SECTION_EVIDENCE:
        if lo <= page <= hi:
            return section, heading, refs, label_refs, note
    return None


def tacm_verdict(value: str, evidence_section: str | None) -> str:
    """TACM p.104-120 判定（判据写入日志 §B.3）。

      evidence_section is None                                 → ambiguous
      value == S                                               → clearly_supported
      value 以 S + '.' 或 S + ' ' 开头（S 内更细粒度的小节标题） → ambiguous
      其余                                                      → clearly_wrong
    """
    if evidence_section is None:
        return TACM_AMBIGUOUS
    if value == evidence_section:
        return TACM_SUPPORTED
    if value.startswith(evidence_section + ".") or value.startswith(evidence_section + " "):
        return TACM_AMBIGUOUS
    return TACM_WRONG


def verify_tacm_evidence(pages: dict[tuple[str, int], PageRecord]) -> None:
    """逐条核验 TACM_SECTION_EVIDENCE 中的子串与标签确实存在于 PDF。抛出 AuditError —— 任一不存在。"""
    for lo, hi, _section, heading, refs, label_refs, _note in TACM_SECTION_EVIDENCE:
        for page in range(lo, hi + 1):
            text = contracts.normalize_text(pages[(TACM_DOC_ID, page)].page_text)
            if contracts.normalize_text(heading) not in text:
                raise AuditError(f"TACM p{page} 找不到证据标题子串 {heading!r}")
        for ref_page, needle in refs:
            if contracts.normalize_text(needle) not in contracts.normalize_text(pages[(TACM_DOC_ID, ref_page)].page_text):
                raise AuditError(f"TACM p{ref_page} 找不到证据子串 {needle!r}")
        for ref_page, label in label_refs:
            rec = pages[(TACM_DOC_ID, ref_page)]
            if rec.derivation.source != SOURCE_EXPLICIT or rec.derivation.page_section != label:
                raise AuditError(f"TACM p{ref_page} SECTION 标签不是 {label!r}: {rec.derivation}")


def doc_header_vocab(pages: dict[tuple[str, int], PageRecord]) -> dict[str, set[str]]:
    vocab: dict[str, set[str]] = defaultdict(set)
    for (doc_id, _), rec in pages.items():
        if rec.derivation.source in (SOURCE_EXPLICIT, SOURCE_TITLE_CHAPTER) and rec.derivation.page_section is not None:
            vocab[doc_id].add(rec.derivation.page_section)
    return vocab


def anomaly_rules_for(record: PageRecord, vocab: set[str]) -> list[str]:
    """按 ANOMALY_RULES 给本页打规则标签。只对有 chunk 的页调用。结果只是 anomaly_candidate。"""
    s = record.effective_section
    hits: list[str] = []
    if s == "":
        hits.append("R01_empty")
    if s == kaiva_pdf.UNKNOWN_SECTION:
        hits.append("R02_unknown")
    if s and all((not ch.isalnum()) and (not ch.isspace()) for ch in s):
        hits.append("R03_pure_punctuation")
    if len(s.strip()) == 1 and not (s.strip().isascii() and s.strip().isalnum()):
        hits.append("R04_single_char_non_alnum")
    if len(s) > OVERLONG_SECTION_CHARS:
        hits.append("R05_overlong")
    if any(unicodedata.category(ch) == "Cc" for ch in s):
        hits.append("R06_control_chars")
    if "ÿ" in s:
        hits.append("R07_contains_U+00FF")
    if "?" in s or _QUESTION_RE.match(s):
        hits.append("R08_question_like")
    if len(record.corpus_sections) > 1:
        hits.append("R09_multiple_sections_on_page")
    if s not in vocab:
        hits.append("R10_not_in_doc_header_vocab")
    return hits


def source_line_removed(record: PageRecord) -> str:
    """section 取值所在行是否被 parser 从正文剥离。按 kaiva_pdf._strip_noise (L436-451) 的三个条件逐一复现。

    返回 'true' / 'false'；本页无取值行（inherited / unresolved）→ ''。
    'false' 表示该行文本仍留在该页送去分块的正文里。
    """
    index = record.derivation.line_index
    if index is None:
        return ""
    meta = kaiva_pdf._extract_page_metadata(record.page_text)
    noise_lines: set[int] = meta["_noise_lines"]  # type: ignore[assignment]
    line = record.page_text.splitlines()[index]
    removed = (index in noise_lines or kaiva_pdf._is_noise_line(line)
               or (index < kaiva_pdf.HEADER_SCAN_LINES and kaiva_pdf._is_doc_id_token(line)))
    return b(removed)


# ==============================================================================
# 行构造
# ==============================================================================

def base_row(record: PageRecord, pages: dict[tuple[str, int], PageRecord], corpus: Corpus,
             flags: tuple[bool, bool, bool]) -> dict[str, str]:
    prev_rec = pages.get((record.doc_id, record.pdf_page - 1))
    next_rec = pages.get((record.doc_id, record.pdf_page + 1))
    d = record.derivation
    per_page_eq = ""
    if record.per_page_text is not None:
        per_page_eq = b(record.per_page_text.replace(kaiva_pdf.PAGE_SEPARATOR, "") == record.page_text)
    row = {c: "" for c in CSV_COLUMNS}
    row.update(
        is_gold_citation_page=b(flags[0]),
        is_tacm_native_audit_page=b(flags[1]),
        is_anomaly_candidate=b(flags[2]),
        doc_id=record.doc_id,
        pdf_page=str(record.pdf_page),
        corpus_sections_on_page=esc(" | ".join(record.corpus_sections)),
        chunk_ids_on_page=" ".join(record.chunk_ids),
        n_chunks_on_page=str(len(record.chunk_ids)),
        parser_page_section=esc(d.page_section),
        parser_effective_section=esc(record.effective_section),
        parser_section_source=record.source,
        parser_section_source_is_rederivation="true",
        parser_section_source_code_ref=SOURCE_CODE_REFS[record.source],
        parser_section_source_line_index="" if d.line_index is None else str(d.line_index),
        parser_section_source_raw_line=esc(d.raw_line),
        source_line_removed_from_body=source_line_removed(record),
        prev_page_effective_section=esc(prev_rec.effective_section) if prev_rec else "",
        next_page_effective_section=esc(next_rec.effective_section) if next_rec else "",
        anomaly_rules=";".join(record.anomaly_rules),
        raw_header_text=esc(header_text(record.page_text)[:TEXT_HEAD_CHARS]),
        body_head_200=esc(record.body[:TEXT_HEAD_CHARS]),
        per_page_equals_wholedoc_split=per_page_eq,
        page_status=record.page_status,
    )
    return row


# ==============================================================================
# 主流程
# ==============================================================================

def page_runs(items: Sequence[tuple[int, str]]) -> list[tuple[int, int, str]]:
    runs: list[tuple[int, int, str]] = []
    for page, value in items:
        if runs and runs[-1][2] == value:
            runs[-1] = (runs[-1][0], page, value)
        else:
            runs.append((page, page, value))
    return runs


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="citation section metadata ground-truth 审计（只读）")
    ap.add_argument("--pdf-dir", required=True)
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--testset", required=True)
    ap.add_argument("--out-csv", required=True)
    ap.add_argument("--out-log", required=True)
    args = ap.parse_args(argv)

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    parser_path = os.path.join(repo_root, "components", "parsers", "kaiva_pdf.py")
    contracts_path = os.path.join(repo_root, "core", "contracts.py")
    script_path = os.path.abspath(__file__)

    corpus = load_corpus(args.corpus)
    gold = load_gold_citations(args.testset)
    pages, files = collect_pages(args.pdf_dir, corpus)
    doc_to_path = {str(info["doc_id"]): str(info["path"]) for info in files.values()}
    verify_tacm_evidence(pages)
    vocab = doc_header_vocab(pages)

    chunked = sorted(k for k, r in pages.items() if r.chunk_ids)
    for key in chunked:
        pages[key].anomaly_rules = anomaly_rules_for(pages[key], vocab[key[0]])
    anomaly_keys = sorted(k for k in chunked if pages[k].anomaly_rules)
    gold_keys = {(str(c["doc_id"]), int(c["pdf_page"])) for _, _, _, c in gold}
    tacm_keys = {(TACM_DOC_ID, p) for p in range(TACM_NATIVE_AUDIT_PAGES[0], TACM_NATIVE_AUDIT_PAGES[1] + 1)}
    for key in gold_keys:
        if key not in pages:
            raise AuditError(f"gold citation 指向 PDF 中不存在的页: {key}")

    extra_keys = {(DECISIVE_DOC_ID, p) for p in DECISIVE_PAGES}
    extra_keys |= {(TACM_DOC_ID, p) for p in range(TACM_VALID_VALUE_CHECK_PAGES[0], TACM_VALID_VALUE_CHECK_PAGES[1] + 1)}
    for key in sorted(gold_keys | tacm_keys | set(anomaly_keys) | extra_keys):
        attach_per_page_text(pages[key], doc_to_path[key[0]])

    def flags(key: tuple[str, int]) -> tuple[bool, bool, bool]:
        return key in gold_keys, key in tacm_keys, key in set(anomaly_keys)

    rows: list[dict[str, str]] = []
    gold_results: list[dict[str, str]] = []
    for qid, qtype, index, citation in gold:
        key = (str(citation["doc_id"]), int(citation["pdf_page"]))
        rec = pages[key]
        row = base_row(rec, pages, corpus, flags(key))
        gold_section = str(citation["section"])
        row.update(record_type=RECORD_GOLD, question_id=qid, question_type=qtype, citation_index=str(index),
                   gold_section=esc(gold_section))
        if not rec.chunk_ids:
            row.update(exact_section_match="", semantic_location_match=SEMANTIC_UNRESOLVED,
                       semantic_evidence="no chunk on page", gold_class=GOLD_CLASS_MISSING)
        else:
            exact = gold_section == rec.effective_section
            semantic, evidence = gold_semantic(gold_section, rec)
            if exact:
                gclass = GOLD_CLASS_EXACT
            elif semantic == SEMANTIC_YES:
                gclass = GOLD_CLASS_REPR
            elif semantic == SEMANTIC_NO:
                gclass = GOLD_CLASS_SEMANTIC
            else:
                gclass = GOLD_CLASS_UNRESOLVED
            row.update(exact_section_match=b(exact), semantic_location_match=semantic,
                       semantic_evidence=evidence, gold_class=gclass)
        rows.append(row)
        gold_results.append(row)

    tacm_results: list[dict[str, str]] = []
    for key in sorted(tacm_keys):
        rec = pages[key]
        row = base_row(rec, pages, corpus, flags(key))
        ev = tacm_evidence_for(rec.pdf_page)
        ev_section = ev[0] if ev else None
        row.update(record_type=RECORD_TACM,
                   tacm_verdict=tacm_verdict(rec.effective_section, ev_section),
                   tacm_evidence_section=esc(ev_section),
                   tacm_evidence=ev[4] if ev else "no evidence entry")
        rows.append(row)
        tacm_results.append(row)

    for key in anomaly_keys:
        rec = pages[key]
        row = base_row(rec, pages, corpus, flags(key))
        row.update(record_type=RECORD_ANOMALY)
        rows.append(row)

    rows.sort(key=lambda r: (RECORD_ORDER[r["record_type"]], r["doc_id"], int(r["pdf_page"]),
                             r["question_id"], r["citation_index"]))

    os.makedirs(os.path.dirname(os.path.abspath(args.out_csv)), exist_ok=True)
    with open(args.out_csv, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    env = {
        "python": platform.python_version(),
        "pdftotext": tool_version("pdftotext"),
        "pdfinfo": tool_version("pdfinfo"),
        "git_commit": run_cmd(["git", "-C", repo_root, "rev-parse", "HEAD"]).strip(),
    }
    tracked = {}
    for label, path in (("kaiva_pdf.py", parser_path), ("contracts.py", contracts_path), ("audit script", script_path)):
        rel = os.path.relpath(path, repo_root)
        listed = run_cmd(["git", "-C", repo_root, "ls-files", "--", rel]).strip()
        tracked[label] = (rel, file_sha256(path), "tracked" if listed else "UNTRACKED")

    write_log(args, env, tracked, files, corpus, pages, gold, gold_results, tacm_results, anomaly_keys, vocab)

    failed = sorted(k for k, r in pages.items() if r.page_status.startswith("error"))
    if failed:
        print(f"单页 pdftotext 失败 {len(failed)} 页，见 CSV page_status", file=sys.stderr)
        return 1
    print(f"wrote {args.out_csv} ({len(rows)} rows)")
    print(f"wrote {args.out_log}")
    return 0


# ==============================================================================
# 日志
# ==============================================================================

def write_log(args, env, tracked, files, corpus: Corpus, pages: dict[tuple[str, int], PageRecord], gold,
              gold_results, tacm_results, anomaly_keys, vocab) -> None:
    out: list[str] = []
    w = out.append

    w("citation section metadata ground-truth 审计")
    w("=" * 78)
    w("§A 环境指纹（无时间戳，保证逐字节确定性）")
    for k in ("python", "pdftotext", "pdfinfo", "git_commit"):
        w(f"  {k:<12} = {env[k]}")
    for label, (rel, sha, status) in tracked.items():
        w(f"  {label:<12} = {rel}  sha256={sha}  git={status}")
    w(f"  corpus       = {args.corpus}  sha256={file_sha256(args.corpus)}  chunks={corpus.n_chunks}")
    w(f"  testset      = {args.testset}  sha256={file_sha256(args.testset)}  citations={len(gold)}")
    for filename in sorted(files):
        info = files[filename]
        w(f"  pdf {str(info['doc_id']):<5}    = {esc(filename)}  pages={info['pages']}  sha256={info['sha256']}")
    w("")

    w("§B 判据（先于结果写下）")
    w("  B.1 parser_section_source 是 RE-DERIVATION，不是 parser 的真实输出。")
    w("      parser 不暴露分支；本脚本按 kaiva_pdf.py 行号逐分支重演，可能与 parser 实际分支归类分歧")
    w("      （仅当两条分支产出同一值时可能分歧）。代码依据:")
    for s in SOURCE_ORDER:
        w(f"        {s:<36} {SOURCE_CODE_REFS[s]}")
    w("      交叉核对（任一不一致即抛异常，本次运行未抛）: 推导值 == _extract_page_metadata()['section']；")
    w("      继承后的 effective section == corpus 该页全部 chunk 的 section；丢页判定 == corpus 有无该页 chunk。")
    w("  B.2 gold citation:")
    w("      exact_section_match := gold_section == parser_effective_section（纯字符串，无任何归一化）")
    w("      semantic_location_match（只用本页 header 的直接 PDF 证据）:")
    w("        本页 source=explicit_header_label → 证据 = 本页 SECTION 标签值 L；identifier 指向证据章节 ⇔ identifier == L")
    w("        本页 source=title_line_fallback:chapter_regex → 证据 = 本页标题行 'Chapter N – ...'；")
    w("            identifier 指向证据章节 ⇔ identifier == N 或 identifier == 'Chapter N'")
    w("            （这是【审计用】的等价判据，只用于回答'是否指向同一章'，不是规范化提案）")
    w("        其他 source → 无直接 header 证据")
    w("        yes = gold 与 parser 都指向证据章节；no = 有证据且至少一方不指向；unresolved = 无直接证据")
    w("        pdf_page 相同是前提（按 gold 的 (doc_id, pdf_page) 取页）。")
    w("      gold_class: exact_match / representation_only_mismatch (exact=false, semantic=yes) /")
    w("                  semantic_location_mismatch (semantic=no) / exact_mismatch_semantic_unresolved / missing_no_chunk_on_page")
    w("  B.3 TACM p.104-120 判定:")
    w("      S := TACM_SECTION_EVIDENCE 给出的章节（人工定位的 PDF 证据，脚本运行时逐条回 PDF 核验存在，不存在即抛异常）")
    w("      clearly_supported : parser 值 == S")
    w("      ambiguous         : 无证据条目；或 parser 值以 'S.' / 'S ' 开头（S 内更细粒度小节的标题——契约未定义 section 粒度）")
    w("      clearly_wrong     : 有证据，且 parser 值既不等于 S，也不以 'S.' / 'S ' 开头")
    w("  B.4 anomaly_candidate 规则（页级：只看有 chunk 的页；命中任一即为 candidate；candidate ≠ wrong_section）:")
    for rid, desc in ANOMALY_RULES:
        w(f"        {rid:<32} {desc}")
    w("      纯数字 ^\\d+$ 与单个 ASCII 字母/数字（如 SECTION '1' / 'A'）只做描述性计数，【不】作为 anomaly 规则:")
    w("      二者是 explicit SECTION 标签的常规形态；把它们列为 candidate 会让 >500 页常规值淹没清单。")
    w("      用户规格中的'单字符'类别因此拆为 R04（非字母数字单字符，candidate）+ 描述性计数（字母数字单字符）。")
    w("      已知局限: R10 以 header 词表为参照——属于词表 ≠ 正确（见 §4.2 的 TACM p.100 '9'），")
    w("      不属于词表 ≠ 错误（如 EMM 'Table of Contents'）。")
    w("")

    # §1 决定性检验
    w("§1 ⭐ 决定性检验：EMM p.96 / p.131 页眉原文")
    w("  判据（先写）: 页眉 SECTION 值为 '15' → 倾向 C；为 'Chapter 15' → 倾向 B；无 SECTION 字段 → parser 走 fallback，追代码路径")
    for page in DECISIVE_PAGES:
        rec = pages[(DECISIVE_DOC_ID, page)]
        d = rec.derivation
        w(f"  --- EMM p.{page}：pdftotext -layout -f {page} -l {page} 前 {DECISIVE_RAW_LINES} 行（每行 JSON 转义，空白原样） ---")
        if rec.per_page_text is None:
            w(f"    per-page 抽取失败: {rec.page_status}")
        else:
            for i, line in enumerate(rec.per_page_text.replace(kaiva_pdf.PAGE_SEPARATOR, "").splitlines()[:DECISIVE_RAW_LINES]):
                w(f"    {i:02d}| {esc(line)}")
            w(f"    per-page 输出 == parser 实际输入（整份抽取按 \\f 切页）: "
              f"{b(rec.per_page_text.replace(kaiva_pdf.PAGE_SEPARATOR, '') == rec.page_text)}")
        labels_in_header = [
            (i, key) for i, line in enumerate(rec.page_text.splitlines()[:kaiva_pdf.HEADER_SCAN_LINES])
            for key, _, _ in kaiva_pdf._iter_label_spans(line)
        ]
        w(f"    header 窗口内识别到的标签 (行, 字段): {labels_in_header}")
        w(f"    SECTION 标签存在: {b(any(k == 'section' for _, k in labels_in_header))}")
        w(f"    re-derived source = {rec.source}; 取值行 {d.line_index}: {esc(d.raw_line)}")
        w(f"    parser section = {esc(rec.effective_section)}; corpus sections = {rec.corpus_sections}")
        body_title = next((ln for ln in rec.body.splitlines() if ln.strip()), "")
        w(f"    正文首个非空行（parser 剥离页眉后）: {esc(body_title)}")
    w("")

    # §2 形态
    w("§2 section 形态（corpus，有 chunk 的页，按 pdf_page）")
    w("  注: pLO-HI 是【有 chunk 的页】上连续同值的首末页；区间内被 parser 丢弃的页不计入 sources 计数。")
    by_doc: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for (doc_id, page), rec in sorted(pages.items()):
        if rec.chunk_ids:
            by_doc[doc_id].append((page, rec.effective_section))
    for doc_id in sorted(by_doc):
        items = by_doc[doc_id]
        distinct = sorted({v for _, v in items})
        digits = sum(1 for _, v in items if _PURE_DIGITS_RE.match(v))
        chapter_like = sum(1 for _, v in items if v.startswith(CHAPTER_PREFIX))
        w(f"  == {doc_id}: pages_with_chunks={len(items)} distinct={len(distinct)} "
          f"pure_digit_pages={digits} 'Chapter '-prefixed_pages={chapter_like}")
        runs = page_runs(items)
        limit = len(runs) if doc_id == DECISIVE_DOC_ID else DISTINCT_SAMPLE_LIMIT
        seen: list[str] = []
        shown = 0
        for lo, hi, value in runs:
            if doc_id != DECISIVE_DOC_ID:
                if value in seen:
                    continue
                seen.append(value)
            if shown >= limit:
                break
            src = Counter(pages[(doc_id, p)].source for p in range(lo, hi + 1) if pages[(doc_id, p)].chunk_ids)
            w(f"     p{lo}-{hi}: {esc(value)}  sources={dict(sorted(src.items()))}")
            shown += 1
        if doc_id != DECISIVE_DOC_ID and len(distinct) > shown:
            w(f"     ...（另有 {len(distinct) - shown} 个 distinct 值未列出，见 CSV）")
    w("")

    # §3 gold
    w("§3 38 条 gold citation 逐条")
    counts = Counter(r["gold_class"] for r in gold_results)
    w("  " + "  ".join(f"{c}={counts.get(c, 0)}" for c in GOLD_CLASS_ORDER) + f"  total={len(gold_results)}")
    sem = Counter(r["semantic_location_match"] for r in gold_results)
    w(f"  semantic_location_match: yes={sem.get(SEMANTIC_YES, 0)} no={sem.get(SEMANTIC_NO, 0)} unresolved={sem.get(SEMANTIC_UNRESOLVED, 0)}")
    w(f"  gold source 分布: {dict(sorted(Counter(r['parser_section_source'] for r in gold_results).items()))}")
    mism = [r for r in gold_results if r["exact_section_match"] != "true"]
    w(f"  exact mismatch source 分布: {dict(sorted(Counter(r['parser_section_source'] for r in mism).items()))}")
    for r in gold_results:
        w(f"  {r['question_id']:<5} #{r['citation_index']} {r['question_type']:<12} {r['doc_id']:<4} p{r['pdf_page']:<4} "
          f"gold={r['gold_section']:<14} parser={r['parser_effective_section']:<10} src={r['parser_section_source']:<34} "
          f"exact={r['exact_section_match']:<5} semantic={r['semantic_location_match']:<3} {r['gold_class']}")
    w("")

    # §4 TACM
    w("§4 TACM p.104-120（native 可读）")
    tv = Counter(r["tacm_verdict"] for r in tacm_results)
    w("  " + "  ".join(f"{v}={tv.get(v, 0)}" for v in TACM_VERDICT_ORDER))
    w(f"  source 分布: {dict(sorted(Counter(r['parser_section_source'] for r in tacm_results).items()))}")
    for r in tacm_results:
        rec = pages[(TACM_DOC_ID, int(r["pdf_page"]))]
        first_lines = [ln.strip() for ln in rec.page_text.splitlines() if ln.strip()][:3]
        w(f"  p{r['pdf_page']}: parser={r['parser_effective_section']} src={r['parser_section_source']} "
          f"line{r['parser_section_source_line_index']}={r['parser_section_source_raw_line']}")
        w(f"        chunks={r['n_chunks_on_page']} prev={r['prev_page_effective_section']} next={r['next_page_effective_section']} "
          f"source_line_removed_from_body={r['source_line_removed_from_body']}")
        w(f"        first_lines={' | '.join(esc(x)[:100] for x in first_lines)}")
        w(f"        verdict={r['tacm_verdict']} S={r['tacm_evidence_section']} evidence={r['tacm_evidence']}")
    w("  4.1 TACM p.104-120 页眉窗口内是否有任何标签（DOCUMENT ID / SECTION / ...）:")
    for page in range(TACM_NATIVE_AUDIT_PAGES[0], TACM_NATIVE_AUDIT_PAGES[1] + 1):
        rec = pages[(TACM_DOC_ID, page)]
        labels = sorted({key for line in rec.page_text.splitlines()[:kaiva_pdf.HEADER_SCAN_LINES]
                         for key, _, _ in kaiva_pdf._iter_label_spans(line)})
        w(f"        p{page}: {labels}")
    w("  4.2 '值合法 ≠ 值正确' 检查 TACM p.95-103（乱码区尾部）:")
    tacm_vocab = sorted(vocab[TACM_DOC_ID], key=lambda v: (len(v), v))
    w(f"        TACM header 词表 V(TACM) = {[esc(v) for v in tacm_vocab]}")
    for page in range(TACM_VALID_VALUE_CHECK_PAGES[0], TACM_VALID_VALUE_CHECK_PAGES[1] + 1):
        rec = pages[(TACM_DOC_ID, page)]
        w(f"        p{page}: section={esc(rec.effective_section)} in_V={b(rec.effective_section in vocab[TACM_DOC_ID])} "
          f"src={rec.source} line{rec.derivation.line_index}={esc(rec.derivation.raw_line)} chunks={len(rec.chunk_ids)}")
    w("")

    # §5 anomaly
    w("§5 全 corpus anomaly_candidate 普查（页级；candidate ≠ wrong_section）")
    n_chunked = sum(1 for r in pages.values() if r.chunk_ids)
    w(f"  有 chunk 的页 = {n_chunked}；candidate 页 = {len(anomaly_keys)}；"
      f"candidate 页上的 chunk = {sum(len(pages[k].chunk_ids) for k in anomaly_keys)}")
    rule_counts = Counter(rule for k in anomaly_keys for rule in pages[k].anomaly_rules)
    for rid, _ in ANOMALY_RULES:
        docs = Counter(k[0] for k in anomaly_keys if rid in pages[k].anomaly_rules)
        w(f"    {rid:<32} pages={rule_counts.get(rid, 0):<4} by_doc={dict(sorted(docs.items()))}")
    digits_pages = Counter(k[0] for k, r in sorted(pages.items()) if r.chunk_ids and _PURE_DIGITS_RE.match(r.effective_section))
    w(f"    （描述性）pure_digits 页: total={sum(digits_pages.values())} by_doc={dict(sorted(digits_pages.items()))}")
    single_alnum = Counter(k[0] for k, r in sorted(pages.items()) if r.chunk_ids and len(r.effective_section.strip()) == 1
                           and r.effective_section.strip().isascii() and r.effective_section.strip().isalnum())
    w(f"    （描述性）单个 ASCII 字母/数字 页: total={sum(single_alnum.values())} by_doc={dict(sorted(single_alnum.items()))}")
    w(f"    （描述性）同一 doc distinct section 数: "
      f"{ {d: len({r.effective_section for k, r in pages.items() if k[0] == d and r.chunk_ids}) for d in sorted(by_doc)} }")
    w(f"  candidate 页 by_doc: {dict(sorted(Counter(k[0] for k in anomaly_keys).items()))}")
    w(f"  candidate 页 by_source: {dict(sorted(Counter(pages[k].source for k in anomaly_keys).items()))}")
    only_r10 = [k for k in anomaly_keys if pages[k].anomaly_rules == ["R10_not_in_doc_header_vocab"]]
    w(f"  仅命中 R10 的页 = {len(only_r10)}")
    w("  全部 candidate（doc p: section | rules | source | raw_line）:")
    for k in anomaly_keys:
        rec = pages[k]
        w(f"    {k[0]:<4} p{k[1]:<4} {esc(rec.effective_section)[:90]} | {';'.join(rec.anomaly_rules)} | {rec.source} | "
          f"{esc((rec.derivation.raw_line or '').strip())[:90]}")
    w("")

    # §6 source 分布
    w("§6 section_source 分布（re-derivation；粒度可区分到 title fallback 的三个子分支）")
    pc = Counter(r.source for r in pages.values() if r.chunk_ids)
    cc = Counter()
    for r in pages.values():
        cc[r.source] += len(r.chunk_ids)
    allp = Counter(r.source for r in pages.values())
    w("  全 corpus（有 chunk 的页 / chunk 数 / 含被丢弃页的全部 PDF 页）:")
    for s in SOURCE_ORDER:
        w(f"    {s:<36} pages={pc.get(s, 0):<5} chunks={cc.get(s, 0):<5} all_pdf_pages={allp.get(s, 0)}")
    w("  按 doc_id（有 chunk 的页）:")
    for doc_id in sorted(by_doc):
        per = Counter(pages[(doc_id, p)].source for p, _ in by_doc[doc_id])
        w(f"    {doc_id:<5} " + " ".join(f"{s}={per.get(s, 0)}" for s in SOURCE_ORDER if per.get(s, 0)))
    lo, hi = TACM_GARBLED_PAGES
    garbled = [pages[(TACM_DOC_ID, p)] for p in range(lo, hi + 1)]
    gsrc_pages = Counter(r.source for r in garbled if r.chunk_ids)
    gsrc_chunks: Counter = Counter()
    for r in garbled:
        if r.chunk_ids:
            gsrc_chunks[r.source] += len(r.chunk_ids)
    w(f"  TACM p.{lo}-{hi}: pages_with_chunks={sum(gsrc_pages.values())} chunks={sum(gsrc_chunks.values())} "
      f"by_source(pages)={dict(sorted(gsrc_pages.items()))} by_source(chunks)={dict(sorted(gsrc_chunks.items()))}")
    lo, hi = TACM_NATIVE_AUDIT_PAGES
    native = [pages[(TACM_DOC_ID, p)] for p in range(lo, hi + 1)]
    nsrc: Counter = Counter()
    for r in native:
        if r.chunk_ids:
            nsrc[r.source] += len(r.chunk_ids)
    w(f"  TACM p.{lo}-{hi}: by_source(pages)={dict(sorted(Counter(r.source for r in native if r.chunk_ids).items()))} "
      f"by_source(chunks)={dict(sorted(nsrc.items()))}")
    inherited_chunked = sorted(k for k, r in pages.items() if r.chunk_ids and r.source in (SOURCE_INHERITED, SOURCE_UNRESOLVED))
    w(f"  有 chunk 且 source ∈ {{inherited, unresolved}} 的页: {len(inherited_chunked)}")
    w("")

    w("§7 section 取值行是否被 parser 从正文剥离（按 _strip_noise L436-451 复现；只看有 chunk 的页）")
    w("  removed=false → 该行文本（如 'PCL E-Learning Matrix Dry' / 问句）仍在送去分块的正文里")
    kept = Counter((r.source, source_line_removed(r)) for r in pages.values() if r.chunk_ids)
    for (s, k), n in sorted(kept.items()):
        w(f"    source={s:<36} removed={k or '(n/a)':<6} pages={n}")
    w("")

    with open(args.out_log, "w", encoding="utf-8") as handle:
        handle.write("\n".join(out) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
