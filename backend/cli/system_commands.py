"""
Phase 11 — System CLI Commands

System operations: status, stats, config
"""
import sys
import os
import platform
import psutil
from datetime import datetime, timedelta
from typing import Dict, Any


class SystemCommand:
    """System CLI command handler."""
    
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
    
    def execute(self, args) -> int:
        """Execute system command."""
        if args.system_action == "status":
            return self._status(args)
        elif args.system_action == "stats":
            return self._stats(args)
        elif args.system_action == "config":
            return self._config(args)
        else:
            print("Error: Unknown system action")
            return 1
    
    def _status(self, args) -> int:
        """Show system status."""
        print("=== System Status ===")
        
        # Platform info
        print(f"\nPlatform: {platform.system()} {platform.release()}")
        print(f"Python: {platform.python_version()}")
        print(f"Time: {datetime.utcnow().isoformat()} UTC")
        
        # Resource usage
        print("\n--- Resource Usage ---")
        
        # CPU
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_count = psutil.cpu_count()
        print(f"CPU: {cpu_percent:.1f}% ({cpu_count} cores)")
        
        # Memory
        memory = psutil.virtual_memory()
        print(f"Memory: {memory.percent:.1f}% used ({memory.used // (1024**3)}GB / {memory.total // (1024**3)}GB)")
        
        # Disk
        disk = psutil.disk_usage('/')
        print(f"Disk: {disk.percent:.1f}% used ({disk.used // (1024**3)}GB / {disk.total // (1024**3)}GB)")
        
        # Load average (Unix only)
        if hasattr(os, 'getloadavg'):
            load1, load5, load15 = os.getloadavg()
            print(f"Load: {load1:.2f} (1m), {load5:.2f} (5m), {load15:.2f} (15m)")
        
        # Network
        net_io = psutil.net_io_counters()
        print(f"Network: ↑{net_io.bytes_sent // (1024**2)}MB ↓{net_io.bytes_recv // (1024**2)}MB")
        
        return 0
    
    def _stats(self, args) -> int:
        """Show system statistics."""
        print(f"=== System Statistics ({args.period}) ===")
        
        try:
            import asyncio
            asyncio.run(self._async_stats(args.period))
            return 0
        except Exception as e:
            print(f"Error: {e}")
            return 1
    
    async def _async_stats(self, period: str) -> None:
        """Async system statistics."""
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy import select, func, and_
        from datetime import datetime, timedelta
        
        database_url = os.environ.get(
            "DATABASE_URL",
            "postgresql+asyncpg://moot_user:moot_pass@localhost:5432/moot_court"
        )
        
        engine = create_async_engine(database_url)
        
        # Calculate time range
        now = datetime.utcnow()
        if period == "hour":
            start = now - timedelta(hours=1)
        elif period == "day":
            start = now - timedelta(days=1)
        elif period == "week":
            start = now - timedelta(weeks=1)
        else:
            start = now - timedelta(days=1)
        
        async with engine.connect() as conn:
            # Audit log stats
            from backend.security.audit_logger import AuditLogEntry
            
            result = await conn.execute(
                select(func.count(AuditLogEntry.id))
                .where(AuditLogEntry.timestamp >= start)
            )
            audit_count = result.scalar()
            
            print(f"\nAudit Log Entries: {audit_count}")
            
            # Security events
            result = await conn.execute(
                select(func.count(AuditLogEntry.id))
                .where(
                    and_(
                        AuditLogEntry.event_type == "SECURITY_EVENT",
                        AuditLogEntry.timestamp >= start
                    )
                )
            )
            security_count = result.scalar()
            
            print(f"Security Events: {security_count}")
            
            # Unique users
            result = await conn.execute(
                select(func.count(func.distinct(AuditLogEntry.user_id)))
                .where(AuditLogEntry.timestamp >= start)
            )
            unique_users = result.scalar()
            
            print(f"Active Users: {unique_users}")
            
            # Requests per hour (if hour period)
            if period == "hour":
                print("\n--- Requests Per 10 Minutes ---")
                for i in range(6):
                    segment_start = start + timedelta(minutes=i*10)
                    segment_end = segment_start + timedelta(minutes=10)
                    
                    result = await conn.execute(
                        select(func.count(AuditLogEntry.id))
                        .where(
                            and_(
                                AuditLogEntry.timestamp >= segment_start,
                                AuditLogEntry.timestamp < segment_end
                            )
                        )
                    )
                    count = result.scalar()
                    print(f"  {segment_start.strftime('%H:%M')}: {count} requests")
        
        await engine.dispose()
    
    def _config(self, args) -> int:
        """Show system configuration."""
        print("=== System Configuration ===")
        
        # Environment variables
        print("\n--- Environment ---")
        
        env_vars = [
            "DATABASE_URL",
            "REDIS_URL",
            "SECRET_KEY",
            "LOG_LEVEL",
            "USE_REDIS_BROADCAST",
        ]
        
        for var in env_vars:
            value = os.environ.get(var, "NOT SET")
            # Mask sensitive values
            if var in ("DATABASE_URL", "REDIS_URL", "SECRET_KEY") and value != "NOT SET":
                value = value[:20] + "..."
            print(f"  {var}: {value}")
        
        # Check configuration
        if args.check:
            print("\n--- Configuration Check ---")
            
            checks = [
                ("Database URL", lambda: bool(os.environ.get("DATABASE_URL"))),
                ("Secret Key", lambda: bool(os.environ.get("SECRET_KEY"))),
                ("Writable Temp", lambda: os.access('/tmp', os.W_OK)),
            ]
            
            all_passed = True
            for name, check_func in checks:
                try:
                    passed = check_func()
                    status = "✓" if passed else "✗"
                    print(f"  {status} {name}")
                    if not passed:
                        all_passed = False
                except Exception as e:
                    print(f"  ✗ {name}: {e}")
                    all_passed = False
            
            if all_passed:
                print("\n✓ All checks passed")
            else:
                print("\n✗ Some checks failed")
        
        return 0
