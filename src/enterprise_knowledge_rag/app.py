import hmac
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
from fastapi.staticfiles import StaticFiles

from enterprise_knowledge_rag.admin_models import (
    AdminOverview,
    DeleteResult,
    ManagedDocument,
    RetrievalDebugRequest,
    RetrievalDebugResponse,
)
from enterprise_knowledge_rag.admin_service import (
    DocumentConfirmationError,
    DocumentNotFoundError,
    UnsafeSourcePathError,
)
from enterprise_knowledge_rag.auth import (
    AuthSessionResolver,
    issue_session,
    verify_password,
)
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
    InternalEvidenceItem,
    InternalEvidenceRequest,
    InternalEvidenceResponse,
    LoginRequest,
    UserContext,
    UserRole,
)
from enterprise_knowledge_rag.tracing import TraceEvent
from enterprise_knowledge_rag.workflow import WorkflowRun


class ChatApiService(Protocol):
    def ready(self) -> bool: ...

    def run(self, request: ChatRequest, user: UserContext) -> WorkflowRun: ...

    def run_knowledge(self, request: ChatRequest, user: UserContext) -> WorkflowRun: ...

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


class AdminApiService(Protocol):
    def overview(self, actor: UserContext) -> AdminOverview: ...
    def documents(self, actor: UserContext) -> tuple[ManagedDocument, ...]: ...
    def deactivate(
        self, document_id: str, version: str, actor: UserContext
    ) -> ManagedDocument: ...
    def restore(
        self, document_id: str, version: str, actor: UserContext
    ) -> ManagedDocument: ...
    def reindex(
        self, document_id: str, version: str, actor: UserContext
    ) -> ManagedDocument: ...
    def delete(
        self, document_id: str, version: str, *, confirmation: str, actor: UserContext
    ) -> DeleteResult: ...
    def audit(self, actor: UserContext, *, limit: int = 50) -> list[Any]: ...
    def debug_retrieve(
        self, request: RetrievalDebugRequest, actor: UserContext
    ) -> RetrievalDebugResponse: ...


class SessionResolver(Protocol):
    def resolve(self, request: Request) -> UserContext: ...


