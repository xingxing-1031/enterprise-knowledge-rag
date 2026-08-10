import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from enterprise_knowledge_rag.config import Settings, get_settings
from enterprise_knowledge_rag.documents.ingestion import (
    ImportNotApprovableError,
    ImportNotFoundError,
)
from enterprise_knowledge_rag.documents.source_models import (
    ImportMetadata,
    ImportPreview,
    SourceFile,
)
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

    def preview_import(
        self,
        source: SourceFile,
        metadata: ImportMetadata,
        user: UserContext,
    ) -> ImportPreview: ...

    def list_imports(self, user: UserContext) -> list[ImportPreview]: ...

    def get_import(self, import_id: str, user: UserContext) -> ImportPreview | None: ...

    def approve_import(
        self,
        import_id: str,
        metadata: ImportMetadata,
        user: UserContext,
    ) -> ImportPreview: ...


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
        is_import_upload = (
            request.method == "POST" and request.url.path == "/knowledge/imports"
        )
        if (
            not is_import_upload
            and content_length
            and int(content_length) > settings.request_max_bytes
        ):
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

    @app.post(
        "/knowledge/imports",
        response_model=ImportPreview,
        status_code=status.HTTP_201_CREATED,
    )
    async def upload_knowledge_document(
        file: UploadFile = File(...),
        metadata: str = Form(...),
        user: UserContext = Depends(require_admin),
    ) -> ImportPreview:
        from pydantic import ValidationError

        try:
            import_metadata = ImportMetadata.model_validate_json(metadata)
        except (ValidationError, ValueError) as exc:
            raise HTTPException(
                status_code=422,
                detail="文档元数据不合法",
            ) from exc
        content = await file.read(settings.upload_max_bytes + 1)
        if len(content) > settings.upload_max_bytes:
            raise HTTPException(status_code=413, detail="文件不能超过 15 MiB")
        try:
            source = SourceFile.from_bytes(
                original_filename=file.filename or "upload",
                media_type=file.content_type or "application/octet-stream",
                content=content,
            )
            return service.preview_import(source, import_metadata, user)
        except ValidationError as exc:
            raise HTTPException(
                status_code=422,
                detail="文件格式不受支持",
            ) from exc

    @app.get("/knowledge/imports", response_model=list[ImportPreview])
    def knowledge_imports(
        user: UserContext = Depends(require_admin),
    ) -> list[ImportPreview]:
        return service.list_imports(user)

    @app.get("/knowledge/imports/{import_id}", response_model=ImportPreview)
    def knowledge_import(
        import_id: str,
        user: UserContext = Depends(require_admin),
    ) -> ImportPreview:
        preview = service.get_import(import_id, user)
        if preview is None:
            raise HTTPException(status_code=404, detail="导入任务不存在")
        return preview

    @app.post(
        "/knowledge/imports/{import_id}/approve",
        response_model=ImportPreview,
    )
    def approve_knowledge_import(
        import_id: str,
        metadata: ImportMetadata,
        user: UserContext = Depends(require_admin),
    ) -> ImportPreview:
        try:
            return service.approve_import(import_id, metadata, user)
        except ImportNotFoundError as exc:
            raise HTTPException(status_code=404, detail="导入任务不存在") from exc
        except ImportNotApprovableError as exc:
            raise HTTPException(
                status_code=409,
                detail="当前导入任务不能批准",
            ) from exc

    if static_dir is not None and (static_dir / "index.html").is_file():
        app.mount(
            "/",
            StaticFiles(directory=static_dir, html=True),
            name="frontend",
        )

    return app
