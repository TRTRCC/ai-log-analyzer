"""
Intrusion Detection Service - 等保三入侵检测与请求过滤
"""

import re
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from collections import defaultdict
import redis

from sqlalchemy.orm import Session
from app.models.user import SecurityEvent, User
from app.config import settings


class IntrusionDetectionService:
    """入侵检测服务"""

    # 检测规则配置
    FAILED_LOGIN_THRESHOLD = 5  # 失败登录阈值
    FAILED_LOGIN_WINDOW_MINUTES = 15  # 时间窗口

    ABNORMAL_ACCESS_HOURS = [0, 1, 2, 3, 4, 5]  # 异常访问时段

    # 恶意模式检测
    MALICIOUS_PATTERNS = [
        # SQL注入模式
        r"(\%27)|(\')|(\-\-)|(\%23)|(#)",
        r"((\%3D)|(=))[^\n]*((\%27)|(\')|(\-\-)|(\%3B)|(;))",
        r"\w*((\%27)|(\'))((\%6F)|o|(\%4F))((\%72)|r|(\%52))",
        r"((\%27)|(\'))union",

        # XSS模式
        r"((\%3C)|<)((\%2F)|\/)*[a-z0-9\%]+((\%3E)|>)",
        r"((\%3C)|<)[a-z0-9\%]+.*((\%3E)|>)",
        r"javascript:",
        r"onerror\s*=",
        r"onload\s*=",

        # 路径遍历
        r"\.\./",
        r"\.\.\\",
        r"\%2e\%2e",

        # 命令注入
        r";.*cat",
        r";.*ls",
        r";.*rm",
        r"\|.*cat",
        r"`.*`",
        r"\$\(.*\)",
    ]

    # 禁止访问的敏感路径
    SENSITIVE_PATHS = [
        "/.env",
        "/config",
        "/admin/config",
        "/backup",
        "/logs/audit",
        "/system",
        "/.git",
        "/database",
    ]

    def __init__(self, db: Session, redis_client: redis.Redis):
        self.db = db
        self.redis = redis_client
        self._compile_patterns()

    def _compile_patterns(self):
        """预编译检测模式"""
        self.compiled_patterns = [re.compile(p, re.IGNORECASE) for p in self.MALICIOUS_PATTERNS]

    def check_request(self, request_data: dict) -> dict:
        """检查请求是否恶意"""
        threats = []

        # 检查路径
        path = request_data.get('path', '')
        threats.extend(self._check_path(path))

        # 检查查询参数
        query = request_data.get('query', '')
        threats.extend(self._check_query(query))

        # 检查请求体
        body = request_data.get('body', '')
        if body:
            threats.extend(self._check_body(body))

        # 检查headers
        headers = request_data.get('headers', {})
        threats.extend(self._check_headers(headers))

        # 检查是否访问敏感路径
        for sensitive in self.SENSITIVE_PATHS:
            if sensitive in path:
                threats.append({
                    "type": "sensitive_path_access",
                    "severity": "high",
                    "path": path,
                    "matched": sensitive
                })

        return {
            "malicious": len(threats) > 0,
            "threats": threats,
            "severity": max([t['severity'] for t in threats], default='none'),
            "action": self._determine_action(threats)
        }

    def _check_path(self, path: str) -> List[dict]:
        """检查路径"""
        threats = []
        for pattern in self.compiled_patterns:
            if pattern.search(path):
                threats.append({
                    "type": "malicious_path",
                    "severity": "high",
                    "pattern": pattern.pattern,
                    "path": path
                })
        return threats

    def _check_query(self, query: str) -> List[dict]:
        """检查查询参数"""
        threats = []
        for pattern in self.compiled_patterns:
            if pattern.search(query):
                threats.append({
                    "type": "malicious_query",
                    "severity": "high",
                    "pattern": pattern.pattern,
                    "query": query[:100]  # 限制长度
                })
        return threats

    def _check_body(self, body: str) -> List[dict]:
        """检查请求体"""
        threats = []
        # 限制检查长度避免性能问题
        check_body = body[:5000] if len(body) > 5000 else body

        for pattern in self.compiled_patterns:
            if pattern.search(check_body):
                threats.append({
                    "type": "malicious_body",
                    "severity": "high",
                    "pattern": pattern.pattern
                })
        return threats

    def _check_headers(self, headers: dict) -> List[dict]:
        """检查headers"""
        threats = []

        # 检查可疑User-Agent
        ua = headers.get('user-agent', '')
        suspicious_ua_patterns = [
            r"sqlmap",
            r"nikto",
            r"nmap",
            r"masscan",
            r"scanner",
            r"exploit",
            r"hack",
            r"curl/.*python",
        ]

        for pattern in suspicious_ua_patterns:
            if re.search(pattern, ua, re.IGNORECASE):
                threats.append({
                    "type": "suspicious_user_agent",
                    "severity": "medium",
                    "pattern": pattern,
                    "user_agent": ua
                })

        # 检查可疑Referer
        referer = headers.get('referer', '')
        if referer:
            for pattern in self.compiled_patterns:
                if pattern.search(referer):
                    threats.append({
                        "type": "malicious_referer",
                        "severity": "medium",
                        "referer": referer[:100]
                    })

        return threats

    def _determine_action(self, threats: List[dict]) -> str:
        """确定处理动作"""
        if not threats:
            return "allow"

        severities = [t['severity'] for t in threats]

        if 'critical' in severities:
            return "block"
        if 'high' in severities:
            return "block_and_alert"
        if 'medium' in severities:
            return "alert"
        return "log"

    def detect_brute_force(self, ip: str, user_id: Optional[str] = None) -> dict:
        """检测暴力破解"""
        # 检查IP失败次数
        key = f"login_failures:{ip}"
        failures = self.redis.get(key)

        if failures:
            fail_count = int(failures)
            if fail_count >= self.FAILED_LOGIN_THRESHOLD:
                # 创建安全事件
                self._create_event(
                    event_type="brute_force_detected",
                    severity="critical",
                    source_ip=ip,
                    user_id=user_id,
                    details={"failure_count": fail_count},
                    action_taken="blocked"
                )

                return {
                    "detected": True,
                    "type": "brute_force",
                    "severity": "critical",
                    "failure_count": fail_count,
                    "action": "block"
                }

        return {"detected": False}

    def record_login_failure(self, ip: str, username: str):
        """记录登录失败"""
        key = f"login_failures:{ip}"
        self.redis.incr(key)
        self.redis.expire(key, self.FAILED_LOGIN_WINDOW_MINUTES * 60)

        # 同时追踪用户名失败
        user_key = f"user_failures:{username}"
        self.redis.incr(user_key)
        self.redis.expire(user_key, self.FAILED_LOGIN_WINDOW_MINUTES * 60)

    def check_abnormal_access(self, user: User, access_time: datetime) -> dict:
        """检测异常访问时间"""
        hour = access_time.hour

        if hour in self.ABNORMAL_ACCESS_HOURS:
            # 创建安全事件
            self._create_event(
                event_type="abnormal_time_access",
                severity="medium",
                user_id=str(user.id),
                details={
                    "access_hour": hour,
                    "access_time": access_time.isoformat(),
                    "username": user.username
                },
                action_taken="logged"
            )

            return {
                "abnormal": True,
                "type": "unusual_time",
                "severity": "medium",
                "hour": hour
            }

        return {"abnormal": False}

    def detect_multiple_sessions(self, user: User) -> dict:
        """检测异常多会话"""
        from app.models.user import UserSession

        active_sessions = self.db.query(UserSession).filter(
            UserSession.user_id == user.id,
            UserSession.is_active == True
        ).count()

        if active_sessions > 5:
            self._create_event(
                event_type="multiple_sessions",
                severity="medium",
                user_id=str(user.id),
                details={
                    "session_count": active_sessions,
                    "username": user.username
                },
                action_taken="logged"
            )

            return {
                "detected": True,
                "session_count": active_sessions,
                "severity": "medium"
            }

        return {"detected": False}

    def detect_location_anomaly(
        self,
        user: User,
        ip: str,
        previous_ips: List[str]
    ) -> dict:
        """检测地理位置异常"""
        # 简化版：检查IP是否与历史IP差异较大
        if not previous_ips:
            return {"anomaly": False}

        # 检查IP前缀变化
        current_prefix = ip.split('.')[0:2]
        for prev_ip in previous_ips[:10]:
            prev_prefix = prev_ip.split('.')[0:2]
            if current_prefix != prev_prefix:
                self._create_event(
                    event_type="location_change",
                    severity="medium",
                    user_id=str(user.id),
                    source_ip=ip,
                    details={
                        "current_ip": ip,
                        "previous_ips": previous_ips[:5]
                    },
                    action_taken="logged"
                )

                return {
                    "anomaly": True,
                    "type": "ip_change",
                    "severity": "medium"
                }

        return {"anomaly": False}

    def analyze_user_behavior(self, user_id: str, days: int = 7) -> dict:
        """分析用户行为模式"""
        from datetime import timedelta
        start_time = datetime.utcnow() - timedelta(days=days)

        # 获取用户操作记录
        from app.models.user import AuditLog
        logs = self.db.query(AuditLog).filter(
            AuditLog.user_id == user_id,
            AuditLog.created_at >= start_time
        ).all()

        if not logs:
            return {"baseline": None, "anomalies": []}

        # 构建行为基线
        action_counts = defaultdict(int)
        hourly_distribution = defaultdict(int)
        ip_addresses = set()

        for log in logs:
            action_counts[log.action] += 1
            hourly_distribution[log.created_at.hour] += 1
            if log.ip_address:
                ip_addresses.add(log.ip_address)

        baseline = {
            "total_actions": len(logs),
            "action_distribution": dict(action_counts),
            "hourly_distribution": dict(hourly_distribution),
            "ip_addresses": list(ip_addresses),
            "avg_actions_per_day": len(logs) / days
        }

        # 检测异常
        anomalies = []

        # 检查突然增加的活动
        if baseline["avg_actions_per_day"] > 50:
            anomalies.append({
                "type": "high_activity",
                "severity": "low",
                "value": baseline["avg_actions_per_day"]
            })

        # 检查异常时间活动占比
        abnormal_hour_count = sum(
            hourly_distribution[h] for h in self.ABNORMAL_ACCESS_HOURS
        )
        if abnormal_hour_count > len(logs) * 0.3:
            anomalies.append({
                "type": "abnormal_time_ratio",
                "severity": "medium",
                "ratio": abnormal_hour_count / len(logs)
            })

        return {
            "baseline": baseline,
            "anomalies": anomalies
        }

    def _create_event(
        self,
        event_type: str,
        severity: str,
        user_id: Optional[str] = None,
        source_ip: Optional[str] = None,
        details: Optional[dict] = None,
        action_taken: Optional[str] = None
    ) -> SecurityEvent:
        """创建安全事件"""
        event = SecurityEvent(
            event_type=event_type,
            severity=severity,
            user_id=user_id,
            source_ip=source_ip,
            details=details,
            action_taken=action_taken
        )
        self.db.add(event)
        self.db.commit()
        return event

    def get_threat_summary(self, hours: int = 24) -> dict:
        """获取威胁概要"""
        from datetime import timedelta
        start_time = datetime.utcnow() - timedelta(hours=hours)

        events = self.db.query(SecurityEvent).filter(
            SecurityEvent.created_at >= start_time
        ).all()

        severity_counts = defaultdict(int)
        type_counts = defaultdict(int)
        blocked_count = 0

        for event in events:
            severity_counts[event.severity] += 1
            type_counts[event.event_type] += 1
            if event.action_taken in ["blocked", "block_and_alert"]:
                blocked_count += 1

        return {
            "period_hours": hours,
            "total_events": len(events),
            "severity_breakdown": dict(severity_counts),
            "type_breakdown": dict(type_counts),
            "blocked_count": blocked_count,
            "critical_count": severity_counts.get('critical', 0)
        }

    def block_ip(self, ip: str, duration_minutes: int = 60, reason: str = "threat_detected"):
        """阻止IP"""
        key = f"blocked_ip:{ip}"
        self.redis.setex(key, duration_minutes * 60, reason)

        self._create_event(
            event_type="ip_blocked",
            severity="high",
            source_ip=ip,
            details={
                "duration_minutes": duration_minutes,
                "reason": reason
            },
            action_taken="blocked"
        )

    def is_ip_blocked(self, ip: str) -> bool:
        """检查IP是否被阻止"""
        key = f"blocked_ip:{ip}"
        return self.redis.exists(key)

    def get_blocked_ips(self) -> List[dict]:
        """获取被阻止的IP列表"""
        blocked = []
        for key in self.redis.scan_iter("blocked_ip:*"):
            ip = key.decode().split(':')[1]
            ttl = self.redis.ttl(key)
            reason = self.redis.get(key)
            blocked.append({
                "ip": ip,
                "ttl_seconds": ttl,
                "reason": reason.decode() if reason else "unknown"
            })
        return blocked


