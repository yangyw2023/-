"""独立的 citation metadata gate（Design Freeze §2.3 / §19）。

它回答且只回答：`(doc_id, section, pdf_page)` 是否能可靠支撑 Citation First。
它【不回答】正文是否正确、是否完整。

production enum 冻结为：
    explicit_supported / uncertain / failed
`verified_structural` 是 rejected terminology，不得作为 production state。

`explicit_supported` 只表示 **evidence-supported explicit metadata extraction**，
不表示 semantic verification：
  - 不表示人工核验过语义位置；
  - 不表示与目录 / 章节 ground truth 一致；
  - 不表示"属于已知章节集合所以正确"（TACM p.100 的 `"9"` 是反例形状）；
  - 不表示 body usable 因此 metadata correct。

本模块是 channel-aware 的：native 与 OCR 的页眉形态不同
（native 来自 `pdftotext -layout` 的列对齐；OCR 文本没有该列对齐），
因此各自有独立的 candidate 抽取器，但**共用同一个 gate**，
且【不预设任何来源优先】。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from components.parsers.page_states import GARBLING_CODEPOINT, is_control_char

# ==============================================================================
# 状态与 source kind
# ==============================================================================

EXPLICIT_SUPPORTED: str = "explicit_supported"
UNCERTAIN: str = "uncertain"
FAILED: str = "failed"
CITATION_STATES: tuple[str, ...] = (EXPLICIT_SUPPORTED, UNCERTAIN, FAILED)

KIND_EXPLICIT_LABEL: str = "explicit_label"
KIND_TITLE_LINE_FALLBACK: str = "title_line_fallback"
KIND_INHERITED: str = "inherited"
KIND_NONE: str = "none"
SOURCE_KINDS: tuple[str, ...] = (KIND_EXPLICIT_LABEL, KIND_TITLE_LINE_FALLBACK, KIND_INHERITED, KIND_NONE)

CHANNEL_NATIVE: str = "native"
CHANNEL_OCR: str = "ocr"
CHANNEL_NONE: str = "none"

# section 值的结构性上限：`Citation.display()` 把 section 内联进单行出处
# （`SMM §2.1 p.1 of 7 [PDF p.12]`）。比一行还长的字符串在构造上就不是 section 标识符。
# ⚠️ 超长【不等于】机械损坏：Design Freeze 的 `failed` 要求"值明确损坏"，
#    而一条过长的表头行属于"只有弱结构证据"，按冻结语义归入 `uncertain`。
#    因此本常量只用于 weak-evidence 判定，不用于 failed 判定。
SECTION_MAX_CHARS: int = 80

# OCR 通道的页眉标签抽取：OCR 文本没有 `-layout` 的多空格列对齐，
# 因此按「标签词 + 分隔 + 取值」的结构匹配，而不是按空格数量。
_OCR_SECTION_LABEL_RE = re.compile(r"(?im)^\s*SECTION\b[\s:|.]*(?P<value>.+?)\s*$")
_OCR_DOC_ID_LABEL_RE = re.compile(r"(?im)^\s*DOCUMENT\s*ID\b[\s:|.]*(?P<value>\S+)")


@dataclass(frozen=True)
class MetadataCandidate:
    """一个 channel 抽到的 section candidate 及其 provenance。

    `value is None` 表示该 channel 没有形成 candidate（不是错误）。
    """

    value: str | None
    source_kind: str
    channel: str
    raw_line: str | None

    def has_value(self) -> bool:
        return bool(self.value and self.value.strip())


def none_candidate(channel: str) -> MetadataCandidate:
    return MetadataCandidate(value=None, source_kind=KIND_NONE, channel=channel, raw_line=None)


# ==============================================================================
# 机械损坏判据（Design Freeze §2.3 条件 4）
# ==============================================================================

def mechanical_damage_reason(value: str) -> str | None:
    """返回损坏原因；None 表示未命中任何机械损坏判据。

    只做机械检查，不做语义判断。"看起来奇怪"不在此列。
    """
    if not value.strip():
        return "empty_value"
    if any(is_control_char(ch) for ch in value):
        return "control_char_in_value"
    if any(ord(ch) == GARBLING_CODEPOINT for ch in value):
        return "garbling_codepoint_u00ff"
    if not any(ch.isalnum() for ch in value):
        return "no_alphanumeric_char"
    if any(unicodedata.category(ch) in ("Co", "Cs", "Cn") for ch in value):
        return "private_use_or_unassigned_codepoint"
    return None


# ==============================================================================
# OCR 通道的 candidate 抽取
# ==============================================================================

def weak_evidence_reason(value: str) -> str | None:
    """返回"只有弱结构证据"的原因；None 表示无此问题。

    与 `mechanical_damage_reason` 严格分开：损坏 → failed，弱证据 → uncertain。
    """
    if len(value) > SECTION_MAX_CHARS:
        return f"value_longer_than_{SECTION_MAX_CHARS}"
    return None


def extract_ocr_candidate(ocr_text: str, header_scan_lines: int) -> MetadataCandidate:
    """从 OCR 文本的页眉扫描窗口抽 section candidate。

    只认显式 `SECTION` 标签；**不实现 title-line fallback** ——
    OCR 通道的 fallback 只会制造无法机械验证的 candidate，
    而 Design Freeze 要求 OCR 路径页必须达到 explicit_supported 才能入库。
    抽不到即返回 none candidate（这是"确实没有"，不是失败）。
    """
    head = "\n".join(ocr_text.splitlines()[:header_scan_lines])
    match = _OCR_SECTION_LABEL_RE.search(head)
    if match is None:
        return none_candidate(CHANNEL_OCR)
    raw_line = match.group(0).strip()
    value = match.group("value").strip()
    # 同一行里若紧跟另一个标签（OCR 常把整张页眉表压成一行），截断到下一个标签之前。
    value = re.split(r"\b(?:REV\.?\s*NO|REVISION|ISSUE\s+DATE|PAGE\s+NO|DOCUMENT\s*ID|ISSUED\s+BY)\b",
                     value, maxsplit=1, flags=re.I)[0].strip()
    if not value:
        return MetadataCandidate(None, KIND_NONE, CHANNEL_OCR, raw_line)
    return MetadataCandidate(value, KIND_EXPLICIT_LABEL, CHANNEL_OCR, raw_line)


def extract_ocr_doc_id(ocr_text: str, header_scan_lines: int) -> str | None:
    """OCR 页眉里的 DOCUMENT ID（只用于交叉校验，不参与 gate 判定）。"""
    head = "\n".join(ocr_text.splitlines()[:header_scan_lines])
    match = _OCR_DOC_ID_LABEL_RE.search(head)
    return match.group("value").strip() if match else None


# ==============================================================================
# Gate
# ==============================================================================

@dataclass(frozen=True)
class CitationGateResult:
    status: str
    reason_code: str
    metadata_conflict: bool
    resolved_value: str | None
    metadata_source_channel: str


def evaluate(native: MetadataCandidate, ocr: MetadataCandidate, page_identity_ok: bool) -> CitationGateResult:
    """对两个 channel 的 candidate 执行独立 gate。

    规则（Design Freeze §2.3 / §2.3.1，不得预设来源优先）：
      - page identity 硬门未过 → failed
      - 两个 candidate 都有值且不相等 → uncertain + metadata_conflict（禁止自动择一 /
        known-vocabulary / 邻页覆盖 / 继承 / majority vote）
      - 无任何 candidate → failed（必需 metadata 完全无法形成）
      - 取到唯一 candidate（或两者相等）后按五条判 explicit_supported，
        否则 uncertain / failed
    """
    if not page_identity_ok:
        return CitationGateResult(FAILED, "page_identity_mismatch", False, None, CHANNEL_NONE)

    # 第一步：机械损坏判据先淘汰不可接受的 candidate。
    # Design Freeze §2.3 的 failed 判据是"值明确损坏【且不存在可接受 candidate】"——
    # 因此损坏值不能作为一张否决票去和另一个 channel 的干净值"冲突"。
    # 这是淘汰的【判定结果】，不是"预设 OCR 优先"。
    present = [c for c in (native, ocr) if c.has_value()]
    if not present:
        return CitationGateResult(FAILED, "no_metadata_candidate", False, None, CHANNEL_NONE)
    damaged = {c.channel: mechanical_damage_reason(str(c.value)) for c in present}
    acceptable = [c for c in present if damaged[c.channel] is None]
    if not acceptable:
        reasons = ",".join(f"{c.channel}:{damaged[c.channel]}" for c in present)
        return CitationGateResult(FAILED, f"mechanical_damage:{reasons}", False, None, CHANNEL_NONE)

    # 第二步：在【可接受】的 candidate 之间判冲突（禁止自动择一 / vocabulary / 邻页 / 继承 / 投票）。
    if len(acceptable) == 2 and acceptable[0].value != acceptable[1].value:
        return CitationGateResult(UNCERTAIN, "metadata_candidate_conflict", True, None, CHANNEL_NONE)

    chosen = acceptable[0]
    agree = len(acceptable) == 2
    weak = weak_evidence_reason(str(chosen.value))
    if weak is not None:
        return CitationGateResult(UNCERTAIN, f"weak_structural_evidence:{weak}", False,
                                  str(chosen.value), chosen.channel)
    if chosen.source_kind != KIND_EXPLICIT_LABEL:
        return CitationGateResult(UNCERTAIN, f"source_kind={chosen.source_kind}", False,
                                  str(chosen.value), chosen.channel)
    if not chosen.raw_line:
        return CitationGateResult(UNCERTAIN, "incomplete_provenance:no_raw_line", False,
                                  str(chosen.value), chosen.channel)

    reason = "explicit_label+clean+provenance" + ("+candidates_agree" if agree else "")
    return CitationGateResult(EXPLICIT_SUPPORTED, reason, False, str(chosen.value), chosen.channel)
