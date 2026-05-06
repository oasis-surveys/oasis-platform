#!/usr/bin/env bash
# ============================================================
#  OASIS - One-command Hetzner / Ubuntu installer
# ============================================================
#  Usage (on a fresh Ubuntu 22.04+ server, as root):
#
#      curl -fsSL https://raw.githubusercontent.com/oasis-surveys/oasis-platform/main/scripts/install.sh | bash
#
#  Or, if you've already cloned the repo:
#
#      sudo bash scripts/install.sh
#
#  The script:
#    1. Updates the system and reboots if a new kernel was installed
#    2. Installs Docker + Docker Compose
#    3. Configures UFW firewall (22, 80, 443)
#    4. Installs fail2ban + unattended-upgrades
#    5. Clones the OASIS repo to /opt/oasis (if not already present)
#    6. Prompts for domain + OPENAI_API_KEY (or reuses existing .env)
#    7. Generates random SECRET_KEY, POSTGRES_PASSWORD, AUTH_PASSWORD
#    8. Configures the Caddyfile for the chosen domain
#    9. Builds and starts all containers
#
#  Total runtime: ~8 min on a fresh server.
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
header() { printf "\n${BOLD}=== %s ===${NC}\n\n" "$*"; }

# ── Sanity checks ────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
    fail "Please run as root (use sudo). Needed for apt, ufw, and Docker install."
fi

if ! command -v lsb_release >/dev/null 2>&1; then
    apt update && apt install -y lsb-release
fi

OS_ID=$(lsb_release -is)
OS_VER=$(lsb_release -rs)
if [[ "$OS_ID" != "Ubuntu" ]]; then
    warn "This script is tested on Ubuntu. You're on $OS_ID $OS_VER. Proceed with caution."
fi

REPO_URL="https://github.com/oasis-surveys/oasis-platform.git"
INSTALL_DIR="/opt/oasis"

export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=a
export NEEDRESTART_SUSPEND=1

# ── Step 1: System update ────────────────────────────────────
header "1/9  Updating system packages"
apt update -qq
apt upgrade -y -qq
apt install -y -qq curl git nano openssl ca-certificates gnupg lsb-release jq
ok "System updated."

# ── Step 2: Pending kernel reboot? ───────────────────────────
header "2/9  Checking for pending kernel reboot"
if [[ -f /var/run/reboot-required ]]; then
    warn "A reboot is required to load a new kernel."
    warn "After the reboot, reconnect via SSH and re-run this same command."
    warn "The script will resume from where it left off."
    read -rp "Reboot now? [Y/n]: " REPLY
    REPLY=${REPLY:-Y}
    if [[ "$REPLY" =~ ^[Yy]$ ]]; then
        log "Rebooting in 5s…"
        sleep 5
        reboot
        exit 0
    else
        warn "Skipping reboot. You should reboot manually before going to production."
    fi
else
    ok "No reboot required."
fi

# ── Step 3: Install Docker ───────────────────────────────────
header "3/9  Installing Docker"
if command -v docker >/dev/null 2>&1; then
    ok "Docker already installed: $(docker --version)"
else
    curl -fsSL https://get.docker.com | sh
    ok "Docker installed: $(docker --version)"
fi
systemctl enable --now docker

# ── Step 4: Configure firewall ───────────────────────────────
header "4/9  Configuring UFW firewall"
if ! command -v ufw >/dev/null 2>&1; then
    apt install -y -qq ufw
fi
ufw default deny incoming  >/dev/null
ufw default allow outgoing >/dev/null
ufw allow 22/tcp  comment 'SSH'  >/dev/null
ufw allow 80/tcp  comment 'HTTP' >/dev/null
ufw allow 443/tcp comment 'HTTPS' >/dev/null
ufw --force enable >/dev/null
ok "UFW configured: 22, 80, 443 open."

# ── Step 5: Hardening (fail2ban + unattended-upgrades) ───────
header "5/9  Installing fail2ban + auto-security-updates"
apt install -y -qq fail2ban unattended-upgrades
systemctl enable --now fail2ban
echo 'Unattended-Upgrade::Automatic-Reboot "false";' \
    > /etc/apt/apt.conf.d/52unattended-upgrades-local
