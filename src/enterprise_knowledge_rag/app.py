import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from enterprise_knowledge_rag.config import Settings, get_settings
from enterprise_knowledge_rag.models import (
    ChatRequest,
    ChatResult,
    UserContext,
    UserRole,
)
from enterprise_knowledge_rag.tracing import TraceEvent
from enterprise_knowledge_rag.workflow import WorkflowRun


class ChatApiService(Protocol):
    def ready(self) -> bool: ...

    def run(self, request: ChatRequest, user: UserContext) -> WorkflowRun: ...

    def clear_session(self, user: UserContext, session_id: str | None) -> None: ...

    def documents_overview(self, user: UserContext) -> list[dict[str, Any]]: ...

    def index_documents(self, user: UserContext) -> dict[str, Any]: ...

    def latest_evaluation(self) -> dict[str, Any]: ...


class SessionResolver(Protocol):
    def resolve(self, request: Request) -> UserContext: ...


class ConfiguredSessionResolver:
    """Demo identity comes from server settings, never from the request body."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def resolve(self, request: Request) -> UserContext:
        del request
        return UserContext(
            user_id=self._settings.demo_user_id,
            role=UserRole(self._settings.demo_role),
            departments={
                item.strip()
                for item in self._settings.demo_departments.split(",")
                if item.strip()
            },
        )


STAGE_LABELS = {
    "domain": "判断问题范围",
    "rewrite": "整理查询条件",
    "retrieve": "检索企业知识",
    "evidence": "构建引用依据",
    "generate": "生成并校验回答",
    "finalize": "完成",
    "refusal": "返回边界说明",
}


def _sse(event: str, payload: dict[str, Any]) -> str:
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {data}\n\n"


def _public_progress(trace: Sequence[TraceEvent]):
    for item in trace:
        yield _sse(
            "progress",
            {
                "stage": item.component,
                "label": STAGE_LABELS.get(item.component, "处理中"),
                "status": item.status,
            },
        )


def create_app(
    service: ChatApiService,
    *,
    settings: Settings | None = None,
    session_resolver: SessionResolver | None = None,
    lifespan: Any | None = None,
    static_dir: Path | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    resolver = session_resolver or ConfiguredSessionResolver(settings)
    app = FastAPI(
        title="企业制度与流程知识库助手 API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            origin.strip()
            for origin in settings.allowed_origins.split(",")
            if origin.strip()
        ],
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization"],
    )

    @app.middleware("http")
    async def enforce_request_size(request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > settings.request_max_bytes:
            return Response(
                "请求内容过大",
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            )
        return await call_next(request)

    def current_user(request: Request) -> UserContext:
        return resolver.resolve(request)

    def require_admin(user: UserContext = Depends(current_user)) -> UserContext:
        if user.role is not UserRole.KNOWLEDGE_ADMIN:
            raise HTTPException(status_code=403, detail="当前账号无管理权限")
        return user

    def safe_run(chat_request: ChatRequest, user: UserContext) -> WorkflowRun:
        try:
            return service.run(chat_request, user)
        except Exception as exc:
            if settings.app_env == "test":
                raise
            raise HTTPException(
                status_code=503,
                detail="知识服务暂时不可用，请稍后重试。",
            ) from exc

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    def ready() -> dict[str, str]:
        if not service.ready():
            raise HTTPException(status_code=503, detail="知识库尚未准备完成")
        return {"status": "ready"}

    @app.get("/session")
    def session(user: UserContext = Depends(current_user)) -> dict[str, Any]:
        return {
            "user_id": user.user_id,
            "role": user.role.value,
            "departments": sorted(user.departments),
            "public_demo_mode": settings.public_demo_mode,
        }

    @app.post("/chat", response_model=ChatResult)
    def chat(
        chat_request: ChatRequest,
        user: UserContext = Depends(current_user),
    ) -> ChatResult:
        return safe_run(chat_request, user).result

    @app.post("/chat/stream")
    def chat_stream(
        chat_request: ChatRequest,
        user: UserContext = Depends(current_user),
    ) -> StreamingResponse:
        run = safe_run(chat_request, user)

        def events():
            yield from _public_progress(run.trace)
            yield _sse("result", run.result.model_dump(mode="json"))

        return StreamingResponse(events(), media_type="text/event-stream")

    @app.post("/chat/clear", status_code=204)
    def clear_chat(
        chat_request: ChatRequest,
        user: UserContext = Depends(current_user),
    ) -> Response:
        service.clear_session(user, chat_request.session_id)
        return Response(status_code=204)

    @app.get("/documents")
    def documents(user: UserContext = Depends(current_user)) -> list[dict[str, Any]]:
        return service.documents_overview(user)

    @app.post("/documents/index")
    def index_documents(
        user: UserContext = Depends(require_admin),
    ) -> dict[str, Any]:
        return service.index_documents(user)

    @app.get("/evaluations/latest")
    def latest_evaluation() -> dict[str, Any]:
        return service.latest_evaluation()

    if static_dir is not None and (static_dir / "index.html").is_file():
        app.mount(
            "/",
            StaticFiles(directory=static_dir, html=True),
            name="frontend",
        )

    return app
