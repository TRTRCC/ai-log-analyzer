#!/bin/bash
# ============================================================
# AI Log Analyzer - One-Click Installation Script
# ============================================================
# This script installs and configures the AI Log Analyzer system
# including all dependencies, Docker containers, and systemd service
# ============================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Logging functions
log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step() { echo -e "${BLUE}[STEP]${NC} $1"; }

# Default configuration
DEFAULT_REPO_URL="https://github.com/TRTRCC/ai-log-analyzer.git"
DEFAULT_INSTALL_DIR="/opt/ai-log-analyzer"
DEFAULT_DATA_DIR="/data/ai-log-analyzer"
SERVICE_NAME="ai-log-analyzer"

# ============================================================
# STEP 1: System Detection
# ============================================================
detect_system() {
    log_step "Detecting system environment..."

    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS=$ID
        OS_VER=$VERSION_ID
        OS_NAME=$PRETTY_NAME
    else
        log_error "Cannot detect operating system"
        exit 1
    fi

    log_info "Detected: $OS_NAME ($OS $OS_VER)"

    # Check architecture
    ARCH=$(uname -m)
    log_info "Architecture: $ARCH"

    # Check if running as root
    if [ "$EUID" -ne 0 ]; then
        log_warn "Not running as root. Some operations may require sudo."
        SUDO="sudo"
    else
        SUDO=""
    fi
}

# ============================================================
# STEP 2: Dependency Installation
# ============================================================
install_dependencies() {
    log_step "Installing dependencies..."

    # Update package manager
    case $OS in
        ubuntu|debian)
            $SUDO apt-get update -qq
            ;;
        centos|rhel|rocky|almalinux)
            $SUDO yum update -y -q
            ;;
        alpine)
            $SUDO apk update
            ;;
        *)
            log_warn "Unknown package manager, attempting generic install"
            ;;
    esac

    # Install Docker if not present
    if ! command -v docker &> /dev/null; then
        log_info "Installing Docker..."
        case $OS in
            ubuntu|debian)
                $SUDO apt-get install -y -qq curl
                curl -fsSL https://get.docker.com | $SUDO sh
                ;;
            centos|rhel|rocky|almalinux)
                $SUDO yum install -y -q docker-ce docker-ce-cli containerd.io || {
                    $SUDO yum config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
                    $SUDO yum install -y -q docker-ce docker-ce-cli containerd.io
                }
                ;;
            alpine)
                $SUDO apk add docker
                ;;
        esac
        $SUDO systemctl enable docker
        $SUDO systemctl start docker
        log_info "Docker installed successfully"
    else
        log_info "Docker already installed: $(docker --version)"
    fi

    # Install Docker Compose if not present
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        log_info "Installing Docker Compose..."
        COMPOSE_VERSION=$(curl -s https://api.github.com/repos/docker/compose/releases/latest | grep '"tag_name"' | sed -E 's/.*"([^"]+)".*/\1/')
        $SUDO curl -L "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-$(uname -s)-$(uname -m)" \
            -o /usr/local/bin/docker-compose
        $SUDO chmod +x /usr/local/bin/docker-compose
        log_info "Docker Compose installed: $COMPOSE_VERSION"
    else
        log_info "Docker Compose already installed"
    fi

    # Install Git if not present
    if ! command -v git &> /dev/null; then
        log_info "Installing Git..."
        case $OS in
            ubuntu|debian)
                $SUDO apt-get install -y -qq git
                ;;
            centos|rhel|rocky|almalinux)
                $SUDO yum install -y -q git
                ;;
            alpine)
                $SUDO apk add git
                ;;
        esac
    fi

    # Install other utilities
    for util in curl wget openssl jq; do
        if ! command -v $util &> /dev/null; then
            case $OS in
                ubuntu|debian)
                    $SUDO apt-get install -y -qq $util
                    ;;
                centos|rhel|rocky|almalinux)
                    $SUDO yum install -y -q $util
                    ;;
                alpine)
                    $SUDO apk add $util
                    ;;
            esac
        fi
    done

    log_info "All dependencies installed"
}

# ============================================================
# STEP 3: Clone or Update Project
# ============================================================
clone_project() {
    local repo_url="${1:-$DEFAULT_REPO_URL}"
    local install_dir="${2:-$DEFAULT_INSTALL_DIR}"

    log_step "Cloning project to $install_dir..."

    if [ -d "$install_dir" ]; then
        log_warn "Directory $install_dir already exists"
        read -p "Do you want to update the existing installation? [y/N]: " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            cd "$install_dir"
            git pull
            log_info "Project updated"
        else
            log_info "Using existing installation"
        fi
    else
        $SUDO git clone "$repo_url" "$install_dir"
        log_info "Project cloned successfully"
    fi

    cd "$install_dir"
}

