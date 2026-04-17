"""
Log Processor Worker - Processes ELK log files and stores to ClickHouse
"""

import asyncio
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from pathlib import Path
import json

try:
    from aiochclient import ChClient
except ImportError:
    ChClient = None

from app.config import settings
from app.services.log_parser import LogParser, LogFileProcessor, get_log_parser, get_file_processor
from app.utils.logging import get_logger
from app.utils.helpers import ensure_directory

logger = get_logger(__name__)


class LogProcessorWorker:
    """Worker for processing log files"""

    def __init__(self):
        self.parser = get_log_parser()
        self.file_processor = get_file_processor()
        self.clickhouse_client = None
        self.running = False

    async def initialize(self):
        """Initialize ClickHouse connection"""
        if ChClient:
            try:
                self.clickhouse_client = ChClient(
                    url=settings.clickhouse_url,
                    user=settings.clickhouse_user,
                    password=settings.clickhouse_password,
                    database=settings.clickhouse_database
                )
                logger.info("ClickHouse client initialized")
            except Exception as e:
                logger.error(f"ClickHouse initialization failed: {e}")

        # Ensure directories exist
        ensure_directory(settings.raw_log_dir)
        ensure_directory(settings.parsed_log_dir)

    async def start(self):
        """Start processing loop"""
        self.running = True
        logger.info("Log processor worker started")

        while self.running:
            try:
                # Check for new files
                await self.process_new_files()

                # Wait before next iteration
                await asyncio.sleep(60)  # Check every minute

            except Exception as e:
                logger.error(f"Processing error: {e}")
                await asyncio.sleep(120)

    async def stop(self):
        """Stop processing"""
        self.running = False
        if self.clickhouse_client:
            await self.clickhouse_client.close()

    async def process_new_files(self):
        """Process new log files in raw directory"""

        raw_dir = Path(settings.raw_log_dir)

        # Find unprocessed files
        for file_path in raw_dir.iterdir():
            if file_path.is_file():
                # Check if it's a new file (by timestamp or checksum)
                if await self.should_process(file_path):
                    await self.process_file(file_path)

    async def should_process(self, file_path: Path) -> bool:
        """Check if file should be processed"""

        # Check file fingerprint in ClickHouse
        file_hash = await self.file_processor._calculate_file_hash(file_path)

        if self.clickhouse_client:
            try:
                result = await self.clickhouse_client.fetch(
                    "SELECT file_hash FROM log_fingerprints WHERE file_hash = ?",
                    params=[file_hash]
                )
                if result:
                    logger.info(f"File {file_path.name} already processed")
                    return False
            except Exception:
                pass

        return True

    async def process_file(self, file_path: Path):
        """Process single log file"""

        logger.info(f"Processing file: {file_path.name}")
        start_time = datetime.utcnow()

        total_logs = 0
        by_type = {"network": 0, "server": 0, "k8s": 0}

        # Process file in chunks
        async for chunk in self.file_processor.process_file(str(file_path)):
            total_logs += len(chunk)

            # Count by type
            for log in chunk:
                log_type = log.get("log_type", "server")
                by_type[log_type] = by_type.get(log_type, 0) + 1

            # Insert to ClickHouse
            await self.insert_logs(chunk)

            logger.info(f"Processed {total_logs} logs from {file_path.name}")

        # Save fingerprint
        file_hash = await self.file_processor._calculate_file_hash(file_path)
        await self.save_fingerprint(file_path, file_hash, total_logs, start_time)

        logger.info(f"File {file_path.name} processed: {total_logs} logs "
                   f"(network: {by_type['network']}, server: {by_type['server']}, k8s: {by_type['k8s']})")

    async def insert_logs(self, logs: list):
        """Insert logs to ClickHouse"""

        if not self.clickhouse_client:
            # Write to parsed files instead
            await self.write_to_parsed_files(logs)
            return

        try:
            # Prepare batch insert
            values = []
            for log in logs:
                values.append((
                    log.get("timestamp"),
                    log.get("log_type", "server"),
                    log.get("source_host") or log.get("hostname") or log.get("device_name"),
                    log.get("source_ip") or log.get("host_ip"),
                    log.get("facility"),
                    log.get("severity") or log.get("log_level"),
                    log.get("program"),
                    log.get("message"),
                    log.get("raw_message"),
                    json.dumps(log.get("parsed_fields", {})),
                    log.get("file_id"),
                ))

            # Insert batch
            await self.clickhouse_client.insert(
                "logs",
                values,
                column_names=[
                    "timestamp", "log_type", "source_host", "source_ip",
                    "facility", "severity", "program", "message",
                    "raw_message", "parsed_fields", "file_id"
                ]
            )

        except Exception as e:
            logger.error(f"ClickHouse insert error: {e}")
            # Fallback to file storage
            await self.write_to_parsed_files(logs)

    async def write_to_parsed_files(self, logs: list):
        """Write logs to parsed files as fallback"""

        # Separate by log type
        by_type = {}
        for log in logs:
            log_type = log.get("log_type", "server")
            if log_type not in by_type:
                by_type[log_type] = []
            by_type[log_type].append(log)

        # Write to separate files
        for log_type, type_logs in by_type.items():
            output_dir = Path(settings.parsed_log_dir) / log_type
            output_dir.mkdir(parents=True, exist_ok=True)

            output_file = output_dir / f"parsed_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"

            with open(output_file, 'w') as f:
                for log in type_logs:
                    f.write(json.dumps(log) + '\n')

    async def save_fingerprint(self, file_path: Path, file_hash: str,
                               log_count: int, start_time: datetime):
        """Save file fingerprint"""

        duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

        if self.clickhouse_client:
            try:
                await self.clickhouse_client.insert(
                    "log_fingerprints",
                    [(file_hash, file_path.name, file_path.stat().st_size,
                      datetime.utcnow(), log_count, duration_ms)],
                    column_names=["file_hash", "file_name", "file_size",
                                 "processed_time", "log_count", "processing_duration_ms"]
                )
            except Exception as e:
                logger.error(f"Failed to save fingerprint: {e}")

    async def process_directory(self, directory: str, recursive: bool = False):
        """Process all files in directory"""

        dir_path = Path(directory)

        if recursive:
            files = list(dir_path.rglob('*'))
        else:
            files = list(dir_path.glob('*'))

        for file_path in files:
            if file_path.is_file() and not file_path.name.startswith('.'):
                await self.process_file(file_path)


async def main():
    """Main entry point"""

    worker = LogProcessorWorker()
    await worker.initialize()

    try:
        await worker.start()
    except KeyboardInterrupt:
        await worker.stop()


if __name__ == "__main__":
    asyncio.run(main())