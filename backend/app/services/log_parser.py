"""
Log Parsing Engine - Multi-format log parser for ELK logs
Supports: Network devices (Cisco, Huawei, Juniper), Servers (Syslog, Applications), K8S
"""

import asyncio
import gzip
import tarfile
import zipfile
import hashlib
import re
import json
from pathlib import Path
from typing import Optional, Dict, Any, List, AsyncGenerator, Tuple
from datetime import datetime
import logging

try:
    import polars as pl
except ImportError:
    import pandas as pd
    pl = None

from app.config import settings
from app.utils.logging import get_logger
from app.utils.helpers import generate_uuid, ensure_directory

logger = get_logger(__name__)


# Log type patterns for classification
LOG_PATTERNS = {
    "network": {
        "cisco": [
            r'%\w+-\d+-\w+:',  # Cisco IOS format
            r'CISCO',
            r'Switch|Router',
        ],
        "huawei": [
            r'%%\w+:',
            r'HUAWEI',
            r'VRP',
        ],
        "juniper": [
            r'\w+\[\d+\]',
            r'JUNOS',
            r'Juniper',
        ],
        "firewall": [
            r'FW_|FIREWALL',
            r'ASA|PIX',
            r' PaloAlto|PA-',
        ],
    },
    "server": {
        "syslog": [
            r'^\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}',  # Standard syslog
            r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}',  # ISO format
        ],
        "apache": [
            r'\[\d{2}/\w{3}/\d{4}:\d{2}:\d{2}:\d{2}',
            r'Apache|nginx',
        ],
        "mysql": [
            r'\d{6}\s+\d{2}:\d{2}:\d{2}',
            r'MySQL|mariadb',
        ],
        "auth": [
            r'authentication|login|ssh|sudo',
            r'FAILED|SUCCESS|session',
        ],
    },
    "k8s": {
        "pod": [
            r'namespace=|pod=|container=',
            r'kubectl|kubelet|kube-apiserver',
            r'\[k8s\]',
        ],
        "event": [
            r'Event:|Type:|Reason:',
            r'Created|Deleted|Scheduled',
        ],
        "audit": [
            r'audit.k8s.io',
            r'user=|group=|resource=',
        ],
    }
}


