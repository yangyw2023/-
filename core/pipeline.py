"""组装层：读配置 → 按 registry 实例化各组件 → 串成一条问答流程。

本模块是整个项目里唯一允许同时 import 多个 components 子包的地方；
组件之间互不 import，靠这里组装（见 DECISIONS.md 的依赖树铁律）。

当前为占位 stub，尚未实现。
"""


def build_pipeline():
    """按配置组装一条完整问答流程并返回。

    契约（待 core/contracts.py 定稿后固化）：
        - 参数签名、返回类型均未定，因为它们必须由 contracts.py 定义，
          而 contracts.py 尚未贴入。在此之前不要为本函数写调用方。

    Raises:
        NotImplementedError: 无条件抛出。本函数目前没有任何实现，
            调用它是调用方的错误，不是"暂时没有结果"。
    """
    raise NotImplementedError("core.pipeline.build_pipeline 尚未实现")
