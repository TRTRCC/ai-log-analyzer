"""
Utility functions and helpers
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TypeVar, Generic
from pathlib import Path
import json


def generate_uuid() -> str:
    """Generate a UUID string"""
    return str(uuid.uuid4())


def get_utc_now() -> datetime:
    """Get current UTC datetime"""
    return datetime.now(timezone.utc)


def ensure_directory(path: str) -> Path:
    """Ensure a directory exists"""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def safe_json_loads(data: str, default: Any = None) -> Any:
    """Safe JSON loading with default value"""
    try:
        return json.loads(data)
    except (json.JSONDecodeError, TypeError):
        return default


def safe_json_dumps(data: Any, default: str = "{}") -> str:
    """Safe JSON dumping with default value"""
    try:
        return json.dumps(data, default=str)
    except (TypeError, ValueError):
        return default


def chunk_list(lst: List[Any], chunk_size: int) -> List[List[Any]]:
    """Split a list into chunks"""
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]


def flatten_dict(d: Dict[str, Any], parent_key: str = '', sep: str = '.') -> Dict[str, Any]:
    """Flatten a nested dictionary"""
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


def format_bytes(size: int) -> str:
    """Format bytes to human-readable string"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} PB"


def format_duration(seconds: float) -> str:
    """Format duration in seconds to human-readable string"""
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    elif seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"


class Result(Generic[TypeVar('T')]):
    """Result type for error handling"""

    def __init__(self, success: bool, value: Optional[TypeVar('T')] = None, error: Optional[str] = None):
        self.success = success
        self.value = value
        self.error = error

    @classmethod
    def ok(cls, value: TypeVar('T') = None) -> 'Result':
        return cls(success=True, value=value)

    @classmethod
    def fail(cls, error: str) -> 'Result':
        return cls(success=False, error=error)

    def is_ok(self) -> bool:
        return self.success

    def is_fail(self) -> bool:
        return not self.success

    def get_or_raise(self) -> TypeVar('T'):
        if not self.success:
            raise ValueError(self.error)
        return self.value


def extract_timestamp_from_log(log_line: str) -> Optional[datetime]:
    """Try to extract timestamp from a log line"""
    # Common log timestamp patterns
    patterns = [
        # ISO format: 2024-01-17T10:30:45
        r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})',
        # Standard: Jan 17 10:30:45
        r'(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})',
        # Syslog: 2024-01-17 10:30:45
        r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})',
    ]

    import re
    for pattern in patterns:
        match = re.search(pattern, log_line)
        if match:
            try:
                # Try to parse the matched timestamp
                ts_str = match.group(1)
                # This is a simplified parser - would need more robust parsing
                return datetime.now()  # Placeholder
            except ValueError:
                continue
    return None


def estimate_tokens(text: str) -> int:
    """Estimate token count for text (rough approximation)"""
    # Rough estimate: ~4 characters per token for English
    return len(text) // 4