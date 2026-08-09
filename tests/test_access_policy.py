from datetime import UTC, datetime

from enterprise_knowledge_rag.models import (
    DocumentRecord,
    DocumentStatus,
    DocumentType,
    UserContext,
    UserRole,
    Visibility,
)
from enterprise_knowledge_rag.policy import can_access, evaluate_access


def make_document(visibility, allowed_roles=()):
    return DocumentRecord(
        document_id="finance-payment-approval",
        title="付款申请审批权限表",
        document_type=DocumentType.POLICY,
        department="finance",
        visibility=visibility,
        allowed_roles=allowed_roles,
        version="1.1",
        status=DocumentStatus.ACTIVE,
        effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        content_hash="a" * 64,
        source_path="finance/payment.md",
        indexed_at=datetime(2026, 8, 10, tzinfo=UTC),
    )


def make_user(role=UserRole.EMPLOYEE, departments=()):
    return UserContext(user_id="user-1", role=role, departments=departments)


def test_public_document_is_visible_to_employee() -> None:
    assert can_access(make_user(), make_document(Visibility.PUBLIC))


def test_department_document_requires_membership() -> None:
    document = make_document(
        Visibility.DEPARTMENT,
        [UserRole.DEPARTMENT_ADMIN],
    )
    assert can_access(make_user(departments=["finance"]), document)
    assert not can_access(make_user(departments=["hr"]), document)


def test_restricted_document_requires_role_and_department() -> None:
    document = make_document(
        Visibility.RESTRICTED,
        [UserRole.DEPARTMENT_ADMIN],
    )
    assert can_access(
        make_user(UserRole.DEPARTMENT_ADMIN, ["finance"]),
        document,
    )
    assert not can_access(make_user(UserRole.EMPLOYEE, ["finance"]), document)
    assert not can_access(
        make_user(UserRole.DEPARTMENT_ADMIN, ["hr"]),
        document,
    )


def test_knowledge_admin_can_access_without_department_membership() -> None:
    document = make_document(
        Visibility.RESTRICTED,
        [UserRole.DEPARTMENT_ADMIN],
    )
    assert can_access(make_user(UserRole.KNOWLEDGE_ADMIN), document)


def test_denial_message_does_not_leak_document_title() -> None:
    document = make_document(
        Visibility.RESTRICTED,
        [UserRole.DEPARTMENT_ADMIN],
    )
    decision = evaluate_access(make_user(), document)
    assert not decision.allowed
    assert document.title not in decision.public_message
    assert document.document_id not in decision.public_message
