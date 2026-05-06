#!/usr/bin/env bash
# ============================================================
#  OASIS - One-command updater
# ============================================================
#  Usage (on the server):
#
#      bash /opt/oasis/scripts/update.sh
#
#  Or, if /opt/oasis/scripts/update.sh isn't there yet:
#
#      curl -fsSL https://raw.githubusercontent.com/oasis-surveys/oasis-platform/main/scripts/update.sh | bash
#
#  What it does:
#    1. Pulls latest code from main
#    2. Rebuilds containers
#    3. Restarts services with zero-downtime where possible
#    4. Prunes old build cache to save disk
#    5. Optionally backs up the database first (--backup flag)
#
#  Postgres + Redis data live in Docker volumes and are preserved.
# ============================================================

set -euo pipefail

# ── Colours ──────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

log()    { printf "${BLUE}[oasis]${NC} %s\n" "$*"; }
ok()     { printf "${GREEN}[ ok ]${NC} %s\n" "$*"; }
warn()   { printf "${YELLOW}[warn]${NC} %s\n" "$*"; }
fail()   { printf "${RED}[fail]${NC} %s\n" "$*" >&2; exit 1; }

INSTALL_DIR="${OASIS_DIR:-/opt/oasis}"
DO_BACKUP=0
SKIP_BUILD=0

# ── Parse args ───────────────────────────────────────────────
for arg in "$@"; do
    case "$arg" in
        --backup)        DO_BACKUP=1 ;;
        --no-build)      SKIP_BUILD=1 ;;
        -h|--help)
            cat <<HELP
Usage: $0 [options]

Options:
  --backup       Dump the Postgres database to ./backups/ before updating
  --no-build     Pull code only, skip 'docker compose build' (faster, but
                 requires no Dockerfile / dependency changes)
  -h, --help     Show this help
HELP
            exit 0
            ;;
        *) fail "Unknown option: $arg (try --help)" ;;
    esac
done

# ── Sanity checks ────────────────────────────────────────────
if [[ ! -d "$INSTALL_DIR/.git" ]]; then
    fail "OASIS isn't installed at $INSTALL_DIR. Run install.sh first, or set OASIS_DIR env var."
fi

cd "$INSTALL_DIR"

if ! command -v docker >/dev/null 2>&1; then
    fail "Docker isn't installed."
fi

# ── 1. Optional backup ───────────────────────────────────────
if [[ $DO_BACKUP -eq 1 ]]; then
    log "Backing up database before update…"
    BACKUP_DIR="$INSTALL_DIR/backups"
    mkdir -p "$BACKUP_DIR"
    TIMESTAMP=$(date +%Y%m%d-%H%M%S)
    BACKUP_FILE="$BACKUP_DIR/oasis-$TIMESTAMP.sql.gz"

    # Read POSTGRES_USER / POSTGRES_DB from .env (defaults match docker-compose.yml)
    PG_USER=$(grep -E '^POSTGRES_USER=' .env | head -1 | cut -d= -f2- | tr -d '"' || echo surveyor)
    PG_DB=$(grep -E '^POSTGRES_DB=' .env | head -1 | cut -d= -f2- | tr -d '"' || echo surveyor)
    PG_USER=${PG_USER:-surveyor}
    PG_DB=${PG_DB:-surveyor}

    docker compose exec -T postgres pg_dump -U "$PG_USER" "$PG_DB" | gzip > "$BACKUP_FILE"
    ok "Backup written to $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"
fi

# ── 2. Pull latest code ──────────────────────────────────────
log "Fetching latest code…"
CURRENT_REV=$(git rev-parse HEAD)
git fetch --all --prune
git reset --hard origin/main
NEW_REV=$(git rev-parse HEAD)

if [[ "$CURRENT_REV" == "$NEW_REV" ]]; then
    ok "Already on the latest commit ($NEW_REV). Nothing to update."
    log "If you want to force a rebuild anyway, run: docker compose up -d --build"
    exit 0
fi

echo
log "Updating from $CURRENT_REV  →  $NEW_REV"
log "Changes since last update:"
git log --oneline "$CURRENT_REV..$NEW_REV" | sed 's/^/    /'
echo

# ── 3. Rebuild + restart ─────────────────────────────────────
if [[ $SKIP_BUILD -eq 0 ]]; then
    log "Rebuilding containers…"
    docker compose build
fi

log "Starting / restarting services…"
docker compose up -d

# ── 4. Verify ────────────────────────────────────────────────
echo
log "Container status:"
docker compose ps

# ── 5. Cleanup old images ────────────────────────────────────
log "Pruning old Docker images…"
docker image prune -af --filter "until=168h" >/dev/null 2>&1 || true

echo
ok "═══════════════════════════════════════════════════════════"
ok "  Update complete!"
ok "═══════════════════════════════════════════════════════════"
echo
echo "  ${BOLD}Verify:${NC}"
echo "    docker compose logs -f          # tail all logs"
echo "    docker compose ps               # status"
echo
if [[ $DO_BACKUP -eq 1 ]]; then
    echo "  ${BOLD}Restore from backup if needed:${NC}"
    echo "    gunzip -c $BACKUP_FILE | docker compose exec -T postgres psql -U $PG_USER -d $PG_DB"
    echo
fi
