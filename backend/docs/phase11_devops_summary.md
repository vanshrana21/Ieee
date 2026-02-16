# Phase 11 — CLI & DevOps Tooling

**Status:** ✅ PRODUCTION-HARDENED  
**Date:** 2025-02-14  
**Purpose:** Operations automation, deployment, and infrastructure management

---

## Executive Summary

| Feature | Phase 10 | Phase 11 (DevOps) |
|---------|----------|-------------------|
| **CLI Interface** | ❌ | ✅ (Full command suite) |
| **Database Ops** | ❌ | ✅ (Migrate, backup, restore) |
| **Security Ops** | ❌ | ✅ (Audit, verify, reset) |
| **Tournament Ops** | ❌ | ✅ (Finalize, results) |
| **Health Monitoring** | ❌ | ✅ (CLI + dashboard) |
| **Docker Deployment** | ❌ | ✅ (Compose + Dockerfile) |
| **Systemd Service** | ❌ | ✅ (Production service) |
| **Nginx Proxy** | ❌ | ✅ (SSL, rate limiting) |
| **Monitoring Stack** | ❌ | ✅ (Prometheus + Grafana) |
| **Tests** | ❌ | ✅ (25+ test cases) |

**Verdict:** 🟢 **PRODUCTION READY**

---

## CLI Commands

### Installation

```bash
# Install CLI
pip install -e .

# Or run directly
python -m backend.cli --help
```

### Available Commands

```
mootcourt [options] <command> [subcommand] [args]

Options:
  --version              Show version
  --log-level LEVEL      DEBUG|INFO|WARNING|ERROR
  --dry-run             Show what would be done

Commands:
  db          Database operations
  security    Security operations  
  tournament  Tournament management
  deploy      Deployment operations
  system      System operations
```

### Database Commands

#### Migrate

```bash
# Run all migrations
python -m backend.cli db migrate --all

# Run specific phase migration
python -m backend.cli db migrate --phase 9

# Migrate and verify
python -m backend.cli db migrate --all --verify
```

#### Verify

```bash
# Quick verification
python -m backend.cli db verify

# Full integrity check
python -m backend.cli db verify --full
```

#### Backup

```bash
# Create backup
python -m backend.cli db backup --output /backups/mootcourt.sql

# Compressed backup
python -m backend.cli db backup --output /backups/ --compress
```

#### Restore

```bash
# Restore from backup
python -m backend.cli db restore --input /backups/mootcourt.sql.gz

# Force restore (skip confirmation)
python -m backend.cli db restore --input backup.sql --force
```

### Security Commands

#### Audit

```bash
# Run full security audit
python -m backend.cli security audit --full

# Verify audit chain integrity
python -m backend.cli security audit --integrity
```

#### Verify Headers

```bash
# Verify security headers
python -m backend.cli security verify --endpoint http://localhost:8000
```

#### Reset Blocked IPs

```bash
# Clear blocked IP list
python -m backend.cli security reset-blocked-ips
```

### Tournament Commands

#### List

```bash
# List all tournaments
python -m backend.cli tournament list

# Filter by status
python -m backend.cli tournament list --status completed
```

#### Finalize

```bash
# Finalize tournament results
python -m backend.cli tournament finalize --id 42 --admin-id 1
```

#### Results

```bash
# Show tournament results
python -m backend.cli tournament results --id 42

# Verify result integrity
python -m backend.cli tournament results --id 42 --verify
```

### Deploy Commands

#### Health Check

```bash
# Single health check
python -m backend.cli deploy health

# Continuous monitoring
python -m backend.cli deploy health --watch

# Check specific endpoint
python -m backend.cli deploy health --endpoint http://api:8000/health
```

#### Status

```bash
# Show deployment status
python -m backend.cli deploy status
```

### System Commands

#### Status

```bash
# Show system status
python -m backend.cli system status
```

#### Stats

```bash
# Show hourly stats
python -m backend.cli system stats --period hour

# Show daily stats
python -m backend.cli system stats --period day

# Show weekly stats
python -m backend.cli system stats --period week
```

