"""Phase B 的页面级编排：states → policy → action → chunks + page record。

层次（Design Freeze §1）：
    signals（kaiva_pdf / ocr artifact）
      → states（page_states / citation_gate）
      → actions（本模块的 policy）

本模块的硬约束：
  - **绝不执行 OCR**：只消费调用方传入的 accepted artifact payload。
  - **primary body 单 channel**：`select_primary_body()` 返回唯一一个 channel 的正文，
    结构上不存在把两个 channel 拼接的路径。
  - **不预设 metadata 来源**：native 与 OCR 两个 candidate 都交给同一个独立 gate。
  - **视觉信号只进审计**：`visual_suspected` 只influence completeness 状态，不参与任何动作。

抛出:
  - PageIngestError —— 需要 OCR 的页面没有 accepted artifact、artifact 身份不符等
    必须 FAIL_INGEST 的情况。调用方不得降级处理。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from components.parsers import citation_gate as cg
from components.parsers import kaiva_pdf as native
from components.parsers import page_states as ps
from core import contracts

# 终态（page accounting 的闭合集合）
ACTION_ADMITTED_NATIVE: str = "ADMITTED_NATIVE"
ACTION_ADMITTED_OCR: str = "ADMITTED_OCR"
ACTION_QUARANTINED: str = "QUARANTINED"
ACTION_SKIPPED_NONCONTENT: str = "SKIPPED_NONCONTENT"
# REQUIRE_REVIEW 是【正交标志】，不是动作的一部分：
# 把它编码进动作字符串会让 "action in (ADMITTED_...)" 这类判断静默失效。
TERMINAL_ACTIONS: tuple[str, ...] = (
    ACTION_ADMITTED_NATIVE, ACTION_ADMITTED_OCR, ACTION_QUARANTINED, ACTION_SKIPPED_NONCONTENT,
)

BODY_CHANNEL_NATIVE: str = "native"
BODY_CHANNEL_OCR: str = "ocr"
BODY_CHANNEL_NONE: str = "none"

# 需要 OCR_ATTEMPT 的 native body 状态（Design Freeze §4 / §18：无条件，不由视觉信号门控）
OCR_ATTEMPT_STATES: frozenset[str] = frozenset({ps.NATIVE_UNUSABLE, ps.NATIVE_INSUFFICIENT})


class PageIngestError(RuntimeError):
    """必须 FAIL_INGEST 的页面级错误（缺 accepted artifact、身份不符等）。"""


@dataclass
class PageInput:
    doc_id: str
    doc_name: str
    source_hash: str
    pdf_page: int
    native_text: str
    doc_lang: str = contracts.CORPUS_LANG_DEFAULT
    ocr_artifact: dict[str, Any] | None = None      # accepted artifact payload；None = 未消费
    visual_suspected: bool | None = None            # 视觉诊断（audit only），None = 不可用
    visual_signal_summary: str | None = None
    inherited_section: str | None = None            # 上一页的有效 section（legacy 继承语义）


@dataclass
class PageResult:
    record: dict[str, Any]
    chunks: list[contracts.Chunk] = field(default_factory=list)
    section_for_inheritance: str | None = None


def needs_ocr(native_body_status: str) -> bool:
    """production rule：insufficient / unusable → OCR_ATTEMPT。不读任何视觉信号。"""
    return native_body_status in OCR_ATTEMPT_STATES


def select_primary_body(native_body: str, ocr_body: str | None, native_status: str,
                        ocr_status: str) -> tuple[str, str]:
    """选出唯一的 primary body 与其 channel。

    结构上只可能返回一个 channel 的文本：本函数【没有】任何把两段文本合并的分支。
    返回 (body, channel)。
    """
    if native_status in OCR_ATTEMPT_STATES:
        if ocr_status == ps.OCR_USABLE and ocr_body is not None:
            return ocr_body, BODY_CHANNEL_OCR
        return "", BODY_CHANNEL_NONE          # OCR 不可用：不退回 native 残余正文
    return native_body, BODY_CHANNEL_NATIVE


def process_page(inp: PageInput, page_identity_ok: bool = True) -> PageResult:
    """处理一页：产生 page_quality 记录与（若入库）该页的 chunks。"""
    view = native.native_page_view(inp.native_text)
    native_body = str(view["body"])
    meta = view["meta"]  # type: ignore[assignment]
    native_status, native_reason = ps.classify_native_body(native_body, inp.doc_lang)

    # ---- native metadata candidate（含 legacy 继承语义）----
    cand_value = view["candidate_value"]
    cand_kind = str(view["candidate_source_kind"])
    cand_raw = view["candidate_raw_line"]
    if cand_value is None and inp.inherited_section is not None:
        native_cand = cg.MetadataCandidate(inp.inherited_section, cg.KIND_INHERITED, cg.CHANNEL_NATIVE, None)
    elif cand_value is None:
        native_cand = cg.none_candidate(cg.CHANNEL_NATIVE)
    else:
        native_cand = cg.MetadataCandidate(str(cand_value), cand_kind, cg.CHANNEL_NATIVE,
                                           str(cand_raw) if cand_raw else None)

    # ---- OCR 通道 ----
    ocr_required = needs_ocr(native_status)
    artifact = inp.ocr_artifact
    if ocr_required and artifact is None:
        raise PageIngestError(
            f"{inp.doc_id}:p{inp.pdf_page} native_body_status={native_status} 需要 accepted OCR artifact，但未提供"
        )
    ocr_body: str | None = None
    ocr_cand = cg.none_candidate(cg.CHANNEL_OCR)
    if artifact is not None:
        if artifact["source_hash"] != inp.source_hash or int(artifact["pdf_page"]) != inp.pdf_page:
            raise PageIngestError(
                f"artifact 身份与页面不一致: {artifact['source_hash']}:{artifact['pdf_page']} "
                f"vs {inp.source_hash}:{inp.pdf_page}"
            )
        ocr_text = str(artifact["text"])
        ocr_body = str(native.ocr_page_view(ocr_text)["body"])
        ocr_cand = cg.extract_ocr_candidate(ocr_text, native.HEADER_SCAN_LINES)
    ocr_raw_text = str(artifact["text"]) if artifact is not None else None
    ocr_status, ocr_reason = ps.classify_ocr_body(ocr_body, artifact is not None,
                                                  ocr_raw_text, ocr_required)

    # ---- 独立 citation gate（两个 candidate 都进，不预设来源）----
    gate = cg.evaluate(native_cand, ocr_cand, page_identity_ok)

    # ---- completeness（audit only）----
    completeness, completeness_reason = ps.classify_completeness(native_status, inp.visual_suspected)

    # ---- primary body 选择（单 channel）----
    body, body_channel = select_primary_body(native_body, ocr_body, native_status, ocr_status)

    # ---- policy：状态 → 动作 ----
    gates_uncertain: list[str] = []
    if gate.status == cg.UNCERTAIN:
        gates_uncertain.append("citation")
    if native_status == ps.NATIVE_UNCERTAIN:
        gates_uncertain.append("native_body")
    if ocr_status == ps.OCR_DEGRADED:
        gates_uncertain.append("ocr_body")
    policy, policy_reason = ps.classify_content_policy(body, gates_uncertain)

    action, action_reason, require_review = _decide_action(native_status, ocr_status, gate, body,
                                                           body_channel, ocr_reason)
    if action not in TERMINAL_ACTIONS:
        raise PageIngestError(f"未定义的终态: {action}")

    # ---- 元数据落到 Chunk 的取值（来自 gate 选定的 channel）----
    section_value = gate.resolved_value or (native_cand.value if native_cand.has_value() else None)
    aux_meta = meta if gate.metadata_source_channel != cg.CHANNEL_OCR else _ocr_aux_meta(artifact)

    chunks: list[contracts.Chunk] = []
    if action in (ACTION_ADMITTED_NATIVE, ACTION_ADMITTED_OCR):
        chunks = _build_chunks(inp, body, section_value, aux_meta)

    record = {
        # identity
        "doc_id": inp.doc_id, "source_filename": inp.doc_name,
        "source_hash": inp.source_hash, "pdf_page": inp.pdf_page,
        # native
        "native_body_status": native_status, "native_detector_reason": native_reason,
        "native_body_chars": len(native_body),
        "native_metadata_candidate": native_cand.value,
        "native_metadata_source_kind": native_cand.source_kind,
        "native_metadata_raw_line": native_cand.raw_line,
        # visual diagnostics（diagnostic only）
        "visual_signal_summary": inp.visual_signal_summary,
        "active_row_diagnostic": inp.visual_suspected,
        # ocr
        "ocr_attempted": bool(artifact is not None),
        "ocr_artifact_sha256": (artifact or {}).get("ocr_artifact_sha256"),
        "ocr_cache_key_digest": (artifact or {}).get("cache_key_digest"),
        "ocr_engine": (artifact or {}).get("ocr_engine"),
        "ocr_engine_version": (artifact or {}).get("ocr_engine_version"),
        "ocr_params_digest": (artifact or {}).get("ocr_params_digest"),
        "langpack_identity_digest": (artifact or {}).get("langpack_identity_digest"),
        "rasterizer": (artifact or {}).get("rasterizer"),
        "rasterizer_version": (artifact or {}).get("rasterizer_version"),
        "raster_dpi": (artifact or {}).get("raster_dpi"),
        "ocr_body_status": ocr_status, "ocr_body_reason": ocr_reason,
        "ocr_body_chars": len(ocr_body) if ocr_body is not None else None,
        "ocr_metadata_candidate": ocr_cand.value,
        "ocr_metadata_source_kind": ocr_cand.source_kind,
        "ocr_engine_confidence_stats": (artifact or {}).get("confidence_stats"),
        # resolved
        "body_source_channel": body_channel,
        "metadata_source_channel": gate.metadata_source_channel,
        "citation_metadata_status": gate.status,
        "metadata_conflict": gate.metadata_conflict,
        "metadata_reason_code": gate.reason_code,
        "resolved_section": section_value,
        "page_content_completeness_status": completeness,
        "page_content_completeness_reason": completeness_reason,
        "content_policy_status": policy, "content_policy_reason": policy_reason,
        "remediation_action": action, "remediation_reason": action_reason,
        "require_review": require_review,
        "chunk_ids": [c.id for c in chunks],
    }
    inherit = native_cand.value if (cand_value is not None) else inp.inherited_section
    return PageResult(record=record, chunks=chunks, section_for_inheritance=inherit)


def _decide_action(native_status: str, ocr_status: str, gate: cg.CitationGateResult,
                   body: str, body_channel: str, ocr_reason: str) -> tuple[str, str, bool]:
    """policy 层：只读 states 与 state 自带的 reason code，不读原始信号。

    `ocr_reason` 只参与【归因文本】的拼装，不参与任何分支判断 ——
    分支仍然只看 states，动作因此与 reason 正交。
    返回 (action, reason, require_review)。
    """
    if native_status in (ps.NATIVE_USABLE, ps.NATIVE_UNCERTAIN):
        # legacy native 页：metadata uncertain 维持 baseline 行为（入库 + 审计标记）；
        # 只有明确 failed 才隔离。这一不对称是 Design Freeze §11 的有意设计。
        if gate.status == cg.FAILED:
            return ACTION_QUARANTINED, f"native_path:citation_failed:{gate.reason_code}", True
        if len(body) < contracts.CHUNK_MIN_CHARS:
            return ACTION_SKIPPED_NONCONTENT, "native_path:body_below_min", False
        if gate.status == cg.UNCERTAIN or native_status == ps.NATIVE_UNCERTAIN:
            return ACTION_ADMITTED_NATIVE, f"native_path:{gate.reason_code}", True
        return ACTION_ADMITTED_NATIVE, "native_path:explicit_supported", False

    # CASE R / CASE S：OCR 路径
    if ocr_status in (ps.OCR_FAILED, ps.OCR_DEGRADED):
        if len(body) < contracts.CHUNK_MIN_CHARS:
            if ocr_status == ps.OCR_FAILED:
                # 归因带上 ocr_reason：剥离后无业务正文 != OCR 引擎失败。
                return ACTION_SKIPPED_NONCONTENT, f"ocr_path:no_business_body:{ocr_reason}", False
            return ACTION_QUARANTINED, "ocr_path:ocr_degraded", True
        return ACTION_QUARANTINED, f"ocr_path:{ocr_status}", True
    if gate.status != cg.EXPLICIT_SUPPORTED:
        # OCR-derived / OCR-recovered 页：非 explicit_supported 一律不入 corpus
        return ACTION_QUARANTINED, f"ocr_path:citation_{gate.status}:{gate.reason_code}", True
    if len(body) < contracts.CHUNK_MIN_CHARS:
        return ACTION_SKIPPED_NONCONTENT, "ocr_path:body_below_min", False
    return ACTION_ADMITTED_OCR, f"ocr_path:{body_channel}_body+explicit_supported", False


def _ocr_aux_meta(artifact: dict[str, Any] | None) -> dict[str, str | None]:
    """OCR 通道的附属展示字段。OCR 页眉不保证列对齐，取不到即 None，不猜。"""
    if artifact is None:
        return {"printed_page": None, "issued_by": None, "revision": None, "section_title": None}
    meta = native.ocr_page_view(str(artifact["text"]))["meta"]
    return {
        "printed_page": meta["printed_page"], "issued_by": meta["issued_by"],  # type: ignore[index]
        "revision": meta["revision"], "section_title": meta["section_title"],  # type: ignore[index]
    }


def _build_chunks(inp: PageInput, body: str, section_value: str | None,
                  aux: dict[str, Any]) -> list[contracts.Chunk]:
    """对已选定的 primary body 分块（复用既有分块规则与 Chunk id 口径）。"""
    section = section_value or native.UNKNOWN_SECTION
    out: list[contracts.Chunk] = []
    for ordinal, text in enumerate(native.split_body_to_texts(body)):
        out.append(contracts.Chunk(
            id=f"{inp.doc_id}:p{inp.pdf_page}:{ordinal}",
            text=text, doc_id=inp.doc_id, doc_name=inp.doc_name,
            section=section, section_title=aux.get("section_title"),
            pdf_page=inp.pdf_page, printed_page=aux.get("printed_page"),
            issued_by=aux.get("issued_by"), revision=aux.get("revision"),
            source_hash=inp.source_hash,
        ))
    return out
