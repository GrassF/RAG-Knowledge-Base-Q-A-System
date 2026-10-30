"""问答接口与会话管理。"""

from __future__ import annotations

from fastapi import APIRouter, Path
from fastapi.responses import StreamingResponse

from app.api.deps import CurrentUser, DbSession, RagService
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
def chat_stream(payload: ChatRequest, user: CurrentUser, rag: RagService) -> StreamingResponse:
    user_id = user.id  # 先把值取出来，避免请求级数据库会话关闭后再访问 ORM 对象
    service = ChatService(rag)
    return StreamingResponse(
        service.stream_chat(user_id, payload),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.get(
    "/conversations",
    response_model=ApiResponse[list[ConversationOut]],
    summary="当前用户的会话列表",
)
def list_conversations(user: CurrentUser, db: DbSession) -> dict:
    return success(ConversationService(db).list_for_user(user.id))


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=ApiResponse[ConversationDetail],
    summary="会话历史消息（含引用来源）",
)
def list_messages(
    user: CurrentUser,
    db: DbSession,
    conversation_id: str = Path(min_length=8, max_length=40),
) -> dict:
    service = ConversationService(db)
    conversation = service.get_owned(conversation_id, user.id)
    detail = ConversationDetail(
        conversation=ConversationOut(
            id=conversation.id,
            title=conversation.title,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        ),
        messages=service.list_messages(conversation_id, user.id),
    )
    return success(detail)


@router.patch(
    "/conversations/{conversation_id}",
    response_model=ApiResponse[ConversationOut],
    summary="重命名会话",
)
def rename_conversation(
    payload: RenameRequest,
    user: CurrentUser,
    db: DbSession,
    conversation_id: str = Path(min_length=8, max_length=40),
) -> dict:
    return success(ConversationService(db).rename(conversation_id, user.id, payload.title))


@router.delete(
    "/conversations/{conversation_id}",
    response_model=ApiResponse[dict | None],
    summary="删除会话",
)
def delete_conversation(
    user: CurrentUser,
    db: DbSession,
    conversation_id: str = Path(min_length=8, max_length=40),
) -> dict:
    ConversationService(db).delete(conversation_id, user.id)
    return success(None, message="会话已删除")