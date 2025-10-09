from __future__ import annotations

import os
from dataclasses import dataclass

import structlog
from sqlalchemy import create_engine, text
from temporalio import activity, workflow
from temporalio.worker import Worker
from temporalio.client import Client


logger = structlog.get_logger(__name__)


@activity.defn
async def finalize_job(job_id: int) -> str:
    engine = create_engine(os.getenv("DATABASE_URL", "postgresql+psycopg://postgres:postgres@db:5432/postgres"))
    with engine.begin() as conn:
        conn.execute(text("update workflow_jobs set status='done' where id=:id"), {"id": job_id})
    logger.info("temporal.activity.finalize", id=job_id)
    return "ok"


@workflow.defn
class ProcessJobWorkflow:
    @workflow.run
    async def run(self, job_id: int) -> str:
        # This is where approvals/waits/etc would be modeled
        return await workflow.execute_activity(finalize_job, job_id, schedule_to_close_timeout=60)


async def main() -> None:
    address = os.getenv("TEMPORAL_ADDRESS", "temporal:7233")
    namespace = os.getenv("TEMPORAL_NAMESPACE", "default")
    client = await Client.connect(address, namespace=namespace)
    worker = Worker(client, task_queue="workflow-jobs", workflows=[ProcessJobWorkflow], activities=[finalize_job])
    await worker.run()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())


