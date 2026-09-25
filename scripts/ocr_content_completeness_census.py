#!/usr/bin/env python3
"""OCR / page-usability 调查 Phase A.2b —— 收敛性诊断（只读）。

Part A: 检验 A.1 已采集的 active-row / active-column 信号能否解决 A.2 的
        EMM p.1（negative cover） vs CRM p.74 / p.77（positive）冲突。
Part B: 用【内容级】对比（不是 ink proxy）普查 QMM p.110 型 extraction incompleteness：
        native text 足够、已有 chunk、V1 不触发，但页面视觉层仍含 native/corpus 未覆盖的业务知识。

不 OCR、不改 parser / corpus / contracts / V1 / V2 / A.2 标签与预注册。

用法:
    python3 scripts/ocr_content_completeness_census.py --stage {parta,select,render,analyze} \\
        --pdf-dir "raw/KAIVA - Manuals" --corpus corpus/chunks.jsonl --testset eval/testset_v5_3.jsonl \\
        --phase-a-csv experiments/ocr_survey/_page_signals.csv \\
        --visual-csv experiments/ocr_survey/_visual_page_signals.csv \\
        --a2-csv experiments/ocr_survey/_visual_threshold_validation.csv \\
        --out-csv experiments/ocr_survey/_content_completeness_census.csv \\
        --out-log experiments/ocr_survey/_content_completeness_census.log \\
        --work-dir <scratchpad>/a2b [--seed 20260921]

stage:
    parta    只做 Part A（写 log 的 Part A 段到 stdout，用于在 review 之前定 CASE）
    select   只做 Part B 的页面选取与 native/corpus 文本导出（写到 --work-dir），不产出最终产物
    render   把 select 选出的页面渲染成 PNG 到 --work-dir/png（pdftoppm，非 OCR）
    analyze  完整产出 --out-csv 与 --out-log（默认）

失败语义:
    corpus sha / chunk 数与冻结值不符、输入缺列、A.2 标签数量与冻结值不符、population 为空、
    pdftoppm / pdftotext 失败、review 标签缺失或非法 → 抛异常。单页失败显式记录，不静默跳过。

确定性:
    CSV 逐字节确定；log 除【TIMING】段外逐字节确定。随机只用于 B-P4 的 control 抽样，seed 固定。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Sequence

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import contracts  # noqa: E402

# ==============================================================================
# 冻结输入与常量
# ==============================================================================

EXPECTED_CORPUS_SHA256: str = "8c6bee0aa952b387e20a2de76253d4384ffe859a8050e6fe8fee9166c956aeaa"
EXPECTED_CHUNK_COUNT: int = 3383
EXPECTED_A2_POS: int = 66
EXPECTED_A2_NEG: int = 7
DEFAULT_SEED: int = 20260921

PDF_SUFFIX: str = ".pdf"
POPPLER_TIMEOUT_S: float = 180.0
HASH_READ_BLOCK_BYTES: int = 1 << 20
RATIO_DECIMALS: int = 6
REVIEW_DPI: int = 100
REVIEW_DPI_FALLBACK: int = 150

SET_POS: str = "POSITIVE_VISUAL_RECOVERY_CANDIDATE"
SET_NEG: str = "NEGATIVE_NON_CONTENT"

# Part A：PRIMARY 候选（预注册 A-P2，gray 固定 245、fraction 固定 0.01）
PRIMARY_FEATURES: tuple[tuple[str, str], ...] = (
    ("A1", "d40_active_row_ratio_245_f0p01"),
    ("A2", "d40_active_column_ratio_245_f0p01"),
    ("A3", "d40_middle_active_row_ratio_245_f0p01"),
    ("A4", "d100_active_row_ratio_245_f0p01"),
    ("A5", "d100_active_column_ratio_245_f0p01"),
    ("A6", "d100_middle_active_row_ratio_245_f0p01"),
)
KEY_PAGES: tuple[tuple[str, int, str], ...] = (
    ("EMM", 1, "negative cover"),
    ("CRM", 74, "positive visual-business-content（超大幅面）"),
    ("CRM", 77, "positive visual-business-content（网络拓扑图）"),
)
SENSITIVITY_GRAYS: tuple[int, ...] = (250, 245, 235)
SENSITIVITY_FRACTIONS: tuple[str, ...] = ("f0p001", "f0p01", "f0p05")
SENSITIVITY_KINDS: tuple[str, ...] = ("active_row_ratio", "active_column_ratio", "middle_active_row_ratio")

# Part B：预注册 B-P3 / B-P4 的机械规则参数
TOP_PERCENT: float = 0.10
ASPECT_TOLERANCE: float = 0.05
AREA_FACTOR: float = 1.5
IMG_HEAVY_PERCENTILE: int = 90
CANDIDATE_CAP: int = 100
RANDOM_CONTROL_N: int = 50
POSITIVE_CONTROL: tuple[str, int] = ("QMM", 110)
POSITIVE_CONTROL_PHRASES: tuple[str, ...] = (
    "Concur with parameters for change",
    "Identify risk assessment team",
    "Close out and Sign Off",
)

REVIEW_LABELS: tuple[str, ...] = (
    "COMPLETE_NATIVE", "VISUAL_KNOWLEDGE_MISSING", "VISUAL_NON_TEXTUAL", "UNCERTAIN",
)
LABEL_MISSING: str = "VISUAL_KNOWLEDGE_MISSING"
REVIEWER: str = "claude_visual_review"
LABEL_SOURCE: str = "Phase_A2b_visual_native_comparison"
TIMING_MARKER: str = "==== 【TIMING】 非确定段：确定性比较时删除本行及其后全部内容 ===="

PREREGISTRATION_NOTE: str = (
    "本常量与 scratchpad a2b/prereg_block.txt 逐字节相同；该文件与 a2b_prereg.log 在读取三个关键页的 "
    "active 信号之前写入，log 头记录其 sha256"
)

PREREGISTRATION: str = r"""==== A.2b PREREGISTRATION（在读取 EMM p.1 / CRM p.74 / CRM p.77 的 active 信号之前写下；之后不修改） ====

[Part A] active-row / active-column 能否解决 A.2 的 cover-vs-business-content 冲突
A-P1 labels：完全沿用 A.2 已冻结标签（_visual_threshold_validation.csv 的 eval_set 列）：
     POSITIVE = 66（visual_business_content），NEGATIVE = 7。本轮不重新人工标注、不改标签。
A-P2 PRIMARY 候选只有这 6 个（gray 固定 245 = A.2 primary；active fraction 固定 0.01 = A.1 三档中间值）：
     A1 d40_active_row_ratio_245_f0p01
     A2 d40_active_column_ratio_245_f0p01
     A3 d40_middle_active_row_ratio_245_f0p01
     A4 d100_active_row_ratio_245_f0p01
     A5 d100_active_column_ratio_245_f0p01
     A6 d100_middle_active_row_ratio_245_f0p01
A-P3 机制假设（方向）：cover = 少数大号标题/logo 文本块，墨迹可能重，但纵向/横向占据的 active row/column 较少；
     visual business diagram / flowchart / 分布式表格 = 框、线、标签分散，active row/column 更广。
     故预期 POSITIVE 的 active 信号整体【高于】NEGATIVE，特别是 CRM p.74 / p.77 【高于】EMM p.1。
     判定方向固定为 "signal > tau ⇒ visual content"。若统计可分但方向与此相反，最多判 STRUCTURE_CASE_2，不得判 CASE_1。
