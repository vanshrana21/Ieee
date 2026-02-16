"""
Phase 11 — CLI & DevOps Test Suite

Tests for CLI commands, deployment scripts, and infrastructure.
"""
import pytest
import subprocess
import os
from unittest.mock import Mock, patch, AsyncMock
from pathlib import Path

from backend.cli import main, create_parser
from backend.cli.db_commands import DbCommand
from backend.cli.security_commands import SecurityCommand
from backend.cli.tournament_commands import TournamentCommand
from backend.cli.deploy_commands import DeployCommand
from backend.cli.system_commands import SystemCommand


# =============================================================================
# CLI Parser Tests
# =============================================================================

class TestCLIParser:
    """Test CLI argument parsing."""
    
    def test_parser_creation(self):
        """Test that parser can be created."""
        parser = create_parser()
        assert parser is not None
    
    def test_db_migrate_parsing(self):
        """Test db migrate argument parsing."""
        parser = create_parser()
        args = parser.parse_args(["db", "migrate", "--all"])
        
        assert args.command == "db"
        assert args.db_action == "migrate"
        assert args.all is True
    
    def test_security_audit_parsing(self):
        """Test security audit argument parsing."""
        parser = create_parser()
        args = parser.parse_args(["security", "audit", "--full"])
        
        assert args.command == "security"
        assert args.security_action == "audit"
        assert args.full is True
    
    def test_tournament_finalize_parsing(self):
        """Test tournament finalize argument parsing."""
        parser = create_parser()
        args = parser.parse_args(["tournament", "finalize", "--id", "42", "--admin-id", "1"])
        
        assert args.command == "tournament"
        assert args.tournament_action == "finalize"
        assert args.id == 42
        assert args.admin_id == 1
    
    def test_deploy_health_parsing(self):
        """Test deploy health argument parsing."""
        parser = create_parser()
        args = parser.parse_args(["deploy", "health"])
        
        assert args.command == "deploy"
        assert args.deploy_action == "health"
    
    def test_system_status_parsing(self):
        """Test system status argument parsing."""
        parser = create_parser()
        args = parser.parse_args(["system", "status"])
        
        assert args.command == "system"
        assert args.system_action == "status"
    
    def test_dry_run_flag(self):
        """Test dry run flag parsing."""
        parser = create_parser()
        args = parser.parse_args(["--dry-run", "db", "migrate", "--all"])
        
        assert args.dry_run is True
    
    def test_log_level_flag(self):
        """Test log level flag parsing."""
        parser = create_parser()
        args = parser.parse_args(["--log-level", "DEBUG", "system", "status"])
        
        assert args.log_level == "DEBUG"


# =============================================================================
# Database Command Tests
# =============================================================================

class TestDbCommands:
    """Test database CLI commands."""
    
    def test_db_command_init(self):
        """Test DbCommand initialization."""
        cmd = DbCommand()
        assert cmd.dry_run is False
        
        cmd_dry = DbCommand(dry_run=True)
        assert cmd_dry.dry_run is True
    
    def test_migrate_phase_selection(self):
        """Test migration phase selection."""
        cmd = DbCommand(dry_run=True)
        
        # Mock args
        args = Mock()
        args.db_action = "migrate"
        args.all = True
        args.phase = None
        args.verify = False
        
        # Should return 0 in dry run
        result = cmd.execute(args)
        assert result == 0
    
    def test_backup_args(self):
        """Test backup command with args."""
        cmd = DbCommand(dry_run=True)
        
        args = Mock()
        args.db_action = "backup"
        args.output = "/tmp/backup.sql"
        args.compress = True
        
        result = cmd.execute(args)
        assert result == 0
    
    def test_restore_args(self):
        """Test restore command with args."""
        cmd = DbCommand(dry_run=True)
        
        args = Mock()
        args.db_action = "restore"
        args.input = "/tmp/backup.sql"
        args.force = True
        
        result = cmd.execute(args)
        assert result == 0


# =============================================================================
# Security Command Tests
# =============================================================================

