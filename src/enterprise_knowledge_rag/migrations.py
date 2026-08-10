from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path


@dataclass(frozen=True)
class Migration:
    version: str
    checksum: str
    sql: str


def discover_migrations(directory: Path) -> list[Migration]:
    migrations: list[Migration] = []
    for path in sorted(directory.glob("*.sql")):
        sql = path.read_text(encoding="utf-8")
        migrations.append(
            Migration(
                version=path.stem,
                checksum=sha256(sql.encode("utf-8")).hexdigest(),
                sql=sql,
            )
        )
    return migrations


def apply_migrations(database_url: str, directory: Path) -> dict[str, int]:
    import psycopg

    migrations = discover_migrations(directory)
    applied = 0
    skipped = 0
    with psycopg.connect(database_url, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    checksum CHAR(64) NOT NULL,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        for migration in migrations:
            with connection.transaction(), connection.cursor() as cursor:
                cursor.execute(
                    "SELECT checksum FROM schema_migrations WHERE version = %s",
                    (migration.version,),
                )
                row = cursor.fetchone()
                if row is not None:
                    if row[0].strip() != migration.checksum:
                        raise RuntimeError(
                            f"migration checksum changed: {migration.version}"
                        )
                    skipped += 1
                    continue
                cursor.execute(migration.sql)
                cursor.execute(
                    """
                    INSERT INTO schema_migrations (version, checksum)
                    VALUES (%s, %s)
                    """,
                    (migration.version, migration.checksum),
                )
                applied += 1
    return {"discovered": len(migrations), "applied": applied, "skipped": skipped}
