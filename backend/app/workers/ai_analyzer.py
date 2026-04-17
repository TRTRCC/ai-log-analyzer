"""
AI Analyzer Worker - Background task processing for AI analysis
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session_factory
from app.models import AnalysisTask, TaskStatus, TaskType, LogType
from app.ai.engine import ai_engine
from app.services.log_parser import get_log_sampler
from app.utils.logging import get_logger

logger = get_logger(__name__)


class AIAnalyzerWorker:
    """Worker for processing AI analysis tasks"""

    def __init__(self):
        self.running = False
        self.log_sampler = get_log_sampler()

    async def start(self):
        """Start processing loop"""
        self.running = True
        logger.info("AI analyzer worker started")

        while self.running:
            try:
                # Process pending tasks
                await self.process_pending_tasks()

                # Wait before next iteration
                await asyncio.sleep(10)  # Check every 10 seconds

            except Exception as e:
                logger.error(f"AI analyzer error: {e}")
                await asyncio.sleep(30)

    async def stop(self):
        """Stop processing"""
        self.running = False
        await ai_engine.close_all()

    async def process_pending_tasks(self):
        """Process pending analysis tasks"""

        async with async_session_factory() as db:
            # Find pending tasks
            result = await db.execute(
                select(AnalysisTask)
                .where(AnalysisTask.status == TaskStatus.PENDING)
                .order_by(AnalysisTask.created_at)
                .limit(5)  # Process up to 5 tasks at once
            )
            pending_tasks = result.scalars().all()

            if pending_tasks:
                logger.info(f"Found {len(pending_tasks)} pending tasks")

            for task in pending_tasks:
                await self.process_task(db, task)

    async def process_task(self, db: AsyncSession, task: AnalysisTask):
        """Process single analysis task"""

        logger.info(f"Processing task {task.id}")

        # Initialize AI engine if needed
        await ai_engine.initialize(db)

        # Get logs sample for analysis
        logs_sample = await self.get_logs_sample(db, task)

        if not logs_sample:
            # No logs to analyze
            await db.execute(
                update(AnalysisTask)
                .where(AnalysisTask.id == task.id)
                .values(
                    status=TaskStatus.FAILED,
                    error_message="No logs found for analysis",
                    completed_at=datetime.utcnow()
                )
            )
            await db.commit()
            return

        # Determine analysis type
        analysis_type = self.get_analysis_type(task)

        # Run AI analysis
        provider_id = str(task.provider_id) if task.provider_id else None
        model_id = str(task.model_id) if task.model_id else None

        result = await ai_engine.analyze_logs(
            db,
            task.id,
            logs_sample,
            analysis_type,
            provider_id,
            model_id
        )

        logger.info(f"Task {task.id} completed: success={result.success}")

    async def get_logs_sample(self, db: AsyncSession, task: AnalysisTask) -> str:
        """Get sample of logs for analysis"""

        # In production, query ClickHouse based on task parameters
        # time_range_start, time_range_end, log_type, devices

        # Mock sample for now
        start = task.time_range_start or datetime.utcnow() - timedelta(hours=24)
        end = task.time_range_end or datetime.utcnow()
        log_type = task.log_type

        sample = f"""
# Log Analysis Sample
# Time Range: {start} to {end}
# Log Type: {log_type}
# Devices: {task.devices or 'All'}

[2024-04-17 08:00:15] [ERROR] [web-server-01] Database connection timeout - unable to reach db-01
[2024-04-17 08:00:20] [WARNING] [network-switch-01] Interface GigabitEthernet0/1 status changed to down
[2024-04-17 08:00:25] [INFO] [k8s-pod-api-01] HTTP request processed successfully - status 200
[2024-04-17 08:01:00] [ERROR] [database-01] Query execution exceeded threshold - 5000ms
[2024-04-17 08:01:30] [WARNING] [k8s-node-01] Pod memory usage at 85%
[2024-04-17 08:02:00] [CRITICAL] [firewall-01] Multiple failed SSH login attempts detected from IP 192.168.1.100
[2024-04-17 08:02:30] [INFO] [load-balancer-01] Health check passed for web-server-02
[2024-04-17 08:03:00] [ERROR] [web-server-02] Application crashed - restarting service
[2024-04-17 08:03:30] [WARNING] [storage-array-01] Disk temperature warning - 45C
[2024-04-17 08:04:00] [INFO] [backup-server-01] Backup job completed successfully
"""

        return sample

    def get_analysis_type(self, task: AnalysisTask) -> str:
        """Determine analysis type based on task parameters"""

        if task.log_type == "network":
            return "network"
        elif task.log_type == "server":
            return "performance"
        elif task.log_type == "k8s":
            return "general"

        # Check task config for specific analysis type
        if task.devices and "security" in str(task.devices).lower():
            return "security"

        return "general"


async def main():
    """Main entry point"""

    worker = AIAnalyzerWorker()

    try:
        await worker.start()
    except KeyboardInterrupt:
        await worker.stop()


if __name__ == "__main__":
    asyncio.run(main())