A-P4 阈值规则（与 A.2 P7 相同，不新造）：P_min = 训练 POS 最小有定义值；V_below = 训练 POS∪NEG 中严格小于 P_min 的最大值；
     有 V_below → tau = midpoint(V_below, P_min)，trigger iff signal > tau；无 → observed boundary，trigger iff signal >= P_min。
     训练 POS 或 NEG 为空 → insufficient data，不产出阈值。
A-P5 validation：(a) descriptive separation：是否存在方向符合 A-P3 的单阈值，使 66 POS 全保留且 EMM p.1 不触发；
     (b) leave-one-out（POS∪NEG 每页一折）；(c) leave-one-document-out；报告 POS miss / NEG trigger / tau 范围 / fold 不稳定 / 失败页。
A-P6 CASE 判据：
     STRUCTURE_CASE_1 = 至少一个 PRIMARY 同时满足：方向符合 A-P3、descriptive separation 成立、LOO 的 POS miss=0 且 NEG trigger=0、
       LODO 每个数据充分折 POS recall=1 且 NEG trigger=0、且相对 A.2 的 F1/F2 冲突有明确改善（即 EMM p.1 不再必然触发）。
     STRUCTURE_CASE_2 = 全样本看似可分但 LOO/LODO 不稳定，或方向与 A-P3 相反，或只有局部页面可分，或改善不足以支持结构解释。
     STRUCTURE_CASE_3 = A1–A6 全部无法分开 EMM p.1 与 CRM p.74/p.77。
A-P7 sensitivity（仅在 PRIMARY 结论写定之后看）：gray 235/250 与 fraction 0.001/0.05，只用于判断 primary 方向是否稳定；
     不得从中挑最优 feature；primary 失败而某 cell 成功只能记 new_observation，不得写 solved。

[Part B] page_content_completeness 普查
B-P1 population := corpus_chunk_count > 0 AND parser_body_chars >= CHUNK_MIN_CHARS(120) AND v1_trigger == false（v1 = alpha_token_ratio <= 0）。
B-P2 GOLD_PAGE_REVIEW 最先执行：eval/testset_v5_3.jsonl 全部 citation 去重成 unique (doc_id, pdf_page)，全部 review（即使不在 B-P1 内也 review，并标注是否属于 B-P1）。
B-P3 prioritized candidate（机械规则，先于看图冻结；全部在 B-P1 内计算）：
     P1 = d40_middle_nonwhite_ratio_245 的 top 10%（降序，最近秩；并列全取）
     P2 = d40_active_row_ratio_245_f0p01 的 top 10%（同上）
     P3 = d40_active_column_ratio_245_f0p01 的 top 10%（同上）
     P4 = 版面异常页：令 aspect = d40_width_px / d40_height_px，area = d40_width_px * d40_height_px；
          取 |aspect - median(aspect)| / median(aspect) > 0.05 或 area > 1.5 * median(area) 的页
     P5 = image-object-heavy：img_object_count >= p90(img_object_count over B-P1, 最近秩) 且 >= 1
     union = P1∪P2∪P3∪P4∪P5。若 |union| > 100，按 (命中 P 集合数 降序, d40_middle_nonwhite_ratio_245 降序, doc_id 升序, pdf_page 升序) 截取前 100；
     若 <= 100 则全取，不补足。percentile 事后不得调整。
B-P4 random control：从 B-P1 \ union 中，按 (doc_id, pdf_page) 排序后用 random.Random(20260921).sample 抽 50 页；不足 50 则全取。
     该组只是 exploratory control，不得称为 corpus prevalence。
B-P5 positive control：QMM p.110，独立复现三个短语 "Concur with parameters for change" / "Identify risk assessment team" /
     "Close out and Sign Off" 在【本页 native text】与【本页 corpus chunk text】中的存在性；无法复现则报 discrepancy，不得沿用 A.2 结论。
B-P6 review labels（看图前冻结，只允许这 4 个）：
     COMPLETE_NATIVE：页面上用于 RAG 的主要文字/结构业务信息已被 native extraction / corpus text 覆盖（可存在 logo、装饰图、表格线、
       非文字照片、native text 已完整描述的示意图）。
     VISUAL_KNOWLEDGE_MISSING：页面含明确业务文字/数值/流程关系/职责关系/表格字段/decision logic，且至少一个具有独立业务意义的信息
       在本页 native text 与本页 corpus chunks 中都找不到。
     VISUAL_NON_TEXTUAL：存在业务相关图片/照片/示意图，但未观察到值得文本抽取的缺失业务文字信息。
     UNCERTAIN：仅凭 rendered page + native/corpus text 无法可靠判断（含视觉文字无法可靠转录）。
     "有图" ≠ MISSING；"墨迹高" ≠ MISSING。
B-P7 证据规则：每个 VISUAL_KNOWLEDGE_MISSING 必须给出至少一个 missing_content_example（优先可见短语/数值/关系/决策步骤/表格字段），
     并分别在本页 native text 与本页 corpus chunk text 中检索，报告 found_in_native / found_in_corpus。
     允许的 normalization 只有：Unicode NFKC、空白折叠、casefold。语义近似不算 found。无法可靠转录 → UNCERTAIN。
B-P8 review 方式：看 100 dpi 渲染图；不可读时 150 dpi。禁止任何 OCR。reviewer = claude_visual_review，label_source = Phase_A2b_visual_native_comparison。
B-P9 计数规则：同一页只 review 一次，但 is_prioritized_candidate / is_random_control / is_gold_page / is_positive_control 四个成员标记独立保留；
     分组 yield 分开报告，禁止合并成总体 prevalence。
