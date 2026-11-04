"""Pydantic 请求/响应模型层：只定义数据形状与校验规则，不含业务逻辑。

按接口分组：chat（问答与会话）、document（文档）、common（统一外壳）
"""

from app.schemas.common import ApiResponse, success  # noqa: F401
