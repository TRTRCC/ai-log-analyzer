"""
Log Query API Routes
"""

from datetime import datetime, timedelta
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_session
from app.models import LogType, User, UserRole
from app.api.auth import get_current_user
from app.services.auth import AuthService, auth_service
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


# Request/Response models
class LogQueryRequest(BaseModel):
    time_range_start: Optional[datetime] = None
    time_range_end: Optional[datetime] = None
    log_type: str = "all"
    severity: Optional[str] = None
    source_host: Optional[str] = None
    keyword: Optional[str] = None
    limit: int = Field(default=50, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class LogEntry(BaseModel):
    timestamp: Optional[datetime] = None
    log_type: str
    source_host: Optional[str] = None
    source_ip: Optional[str] = None
    severity: str
    program: Optional[str] = None
    message: str
    raw_message: str
    parsed_fields: dict = {}


class LogQueryResponse(BaseModel):
    logs: List[LogEntry]
    total: int
    limit: int
    offset: int


class LogStats(BaseModel):
    total_count: int
    error_count: int
    warning_count: int
    info_count: int
    unique_hosts: int


# Helper for permission check
def check_log_access(current_user: dict, log_type: str) -> bool:
    """Check if user can access specific log type"""

    user_role = current_user.get("role")

    if user_role in ["super_admin", "audit_admin"]:
        return True

    if user_role == "network_user" and log_type == "network":
        return True
    if user_role == "server_user" and log_type == "server":
        return True
    if user_role == "k8s_user" and log_type == "k8s":
        return True

    return False


# Routes
@router.get("/query", response_model=LogQueryResponse)
async def query_logs(
    time_range_start: Optional[datetime] = Query(None),
    time_range_end: Optional[datetime] = Query(None),
    log_type: str = Query(default="all"),
    severity: Optional[str] = Query(None),
    source_host: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Query logs with filters"""

    # Check permission for log type
    if log_type != "all" and not check_log_access(current_user, log_type):
        raise HTTPException(
            status_code=403,
            detail=f"Access denied to {log_type} logs"
        )

    # For non-admin users, force their log type
    user_role = current_user.get("role")
    if user_role not in ["super_admin", "audit_admin"]:
        if user_role == "network_user":
            log_type = "network"
        elif user_role == "server_user":
            log_type = "server"
        elif user_role == "k8s_user":
            log_type = "k8s"

    # Query ClickHouse (mock response for now)
    # In production, this would query ClickHouse directly
    logs = await query_clickhouse_logs(
        time_range_start,
        time_range_end,
        log_type,
        severity,
        source_host,
        keyword,
        limit,
        offset
    )

    return LogQueryResponse(
        logs=logs,
        total=len(logs) + offset,  # Placeholder
        limit=limit,
        offset=offset
    )


@router.get("/stats", response_model=LogStats)
async def get_log_stats(
    time_range_start: Optional[datetime] = Query(None),
    time_range_end: Optional[datetime] = Query(None),
    log_type: str = Query(default="all"),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Get log statistics"""

    # Check permissions
    if log_type != "all" and not check_log_access(current_user, log_type):
        raise HTTPException(status_code=403, detail="Access denied")

    # Force log type for non-admin
    user_role = current_user.get("role")
    if user_role not in ["super_admin", "audit_admin"]:
        type_map = {
            "network_user": "network",
            "server_user": "server",
            "k8s_user": "k8s"
        }
        log_type = type_map.get(user_role, log_type)

    # Query stats from ClickHouse (mock)
    return await get_clickhouse_stats(time_range_start, time_range_end, log_type)


@router.get("/hosts")
async def get_log_hosts(
    log_type: str = Query(default="all"),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Get list of source hosts"""

    # Check permissions and get appropriate hosts
    hosts = await get_available_hosts(current_user, log_type)

    return {"hosts": hosts}


@router.get("/entry/{log_hash}")
async def get_log_entry(
    log_hash: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Get single log entry details"""

    log = await get_log_by_hash(log_hash)

    if not log:
        raise HTTPException(status_code=404, detail="Log entry not found")

    # Check permission
    if not check_log_access(current_user, log.get("log_type", "all")):
        raise HTTPException(status_code=403, detail="Access denied")

    return log


@router.get("/timeline")
async def get_log_timeline(
    time_range_start: datetime = Query(...),
    time_range_end: datetime = Query(...),
    log_type: str = Query(default="all"),
    current_user: dict = Depends(get_current_user)
):
    """Get log count timeline for charts"""

    timeline = await get_clickhouse_timeline(
        time_range_start,
        time_range_end,
        log_type,
        current_user
    )

    return {"timeline": timeline}


# Mock implementations (replace with real ClickHouse queries)
async def query_clickhouse_logs(
    time_start, time_end, log_type, severity, source_host, keyword, limit, offset
) -> List[LogEntry]:

    # In production: use aiochclient or clickhouse-driver
    # This is a mock response

    if not time_start:
        time_start = datetime.utcnow() - timedelta(hours=24)
    if not time_end:
        time_end = datetime.utcnow()

    # Mock data
    mock_logs = []
    for i in range(min(limit, 10)):
        mock_logs.append(LogEntry(
            timestamp=datetime.utcnow() - timedelta(minutes=i * 5),
            log_type=log_type if log_type != "all" else "server",
            source_host=f"host-{i}",
            source_ip=f"192.168.1.{i}",
            severity="INFO" if i % 3 != 0 else "ERROR",
            program="system",
            message=f"Sample log message {i}",
            raw_message=f"Raw log line {i}",
            parsed_fields={}
        ))

    return mock_logs


async def get_clickhouse_stats(time_start, time_end, log_type) -> LogStats:
    """Get statistics from ClickHouse"""

    return LogStats(
        total_count=100000,
        error_count=500,
        warning_count=1000,
        info_count=98500,
        unique_hosts=50
    )


async def get_available_hosts(current_user: dict, log_type: str) -> List[str]:
    """Get available hosts based on user permissions"""

    # Mock response
    hosts = ["web-01", "web-02", "db-01", "switch-01", "k8s-master"]

    return hosts


async def get_log_by_hash(log_hash: str) -> Optional[dict]:
    """Get log by hash"""

    # Mock
    return {
        "timestamp": datetime.utcnow(),
        "log_type": "server",
        "source_host": "web-01",
        "severity": "ERROR",
        "message": "Sample error message",
        "raw_message": "Full raw log line",
        "parsed_fields": {}
    }


async def get_clickhouse_timeline(time_start, time_end, log_type, current_user) -> List[dict]:
    """Get timeline data for charts"""

    # Mock hourly timeline
    timeline = []
    hours = int((time_end - time_start).total_seconds() / 3600)

    for i in range(min(hours, 24)):
        timeline.append({
            "hour": (time_start + timedelta(hours=i)).isoformat(),
            "total": 1000 + i * 100,
            "errors": 10 + i
        })

    return timeline