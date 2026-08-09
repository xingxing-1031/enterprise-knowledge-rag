from dataclasses import dataclass

from enterprise_knowledge_rag.models import (
    DocumentRecord,
    UserContext,
    UserRole,
    Visibility,
)


@dataclass(frozen=True, slots=True)
class AccessDecision:
    allowed: bool
    internal_reason: str
    public_message: str


DENIED_MESSAGE = "当前账号无权访问相关知识，请联系知识库管理员。"


def evaluate_access(user: UserContext, document: DocumentRecord) -> AccessDecision:
    if user.role is UserRole.KNOWLEDGE_ADMIN:
        return AccessDecision(True, "knowledge_admin", "允许访问")

    if document.visibility is Visibility.PUBLIC:
        return AccessDecision(True, "public_document", "允许访问")

    belongs_to_department = document.department in user.departments
    if document.visibility is Visibility.DEPARTMENT:
        if belongs_to_department:
            return AccessDecision(True, "department_member", "允许访问")
        return AccessDecision(False, "department_mismatch", DENIED_MESSAGE)

    role_allowed = user.role in document.allowed_roles
    if role_allowed and belongs_to_department:
        return AccessDecision(True, "restricted_role_and_department", "允许访问")
    if not role_allowed:
        return AccessDecision(False, "restricted_role_missing", DENIED_MESSAGE)
    return AccessDecision(False, "restricted_department_mismatch", DENIED_MESSAGE)


def can_access(user: UserContext, document: DocumentRecord) -> bool:
    return evaluate_access(user, document).allowed