# ============================================================
# STEP 4: Environment Configuration
# ============================================================
setup_environment() {
    local install_dir="${1:-$DEFAULT_INSTALL_DIR}"
    local data_dir="${2:-$DEFAULT_DATA_DIR}"

    log_step "Configuring environment..."

    cd "$install_dir"

    # Create data directories
    $SUDO mkdir -p "$data_dir"/{raw,parsed/{network,server,k8s},reports/{daily,adhoc},audit}
    $SUDO chmod 750 "$data_dir"/audit

    # Generate .env file if not exists
    if [ ! -f .env ]; then
        log_info "Generating configuration file..."

        # Copy example
        cp .env.example .env

        # Generate secure secrets
        SECRET_KEY=$(openssl rand -hex 32)
        JWT_SECRET=$(openssl rand -hex 32)
        POSTGRES_PASSWORD=$(openssl rand -base64 16)
        CLICKHOUSE_PASSWORD=$(openssl rand -base64 16)

        # Update configuration
        sed -i "s/SECRET_KEY=.*/SECRET_KEY=$SECRET_KEY/" .env
        sed -i "s/JWT_SECRET_KEY=.*/JWT_SECRET_KEY=$JWT_SECRET/" .env
        sed -i "s/POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$POSTGRES_PASSWORD/" .env
        sed -i "s/CLICKHOUSE_PASSWORD=.*/CLICKHOUSE_PASSWORD=$CLICKHOUSE_PASSWORD/" .env

        # Generate admin password
        ADMIN_PASSWORD=$(openssl rand -base64 12)
        sed -i "s/ADMIN_PASSWORD=.*/ADMIN_PASSWORD=$ADMIN_PASSWORD/" .env

        # Set data directory
        sed -i "s|DATA_DIR=.*|DATA_DIR=$data_dir|" .env
        sed -i "s|RAW_LOG_DIR=.*|RAW_LOG_DIR=$data_dir/raw|" .env
        sed -i "s|PARSED_LOG_DIR=.*|PARSED_LOG_DIR=$data_dir/parsed|" .env
        sed -i "s|REPORT_DIR=.*|REPORT_DIR=$data_dir/reports|" .env
        sed -i "s|AUDIT_DIR=.*|AUDIT_DIR=$data_dir/audit|" .env

        # Set file permissions
        $SUDO chmod 600 .env

        log_info "Configuration generated"
        log_warn "============================================"
        log_warn "IMPORTANT: Save these credentials securely!"
        log_warn "Admin password: $ADMIN_PASSWORD"
        log_warn "============================================"
    else
        log_info "Using existing configuration"
    fi
}

# ============================================================
# STEP 5: Start Services
# ============================================================
start_services() {
    local install_dir="${1:-$DEFAULT_INSTALL_DIR}"

    log_step "Starting Docker services..."

    cd "$install_dir"

    # Pull images first
    log_info "Pulling Docker images..."
    docker-compose pull || docker compose pull

    # Build if needed
    log_info "Building containers..."
    docker-compose build --parallel || docker compose build

    # Start services
    log_info "Starting services..."
    docker-compose up -d || docker compose up -d

    log_info "Waiting for services to be ready..."
    sleep 30

    # Check service health
    log_info "Checking service health..."
    for service in postgres clickhouse redis api frontend; do
        if docker-compose ps | grep -q "$service.*Up"; then
            log_info "Service $service: running"
        else
            log_warn "Service $service: not running, check logs"
        fi
    done

    # Initialize database (if script exists)
    if [ -f scripts/init_db.py ]; then
        log_info "Initializing database..."
        docker-compose exec api python -m scripts.init_db || docker compose exec api python -m scripts.init_db
    fi

    log_info "Services started successfully"
}

# ============================================================
# STEP 6: Configure Systemd Service
# ============================================================
setup_systemd() {
    local install_dir="${1:-$DEFAULT_INSTALL_DIR}"

    log_step "Configuring systemd service for auto-start..."

    # Create systemd service file
    cat > /tmp/$SERVICE_NAME.service << EOF
[Unit]
Description=AI Log Analyzer System
After=docker.service network-online.target
Requires=docker.service
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$install_dir
ExecStartPre=-/usr/local/bin/docker-compose down
ExecStart=/usr/local/bin/docker-compose up -d
ExecStop=/usr/local/bin/docker-compose down
TimeoutStartSec=300
TimeoutStopSec=60

[Install]
WantedBy=multi-user.target
EOF

    # Use docker compose command if docker-compose binary not available
    if ! command -v docker-compose &> /dev/null; then
        sed -i 's|/usr/local/bin/docker-compose|docker compose|g' /tmp/$SERVICE_NAME.service
    fi

    # Install service
    $SUDO mv /tmp/$SERVICE_NAME.service /etc/systemd/system/
    $SUDO systemctl daemon-reload
    $SUDO systemctl enable $SERVICE_NAME

    log_info "Systemd service configured and enabled"
}

