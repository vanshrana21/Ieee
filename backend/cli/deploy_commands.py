"""
Phase 11 — Deploy CLI Commands

Deployment operations: health check, status
"""
import sys
import time
import requests
from typing import Optional


class DeployCommand:
    """Deploy CLI command handler."""
    
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
    
    def execute(self, args) -> int:
        """Execute deploy command."""
        if args.deploy_action == "health":
            return self._health(args)
        elif args.deploy_action == "status":
            return self._status(args)
        else:
            print("Error: Unknown deploy action")
            return 1
    
    def _health(self, args) -> int:
        """Health check."""
        endpoint = args.endpoint
        
        print("=== Health Check ===")
        print(f"Endpoint: {endpoint}")
        
        if args.watch:
            print("\nPress Ctrl+C to stop\n")
            try:
                while True:
                    self._check_health(endpoint)
                    time.sleep(5)
            except KeyboardInterrupt:
                print("\nStopped")
                return 0
        else:
            return self._check_health(endpoint)
    
    def _check_health(self, endpoint: str) -> int:
        """Single health check."""
        try:
            start = time.time()
            response = requests.get(endpoint, timeout=10)
            duration = (time.time() - start) * 1000
            
            timestamp = time.strftime("%H:%M:%S")
            
            if response.status_code == 200:
                data = response.json()
                status = data.get("status", "unknown")
                
                if status == "healthy":
                    print(f"[{timestamp}] ✓ HEALTHY ({duration:.0f}ms)")
                    return 0
                else:
                    print(f"[{timestamp}] ⚠ {status.upper()} ({duration:.0f}ms)")
                    return 1
            else:
                print(f"[{timestamp}] ✗ ERROR {response.status_code}")
                return 1
                
        except requests.RequestException as e:
            timestamp = time.strftime("%H:%M:%S")
            print(f"[{timestamp}] ✗ UNREACHABLE: {e}")
            return 1
    
    def _status(self, args) -> int:
        """Show deployment status."""
        print("=== Deployment Status ===")
        
        checks = [
            ("Database", self._check_database),
            ("API Server", self._check_api),
            ("Redis", self._check_redis),
            ("Audit Log", self._check_audit_log),
        ]
        
        all_healthy = True
        
        for name, check_func in checks:
            print(f"\n{name}...")
            try:
                healthy = check_func()
                status = "✓" if healthy else "✗"
                print(f"  {status} {name}")
                if not healthy:
                    all_healthy = False
            except Exception as e:
                print(f"  ✗ {name}: {e}")
                all_healthy = False
        
        print("\n" + "=" * 30)
        if all_healthy:
            print("✓ All systems operational")
            return 0
        else:
            print("✗ Some systems unhealthy")
            return 1
    
    def _check_database(self) -> bool:
        """Check database connectivity."""
        import os
        import asyncio
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy import text
        
        database_url = os.environ.get(
            "DATABASE_URL",
            "postgresql+asyncpg://moot_user:moot_pass@localhost:5432/moot_court"
        )
        
        async def check():
            engine = create_async_engine(database_url)
            try:
                async with engine.connect() as conn:
                    result = await conn.execute(text("SELECT 1"))
                    return result.scalar() == 1
            finally:
                await engine.dispose()
        
        return asyncio.run(check())
    
    def _check_api(self) -> bool:
        """Check API server."""
        try:
            response = requests.get("http://localhost:8000/health", timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def _check_redis(self) -> bool:
        """Check Redis connectivity."""
        try:
            import aioredis
            
            async def check():
                redis = await aioredis.from_url("redis://localhost:6379/0")
                try:
                    await redis.ping()
                    return True
                finally:
                    await redis.close()
            
            return asyncio.run(check())
        except:
            return False
    
    def _check_audit_log(self) -> bool:
        """Check audit log."""
        import os
        import asyncio
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy import text
        
        database_url = os.environ.get(
            "DATABASE_URL",
            "postgresql+asyncpg://moot_user:moot_pass@localhost:5432/moot_court"
        )
        
        async def check():
            engine = create_async_engine(database_url)
            try:
                async with engine.connect() as conn:
                    result = await conn.execute(
                        text("SELECT COUNT(*) FROM audit_log LIMIT 1")
                    )
                    # If query succeeds, audit log is accessible
                    return True
            except:
                return False
            finally:
                await engine.dispose()
        
        return asyncio.run(check())
