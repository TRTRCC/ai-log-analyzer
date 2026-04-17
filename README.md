# AI Log Analyzer

Enterprise-grade AI-powered log analysis system with multi-provider support, role-based access control, and comprehensive reporting capabilities.

## Features

- **Large-scale Log Processing**: Handle 100GB+ ELK logs efficiently
- **Multi-source Log Support**: Network devices, servers, Kubernetes
- **AI-powered Analysis**: Multiple AI providers (Claude, OpenAI, Azure, Local models)
- **Role-based Access Control**: Fine-grained permissions for different user groups
- **Comprehensive Reporting**: Daily reports with email notifications
- **Interactive Dashboards**: Real-time charts and visualizations
- **Audit Trail**: Complete operation logging and AI usage statistics
- **Easy Deployment**: One-click installation with Docker Compose

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Nginx (Reverse Proxy)                       │
└─────────────────────────────────────────────────────────────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        ▼                           ▼                           ▼
┌───────────────┐          ┌───────────────┐          ┌───────────────┐
│   Frontend    │          │   Backend     │          │   Workers     │
│   (Vue 3)     │          │   (FastAPI)   │          │   (Celery)    │
└───────────────┘          └───────────────┘          └───────────────┘
                                    │                           │
        ┌───────────────────────────┼───────────────────────────┤
        ▼                           ▼                           ▼
┌───────────────┐          ┌───────────────┐          ┌───────────────┐
│  PostgreSQL   │          │  ClickHouse   │          │    Redis      │
│   (Main DB)   │          │  (Logs DB)    │          │  (Queue/Cache)│
└───────────────┘          └───────────────┘          └───────────────┘
```

## Quick Start

### One-Click Installation (Linux)

```bash
curl -fsSL https://raw.githubusercontent.com/TRTRCC/ai-log-analyzer/main/install.sh | bash
```

### Manual Installation

1. **Clone the repository**
```bash
git clone https://github.com/TRTRCC/ai-log-analyzer.git
cd ai-log-analyzer
```

2. **Configure environment**
```bash
cp .env.example .env
# Edit .env with your settings
```

3. **Start services**
```bash
docker-compose up -d
```

4. **Access the system**
- Web UI: http://localhost
- API Docs: http://localhost/api/docs
- Default credentials: admin / (password from .env)

## System Requirements

### Minimum (Testing)
- CPU: 8 cores
- RAM: 32GB
- Storage: 500GB SSD
- Suitable for < 10GB/day logs

### Recommended (Production)
- CPU: 16+ cores
- RAM: 64GB+
- Storage: 2TB NVMe SSD
- Suitable for 10-100GB/day logs

### High Performance
- CPU: 32+ cores
- RAM: 128GB+
- Storage: 4TB+ NVMe SSD RAID
- Suitable for > 100GB/day logs

## User Roles

| Role | Description | Permissions |
|------|-------------|-------------|
| `super_admin` | System administrator | Full access + system config |
| `audit_admin` | Security auditor | All logs + audit logs + AI usage |
| `dept_admin` | Department manager | Department user management |
| `network_user` | Network team | Network device logs only |
| `server_user` | Server team | Server logs only |
| `k8s_user` | K8S team | Kubernetes logs only |

## Configuration

### AI Providers

Configure AI providers in the admin panel:

1. Navigate to Admin > AI Configuration
2. Add provider (Claude, OpenAI, Azure, or Custom)
3. Configure models and pricing
4. Set default provider/model

### Email Notifications

1. Navigate to Admin > Email Configuration
2. Configure SMTP settings
3. Enable/disable daily report emails
4. Manage subscriber list

### Storage Paths

Configure in Admin > Storage Management:
- Raw ELK files directory
- Parsed log storage
- Report archive location
- Audit log location

## API Documentation

Access the interactive API documentation at:
- Swagger UI: http://localhost/api/docs
- ReDoc: http://localhost/api/redoc

## Directory Structure

```
ai-log-analyzer/
├── backend/               # FastAPI backend
│   ├── app/
│   │   ├── api/          # API routes
│   │   ├── models/       # Database models
│   │   ├── services/     # Business logic
│   │   ├── ai/           # AI providers
│   │   ├── workers/      # Background tasks
│   │   └── utils/        # Utilities
│   └── tests/
├── frontend/              # Vue frontend
│   └── src/
│       ├── views/        # Page components
│       ├── components/   # Reusable components
│       ├── stores/       # Pinia stores
│       └── router/       # Vue Router
├── scripts/               # Setup scripts
├── nginx/                 # Nginx config
├── docs/                  # Documentation
├── docker-compose.yml
├── install.sh            # One-click installer
└── README.md
```

## Maintenance

### Service Management

```bash
# Start services
sudo systemctl start ai-log-analyzer

# Stop services
sudo systemctl stop ai-log-analyzer

# View status
sudo systemctl status ai-log-analyzer

# View logs
docker-compose logs -f
```

### Backup

```bash
# Backup database
docker-compose exec postgres pg_dump -U ailoguser ailoganalyzer > backup.sql

# Backup ClickHouse
docker-compose exec clickhouse clickhouse-client --query "BACKUP DATABASE ailoganalyzer_logs"

# Backup configuration
cp .env .env.backup
```

### Update

```bash
# Update installation
curl -fsSL https://raw.githubusercontent.com/TRTRCC/ai-log-analyzer/main/install.sh | bash -s update
```

## Security

- JWT-based authentication with refresh tokens
- Password hashing with bcrypt
- API key encryption for AI providers
- Role-based access control (RBAC)
- Audit logging for all operations
- Rate limiting on API endpoints
- HTTPS support (configure in nginx/)

## License

MIT License

## Support

For issues and feature requests, please use GitHub Issues.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request