"""Exact vector 检索器（components/retrievers/vector.py）的最小测试（prereg §15，D-V1–D-V10）。

只用合成 1024 维向量；query embedding 通过 mock 替换 vector.embed_texts（或 urlopen），不调用 Ollama、不读评测集、不算检索指标。
T13 的真实 artifact 子项在 experiments/m1c_s8_vector/ 生成后才执行（不在场则跳过）。

运行: python3 -m unittest tests.test_vector_retriever -v
"""

from __future__ import annotations

import ast
import json
import math
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import contracts
from core.contracts import Chunk, ContractViolation, RetrievalError, serialize_retrieval_record, validate_retrieval_records
from components.retrievers import vector
from components.retrievers.vector import VectorRetriever

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VECTOR_SOURCE = os.path.join(REPO_ROOT, "components", "retrievers", "vector.py")
ARTIFACT_META = os.path.join(REPO_ROOT, "experiments", "m1c_s8_vector", "corpus_embeddings.meta.json")
CORPUS_PATH = os.path.join(REPO_ROOT, "corpus", "chunks.jsonl")
DIM = 1024
REPEATS = 10


def read_text(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def basis(*pairs) -> list[float]:
    """1024 维向量: pairs = (index, value)，其余为 0.0。"""
    v = [0.0] * DIM
    for i, x in pairs:
        v[i] = float(x)
    return v


def chunk(cid: str) -> Chunk:
    return Chunk(id=cid, text=f"text {cid}", doc_id="D", doc_name="Synthetic", section="1", pdf_page=1)


# 合成语料（下标 = corpus_ordinal）: 3 与 4 向量相同（精确 tie），且 4 的 id 字典序更小。
IDS = ["D:p1:0", "D:p1:1", "D:p2:0", "D:p2:1", "C:p9:0", "D:p3:0"]
VECTORS = [
    basis((0, 1.0)),                       # 0: 与 query e0 同向 → cos 1
    basis((0, 1.0), (1, 1.0)),             # 1: cos 1/√2（非单位范数，检验显式 cosine）
    basis((1, 1.0)),                       # 2: 正交 → cos 0
    basis((0, -1.0), (1, 1.0)),            # 3: cos −1/√2
    basis((0, -1.0), (1, 1.0)),            # 4: 与 3 相同 → 精确 tie
    basis((0, -1.0)),                      # 5: 反向 → cos −1
]
QUERY = basis((0, 1.0))


def make_retriever(vectors=VECTORS, ids=IDS) -> VectorRetriever:
    return VectorRetriever([chunk(i) for i in ids], [list(v) for v in vectors])


def fake_embed(vectors_by_call):
    calls = []

    def _embed(texts):
        calls.append(list(texts))
        return [list(vectors_by_call) for _ in texts]
    return _embed, calls


class TestVectorRetriever(unittest.TestCase):

    def search(self, query="pump", k=contracts.TOP_K_RETRIEVE, qvec=QUERY, retriever=None):
        embed, calls = fake_embed(qvec)
        with mock.patch.object(vector, "embed_texts", embed):
            records = (retriever or make_retriever()).search_records(query, k)
        return records, calls

    def test_t01_empty_query_no_endpoint_call(self):
        records, calls = self.search(query="")
        self.assertEqual((records, calls), ([], []))

    def test_t02_whitespace_query_no_endpoint_call(self):
        for q in ("   ", "\n\t ", "　"):
            records, calls = self.search(query=q)
            self.assertEqual((records, calls), ([], []), repr(q))

    def test_t03_dimension_validation(self):
        with self.assertRaises(ContractViolation):
            make_retriever(vectors=[v[:DIM - 1] for v in VECTORS])
        with self.assertRaises(ContractViolation):
            make_retriever(vectors=VECTORS[:-1])                       # 数量不符
        with self.assertRaises(ContractViolation):
            make_retriever(vectors=[basis()] + VECTORS[1:])            # 零向量
        bad = [list(v) for v in VECTORS]
        bad[0][0] = math.nan
        with self.assertRaises(ContractViolation):
            make_retriever(vectors=bad)
        for payload in ({"embeddings": [basis((0, 1.0))[:-1]]}, {"embeddings": []}, {}, {"embeddings": [[math.inf] * DIM]}):
            with self.subTest(payload=str(payload)[:40]), self.assertRaises(RetrievalError):
                vector._validated_embeddings(payload, 1)

    def test_t04_exact_cosine_hand_fixture(self):
        a, b = basis((0, 3.0), (1, 4.0)), basis((0, 4.0), (1, 3.0))
        self.assertEqual(vector.exact_cosine(a, b, vector.vector_norm(a), vector.vector_norm(b)), 24 / 25)
        records, _ = self.search()
        by_ord = {r.corpus_ordinal: r.raw_score for r in records}
        self.assertEqual(by_ord[0], 1.0)
        self.assertTrue(math.isclose(by_ord[1], 1 / math.sqrt(2), rel_tol=1e-15))
        self.assertEqual(by_ord[2], 0.0)
        self.assertEqual(by_ord[5], -1.0)

    def test_t05_near_unit_vectors_still_explicit_cosine(self):
        scale = 1.0 + 6.4e-7                                             # 与 probe 实测的范数偏差同量级
        a = [x * scale for x in basis((0, 0.6), (1, 0.8))]
        b = basis((0, 0.8), (1, 0.6))
        cos = vector.exact_cosine(a, b, vector.vector_norm(a), vector.vector_norm(b))
        dot = math.fsum(x * y for x, y in zip(a, b))
        self.assertNotEqual(cos, dot)
        self.assertTrue(math.isclose(cos, 0.96, rel_tol=1e-15))
        source = read_text(VECTOR_SOURCE)
        self.assertIn("/ (norm_a * norm_b)", source)

    def test_t06_t07_t08_score_mapping_and_kinds(self):
        records, _ = self.search()
        for r in records:
            self.assertEqual(r.match_score, (r.raw_score + 1.0) / 2.0)        # T6
            self.assertEqual(r.relevance, r.match_score)                       # T7
            self.assertEqual((r.raw_score_kind, r.relevance_kind, r.match_score_kind),
                             ("cosine", "cosine_affine_01", "cosine_affine_01"))   # T8
        with mock.patch.object(vector, "_relevance", lambda raw: 0.5):        # 字段独立求值、排序不读 relevance
            records2, _ = self.search()
        self.assertEqual([r.corpus_ordinal for r in records2], [r.corpus_ordinal for r in records])
        self.assertTrue(all(r.match_score == (r.raw_score + 1.0) / 2.0 for r in records2))

    def test_t09_negative_cosine_returned(self):
        records, _ = self.search()
        self.assertEqual(len(records), len(IDS))                               # min(k, N)，不按正负过滤
        self.assertIn(5, [r.corpus_ordinal for r in records])
        self.assertEqual(records[-1].raw_score, -1.0)
        self.assertEqual(records[-1].match_score, 0.0)

    def test_t10_t11_order_and_exact_tie(self):
        records, _ = self.search()
        self.assertEqual([r.corpus_ordinal for r in records], [0, 1, 2, 3, 4, 5])
        raws = [r.raw_score for r in records]
        self.assertEqual(raws, sorted(raws, reverse=True))                     # T10
        self.assertEqual(records[3].raw_score, records[4].raw_score)            # T11: 精确 tie
        self.assertLess(records[4].chunk_id, records[3].chunk_id)               # 若按 chunk_id 打破 tie，顺序会反
        validate_retrieval_records(records, k=contracts.TOP_K_RETRIEVE, corpus_chunk_ids=IDS)

    def test_t12_k_behavior(self):
        self.assertEqual([r.corpus_ordinal for r in self.search(k=1)[0]], [0])
        self.assertEqual(len(self.search(k=100)[0]), len(IDS))
        for bad in (0, -1, True, 2.0, None):
            with self.subTest(k=bad), self.assertRaises(ContractViolation):
                self.search(k=bad)
        with self.assertRaises(ContractViolation):
            self.search(query=None)

    def test_t13_corpus_ordinal_alignment_synthetic(self):
        records, _ = self.search()
        for r in records:
            self.assertEqual(IDS[r.corpus_ordinal], r.chunk_id)

    @unittest.skipUnless(os.path.isfile(ARTIFACT_META), "corpus embedding artifact 尚未生成")
    def test_t13_corpus_embedding_artifact_alignment(self):
        meta = json.loads(read_text(ARTIFACT_META))
        ids = [json.loads(line)["id"] for line in read_text(CORPUS_PATH).splitlines()]
        import hashlib
        self.assertEqual(meta["rows"], len(ids))
        self.assertEqual(meta["dimension"], DIM)
        self.assertEqual(meta["chunk_ids_sha256"], hashlib.sha256("\n".join(ids).encode("utf-8")).hexdigest())

    def test_t14_query_embedding_request_protocol(self):
        self.assertEqual(vector.build_embed_request(["q"]), {"model": "bge-m3:latest", "input": ["q"], "truncate": False})
        self.assertNotIn("options", vector.build_embed_request(["q"]))         # 默认 Metal：无 num_gpu 覆盖
        self.assertEqual((vector.QUERY_PREFIX, vector.DOCUMENT_PREFIX), ("", ""))
        _, calls = self.search(query="Fire pump?")
        self.assertEqual(calls, [["Fire pump?"]])                              # 无 prefix、原样字符串
        captured = {}

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return json.dumps({"embeddings": [QUERY]}).encode()

        def _urlopen(req, timeout):
            captured["url"], captured["body"] = req.full_url, json.loads(req.data)
            return _Resp()
        with mock.patch.object(vector.urllib.request, "urlopen", _urlopen):
            vector.embed_texts(["Fire pump?"])
        self.assertEqual(captured["url"], "http://localhost:11434/api/embed")
        self.assertEqual(captured["body"], {"model": "bge-m3:latest", "input": ["Fire pump?"], "truncate": False})

    def test_t15_no_eval_or_gold_dependency(self):
        tree = ast.parse(read_text(VECTOR_SOURCE))
        imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names} | \
                   {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        self.assertEqual(imported, {"__future__", "json", "math", "urllib.error", "urllib.request", "typing", "core.contracts"})
        names = {n.id.lower() for n in ast.walk(tree) if isinstance(n, ast.Name)} | \
                {n.attr.lower() for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        for word in ("gold", "testset", "citation", "expected", "question", "recall", "open"):
            self.assertFalse([x for x in names if word == x or x.startswith(word + "_")], word)
        import inspect
        self.assertEqual(list(inspect.signature(VectorRetriever.__init__).parameters), ["self", "chunks", "corpus_vectors"])
        self.assertEqual(list(inspect.signature(VectorRetriever.search_records).parameters), ["self", "query", "k"])

    def test_t16_deterministic_synthetic_result(self):
        r = make_retriever()
        first = None
        for _ in range(REPEATS):
            records, _ = self.search(retriever=r)
            out = "\n".join(serialize_retrieval_record(x) for x in records)
            first = first or out
            self.assertEqual(out, first)
        hits_embed, _ = fake_embed(QUERY)
        with mock.patch.object(vector, "embed_texts", hits_embed):
            hits = r.search("pump")
        self.assertEqual([(h.chunk.id, h.relevance, h.match_score, h.origin) for h in hits],
                         [(x.chunk_id, x.relevance, x.match_score, "vector") for x in self.search(retriever=r)[0]])


if __name__ == "__main__":
    unittest.main()
