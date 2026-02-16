"""
Phase 11 — Gunicorn Configuration

Production-ready Gunicorn settings for Moot Court API.
"""
import os
import multiprocessing

# Server socket
bind = "0.0.0.0:8000"
backlog = 2048

# Worker processes
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 1000
timeout = 120
keepalive = 5

# Logging
accesslog = "/app/logs/gunicorn_access.log"
errorlog = "/app/logs/gunicorn_error.log"
loglevel = os.environ.get("LOG_LEVEL", "info").lower()
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = "mootcourt"

# Server mechanics
daemon = False
pidfile = "/tmp/gunicorn.pid"

# SSL (handled by Nginx in production)
# keyfile = 
# certfile = 

# Security
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

# Server hooks
def on_starting(server):
    """Called just before the master process is initialized."""
    pass

def on_reload(server):
    """Called when receiving SIGHUP signal."""
    pass

def when_ready(server):
    """Called just after the server is started."""
    pass

def worker_int(worker):
    """Called when a worker receives SIGINT or SIGQUIT."""
    pass

def on_exit(server):
    """Called just before exiting Gunicorn."""
    pass
