"""S8 失败归因：把人工标签写入审核包 CSV 的两列人工字段（human_failure_tag / human_failure_note）。

契约：
  - 只改 13 行的两列人工字段；其余 24 列、列顺序、行顺序、换行符与写法（csv.DictWriter，lineterminator="\\n"，UTF-8）不变。
  - 前置：CSV 的 sha256 必须等于生成时的冻结值（全部人工字段仍为 PENDING_HUMAN / ""），否则 PacketIdentityError；
    因此本脚本对同一文件只能成功执行一次，不会覆盖已录入的结果。
  - 写文件前必须全部通过（任一不过 → LabelCheckError，不写任何文件）：
      a. 标签 qid 集合与 CSV 的 13 个 qid 一一对应，无重复；
      b. R1–R3：tag 取值合法；任一路 *_top20_candidate_miss == "True" 的行必须用五个 S8 标签之一，否则必须是 NO_RETRIEVAL_FAILURE；
      c. round-trip：把两列还原为 PENDING_HUMAN / "" 后按同样写法序列化，与原文件逐字节相同。
  - 不读聊天、不联网、不调用模型。成功后打印新 CSV 的 sha256 与各标签计数（JSON）。

用法: python3 experiments/m1c_s8_attribution/apply_human_labels.py
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from collections import Counter

PACKET_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "failure_attribution_packet.csv")
PACKET_SHA256_BEFORE = "c1a033978447b787f9e6c9140371a98c6acbdf4b3a8a0c68670a7be1b5e9fc34"
TAG_FIELD, NOTE_FIELD = "human_failure_tag", "human_failure_note"
PENDING_TAG, PENDING_NOTE = "PENDING_HUMAN", ""
ROUTES = ("bm25", "vector", "hybrid")
MISS_TRUE = "True"
S8_TAGS = frozenset({"parse_failure", "chunk_boundary", "bm25_miss", "vector_miss", "fusion_miss"})
NO_FAILURE = "NO_RETRIEVAL_FAILURE"
LINE_TERMINATOR = "\n"

# 人工标签（Arya 审阅采纳）。每行一题：qid / tag / note。
LABELS_JSONL = r'''
{"qid": "FL08", "tag": "NO_RETRIEVAL_FAILURE", "note": "无检索失败。BM25@1、hybrid@2、vector@7。vector@1 与 hybrid@1 都是非 gold 的 QMM:p83:2：原页是 §12.6 审核员资格矩阵，'Training – ISM/ISPS/MLC Internal Audit - 5 yearly' 一行对内审员打勾，与答案一致，属 GoldChunkMap 可能漏收的有效证据（矩阵列标题在上一块 QMM:p83:1；map 冻结不改）。"}
{"qid": "FL14", "tag": "vector_miss", "note": "vector top-20 无 gold；BM25@5、hybrid@13（只有 BM25 一路命中，被 RRF 压后）。gold SMM:p15:3 是 §1 两栏术语表中的 7 行（High Voltage…Interested Parties）；解析把左栏术语插进右栏句中（'referred Inert Gas to as'），但答案句和 'less than 5% by volume' 完整、未跨块，故不记 parse_failure / chunk_boundary（R4：上游原因未被证明足以解释）。vector top-5 全是 §2.16 gas freeing / purging / enclosed space 块，本身就在讲惰性气体与含氧量。原因假设（未验证）：多条定义同块稀释向量、术语错位、§2.16 强竞争。M5 可单独嵌入 Inert Gas 一行检验；修法候选是术语表按条目切分。"}
{"qid": "CN02", "tag": "NO_RETRIEVAL_FAILURE", "note": "无检索失败。vector@1、hybrid@3、BM25@7。BM25 前 3 是 QMM 目录（p1:0）、1.8 Management System（p14:0）、14.1 Safety and Environmental Management Planning（p97:0），靠 safety / management / system 等泛化词得分；gold 有区分度的共享词只有 risk / assessment。"}
{"qid": "CN03", "tag": "NO_RETRIEVAL_FAILURE", "note": "无检索失败（按任一 gold 命中）。两项 required 都在 ERM:p14:0（BM25@2、vector@1、hybrid@1）。第二个 gold QMM:p46:1 三路 top-20 都没有：它是 DPA 职责清单，只支撑 acceptable（lead role in ERT），块内没有 'DPA'，主语在上一块 QMM:p46:0（引导语与清单分块）。citation 取 AND 还是 OR 属 prereg §8.2 未决的标注问题；若取 AND，这一块构成三路漏召回。"}
{"qid": "CN04", "tag": "NO_RETRIEVAL_FAILURE", "note": "无检索失败。vector@1、hybrid@4、BM25@9。gold 与 query 只共享 toolbox / meeting 和虚词，不含 purpose / before / job；BM25@1 的 SMM:p43:1（'Before resuming work… job site'）靠 before / job / work 得分。"}
{"qid": "PR01", "tag": "NO_RETRIEVAL_FAILURE", "note": "无检索失败。10 项 required 全在 ERM:p103:1（BM25@19、vector@4、hybrid@4）。三路 @1 都是非 gold 的 ERM:p103:0，即这份清单的引导句（'In the event of man overboard… the following'）：与 PR03 / PR04 同类的引导语与清单分块，此处未造成漏召回。ERM:p103:2 只支撑 acceptable：BM25 与 hybrid top-20 都没有，vector@12。"}
{"qid": "PR03", "tag": "chunk_boundary", "note": "BM25 top-20 无 gold；vector@4/5、hybrid@9/11。原页 CMM p.74 是一个完整单元：引导段（'…In absence of Flag state grievance procedure, following procedure will apply:'）加 1–10 步，被切成 p74:0（引导段）、p74:1（1–6 步）、p74:2（7–10 步）。query 的 grievance / procedure 只出现在引导段；BM25 找到了引导块 CMM:p74:0（@6），没找到答案块。反事实：只把引导段移入 p74:1，BM25 即可召回 p74:1（数值见 DECISIONS 本条）。次要因素：步骤正文用 complaint / refer / lodge，与 query 的 grievance / raise / escalate 是同义改写，加词干也无法匹配。"}
{"qid": "PR04", "tag": "chunk_boundary", "note": "BM25 top-20 无 gold；vector@2、hybrid@10。原页 SMM p.35：引导句 'All permits to be correctly numbered for type of permit as per below convention:' 紧贴在表格上方，是这张表的标题；切块把它留在 p35:0，表格单独成为 p35:1。表格块里没有 query 的 permit（只有 Permits）和 convention，这两个词引导句里都有；表格块与 query 只共享 jobs / to / work；BM25 找到了引导块 SMM:p35:0（@1），没找到表格块。反事实：只把引导句移回表格块，BM25 即可召回（数值见 DECISIONS 本条）。原页表格只有一列 10 个作业名、没有编号列，解析未丢内容。次要因素：analyzer 无词干（permit / permits、require / requiring、numbering / numbered）。"}
{"qid": "CD01", "tag": "NO_RETRIEVAL_FAILURE", "note": "无检索失败：5 个 gold 三路 top-20 全在。hybrid：SMM:p73:1@1（validity ≤ 8 h、Checklist S-14）、ERM:p105:0@4（first action: raise the alarm）、SMM:p73:0@6、SMM:p74:0@7、ERM:p105:1@8（do not attempt rescue alone；rescue team with BA）。4 项 required 中 ERM 侧两项最早分别在 hybrid@4 与 @8。按当前可执行打包契约（765），BM25 实测 realized k 中位为 2，ERM 一半可能进不了 context，与执行手册'可能结构性不可答'的预测一致（描述性；packing 结论待数值契约冻结，不属本标签）。"}
{"qid": "CD03", "tag": "NO_RETRIEVAL_FAILURE", "note": "无检索失败。FMM:p38:2（RA + MOC + Office approval；24 h in advance）BM25@8、vector@2、hybrid@4；SMM:p35:2（Master is the approving authority for all PTWs）BM25@12、vector@8、hybrid@7。三路 @1 都是非 gold 的 SMM:p29:0（critical task 风险评估表）。"}
{"qid": "ML01", "tag": "bm25_miss", "note": "结构性（prereg §8.3 DERIVED）：中文 query 被 analyzer 切成 2 个汉字长串 token，英文语料不可能有相同 token，BM25 返回 0 条；这只说明 analyzer 的限制，不说明中文问题检索不到证据。vector@2、hybrid@2（BM25 为空，hybrid 顺序即 vector 顺序）；同一事实的英文题 FL01 为 vector@1。@1 的 CMM:p123:1 是附录 VI '大副晋升船长' 流程图的终点框（'For Promotion, ≥5 days handover period with 1 voyage double up'），与答案一致，属 GoldChunkMap 可能漏收的有效证据；但图标题 'In-house promotion (CO to Master)' 在上一块 p123:0，单看 p123:1 与 @3 的 p124:1（2E→C/E 流程图，testset known_distractor）几乎同文，生成阶段有混淆风险。"}
{"qid": "ML02", "tag": "bm25_miss", "note": "跨语言（tl），但与 gold 有部分共享（at / drug / test），不属 prereg §8.3 意义的结构性限制。词面原因：analyzer 无词干（gold 写 Testing / Tankers，query 是 test / tanker）；tl 虚词 'sa' 在 query 中出现 3 次，casefold 后与语料缩写 'SA'（Salvage Association）相同，BM25 按多重集计分，前 3 全是含 'SA Surveyor' 的 ERM 矩阵表块（p40:1、p130:2、p39:2）。vector@1/2；hybrid gold 降到 @4/@6（两路都弱命中的 QMM:p32:3 / p32:5 占 1/2，BM25 噪声 ERM:p40:1 占 3）。生成风险：答案行（3）在 QMM:p33:2 中单元格交错（'6 Months and at • Not Required. Testing By random'），且 For Tankers / For Dry Vessels 表头在另一块 QMM:p33:0。"}
{"qid": "ML03", "tag": "NO_RETRIEVAL_FAILURE", "note": "无检索失败。BM25@4 只靠 query 中唯一的拉丁 token 'dpa' 命中（脆弱）；vector@2、hybrid@1。vector@1 的 ERM:p21:0（'1st Step: Call DPA within 30 mins of incident'，适用于所有紧急情况）与答案一致，属 GoldChunkMap 可能漏收的有效证据。"}
'''


class PacketIdentityError(RuntimeError):
    """CSV 不是生成时的冻结版本。"""


class LabelCheckError(RuntimeError):
    """标签未通过 a / b / c 检查。"""


def _serialize(fieldnames: list[str], rows: list[dict[str, str]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator=LINE_TERMINATOR)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _load_labels() -> dict[str, dict[str, str]]:
    labels: dict[str, dict[str, str]] = {}
    for line in LABELS_JSONL.strip().splitlines():
        item = json.loads(line)
        if item["qid"] in labels:
            raise LabelCheckError(f"a. 标签 qid 重复: {item['qid']}")
        labels[item["qid"]] = {"tag": item["tag"], "note": item["note"]}
    return labels


def main() -> None:
    with open(PACKET_PATH, "rb") as handle:
        original = handle.read()
    actual_sha = hashlib.sha256(original).hexdigest()
    if actual_sha != PACKET_SHA256_BEFORE:
        raise PacketIdentityError(f"packet CSV sha256 {actual_sha} != 冻结值 {PACKET_SHA256_BEFORE}（可能已录入过）")
    reader = csv.DictReader(io.StringIO(original.decode("utf-8")))
    fieldnames = list(reader.fieldnames or [])
    rows = list(reader)
    labels = _load_labels()

    qids = [row["question_id"] for row in rows]
    if len(set(qids)) != len(qids) or set(qids) != set(labels):
        raise LabelCheckError(f"a. qid 不一一对应: CSV={sorted(qids)} labels={sorted(labels)}")

    for row in rows:
        tag = labels[row["question_id"]]["tag"]
        missed = any(row[f"{route}_top20_candidate_miss"] == MISS_TRUE for route in ROUTES)
        if tag not in S8_TAGS | {NO_FAILURE}:
            raise LabelCheckError(f"b. R1 取值非法: {row['question_id']} = {tag}")
        if missed and tag not in S8_TAGS:
            raise LabelCheckError(f"b. R3 有 top-20 漏召回却未用 S8 标签: {row['question_id']} = {tag}")
        if not missed and tag != NO_FAILURE:
            raise LabelCheckError(f"b. R3 无漏召回却未用 {NO_FAILURE}: {row['question_id']} = {tag}")

    labelled = [dict(row, **{TAG_FIELD: labels[row["question_id"]]["tag"], NOTE_FIELD: labels[row["question_id"]]["note"]})
                for row in rows]
    new_bytes = _serialize(fieldnames, labelled)
    restored = [dict(row, **{TAG_FIELD: PENDING_TAG, NOTE_FIELD: PENDING_NOTE})
                for row in csv.DictReader(io.StringIO(new_bytes.decode("utf-8")))]
    if _serialize(fieldnames, restored) != original:
        raise LabelCheckError("c. round-trip 不一致：除两列人工字段外有内容被改动")

    with open(PACKET_PATH, "wb") as handle:
        handle.write(new_bytes)
    print(json.dumps({"packet_csv_sha256": hashlib.sha256(new_bytes).hexdigest(),
                      "tag_counts": dict(sorted(Counter(row[TAG_FIELD] for row in labelled).items())),
                      "checks": {"a_qid_bijection": "PASS", "b_R1_R3": "PASS", "c_round_trip": "PASS"}},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
