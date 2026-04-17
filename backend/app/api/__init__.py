"""Package initialization for API routes"""

from app.api.auth import router as auth_router
from app.api.logs import router as logs_router
from app.api.analysis import router as analysis_router
from app.api.reports import router as reports_router
from app.api.admin import router as admin_router
from app.api.security import router as security_router
from app.api.backup import router as backup_router