#!/usr/bin/env python3
"""OCR fallback Phase A 调查：全语料逐页信号采集 + detector 校准报表。

只读调查脚本。不修改 PDF、不修改 corpus、不做 OCR、不改 parser 行为。

用法:
    python3 scripts/ocr_survey.py \\
        --pdf-dir "raw/KAIVA - Manuals" \\
        --corpus corpus/chunks.jsonl \\
        --confirmed-bad TACM:38-103 \\
        --out-csv experiments/ocr_survey/_page_signals.csv \\
        --out-log experiments/ocr_survey/_criterion_calibration.log

产出:
    --out-csv  每页一行，按 (source_filename, pdf_page) 稳定排序。逐字节确定性：
               不含时间戳、耗时或任何运行期可变量。
    --out-log  运行环境、耗时（⚠️ 耗时段落天然不确定）、分布、detector 校准结果、
               所有 unreviewed trigger 的审计清单。

标签契约（校准用，不是生产规则）:
    --confirmed-bad 给出的 (doc_id, 页区间) 标为 confirmed_bad，其余一律 unreviewed。
    unreviewed 不等于 good；本脚本不输出 FP/TN。

失败语义:
    - 单页采集失败（poppler 返回非零 / 超时 / 输出无法解析）记入该页 collect_status，
      不跳过该行；只要存在失败页，脚本在写完产物后以非零码退出。
    - 输入目录不存在、无 PDF、corpus 缺失、--confirmed-bad 格式错误 → 直接抛异常。

parser 等价字段（parser_*）:
    通过 import components.parsers.kaiva_pdf 的页眉解析与去噪函数【只读复用】，
    并按 parser.parse 的循环复现 section 继承与 CHUNK_MIN_CHARS 丢页判定。
    复现是否忠实，由脚本与 --corpus 逐页交叉核对（不一致即抛异常）。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import re
import statistics
import subprocess
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Callable, Sequence

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from components.parsers import kaiva_pdf  # noqa: E402  只读复用，见模块 docstring
from core import contracts  # noqa: E402

# ==============================================================================
# 模块常量
# ==============================================================================

PDF_SUFFIX: str = ".pdf"
POPPLER_TIMEOUT_S: float = 120.0
FORM_FEED: str = "\f"
HASH_READ_BLOCK_BYTES: int = 1 << 20

# 审计片段长度（用户规格：pdftotext 前 200 字符）。
TEXT_HEAD_CHARS: int = 200
# 用户规格第 5 节要求单独统计的字符数分界。
SHORT_PAGE_CHARS: int = 120
# unique_non_ascii 摘要里列出的最常见码位个数（仅展示用，不参与判定）。
TOP_CODEPOINTS_SHOWN: int = 5
# 分布报表的分位点（百分数）。
REPORT_PERCENTILES: tuple[int, ...] = (0, 1, 5, 25, 50, 75, 95, 99, 100)

# Unicode 区段（闭区间）。
C1_CONTROL_RANGE: tuple[int, int] = (0x80, 0x9F)
LATIN_EXTENDED_RANGE: tuple[int, int] = (0xA0, 0x24F)  # Latin-1 Supplement 可见部分 + Ext-A/B
PUA_RANGES: tuple[tuple[int, int], ...] = ((0xE000, 0xF8FF), (0xF0000, 0xFFFFD), (0x100000, 0x10FFFD))
REPLACEMENT_CHAR: int = 0xFFFD
# 不计入控制字符的 C0 字符：正常换行/制表。form feed 单独计数但计入 total。
NON_CONTROL_C0: frozenset[str] = frozenset({"\n", "\r", "\t"})

_T_NUMBER_FONT_RE = re.compile(r"^T\d+$")
# “字母词”：纯 ASCII 字母 ≥2，可带一个常见尾随标点。仅作描述性信号。
_ALPHA_TOKEN_RE = re.compile(r"^[A-Za-z]{2,}[.,;:)]?$")
_CONFIRMED_BAD_RE = re.compile(r"^(?P<doc>[^:]+):(?P<lo>\d+)-(?P<hi>\d+)$")

LABEL_CONFIRMED_BAD: str = "confirmed_bad"
LABEL_UNREVIEWED: str = "unreviewed"

SECTION_SOURCE_CURRENT: str = "current_page"
SECTION_SOURCE_INHERITED: str = "inherited"
SECTION_SOURCE_UNRESOLVED: str = "unresolved"

CSV_COLUMNS: tuple[str, ...] = (
    "doc_id", "source_filename", "pdf_page", "label", "collect_status",
    # structural —— pdffonts -f p -l p
    "font_count", "uni_yes_count", "uni_no_count", "uni_no_ratio",
    "has_type3", "has_custom_encoding", "has_font_name_none", "has_font_name_T_number",
    "mixed_uni_page", "font_types", "font_encodings",
    # native extraction —— pdftotext -layout -f p -l p
    "extracted_chars", "nonspace_chars",
    "printable_ascii_ratio", "alpha_ratio", "digit_ratio", "whitespace_ratio",
    "word_count", "mean_word_length", "alpha_token_ratio", "longest_whitespace_run",
    "control_char_count_total", "form_feed_count", "control_char_count_excluding_form_feed",
    "non_ascii_count", "latin_extended_count", "private_use_area_count",
    "replacement_character_count", "other_non_ascii_count",
    "unique_non_ascii_codepoints", "top_non_ascii_codepoints",
    "per_page_equals_wholedoc_split",
    # parser 等价 + corpus
    "parser_header_section", "parser_section_source", "parser_effective_section",
    "parser_body_chars", "parser_dropped_short", "corpus_chunk_count", "corpus_chunk_ids",
    # 页眉区（前 kaiva_pdf.HEADER_SCAN_LINES 行）—— citation 元数据所在区域的独立信号
    "header_nonspace_chars", "header_alpha_token_ratio", "header_control_chars",
    "text_head_200",
)


# ==============================================================================
# 基础工具
# ==============================================================================

class SurveyError(RuntimeError):
    """调查脚本的输入/环境错误。"""


def run_cmd(argv: Sequence[str]) -> str:
    """跑命令返回 stdout（utf-8, errors=replace 与 parser 一致）。

    抛出: SurveyError —— 命令不存在 / 非零返回 / 超时。
    """
    try:
        proc = subprocess.run(list(argv), capture_output=True, timeout=POPPLER_TIMEOUT_S)
    except FileNotFoundError as exc:
        raise SurveyError(f"命令不可用: {argv[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise SurveyError(f"超时 >{POPPLER_TIMEOUT_S}s: {' '.join(argv)}") from exc
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", errors="replace").strip()
        raise SurveyError(f"{argv[0]} 返回 {proc.returncode}: {detail}")
    return proc.stdout.decode("utf-8", errors="replace")


def tool_version(tool: str) -> str:
    """poppler 工具的版本行（-v 打到 stderr，返回码 0 或 99 视版本而定，故不看返回码）。"""
    proc = subprocess.run([tool, "-v"], capture_output=True, timeout=POPPLER_TIMEOUT_S)
    text = (proc.stdout + proc.stderr).decode("utf-8", errors="replace").strip()
    if not text:
        raise SurveyError(f"{tool} -v 无输出")
    return text.splitlines()[0]


def file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(HASH_READ_BLOCK_BYTES), b""):
            digest.update(block)
    return digest.hexdigest()


def esc(text: str | None) -> str:
    """把任意字符串转成纯 ASCII 的 JSON 字面量，保证 CSV/log 里控制字符可见且不破坏行结构。"""
    return json.dumps(text, ensure_ascii=True)


def page_count(path: str) -> int:
    for line in run_cmd(["pdfinfo", path]).splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":", 1)[1].strip())
    raise SurveyError(f"pdfinfo 无 Pages 行: {path}")


# ==============================================================================
# 信号
# ==============================================================================

@dataclass(frozen=True)
class FontRow:
    name: str
    type: str
    encoding: str
    uni: str


def parse_pdffonts(output: str) -> list[FontRow]:
    """按表头下的破折号行定列宽解析 pdffonts 输出（字体名/类型可含空格）。

    抛出: SurveyError —— 找不到表头，或 uni 列不是 yes/no。
    返回: 该页资源中引用的字体行；无字体时为 []（表头存在但无数据行）。
    """
    lines = output.splitlines()
    if len(lines) < 2 or not lines[1].startswith("-"):
        raise SurveyError(f"pdffonts 输出无表头: {output[:200]!r}")
    spans: list[tuple[int, int]] = [(m.start(), m.end()) for m in re.finditer(r"-+", lines[1])]
    header = [lines[0][s:e if i + 1 < len(spans) else None].strip() for i, (s, e) in enumerate(spans)]
    expected = ["name", "type", "encoding", "emb", "sub", "uni", "object ID"]
    if header[:6] != expected[:6]:
        raise SurveyError(f"pdffonts 表头不符合预期: {header}")
    rows: list[FontRow] = []
    for line in lines[2:]:
        if not line.strip():
            continue
        cells = [line[s:(spans[i + 1][0] if i + 1 < len(spans) else None)].strip() for i, (s, _) in enumerate(spans)]
        uni = cells[5]
        if uni not in ("yes", "no"):
            raise SurveyError(f"pdffonts uni 列异常: {line!r}")
        rows.append(FontRow(name=cells[0], type=cells[1], encoding=cells[2], uni=uni))
    return rows


def structural_signals(fonts: Sequence[FontRow]) -> dict[str, object]:
    uni_yes = sum(1 for f in fonts if f.uni == "yes")
    uni_no = sum(1 for f in fonts if f.uni == "no")
    return {
        "font_count": len(fonts),
        "uni_yes_count": uni_yes,
        "uni_no_count": uni_no,
        "uni_no_ratio": round(uni_no / len(fonts), 6) if fonts else "",
        "has_type3": int(any(f.type == "Type 3" for f in fonts)),
        "has_custom_encoding": int(any(f.encoding == "Custom" for f in fonts)),
        "has_font_name_none": int(any(f.name == "[none]" for f in fonts)),
        "has_font_name_T_number": int(any(_T_NUMBER_FONT_RE.match(f.name) for f in fonts)),
        "mixed_uni_page": int(uni_yes > 0 and uni_no > 0),
        "font_types": "|".join(sorted({f.type for f in fonts})),
        "font_encodings": "|".join(sorted({f.encoding for f in fonts})),
    }


def _in(cp: int, lo_hi: tuple[int, int]) -> bool:
    return lo_hi[0] <= cp <= lo_hi[1]


def output_signals(raw: str) -> dict[str, object]:
    """pdftotext 单页输出的描述性信号。口径（分母）写在 log 的“信号口径”段。"""
    form_feeds = raw.count(FORM_FEED)
    text = raw.replace(FORM_FEED, "")
    n = len(text)
    nonspace = [ch for ch in text if not ch.isspace()]
    ns = len(nonspace)

    control_total = sum(
        1 for ch in raw
        if (ord(ch) < 0x20 and ch not in NON_CONTROL_C0) or ord(ch) == 0x7F or _in(ord(ch), C1_CONTROL_RANGE)
    )
    non_ascii = [ord(ch) for ch in text if ord(ch) > 0x7F]
    latin_ext = sum(1 for cp in non_ascii if _in(cp, LATIN_EXTENDED_RANGE))
    pua = sum(1 for cp in non_ascii if any(_in(cp, r) for r in PUA_RANGES))
    repl = sum(1 for cp in non_ascii if cp == REPLACEMENT_CHAR)
    counts = Counter(non_ascii)
    top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP_CODEPOINTS_SHOWN]

    words = text.split()
    ws_runs = [len(m.group(0)) for m in re.finditer(r" +", text)]
    return {
        "extracted_chars": n,
        "nonspace_chars": ns,
        "printable_ascii_ratio": round(sum(1 for ch in text if 0x20 <= ord(ch) <= 0x7E or ch in NON_CONTROL_C0) / n, 6) if n else "",
        "alpha_ratio": round(sum(1 for ch in nonspace if ch.isascii() and ch.isalpha()) / ns, 6) if ns else "",
        "digit_ratio": round(sum(1 for ch in nonspace if ch.isascii() and ch.isdigit()) / ns, 6) if ns else "",
        "whitespace_ratio": round((n - ns) / n, 6) if n else "",
        "word_count": len(words),
        "mean_word_length": round(statistics.fmean(len(w) for w in words), 6) if words else "",
        "alpha_token_ratio": round(sum(1 for w in words if _ALPHA_TOKEN_RE.match(w)) / len(words), 6) if words else "",
        "longest_whitespace_run": max(ws_runs) if ws_runs else 0,
        "control_char_count_total": control_total,
        "form_feed_count": form_feeds,
        "control_char_count_excluding_form_feed": control_total - form_feeds,
        "non_ascii_count": len(non_ascii),
        "latin_extended_count": latin_ext,
        "private_use_area_count": pua,
        "replacement_character_count": repl,
        "other_non_ascii_count": len(non_ascii) - latin_ext - pua - repl,
        "unique_non_ascii_codepoints": len(counts),
        "top_non_ascii_codepoints": " ".join(f"U+{cp:04X}:{c}" for cp, c in top),
        "text_head_200": esc(text[:TEXT_HEAD_CHARS]),
    }


# ==============================================================================
# 采集
# ==============================================================================

@dataclass
class Timing:
    pdfinfo_s: float = 0.0
    pdffonts_s: float = 0.0
    pdftotext_per_page_s: float = 0.0
    pdftotext_wholedoc_s: float = 0.0
    parser_equiv_s: float = 0.0
    sha256_s: float = 0.0


def parse_confirmed_bad(specs: Sequence[str]) -> dict[str, tuple[int, int]]:
    out: dict[str, tuple[int, int]] = {}
    for spec in specs:
        m = _CONFIRMED_BAD_RE.match(spec)
        if m is None:
            raise SurveyError(f"--confirmed-bad 格式应为 DOC_ID:LO-HI，得到 {spec!r}")
        lo, hi = int(m.group("lo")), int(m.group("hi"))
        if lo < 1 or hi < lo:
            raise SurveyError(f"--confirmed-bad 页区间非法（pdf_page 从 1 开始）: {spec!r}")
        out[m.group("doc")] = (lo, hi)
    return out


def load_corpus(
    path: str,
) -> tuple[dict[str, str], dict[tuple[str, int], list[str]], dict[tuple[str, int], set[str]]]:
    """返回 (doc_name→doc_id, (doc_id,pdf_page)→按文件顺序的 chunk id 列表, (doc_id,pdf_page)→section 集合)。

    抛出: SurveyError —— 同一 doc_name 对应多个 doc_id（此时按文件名定 doc_id 不成立）。
    """
    name_to_id: dict[str, set[str]] = defaultdict(set)
    page_chunks: dict[tuple[str, int], list[str]] = defaultdict(list)
    page_sections: dict[tuple[str, int], set[str]] = defaultdict(set)
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            chunk = json.loads(line)
            name_to_id[chunk["doc_name"]].add(chunk["doc_id"])
            page_chunks[(chunk["doc_id"], chunk["pdf_page"])].append(chunk["id"])
            page_sections[(chunk["doc_id"], chunk["pdf_page"])].add(chunk["section"])
    resolved: dict[str, str] = {}
    for name, ids in name_to_id.items():
        if len(ids) != 1:
            raise SurveyError(f"corpus 中 {name} 对应多个 doc_id: {sorted(ids)}")
        resolved[name] = next(iter(ids))
    return resolved, page_chunks, page_sections


def collect(
    pdf_dir: str, corpus_path: str, confirmed_bad: dict[str, tuple[int, int]]
) -> tuple[list[dict[str, object]], dict[str, dict[str, object]], Timing]:
    """逐 PDF 逐页采集。返回 (rows, per_file_info, timing)。

    抛出: SurveyError —— 目录无 PDF / PDF 不在 corpus 中 / parser 复现与 corpus 不一致。
    单页 poppler 失败不抛，记入 collect_status。
    """
    if not os.path.isdir(pdf_dir):
        raise SurveyError(f"PDF 目录不存在: {pdf_dir}")
    filenames = sorted(f for f in os.listdir(pdf_dir) if f.lower().endswith(PDF_SUFFIX))
    if not filenames:
        raise SurveyError(f"目录下没有 PDF: {pdf_dir}")
    name_to_id, page_chunks, page_sections = load_corpus(corpus_path)
    for doc in confirmed_bad:
        if doc not in name_to_id.values():
            raise SurveyError(f"--confirmed-bad 的 doc_id 不在 corpus 中: {doc}")

    timing = Timing()
    rows: list[dict[str, object]] = []
    files: dict[str, dict[str, object]] = {}

    for filename in filenames:
        path = os.path.join(pdf_dir, filename)
        if filename not in name_to_id:
            raise SurveyError(f"PDF 不在 corpus 中，无法确定 doc_id: {filename}")
        doc_id = name_to_id[filename]

        t0 = time.perf_counter()
        sha = file_sha256(path)
        timing.sha256_s += time.perf_counter() - t0

        t0 = time.perf_counter()
        n_pages = page_count(path)
        timing.pdfinfo_s += time.perf_counter() - t0

        # parser 实际看到的输入：整份 -layout 抽取后按 \f 切页。
        t0 = time.perf_counter()
        whole = run_cmd([*kaiva_pdf.PDFTOTEXT_ARGS, path, "-"])
        timing.pdftotext_wholedoc_s += time.perf_counter() - t0
        whole_pages = whole.split(kaiva_pdf.PAGE_SEPARATOR)
        if whole_pages and not whole_pages[-1].strip():
            whole_pages.pop()
        if len(whole_pages) != n_pages:
            raise SurveyError(f"整份抽取分页数 {len(whole_pages)} ≠ pdfinfo {n_pages}: {filename}")

        files[filename] = {"doc_id": doc_id, "sha256": sha, "pages": n_pages}
        last_section: str | None = None
        lo_hi = confirmed_bad.get(doc_id)

        for page_no in range(1, n_pages + 1):
            row: dict[str, object] = {c: "" for c in CSV_COLUMNS}
            row.update(doc_id=doc_id, source_filename=filename, pdf_page=page_no)
            row["label"] = LABEL_CONFIRMED_BAD if lo_hi and lo_hi[0] <= page_no <= lo_hi[1] else LABEL_UNREVIEWED
            errors: list[str] = []

            t0 = time.perf_counter()
            try:
                fonts = parse_pdffonts(run_cmd(["pdffonts", "-f", str(page_no), "-l", str(page_no), path]))
                row.update(structural_signals(fonts))
            except SurveyError as exc:
                errors.append(f"pdffonts: {exc}")
            timing.pdffonts_s += time.perf_counter() - t0

            t0 = time.perf_counter()
            try:
                per_page = run_cmd([*kaiva_pdf.PDFTOTEXT_ARGS, "-f", str(page_no), "-l", str(page_no), path, "-"])
                row.update(output_signals(per_page))
                row["per_page_equals_wholedoc_split"] = int(per_page.replace(FORM_FEED, "") == whole_pages[page_no - 1])
            except SurveyError as exc:
                errors.append(f"pdftotext: {exc}")
            timing.pdftotext_per_page_s += time.perf_counter() - t0

            # parser 等价：逐行复现 KaivaPdfParser.parse 的 section 继承与短页丢弃。
            t0 = time.perf_counter()
            page_text = whole_pages[page_no - 1]
            meta = kaiva_pdf._extract_page_metadata(page_text)
            header_section = meta["section"]
            if header_section is not None:
                source = SECTION_SOURCE_CURRENT
                effective = header_section
                last_section = header_section
            elif last_section is not None:
                source = SECTION_SOURCE_INHERITED
                effective = last_section
            else:
                source = SECTION_SOURCE_UNRESOLVED
                effective = kaiva_pdf.UNKNOWN_SECTION
            header_sig = output_signals("\n".join(page_text.splitlines()[:kaiva_pdf.HEADER_SCAN_LINES]))
            row.update(
                header_nonspace_chars=header_sig["nonspace_chars"],
                header_alpha_token_ratio=header_sig["alpha_token_ratio"],
                header_control_chars=header_sig["control_char_count_excluding_form_feed"],
            )
            body = kaiva_pdf._strip_noise(page_text, meta)
            dropped = len(body) < contracts.CHUNK_MIN_CHARS
            chunk_ids = page_chunks.get((doc_id, page_no), [])
            n_chunks = len(chunk_ids)
            timing.parser_equiv_s += time.perf_counter() - t0

            if dropped != (n_chunks == 0):
                raise SurveyError(
                    f"parser 复现与 corpus 不一致（丢页判定）: {filename} p{page_no} "
                    f"body={len(body)} corpus_chunks={n_chunks}"
                )
            if n_chunks and page_sections[(doc_id, page_no)] != {effective}:
                raise SurveyError(
                    f"parser 复现与 corpus 不一致（section）: {filename} p{page_no} "
                    f"复现={effective!r} corpus={sorted(page_sections[(doc_id, page_no)])!r}"
                )

            row.update(
                parser_header_section=esc(header_section),
                parser_section_source=source,
                parser_effective_section=esc(effective),
                parser_body_chars=len(body),
                parser_dropped_short=int(dropped),
                corpus_chunk_count=n_chunks,
                corpus_chunk_ids=" ".join(chunk_ids),
            )
            row["collect_status"] = "ok" if not errors else "error: " + " ; ".join(errors)
            rows.append(row)

    rows.sort(key=lambda r: (str(r["source_filename"]), int(r["pdf_page"])))
    return rows, files, timing


def write_csv(rows: Sequence[dict[str, object]], path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


# ==============================================================================
# 报表
# ==============================================================================

Row = dict[str, object]
Predicate = Callable[[Row], bool]

# 输出信号的“坏方向”。只描述 confirmed_bad 相对全语料落在哪一侧，不含阈值。
LOW_IS_BAD_SIGNALS: tuple[str, ...] = ("alpha_token_ratio", "alpha_ratio", "printable_ascii_ratio")
HIGH_IS_BAD_SIGNALS: tuple[str, ...] = (
    "control_char_count_excluding_form_feed", "latin_extended_count", "digit_ratio",
)
DISTRIBUTION_SIGNALS: tuple[str, ...] = (
    "font_count", "uni_no_ratio", "extracted_chars", "nonspace_chars", "printable_ascii_ratio",
    "alpha_ratio", "digit_ratio", "whitespace_ratio", "word_count", "mean_word_length",
    "alpha_token_ratio", "longest_whitespace_run", "control_char_count_excluding_form_feed",
    "latin_extended_count", "private_use_area_count", "replacement_character_count",
    "other_non_ascii_count", "unique_non_ascii_codepoints", "parser_body_chars",
    "header_nonspace_chars", "header_alpha_token_ratio", "header_control_chars",
)
AUDIT_STRUCT_COLS: tuple[str, ...] = (
    "font_count", "uni_yes_count", "uni_no_count", "has_type3", "has_custom_encoding",
    "has_font_name_none", "has_font_name_T_number", "mixed_uni_page", "font_types", "font_encodings",
)
AUDIT_OUTPUT_COLS: tuple[str, ...] = (
    "extracted_chars", "nonspace_chars", "printable_ascii_ratio", "alpha_ratio", "digit_ratio",
    "alpha_token_ratio", "control_char_count_excluding_form_feed", "latin_extended_count",
    "private_use_area_count", "other_non_ascii_count", "top_non_ascii_codepoints",
    "parser_body_chars", "corpus_chunk_count",
)


def num(row: Row, key: str) -> float | None:
    """数值字段；空串（该页信号无定义，如无文本时的比值）返回 None。"""
    value = row[key]
    return None if value == "" else float(value)  # type: ignore[arg-type]


def pct(values: Sequence[float], p: int) -> float:
    """最近秩分位数（确定性，无插值）。输入非空。"""
    ordered = sorted(values)
    rank = max(0, min(len(ordered) - 1, round(p / 100 * (len(ordered) - 1))))
    return ordered[rank]


def page_ranges(rows: Sequence[Row]) -> str:
    """把页清单压成 DOC:p1-3,7 的紧凑形式，仅用于可读性；完整审计见逐页段落。"""
    by_doc: dict[str, list[int]] = defaultdict(list)
    for r in rows:
        by_doc[str(r["doc_id"])].append(int(r["pdf_page"]))  # type: ignore[arg-type]
    parts: list[str] = []
    for doc in sorted(by_doc):
        pages = sorted(by_doc[doc])
        spans: list[str] = []
        start = prev = pages[0]
        for p in pages[1:] + [None]:  # type: ignore[list-item]
            if p is not None and p == prev + 1:
                prev = p
                continue
            spans.append(f"{start}-{prev}" if start != prev else f"{start}")
            if p is not None:
                start = prev = p
        parts.append(f"{doc}:p" + ",".join(spans))
    return " ; ".join(parts) if parts else "(none)"


def signal_descriptor(row: Row) -> str:
    """【信号派生】的描述标签，不是人工核验。规则即下列分支本身，逐页可复算。"""
    if int(row["nonspace_chars"]) == 0:  # type: ignore[arg-type]
        return "no_extracted_text"
    if int(row["control_char_count_excluding_form_feed"]) > 0:  # type: ignore[arg-type]
        return "suspicious:control_chars_present"
    if num(row, "alpha_token_ratio") == 0.0:
        return "suspicious:no_ascii_word_tokens"
    if int(row["parser_body_chars"]) < contracts.CHUNK_MIN_CHARS:  # type: ignore[arg-type]
        return "header_or_short_text_only"
    return "head_has_ascii_word_tokens_no_control_chars"


@dataclass(frozen=True)
class Detector:
    family: str
    name: str
    rule: str
    predicate: Predicate


def detector_stats(det: Detector, rows: Sequence[Row]) -> dict[str, object]:
    bad = [r for r in rows if r["label"] == LABEL_CONFIRMED_BAD]
    unrev = [r for r in rows if r["label"] == LABEL_UNREVIEWED]
    bad_hit = [r for r in bad if det.predicate(r)]
    unrev_hit = [r for r in unrev if det.predicate(r)]
    return {
        "confirmed_bad_total": len(bad),
        "confirmed_bad_triggered": len(bad_hit),
        "confirmed_bad_missed": len(bad) - len(bad_hit),
        "confirmed_bad_recall": round(len(bad_hit) / len(bad), 4) if bad else "",
        "unreviewed_total": len(unrev),
        "unreviewed_triggered": len(unrev_hit),
        "unreviewed_trigger_rate": round(len(unrev_hit) / len(unrev), 4) if unrev else "",
        "_bad_missed_rows": [r for r in bad if not det.predicate(r)],
        "_unrev_hit_rows": unrev_hit,
    }


def build_detectors(rows: Sequence[Row], out: list[str]) -> list[Detector]:
    """构造 A/B/C 三族候选 detector；B 的阈值由本次数据的分布端点推出，并把推导写进 out。

    抛出: SurveyError —— 没有 confirmed_bad 页（无法校准）。
    """
    bad = [r for r in rows if r["label"] == LABEL_CONFIRMED_BAD]
    unrev = [r for r in rows if r["label"] == LABEL_UNREVIEWED]
    if not bad:
        raise SurveyError("没有 confirmed_bad 页，无法做 detector 校准")

    dets: list[Detector] = [
        Detector("A", "A1_any_uni_no", "uni_no_count >= 1", lambda r: int(r["uni_no_count"]) >= 1),  # type: ignore[arg-type]
        Detector("A", "A2_all_fonts_uni_no", "font_count >= 1 and uni_no_count == font_count",
                 lambda r: int(r["font_count"]) >= 1 and r["uni_no_count"] == r["font_count"]),  # type: ignore[arg-type]
        Detector("A", "A3_mixed_uni_page", "mixed_uni_page == 1", lambda r: r["mixed_uni_page"] == 1 or r["mixed_uni_page"] == "1"),
        Detector("A", "A4_type3", "has_type3 == 1", lambda r: str(r["has_type3"]) == "1"),
        Detector("A", "A5_custom_encoding", "has_custom_encoding == 1", lambda r: str(r["has_custom_encoding"]) == "1"),
        Detector("A", "A6_type3_and_custom", "has_type3 and has_custom_encoding",
                 lambda r: str(r["has_type3"]) == "1" and str(r["has_custom_encoding"]) == "1"),
        Detector("A", "A7_type3_or_custom", "has_type3 or has_custom_encoding",
                 lambda r: str(r["has_type3"]) == "1" or str(r["has_custom_encoding"]) == "1"),
        Detector("A", "A8_font_name_T_number", "has_font_name_T_number == 1", lambda r: str(r["has_font_name_T_number"]) == "1"),
        Detector("A", "A9_uni_no_and_type3_or_custom", "uni_no_count >= 1 and (has_type3 or has_custom_encoding)",
                 lambda r: int(r["uni_no_count"]) >= 1 and (str(r["has_type3"]) == "1" or str(r["has_custom_encoding"]) == "1")),  # type: ignore[arg-type]
    ]

    out.append("B 阈值推导（只用本次数据的分布端点，无经验常数）：")
    out.append("  对每个输出信号，只在该信号有定义的页上取值（无文本页比值无定义，恒不触发）。")
    out.append("  t_recall  = confirmed_bad 的端点 → 在有定义的 confirmed_bad 页上 recall 最大的最松阈值")
    out.append("  t_zero_ut = unreviewed 的端点   → 不触发任何 unreviewed 页的最松阈值")
    out.append("  ⚠️ t_zero_ut 只描述“这批 unreviewed 页的取值端点”，不代表这些页是好页；")
    out.append("     两个阈值都过拟合于单一文档单一坏区间（TACM），换语料必须重新校准。")
    thresholds: dict[str, dict[str, float]] = {}
    for key in LOW_IS_BAD_SIGNALS + HIGH_IS_BAD_SIGNALS:
        bvals = [v for v in (num(r, key) for r in bad) if v is not None]
        uvals = [v for v in (num(r, key) for r in unrev) if v is not None]
        low_bad = key in LOW_IS_BAD_SIGNALS
        t_recall = max(bvals) if low_bad else min(bvals)
        t_zero = min(uvals) if low_bad else max(uvals)
        thresholds[key] = {"t_recall": t_recall, "t_zero_ut": t_zero}
        sep = (t_recall < t_zero) if low_bad else (t_recall > t_zero)
        out.append(
            f"  {key:<42} dir={'low' if low_bad else 'high'}_is_bad  bad_defined={len(bvals)}/{len(bad)}  "
            f"t_recall={t_recall:g}  t_zero_ut={t_zero:g}  confirmed_bad 与 unreviewed 取值区间不相交={sep}"
        )

        def mk(k: str, t: float, low: bool, strict: bool) -> Predicate:
            def pred(r: Row) -> bool:
                v = num(r, k)
                if v is None:
                    return False
                if low:
                    return v < t if strict else v <= t
                return v > t if strict else v >= t
            return pred

        op_r, op_z = ("<=", "<") if low_bad else (">=", ">")
        all_defined = [v for v in (num(r, key) for r in rows) if v is not None]
        degenerate = all((v <= t_recall) if low_bad else (v >= t_recall) for v in all_defined)
        if degenerate:
            out.append(f"    ↳ t_recall 退化：{key} {op_r} {t_recall:g} 覆盖全部有定义页，不构成 detector，跳过")
        else:
            dets.append(Detector("B", f"B_{key}@t_recall", f"{key} {op_r} {t_recall:g}", mk(key, t_recall, low_bad, False)))
        dets.append(Detector("B", f"B_{key}@t_zero_ut", f"{key} {op_z} {t_zero:g}", mk(key, t_zero, low_bad, True)))

    atr_r = thresholds["alpha_token_ratio"]["t_recall"]
    ctl_r = thresholds["control_char_count_excluding_form_feed"]["t_recall"]
    ctl_z = thresholds["control_char_count_excluding_form_feed"]["t_zero_ut"]

    def atr_bad(r: Row) -> bool:
        v = num(r, "alpha_token_ratio")
        return v is not None and v <= atr_r

    def ctl_bad(r: Row) -> bool:
        return int(r["control_char_count_excluding_form_feed"]) > ctl_z  # type: ignore[arg-type]

    def struct_tc(r: Row) -> bool:
        return str(r["has_type3"]) == "1" or str(r["has_custom_encoding"]) == "1"

    dets += [
        Detector("B", "B_or_atr@t_recall_or_ctl@t_zero_ut",
                 f"alpha_token_ratio <= {atr_r:g} or control_excl_ff > {ctl_z:g}",
                 lambda r: atr_bad(r) or ctl_bad(r)),
        Detector("C", "C1_type3orcustom_AND_atr",
                 f"(has_type3 or has_custom_encoding) and alpha_token_ratio <= {atr_r:g}",
                 lambda r: struct_tc(r) and atr_bad(r)),
        Detector("C", "C2_type3orcustom_OR_atr",
                 f"(has_type3 or has_custom_encoding) or alpha_token_ratio <= {atr_r:g}",
                 lambda r: struct_tc(r) or atr_bad(r)),
        Detector("C", "C3_any_uni_no_AND_atr",
                 f"uni_no_count >= 1 and alpha_token_ratio <= {atr_r:g}",
                 lambda r: int(r["uni_no_count"]) >= 1 and atr_bad(r)),  # type: ignore[arg-type]
        Detector("C", "C4_any_uni_no_AND_(atr_or_ctl)",
                 f"uni_no_count >= 1 and (alpha_token_ratio <= {atr_r:g} or control_excl_ff > {ctl_z:g})",
                 lambda r: int(r["uni_no_count"]) >= 1 and (atr_bad(r) or ctl_bad(r))),  # type: ignore[arg-type]
        Detector("C", "C5_all_uni_no_AND_atr",
                 f"font_count >= 1 and uni_no_count == font_count and alpha_token_ratio <= {atr_r:g}",
                 lambda r: int(r["font_count"]) >= 1 and r["uni_no_count"] == r["font_count"] and atr_bad(r)),  # type: ignore[arg-type]
    ]
    out.append(f"  （C 族引用：alpha_token_ratio t_recall={atr_r:g}；control_excl_ff t_recall={ctl_r:g}, t_zero_ut={ctl_z:g}）")
    return dets


def audit_line(r: Row) -> str:
    struct = " ".join(f"{c}={r[c]}" for c in AUDIT_STRUCT_COLS)
    output = " ".join(f"{c}={r[c]}" for c in AUDIT_OUTPUT_COLS)
    return (
        f"{r['doc_id']} | {r['source_filename']} | pdf_page={r['pdf_page']} | label={r['label']}\n"
        f"    struct: {struct}\n    output: {output}\n"
        f"    signal_descriptor(非人工核验)={signal_descriptor(r)}\n"
        f"    head200={r['text_head_200']}"
    )


def write_log(args, env, files, rows: Sequence[Row], timing: Timing, total_s: float) -> None:
    """写校准报表。除【运行耗时】段外，内容只依赖输入，逐字节确定。"""
    out: list[str] = []
    w = out.append
    bad = [r for r in rows if r["label"] == LABEL_CONFIRMED_BAD]
    unrev = [r for r in rows if r["label"] == LABEL_UNREVIEWED]

    w("# OCR fallback Phase A —— 逐页信号调查与 detector 校准")
    w("# 标签契约: confirmed_bad = --confirmed-bad 指定区间；其余全部 unreviewed（≠ good）。不输出 FP/TN。")
    w(f"# 命令参数: pdf_dir={args.pdf_dir!r} corpus={args.corpus!r} confirmed_bad={args.confirmed_bad!r}")
    w("")
    w("== 1. 运行环境 ==")
    for k in ("python", "pdffonts", "pdftotext", "git_commit", "corpus_sha256"):
        w(f"  {k}: {env[k]}")
    w(f"  CHUNK_MIN_CHARS (contracts): {contracts.CHUNK_MIN_CHARS}")
    w(f"  HEADER_SCAN_LINES (parser): {kaiva_pdf.HEADER_SCAN_LINES}")
    w("  source files:")
    for fn in sorted(files):
        info = files[fn]
        w(f"    {info['doc_id']:<5} pages={info['pages']:<4} sha256={info['sha256']}  {fn}")

    w("")
    w("== 2. 采集完成情况 ==")
    failures = [r for r in rows if r["collect_status"] != "ok"]
    w(f"  PDF 数={len(files)}  总页数={len(rows)}  采集失败页={len(failures)}")
    for r in failures:
        w(f"    FAIL {r['doc_id']} p{r['pdf_page']}: {r['collect_status']}")
    eq = sum(1 for r in rows if str(r["per_page_equals_wholedoc_split"]) == "1")
    w(f"  逐页 pdftotext 输出（去 \\f）== 整份抽取按 \\f 切页 的页数: {eq}/{len(rows)}")
    w("  parser 复现（section 继承 / CHUNK_MIN_CHARS 丢页）与 corpus 逐页一致：是（不一致会在采集阶段抛异常）")

    w("")
    w("== 3. 运行耗时（⚠️ 本段天然不确定，不参与确定性比较） ==")
    for k, v in timing.__dict__.items():
        w(f"  {k}: {v:.3f}")
    w(f"  total_s: {total_s:.3f}")

    w("")
    w("== 4. 信号口径 ==")
    w("  extracted_chars: pdftotext -layout 单页输出去掉 \\f 后的字符数；nonspace_chars: 其中非空白字符数")
    w("  printable_ascii_ratio: (0x20–0x7E 或 \\n\\r\\t) / extracted_chars")
    w("  alpha_ratio / digit_ratio: ASCII 字母 / 数字 占 nonspace_chars 的比例")
    w("  whitespace_ratio: 空白 / extracted_chars；longest_whitespace_run: 最长连续空格（仅 U+0020）")
    w("  word_count: 按空白切分的 token 数；alpha_token_ratio: 形如 [A-Za-z]{2,} 可带一个 .,;:) 的 token 占比")
    w("  control_char_count_total: C0(除 \\n\\r\\t) + DEL + C1，含 \\f；form_feed 单独计；excluding_form_feed = total - form_feed")
    w("  latin_extended: U+00A0–U+024F；PUA: U+E000–F8FF 与 plane 15/16；other_non_ascii = non_ascii - latin_ext - PUA - U+FFFD")
    w("  header_*: parser 实际输入页（整份抽取切页）的前 HEADER_SCAN_LINES 行上的同口径信号 —— citation 元数据所在区域")
    w("  比值类信号在分母为 0 时无定义（CSV 为空串），不参与分布，detector 恒不触发。")

    w("")
    w("== 5. 分布（最近秩分位；只含有定义的页） ==")
    w(f"  {'signal':<42} {'label':<14} {'n':>5}  " + "  ".join(f"p{p:<3}" for p in REPORT_PERCENTILES))
    for key in DISTRIBUTION_SIGNALS:
        for label, grp in ((LABEL_CONFIRMED_BAD, bad), (LABEL_UNREVIEWED, unrev)):
            vals = [v for v in (num(r, key) for r in grp) if v is not None]
            cells = "  ".join(f"{pct(vals, p):<4g}" for p in REPORT_PERCENTILES) if vals else "(无定义)"
            w(f"  {key:<42} {label:<14} {len(vals):>5}  {cells}")
    w("  结构布尔信号计数（confirmed_bad / unreviewed）:")
    for key in ("has_type3", "has_custom_encoding", "has_font_name_none", "has_font_name_T_number", "mixed_uni_page"):
        w(f"    {key:<26} {sum(1 for r in bad if str(r[key]) == '1'):>4}/{len(bad)}   {sum(1 for r in unrev if str(r[key]) == '1'):>5}/{len(unrev)}")
    w("  unreviewed 中含 uni=no 字体页的 (font_types, font_encodings) 组合:")
    combo = Counter((r["font_types"], r["font_encodings"]) for r in unrev if int(r["uni_no_count"]) >= 1)  # type: ignore[arg-type]
    for (t, e), c in sorted(combo.items(), key=lambda kv: (-kv[1], kv[0])):
        w(f"    {c:>5}  types={t}  encodings={e}")
    w("  unreviewed 中含 uni=no 字体页的 doc 分布: " + json.dumps(dict(sorted(Counter(r['doc_id'] for r in unrev if int(r['uni_no_count']) >= 1).items()))))  # type: ignore[arg-type]

    w("")
    w("== 6. Detector 校准 ==")
    derivation: list[str] = []
    dets = build_detectors(rows, derivation)
    for line in derivation:
        w(line)
    w("")
    w(f"  {'detector':<46} {'bad_trig':>8} {'missed':>6} {'recall':>7} {'unrev_trig':>10} {'rate':>7}  rule")
    stats = {d.name: detector_stats(d, rows) for d in dets}
    for d in dets:
        s = stats[d.name]
        w(f"  {d.name:<46} {s['confirmed_bad_triggered']:>8} {s['confirmed_bad_missed']:>6} {s['confirmed_bad_recall']:>7} "
          f"{s['unreviewed_triggered']:>10} {s['unreviewed_trigger_rate']:>7}  {d.rule}")
    w("")
    w("  每个 detector 的 confirmed_bad missed 与 unreviewed trigger 页清单（紧凑形式；逐页审计见 §7）:")
    for d in dets:
        s = stats[d.name]
        w(f"  [{d.name}]")
        w(f"    confirmed_bad_missed: {page_ranges(s['_bad_missed_rows'])}")  # type: ignore[arg-type]
        w(f"    unreviewed_triggered ({s['unreviewed_triggered']}): {page_ranges(s['_unrev_hit_rows'])}")  # type: ignore[arg-type]
        desc = Counter(signal_descriptor(r) for r in s["_unrev_hit_rows"])  # type: ignore[union-attr]
        w(f"    unreviewed_triggered 的 signal_descriptor 分布(非人工核验): {json.dumps(dict(sorted(desc.items())))}")

    w("")
    w("== 7. 逐页审计：被任一 detector 触发的全部 unreviewed 页（每页一次，列出触发它的 detector） ==")
    w("  observation 列只有 signal_descriptor（由 signal_descriptor() 的分支规则算出），不是人工核验，不称 false positive。")
    for r in unrev:
        hit_by = [d.name for d in dets if d.predicate(r)]
        if hit_by:
            w(audit_line(r))
            w(f"    triggered_by={','.join(hit_by)}")

    w("")
    w("== 8. confirmed_bad 逐页（含 missed） ==")
    for r in bad:
        w(audit_line(r))
        w(f"    triggered_by={','.join(d.name for d in dets if d.predicate(r))}")

    w("")
    w("== 9. 无文本 / 短文本 / parser 丢页 ==")
    zero = [r for r in rows if int(r["extracted_chars"]) == 0]  # type: ignore[arg-type]
    short = [r for r in rows if 0 < int(r["extracted_chars"]) < SHORT_PAGE_CHARS]  # type: ignore[arg-type]
    below_min = [r for r in rows if int(r["extracted_chars"]) < contracts.CHUNK_MIN_CHARS]  # type: ignore[arg-type]
    dropped = [r for r in rows if str(r["parser_dropped_short"]) == "1"]
    for title, grp in (
        ("extracted_chars == 0", zero),
        (f"0 < extracted_chars < {SHORT_PAGE_CHARS}", short),
        (f"extracted_chars < CHUNK_MIN_CHARS({contracts.CHUNK_MIN_CHARS})", below_min),
        (f"parser_body_chars < CHUNK_MIN_CHARS（去页眉页脚后，parser 实际丢弃，无 chunk）", dropped),
    ):
        w(f"  {title}: {len(grp)}  by_doc={json.dumps(dict(sorted(Counter(r['doc_id'] for r in grp).items())))}  "
          f"by_label={json.dumps(dict(sorted(Counter(r['label'] for r in grp).items())))}")
        w(f"    pages: {page_ranges(grp)}")
    w("  parser 丢弃页逐页（extracted_chars 高而 body 低 = 文本层几乎只有页眉页脚）:")
    for r in dropped:
        w(f"    {r['doc_id']} p{r['pdf_page']} label={r['label']} fonts={r['font_count']} types={r['font_types']} "
          f"extracted_chars={r['extracted_chars']} body={r['parser_body_chars']} section_source={r['parser_section_source']} "
          f"descriptor={signal_descriptor(r)} head200={r['text_head_200']}")

    w("")
    w("== 10. confirmed_bad 区间当前 corpus chunk 的 section ==")
    w("  section_source: current_page = 本页 _extract_page_metadata 返回非 None；inherited = 本页为 None 沿用上一页；")
    w("  unresolved = 本页为 None 且此前无 section（→ UNKNOWN）。")
    w("  visible_garbling_evidence: section 含 C0/C1 控制字符或 U+00FF（机械判据；无证据 ≠ 正确）。")
    doc_sections: dict[str, set[str]] = defaultdict(set)
    for r in unrev:
        if int(r["corpus_chunk_count"]) > 0:  # type: ignore[arg-type]
            doc_sections[str(r["doc_id"])].add(json.loads(str(r["parser_effective_section"])))
    prev_effective: dict[str, str] = {}
    n_chunks = 0
    for r in rows:
        doc = str(r["doc_id"])
        eff = json.loads(str(r["parser_effective_section"]))
        if r["label"] == LABEL_CONFIRMED_BAD and int(r["corpus_chunk_count"]) > 0:  # type: ignore[arg-type]
            garbled = any(ord(ch) < 0x20 or 0x7F <= ord(ch) <= 0x9F or ord(ch) == 0xFF for ch in eff)
            for cid in str(r["corpus_chunk_ids"]).split():
                n_chunks += 1
                w(f"  {cid:<14} pdf_page={r['pdf_page']:<4} section={esc(eff):<44} source={r['parser_section_source']:<12} "
                  f"visible_garbling_evidence={int(garbled)} same_as_prev_chunked_page={int(prev_effective.get(doc) == eff)} "
                  f"collides_with_unreviewed_section_in_doc={int(eff in doc_sections[doc])}")
        if int(r["corpus_chunk_count"]) > 0:  # type: ignore[arg-type]
            prev_effective[doc] = eff
    w(f"  合计 chunk: {n_chunks}")
    w("  section_source 分布（全语料 有 chunk 的页）: " + json.dumps(dict(sorted(Counter(r['parser_section_source'] for r in rows if int(r['corpus_chunk_count']) > 0).items()))))  # type: ignore[arg-type]
    w("  section_source 分布（全语料 全部页）: " + json.dumps(dict(sorted(Counter(r['parser_section_source'] for r in rows).items()))))

    os.makedirs(os.path.dirname(os.path.abspath(args.out_log)), exist_ok=True)
    with open(args.out_log, "w", encoding="utf-8") as handle:
        handle.write("\n".join(out) + "\n")


# ==============================================================================
# 入口
# ==============================================================================

def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pdf-dir", required=True)
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--confirmed-bad", action="append", default=[], help="DOC_ID:LO-HI，可重复")
    ap.add_argument("--out-csv", required=True)
    ap.add_argument("--out-log", required=True)
    args = ap.parse_args(argv)

    confirmed_bad = parse_confirmed_bad(args.confirmed_bad)
    t_total = time.perf_counter()
    rows, files, timing = collect(args.pdf_dir, args.corpus, confirmed_bad)
    write_csv(rows, args.out_csv)
    total_s = time.perf_counter() - t_total

    env = {
        "python": platform.python_version(),
        "pdffonts": tool_version("pdffonts"),
        "pdftotext": tool_version("pdftotext"),
        "git_commit": run_cmd(["git", "rev-parse", "HEAD"]).strip(),
        "corpus_sha256": file_sha256(args.corpus),
    }
    write_log(args, env, files, rows, timing, total_s)

    failures = [r for r in rows if r["collect_status"] != "ok"]
    print(f"pages={len(rows)} failures={len(failures)} total_s={total_s:.2f}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