==== END A.2b PREREGISTRATION ====
"""

CSV_COLUMNS: tuple[str, ...] = (
    "doc_id", "pdf_page", "source_filename", "chunk_ids", "parser_body_chars", "corpus_chunk_count", "v1_trigger",
    "d40_middle_nonwhite_ratio_245", "d40_active_row_ratio_245_f0p01", "d40_active_column_ratio_245_f0p01",
    "page_width", "page_height", "image_object_count",
    "in_part_b_population",
    "is_prioritized_candidate", "prioritized_sets", "is_random_control", "is_gold_page", "gold_question_ids",
    "is_positive_control",
    "review_label", "review_dpi", "visual_observation",
    "missing_content_example", "found_in_native", "found_in_corpus",
    "native_text_chars", "reviewer", "label_source",
)


class CensusError(RuntimeError):
    """输入不一致或环境错误。"""


# ==============================================================================
# 人工 review 结果（reviewer = claude_visual_review；看 100 dpi 渲染图 + 本页 native/corpus 文本）
# 键 (doc_id, pdf_page) → (label, review_dpi, visual_observation, missing_content_example)
# missing_content_example 仅 VISUAL_KNOWLEDGE_MISSING 必填；其余为 ""。
# ==============================================================================

A2B_REVIEW_LABELS: dict[tuple[str, int], tuple[str, int, str, str]] = {
    ('CMM', 20): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('CMM', 32): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('CMM', 60): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('CMM', 74): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('CMM', 75): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('CMM', 79): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('CMM', 83): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('CMM', 87): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('CMM', 97): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('CMM', 112): ('VISUAL_KNOWLEDGE_MISSING', 100, 'Appendix V 表 BC1（高级船员行为特征）整表为图像，仅标题为原生文本', 'Able to carry out duties effectively and efficiently on time'),
    ('CMM', 117): ('VISUAL_KNOWLEDGE_MISSING', 100, 'Appendix V 表 Engine KPI 2 整表为图像，仅标题为原生文本', 'TARB Requirements'),
    ('CMM', 132): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('CRM', 12): ('VISUAL_NON_TEXTUAL', 100, 'NIST CSF 五功能轮盘图（IDENTIFY/PROTECT/DETECT/RESPOND/RECOVER）；本页 PR.AC 子类表为原生文本，轮盘只重复章节结构', ''),
    ('CRM', 28): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('CRM', 30): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('CRM', 49): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('CRM', 56): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('CRM', 57): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('CRM', 59): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('CRM', 68): ('VISUAL_KNOWLEDGE_MISSING', 100, 'GP 1.7 数据分级表（Level 0-3 及示例、影响）整表为图像', 'Marketing materials, Job descriptions'),
    ('CRM', 72): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('CRM', 75): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('CRM', 76): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('CRM', 81): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('CRM', 93): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('CRM', 94): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('EMM', 3): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('EMM', 4): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('EMM', 5): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('EMM', 7): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('EMM', 10): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('EMM', 11): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('EMM', 12): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('EMM', 15): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('EMM', 16): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('EMM', 23): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('EMM', 25): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('EMM', 27): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('EMM', 29): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('EMM', 39): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('EMM', 41): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('EMM', 48): ('VISUAL_KNOWLEDGE_MISSING', 100, 'DYNAMARINe EMP 报表界面截图，内含填报与提交时限说明', 'by the 5th of the following month'),
    ('EMM', 49): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('EMM', 62): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('EMM', 63): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('EMM', 72): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('EMM', 77): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('EMM', 80): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('EMM', 81): ('VISUAL_KNOWLEDGE_MISSING', 100, 'e-learning 模块矩阵（12 个月有效期）为图像：模块编号/名称/各职级强制标记', 'Sustainable shipping'),
    ('EMM', 82): ('VISUAL_KNOWLEDGE_MISSING', 100, 'e-learning 模块矩阵（24 个月有效期）为图像', 'Green Passport'),
    ('EMM', 83): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('EMM', 86): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('EMM', 88): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('EMM', 91): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('EMM', 93): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('EMM', 96): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('EMM', 97): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('EMM', 98): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('EMM', 99): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('EMM', 100): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('EMM', 102): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('EMM', 105): ('VISUAL_NON_TEXTUAL', 100, '封条样例照片（编号为样品），图注与规则为原生文本', ''),
    ('EMM', 108): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('EMM', 111): ('VISUAL_NON_TEXTUAL', 100, '封条/链条加封照片，规则与图注为原生文本', ''),
    ('EMM', 112): ('VISUAL_KNOWLEDGE_MISSING', 100, '封条照片内的标注文字给出加封规则；本页原生文本只有图注（同一规则的原生表述在相邻 p.111）', 'One seal should pass through the hole in the spindle'),
    ('EMM', 114): ('VISUAL_NON_TEXTUAL', 100, '人孔盖加封照片，标注文字与本页原生文本表述同一规则', ''),
    ('EMM', 115): ('VISUAL_KNOWLEDGE_MISSING', 100, "无法兰管路封堵照片标注给出材料规格；本页原生文本只写 'angle bars'，未含 PVC 材质", 'Use PVC angle bar'),
    ('EMM', 117): ('VISUAL_NON_TEXTUAL', 100, '舱底管系涂色照片 + 原生说明', ''),
    ('EMM', 118): ('VISUAL_NON_TEXTUAL', 100, '应急舱底吸口照片 + 原生说明', ''),
    ('EMM', 119): ('VISUAL_NON_TEXTUAL', 100, '开闭件固定照片（cotter key）+ 原生说明', ''),
    ('EMM', 120): ('VISUAL_NON_TEXTUAL', 100, '封条位置照片 + 原生说明', ''),
    ('EMM', 122): ('VISUAL_NON_TEXTUAL', 100, '清洁剂/容器照片 + 原生说明', ''),
    ('EMM', 124): ('VISUAL_NON_TEXTUAL', 100, '取样点照片，标注文字为原生文本', ''),
    ('EMM', 127): ('VISUAL_NON_TEXTUAL', 100, '15ppm 报警设备照片 + 原生参数表', ''),
    ('EMM', 131): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('EMM', 132): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('EMM', 133): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('EMM', 135): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('EMM', 141): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('EMM', 144): ('VISUAL_KNOWLEDGE_MISSING', 100, 'Westfalia 说明书节选为图像：孔板直径与处理量对照表', 'no orifice plate'),
    ('EMM', 146): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('EMM', 147): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('EMM', 149): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('EMM', 150): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('EMM', 154): ('VISUAL_KNOWLEDGE_MISSING', 100, '生活污水处理装置流程示意图为图像：各舱室与部件标签', 'Sludge Return Line'),
    ('EMM', 159): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('EMM', 169): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('EMM', 171): ('VISUAL_NON_TEXTUAL', 100, 'ABS NSE 软件界面截图（示例数据），原生正文说明标记方法', ''),
    ('EMM', 172): ('VISUAL_NON_TEXTUAL', 100, 'NSE 关键备件清单截图（某船示例数据），非权威内容，原生正文指向系统', ''),
    ('EMM', 173): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('ERM', 14): ('VISUAL_KNOWLEDGE_MISSING', 100, '4.1.2 Line of Communication 关系图为图像：船-岸上报与 CRT/CMT 升级关系', 'In charge of vessel'),
    ('ERM', 20): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('ERM', 27): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('ERM', 37): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('ERM', 38): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('ERM', 39): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('ERM', 57): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('ERM', 68): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('ERM', 70): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('ERM', 85): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('ERM', 98): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('ERM', 103): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('ERM', 105): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('ERM', 108): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('ERM', 110): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('ERM', 118): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('ERM', 119): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('ERM', 127): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('ERM', 128): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('ERM', 129): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('ERM', 130): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('ERM', 131): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('ERM', 133): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('ERM', 139): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('FMM', 29): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('FMM', 32): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('FMM', 38): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('FMM', 69): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('FMM', 118): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('FMM', 159): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('FMM', 160): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('FMM', 161): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('FMM', 243): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('FMM', 251): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('FMM', 289): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('FMM', 307): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('NPM', 14): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('NPM', 27): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('NPM', 35): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('NPM', 44): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('NPM', 51): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('NPM', 79): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('QMM', 10): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('QMM', 12): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('QMM', 23): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('QMM', 32): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('QMM', 33): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('QMM', 34): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('QMM', 46): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('QMM', 51): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('QMM', 52): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('QMM', 57): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('QMM', 71): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('QMM', 73): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('QMM', 92): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('QMM', 110): ('VISUAL_KNOWLEDGE_MISSING', 100, '19.x MOC 六步流程图为图像：步骤与责任人', 'Concur with parameters for change'),
    ('QMM', 121): ('VISUAL_KNOWLEDGE_MISSING', 100, 'Flowchart Q-19.8 技术/维护/采购流程图为图像：环节与循环关系', 'Sign Ship Management Agreement'),
    ('QMM', 136): ('VISUAL_KNOWLEDGE_MISSING', 100, 'Open Reporting 海报：大部分文字为原生，但 24/7 热线号码在电话图形内', '24/7 HOTLINE +65 6839 6545'),
    ('QMM', 149): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('QMM', 158): ('VISUAL_KNOWLEDGE_MISSING', 100, '同 A.1 PTM 版 Open Reporting 海报：热线号码在图形内', '24/7 HOTLINE +65 6839 6545'),
    ('SMM', 6): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('SMM', 14): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('SMM', 15): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('SMM', 16): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('SMM', 17): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('SMM', 20): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('SMM', 23): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('SMM', 32): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('SMM', 35): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('SMM', 38): ('VISUAL_KNOWLEDGE_MISSING', 100, 'STEP-2 Toolbox Meeting 流程图为图像：会议内容要求（PPE Matrix / Safety Flash / 指定讲解人）', 'Check what PPE is required as per the PPE Matrix'),
    ('SMM', 43): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('SMM', 46): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('SMM', 56): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('SMM', 57): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('SMM', 61): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('SMM', 72): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('SMM', 73): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('SMM', 74): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('SMM', 79): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('SMM', 94): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('TACM', 14): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('TACM', 15): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('TACM', 16): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('TACM', 23): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
    ('TACM', 110): ('COMPLETE_NATIVE', 100, '100 dpi 人工查看：页面正文/表格/清单为原生文本，未见 native extraction 未覆盖的业务文字信息', ''),
}


# ==============================================================================
# 基础工具
# ==============================================================================

def run_cmd(argv: Sequence[str]) -> bytes:
    try:
        proc = subprocess.run(list(argv), capture_output=True, timeout=POPPLER_TIMEOUT_S)
    except FileNotFoundError as exc:
        raise CensusError(f"命令不可用: {argv[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise CensusError(f"超时: {' '.join(argv)}") from exc
    if proc.returncode != 0:
        raise CensusError(f"{argv[0]} 返回 {proc.returncode}: {proc.stderr.decode('utf-8', 'replace').strip()}")
    return proc.stdout


def tool_version(tool: str) -> str:
    proc = subprocess.run([tool, "-v"], capture_output=True, timeout=POPPLER_TIMEOUT_S)
    text = (proc.stdout + proc.stderr).decode("utf-8", "replace").strip()
    if not text:
        raise CensusError(f"{tool} -v 无输出")
    return text.splitlines()[0]


def file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(HASH_READ_BLOCK_BYTES), b""):
            digest.update(block)
    return digest.hexdigest()


def fmt(x: float | None) -> str:
    return "" if x is None else f"{x:.{RATIO_DECIMALS}f}"


def pct(values: Sequence[float], p: int) -> float:
    """最近秩分位（确定性）。输入非空。"""
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, round(p / 100 * (len(ordered) - 1))))]


def norm(text: str) -> str:
    """B-P7 允许的唯一归一化：NFKC + 空白折叠 + casefold。"""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip().casefold()


def read_csv(path: str, required: Sequence[str]) -> list[dict[str, str]]:
    with open(path, encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [c for c in required if c not in (reader.fieldnames or [])]
        if missing:
            raise CensusError(f"{path} 缺列: {missing}")
        return list(reader)


def page_native_text(pdf_dir: str, filename: str, page: int) -> str:
    """单页 pdftotext -layout（与 parser 同口径的命令，非 OCR）。"""
    raw = run_cmd(["pdftotext", "-layout", "-f", str(page), "-l", str(page), os.path.join(pdf_dir, filename), "-"])
    return raw.decode("utf-8", errors="replace").replace("\f", "")


def render_png(pdf_dir: str, filename: str, page: int, dpi: int, out_root: str) -> str:
    run_cmd(["pdftoppm", "-gray", "-png", "-singlefile", "-r", str(dpi),
             "-f", str(page), "-l", str(page), os.path.join(pdf_dir, filename), out_root])
    return out_root + ".png"


# ==============================================================================
# 输入装载
# ==============================================================================

@dataclass
class Inputs:
    phase_a: dict[tuple[str, int], dict[str, str]]
    visual: dict[tuple[str, int], dict[str, str]]
    a2: dict[tuple[str, int], dict[str, str]]
    chunks: dict[tuple[str, int], list[dict[str, object]]]
    gold: dict[tuple[str, int], list[str]]


def load_inputs(args: argparse.Namespace) -> Inputs:
    corpus_sha = file_sha256(args.corpus)
    chunks: dict[tuple[str, int], list[dict[str, object]]] = defaultdict(list)
    n = 0
    with open(args.corpus, encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            c = json.loads(line)
            chunks[(c["doc_id"], int(c["pdf_page"]))].append(c)
            n += 1
    if corpus_sha != EXPECTED_CORPUS_SHA256 or n != EXPECTED_CHUNK_COUNT:
        raise CensusError(f"corpus 与冻结值不符: sha={corpus_sha} chunks={n}")

    phase_a = {(r["doc_id"], int(r["pdf_page"])): r for r in read_csv(
        args.phase_a_csv, ("doc_id", "pdf_page", "source_filename", "alpha_token_ratio",
                           "parser_body_chars", "corpus_chunk_count"))}
    visual = {(r["doc_id"], int(r["pdf_page"])): r for r in read_csv(
        args.visual_csv, ("doc_id", "pdf_page", "img_object_count", "d40_width_px", "d40_height_px",
                          "d40_middle_nonwhite_ratio_245", *(f for _, f in PRIMARY_FEATURES)))}
    a2 = {(r["doc_id"], int(r["pdf_page"])): r for r in read_csv(
        args.a2_csv, ("doc_id", "pdf_page", "eval_set", "review_label"))}
    pos = sum(1 for r in a2.values() if r["eval_set"] == SET_POS)
    neg = sum(1 for r in a2.values() if r["eval_set"] == SET_NEG)
    if pos != EXPECTED_A2_POS or neg != EXPECTED_A2_NEG:
        raise CensusError(f"A.2 标签与冻结值不符: POS={pos} NEG={neg}")

    gold: dict[tuple[str, int], list[str]] = defaultdict(list)
    with open(args.testset, encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            q = json.loads(line)
            for cit in q.get("citations") or []:
                key = (cit["doc_id"], int(cit["pdf_page"]))
                if q["id"] not in gold[key]:
                    gold[key].append(q["id"])
    return Inputs(phase_a, visual, a2, dict(chunks), dict(gold))


def env_lines(args: argparse.Namespace) -> list[str]:
    lines = [
        f"  python           = {platform.python_version()}",
        f"  pdftoppm         = {tool_version('pdftoppm')}",
        f"  pdftotext        = {tool_version('pdftotext')}",
        f"  git_commit       = {run_cmd(['git', 'rev-parse', 'HEAD']).decode().strip()}",
        f"  script           = scripts/ocr_content_completeness_census.py sha256={file_sha256(os.path.abspath(__file__))}",
        f"  corpus           = {args.corpus} sha256={file_sha256(args.corpus)} chunks={EXPECTED_CHUNK_COUNT}（已校验）",
        f"  testset          = {args.testset} sha256={file_sha256(args.testset)}",
        f"  phase_a_csv      = {args.phase_a_csv} sha256={file_sha256(args.phase_a_csv)}",
        f"  a1_visual_csv    = {args.visual_csv} sha256={file_sha256(args.visual_csv)}",
        f"  a2_csv           = {args.a2_csv} sha256={file_sha256(args.a2_csv)}",
        f"  seed             = {args.seed}",
        f"  CHUNK_MIN_CHARS  = {contracts.CHUNK_MIN_CHARS}",
        f"  prereg           = {PREREGISTRATION_NOTE}",
        f"  prereg_block_sha256 = {hashlib.sha256(PREREGISTRATION.encode('utf-8')).hexdigest()}",
    ]
    for fn in sorted(f for f in os.listdir(args.pdf_dir) if f.lower().endswith(PDF_SUFFIX)):
        lines.append(f"  pdf sha256={file_sha256(os.path.join(args.pdf_dir, fn))}  {fn}")
    return lines


# ==============================================================================
# Part A
# ==============================================================================

@dataclass(frozen=True)
class Threshold:
    tau: float
    inclusive: bool
    how: str

    def fires(self, v: float | None) -> bool:
        if v is None:
            return False
        return v >= self.tau if self.inclusive else v > self.tau

    def text(self) -> str:
        return f"signal {'>=' if self.inclusive else '>'} {self.tau:.6f} ({self.how})"


def fit_threshold(pos: Sequence[float | None], neg: Sequence[float | None]) -> Threshold | None:
    """A-P4（= A.2 P7）。训练 POS 无有定义值或 NEG 为空 → None。"""
    pd = [v for v in pos if v is not None]
    if not pd or not neg:
        return None
    p_min = min(pd)
    below = [v for v in (*pd, *(x for x in neg if x is not None)) if v < p_min]
    if below:
        vb = max(below)
        return Threshold((vb + p_min) / 2, False, f"midpoint({vb:.6f}, {p_min:.6f})")
    return Threshold(p_min, True, f"observed_boundary(P_min={p_min:.6f})")


def part_a(inp: Inputs, out: list[str]) -> str:
    w = out.append
    labelled = []
    for key, row in sorted(inp.a2.items()):
        if row["eval_set"] in (SET_POS, SET_NEG):
            v = inp.visual[key]
            labelled.append({"key": key, "doc_id": key[0], "pdf_page": key[1], "set": row["eval_set"],
                             "a2_label": row["review_label"],
                             "sig": {name: (float(v[col]) if v[col] != "" else None) for name, col in PRIMARY_FEATURES}})
    pos = [p for p in labelled if p["set"] == SET_POS]
    neg = [p for p in labelled if p["set"] == SET_NEG]

    w("§A Part A —— active-row / active-column 能否解决 A.2 的 cover vs business-content 冲突")
    w(f"  标签沿用 A.2（未重新标注）: POSITIVE={len(pos)} NEGATIVE={len(neg)}")
    w("  A.1 -> 本轮列名映射: " + "; ".join(f"{n}={c}" for n, c in PRIMARY_FEATURES))
    w("")
    w("  §A.1 三个关键页的 A1–A6 数值")
    w(f"    {'page':<12} {'role':<40} " + " ".join(f"{n:>10}" for n, _ in PRIMARY_FEATURES))
    for doc, page, role in KEY_PAGES:
        p = next(x for x in labelled if x["key"] == (doc, page))
        w(f"    {doc + ':p' + str(page):<12} {role:<40} " + " ".join(f"{fmt(p['sig'][n]):>10}" for n, _ in PRIMARY_FEATURES))
    w("")
    w("  §A.2 POS / NEG 分布")
    w(f"    {'feature':<6} {'POS min':>10} {'POS p5':>10} {'POS p50':>10} {'POS max':>10} | {'NEG min':>10} {'NEG p50':>10} {'NEG max':>10}")
    for name, _ in PRIMARY_FEATURES:
        pv = [p["sig"][name] for p in pos if p["sig"][name] is not None]
        nv = [p["sig"][name] for p in neg if p["sig"][name] is not None]
        w(f"    {name:<6} {pct(pv, 0):>10.6f} {pct(pv, 5):>10.6f} {pct(pv, 50):>10.6f} {pct(pv, 100):>10.6f} | "
          f"{pct(nv, 0):>10.6f} {pct(nv, 50):>10.6f} {pct(nv, 100):>10.6f}")
    w("")
    w("  §A.3 descriptive separation（方向固定 signal > tau ⇒ visual content，见 A-P3）")
    emm = next(x for x in labelled if x["key"] == ("EMM", 1))
    case1_ok: list[str] = []
    summary: dict[str, dict[str, object]] = {}
    for name, _ in PRIMARY_FEATURES:
        pv = [p["sig"][name] for p in pos if p["sig"][name] is not None]
        e = emm["sig"][name]
        sep = e is not None and min(pv) > e
        w(f"    {name}: POS min={fmt(min(pv))} EMM:p1={fmt(e)} → 存在保留全部 POS 且不触发 EMM:p1 的单阈值 = {sep}")
        summary[name] = {"descriptive_sep": sep}
    w("")
    w("  §A.4 leave-one-out（与 A.2 相同的折与阈值规则）")
    for name, _ in PRIMARY_FEATURES:
        folds = []
        for held in labelled:
            train = [p for p in labelled if p is not held]
            th = fit_threshold([p["sig"][name] for p in train if p["set"] == SET_POS],
                               [p["sig"][name] for p in train if p["set"] == SET_NEG])
            if th is None:
                raise CensusError(f"LOO 训练数据不足: {name}")
            folds.append((held, th, th.fires(held["sig"][name])))
        miss = [h for h, _, f in folds if h["set"] == SET_POS and not f]
        trig = [h for h, _, f in folds if h["set"] == SET_NEG and f]
        full = fit_threshold([p["sig"][name] for p in pos], [p["sig"][name] for p in neg])
        unstable = 0
        for held, th, _ in folds:
            for p in labelled:
                if p is not held and full is not None and th.fires(p["sig"][name]) != full.fires(p["sig"][name]):
                    unstable += 1
        taus = [th.tau for _, th, _ in folds]
        summary[name].update(loo_miss=miss, loo_trig=trig, unstable=unstable, full=full)
        w(f"    {name}: POS miss={len(miss)}/{len(pos)} [{','.join(f'{h[0]}:p{h[1]}' for h in (x['key'] for x in miss)) or '-'}]"
          f"  NEG trigger={len(trig)}/{len(neg)} [{','.join(f'{h[0]}:p{h[1]}' for h in (x['key'] for x in trig)) or '-'}]"
          f"  tau[min/p50/max]={min(taus):.6f}/{pct(taus, 50):.6f}/{max(taus):.6f}  unstable={unstable}"
          f"  full_tau={full.text() if full else 'n/a'}")
    w("")
    w("  §A.5 leave-one-document-out")
    docs = sorted({p["doc_id"] for p in labelled})
    for name, _ in PRIMARY_FEATURES:
        ok = True
        details = []
        for d in docs:
            train = [p for p in labelled if p["doc_id"] != d]
            test = [p for p in labelled if p["doc_id"] == d]
            th = fit_threshold([p["sig"][name] for p in train if p["set"] == SET_POS],
                               [p["sig"][name] for p in train if p["set"] == SET_NEG])
            hp = [p for p in test if p["set"] == SET_POS]
            hn = [p for p in test if p["set"] == SET_NEG]
            if th is None:
                details.append(f"{d}=insufficient_data")
                continue
            miss = [p for p in hp if not th.fires(p["sig"][name])]
            trig = [p for p in hn if th.fires(p["sig"][name])]
            if miss or trig:
                ok = False
            details.append(f"{d}(POS {len(hp) - len(miss)}/{len(hp)}, NEG trig {len(trig)}/{len(hn)}"
                           + (f", missed {','.join(f'{p[0]}:p{p[1]}' for p in (x['key'] for x in miss))}" if miss else "")
                           + (f", trig {','.join(f'{p[0]}:p{p[1]}' for p in (x['key'] for x in trig))}" if trig else "") + ")")
        summary[name]["lodo_ok"] = ok
        w(f"    {name}: " + " ".join(details))
    w("")
    w("  §A.6 CASE 判定（A-P6）")
    for name, _ in PRIMARY_FEATURES:
        s = summary[name]
        cond = (bool(s["descriptive_sep"]) and not s["loo_miss"] and not s["loo_trig"] and bool(s["lodo_ok"]))
        w(f"    {name}: descriptive_sep={int(bool(s['descriptive_sep']))} loo_miss={len(s['loo_miss'])} "  # type: ignore[arg-type]
          f"loo_neg_trig={len(s['loo_trig'])} lodo_ok={int(bool(s['lodo_ok']))} unstable={s['unstable']} → CASE_1 条件={int(cond)}")
        if cond:
            case1_ok.append(name)
    direction_ok = []
    for name, _ in PRIMARY_FEATURES:
        pv = [p["sig"][name] for p in pos if p["sig"][name] is not None]
        nv = [p["sig"][name] for p in neg if p["sig"][name] is not None]
        direction_ok.append(pct(pv, 50) > pct(nv, 50))
    any_sep = any(bool(summary[n]["descriptive_sep"]) for n, _ in PRIMARY_FEATURES)
    case = "STRUCTURE_CASE_1" if case1_ok else ("STRUCTURE_CASE_2" if any_sep else "STRUCTURE_CASE_3")
    w(f"    POS p50 > NEG p50 的特征数（方向核对）= {sum(direction_ok)}/6")
    w(f"    → {case}" + (f"（满足 CASE_1 的特征: {','.join(case1_ok)}）" if case1_ok else ""))
    w("")
    w("  §A.7 sensitivity（在 PRIMARY 结论之后；只看方向是否稳定，不从中挑最优）")
    w(f"    {'cell':<42} {'EMM:p1':>10} {'CRMp74':>10} {'CRMp77':>10} {'POS min':>10} {'sep':>5}")
    for dpi in (40, 100):
        for kind in SENSITIVITY_KINDS:
            for gray in SENSITIVITY_GRAYS:
                for frac in SENSITIVITY_FRACTIONS:
                    col = f"d{dpi}_{kind}_{gray}_{frac}"
                    vals = {}
                    for key in [k["key"] for k in labelled]:
                        raw = inp.visual[key][col]
                        vals[key] = float(raw) if raw != "" else None
                    pv = [vals[p["key"]] for p in pos if vals[p["key"]] is not None]
                    e = vals[("EMM", 1)]
                    sep = e is not None and min(pv) > e
                    w(f"    {col:<42} {fmt(e):>10} {fmt(vals[('CRM', 74)]):>10} {fmt(vals[('CRM', 77)]):>10} "
                      f"{fmt(min(pv)):>10} {str(sep):>5}")
    return case


# ==============================================================================
# Part B
# ==============================================================================

def part_b_population(inp: Inputs) -> list[dict[str, object]]:
    """B-P1。返回按 (doc_id, pdf_page) 排序的页面记录。"""
    pages: list[dict[str, object]] = []
    for key, r in sorted(inp.phase_a.items()):
        atr = r["alpha_token_ratio"]
        v1 = atr != "" and float(atr) <= 0.0
        n_chunks = int(r["corpus_chunk_count"])
        body = int(r["parser_body_chars"])
        if n_chunks > 0 and body >= contracts.CHUNK_MIN_CHARS and not v1:
            v = inp.visual[key]
            pages.append({
                "doc_id": key[0], "pdf_page": key[1], "source_filename": r["source_filename"],
                "parser_body_chars": body, "corpus_chunk_count": n_chunks, "v1_trigger": int(v1),
                "mid": float(v["d40_middle_nonwhite_ratio_245"]),
                "arow": float(v["d40_active_row_ratio_245_f0p01"]),
                "acol": float(v["d40_active_column_ratio_245_f0p01"]),
                "width": int(v["d40_width_px"]), "height": int(v["d40_height_px"]),
                "img": int(v["img_object_count"]),
            })
    if not pages:
        raise CensusError("Part B population 为空")
    return pages


def top_percent(pages: Sequence[dict[str, object]], field: str) -> set[tuple[str, int]]:
    """降序 top 10%（最近秩；并列全取）。"""
    k = max(1, math.ceil(len(pages) * TOP_PERCENT))
    ordered = sorted(pages, key=lambda p: (-float(p[field]), p["doc_id"], p["pdf_page"]))  # type: ignore[arg-type]
    cutoff = float(ordered[k - 1][field])  # type: ignore[arg-type]
    return {(str(p["doc_id"]), int(p["pdf_page"])) for p in pages if float(p[field]) >= cutoff}  # type: ignore[arg-type]


def prioritized_sets(pages: Sequence[dict[str, object]]) -> dict[str, set[tuple[str, int]]]:
    aspects = [float(p["width"]) / float(p["height"]) for p in pages]  # type: ignore[arg-type]
    areas = [float(p["width"]) * float(p["height"]) for p in pages]  # type: ignore[arg-type]
    med_a, med_area = pct(aspects, 50), pct(areas, 50)
    img_cut = pct([float(p["img"]) for p in pages], IMG_HEAVY_PERCENTILE)  # type: ignore[arg-type]
    p4, p5 = set(), set()
    for p in pages:
        key = (str(p["doc_id"]), int(p["pdf_page"]))
        aspect = float(p["width"]) / float(p["height"])  # type: ignore[arg-type]
        area = float(p["width"]) * float(p["height"])  # type: ignore[arg-type]
        if abs(aspect - med_a) / med_a > ASPECT_TOLERANCE or area > AREA_FACTOR * med_area:
            p4.add(key)
        if int(p["img"]) >= img_cut and int(p["img"]) >= 1:  # type: ignore[arg-type]
            p5.add(key)
    return {"P1": top_percent(pages, "mid"), "P2": top_percent(pages, "arow"),
            "P3": top_percent(pages, "acol"), "P4": p4, "P5": p5}


def select_candidates(pages: Sequence[dict[str, object]], sets: dict[str, set[tuple[str, int]]]) -> list[tuple[str, int]]:
    by_key = {(str(p["doc_id"]), int(p["pdf_page"])): p for p in pages}
    union = sorted(set().union(*sets.values()))
    if len(union) <= CANDIDATE_CAP:
        return union
    ranked = sorted(union, key=lambda k: (-sum(1 for s in sets.values() if k in s), -float(by_key[k]["mid"]), k[0], k[1]))  # type: ignore[arg-type]
    return sorted(ranked[:CANDIDATE_CAP])


def random_control(pages: Sequence[dict[str, object]], exclude: set[tuple[str, int]], seed: int) -> list[tuple[str, int]]:
    pool = sorted((str(p["doc_id"]), int(p["pdf_page"])) for p in pages
                  if (str(p["doc_id"]), int(p["pdf_page"])) not in exclude)
    if len(pool) <= RANDOM_CONTROL_N:
        return pool
    return sorted(random.Random(seed).sample(pool, RANDOM_CONTROL_N))


def review_set(inp: Inputs, pages: Sequence[dict[str, object]], seed: int) -> dict[str, object]:
    """B-P2/B-P3/B-P4/B-P5 的选取，全部为机械规则。返回各组与并集。"""
    sets = prioritized_sets(pages)
    cand = select_candidates(pages, sets)
    gold = sorted(inp.gold.keys())
    rnd = random_control(pages, set(cand), seed)
    pc = [POSITIVE_CONTROL]
    union = sorted(set(cand) | set(gold) | set(rnd) | set(pc))
    return {"sets": sets, "candidates": cand, "gold": gold, "random": rnd, "positive_control": pc, "union": union}


def page_record(inp: Inputs, key: tuple[str, int], sel: dict[str, object], pop_keys: set[tuple[str, int]],
                pdf_dir: str) -> dict[str, object]:
    """组装一页的完整记录（含 native text、corpus text、成员标记）。抛出 CensusError —— 该页不在 Phase A CSV。"""
    if key not in inp.phase_a:
        raise CensusError(f"页不在 Phase A CSV: {key}")
    pa, v = inp.phase_a[key], inp.visual[key]
    chunks = inp.chunks.get(key, [])
    atr = pa["alpha_token_ratio"]
    native = page_native_text(pdf_dir, pa["source_filename"], key[1])
    sets = sel["sets"]  # type: ignore[index]
    hits = sorted(name for name, s in sets.items() if key in s)  # type: ignore[union-attr]
    return {
        "doc_id": key[0], "pdf_page": key[1], "source_filename": pa["source_filename"],
        "chunk_ids": " ".join(str(c["id"]) for c in chunks),
        "parser_body_chars": int(pa["parser_body_chars"]), "corpus_chunk_count": len(chunks),
        "v1_trigger": int(atr != "" and float(atr) <= 0.0),
        "d40_middle_nonwhite_ratio_245": v["d40_middle_nonwhite_ratio_245"],
        "d40_active_row_ratio_245_f0p01": v["d40_active_row_ratio_245_f0p01"],
        "d40_active_column_ratio_245_f0p01": v["d40_active_column_ratio_245_f0p01"],
        "page_width": v["d40_width_px"], "page_height": v["d40_height_px"],
        "image_object_count": v["img_object_count"],
        "in_part_b_population": int(key in pop_keys),
        "is_prioritized_candidate": int(key in sel["candidates"]),  # type: ignore[operator]
        "prioritized_sets": "|".join(hits),
        "is_random_control": int(key in sel["random"]),  # type: ignore[operator]
        "is_gold_page": int(key in inp.gold),
        "gold_question_ids": " ".join(inp.gold.get(key, [])),
        "is_positive_control": int(key == POSITIVE_CONTROL),
        "native_text": native, "native_text_chars": len(native),
        "corpus_text": "\n".join(str(c["text"]) for c in chunks),
    }


def apply_reviews(records: Sequence[dict[str, object]]) -> None:
    """把 A2B_REVIEW_LABELS 贴到记录上并执行 B-P7 的证据检索。

    抛出 CensusError —— 标签缺失 / 非法 / MISSING 缺 example / example 在 native 或 corpus 中被找到却仍标 MISSING。
    """
    for r in records:
        key = (str(r["doc_id"]), int(r["pdf_page"]))
        if key not in A2B_REVIEW_LABELS:
            raise CensusError(f"缺 review 标签: {key}")
        label, dpi, observation, example = A2B_REVIEW_LABELS[key]
        if label not in REVIEW_LABELS:
            raise CensusError(f"非法标签 {label!r}: {key}")
        if label == LABEL_MISSING and not example:
            raise CensusError(f"{LABEL_MISSING} 缺 missing_content_example: {key}")
        found_native = found_corpus = ""
        if example:
            e = norm(example)
            found_native = "yes" if e in norm(str(r["native_text"])) else "no"
            found_corpus = "yes" if e in norm(str(r["corpus_text"])) else "no"
            if label == LABEL_MISSING and (found_native == "yes" or found_corpus == "yes"):
                raise CensusError(f"{key} 标为 {LABEL_MISSING}，但 example 在 native/corpus 中找到，标签与证据矛盾")
        r.update(review_label=label, review_dpi=dpi, visual_observation=observation,
                 missing_content_example=example, found_in_native=found_native, found_in_corpus=found_corpus,
                 reviewer=REVIEWER, label_source=LABEL_SOURCE)


def positive_control_check(inp: Inputs, pdf_dir: str) -> list[str]:
    """B-P5：独立复现 QMM p.110 的三个短语在本页 native text 与本页 corpus chunk 中的存在性。"""
    key = POSITIVE_CONTROL
    pa = inp.phase_a[key]
    native = norm(page_native_text(pdf_dir, pa["source_filename"], key[1]))
    corpus_page = norm("\n".join(str(c["text"]) for c in inp.chunks.get(key, [])))
    corpus_all = norm("\n".join(str(c["text"]) for cs in inp.chunks.values() for c in cs))
    lines = []
    for phrase in POSITIVE_CONTROL_PHRASES:
        p = norm(phrase)
        lines.append(f"    {phrase!r}: found_in_page_native={'yes' if p in native else 'no'} "
                     f"found_in_page_corpus={'yes' if p in corpus_page else 'no'} "
                     f"found_in_whole_corpus={'yes' if p in corpus_all else 'no'}")
    return lines


def write_csv(path: str, records: Sequence[dict[str, object]]) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        for r in sorted(records, key=lambda x: (str(x["doc_id"]), int(x["pdf_page"]))):
            writer.writerow(r)


def group_counts(records: Sequence[dict[str, object]], flag: str) -> str:
    grp = [r for r in records if r[flag]]
    c = Counter(str(r["review_label"]) for r in grp)
    return f"n={len(grp)} " + " ".join(f"{lab}={c.get(lab, 0)}" for lab in REVIEW_LABELS)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", choices=("parta", "select", "render", "analyze"), default="analyze")
    ap.add_argument("--pdf-dir", required=True)
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--testset", required=True)
    ap.add_argument("--phase-a-csv", required=True)
    ap.add_argument("--visual-csv", required=True)
    ap.add_argument("--a2-csv", required=True)
    ap.add_argument("--out-csv", required=True)
    ap.add_argument("--out-log", required=True)
    ap.add_argument("--work-dir", required=True)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = ap.parse_args(argv)

    t0 = time.perf_counter()
    inp = load_inputs(args)
    pages = part_b_population(inp)
    pop_keys = {(str(p["doc_id"]), int(p["pdf_page"])) for p in pages}
    sel = review_set(inp, pages, args.seed)
    os.makedirs(args.work_dir, exist_ok=True)

    if args.stage == "parta":
        out: list[str] = []
        part_a(inp, out)
        print("\n".join(out))
        return 0

    if args.stage in ("select", "render"):
        union: list[tuple[str, int]] = sel["union"]  # type: ignore[assignment]
        manifest = []
        for key in union:
            rec = page_record(inp, key, sel, pop_keys, args.pdf_dir)
            manifest.append({k: rec[k] for k in ("doc_id", "pdf_page", "source_filename", "chunk_ids",
                                                 "parser_body_chars", "corpus_chunk_count", "in_part_b_population",
                                                 "is_prioritized_candidate", "prioritized_sets", "is_random_control",
                                                 "is_gold_page", "gold_question_ids", "is_positive_control",
                                                 "native_text_chars")})
            if args.stage == "select":
                with open(os.path.join(args.work_dir, f"text_{key[0]}_p{key[1]:03d}.txt"), "w", encoding="utf-8") as h:
                    h.write(f"=== {key[0]} p{key[1]} native (pdftotext -layout) ===\n{rec['native_text']}\n")
                    h.write(f"=== corpus chunks ({rec['corpus_chunk_count']}) ===\n{rec['corpus_text']}\n")
            else:
                png_dir = os.path.join(args.work_dir, "png")
                os.makedirs(png_dir, exist_ok=True)
                render_png(args.pdf_dir, str(rec["source_filename"]), key[1], REVIEW_DPI,
                           os.path.join(png_dir, f"{key[0]}_p{key[1]:03d}_{REVIEW_DPI}dpi"))
        with open(os.path.join(args.work_dir, "manifest.json"), "w", encoding="utf-8") as h:
            json.dump(manifest, h, ensure_ascii=False, indent=1)
        print(f"stage={args.stage} union={len(union)} candidates={len(sel['candidates'])} "  # type: ignore[arg-type]
              f"gold={len(sel['gold'])} random={len(sel['random'])}")  # type: ignore[arg-type]
        return 0

    # ---- analyze ----
    out = ["OCR / page-usability Phase A.2b —— 收敛性诊断", "=" * 78, "§0 环境与冻结输入"]
    out += env_lines(args)
    out += ["", PREREGISTRATION, ""]
    case = part_a(inp, out)
    w = out.append

    union = sel["union"]  # type: ignore[assignment]
    records = [page_record(inp, key, sel, pop_keys, args.pdf_dir) for key in union]  # type: ignore[union-attr]
    apply_reviews(records)

    w("")
    w("§B Part B —— page_content_completeness（内容级对比，不是 ink proxy）")
    w(f"  B-P1 population N = {len(pages)}（corpus_chunk_count>0 且 parser_body_chars>={contracts.CHUNK_MIN_CHARS} 且 v1_trigger=false）")
    w(f"    按 doc: {json.dumps(dict(sorted(Counter(str(p['doc_id']) for p in pages).items())))}")
    sets = sel["sets"]  # type: ignore[assignment]
    w(f"  B-P3 各集合大小: " + " ".join(f"{k}={len(v)}" for k, v in sorted(sets.items())))  # type: ignore[union-attr]
    w(f"    union={len(set().union(*sets.values()))}（cap={CANDIDATE_CAP}）→ prioritized candidates={len(sel['candidates'])}")  # type: ignore[union-attr,arg-type]
    w("")
    w("  §B.1 GOLD_PAGE_REVIEW（最先执行）")
    gold_recs = [r for r in records if r["is_gold_page"]]
    w(f"    testset citation 记录数 = {sum(len(v) for v in inp.gold.values())}（question-page 对）；unique gold pages = {len(inp.gold)}")
    w(f"    标签分布: {group_counts(records, 'is_gold_page')}")
    w(f"    其中在 B-P1 population 内 = {sum(1 for r in gold_recs if r['in_part_b_population'])}")
    for r in sorted(gold_recs, key=lambda x: (str(x["doc_id"]), int(x["pdf_page"]))):
        w(f"    {r['doc_id']}:p{r['pdf_page']:<4} label={r['review_label']:<24} qids={r['gold_question_ids']:<28} "
          f"body={r['parser_body_chars']:<5} chunks={r['corpus_chunk_count']} obs={r['visual_observation']}")
    miss_gold = [r for r in gold_recs if r["review_label"] == LABEL_MISSING]
    w(f"    VISUAL_KNOWLEDGE_MISSING 的 gold pages = {len(miss_gold)}")
    for r in miss_gold:
        w(f"      {r['doc_id']}:p{r['pdf_page']} qids={r['gold_question_ids']} example={r['missing_content_example']!r} "
          f"found_in_native={r['found_in_native']} found_in_corpus={r['found_in_corpus']}")
    w("    ⚠️ 这是 citation page completeness，不是 question-level answer correctness。")

    w("")
    w("  §B.2 QMM p.110 positive control（本轮独立复现，不沿用 A.2 结论）")
    for line in positive_control_check(inp, args.pdf_dir):
        w(line)
    pc_rec = next(r for r in records if r["is_positive_control"])
    w(f"    本轮 review: label={pc_rec['review_label']} example={pc_rec['missing_content_example']!r} "
      f"found_in_native={pc_rec['found_in_native']} found_in_corpus={pc_rec['found_in_corpus']}")

    w("")
    w("  §B.3 sampling accounting（同一页只 review 一次，成员标记独立保留）")
    w(f"    prioritized raw N = {len(sel['candidates'])}")  # type: ignore[arg-type]
    w(f"    random raw N      = {len(sel['random'])}")  # type: ignore[arg-type]
    w(f"    gold raw unique N = {len(sel['gold'])}")  # type: ignore[arg-type]
    w(f"    positive-control  = {len(sel['positive_control'])}")  # type: ignore[arg-type]
    cand_s, gold_s, rnd_s = set(sel["candidates"]), set(sel["gold"]), set(sel["random"])  # type: ignore[arg-type]
    pc_s = set(sel["positive_control"])  # type: ignore[arg-type]
    w(f"    overlap prioritized∩gold={len(cand_s & gold_s)} prioritized∩random={len(cand_s & rnd_s)} "
      f"gold∩random={len(gold_s & rnd_s)} positive_control∩prioritized={len(pc_s & cand_s)} "
      f"positive_control∩gold={len(pc_s & gold_s)} positive_control∩random={len(pc_s & rnd_s)}")
    w(f"    unique reviewed N = {len(records)}")

    w("")
    w("  §B.4 分组结果（禁止合并成总体 prevalence）")
    w(f"    prioritized yield : {group_counts(records, 'is_prioritized_candidate')}")
    w(f"    random control    : {group_counts(records, 'is_random_control')}  ← exploratory estimate; not a production prevalence estimate")
    w(f"    gold pages        : {group_counts(records, 'is_gold_page')}")
    w(f"    全部 reviewed     : n={len(records)} " + " ".join(
        f"{lab}={sum(1 for r in records if r['review_label'] == lab)}" for lab in REVIEW_LABELS))

    w("")
    w("  §B.5 全部 VISUAL_KNOWLEDGE_MISSING 页（每页一个 missing business-content example + 证据检索）")
    miss = [r for r in records if r["review_label"] == LABEL_MISSING]
    w(f"    confirmed VISUAL_KNOWLEDGE_MISSING 去重页数 = {len(miss)}")
    for r in sorted(miss, key=lambda x: (str(x["doc_id"]), int(x["pdf_page"]))):
        w(f"    {r['doc_id']}:p{r['pdf_page']}  chunks={r['chunk_ids']} body={r['parser_body_chars']} "
          f"native_chars={r['native_text_chars']} groups=[{'P' if r['is_prioritized_candidate'] else ''}"
          f"{'R' if r['is_random_control'] else ''}{'G' if r['is_gold_page'] else ''}{'C' if r['is_positive_control'] else ''}]")
        w(f"      visual: {r['visual_observation']}")
        w(f"      missing_content_example: {r['missing_content_example']!r} → found_in_native={r['found_in_native']} "
          f"found_in_corpus={r['found_in_corpus']}")
        w(f"      native snippet: {' '.join(str(r['native_text']).split())[:160]!r}")
        w(f"      corpus snippet: {' '.join(str(r['corpus_text']).split())[:160]!r}")

    w("")
    w("  §B.6 边界")
    w("    禁止由本轮给出 corpus prevalence：prioritized 不是概率样本，random control n 很小，gold 是全量但只有 citation 页。")
    w("    V1 / V2 定义与状态本轮未改；Part B 与 V1 / V2 是三个不同的被测量对象，不合成单一 score。")
    w(f"    Part A 结论: {case}")

    write_csv(args.out_csv, records)
    w("")
    w(TIMING_MARKER)
    w(f"  total {time.perf_counter() - t0:.3f} s")
    with open(args.out_log, "w", encoding="utf-8") as handle:
        handle.write("\n".join(out) + "\n")
    print(f"reviewed={len(records)} missing={len(miss)} case={case}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
