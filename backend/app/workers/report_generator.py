"""
Report Generator Worker - Generates PDF/HTML reports
"""

import asyncio
import os
from datetime import datetime, date
from typing import Optional, Dict, Any
from pathlib import Path
from uuid import UUID
import json
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session_factory
from app.models import Report, ReportType, AnalysisTask, TaskStatus
from app.utils.logging import get_logger
from app.utils.helpers import ensure_directory

logger = get_logger(__name__)


class ReportGeneratorWorker:
    """Worker for generating report files"""

    def __init__(self):
        self.running = False
        self.template_dir = Path(__file__).parent.parent / "templates"

    async def start(self):
        """Start generation loop"""
        self.running = True
        logger.info("Report generator worker started")

        # Ensure report directory exists
        ensure_directory(settings.report_dir)

        while self.running:
            try:
                await self.generate_pending_reports()
                await asyncio.sleep(30)

            except Exception as e:
                logger.error(f"Report generator error: {e}")
                await asyncio.sleep(60)

    async def stop(self):
        """Stop generator"""
        self.running = False

    async def generate_pending_reports(self):
        """Generate pending reports"""

        async with async_session_factory() as db:
            # Find reports without file_path (not yet generated)
            result = await db.execute(
                select(Report)
                .where(Report.file_path == None)
                .order_by(Report.created_at)
                .limit(10)
            )
            pending = result.scalars().all()

            for report in pending:
                await self.generate_report(db, report)

    async def generate_report(self, db: AsyncSession, report: Report):
        """Generate single report"""

        logger.info(f"Generating report: {report.id}")

        try:
            # Generate content
            content = await self.get_report_content(db, report)

            # Generate files
            output_dir = Path(settings.report_dir)
            if report.report_type == ReportType.DAILY:
                output_dir = output_dir / "daily"
            else:
                output_dir = output_dir / "adhoc"

            output_dir.mkdir(parents=True, exist_ok=True)

            report_id = str(report.id)

            # Generate HTML
            html_path = output_dir / f"{report_id}.html"
            html_content = self.generate_html(report, content)
            with open(html_path, 'w') as f:
                f.write(html_content)

            # Generate JSON
            json_path = output_dir / f"{report_id}.json"
            with open(json_path, 'w') as f:
                json.dump(content, f)

            # Generate PDF (would use weasyprint in production)
            pdf_path = output_dir / f"{report_id}.pdf"
            # await self.generate_pdf(html_path, pdf_path)

            # Update report
            report.file_path = str(pdf_path)
            report.file_format = "pdf"
            report.content = content

            if "summary" in content:
                report.summary = content["summary"]

            await db.commit()

            logger.info(f"Report {report.id} generated successfully")

        except Exception as e:
            logger.error(f"Failed to generate report {report.id}: {e}")

    async def get_report_content(self, db: AsyncSession, report: Report) -> Dict:
        """Get content for report"""

        # If report has task_id, use task result
        if report.task_id:
            result = await db.execute(
                select(AnalysisTask).where(AnalysisTask.id == report.task_id)
            )
            task = result.scalar_one_or_none()

            if task and task.result:
                return {
                    "task_result": task.result,
                    "generated_at": datetime.utcnow().isoformat()
                }

        # Generate default daily report content
        return await self.generate_daily_content(db, report)

    async def generate_daily_content(self, db: AsyncSession, report: Report) -> Dict:
        """Generate daily report content"""

        report_date = report.report_date or date.today()

        # Mock content - in production would query ClickHouse
        return {
            "report_date": str(report_date),
            "summary": f"Daily analysis report for {report_date}",
            "statistics": {
                "total_logs": 100000,
                "errors": 500,
                "warnings": 1000,
                "info": 98500,
                "unique_hosts": 50,
                "top_hosts": [
                    {"name": "web-01", "count": 25000},
                    {"name": "db-01", "count": 15000},
                    {"name": "switch-01", "count": 10000}
                ]
            },
            "error_analysis": {
                "top_errors": [
                    {"message": "Connection timeout", "count": 100},
                    {"message": "Authentication failure", "count": 50},
                    {"message": "Disk I/O error", "count": 30}
                ],
                "error_by_type": {
                    "network": 150,
                    "server": 200,
                    "k8s": 150
                }
            },
            "security_events": {
                "failed_logins": 25,
                "suspicious_ips": ["192.168.1.100", "10.0.0.50"],
                "blocked_connections": 10
            },
            "performance": {
                "slow_queries": 15,
                "high_cpu_events": 20,
                "memory_warnings": 10
            },
            "recommendations": [
                "Review network switch connectivity issues",
                "Investigate authentication failure patterns",
                "Monitor disk I/O on database servers"
            ],
            "generated_at": datetime.utcnow().isoformat()
        }

    def generate_html(self, report: Report, content: Dict) -> str:
        """Generate HTML report"""

        title = report.title or f"Analysis Report - {report.report_date}"
        summary = content.get("summary", "")
        stats = content.get("statistics", {})
        errors = content.get("error_analysis", {})
        recommendations = content.get("recommendations", [])

        html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; }
        h1 { color: #333; }
        h2 { color: #666; border-bottom: 1px solid #ddd; padding-bottom: 10px; }
        table { border-collapse: collapse; width: 100%; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #f5f5f5; }
        .error { color: #d32f2f; }
        .warning { color: #ff9800; }
        .success { color: #4caf50; }
        .card { background: #f5f5f5; padding: 20px; margin: 20px 0; border-radius: 8px; }
        .stats-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; }
        .stat-box { background: #fff; padding: 15px; border-radius: 4px; text-align: center; }
        .stat-value { font-size: 24px; font-weight: bold; }
        .stat-label { color: #666; }
        ul { list-style-type: disc; padding-left: 20px; }
    </style>
</head>
<body>
    <h1>{title}</h1>
    <p><strong>Generated:</strong> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}</p>
    <p><strong>Report Type:</strong> {report.report_type}</p>

    <h2>Summary</h2>
    <p>{summary}</p>

    <div class="stats-grid">
        <div class="stat-box">
            <div class="stat-value">{stats.get('total_logs', 0)}</div>
            <div class="stat-label">Total Logs</div>
        </div>
        <div class="stat-box">
            <div class="stat-value error">{stats.get('errors', 0)}</div>
            <div class="stat-label">Errors</div>
        </div>
        <div class="stat-box">
            <div class="stat-value warning">{stats.get('warnings', 0)}</div>
            <div class="stat-label">Warnings</div>
        </div>
        <div class="stat-box">
            <div class="stat-value">{stats.get('unique_hosts', 0)}</div>
            <div class="stat-label">Hosts</div>
        </div>
    </div>

    <h2>Top Errors</h2>
    <table>
        <tr><th>Error Message</th><th>Count</th></tr>
        {self._generate_error_rows(errors.get('top_errors', []))}
    </table>

    <h2>Recommendations</h2>
    <ul>
        {self._generate_recommendation_list(recommendations)}
    </ul>

    <footer style="margin-top: 40px; color: #666; text-align: center;">
        <p>AI Log Analyzer - Automated Report</p>
    </footer>
</body>
</html>
"""
        return html

    def _generate_error_rows(self, errors: list) -> str:
        rows = ""
        for error in errors:
            rows += f"<tr><td>{error.get('message', 'Unknown')}</td><td>{error.get('count', 0)}</td></tr>"
        return rows

    def _generate_recommendation_list(self, recommendations: list) -> str:
        items = ""
        for rec in recommendations:
            items += f"<li>{rec}</li>"
        return items


async def main():
    """Main entry point"""

    worker = ReportGeneratorWorker()

    try:
        await worker.start()
    except KeyboardInterrupt:
        await worker.stop()


if __name__ == "__main__":
    asyncio.run(main())