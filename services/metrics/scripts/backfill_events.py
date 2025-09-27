import os
from datetime import datetime, timedelta, timezone

import psycopg


def main() -> None:
    dsn = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/postgres",
    )
    now = datetime.now(timezone.utc)

    rows = []
    # Create a few synthetic deliveries
    for i in range(1, 6):
        delivery = f"demo-{i}"
        commit_t = now - timedelta(days=5 - i, hours=i)
        deploy_t = commit_t + timedelta(hours=12 + i)
        # commit/push
        rows.append(
            (
                "github",
                "push",
                delivery,
                None,
                {"demo": True},
                "{\"msg\": \"commit\"}",
                commit_t,
            )
        )
        # pr opened
        rows.append(
            (
                "github",
                "pull_request",
                delivery,
                None,
                {"demo": True},
                "{\"msg\": \"pr_opened\"}",
                commit_t + timedelta(hours=1),
            )
        )
        # first review
        rows.append(
            (
                "github",
                "pull_request_review",
                delivery,
                None,
                {"demo": True},
                "{\"msg\": \"review\"}",
                commit_t + timedelta(hours=3),
            )
        )
        # deploy
        rows.append(
            (
                "github",
                "deployment_status",
                delivery,
                None,
                {"demo": True},
                "{\"msg\": \"deploy\"}",
                deploy_t,
            )
        )

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                create table if not exists events_raw (
                  id serial primary key,
                  source varchar(32) not null,
                  event_type varchar(64),
                  delivery_id varchar(128) not null,
                  signature varchar(256),
                  headers json not null default '{}'::json,
                  payload text not null,
                  received_at timestamptz not null default now()
                )
                """
            )
            cur.executemany(
                """
                insert into events_raw(source, event_type, delivery_id, signature, headers, payload, received_at)
                values (%s, %s, %s, %s, %s, %s, %s)
                """,
                rows,
            )
        conn.commit()

    print(f"Seeded {len(rows)} events into events_raw")


if __name__ == "__main__":
    main()


