from datetime import UTC, datetime
from pathlib import Path

from enterprise_knowledge_rag.multi_agent_evaluation import (
    evaluate_supervisor,
    load_cases,
    save_report,
)
from enterprise_knowledge_rag.supervisor import Supervisor


def main() -> None:
    root = Path(__file__).parents[1]
    dataset = root / "evaluation" / "multi_agent_development.jsonl"
    report = evaluate_supervisor(
        load_cases(dataset), Supervisor(), dataset=dataset.name
    )
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output = (
        root
        / "evaluation"
        / "reports"
        / f"multi-agent-development-{timestamp}.json"
    )
    save_report(report, output)
    print(output)
    print(f"route_accuracy={report.route_accuracy:.4f}")
    print(f"agent_selection_accuracy={report.agent_selection_accuracy:.4f}")


if __name__ == "__main__":
    main()
