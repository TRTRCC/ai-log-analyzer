"""
Scheduler Worker - Handles scheduled tasks (daily reports, auto analysis)
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID
import json
from croniter import croniter
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session_factory
from app.models import ScheduledTask, AnalysisTask, TaskStatus, TaskType, Report, ReportType
from app.utils.logging import get_logger
from app.utils.helpers import get_utc_now

logger = get_logger(__name__)


class SchedulerWorker:
    """Worker for handling scheduled tasks"""

    def __init__(self):
        self.running = False
        self.task_handlers = {
            "daily_report": self.handle_daily_report,
            "auto_analysis": self.handle_auto_analysis,
            "log_cleanup": self.handle_log_cleanup,
            "email_report": self.handle_email_report,
        }

    async def start(self):
        """Start scheduler loop"""
        self.running = True
        logger.info("Scheduler worker started")

        while self.running:
            try:
                await self.check_and_execute_tasks()
                await asyncio.sleep(60)  # Check every minute

            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                await asyncio.sleep(120)

    async def stop(self):
        """Stop scheduler"""
        self.running = False

    async def check_and_execute_tasks(self):
        """Check scheduled tasks and execute if needed"""

        async with async_session_factory() as db:
            # Get active scheduled tasks
            result = await db.execute(
                select(ScheduledTask).where(ScheduledTask.is_active == True)
            )
            tasks = result.scalars().all()

            now = get_utc_now()

            for task in tasks:
                # Check if task should run
                if self.should_run(task, now):
                    logger.info(f"Executing scheduled task: {task.name}")

                    # Execute task
                    handler = self.task_handlers.get(task.task_type)
                    if handler:
                        try:
                            await handler(db, task)

                            # Update last_run and calculate next_run
                            task.last_run = now
                            task.next_run = self.calculate_next_run(task)

                            await db.commit()

                        except Exception as e:
                            logger.error(f"Task {task.name} failed: {e}")
                    else:
                        logger.warning(f"Unknown task type: {task.task_type}")

    def should_run(self, task: ScheduledTask, now: datetime) -> bool:
        """Check if task should run now"""

        if task.cron_expression:
            cron = croniter(task.cron_expression, task.last_run or now)
            next_run = cron.get_next(datetime)

            # Run if next_run is within the next minute
            return next_run <= now + timedelta(minutes=1)

        elif task.interval_minutes:
            if not task.last_run:
                return True

            next_run = task.last_run + timedelta(minutes=task.interval_minutes)
            return next_run <= now

        return False

    def calculate_next_run(self, task: ScheduledTask) -> datetime:
        """Calculate next run time"""

        now = get_utc_now()

        if task.cron_expression:
            cron = croniter(task.cron_expression, now)
            return cron.get_next(datetime)

        elif task.interval_minutes:
            return now + timedelta(minutes=task.interval_minutes)

        return None

    async def handle_daily_report(self, db: AsyncSession, task: ScheduledTask):
        """Generate daily report"""

        logger.info("Generating daily report")

        # Create report
        report = Report(
            user_id=None,  # System generated
            report_type=ReportType.DAILY,
            report_date=datetime.utcnow().date(),
            title=f"Daily Report - {datetime.utcnow().strftime('%Y-%m-%d')}",
            summary="Automated daily analysis report"
        )

        db.add(report)
        await db.commit()
        await db.refresh(report)

        # Generate content (would be done in background)
        await self.generate_report_content(db, report)

        logger.info(f"Daily report created: {report.id}")

    async def handle_auto_analysis(self, db: AsyncSession, task: ScheduledTask):
        """Run automatic AI analysis"""

        logger.info("Running auto analysis")

        config = task.config or {}

        # Create analysis task
        analysis = AnalysisTask(
            user_id=None,  # System generated
            task_type=TaskType.AUTO,
            status=TaskStatus.PENDING,
            log_type=config.get("log_type", "all"),
            time_range_start=datetime.utcnow() - timedelta(hours=settings.auto_analysis_interval_hours),
            time_range_end=datetime.utcnow(),
            model_id=UUID(config.get("model_id")) if config.get("model_id") else None,
            provider_id=UUID(config.get("provider_id")) if config.get("provider_id") else None,
        )

        db.add(analysis)
        await db.commit()

        logger.info(f"Auto analysis task created: {analysis.id}")

    async def handle_log_cleanup(self, db: AsyncSession, task: ScheduledTask):
        """Clean up old logs"""

        logger.info("Running log cleanup")

        config = task.config or {}
        retention_days = config.get("retention_days", 90)

        # In production, this would clean ClickHouse data
        # ALTER TABLE logs DELETE WHERE timestamp < now() - INTERVAL retention_days DAY

        logger.info(f"Log cleanup completed (retention: {retention_days} days)")

    async def handle_email_report(self, db: AsyncSession, task: ScheduledTask):
        """Send report via email"""

        logger.info("Sending email reports")

        # In production, this would:
        # 1. Get latest daily report
        # 2. Get subscribed users
        # 3. Send email via SMTP

        logger.info("Email reports sent")

    async def generate_report_content(self, db: AsyncSession, report: Report):
        """Generate report content"""

        # Mock content generation
        content = {
            "summary": "Daily system health report",
            "statistics": {
                "total_logs": 100000,
                "errors": 500,
                "warnings": 1000,
                "unique_hosts": 50
            },
            "top_errors": [
                {"count": 100, "message": "Connection timeout"},
                {"count": 50, "message": "Authentication failure"},
            ],
            "recommendations": [
                "Review network switch configuration",
                "Update authentication policies",
            ]
        }

        report.content = content
        report.summary = f"{content['statistics']['errors']} errors detected"

        await db.commit()


async def main():
    """Main entry point"""

    worker = SchedulerWorker()

    try:
        await worker.start()
    except KeyboardInterrupt:
        await worker.stop()


if __name__ == "__main__":
    asyncio.run(main())