class LogParser:
    """Multi-format log parser"""

    def __init__(self):
        self.parsers = {
            "network": self._parse_network_log,
            "server": self._parse_server_log,
            "k8s": self._parse_k8s_log,
        }

    def classify_log_type(self, log_line: str) -> Tuple[str, str]:
        """Classify log line into type and subtype"""
        log_line_lower = log_line.lower()

        for log_type, subtypes in LOG_PATTERNS.items():
            for subtype, patterns in subtypes.items():
                for pattern in patterns:
                    if re.search(pattern, log_line, re.IGNORECASE):
                        return log_type, subtype

        # Default classification based on content
        if any(kw in log_line_lower for kw in ['error', 'warning', 'critical']):
            return "server", "general"
        if any(kw in log_line_lower for kw in ['pod', 'container', 'namespace']):
            return "k8s", "pod"
        if any(kw in log_line_lower for kw in ['eth', 'interface', 'vlan', 'switch']):
            return "network", "generic"

        return "server", "general"

    def parse_line(self, log_line: str) -> Dict[str, Any]:
        """Parse a single log line"""
        log_type, subtype = self.classify_log_type(log_line)

        # Use specific parser
        parser_func = self.parsers.get(log_type, self._parse_generic_log)
        parsed = parser_func(log_line)

        # Add classification
        parsed["log_type"] = log_type
        parsed["subtype"] = subtype
        parsed["raw_message"] = log_line
        parsed["log_hash"] = hashlib.md5(log_line.encode()).hexdigest()[:16]

        return parsed

    def _parse_network_log(self, log_line: str) -> Dict[str, Any]:
        """Parse network device log"""
        result = {
            "timestamp": None,
            "device_name": None,
            "device_ip": None,
            "log_level": "INFO",
            "event_type": None,
            "message": log_line,
            "parsed_fields": {}
        }

        # Cisco format: timestamp: %FACILITY-SEVERITY-MNEMONIC: message
        cisco_match = re.search(
            r'(?P<ts>\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s*:\s*'
            r'%(?P<facility>\w+)-(?P<severity>\d+)-(?P<mnemonic>\w+):\s*'
            r'(?P<msg>.+)',
            log_line
        )
        if cisco_match:
            result["timestamp"] = self._parse_timestamp(cisco_match.group('ts'))
            result["parsed_fields"]["facility"] = cisco_match.group('facility')
            severity_map = {0: "EMERGENCY", 1: "ALERT", 2: "CRITICAL",
                           3: "ERROR", 4: "WARNING", 5: "NOTIFICATION",
                           6: "INFORMATIONAL", 7: "DEBUG"}
            result["log_level"] = severity_map.get(int(cisco_match.group('severity')), "INFO")
            result["parsed_fields"]["mnemonic"] = cisco_match.group('mnemonic')
            result["message"] = cisco_match.group('msg')

        # Huawei VRP format
        huawei_match = re.search(
            r'%(?P<ts>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+'
            r'%%(?P<module>\w+)@(?P<host>[^:]+):\s*'
            r'(?:Severity=(?P<sev>\w+))?\s*'
            r'(?P<msg>.+)',
            log_line
        )
        if huawei_match:
            result["timestamp"] = self._parse_timestamp(huawei_match.group('ts'))
            result["device_name"] = huawei_match.group('host')
            result["parsed_fields"]["module"] = huawei_match.group('module')
            result["log_level"] = huawei_match.group('sev') or "INFO"
            result["message"] = huawei_match.group('msg')

        # Juniper JunOS format
        juniper_match = re.search(
            r'(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+[+-]\d{2})\s+'
            r'(?P<host>\w+)\s+'
            r'(?P<process>\w+)\[(?P<pid>\d+)\]:\s*'
            r'(?P<msg>.+)',
            log_line
        )
        if juniper_match:
            result["timestamp"] = self._parse_timestamp(juniper_match.group('ts'))
            result["device_name"] = juniper_match.group('host')
            result["parsed_fields"]["process"] = juniper_match.group('process')
            result["message"] = juniper_match.group('msg')

        return result

    def _parse_server_log(self, log_line: str) -> Dict[str, Any]:
        """Parse server/syslog log"""
        result = {
            "timestamp": None,
            "hostname": None,
            "host_ip": None,
            "facility": None,
            "severity": "INFO",
            "program": None,
            "pid": None,
            "message": log_line,
            "parsed_fields": {}
        }

        # Standard syslog RFC 3164
        syslog_match = re.search(
            r'(?P<ts>\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+'
            r'(?P<host>\S+)\s+'
            r'(?P<prog>[^:\[\]]+?)(?:\[(?P<pid>\d+)\])?:\s*'
            r'(?P<msg>.+)',
            log_line
        )
        if syslog_match:
            result["timestamp"] = self._parse_timestamp(syslog_match.group('ts'))
            result["hostname"] = syslog_match.group('host')
            result["program"] = syslog_match.group('prog').strip()
            result["pid"] = syslog_match.group('pid')
            result["message"] = syslog_match.group('msg')

        # ISO format syslog RFC 5424
        iso_match = re.search(
            r'(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)\s+'
            r'(?P<host>\S+)\s+'
            r'(?P<prog>\S+?)(?:\[(?P<pid>\d+)\])?:\s*'
            r'(?P<msg>.+)',
            log_line
        )
        if iso_match:
            result["timestamp"] = self._parse_timestamp(iso_match.group('ts'))
            result["hostname"] = iso_match.group('host')
            result["program"] = iso_match.group('prog')
            result["message"] = iso_match.group('msg')

        # Detect severity from keywords
        lower_msg = log_line.lower()
        if 'error' in lower_msg or 'err' in lower_msg:
            result["severity"] = "ERROR"
        elif 'warning' in lower_msg or 'warn' in lower_msg:
            result["severity"] = "WARNING"
        elif 'critical' in lower_msg or 'crit' in lower_msg:
            result["severity"] = "CRITICAL"
        elif 'fatal' in lower_msg:
            result["severity"] = "CRITICAL"
        elif 'debug' in lower_msg:
            result["severity"] = "DEBUG"

        return result

    def _parse_k8s_log(self, log_line: str) -> Dict[str, Any]:
        """Parse Kubernetes log"""
        result = {
            "timestamp": None,
            "namespace": None,
            "pod_name": None,
            "container_name": None,
            "node_name": None,
            "log_level": "INFO",
            "message": log_line,
            "parsed_fields": {}
        }

        # K8s pod log format
        pod_match = re.search(
            r'(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z)\s+'
            r'(?:stdout|stderr)\s+[FPIWE]\s+'
            r'(?P<msg>.+)',
            log_line
        )
        if pod_match:
            result["timestamp"] = self._parse_timestamp(pod_match.group('ts'))
            result["message"] = pod_match.group('msg')

        # K8s event log
        event_match = re.search(
            r'(?P<ts>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+'
            r'(?P<type>\w+)\s+'
            r'(?P<reason>\w+)\s+'
            r'(?:Object:\s*(?P<object>\S+))?\s*'
            r'(?P<msg>.+)',
            log_line
        )
        if event_match:
            result["timestamp"] = self._parse_timestamp(event_match.group('ts'))
            result["parsed_fields"]["event_type"] = event_match.group('type')
            result["parsed_fields"]["reason"] = event_match.group('reason')
            result["message"] = event_match.group('msg')

        # K8s audit log (JSON)
        if log_line.startswith('{') and 'audit.k8s.io' in log_line:
            try:
                data = json.loads(log_line)
                result["timestamp"] = self._parse_timestamp(data.get('stageTimestamp', ''))
                result["parsed_fields"]["user"] = data.get('user', {}).get('username', '')
                result["parsed_fields"]["verb"] = data.get('verb', '')
                result["parsed_fields"]["resource"] = data.get('objectRef', {}).get('resource', '')
                result["message"] = json.dumps(data)
            except json.JSONDecodeError:
                pass

        # Extract namespace/pod from message
        ns_match = re.search(r'namespace[=:]\s*(\S+)', log_line)
        if ns_match:
            result["namespace"] = ns_match.group(1)

        pod_match = re.search(r'pod[=:]\s*(\S+)', log_line)
        if pod_match:
            result["pod_name"] = pod_match.group(1)

        return result

    def _parse_generic_log(self, log_line: str) -> Dict[str, Any]:
        """Generic log parser for unknown formats"""
        result = {
            "timestamp": None,
            "log_level": "INFO",
            "message": log_line,
            "parsed_fields": {}
        }

        # Try to extract timestamp
        ts_patterns = [
            r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})',
            r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})',
            r'(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})',
            r'(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2})',
        ]

        for pattern in ts_patterns:
            match = re.search(pattern, log_line)
            if match:
                result["timestamp"] = self._parse_timestamp(match.group(1))
                break

        # Extract severity
        if re.search(r'\b(ERROR|ERR|FAIL|CRITICAL|CRIT|FATAL)\b', log_line, re.I):
            result["log_level"] = "ERROR"
        elif re.search(r'\b(WARNING|WARN)\b', log_line, re.I):
            result["log_level"] = "WARNING"
        elif re.search(r'\b(DEBUG|TRACE)\b', log_line, re.I):
            result["log_level"] = "DEBUG"

        return result

    def _parse_timestamp(self, ts_str: str) -> Optional[datetime]:
        """Parse timestamp from various formats"""
        if not ts_str:
            return None

        formats = [
            '%Y-%m-%dT%H:%M:%S.%fZ',
            '%Y-%m-%dT%H:%M:%S.%f',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%d %H:%M:%S',
            '%b %d %H:%M:%S',
            '%d/%m/%Y %H:%M:%S',
            '%Y-%m-%dT%H:%M:%S%z',
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(ts_str.strip(), fmt)
                # Handle year-less timestamps ( syslog format)
                if dt.year == 1900:
                    dt = dt.replace(year=datetime.now().year)
                return dt
            except ValueError:
                continue

        return None


class LogFileProcessor:
    """Process ELK log files (gzip, tar, zip)"""

    def __init__(self, parser: LogParser):
        self.parser = parser
        self.processed_hashes: Dict[str, str] = {}  # file_hash -> processed_time

    async def process_file(
        self,
        file_path: str,
        chunk_size: int = 10000,
        progress_callback: Optional[callable] = None
    ) -> AsyncGenerator[List[Dict], None]:
        """
        Process log file and yield chunks of parsed logs

        Args:
            file_path: Path to log file (supports .gz, .tar, .tar.gz, .zip)
            chunk_size: Number of logs per chunk
            progress_callback: Callback for progress updates

        Yields:
            List of parsed log dictionaries
        """

        file_path = Path(file_path)
        file_hash = await self._calculate_file_hash(file_path)

        # Check if already processed (deduplication)
        if file_hash in self.processed_hashes:
            logger.info(f"File {file_path.name} already processed, skipping duplicates")
            return

        total_lines = 0
        chunk = []

        # Open file based on format
        async for line in self._read_file_lines(file_path):
            total_lines += 1

            if line.strip():
                parsed = self.parser.parse_line(line.strip())
                parsed["file_id"] = file_hash
                chunk.append(parsed)

                if len(chunk) >= chunk_size:
                    if progress_callback:
                        await progress_callback(total_lines, len(chunk))
                    yield chunk
                    chunk = []

        # Yield remaining logs
        if chunk:
            if progress_callback:
                await progress_callback(total_lines, len(chunk))
            yield chunk

        # Mark as processed
        self.processed_hashes[file_hash] = datetime.utcnow().isoformat()
        logger.info(f"Processed {file_path.name}: {total_lines} lines")

    async def _read_file_lines(self, file_path: Path) -> AsyncGenerator[str, None]:
        """Read lines from various file formats"""

        ext = file_path.suffix.lower()

        if ext == '.gz':
            # Gzip single file
            with gzip.open(file_path, 'rt', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    yield line

        elif ext in ['.tar', '.tgz'] or (ext == '.gz' and '.tar' in file_path.name.lower()):
            # Tar archive (possibly gzipped)
            mode = 'r:gz' if ext in ['.tgz', '.gz'] else 'r:'
            with tarfile.open(file_path, mode) as tar:
                for member in tar.getmembers():
                    if member.isfile() and not member.name.startswith('.'):
                        try:
                            f = tar.extractfile(member)
                            if f:
                                for line in f:
                                    yield line.decode('utf-8', errors='ignore')
                        except Exception as e:
                            logger.warning(f"Error reading {member.name}: {e}")

        elif ext == '.zip':
            # Zip archive
            with zipfile.ZipFile(file_path, 'r') as z:
                for name in z.namelist():
                    if not name.startswith('.') and not name.endswith('/'):
                        try:
                            with z.open(name) as f:
                                for line in f:
                                    yield line.decode('utf-8', errors='ignore')
                        except Exception as e:
                            logger.warning(f"Error reading {name}: {e}")

        else:
            # Plain text file
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    yield line

    async def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA256 hash of file for deduplication"""
        sha256 = hashlib.sha256()
        sha256.update(str(file_path).encode())
        sha256.update(str(file_path.stat().st_size).encode())

        # Sample first 1MB for quick hash
        try:
            with open(file_path, 'rb') as f:
                chunk = f.read(1024 * 1024)
                sha256.update(chunk)
        except Exception:
            pass

        return sha256.hexdigest()[:32]

    async def estimate_line_count(self, file_path: Path) -> int:
        """Estimate number of lines in file"""
        try:
            file_size = file_path.stat().st_size

            # Sample average line length
            with open(file_path, 'rb') as f:
                sample = f.read(min(file_size, 10000))

            avg_line_length = len(sample.split(b'\n')[0]) + 1 if sample else 100

            return int(file_size / avg_line_length)
        except Exception:
            return 100000  # Default estimate


class LogSampler:
    """Sample logs for AI analysis to fit token limits"""

    def __init__(self, max_tokens: int = 50000):
        self.max_tokens = max_tokens

    def sample_for_analysis(
        self,
        logs: List[Dict],
        strategy: str = "smart"
    ) -> str:
        """
        Sample logs to fit within token limit

        Strategies:
        - smart: Balance time coverage + severity prioritization
        - errors_only: Only error/warning logs
        - recent: Most recent logs
        - uniform: Uniform random sampling
        """

        if strategy == "errors_only":
            sampled = [l for l in logs if l.get('severity') in ['ERROR', 'CRITICAL', 'WARNING']]
        elif strategy == "recent":
            # Sort by timestamp and take most recent
            sorted_logs = sorted(logs, key=lambda x: x.get('timestamp') or datetime.min)
            sampled = sorted_logs[-1000:]
        elif strategy == "uniform":
            # Uniform random sampling
            import random
            sample_size = min(len(logs), 2000)
            sampled = random.sample(logs, sample_size) if len(logs) > sample_size else logs
        else:
            # Smart sampling
            sampled = self._smart_sample(logs)

        # Format for AI
        formatted = self._format_logs_for_ai(sampled)

        # Trim if too long
        estimated_tokens = len(formatted) // 4
        if estimated_tokens > self.max_tokens:
            formatted = formatted[:self.max_tokens * 4]

        return formatted

    def _smart_sample(self, logs: List[Dict]) -> List[Dict]:
        """Smart sampling: prioritize errors + time coverage"""
        # Separate by severity
        errors = [l for l in logs if l.get('severity') in ['ERROR', 'CRITICAL']]
        warnings = [l for l in logs if l.get('severity') == 'WARNING']
        others = [l for l in logs if l.get('severity') not in ['ERROR', 'CRITICAL', 'WARNING']]

        # Take all errors (up to 500)
        sampled = errors[:500]

        # Add warnings (up to 300)
        sampled.extend(warnings[:300])

        # Add time-stratified sample of others
        if others:
            # Sort by timestamp
            sorted_others = sorted(others, key=lambda x: x.get('timestamp') or datetime.min)

            # Take samples from different time periods
            n_periods = min(10, len(sorted_others))
            period_size = len(sorted_others) // n_periods

            for i in range(n_periods):
                start = i * period_size
                end = min(start + period_size, len(sorted_others))
                if start < end:
                    # Take 50 from each period
                    sampled.extend(sorted_others[start:end][:50])

        return sampled[:2000]  # Cap total

    def _format_logs_for_ai(self, logs: List[Dict]) -> str:
        """Format logs for AI analysis"""
        lines = []
        for log in logs:
            ts = log.get('timestamp', '').strftime('%Y-%m-%d %H:%M:%S') if log.get('timestamp') else ''
            severity = log.get('severity') or log.get('log_level', 'INFO')
            source = log.get('hostname') or log.get('device_name') or log.get('source_host', 'unknown')
            msg = log.get('message', log.get('raw_message', ''))[:200]

            lines.append(f"[{ts}] [{severity}] [{source}] {msg}")

        return '\n'.join(lines)


# Global instances
log_parser = LogParser()
file_processor = LogFileProcessor(log_parser)
log_sampler = LogSampler()


def get_log_parser() -> LogParser:
    return log_parser

def get_file_processor() -> LogFileProcessor:
    return file_processor

def get_log_sampler() -> LogSampler:
    return log_sampler