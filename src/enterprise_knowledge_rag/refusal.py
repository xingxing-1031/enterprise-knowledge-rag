from enterprise_knowledge_rag.models import ChatResult, RefusalReason

REFUSAL_MESSAGES = {
    RefusalReason.OUT_OF_SCOPE: "这个问题不属于当前企业制度与流程知识库的范围。",
    RefusalReason.INSUFFICIENT_EVIDENCE: "当前知识库中没有足够依据回答这个问题。",
    RefusalReason.PERMISSION_DENIED: "当前账号无权访问相关知识，请联系知识库管理员。",
    RefusalReason.VERSION_AMBIGUOUS: "无法确定适用的制度版本，请补充查询时间或版本。",
    RefusalReason.SERVICE_FAILED: "知识服务暂时不可用，请稍后重试。",
}


def build_refusal(reason: RefusalReason) -> ChatResult:
    return ChatResult(
        status="refused" if reason is not RefusalReason.SERVICE_FAILED else "failed",
        answer=REFUSAL_MESSAGES[reason],
        refusal_reason=reason,
    )