ok "Hardening installed."

# ── Step 6: Clone or update the repo ─────────────────────────
header "6/9  Fetching OASIS source"
if [[ -d "$INSTALL_DIR/.git" ]]; then
    log "Repo already exists at $INSTALL_DIR. Pulling latest."
    git -C "$INSTALL_DIR" fetch origin
    git -C "$INSTALL_DIR" reset --hard origin/main
else
    log "Cloning to $INSTALL_DIR"
    git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
fi
cd "$INSTALL_DIR"
ok "Source ready."

# ── Step 7: Configure .env ───────────────────────────────────
header "7/9  Configuring environment"

ENV_FILE="$INSTALL_DIR/.env"

if [[ -f "$ENV_FILE" ]]; then
    log "Existing .env found. Keeping it. Edit $ENV_FILE manually if you need to change values."
else
    cp .env.example "$ENV_FILE"

    # Detect public IP (used for sslip.io fallback)
    PUBLIC_IP=$(curl -fsSL --max-time 5 https://api.ipify.org 2>/dev/null \
              || curl -fsSL --max-time 5 https://ifconfig.me 2>/dev/null \
              || echo "")
    if [[ -z "$PUBLIC_IP" ]]; then
        warn "Couldn't auto-detect public IP."
        read -rp "Enter your server's public IP: " PUBLIC_IP
    fi
    SSLIP_HOST="oasis.${PUBLIC_IP//./-}.sslip.io"

    # Domain prompt
    echo
    echo "Enter the domain you want OASIS to run on."
    echo "  - Real domain like  ${BOLD}oasis.example.com${NC}  (DNS A-record must point to $PUBLIC_IP)"
    echo "  - Or just press Enter to use the free fallback: ${BOLD}$SSLIP_HOST${NC}"
    read -rp "Domain [$SSLIP_HOST]: " DOMAIN_INPUT
    DOMAIN_INPUT=${DOMAIN_INPUT:-$SSLIP_HOST}

    # OpenAI key (required). Read silently like a password.
    echo
    echo "Enter your OpenAI API key (required, get one at https://platform.openai.com/api-keys)."
    echo "Input is hidden for security."
    while true; do
        read -rsp "OPENAI_API_KEY: " OPENAI_KEY; echo
        if [[ -z "$OPENAI_KEY" ]]; then
            warn "Empty key. Try again."
            continue
        fi
        if [[ "$OPENAI_KEY" != sk-* ]]; then
            warn "Key should start with 'sk-'. Try again."
            continue
        fi
        # Echo a masked confirmation so the user knows it was captured
        MASKED="${OPENAI_KEY:0:7}...${OPENAI_KEY: -4}"
        echo "  Captured: $MASKED"
        break
    done

    # Admin password
    echo
    echo "Choose an admin password for the OASIS dashboard (or press Enter to auto-generate)."
    read -rsp "AUTH_PASSWORD: " ADMIN_PASS; echo
    if [[ -z "$ADMIN_PASS" ]]; then
        ADMIN_PASS=$(openssl rand -hex 16)
        log "Generated admin password: $ADMIN_PASS"
        warn "Save this password now. You'll need it to log in."
    fi

    # Auto-generate secrets
    SECRET_KEY=$(openssl rand -hex 32)
    POSTGRES_PASSWORD=$(openssl rand -hex 24)

    # Patch .env in-place (sed expressions ordered to avoid partial-match conflicts)
    sed -i \
        -e "s|^APP_ENV=.*|APP_ENV=production|" \
        -e "s|^DEBUG=.*|DEBUG=false|" \
        -e "s|^SECRET_KEY=.*|SECRET_KEY=$SECRET_KEY|" \
        -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$POSTGRES_PASSWORD|" \
        -e "s|^OPENAI_API_KEY=.*|OPENAI_API_KEY=$OPENAI_KEY|" \
        -e "s|^DOMAIN=.*|DOMAIN=$DOMAIN_INPUT|" \
        -e "s|^AUTH_ENABLED=.*|AUTH_ENABLED=true|" \
        -e "s|^AUTH_USERNAME=.*|AUTH_USERNAME=admin|" \
        -e "s|^AUTH_PASSWORD=.*|AUTH_PASSWORD=$ADMIN_PASS|" \
        "$ENV_FILE"

    chmod 600 "$ENV_FILE"
    ok "Created $ENV_FILE (mode 600)."