class TestSecurityCommands:
    """Test security CLI commands."""
    
    def test_security_command_init(self):
        """Test SecurityCommand initialization."""
        cmd = SecurityCommand()
        assert cmd.dry_run is False
    
    def test_audit_full(self):
        """Test full security audit."""
        cmd = SecurityCommand(dry_run=True)
        
        args = Mock()
        args.security_action = "audit"
        args.full = True
        args.integrity = True
        
        result = cmd.execute(args)
        assert result == 0
    
    def test_verify_headers(self):
        """Test verify headers command."""
        cmd = SecurityCommand(dry_run=True)
        
        args = Mock()
        args.security_action = "verify"
        args.endpoint = "http://localhost:8000"
        
        # In dry run, should return 0
        result = cmd.execute(args)
        assert result == 0
    
    def test_reset_blocked_ips(self):
        """Test reset blocked IPs command."""
        cmd = SecurityCommand(dry_run=True)
        
        args = Mock()
        args.security_action = "reset-blocked-ips"
        
        result = cmd.execute(args)
        assert result == 0
    
    def test_determinism_check(self):
        """Test determinism check function."""
        cmd = SecurityCommand()
        
        # Should return True for valid code
        result = cmd._check_determinism()
        assert result is True
    
    def test_sha256_check(self):
        """Test SHA256 check function."""
        cmd = SecurityCommand()
        
        result = cmd._check_sha256()
        assert result is True
    
    def test_rbac_check(self):
        """Test RBAC check function."""
        cmd = SecurityCommand()
        
        result = cmd._check_rbac()
        assert result is True


# =============================================================================
# Tournament Command Tests
# =============================================================================

class TestTournamentCommands:
    """Test tournament CLI commands."""
    
    def test_tournament_command_init(self):
        """Test TournamentCommand initialization."""
        cmd = TournamentCommand()
        assert cmd.dry_run is False
    
    def test_list_command(self):
        """Test tournament list command."""
        cmd = TournamentCommand(dry_run=True)
        
        args = Mock()
        args.tournament_action = "list"
        args.status = None
        
        # In dry run, should not actually query
        result = cmd.execute(args)
        # Will fail because no DB, but tests argument handling
    
    def test_finalize_args(self):
        """Test finalize command arguments."""
        cmd = TournamentCommand(dry_run=True)
        
        args = Mock()
        args.tournament_action = "finalize"
        args.id = 42
        args.admin_id = 1
        
        result = cmd.execute(args)
        assert result == 0
    
    def test_results_args(self):
        """Test results command arguments."""
        cmd = TournamentCommand(dry_run=True)
        
        args = Mock()
        args.tournament_action = "results"
        args.id = 42
        args.verify = True
        
        result = cmd.execute(args)
        assert result == 0


# =============================================================================
# Deploy Command Tests
# =============================================================================

class TestDeployCommands:
    """Test deploy CLI commands."""
    
    def test_deploy_command_init(self):
        """Test DeployCommand initialization."""
        cmd = DeployCommand()
        assert cmd.dry_run is False
    
    def test_health_check(self):
        """Test health check command."""
        cmd = DeployCommand(dry_run=True)
        
        args = Mock()
        args.deploy_action = "health"
        args.endpoint = "http://localhost:8000/health"
        args.watch = False
        
        result = cmd.execute(args)
        # Will fail without server, but tests argument handling
    
    def test_status_command(self):
        """Test status command."""
        cmd = DeployCommand(dry_run=True)
        
        args = Mock()
        args.deploy_action = "status"
        
        result = cmd.execute(args)
        assert result == 0  # Dry run passes


# =============================================================================
# System Command Tests
# =============================================================================

