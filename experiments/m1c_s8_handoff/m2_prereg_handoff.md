# M1c → M2 预注册 handoff：CD01

执行手册 S8.4 要求把 CD01 的观察写进 M2 预注册的「预期最可能结果」。正式 M2 预注册尚未创建（仓库中只有
`experiments/M2_preregistration_TEMPLATE.md`），因此先记录在此；**创建正式 M2 预注册时必须带入本条**。本文件不写任何 M2 结果。

## CD01 观察（来源：DECISIONS 2026-10-02 "S8 failure attribution result（human）" 与 "S8 reranker prerequisite real-window measurement"；
`experiments/m1c_s8_reranker/reranker_prerequisite.json` `4e035f85d9f3e376d3a420ca27aca0a3a52f6aba57cb2de1c881b8815f603d59`）

- formal gold（GoldChunkMap）：ERM:p105:0、ERM:p105:1、SMM:p73:0、SMM:p73:1、SMM:p74:0（5 块，跨 ERM / SMM 两份手册）。
- 检索归因：`NO_RETRIEVAL_FAILURE` —— 5 个 gold 在 BM25 / vector / hybrid 三路 top-20 内全部召回。
- 当前可执行打包契约（CONTEXT_PACK_BUDGET_TOKENS 765，TOP_K_CONTEXT 5）下的 realized k：BM25 / vector / hybrid = 2 / 2 / 2。
- packed gold coverage：1/5 / 1/5 / 1/5（三路都只装入 SMM:p73:1）。
- ERM 侧 gold（ERM:p105:0、ERM:p105:1）三路都未进入当前 packed context。

## 解释与边界

- 当前主要风险是 packing / context availability，不是 candidate retrieval miss。
- numeric token contract 尚未最终冻结；以上 packing 结果只代表当前可执行契约，不是最终 production claim。
  M2 预注册创建时应按届时冻结的契约重新核对，再写入「预期最可能结果」。
