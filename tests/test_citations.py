from datetime import UTC, datetime

from enterprise_knowledge_rag.citations import validate_citations
from enterprise_knowledge_rag.generation import AnswerClaim, DraftAnswer
from enterprise_knowledge_rag.models import RetrievalEvidence


def make_evidence() -> RetrievalEvidence:
    return RetrievalEvidence(
        evidence_id="ev:expense-v2:deadline",
        chunk_id="expense-v2:deadline",
        document_id="finance-expense-policy",
        title="差旅与费用报销管理制度",
        section_path=["差旅与费用报销管理制度", "报销期限"],
        version="2.0",
        effective_from=datetime(2026, 6, 1, tzinfo=UTC),
        quote="出差结束后15个自然日内提交报销申请，逾期由直属主管补充说明。",
        retrieval_channels={"bm25", "vector"},
        retrieval_rank=1,
        reranker_score=0.9,
    )


def test_valid_citation_supports_number_and_approver() -> None:
    evidence = make_evidence()
    draft = DraftAnswer(
        answer="请在15个自然日内提交，逾期由直属主管补充说明。",
        claims=[
            AnswerClaim(
                text="请在15个自然日内提交，逾期由直属主管补充说明。",
                evidence_ids=[evidence.evidence_id],
            )
        ],
    )
    assert validate_citations(draft, [evidence]).valid


def test_unknown_evidence_id_is_rejected() -> None:
    draft = DraftAnswer(
        answer="需要提交。",
        claims=[AnswerClaim(text="需要提交。", evidence_ids=["ev:missing"])],
    )
    result = validate_citations(draft, [make_evidence()])
    assert not result.valid
    assert "unknown evidence" in result.errors[0]


def test_unsupported_number_is_rejected() -> None:
    evidence = make_evidence()
    draft = DraftAnswer(
        answer="请在30个自然日内提交。",
        claims=[
            AnswerClaim(
                text="请在30个自然日内提交。",
                evidence_ids=[evidence.evidence_id],
            )
        ],
    )
    result = validate_citations(draft, [evidence])
    assert not result.valid
    assert "30个" in result.errors[0]


def test_unsupported_approval_role_is_rejected() -> None:
    evidence = make_evidence()
    draft = DraftAnswer(
        answer="逾期由总经理补充说明。",
        claims=[
            AnswerClaim(
                text="逾期由总经理补充说明。",
                evidence_ids=[evidence.evidence_id],
            )
        ],
    )
    result = validate_citations(draft, [evidence])
    assert not result.valid
    assert "总经理" in result.errors[0]


def test_citations_must_cover_every_required_evidence_need() -> None:
    evidence = make_evidence().model_copy(
        update={"supports_need_ids": {"deadline"}}
    )
    draft = DraftAnswer(
        answer="请按制度期限提交。",
        claims=[
            AnswerClaim(
                text="请按制度期限提交。",
                evidence_ids=[evidence.evidence_id],
            )
        ],
    )

    result = validate_citations(
        draft,
        [evidence],
        required_need_ids=frozenset({"deadline", "approver"}),
    )

    assert not result.valid
    assert "missing required evidence needs" in result.errors[-1]
