import json

from enterprise_knowledge_rag.config import get_settings
from enterprise_knowledge_rag.migrations import apply_migrations


def main() -> int:
    settings = get_settings()
    result = apply_migrations(settings.database_url, settings.migrations_dir)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
