"""KAIVA 手册 PDF 解析器 —— 按页切分，页眉元数据入字段，页眉页脚出正文。

只依赖 core.contracts 与 poppler 命令行（pdftotext / pdfinfo）。
刻意不引入任何 Python 第三方包：船端部署时每个依赖都是一个故障点。
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from typing import Iterator, Sequence

from core import contracts

# ==============================================================================
# 模块常量 —— 阈值一律从 contracts 引入，此处只放本解析器自己的结构参数
# ==============================================================================

# 页眉元数据的扫描窗口。KAIVA 页眉表格最深占 5 行（DOCUMENT ID / ISSUED BY /
# SECTION / 章节标题 / REV. NO.），留到 8 行是为了容纳标题折行与空行。
HEADER_SCAN_LINES: int = 8

# OCR 通道的页脚扫描窗口。native 通道靠 `-layout` 的 >=2 空格列间隔识别页眉表格行，
# OCR 文本没有列间隔（整张页眉表被压成单空格的一行），故 OCR 通道另按
# 【标签结构 + 行位置】剥离，见 `_ocr_structural_line_indices`。
OCR_FOOTER_SCAN_LINES: int = 3

# OCR 通道单标签行的长度判别式：一条页眉表格行显著短于一句正文散文。
# 取值依据：S5c post-QA residual census 在 1197 页 native-admitted 正文上的对照
# （正文里含 "Section" 的句子长度远超此值，且不落在 header/footer 区）。
OCR_LABEL_LINE_MAX_CHARS: int = 60

# pdftotext 必须带 -layout：默认模式下项目符号会与其正文分离（所有 • 挤成一堆，
# 内容跟在后面），语义被破坏。
PDFTOTEXT_ARGS: tuple[str, ...] = ("pdftotext", "-layout")

# poppler 子进程超时（float 秒，约定第 6 条）。整份文档一次调用，故给到分钟级。
PDFTOTEXT_TIMEOUT_S: float = 120.0
PDFINFO_TIMEOUT_S: float = 30.0

# pdftotext 在每页末尾输出的分页符。实测 9 份手册的分页符数与 pdfinfo 的
# Pages 完全一致，故按它切页是精确的（而非启发式）。
PAGE_SEPARATOR: str = "\f"

# 分块目标字符数。由 contracts 的 token 阈值换算，此处不另立阈值。
CHUNK_TARGET_CHARS: int = contracts.CHUNK_TARGET_TOKENS * contracts.CHARS_PER_TOKEN_EST

# section 抽不到且无上一页可继承时的占位值。
UNKNOWN_SECTION: str = "UNKNOWN"

# 文件名 → doc_id 兜底映射（页眉抽不到 DOCUMENT ID 时用）。
# 键是 raw/KAIVA - Manuals/ 下的真实文件名。
FILENAME_DOC_ID_MAP: dict[str, str] = {
    "0. CRM_Consolidated 2025.pdf": "CRM",
    "Crew Management Manual Ver 2.1_Consolidated Feb2024 (1).pdf": "CMM",
    "Emergency Response Manual_Consolidated May 2025.pdf": "ERM",
    "EMM Revision 3.0 - Consolidated Version.pdf": "EMM",
    "Fleet Maintenance Manual Consolidated May 2025.pdf": "FMM",
    "Navigational Procedures Manual_Consolidated Sep2024.pdf": "NPM",
    "Quality Management Manual_Consolidated May 2025.pdf": "QMM",
    "Safety Management Manual_Consolidated May 2025.pdf": "SMM",
    "Training and Competency Assurance Manual_01.12.2024.pdf": "TACM",
}

# 已知 doc_id 词表。用于识别页眉里那个孤立漂浮的手册代号（EMM 页眉右上角），
# 它既不是标签也不是正文，必须与章节标题区分开。
KNOWN_DOC_IDS: frozenset[str] = frozenset(FILENAME_DOC_ID_MAP.values())

# 页眉标签 → 字段名。值与标签同行，中间由 2 个以上空格分隔（-layout 的列对齐）。
# ⚠️ REVISION NO. 必须排在 REV. NO. 之前，否则前者会被后者的前缀吃掉。
_LABEL_ALTERNATION: tuple[tuple[str, str], ...] = (
    ("doc_id", r"DOCUMENT\s+ID"),
    ("issued_by", r"ISSUED\s+BY"),
    ("section", r"SECTION"),
    ("revision", r"REVISION\s+NO\.?"),
    ("revision2", r"REV\.?\s*NO\.?"),
    ("printed_page", r"PAGE\s+NO\.?"),
    ("issue_date", r"ISSUE\s+DATE"),
)
# 同一字段的多个拼写变体归一到同一个键。
_LABEL_KEY_ALIASES: dict[str, str] = {"revision2": "revision"}

_LABEL_RE = re.compile(
    "|".join(f"(?P<{key}>(?<![A-Za-z]){pat}(?![A-Za-z]))" for key, pat in _LABEL_ALTERNATION),
    re.IGNORECASE,
)
# 标签与其取值之间至少 2 个空格；不足 2 个空格说明这不是表格列（如正文里的 "Section /"）。
_LABEL_VALUE_GAP_RE = re.compile(r"\s{2,}")

# 页脚噪声。印刷页码按【章节】独立编号，"Page 1" 在一份手册里会重复出现，
# 故只存进 printed_page 展示给船员核对，绝不用于定位（引用契约）。
_PRINTED_PAGE_RE = re.compile(r"\bPage\s+(?:No\.?\s*)?(\d+\s+of\s+\d+)\b", re.IGNORECASE)
_NOISE_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"UNCONTROLLED\s+WHEN\s+PRINTED", re.IGNORECASE),
    re.compile(r"\bPage\s+(?:No\.?\s*)?\d+\s+of\s+\d+\b", re.IGNORECASE),
)

# 章节标题行的两种形态：
#   "2.1 - Hazard Identification..." / "9- Cadet Training"   （8 份手册）
#   "Chapter 2 – Legal, Environmental Requirements..."       （第 9 份）
_DASHES = r"\-‐‑‒–—―"
_CHAPTER_RE = re.compile(rf"^\s*Chapter\s+([0-9A-Za-z][0-9A-Za-z.]*)\s*[{_DASHES}]\s*(.+)$", re.IGNORECASE)
_NUMBERED_TITLE_RE = re.compile(rf"^\s*([0-9A-Za-z][0-9A-Za-z. ]*?)\s*[{_DASHES}]\s*(.+)$")

# 段落切分：一个或多个空行。
_PARA_SPLIT_RE = re.compile(r"\n\s*\n")


class KaivaPdfParser:
    """把一份 KAIVA 手册 PDF 解析成 Chunk 序列，实现 contracts.Parser 协议。

    切分粒度是【页】。页是最小语义单元：KAIVA 手册的页边界与章节边界高度对齐，
    跨页合并会让一个 chunk 同时携带两个 section，破坏引用契约
    （Citation 要求 (doc_id, section, pdf_page) 足以唯一定位）。
    一页过长时【只在页内】继续切分，切出的多个 chunk 共享该页的全部元数据。

    输入假设:
      - path 指向一份有文本层的 PDF。本解析器不做 OCR，也不检测文本层是否可读：
        若某页嵌入的是无 ToUnicode 映射的字体（如 Type 3 / Custom 编码），
        pdftotext 会产出不可读字符，本解析器会照原样产出 chunk，【不会报错】。
        文本层质量属于语料勘察的职责，不在解析器内判定。
      - 环境中有 poppler 的 pdftotext 与 pdfinfo。

    抛出:
      - contracts.ParseError —— 文件不存在 / 不可读；pdfinfo 或 pdftotext 缺失、
        返回非零、或超时；pdfinfo 页数与 pdftotext 分页符数不一致（静默截断）；
        整份文档解析后无任何有效内容。
        绝不返回空列表：空列表的唯一含义是"确实没检索到"，不能用来表示"崩了"。

    返回值语义:
      - 按 pdf_page 升序、页内序号升序排列的 Chunk 序列。
      - pdf_page 从 1 开始（约定第 4 条）。
      - 每个 chunk 的 text 已剥离页眉页脚，长度 ≥ contracts.CHUNK_MIN_CHARS。
      - section 恒为非空 str；确实无从得知时为 UNKNOWN_SECTION，不是 None。
      - Chunk.id 是确定性的：同一输入两次解析产生完全相同的 id
        （由 doc_id / pdf_page / 页内序号 构成，不含随机数、时间戳或内存地址）。
    """

    name: str = "kaiva_pdf_v1"

    def parse(self, path: str) -> Sequence[contracts.Chunk]:
        """解析一份文档为 Chunk 序列。契约见类 docstring。"""
        if not os.path.isfile(path):
            raise contracts.ParseError(f"文件不存在或不是普通文件: {path}")

        filename = os.path.basename(path)
        fallback_doc_id = FILENAME_DOC_ID_MAP.get(filename, _doc_id_from_filename(filename))
        expected_pages = _pdfinfo_page_count(path)
        pages = _pdftotext_pages(path)

        if len(pages) != expected_pages:
            raise contracts.ParseError(
                f"页数不一致，疑似抽取被截断: pdfinfo={expected_pages} "
                f"pdftotext 分页={len(pages)}: {path}"
            )

        source_hash = _file_sha256(path)
        chunks: list[contracts.Chunk] = []
        # 章节跨页继承：一个章节本来就横跨多页，沿用上一页比标 UNKNOWN 更符合事实。
        # 这是逐文档的状态，与具体是哪份手册无关。
        last_section: str | None = None
        last_section_title: str | None = None

        for page_no, page_text in enumerate(pages, start=1):
            meta = _extract_page_metadata(page_text)

            section = meta["section"]
            section_title = meta["section_title"]
            if section is None:
                section = last_section
                # section 是继承来的，标题也应一并继承，否则两者会对不上。
                section_title = last_section_title
            if section is not None:
                last_section = section
                last_section_title = section_title

            body = _strip_noise(page_text, meta)
            if len(body) < contracts.CHUNK_MIN_CHARS:
                continue

            doc_id = meta["doc_id"] or fallback_doc_id
            for ordinal, text in enumerate(_split_page_body(body)):
                chunks.append(
                    contracts.Chunk(
                        id=f"{doc_id}:p{page_no}:{ordinal}",
                        text=text,
                        doc_id=doc_id,
                        doc_name=filename,
                        section=section or UNKNOWN_SECTION,
                        section_title=section_title,
                        pdf_page=page_no,
                        printed_page=meta["printed_page"],
                        issued_by=meta["issued_by"],
                        revision=meta["revision"],
                        source_hash=source_hash,
                    )
                )

        if not chunks:
            raise contracts.ParseError(f"整份文档解析后无有效内容: {path}")
        return chunks


# ==============================================================================
# poppler 调用
# ==============================================================================

def _run_poppler(argv: Sequence[str], timeout_s: float, path: str) -> str:
    """跑一个 poppler 命令并返回 stdout。

    抛出: contracts.ParseError —— 命令不存在、返回非零、或超时。
    ⚠️ 不看 stderr：部分手册会在 stderr 打印 "Syntax Error: ..." 但仍能正确抽取，
      把 stderr 当失败会误杀整份文档。判据只有返回码。
    """
    try:
        proc = subprocess.run(argv, capture_output=True, timeout=timeout_s)
    except FileNotFoundError as exc:
        raise contracts.ParseError(f"poppler 命令不可用: {argv[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise contracts.ParseError(f"{argv[0]} 超时（>{timeout_s}s）: {path}") from exc
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", errors="replace").strip()
        raise contracts.ParseError(f"{argv[0]} 返回 {proc.returncode}: {path}: {detail}")
    return proc.stdout.decode("utf-8", errors="replace")


def _pdfinfo_page_count(path: str) -> int:
    """读取 PDF 页数。抛出 contracts.ParseError（含 pdfinfo 输出里没有 Pages 行）。"""
    out = _run_poppler(["pdfinfo", path], PDFINFO_TIMEOUT_S, path)
    for line in out.splitlines():
        if line.startswith("Pages:"):
            try:
                return int(line.split(":", 1)[1].strip())
            except ValueError as exc:
                raise contracts.ParseError(f"pdfinfo 的 Pages 行无法解析: {line!r}") from exc
    raise contracts.ParseError(f"pdfinfo 输出中没有 Pages 行: {path}")


def _pdftotext_pages(path: str) -> list[str]:
    """整份抽取后按分页符切页，返回逐页文本（不含末尾那个空段）。

    整份一次调用而非逐页调用：实测分页符数与 pdfinfo 页数在 9 份手册上完全一致，
    结果相同而进程数从 1335 降到 9。
    """
    raw = _run_poppler([*PDFTOTEXT_ARGS, path, "-"], PDFTOTEXT_TIMEOUT_S, path)
    pages = raw.split(PAGE_SEPARATOR)
    # pdftotext 在【每页】末尾都放分页符，故 split 后末尾必有一个空段，去掉它。
    if pages and not pages[-1].strip():
        pages.pop()
    return pages


def _file_sha256(path: str) -> str:
    """源文件 sha256 十六进制串，填入 Chunk.source_hash 供后续增量更新使用。"""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _doc_id_from_filename(filename: str) -> str:
    """映射表未覆盖的文件名的兜底 doc_id：取主干的首个词，大写。

    仅用于新增手册尚未登记进 FILENAME_DOC_ID_MAP 的情况，保证 doc_id 非空。
    """
    stem = os.path.splitext(filename)[0].strip()
    head = re.split(r"[\s_]+", stem)[0] or stem
    return head.upper()


# ==============================================================================
# 页眉解析
# ==============================================================================

def _iter_label_spans(line: str) -> list[tuple[str, int, int]]:
    """返回该行上所有 (字段名, 标签起点, 标签终点)，按位置升序。

    只认后面跟着 2 个以上空格再跟非空内容的标签 —— -layout 模式下表格列之间
    必然是多空格。这样 "Section /" 这类正文措辞不会被误当成标签。
    """
    spans: list[tuple[str, int, int]] = []
    for match in _LABEL_RE.finditer(line):
        key = match.lastgroup
        if key is None:
            continue
        gap = _LABEL_VALUE_GAP_RE.match(line, match.end())
        if gap is None or not line[gap.end():].strip():
            continue
        spans.append((_LABEL_KEY_ALIASES.get(key, key), match.start(), match.end()))
    return spans


def _extract_page_metadata(page_text: str) -> dict[str, str | None]:
    """从一页文本里抽出页眉元数据与印刷页码。

    输入假设: page_text 是【单页】的 -layout 文本。
    返回: 键为 doc_id / issued_by / section / revision / section_title /
          printed_page 的字典，抽不到的键为 None。
          同时带一个私有键 _noise_lines：页眉里应当从正文剥掉的行号集合。
    本函数不做跨页继承 —— 继承是文档级的状态，由 parse 负责。
    """
    lines = page_text.splitlines()
    header = lines[:HEADER_SCAN_LINES]

    fields: dict[str, str] = {}
    noise_lines: set[int] = set()
    # 每行剥掉标签与取值之后剩下的左栏文字（章节标题就在这里，可能折行）。
    # 带上行号：标题折行必然【相邻】，中间隔了空行就说明已经进入正文。
    leftovers: list[tuple[int, str]] = []

    for index, line in enumerate(header):
        spans = _iter_label_spans(line)
        if spans:
            noise_lines.add(index)
        cursor = 0
        pieces: list[str] = []
        for position, (key, start, end) in enumerate(spans):
            pieces.append(line[cursor:start])
            stop = spans[position + 1][1] if position + 1 < len(spans) else len(line)
            value = line[end:stop].strip()
            # 首次出现者胜：页眉表格在最前面，靠后的同名词多半是正文或目录表头。
            if value and key not in fields:
                fields[key] = value
            cursor = stop
        pieces.append(line[cursor:])
        remainder = " ".join(piece.strip() for piece in pieces if piece.strip()).strip()
        if remainder and not _is_noise_line(remainder):
            leftovers.append((index, remainder))

    section = fields.get("section")
    section_title, title_lines = _extract_section_title(leftovers, section)

    if section is None:
        # 无 SECTION 标签时，页眉的居中标题行就是本页的章节标识。
        # "Chapter 2 – ..." 取编号 2；"2.1 - ..." 取 2.1；其余（如 "Record of
        # Revision"）整行即章节名 —— 这与带标签手册里 SECTION 取值同为自由文本
        # （实测有 "PART I" / "GP 1.3" / "CMM II Record of Revision"）是一致的。
        section = _section_from_title_line(leftovers)

    noise_lines |= title_lines

    printed_page = fields.get("printed_page")
    if printed_page is not None:
        match = _PRINTED_PAGE_RE.search(printed_page)
        printed_page = match.group(1) if match else printed_page
    if printed_page is None:
        match = _PRINTED_PAGE_RE.search(page_text)
        printed_page = match.group(1) if match else None

    return {
        "doc_id": _clean_doc_id(fields.get("doc_id")),
        "issued_by": fields.get("issued_by"),
        "section": section,
        "revision": fields.get("revision"),
        "section_title": section_title,
        "printed_page": printed_page,
        "_noise_lines": noise_lines,  # type: ignore[dict-item]
    }


def _clean_doc_id(value: str | None) -> str | None:
    """页眉 DOCUMENT ID 取值归一：取首个词。抽不到返回 None，由调用方兜底到文件名。"""
    if not value:
        return None
    head = value.split()[0].strip()
    return head or None


def _is_doc_id_token(text: str) -> bool:
    """该行是否只是页眉里那个孤立漂浮的手册代号（如 EMM 右上角的 "EMM"）。"""
    return text.strip().upper() in KNOWN_DOC_IDS


def _is_noise_line(text: str) -> bool:
    """该行是否是页眉页脚噪声（UNCONTROLLED WHEN PRINTED / Page N of M）。"""
    return any(pattern.search(text) for pattern in _NOISE_RES)


def _extract_section_title(
    leftovers: Sequence[tuple[int, str]], section: str | None
) -> tuple[str | None, set[int]]:
    """从页眉左栏文字里拼出章节标题。

    输入: (行号, 该行左栏文字) 序列，行号是页内 0-based 行号。
    返回: (标题或 None, 构成标题的行号集合)。后者用于把这些行从正文里剥掉。

    标题可能折行（实测 CRM "GP 1.3 - Fleet Business Continuity and" /
    "Disaster Recovery (BCDR) Plan"），故命中后继续拼接后续左栏行。
    ⚠️ 只拼【行号相邻】的行：折行的下一半必然紧挨着，中间隔了空行就说明已经
      进入正文。少了这道闸，正文的第一个小标题会被吸进标题、并被当噪声剥掉。
    """
    start = None
    for position, (_, text) in enumerate(leftovers):
        if _CHAPTER_RE.match(text):
            start = position
            break
        if section is not None and _title_matches_section(text, section):
            start = position
            break
    if start is None:
        return None, set()

    line_no, text = leftovers[start]
    parts = [text]
    lines = {line_no}
    previous = line_no
    for next_line_no, next_text in leftovers[start + 1:]:
        if next_line_no != previous + 1 or _is_doc_id_token(next_text):
            break
        parts.append(next_text)
        lines.add(next_line_no)
        previous = next_line_no
    return " ".join(parts).strip(), lines


def _title_matches_section(text: str, section: str) -> bool:
    """该左栏行是否是形如 "<section> - <标题>" 的章节标题行。"""
    match = _NUMBERED_TITLE_RE.match(text)
    if match is None:
        return False
    return match.group(1).strip().casefold() == section.strip().casefold()


def _section_from_title_line(leftovers: Sequence[tuple[int, str]]) -> str | None:
    """无 SECTION 标签时，从页眉标题行推出章节标识。抽不到返回 None（交由调用方继承）。"""
    for _, text in leftovers:
        if _is_doc_id_token(text):
            continue
        chapter = _CHAPTER_RE.match(text)
        if chapter:
            return chapter.group(1).strip()
        numbered = _NUMBERED_TITLE_RE.match(text)
        if numbered:
            return numbered.group(1).strip()
        return text.strip()
    return None


# ==============================================================================
# 正文提取与页内切分
# ==============================================================================

def _strip_noise(page_text: str, meta: dict[str, str | None]) -> str:
    """剥掉页眉表格行、章节标题行与页脚噪声行，只留正文。

    返回去掉首尾空行后的正文字符串（可能为空）。
    """
    noise_lines: set[int] = meta["_noise_lines"]  # type: ignore[assignment]
    kept: list[str] = []
    for index, line in enumerate(page_text.splitlines()):
        if index in noise_lines:
            continue
        if _is_noise_line(line):
            continue
        if index < HEADER_SCAN_LINES and _is_doc_id_token(line):
            continue
        kept.append(line.rstrip())
    return "\n".join(kept).strip("\n").strip()


def _est_tokens(text: str) -> int:
    """本模块的 token 估算，口径与 contracts.Chunk.est_tokens 一致。

    刻意不引入 tokenizer 依赖：该估算只用于分块决策，误差不改变切分结果的可用性。
    """
    return max(1, len(text) // contracts.CHARS_PER_TOKEN_EST)


def _split_page_body(body: str) -> list[str]:
    """把一页正文切成若干块，每块 token 估算不超过 CHUNK_TARGET_TOKENS。

    输入假设: body 已剥离页眉页脚，长度 ≥ contracts.CHUNK_MIN_CHARS。
    策略:
      1. 按空行切段，贪心聚合到接近目标长度；
      2. 若单个"段落"本身就超长（表格页在 -layout 下整页不含空行，会被当成一个
         超长段落），退回【按行】切分 —— 表格的一行是一条记录，不能拦腰截断，
         故长度超标的单行宁可独立成块也不切开；
      3. 末块若短于 contracts.CHUNK_MIN_CHARS，并回前一块，避免丢正文。
    返回: 至少含一个元素的列表，顺序即页内阅读顺序。
    """
    paragraphs = [p for p in _PARA_SPLIT_RE.split(body) if p.strip()]
    chunks: list[str] = []
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            chunks.append("\n\n".join(buffer).strip())
            buffer.clear()

    for paragraph in paragraphs:
        if _est_tokens(paragraph) > contracts.CHUNK_TARGET_TOKENS:
            flush()
            chunks.extend(_split_by_lines(paragraph))
            continue
        candidate = "\n\n".join([*buffer, paragraph])
        if buffer and _est_tokens(candidate) > contracts.CHUNK_TARGET_TOKENS:
            flush()
        buffer.append(paragraph)
    flush()

    return _merge_undersized(chunks)


def _split_by_lines(paragraph: str) -> Iterator[str]:
    """超长段落的兜底切分：按行聚合，不切开任何一行。

    表格页在 -layout 下整页无空行，一行就是一条记录；从行中间截断会把一条记录
    劈成两半，两边都不可读。故单行长度超标时让它独立成块，宁可超过目标长度。
    """
    buffer: list[str] = []
    for line in paragraph.splitlines():
        candidate = "\n".join([*buffer, line])
        if buffer and _est_tokens(candidate) > contracts.CHUNK_TARGET_TOKENS:
            yield "\n".join(buffer).strip()
            buffer = []
        buffer.append(line)
    if buffer:
        tail = "\n".join(buffer).strip()
        if tail:
            yield tail


def _merge_undersized(chunks: list[str]) -> list[str]:
    """把短于 contracts.CHUNK_MIN_CHARS 的块并进相邻块，避免产出碎片。

    为什么需要: 页内切分会在遇到超长段落前先把缓冲区 flush 掉，若此时缓冲区里
    只有一个短小标题（实测见过 3 字符的块），它就会独立成块。这类碎片既检索不出
    东西，又会污染 chunk 数与长度分布。

    合并方向: 短块向【后】并入下一块；末块没有下一块，则向前并入上一块。
    合并后长度上限为 CHUNK_TARGET_CHARS + CHUNK_MIN_CHARS，仍远低于单块 2000 字符。
    只剩一块且它本身过短时原样返回，由调用方按 CHUNK_MIN_CHARS 决定去留。
    """
    merged: list[str] = []
    for text in chunks:
        if merged and len(merged[-1]) < contracts.CHUNK_MIN_CHARS:
            merged[-1] = f"{merged[-1]}\n\n{text}".strip()
        else:
            merged.append(text)
    if len(merged) > 1 and len(merged[-1]) < contracts.CHUNK_MIN_CHARS:
        tail = merged.pop()
        merged[-1] = f"{merged[-1]}\n\n{tail}".strip()
    return [c for c in merged if c.strip()]


# ==============================================================================
# Phase B：native 通道的页面视图（不改变既有 parse() 的 baseline 行为）
# ==============================================================================

def iter_native_pages(path: str) -> tuple[list[str], int]:
    """整份文档的 native 逐页文本 + pdfinfo 页数。

    抛出 contracts.ParseError —— 文件缺失、poppler 失败、页数与分页符数不一致。
    返回 (pages, expected_pages)；两者长度必须相等（调用方可据此做 page identity 硬门）。
    """
    if not os.path.isfile(path):
        raise contracts.ParseError(f"文件不存在或不是普通文件: {path}")
    expected = _pdfinfo_page_count(path)
    pages = _pdftotext_pages(path)
    if len(pages) != expected:
        raise contracts.ParseError(
            f"页数不一致，疑似抽取被截断: pdfinfo={expected} pdftotext 分页={len(pages)}: {path}"
        )
    return pages, expected


def _section_label_raw_line(page_text: str) -> str | None:
    """页眉扫描窗口内第一条带 SECTION 标签【且标签后有取值】的原始行。"""
    for line in page_text.splitlines()[:HEADER_SCAN_LINES]:
        for key, start, end in _iter_label_spans(line):
            if key == "section":
                return line.strip()
    return None


def native_metadata_candidate(page_text: str, meta: dict[str, str | None]) -> tuple[str | None, str, str | None]:
    """native 通道的 section candidate 及其 provenance。

    返回 (value, source_kind, raw_line)：
      - source_kind = "explicit_label"        页眉表格里的 SECTION 标签取值
      - source_kind = "title_line_fallback"   无 SECTION 标签时由页眉标题行推出（legacy 行为）
      - source_kind = "none"                  本页没有形成 candidate
    本函数【不判断对错】，只如实报告 candidate 与来源；判定在 citation_gate。
    """
    value = meta["section"]
    if value is None:
        return None, "none", None
    raw = _section_label_raw_line(page_text)
    if raw is not None:
        return value, "explicit_label", raw
    for line in page_text.splitlines()[:HEADER_SCAN_LINES]:
        stripped = line.strip()
        if stripped and not _is_noise_line(stripped) and not _is_doc_id_token(stripped):
            return value, "title_line_fallback", stripped
    return value, "title_line_fallback", None


def native_page_view(page_text: str) -> dict[str, object]:
    """一页 native 文本的结构化视图：正文 + 页眉元数据 + candidate provenance。

    输入假设: page_text 是整份 `-layout` 抽取后按分页符切出的【单页】文本。
    返回键: body / meta / candidate_value / candidate_source_kind / candidate_raw_line。
    不做任何状态判定，也不做跨页继承 —— 继承与否由上层 policy 决定。
    """
    meta = _extract_page_metadata(page_text)
    body = _strip_noise(page_text, meta)
    value, kind, raw = native_metadata_candidate(page_text, meta)
    return {"body": body, "meta": meta, "candidate_value": value,
            "candidate_source_kind": kind, "candidate_raw_line": raw}


def _ocr_structural_line_indices(lines: Sequence[str]) -> set[int]:
    """OCR 文本中应当作为页眉/页脚剥掉的行号集合。

    输入假设: lines 是【单页】OCR 文本按行切分的结果。
    判据（纯结构，不依赖 doc_id / 文件名 / 页码）：
      - 行位于 header 区（前 `HEADER_SCAN_LINES` 行）或 footer 区
        （后 `OCR_FOOTER_SCAN_LINES` 行）；且
      - 该行含 >= 2 个不同页眉标签，或含 >= 1 个标签且长度 <= `OCR_LABEL_LINE_MAX_CHARS`。
    正文区（两区之外）内含 "SECTION" 字样的句子不在此列，不会被剥掉。
    本函数只返回行号，不修改文本，也不做任何语义判断。
    """
    total = len(lines)
    indices: set[int] = set()
    for index, line in enumerate(lines):
        if index >= HEADER_SCAN_LINES and index < total - OCR_FOOTER_SCAN_LINES:
            continue
        labels = {
            _LABEL_KEY_ALIASES.get(match.lastgroup, match.lastgroup)
            for match in _LABEL_RE.finditer(line)
            if match.lastgroup is not None
        }
        if not labels:
            continue
        if len(labels) >= 2 or len(line.strip()) <= OCR_LABEL_LINE_MAX_CHARS:
            indices.add(index)
    return indices


def ocr_page_view(ocr_text: str) -> dict[str, object]:
    """一页 OCR 文本的结构化视图：去页眉页脚后的正文。

    输入假设: ocr_text 是【单页】已接受 OCR artifact 的文本。
    返回键: body / meta。body 可能为空字符串（"整页都是页眉" 是合法结果）。
    去噪在 native 流程（`_extract_page_metadata` + `_strip_noise`）之上叠加
    `_ocr_structural_line_indices`：native 的列间隔判据在 OCR 文本上必然落空，
    不叠加会把整张页眉表留在 body 里。
    section candidate 由 citation_gate 的 channel-aware 抽取器从【原始】OCR
    文本抽取，不受本函数剥离的影响。
    """
    meta = _extract_page_metadata(ocr_text)
    existing: set[int] = meta["_noise_lines"]  # type: ignore[assignment]
    meta["_noise_lines"] = existing | _ocr_structural_line_indices(ocr_text.splitlines())  # type: ignore[assignment]
    return {"body": _strip_noise(ocr_text, meta), "meta": meta}


def split_body_to_texts(body: str) -> list[str]:
    """把已选定的 primary body 切成 chunk 文本列表（复用既有分块规则）。"""
    return _split_page_body(body)