fi

# Read the final DOMAIN value back out (whether we just wrote it or it pre-existed)
DOMAIN_FINAL=$(grep -E '^DOMAIN=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"')
if [[ -z "$DOMAIN_FINAL" || "$DOMAIN_FINAL" == "localhost" ]]; then
    warn "DOMAIN in .env is empty or 'localhost'."
    warn "Caddy will not auto-issue an SSL cert. Edit .env and set DOMAIN to a real domain."
fi

# ── Step 8: Configure Caddy for the domain ───────────────────
header "8/9  Configuring Caddy for $DOMAIN_FINAL"
CADDYFILE="$INSTALL_DIR/docker/Caddyfile"

if [[ -n "$DOMAIN_FINAL" && "$DOMAIN_FINAL" != "localhost" ]]; then
    # Replace the leading ":80" or any existing site address with the chosen domain.
    # The Caddyfile on main starts with `:80 {`. For idempotency, also handle the
    # case where the file was already edited.
    sed -i -E "0,/^[[:space:]]*[^[:space:]{]+[[:space:]]*\{[[:space:]]*$/s//$DOMAIN_FINAL {/" "$CADDYFILE"
    ok "Caddyfile set to listen on $DOMAIN_FINAL (auto-SSL via Let's Encrypt)."
else
    log "Leaving Caddyfile listening on :80 (no domain)."
fi

# ── Step 9: Build + start containers ─────────────────────────
header "9/9  Building and starting containers (this takes ~5 min)"

cd "$INSTALL_DIR"
docker compose pull --quiet 2>/dev/null || true
docker compose build
docker compose up -d

echo
log "Waiting for services to become healthy…"
sleep 5
docker compose ps

echo
ok "═══════════════════════════════════════════════════════════"
ok "  OASIS is starting up."
ok "═══════════════════════════════════════════════════════════"
echo
if [[ -n "$DOMAIN_FINAL" && "$DOMAIN_FINAL" != "localhost" ]]; then
    echo "  Open in your browser:  ${BOLD}https://$DOMAIN_FINAL${NC}"
    echo
    echo "  (First load may take 30-60s while Caddy provisions a Let's Encrypt"
    echo "  certificate. If you see a TLS error, wait a minute and retry.)"
else
    echo "  Open in your browser:  ${BOLD}http://<your-server-ip>${NC}"
fi
echo
echo "  Login:    ${BOLD}admin${NC}  / (the AUTH_PASSWORD from .env)"
echo
echo "  ${BOLD}Files & data on the server:${NC}"
echo "    Code & config:   $INSTALL_DIR"
echo "    Env / secrets:   $INSTALL_DIR/.env  (mode 600, owner-only)"
echo "    Postgres data:   docker volume 'oasis_pgdata' (persists across restarts/updates)"
echo "    Redis data:      docker volume 'oasis_redisdata'"
echo
echo "  ${BOLD}View / edit secrets:${NC}"
echo "    cat   $INSTALL_DIR/.env       # show all env vars"
echo "    nano  $INSTALL_DIR/.env       # edit"
echo "    cd $INSTALL_DIR && docker compose up -d   # apply changes"
echo
echo "  ${BOLD}Useful commands:${NC}"
echo "    cd $INSTALL_DIR"
echo "    docker compose logs -f          # tail all logs"
echo "    docker compose logs -f backend  # one service"
echo "    docker compose ps               # status"
echo "    docker compose restart backend  # restart one service"
echo
echo "  ${BOLD}Update to latest version:${NC}"
echo "    bash $INSTALL_DIR/scripts/update.sh"
echo