# ============================================================
# STEP 7: Security Hardening
# ============================================================
security_hardening() {
    log_step "Applying security hardening..."

    # Configure firewall
    if command -v ufw &> /dev/null; then
        log_info "Configuring UFW firewall..."
        $SUDO ufw --force reset
        $SUDO ufw default deny incoming
        $SUDO ufw default allow outgoing
        $SUDO ufw allow 80/tcp comment 'HTTP'
        $SUDO ufw allow 443/tcp comment 'HTTPS'
        $SUDO ufw allow 22/tcp comment 'SSH'
        $SUDO ufw --force enable
        log_info "UFW configured"
    elif command -v firewall-cmd &> /dev/null; then
        log_info "Configuring firewalld..."
        $SUDO firewall-cmd --permanent --add-service=http
        $SUDO firewall-cmd --permanent --add-service=https
        $SUDO firewall-cmd --permanent --add-service=ssh
        $SUDO firewall-cmd --reload
        log_info "Firewalld configured"
    else
        log_warn "No firewall detected, please configure manually"
    fi

    # Set proper permissions
    $SUDO chmod 600 "$DEFAULT_INSTALL_DIR/.env"
    $SUDO chmod 700 "$DEFAULT_DATA_DIR/audit"

    # Docker security (if applicable)
    if [ -f /etc/docker/daemon.json ]; then
        log_info "Docker security already configured"
    else
        log_info "Applying Docker security settings..."
        echo '{"icc": false, "userns-remap": "default"}' | $SUDO tee /etc/docker/daemon.json > /dev/null
        $SUDO systemctl restart docker
    fi

    log_info "Security hardening applied"
}

# ============================================================
# STEP 8: Verification
# ============================================================
verify_installation() {
    log_step "Verifying installation..."

    # Check if services are running
    if docker-compose ps | grep -q "Up"; then
        log_info "All Docker services running"
    else
        log_error "Some services not running"
        docker-compose ps
    fi

    # Check API health
    if curl -s http://localhost/health | grep -q "healthy"; then
        log_info "API health check passed"
    else
        log_warn "API health check failed, may still be starting"
    fi

    # Print access info
    echo ""
    echo "============================================"
    echo "    Installation Complete!"
    echo "============================================"
    echo ""
    echo "Access the system at:"
    echo "  Web UI:      http://localhost"
    echo "  API Docs:    http://localhost/api/docs"
    echo "  Health:      http://localhost/health"
    echo ""
    echo "Default credentials:"
    echo "  Username: admin"
    echo "  Password: (check .env file or installation output)"
    echo ""
    echo "Log directory: $DEFAULT_DATA_DIR"
    echo "Config file:   $DEFAULT_INSTALL_DIR/.env"
    echo ""
    echo "Manage service:"
    echo "  Start:   sudo systemctl start $SERVICE_NAME"
    echo "  Stop:    sudo systemctl stop $SERVICE_NAME"
    echo "  Status:  sudo systemctl status $SERVICE_NAME"
    echo "  Logs:    docker-compose logs -f"
    echo ""
    echo "============================================"
}

# ============================================================
# STEP 9: Uninstall (Optional)
# ============================================================
uninstall() {
    log_step "Uninstalling AI Log Analyzer..."

    read -p "This will remove all data and containers. Continue? [y/N]: " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Uninstall cancelled"
        exit 0
    fi

    # Stop services
    $SUDO systemctl stop $SERVICE_NAME || true
    $SUDO systemctl disable $SERVICE_NAME || true

    # Remove containers
    cd "$DEFAULT_INSTALL_DIR"
    docker-compose down -v --remove-orphans || docker compose down -v --remove-orphans

    # Remove service file
    $SUDO rm -f /etc/systemd/system/$SERVICE_NAME.service
    $SUDO systemctl daemon-reload

    # Remove installation directory (optional)
    read -p "Remove installation directory? [y/N]: " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        $SUDO rm -rf "$DEFAULT_INSTALL_DIR"
    fi

    # Remove data directory (optional)
    read -p "Remove data directory ($DEFAULT_DATA_DIR)? [y/N]: " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        $SUDO rm -rf "$DEFAULT_DATA_DIR"
    fi

    log_info "Uninstallation complete"
}

# ============================================================
# Main Entry Point
# ============================================================
main() {
    local action="${1:-install}"
    local repo_url="${2:-$DEFAULT_REPO_URL}"
    local install_dir="${3:-$DEFAULT_INSTALL_DIR}"
    local data_dir="${4:-$DEFAULT_DATA_DIR}"

    echo ""
    echo "============================================"
    echo "    AI Log Analyzer Installer v1.0"
    echo "============================================"
    echo ""

    case $action in
        install)
            detect_system
            install_dependencies
            clone_project "$repo_url" "$install_dir"
            setup_environment "$install_dir" "$data_dir"
            start_services "$install_dir"
            setup_systemd "$install_dir"
            security_hardening
            verify_installation
            ;;
        update)
            detect_system
            cd "$install_dir"
            git pull
            docker-compose build --parallel || docker compose build
            docker-compose up -d || docker compose up -d
            log_info "Update complete"
            ;;
        uninstall)
            uninstall
            ;;
        *)
            echo "Usage: $0 {install|update|uninstall} [repo_url] [install_dir] [data_dir]"
            echo ""
            echo "Actions:"
            echo "  install   - Full installation"
            echo "  update    - Update existing installation"
            echo "  uninstall - Remove everything"
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"