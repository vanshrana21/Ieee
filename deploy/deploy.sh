#!/bin/bash
#
# Phase 11 — Production Deployment Script
#
# Usage: ./deploy.sh [environment]
#   environment: development, staging, production (default: production)
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
ENVIRONMENT="${1:-production}"
APP_NAME="mootcourt"
DEPLOY_DIR="/opt/${APP_NAME}"
BACKUP_DIR="/var/backups/${APP_NAME}"
LOG_DIR="/var/log/${APP_NAME}"

# Load environment-specific configuration
if [[ -f ".env.${ENVIRONMENT}" ]]; then
    source ".env.${ENVIRONMENT}"
fi

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Pre-deployment checks
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check if running as root (should not be)
    if [[ $EUID -eq 0 ]]; then
        log_error "Do not run as root"
        exit 1
    fi
    
    # Check required tools
    command -v python3 >/dev/null 2>&1 || { log_error "python3 not found"; exit 1; }
    command -v pip3 >/dev/null 2>&1 || { log_error "pip3 not found"; exit 1; }
    command -v psql >/dev/null 2>&1 || { log_warn "psql not found (optional)"; }
    
    # Check environment variables
    if [[ -z "${DATABASE_URL:-}" ]]; then
        log_error "DATABASE_URL not set"
        exit 1
    fi
    
    if [[ -z "${SECRET_KEY:-}" ]]; then
        log_error "SECRET_KEY not set"
        exit 1
    fi
    
    log_info "Prerequisites check passed"
}

# Create backup before deployment
backup_database() {
    log_info "Creating database backup..."
    
    mkdir -p "${BACKUP_DIR}"
    
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    BACKUP_FILE="${BACKUP_DIR}/backup_${TIMESTAMP}.sql.gz"
    
    # Extract database name from URL
    DB_NAME=$(echo "${DATABASE_URL}" | sed -n 's/.*\/\([^?]*\).*/\1/p')
    
    if pg_dump "${DATABASE_URL}" | gzip > "${BACKUP_FILE}"; then
        log_info "Backup created: ${BACKUP_FILE}"
    else
        log_error "Backup failed"
        exit 1
    fi
    
    # Keep only last 10 backups
    ls -t "${BACKUP_DIR}"/backup_*.sql.gz | tail -n +11 | xargs -r rm -f
}

# Install dependencies
install_dependencies() {
    log_info "Installing dependencies..."
    
    python3 -m pip install --upgrade pip
    pip3 install -r requirements.txt --no-cache-dir
    
    log_info "Dependencies installed"
}

# Run database migrations
run_migrations() {
    log_info "Running database migrations..."
    
    python3 -m backend.cli db migrate --all --verify
    
    log_info "Migrations complete"
}

# Run security audit
security_audit() {
    log_info "Running security audit..."
    
    python3 -m backend.cli security audit --full
    
    log_info "Security audit complete"
}

# Health check
health_check() {
    log_info "Running health check..."
    
    if python3 -m backend.cli deploy health --endpoint "http://localhost:8000/health"; then
        log_info "Health check passed"
    else
        log_error "Health check failed"
        exit 1
    fi
}

# Restart services
restart_services() {
    log_info "Restarting services..."
    
    # Reload systemd
    sudo systemctl daemon-reload
    
    # Restart application
    sudo systemctl restart mootcourt
    
    # Wait for startup
    sleep 5
    
    # Check status
    if systemctl is-active --quiet mootcourt; then
        log_info "Service restarted successfully"
    else
        log_error "Service failed to start"
        sudo systemctl status mootcourt
        exit 1
    fi
}

# Main deployment function
deploy() {
    log_info "Starting deployment to ${ENVIRONMENT}..."
    
    check_prerequisites
    backup_database
    install_dependencies
    run_migrations
    security_audit
    restart_services
    health_check
    
    log_info "Deployment to ${ENVIRONMENT} completed successfully!"
}

# Rollback function
rollback() {
    log_warn "Rolling back deployment..."
    
    # Find latest backup
    LATEST_BACKUP=$(ls -t "${BACKUP_DIR}"/backup_*.sql.gz | head -1)
    
    if [[ -f "${LATEST_BACKUP}" ]]; then
        log_info "Restoring from backup: ${LATEST_BACKUP}"
        python3 -m backend.cli db restore --input "${LATEST_BACKUP}" --force
        restart_services
        log_info "Rollback complete"
    else
        log_error "No backup found for rollback"
        exit 1
    fi
}

# Parse command line arguments
case "${1:-}" in
    rollback)
        rollback
        ;;
    *)
        deploy
        ;;
esac
