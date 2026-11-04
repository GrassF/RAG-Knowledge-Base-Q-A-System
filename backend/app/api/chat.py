"""问答与会话接口：SSE 流式问答 + 会话的查/改/删。

位置：HTTP 入口 → ChatService（生成）→ ConversationService（落库）
接口：POST /chat/stream（SSE）、GET /conversations、GET /conversations/{id}、
      PATCH /conversations/{id}、DELETE /conversations/{id}
要点：SSE 事件顺序为 meta → sources → delta* → done
"""

from __future__ import annotations

from fastapi import APIRouter, Path
from fastapi.responses import StreamingResponse

from app.api.deps import DbSession, RagService
from app.schemas.chat import (
    ChatRequest,
    ConversationDetail,
    ConversationOut,
    RenameRequest,
)
from app.schemas.common import ApiResponse, success
from app.services.chat_service import ChatService
from app.services.conversation import ConversationService

router = APIRouter(prefix="/chat", tags=["问答"])

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    # 关闭 Nginx 缓冲，否则流式会被攒成一坨再返回
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}


@router.post(
    "/stream",
    summary="流式问答（SSE）",
    response_class=StreamingResponse,
    responses={
        200: {
            "content": {"text/event-stream": {}},
            "description": (
                "SSE 事件流：meta -> sources -> delta(多次) -> done，"
                "任意阶段出错则发 error 事件"
            ),
        }
    },
)
def chat_stream(payload: ChatRequest, rag: RagService) -> StreamingResponse:
    service = ChatService(rag)
    return StreamingResponse(
        service.stream_chat(payload),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.get(
    "/conversations",
    response_model=ApiResponse[list[ConversationOut]],
    summary="会话列表",
)
def list_conversations(db: DbSession) -> dict:
    return success(ConversationService(db).list_all())


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=ApiResponse[ConversationDetail],
    summary="会话历史消息（含引用来源）",
)
def list_messages(
    db: DbSession,
    conversation_id: str = Path(min_length=8, max_length=40),
) -> dict:
    service = ConversationService(db)
    conversation = service.get(conversation_id)
    detail = ConversationDetail(
        conversation=ConversationOut(
            id=conversation.id,
            title=conversation.title,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        ),
        messages=service.list_messages(conversation_id),
    )
    return success(detail)


@router.patch(  # 注册 PATCH 接口：局部更新，只改请求里传的字段
    "/conversations/{conversation_id}",  # 路径参数，拼成 /api/v1/chat/conversations/{conversation_id}
    response_model=ApiResponse[ConversationOut],  # 响应结构：data 部分是 ConversationOut
    summary="重命名会话",  # 接口摘要，显示在 /docs 列表
)
def rename_conversation(  # 处理函数：只修改会话标题
    payload: RenameRequest,  # 请求体：内部只有 title 字段
    db: DbSession,  # 依赖注入：请求级数据库会话，结束后自动关闭
    conversation_id: str = Path(min_length=8, max_length=40),  # 路径参数：长度 8~40 校验
) -> dict:  # 返回统一响应字典
    service = ConversationService(db)  # 用请求级会话构造会话服务
    result = service.rename(conversation_id, payload.title)  # 改标题（超长截断 128）
    db.commit()  # 提交事务，否则请求结束时会话关闭会回滚
    return success(result)  # 包装成 {code, message, data, request_id}


@router.delete(  # 注册 DELETE 接口：删除整个会话
    "/conversations/{conversation_id}",  # 路径参数，指向某个具体会话
    response_model=ApiResponse[dict | None],  # 响应结构：成功时 data 为 null
    summary="删除会话",  # 接口摘要，显示在 /docs 列表
)
def delete_conversation(  # 处理函数：删会话及其下所有消息
    db: DbSession,  # 依赖注入：请求级数据库会话，结束后自动关闭
    conversation_id: str = Path(min_length=8, max_length=40),  # 路径参数：长度 8~40 校验
) -> dict:  # 返回统一响应字典
    ConversationService(db).delete(conversation_id)  # 删除；外键 CASCADE 一并删掉消息
    db.commit()  # 提交事务，否则请求结束时会话关闭会回滚
    return success(None, message="会话已删除")  # data 为 null，只带提示与 request_id