STAGE_LABELS = {
    "knowledge_agent": "知识 Agent 正在核验企业证据",
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


def _demo_accounts(
    settings: Settings,
) -> tuple[tuple[str, str, UserRole, str, str], ...]:
    return (
        (
            settings.auth_knowledge_admin_username,
            settings.auth_knowledge_admin_user_id,
            UserRole.KNOWLEDGE_ADMIN,
            settings.auth_knowledge_admin_departments,
            settings.auth_knowledge_admin_password_hash,
        ),
    )


def create_app(
    service: ChatApiService,
    *,
    settings: Settings | None = None,
    session_resolver: SessionResolver | None = None,
    lifespan: Any | None = None,
    static_dir: Path | None = None,
    admin_service: AdminApiService | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    resolver = session_resolver or AuthSessionResolver(settings)
    app = FastAPI(
        title="企业知识库 RAG API",
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
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "Authorization", "X-Internal-Token"],
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

    def require_internal_token(request: Request) -> None:
        configured = settings.internal_service_token
        if configured is None:
            raise HTTPException(status_code=503, detail="内部知识接口未配置")
        supplied = request.headers.get("X-Internal-Token", "")
        if not hmac.compare_digest(
            supplied,
            configured.get_secret_value(),
        ):
            raise HTTPException(status_code=401, detail="内部服务认证失败")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    def ready() -> dict[str, str]:
        if not service.ready():
            raise HTTPException(status_code=503, detail="知识库尚未准备完成")
        return {"status": "ready"}

    @app.post("/auth/login")
    def login(login_request: LoginRequest, response: Response) -> dict[str, Any]:
        for username, user_id, role, departments, password_hash in _demo_accounts(
            settings
        ):
            if login_request.username != username:
                continue
            if not verify_password(login_request.password, password_hash):
                raise HTTPException(status_code=401, detail="用户名或密码错误。")
            token = issue_session(
                user_id=user_id,
                role=role,
                departments=departments.split(","),
                secret=settings.auth_session_secret,
                ttl_seconds=settings.auth_session_ttl_seconds,
            )
            response.set_cookie(
                key=settings.auth_cookie_name,
                value=token,
                max_age=settings.auth_session_ttl_seconds,
                httponly=True,
                samesite="lax",
                secure=settings.auth_cookie_secure,
                path="/",
            )
            return {
                "user_id": user_id,
                "role": role.value,
                "departments": [item for item in departments.split(",") if item],
                "public_demo_mode": settings.public_demo_mode,
            }
        raise HTTPException(status_code=401, detail="用户名或密码错误。")

    @app.post("/auth/logout")
    def logout() -> Response:
        response = Response(status_code=status.HTTP_204_NO_CONTENT)
        response.delete_cookie(settings.auth_cookie_name, path="/")
        return response

    @app.get("/session")
    def session(user: UserContext = Depends(require_admin)) -> dict[str, Any]:
        return {
            "user_id": user.user_id,
            "role": user.role.value,
            "departments": sorted(user.departments),
            "public_demo_mode": settings.public_demo_mode,
        }

    @app.post(
        "/internal/evidence",
        response_model=InternalEvidenceResponse,
        include_in_schema=False,
    )
    def internal_evidence(
        evidence_request: InternalEvidenceRequest,
        request: Request,
    ) -> InternalEvidenceResponse:
        require_internal_token(request)
        role = (
            UserRole.DEPARTMENT_ADMIN
            if evidence_request.role == "admin"
            else UserRole.EMPLOYEE
        )
        user = UserContext(
            user_id=evidence_request.user_id,
            role=role,
            departments=evidence_request.departments,
        )
        chat_request = ChatRequest(
            question=evidence_request.query,
            session_id=evidence_request.session_id,
            as_of=evidence_request.as_of,
        )
        try:
            knowledge_runner = getattr(service, "run_knowledge", service.run)
            result = knowledge_runner(chat_request, user).result
        except Exception as exc:
            if settings.app_env == "test":
                raise
            raise HTTPException(
                status_code=503,
                detail="知识服务暂时不可用，请稍后重试。",
            ) from exc
        evidence = [
            InternalEvidenceItem(
                source_id=item.evidence_id,
                title=item.title,
                version=item.version,
                effective_from=item.effective_from,
                quote=item.quote,
                score=max(0.0, min(1.0, item.reranker_score or 0.0)),
                permissions={role.value},
            )
            for item in result.evidence[: evidence_request.top_k]
        ]
        return InternalEvidenceResponse(
            status=result.status,
            evidence=evidence,
            refusal_reason=result.refusal_reason,
            degradation_reason=result.degradation_reason,
        )

    @app.get("/documents")
    def documents(user: UserContext = Depends(require_admin)) -> Any:
        if admin_service is not None:
            return admin_service.documents(user)
        return service.documents_overview(user)

    @app.post("/documents/index")
    def index_documents(
        user: UserContext = Depends(require_admin),
    ) -> dict[str, Any]:
        return service.index_documents(user)

    @app.get("/evaluations/latest")
    def latest_evaluation(user: UserContext = Depends(require_admin)) -> dict[str, Any]:
        del user
        return service.latest_evaluation()

    @app.get("/admin/overview", response_model=AdminOverview)
    def admin_overview(user: UserContext = Depends(require_admin)) -> AdminOverview:
        if admin_service is None:
            raise HTTPException(status_code=503, detail="管理服务尚未配置")
        return admin_service.overview(user)

    def _document_action_error(exc: Exception) -> HTTPException:
        if isinstance(exc, DocumentNotFoundError):
            return HTTPException(status_code=404, detail="文档版本不存在")
        if isinstance(exc, DocumentConfirmationError):
            return HTTPException(status_code=409, detail="文档标题确认不匹配")
        if isinstance(exc, UnsafeSourcePathError):
            return HTTPException(status_code=409, detail="文档源文件不在受控目录")
        if isinstance(exc, FileNotFoundError):
            return HTTPException(status_code=409, detail="文档源文件不存在")
        return HTTPException(status_code=503, detail="文档操作暂时不可用")

    @app.post(
        "/admin/documents/{document_id}/{version}/deactivate",
        response_model=ManagedDocument,
    )
    def deactivate_document(
        document_id: str, version: str, user: UserContext = Depends(require_admin)
    ) -> ManagedDocument:
        if admin_service is None:
            raise HTTPException(status_code=503, detail="管理服务尚未配置")
        try:
            return admin_service.deactivate(document_id, version, user)
        except Exception as exc:
            raise _document_action_error(exc) from exc

    @app.post(
        "/admin/documents/{document_id}/{version}/restore",
        response_model=ManagedDocument,
    )
    def restore_document(
        document_id: str, version: str, user: UserContext = Depends(require_admin)
    ) -> ManagedDocument:
        if admin_service is None:
            raise HTTPException(status_code=503, detail="管理服务尚未配置")
        try:
            return admin_service.restore(document_id, version, user)
        except Exception as exc:
            raise _document_action_error(exc) from exc

    @app.post(
        "/admin/documents/{document_id}/{version}/reindex",
        response_model=ManagedDocument,
    )
    def reindex_document(
        document_id: str, version: str, user: UserContext = Depends(require_admin)
    ) -> ManagedDocument:
        if admin_service is None:
            raise HTTPException(status_code=503, detail="管理服务尚未配置")
        try:
            return admin_service.reindex(document_id, version, user)
        except Exception as exc:
            raise _document_action_error(exc) from exc

    @app.delete("/admin/documents/{document_id}/{version}", response_model=DeleteResult)
    def delete_document(
        document_id: str,
        version: str,
        confirmation: str,
        user: UserContext = Depends(require_admin),
    ) -> DeleteResult:
        if admin_service is None:
            raise HTTPException(status_code=503, detail="管理服务尚未配置")
        try:
            return admin_service.delete(
                document_id, version, confirmation=confirmation, actor=user
            )
        except Exception as exc:
            raise _document_action_error(exc) from exc

    @app.get("/admin/audit")
    def admin_audit(
        limit: int = 50, user: UserContext = Depends(require_admin)
    ) -> list[Any]:
        if admin_service is None:
            raise HTTPException(status_code=503, detail="管理服务尚未配置")
        return admin_service.audit(user, limit=limit)

    @app.post("/admin/retrieval/debug", response_model=RetrievalDebugResponse)
    def debug_retrieval(
        debug_request: RetrievalDebugRequest,
        user: UserContext = Depends(require_admin),
    ) -> RetrievalDebugResponse:
        if admin_service is None:
            raise HTTPException(status_code=503, detail="管理服务尚未配置")
        try:
            return admin_service.debug_retrieve(debug_request, user)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="检索调试参数不合法") from exc
        except Exception as exc:
            if settings.app_env == "test":
                raise
            raise HTTPException(status_code=503, detail="检索调试暂时不可用") from exc

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
