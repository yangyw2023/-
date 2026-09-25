"""Phase B 的五个页面状态轴（Design Freeze §2）。

本模块只做 signals → states，**不产生任何动作**（动作在 phase_b_ingest 的 policy 层）。
五个轴互不兼职：
  native_body_status               正文本身是否适合 retrieval
  page_content_completeness_status 页面业务内容是否已被当前 text representation 覆盖
  ocr_body_status                  OCR 新取得的文本是否可用
  citation_metadata_status         见 citation_gate.py（独立 gate）
  content_policy_status            已抽到的内容是否值得进 corpus

所有判据只复用既有冻结常量（contracts.CHUNK_MIN_CHARS）与 Phase A 已验证的
文本信号口径，**不引入任何新校准阈值**。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from core import contracts

# ==============================================================================
# 状态枚举（冻结）
# ==============================================================================

NATIVE_USABLE: str = "usable"
NATIVE_UNUSABLE: str = "unusable"
NATIVE_INSUFFICIENT: str = "insufficient"
NATIVE_UNCERTAIN: str = "uncertain"
NATIVE_BODY_STATES: tuple[str, ...] = (NATIVE_USABLE, NATIVE_UNUSABLE, NATIVE_INSUFFICIENT, NATIVE_UNCERTAIN)

COMPLETENESS_PRESUMED: str = "presumed_complete"
COMPLETENESS_SUSPECTED: str = "visual_content_suspected"
COMPLETENESS_NOT_ASSESSED: str = "not_assessed"
COMPLETENESS_STATES: tuple[str, ...] = (COMPLETENESS_PRESUMED, COMPLETENESS_SUSPECTED, COMPLETENESS_NOT_ASSESSED)

OCR_NOT_ATTEMPTED: str = "not_attempted"
OCR_USABLE: str = "usable"
OCR_DEGRADED: str = "degraded"
OCR_FAILED: str = "failed"
OCR_BODY_STATES: tuple[str, ...] = (OCR_NOT_ATTEMPTED, OCR_USABLE, OCR_DEGRADED, OCR_FAILED)

# ocr_body_status 的 reason code —— 状态是四态 enum，失败归因靠这组常量区分。
# "引擎失败" / "原文为空" / "剥离后无业务正文" 是三件不同的事，不得混用同一个名字。
OCR_REASON_NOT_ATTEMPTED: str = "no_accepted_artifact_consumed"
OCR_REASON_ENGINE_FAILED: str = "ocr_engine_failed_no_artifact"
OCR_REASON_TEXT_EMPTY_RAW: str = "ocr_text_empty_raw"
OCR_REASON_EMPTY_AFTER_STRIP: str = "ocr_body_empty_after_structural_strip"
OCR_FAILURE_REASONS: tuple[str, ...] = (
    OCR_REASON_ENGINE_FAILED, OCR_REASON_TEXT_EMPTY_RAW, OCR_REASON_EMPTY_AFTER_STRIP,
)

POLICY_ADMIT: str = "admit"
POLICY_HOLD: str = "hold_for_review"
POLICY_REJECT: str = "reject_noncontent"
CONTENT_POLICY_STATES: tuple[str, ...] = (POLICY_ADMIT, POLICY_HOLD, POLICY_REJECT)

# V1 的作用域（Design Freeze §3）：只在 Latin-script 语料上允许判 unusable。
# 作用域外一律 uncertain，绝不自动判 unusable。
LATIN_SCRIPT_LANGS: frozenset[str] = frozenset({"en"})

# 机械损坏判据用到的字符集合（Phase A 的既有口径）。
_ALPHA_TOKEN_RE = re.compile(r"^[A-Za-z]{2,}[.,;:)]?$")
_NON_CONTROL_C0: frozenset[str] = frozenset({"\n", "\r", "\t"})
GARBLING_CODEPOINT: int = 0xFF  # Phase A 实测：TACM Type-3 乱码页的主导非 ASCII 码位


def is_control_char(ch: str) -> bool:
    """C0（除 \\n\\r\\t）/ DEL / C1 视为控制字符；form feed 也计入（正文里不应出现）。"""
    code = ord(ch)
    return (code < 0x20 and ch not in _NON_CONTROL_C0) or code == 0x7F or 0x80 <= code <= 0x9F


@dataclass(frozen=True)
class TextSignals:
    """一段正文的确定性文本信号（Phase A 口径）。"""

    chars: int
    word_count: int
    alpha_token_ratio: float | None   # 无 token 时 None（无定义，不伪造 0）
    control_chars: int
    garbling_chars: int

    @classmethod
    def of(cls, text: str) -> "TextSignals":
        words = text.split()
        alpha = sum(1 for w in words if _ALPHA_TOKEN_RE.match(w))
        return cls(
            chars=len(text),
            word_count=len(words),
            alpha_token_ratio=(alpha / len(words)) if words else None,
            control_chars=sum(1 for ch in text if is_control_char(ch)),
            garbling_chars=sum(1 for ch in text if ord(ch) == GARBLING_CODEPOINT),
        )


def classify_native_body(body: str, doc_lang: str) -> tuple[str, str]:
    """native_body_status + reason code。

    判定顺序（Design Freeze §2.1，确定性、互斥）：
      insufficient → unusable → uncertain → usable
    `insufficient` 优先于 `unusable`：短 body 上的比值统计不稳定
    （Phase A 实测 TACM p.39–50 的 `"010213433"`）。

    返回 (status, reason_code)。
    """
    sig = TextSignals.of(body)
    if sig.chars < contracts.CHUNK_MIN_CHARS:
        return NATIVE_INSUFFICIENT, f"body_chars={sig.chars}<CHUNK_MIN_CHARS={contracts.CHUNK_MIN_CHARS}"
    in_scope = doc_lang in LATIN_SCRIPT_LANGS
    if not in_scope:
        return NATIVE_UNCERTAIN, f"v1_out_of_scope:lang={doc_lang}"
    if sig.word_count >= 1 and sig.alpha_token_ratio == 0.0:
        return NATIVE_UNUSABLE, f"v1:alpha_token_ratio=0 words={sig.word_count}"
    if sig.control_chars > 0:
        return NATIVE_UNCERTAIN, f"contradictory:control_chars={sig.control_chars} alpha_token_ratio={sig.alpha_token_ratio}"
    return NATIVE_USABLE, "body>=min;control=0;alpha_token_ratio>0"


def classify_ocr_body(ocr_body: str | None, artifact_present: bool,
                      raw_ocr_text: str | None = None,
                      ocr_attempted: bool = False) -> tuple[str, str]:
    """ocr_body_status + reason code（Design Freeze §2.4）。

    输入假设:
      - `ocr_body` 已经过去页眉页脚流程（OCR 通道还叠加了结构标签行剥离）；
      - `raw_ocr_text` 是【剥离之前】的 accepted artifact 原文；给 None 表示调用方
        不提供原文，此时无法区分"原文就空"与"剥离后才空"，统一按前者归因。
      - `ocr_attempted` 表示 policy 是否把本页选为 OCR 目标。

    状态 enum 冻结为四态，本函数不新增状态；三类失败只由 reason code 区分：
      A `OCR_REASON_ENGINE_FAILED`      —— 选为目标却没有 accepted artifact。
         production 路径上 build 层会先抛异常（fail-fast），此分支是状态层的完整性兜底。
      B `OCR_REASON_TEXT_EMPTY_RAW`     —— artifact 存在但原文为空 → OCR 本身没产出。
      C `OCR_REASON_EMPTY_AFTER_STRIP`  —— 原文非空，但剥掉页眉页脚后没有业务正文。
         **C 不是 OCR 失败**：引擎成功、原文可溯源，只是这一页除页眉外没有内容。
    判据只复用 CHUNK_MIN_CHARS 与 V1 语义，不引入引擎置信度阈值。
    """
    if not artifact_present:
        if ocr_attempted:
            return OCR_FAILED, OCR_REASON_ENGINE_FAILED
        return OCR_NOT_ATTEMPTED, OCR_REASON_NOT_ATTEMPTED
    if ocr_body is None or not ocr_body.strip():
        if raw_ocr_text is not None and raw_ocr_text.strip():
            return OCR_FAILED, OCR_REASON_EMPTY_AFTER_STRIP
        return OCR_FAILED, OCR_REASON_TEXT_EMPTY_RAW
    sig = TextSignals.of(ocr_body)
    if sig.chars < contracts.CHUNK_MIN_CHARS:
        return OCR_DEGRADED, f"ocr_body_chars={sig.chars}<CHUNK_MIN_CHARS"
    if sig.word_count >= 1 and sig.alpha_token_ratio == 0.0:
        return OCR_DEGRADED, "v1:alpha_token_ratio=0"
    return OCR_USABLE, "ocr_body>=min;alpha_token_ratio>0"


def classify_completeness(native_body_status: str, visual_suspected: bool | None) -> tuple[str, str]:
    """page_content_completeness_status（Design Freeze §2.2）。

    被评估 population = body 非 usable 的页；body usable 的页在 Phase B 内不评估（C3）。
    `visual_suspected` 为 None 表示视觉诊断输入不可用 → 评估未做。
    **该状态不参与任何动作**（视觉信号 diagnostic only）。
    """
    if native_body_status == NATIVE_USABLE:
        return COMPLETENESS_NOT_ASSESSED, "body_usable:class3_out_of_phase_b_scope"
    if visual_suspected is None:
        return COMPLETENESS_NOT_ASSESSED, "visual_diagnostic_unavailable"
    if visual_suspected:
        return COMPLETENESS_SUSPECTED, "active_row_diagnostic_above_frozen_tau"
    return COMPLETENESS_PRESUMED, "active_row_diagnostic_below_frozen_tau"


def classify_content_policy(selected_body: str, gates_uncertain: Sequence[str]) -> tuple[str, str]:
    """content_policy_status（Design Freeze §2.5）。

    只有两种确定性判据：既有的 CHUNK_MIN_CHARS 规则，以及"任一 gate 为 uncertain"。
    **不引入任何自动化的业务价值分类器**（A.2b 已证明 form/scaffold 价值密度不可由信号判定）。
    """
    if len(selected_body) < contracts.CHUNK_MIN_CHARS:
        return POLICY_REJECT, f"body_chars={len(selected_body)}<CHUNK_MIN_CHARS"
    if gates_uncertain:
        return POLICY_HOLD, "uncertain:" + ",".join(sorted(gates_uncertain))
    return POLICY_ADMIT, "gates_clear"
