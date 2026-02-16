#!/usr/bin/env python3
"""
Phase 11 — CLI & DevOps Tooling

Moot Court Tournament Management CLI

Usage:
    python -m backend.cli <command> [options]
    
Commands:
    db          Database operations (migrate, verify, backup)
    security    Security operations (audit, verify, reset)
    tournament  Tournament management (create, finalize, results)
    deploy      Deployment operations (health, status, rollback)
    system      System operations (health, stats, config)

Environment:
    DATABASE_URL    PostgreSQL connection string
    REDIS_URL       Redis connection string (optional)
    LOG_LEVEL       DEBUG|INFO|WARNING|ERROR
"""
import sys
import argparse
import logging
from typing import Optional

from backend.cli.db_commands import DbCommand
from backend.cli.security_commands import SecurityCommand
from backend.cli.tournament_commands import TournamentCommand
from backend.cli.deploy_commands import DeployCommand
from backend.cli.system_commands import SystemCommand
from backend.cli.audit_commands import AuditCommand


def setup_logging(level: str = "INFO") -> None:
    """Configure logging."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )


def create_parser() -> argparse.ArgumentParser:
    """Create CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="mootcourt",
        description="Moot Court Tournament Management CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s db migrate --all
  %(prog)s security audit --full
  %(prog)s tournament finalize --id 42
  %(prog)s deploy health
  %(prog)s system status
        """
    )
    
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 1.0.0"
    )
    
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without executing"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Database commands
    db_parser = subparsers.add_parser("db", help="Database operations")
    db_subparsers = db_parser.add_subparsers(dest="db_action")
    
    # db migrate
    migrate_parser = db_subparsers.add_parser("migrate", help="Run database migrations")
    migrate_parser.add_argument("--all", action="store_true", help="Run all migrations")
    migrate_parser.add_argument("--phase", type=int, help="Run specific phase migration (1-10)")
    migrate_parser.add_argument("--verify", action="store_true", help="Verify after migration")
    
    # db verify
    verify_parser = db_subparsers.add_parser("verify", help="Verify database integrity")
    verify_parser.add_argument("--full", action="store_true", help="Full integrity check")
    
    # db backup
    backup_parser = db_subparsers.add_parser("backup", help="Create database backup")
    backup_parser.add_argument("--output", "-o", required=True, help="Backup file path")
    backup_parser.add_argument("--compress", action="store_true", help="Compress backup")
    
    # db restore
    restore_parser = db_subparsers.add_parser("restore", help="Restore database from backup")
    restore_parser.add_argument("--input", "-i", required=True, help="Backup file path")
    restore_parser.add_argument("--force", action="store_true", help="Skip confirmation")
    
    # Security commands
    security_parser = subparsers.add_parser("security", help="Security operations")
    security_subparsers = security_parser.add_subparsers(dest="security_action")
    
    # security audit
    audit_parser = security_subparsers.add_parser("audit", help="Run security audit")
    audit_parser.add_argument("--full", action="store_true", help="Full security audit")
    audit_parser.add_argument("--integrity", action="store_true", help="Verify audit chain integrity")
    
    # security verify
    verify_sec_parser = security_subparsers.add_parser("verify", help="Verify security headers")
    verify_sec_parser.add_argument("--endpoint", default="http://localhost:8000", help="API endpoint")
    
    # security reset-blocked-ips
    reset_ips_parser = security_subparsers.add_parser("reset-blocked-ips", help="Reset blocked IPs")
    
    # Tournament commands
    tournament_parser = subparsers.add_parser("tournament", help="Tournament management")
    tournament_subparsers = tournament_parser.add_subparsers(dest="tournament_action")
    
    # tournament list
    list_parser = tournament_subparsers.add_parser("list", help="List tournaments")
    list_parser.add_argument("--status", choices=["pending", "active", "completed"], help="Filter by status")
    
    # tournament finalize
    finalize_parser = tournament_subparsers.add_parser("finalize", help="Finalize tournament")
    finalize_parser.add_argument("--id", "-i", type=int, required=True, help="Tournament ID")
    finalize_parser.add_argument("--admin-id", type=int, required=True, help="Admin user ID")
    
    # tournament results
    results_parser = tournament_subparsers.add_parser("results", help="Show tournament results")
    results_parser.add_argument("--id", "-i", type=int, required=True, help="Tournament ID")
    results_parser.add_argument("--verify", action="store_true", help="Verify result integrity")
    
    # Deploy commands
    deploy_parser = subparsers.add_parser("deploy", help="Deployment operations")
    deploy_subparsers = deploy_parser.add_subparsers(dest="deploy_action")
    
    # deploy health
    health_parser = deploy_subparsers.add_parser("health", help="Health check")
    health_parser.add_argument("--endpoint", default="http://localhost:8000/health", help="Health endpoint")
    health_parser.add_argument("--watch", action="store_true", help="Continuous monitoring")
    
    # deploy status
    status_parser = deploy_subparsers.add_parser("status", help="Deployment status")
    
    # System commands
    system_parser = subparsers.add_parser("system", help="System operations")
    system_subparsers = system_parser.add_subparsers(dest="system_action")
    
    # system status
    system_status_parser = system_subparsers.add_parser("status", help="System status")
    
    # system stats
    stats_parser = system_subparsers.add_parser("stats", help="System statistics")
    stats_parser.add_argument("--period", choices=["hour", "day", "week"], default="day")
    
    # system config
    config_parser = system_subparsers.add_parser("config", help="Show configuration")
    config_parser.add_argument("--check", action="store_true", help="Validate configuration")
    
    # Phase 12 - Audit commands
    audit_parser = subparsers.add_parser("audit", help="Tournament audit operations")
    audit_subparsers = audit_parser.add_subparsers(dest="audit_action")
    
    # audit generate
    audit_gen_parser = audit_subparsers.add_parser("generate", help="Generate audit snapshot")
    audit_gen_parser.add_argument("--tournament", "-t", type=int, required=True, help="Tournament ID")
    
    # audit verify
    audit_verify_parser = audit_subparsers.add_parser("verify", help="Verify audit snapshot")
    audit_verify_parser.add_argument("--tournament", "-t", type=int, required=True, help="Tournament ID")
    
    # audit export
    audit_export_parser = audit_subparsers.add_parser("export", help="Export audit bundle")
    audit_export_parser.add_argument("--tournament", "-t", type=int, required=True, help="Tournament ID")
    audit_export_parser.add_argument("--output", "-o", required=True, help="Output path")
    
    # audit certificate
    audit_cert_parser = audit_subparsers.add_parser("certificate", help="Generate certificate")
    audit_cert_parser.add_argument("--tournament", "-t", type=int, required=True, help="Tournament ID")
    audit_cert_parser.add_argument("--format", choices=["json", "text"], default="json", help="Output format")
    
    return parser


def main(args: Optional[list] = None) -> int:
    """Main entry point."""
    parser = create_parser()
    parsed = parser.parse_args(args)
    
    if not parsed.command:
        parser.print_help()
        return 1
    
    # Setup logging
    setup_logging(parsed.log_level)
    
    # Route to appropriate command handler
    command_map = {
        "db": DbCommand,
        "security": SecurityCommand,
        "tournament": TournamentCommand,
        "deploy": DeployCommand,
        "system": SystemCommand,
        "audit": AuditCommand,
    }
    
    if parsed.command in command_map:
        handler = command_map[parsed.command](dry_run=parsed.dry_run)
        return handler.execute(parsed)
    
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