#### Config

```bash
# Show configuration
python -m backend.cli system config

# Validate configuration
python -m backend.cli system config --check
```

---

## Docker Deployment

### Quick Start

```bash
# Start all services
cd deploy
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f api
```

### Services

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| api | Custom | 8000 | Main application |
| postgres | postgres:15 | 5432 | Database |
| redis | redis:7 | 6379 | Cache/PubSub |
| nginx | nginx:alpine | 80/443 | Reverse proxy |
| prometheus | prom/prometheus | 9090 | Metrics |
| grafana | grafana/grafana | 3000 | Dashboards |

### Environment Variables

```bash
# Required
DATABASE_URL=postgresql+asyncpg://user:pass@postgres:5432/moot_court
SECRET_KEY=your-secret-key-here

# Optional
REDIS_URL=redis://redis:6379/0
LOG_LEVEL=INFO
USE_REDIS_BROADCAST=true
WS_MAX_QUEUE=100
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=admin
```

### Production Deployment

```bash
# Production environment
cp .env.example .env.production
# Edit .env.production with production values

# Deploy
docker-compose -f docker-compose.yml up -d
```

---

## Systemd Service

### Installation

```bash
# Copy service file
sudo cp deploy/mootcourt.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable service
sudo systemctl enable mootcourt

# Start service
sudo systemctl start mootcourt

# Check status
sudo systemctl status mootcourt
```

### Service Configuration

```ini
[Unit]
Description=Moot Court Tournament API Server
After=network.target postgresql.service redis.service

[Service]
Type=notify
User=mootcourt
Group=mootcourt
WorkingDirectory=/opt/mootcourt
ExecStart=/opt/mootcourt/venv/bin/gunicorn -c deploy/gunicorn.conf.py backend.main:app
Restart=on-failure

# Security hardening
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true

[Install]
WantedBy=multi-user.target
```

### Logs

```bash
# View logs
sudo journalctl -u mootcourt -f

# View recent logs
sudo journalctl -u mootcourt --since "1 hour ago"
```

---

## Nginx Configuration

### Features

- **SSL/TLS**: TLS 1.2+ with strong cipher suites
- **Rate Limiting**: 10 req/s for API, 5 req/min for auth
- **WebSocket Support**: `/live/ws/` proxy
- **Security Headers**: HSTS, CSP, X-Frame-Options
- **Gzip Compression**: Text assets

### SSL Setup

```bash
# Generate self-signed certificate (dev)
mkdir -p deploy/nginx/ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout deploy/nginx/ssl/key.pem \
  -out deploy/nginx/ssl/cert.pem

# Production: Use Let's Encrypt
certbot --nginx -d yourdomain.com
```

---

## Monitoring Stack

### Prometheus

- **URL**: http://localhost:9090
- **Scrape Interval**: 15s
- **Retention**: 200 hours

### Grafana

- **URL**: http://localhost:3000
- **Default User**: admin/admin
- **Dashboard**: Moot Court Platform Overview

### Metrics

| Metric | Description |
|--------|-------------|
| http_requests_total | Total HTTP requests |
| http_request_duration_seconds | Request latency |
| websocket_active_connections | Active WebSocket connections |
| pg_stat_activity_count | Database connections |
| redis_memory_used_bytes | Redis memory usage |
| audit_log_entries_total | Audit log entries |
| security_events_total | Security events |

---

## Deployment Script

### Usage

```bash
# Production deployment
./deploy/deploy.sh production

# Staging deployment
./deploy/deploy.sh staging

# Rollback
./deploy/deploy.sh rollback
```

### Features

1. **Prerequisites Check**: Verifies environment
2. **Database Backup**: Creates backup before deployment
3. **Dependency Install**: Updates Python packages
4. **Migration Run**: Applies database migrations
5. **Security Audit**: Runs security checks
6. **Health Check**: Verifies deployment
7. **Service Restart**: Graceful restart

### Backup Management

