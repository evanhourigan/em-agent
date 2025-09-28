import os
from datetime import datetime, timedelta, timezone

import psycopg


def main() -> None:
    dsn = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/postgres",
    )
    days = int(os.getenv("RETENTION_DAYS", "30"))
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("delete from events_raw where received_at < %s", (cutoff,))
            deleted = cur.rowcount
        conn.commit()

    print(f"Deleted {deleted} rows older than {days} days (cutoff {cutoff.isoformat()})")


if __name__ == "__main__":
    main()