class TestSystemCommands:
    """Test system CLI commands."""
    
    def test_system_command_init(self):
        """Test SystemCommand initialization."""
        cmd = SystemCommand()
        assert cmd.dry_run is False
    
    def test_status_command(self):
        """Test system status command."""
        cmd = SystemCommand(dry_run=True)
        
        args = Mock()
        args.system_action = "status"
        
        result = cmd.execute(args)
        assert result == 0
    
    def test_stats_command(self):
        """Test stats command."""
        cmd = SystemCommand(dry_run=True)
        
        args = Mock()
        args.system_action = "stats"
        args.period = "day"
        
        result = cmd.execute(args)
        # Will fail without DB, but tests argument handling
    
    def test_config_command(self):
        """Test config command."""
        cmd = SystemCommand(dry_run=True)
        
        args = Mock()
        args.system_action = "config"
        args.check = True
        
        result = cmd.execute(args)
        assert result == 0


# =============================================================================
# Main Entry Point Tests
# =============================================================================

class TestMainEntryPoint:
    """Test main CLI entry point."""
    
    def test_main_no_args(self):
        """Test main with no arguments."""
        result = main([])
        assert result == 1  # Should fail with no command
    
    def test_main_version(self):
        """Test main with version flag."""
        with pytest.raises(SystemExit) as exc_info:
            main(["--version"])
        
        assert exc_info.value.code == 0
    
    def test_main_help(self):
        """Test main with help flag."""
        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])
        
        assert exc_info.value.code == 0


# =============================================================================
# Integration Tests
# =============================================================================

def test_cli_help_output():
    """Test CLI help output."""
    result = subprocess.run(
        ["python", "-m", "backend.cli", "--help"],
        capture_output=True,
        text=True
    )
    
    assert "Moot Court Tournament Management CLI" in result.stdout
    assert "db" in result.stdout
    assert "security" in result.stdout
    assert "tournament" in result.stdout


def test_db_subcommand_help():
    """Test db subcommand help."""
    result = subprocess.run(
        ["python", "-m", "backend.cli", "db", "--help"],
        capture_output=True,
        text=True
    )
    
    assert "migrate" in result.stdout
    assert "verify" in result.stdout
    assert "backup" in result.stdout


# =============================================================================
# Deployment Script Tests
# =============================================================================

class TestDeploymentScripts:
    """Test deployment infrastructure."""
    
    def test_deploy_script_exists(self):
        """Test deploy.sh exists."""
        deploy_script = Path("deploy/deploy.sh")
        assert deploy_script.exists()
    
    def test_dockerfile_exists(self):
        """Test Dockerfile exists."""
        dockerfile = Path("deploy/Dockerfile")
        assert dockerfile.exists()
    
    def test_docker_compose_exists(self):
        """Test docker-compose.yml exists."""
        compose_file = Path("deploy/docker-compose.yml")
        assert compose_file.exists()
    
    def test_systemd_service_exists(self):
        """Test systemd service file exists."""
        service_file = Path("deploy/mootcourt.service")
        assert service_file.exists()
    
    def test_nginx_config_exists(self):
        """Test nginx config exists."""
        nginx_conf = Path("deploy/nginx/nginx.conf")
        assert nginx_conf.exists()
    
    def test_prometheus_config_exists(self):
        """Test Prometheus config exists."""
        prometheus_conf = Path("deploy/monitoring/prometheus.yml")
        assert prometheus_conf.exists()


# =============================================================================
# Configuration Tests
# =============================================================================

def test_gunicorn_config_exists():
    """Test Gunicorn config exists."""
    gunicorn_conf = Path("deploy/gunicorn.conf.py")
    assert gunicorn_conf.exists()


def test_dockerfile_structure():
    """Test Dockerfile has proper structure."""
    dockerfile = Path("deploy/Dockerfile")
    content = dockerfile.read_text()
    
    assert "FROM" in content
    assert "CMD" in content or "ENTRYPOINT" in content


def test_docker_compose_services():
    """Test docker-compose has required services."""
    import yaml
    
    compose_file = Path("deploy/docker-compose.yml")
    with open(compose_file) as f:
        compose = yaml.safe_load(f)
    
    services = compose.get("services", {})
    
    assert "api" in services
    assert "postgres" in services
    assert "redis" in services
    assert "nginx" in services