class RequestFilter:
    """请求过滤器"""

    def __init__(self, detection_service: IntrusionDetectionService):
        self.detection = detection_service

    def filter_request(self, request: dict) -> dict:
        """过滤请求"""
        result = {
            "allowed": True,
            "filtered": False,
            "sanitized_data": request,
            "warnings": []
        }

        # 检查IP是否被阻止
        ip = request.get('client_ip', '')
        if self.detection.is_ip_blocked(ip):
            result['allowed'] = False
            result['reason'] = 'ip_blocked'
            return result

        # 检查请求是否恶意
        threat_check = self.detection.check_request(request)

        if threat_check['malicious']:
            result['warnings'] = threat_check['threats']

            if threat_check['action'] in ['block', 'block_and_alert']:
                result['allowed'] = False
                result['reason'] = 'malicious_request'
                self.detection.block_ip(ip, reason=threat_check['severity'])
                return result

            # 清理恶意数据
            result['sanitized_data'] = self._sanitize_request(request, threat_check['threats'])
            result['filtered'] = True

        return result

    def _sanitize_request(self, request: dict, threats: List[dict]) -> dict:
        """清理请求中的恶意数据"""
        sanitized = request.copy()

        # 移除威胁字符
        for threat in threats:
            if threat['type'] in ['malicious_query', 'malicious_path']:
                pattern = threat['pattern']
                if 'query' in sanitized:
                    sanitized['query'] = re.sub(pattern, '', sanitized['query'], flags=re.IGNORECASE)
                if 'path' in sanitized:
                    sanitized['path'] = re.sub(pattern, '', sanitized['path'], flags=re.IGNORECASE)

        return sanitized