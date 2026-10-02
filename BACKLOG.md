# BACKLOG

这一版明确不做、但需要保留的后续事项。
加入 BACKLOG 表示“已识别且当前不做”，不得顺手混入当前范围。

## M5 · 安全验证与迭代优化

- 扩充陷阱题至 ≥15 道。
  当前实际计分陷阱仅 7 道，M2 只能按个案定性呈现，不能对子类型报告稳定比例。

- 建独立拒答校准集。
  用于正式校准 MIN_RELEVANCE；M2 只使用 provisional threshold，并量化同集校准的乐观偏差。

- 比较 prefix packing 与 skip-and-fill / knapsack packing。
  M1c/M2 基线锁定 prefix，避免引入对短 chunk 的隐性偏好。

- 人工抽检 ≥200 个 chunk。
  当前解析统计已通过，但人工内容质量抽检仍不足。

- 真正的多语种能力评估。
  当前 zh / tl / hi 各 1 题，只够冒烟，不足以形成结构性结论。

- 若 C 臂表现好，建立“训练时排除 source chunk”的独立泛化集。
  用于区分微调真正泛化与记忆训练语料。

## M6 · 船端工程优化

- 评估 prompt cache。
  固定 system prompt / instruction 前缀存在缓存机会；待真实船端 runtime 与硬件确定后实测。