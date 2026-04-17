# AI Log Analyzer 部署文档

## 目录
1. [系统概述](#系统概述)
2. [环境要求](#环境要求)
3. [快速部署](#快速部署)
4. [详细配置](#详细配置)
5. [使用指南](#使用指南)
6. [API文档](#api文档)
7. [常见问题](#常见问题)

---

## 系统概述

AI Log Analyzer 是一套企业级AI日志分析系统，支持：
- **百G级日志处理**: 100GB+ ELK日志高效解析入库
- **多AI服务商**: Claude、OpenAI、Azure、本地模型、自定义接口
- **权限隔离**: 网络组/系统组/K8S组/审计组角色隔离
- **自动报告**: 每日自动生成分析报告并发送邮件
- **完整审计**: 所有操作和AI使用量完整记录

### 技术架构
```
┌─────────────────────────────────────────────────────────────┐
│                    Nginx (反向代理/HTTPS)                     │
└─────────────────────────────────────────────────────────────┘
                              │
    ┌─────────────────────────┼─────────────────────────┐
    ▼                         ▼                         ▼
┌─────────┐            ┌─────────┐              ┌─────────┐
│ 前端    │            │ API服务 │              │ Workers │
│ Vue 3   │            │ FastAPI │              │ Celery  │
└─────────┘            └─────────┘              └─────────┘
                              │
    ┌─────────────────────────┼─────────────────────────┐
    ▼                         ▼                         ▼
┌─────────┐            ┌─────────┐              ┌─────────┐
│PostgreSQL│           │ClickHouse│             │ Redis   │
│ 主数据库 │           │ 日志存储 │             │队列/缓存│
└─────────┘            └─────────┘              └─────────┘
```

---

## 环境要求

### 硬件配置

| 配置级别 | CPU | 内存 | 存储 | 适用场景 |
|---------|-----|------|------|---------|
| 最小配置 | 8核 | 32GB | 500GB SSD | 测试/日志<10GB/天 |
| 推荐配置 | 16核 | 64GB | 2TB NVMe | 生产/日志10-100GB/天 |
| 高性能配置 | 32核 | 128GB | 4TB NVMe RAID | 大规模/日志>100GB/天 |

### 软件要求

| 软件 | 版本 | 说明 |
|------|------|------|
| Docker | 20.x+ | 容器运行环境 |
| Docker Compose | 2.x+ | 服务编排 |
| Git | 2.x+ | 版本控制 |

### 操作系统支持
- Ubuntu 20.04/22.04 LTS
- Debian 11/12
- CentOS 7/8
- Rocky Linux 8/9
- Alpine Linux 3.18+

---

## 快速部署

### 方式一：一键安装脚本 (推荐)

```bash
# 下载并执行安装脚本
curl -fsSL https://raw.githubusercontent.com/TRTRCC/ai-log-analyzer/main/install.sh | bash

# 或指定安装目录
curl -fsSL https://raw.githubusercontent.com/TRTRCC/ai-log-analyzer/main/install.sh | bash -s install /opt/ai-log-analyzer /data/ai-logs
```

安装脚本会自动：
1. 检测系统环境并安装Docker/Docker Compose
2. 克隆项目代码
3. 生成安全配置（密码、密钥）
4. 启动所有服务
5. 配置systemd自启动
6. 应用安全加固（防火墙）

### 方式二：手动部署

```bash
# 1. 克隆项目
git clone https://github.com/TRTRCC/ai-log-analyzer.git
cd ai-log-analyzer

# 2. 创建配置文件
cp .env.example .env

# 3. 编辑配置（重要！）
vim .env
# 必须修改：
# - POSTGRES_PASSWORD (数据库密码)
# - SECRET_KEY (应用密钥)
# - ADMIN_PASSWORD (管理员密码)
# - AI API密钥 (CLAUDE_API_KEY / OPENAI_API_KEY 等)

# 4. 创建数据目录
mkdir -p data/{raw,parsed/{network,server,k8s},reports/{daily,adhoc},audit}

# 5. 启动服务
docker-compose up -d

# 6. 初始化数据库
docker-compose exec api python scripts/init_db.py

# 7. 查看服务状态
docker-compose ps
```

### 方式三：开发模式

```bash
# 后端开发
cd backend
pip install -r requirements.txt
python -m app.main

# 前端开发
cd frontend
npm install
npm run dev
```

---

## 详细配置

### 环境变量配置 (.env)

```bash
# === 数据库配置 ===
POSTGRES_DB=ailoganalyzer
POSTGRES_USER=ailoguser
POSTGRES_PASSWORD=your_secure_password_here

CLICKHOUSE_USER=default
CLICKHOUSE_PASSWORD=your_clickhouse_password

# === 安全配置 ===
SECRET_KEY=至少32字符的随机字符串
JWT_SECRET_KEY=JWT签名密钥
JWT_EXPIRATION_HOURS=24

# === 管理员账户 ===
ADMIN_EMAIL=admin@yourcompany.com
ADMIN_PASSWORD=初始管理员密码

# === AI服务商配置 ===
# Claude (Anthropic)
CLAUDE_API_KEY=sk-ant-xxx
CLAUDE_API_URL=https://api.anthropic.com

# OpenAI
OPENAI_API_KEY=sk-xxx
OPENAI_API_URL=https://api.openai.com/v1

# Azure OpenAI
AZURE_OPENAI_API_KEY=xxx
AZURE_OPENAI_ENDPOINT=https://xxx.openai.azure.com
AZURE_OPENAI_DEPLOYMENT=gpt-4

# === 邮件配置 ===
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_email_password
SMTP_FROM_EMAIL=noreply@yourcompany.com
SMTP_USE_TLS=true

# === 存储路径 ===
DATA_DIR=/data/ai-log-analyzer
RAW_LOG_DIR=/data/ai-log-analyzer/raw
PARSED_LOG_DIR=/data/ai-log-analyzer/parsed
REPORT_DIR=/data/ai-log-analyzer/reports
AUDIT_DIR=/data/ai-log-analyzer/audit
```

### 日志文件放置

```bash
# ELK原始文件放置目录
/data/ai-log-analyzer/raw/

# 支持的文件格式：
# - .gz (gzip压缩的单文件)
# - .tar / .tar.gz (tar归档)
# - .zip (zip压缩)
# - .log (纯文本日志)
```

### AI服务商配置

通过管理后台配置：
1. 登录系统 → Admin → AI Configuration
2. 点击 "Add Provider"
3. 选择类型并填写API信息
4. 添加支持的模型
5. 设置默认模型

### 定时任务配置

在 Admin → Task Scheduling 中配置：
- Daily Report: 每日报告生成时间 (默认 8:00)
- Auto Analysis: 自动分析间隔 (默认每6小时)
- Log Cleanup: 日志清理策略

---

## 使用指南

### 用户角色说明

| 角色 | 权限范围 |
|------|---------|
| super_admin | 全部权限 + 系统配置 |
| audit_admin | 全部日志 + 审计记录 |
| dept_admin | 部门用户管理 |
| network_user | 仅网络设备日志 |
| server_user | 仅服务器日志 |
| k8s_user | 仅K8S日志 |

### 日常操作流程

1. **上传日志文件**
   - 将ELK导出文件放入 `/data/raw/` 目录
   - 系统自动检测并解析入库

2. **查询日志**
   - Logs → 设置时间范围、类型、关键词
   - 查看详情、导出结果

3. **AI分析**
   - Analysis → 选择分析类型、日志范围
   - 选择AI模型 → 创建任务
   - 查看分析结果和报告

4. **查看报告**
   - Reports → 预览、下载PDF
   - 订阅每日邮件报告

### 管理员操作

1. **用户管理**
   - Admin → Users → 添加/编辑/删除用户
   - 分配角色和部门

2. **AI配置**
   - 添加新的AI服务商
   - 配置模型参数和成本

3. **审计查看**
   - Admin → Audit Logs → 查看操作记录
   - AI Usage → 查看AI使用统计和成本

---

## API文档

### 访问地址
- Swagger UI: http://localhost/api/docs
- ReDoc: http://localhost/api/redoc

### 主要API端点

```
# 认证
POST /api/v1/auth/login          # 登录
POST /api/v1/auth/refresh        # 刷新Token
POST /api/v1/auth/logout         # 登出
GET  /api/v1/auth/me             # 当前用户信息

# 日志查询
GET  /api/v1/logs/query          # 查询日志
GET  /api/v1/logs/stats          # 日志统计
GET  /api/v1/logs/hosts          # 主机列表
GET  /api/v1/logs/timeline       # 时间线数据

# AI分析
POST /api/v1/analysis/tasks      # 创建分析任务
GET  /api/v1/analysis/tasks      # 任务列表
GET  /api/v1/analysis/tasks/{id} # 任务详情
GET  /api/v1/analysis/tasks/{id}/result # 分析结果

# 报告
GET  /api/v1/reports             # 报告列表
GET  /api/v1/reports/{id}        # 报告详情
GET  /api/v1/reports/{id}/download # 下载报告
POST /api/v1/reports/generate    # 生成报告

# 管理后台
GET  /api/v1/admin/ai/providers  # AI服务商列表
POST /api/v1/admin/ai/providers  # 添加服务商
GET  /api/v1/admin/ai/models     # AI模型列表
GET  /api/v1/admin/audit/logs    # 审计日志
GET  /api/v1/admin/ai/usage      # AI使用统计
GET  /api/v1/admin/email         # 邮件配置
GET  /api/v1/admin/tasks         # 定时任务
```

---

## 常见问题

### Q: 服务启动失败？
```bash
# 查看日志
docker-compose logs api
docker-compose logs clickhouse

# 常见原因：
# 1. 端口被占用 - 修改docker-compose.yml端口
# 2. 权限问题 - chmod 755 data目录
# 3. 内存不足 - 增加系统内存
```

### Q: 日志解析慢？
```bash
# 优化建议：
# 1. 增加ClickHouse内存配置
# 2. 调整解析chunk大小
# 3. 使用更快的SSD存储
```

### Q: AI分析成本高？
```bash
# 控制成本方法：
# 1. 使用采样策略减少输入Token
# 2. 选择成本更低的模型
# 3. 配置Token配额限制
# 4. 使用本地模型 (Ollama)
```

### Q: 如何更换AI服务商？
```bash
# 在管理后台：
# 1. Admin → AI Configuration → Providers
# 2. 添加新服务商和模型
# 3. 设置为默认
# 4. 禁用旧服务商
```

### Q: 如何备份数据？
```bash
# 备份PostgreSQL
docker-compose exec postgres pg_dump -U ailoguser ailoganalyzer > backup.sql

# 备份ClickHouse
docker-compose exec clickhouse clickhouse-client --query "BACKUP DATABASE ailoganalyzer_logs"

# 备份配置
cp .env .env.backup
tar -czf data_backup.tar.gz data/
```

### Q: 如何升级系统？
```bash
# 拉取最新代码
git pull

# 重新构建
docker-compose build

# 重启服务
docker-compose up -d

# 或使用安装脚本
curl -fsSL https://raw.githubusercontent.com/TRTRCC/ai-log-analyzer/main/install.sh | bash -s update
```

---

## 技术支持

- GitHub Issues: https://github.com/TRTRCC/ai-log-analyzer/issues
- 文档更新: 查看 Wiki 页面

---

**安全提醒**:
1. 首次登录后立即修改管理员密码
2. 定期备份 .env 配置文件
3. 不要在公网暴露数据库端口
4. 定期更新系统和依赖包