#!/bin/bash
# Environment Snapshot Script for Windsurf Test Harness
# Captures environment state before test runs

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
OUTPUT_DIR="${PROJECT_ROOT}/artifacts/env_snapshots/$(date +%Y%m%d_%H%M%S)"

mkdir -p "$OUTPUT_DIR"

echo "=== Windsurf Environment Snapshot ==="
echo "Output: $OUTPUT_DIR"
echo ""

# 1. Environment variables (filtered)
echo "Capturing environment variables..."
env | sort | grep -E '^(PYTHON|PG_|DB_|REDIS_|API_|HOST|PORT|ENV|FEATURE_)' > "$OUTPUT_DIR/windsurf_env_snapshot.txt" 2>/dev/null || true
echo "  ✓ Environment snapshot saved"

# 2. Git state
echo "Capturing Git state..."
cd "$PROJECT_ROOT"
git rev-parse --abbrev-ref HEAD > "$OUTPUT_DIR/windsurf_branch.txt" 2>/dev/null || echo "unknown" > "$OUTPUT_DIR/windsurf_branch.txt"
git rev-parse HEAD > "$OUTPUT_DIR/windsurf_commit.txt" 2>/dev/null || echo "unknown" > "$OUTPUT_DIR/windsurf_commit.txt"
git log --oneline -5 > "$OUTPUT_DIR/windsurf_recent_commits.txt" 2>/dev/null || true
git status --short > "$OUTPUT_DIR/windsurf_git_status.txt" 2>/dev/null || true
echo "  ✓ Git state captured"

# 3. Python environment
echo "Capturing Python environment..."
python3 -V > "$OUTPUT_DIR/windsurf_py_version.txt" 2>&1 || python -V > "$OUTPUT_DIR/windsurf_py_version.txt" 2>&1
pip freeze > "$OUTPUT_DIR/windsurf_pip_freeze.txt" 2>/dev/null || echo "pip not available" > "$OUTPUT_DIR/windsurf_pip_freeze.txt"
echo "  ✓ Python environment captured"

# 4. Database schema
echo "Capturing database schema..."
if [ -n "$PG_HOST" ] && [ -n "$PG_USER" ] && [ -n "$PG_DB" ]; then
    # PostgreSQL
    PGPASSWORD="${PG_PASS:-}" psql -h "$PG_HOST" -U "$PG_USER" -d "$PG_DB" -c "\d+" > "$OUTPUT_DIR/windsurf_db_schema.txt" 2>/dev/null || \
        echo "PostgreSQL connection failed" > "$OUTPUT_DIR/windsurf_db_schema.txt"
elif [ -f "$PROJECT_ROOT/data/dev.db" ]; then
    # SQLite
    sqlite3 "$PROJECT_ROOT/data/dev.db" .schema > "$OUTPUT_DIR/windsurf_db_schema.txt" 2>/dev/null || \
        echo "SQLite read failed" > "$OUTPUT_DIR/windsurf_db_schema.txt"
else
    echo "No database detected" > "$OUTPUT_DIR/windsurf_db_schema.txt"
fi
echo "  ✓ Database schema captured"

# 5. System info
echo "Capturing system info..."
uname -a > "$OUTPUT_DIR/windsurf_system_info.txt" 2>/dev/null || systeminfo > "$OUTPUT_DIR/windsurf_system_info.txt" 2>/dev/null || echo "unknown" > "$OUTPUT_DIR/windsurf_system_info.txt"
echo "  ✓ System info captured"

# 6. Feature flags
echo "Capturing feature flags..."
python3 << 'EOF' > "$OUTPUT_DIR/windsurf_feature_flags.txt" 2>/dev/null || echo "Feature flag capture failed" > "$OUTPUT_DIR/windsurf_feature_flags.txt"
import sys
sys.path.insert(0, '.')
try:
    from backend.config.feature_flags import feature_flags
    for attr in dir(feature_flags):
        if attr.startswith('FEATURE_'):
            print(f"{attr}: {getattr(feature_flags, attr)}")
except Exception as e:
    print(f"Error: {e}")
EOF
echo "  ✓ Feature flags captured"

# 7. Summary
echo ""
echo "=== Snapshot Complete ==="
echo "Location: $OUTPUT_DIR"
echo "Files:"
ls -la "$OUTPUT_DIR/"

# Create symlink to latest
ln -sfn "$OUTPUT_DIR" "${PROJECT_ROOT}/artifacts/env_snapshots/latest"
echo ""
echo "Symlink created: artifacts/env_snapshots/latest -> $OUTPUT_DIR"