```bash
# Automatic backups on deployment
/var/backups/mootcourt/backup_YYYYMMDD_HHMMSS.sql.gz

# Retention: Last 10 backups
ls -t /var/backups/mootcourt/backup_*.sql.gz | tail -n +11 | xargs rm -f
```

---

## Testing

### Run CLI Tests

```bash
# All tests
pytest backend/tests/test_phase11_cli.py -v

# Specific test
pytest backend/tests/test_phase11_cli.py::TestDbCommands -v
```

### Test Coverage

| Component | Tests |
|-----------|-------|
| CLI Parser | 6 |
| DB Commands | 4 |
| Security Commands | 6 |
| Tournament Commands | 4 |
| Deploy Commands | 2 |
| System Commands | 4 |
| Integration | 3 |
| Deployment | 6 |
| **Total** | **35** |

---

## Phase 1-11 Summary

| Phase | Feature | Status |
|-------|---------|--------|
| Phase 1 | Memorial Submissions | ✅ |
| Phase 2 | Oral Rounds | ✅ |
| Phase 3 | Round Pairing | ✅ |
| Phase 4 | Judge Panels | ✅ |
| Phase 5 | Live Courtroom | ✅ |
| Phase 6 | Objection Control | ✅ |
| Phase 7 | Exhibit Management | ✅ |
| Phase 8 | Real-Time Scaling | ✅ |
| Phase 9 | Results & Ranking | ✅ |
| Phase 10 | Final Security Layer | ✅ |
| Phase 11 | CLI & DevOps | ✅ |

---

## Deployment Checklist

### Pre-deployment

- [ ] Environment variables configured
- [ ] Database accessible
- [ ] Redis accessible (if used)
- [ ] SSL certificates ready
- [ ] Backup strategy verified

### Deployment

- [ ] Run database migrations
- [ ] Execute security audit
- [ ] Deploy application code
- [ ] Verify health checks
- [ ] Test critical paths

### Post-deployment

- [ ] Monitor error rates
- [ ] Verify audit logging
- [ ] Check resource usage
- [ ] Test rollback procedure

---

## Operations Runbook

### Daily

```bash
# Check system status
python -m backend.cli system status

# Review audit logs
python -m backend.cli system stats --period day

# Health check
python -m backend.cli deploy health
```

### Weekly

```bash
# Database backup verification
python -m backend.cli db backup --output /backups/weekly.sql

# Security audit
python -m backend.cli security audit

# Review security events
python -m backend.cli system stats --period week
```

### Monthly

```bash
# Full integrity verification
python -m backend.cli db verify --full

# Security header verification
python -m backend.cli security verify --endpoint https://prod.api.com

# Update dependencies
pip install -r requirements.txt --upgrade

# Security audit with full scan
python -m backend.cli security audit --full
```

---

## Troubleshooting

### Service Won't Start

```bash
# Check logs
sudo journalctl -u mootcourt -n 50

# Verify configuration
python -m backend.cli system config --check

# Test database connection
python -m backend.cli deploy status
```

### Database Issues

```bash
# Verify connectivity
python -m backend.cli db verify

# Check migrations status
python -m backend.cli db migrate --all --dry-run

# Restore from backup
python -m backend.cli db restore --input backup.sql --force
```

### Performance Issues

```bash
# Check system resources
python -m backend.cli system status

# Review slow queries
# (Check PostgreSQL logs)

# Monitor WebSocket connections
# (Check Grafana dashboard)
```

---

## Sign-Off

| Component | Status |
|-----------|--------|
| CLI Interface | ✅ Complete |
| Database Ops | ✅ Complete |
| Security Ops | ✅ Complete |
| Tournament Ops | ✅ Complete |
| Docker Deployment | ✅ Complete |
| Systemd Service | ✅ Complete |
| Nginx Proxy | ✅ Complete |
| Monitoring Stack | ✅ Complete |
| Tests | ✅ 35 tests |
| Documentation | ✅ Complete |

**All Phase 11 deliverables complete.**

---

**PHASE 11 IMPLEMENTATION COMPLETE**

Operations-Ready  
Deployment-Ready  
Monitoring-Ready  
Production-Ready
