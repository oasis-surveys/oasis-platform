# Deploying OASIS to a Hetzner Cloud VM

This is the deployment guide for putting OASIS on the public internet so participants can take interviews. The total cost is around 5 EUR per month for the server, plus an optional 10 EUR per year for a domain. Time from clicking "create server" to a working HTTPS dashboard is about 15 minutes if you go slowly and read each step.

This guide is deliberately step-by-step. Every Hetzner click is spelled out. If you follow each step in order, you will not get stuck. If you do get stuck, the [Common issues](#common-issues) section at the bottom covers everything that has actually gone wrong for previous users.

If you are part of a research group and you would rather have someone walk you through the whole thing, OASIS runs a [pilot program](mailto:max.lang@stx.ox.ac.uk?subject=OASIS%20pilot%20program). Email me and I will help you get set up.

If you are a sysadmin who wants the technical details (what the firewall actually does, how fail2ban is configured, how Caddy gets the TLS cert, the Docker compose layout, etc.), jump to the [Expert section](#expert-section-what-the-install-actually-does) at the bottom. Otherwise just read top to bottom.

---

## Contents

1. [What you need before you start](#what-you-need-before-you-start)
2. [Step 1: Sign up for Hetzner Cloud](#step-1-sign-up-for-hetzner-cloud)
3. [Step 2: Add your SSH key to Hetzner](#step-2-add-your-ssh-key-to-hetzner)
4. [Step 3: Create the server](#step-3-create-the-server)
5. [Step 4: Add a Cloud Firewall (recommended)](#step-4-add-a-cloud-firewall-recommended)
6. [Step 5: Get a domain (optional)](#step-5-get-a-domain-optional)
7. [Step 6: SSH into your server](#step-6-ssh-into-your-server)
8. [Step 7: Run the installer](#step-7-run-the-installer)
9. [Step 8: Open OASIS in your browser](#step-8-open-oasis-in-your-browser)
10. [Adding more API keys later](#adding-more-api-keys-later)
11. [Updating OASIS](#updating-oasis)
12. [Restarting services](#restarting-services)
13. [Checking logs](#checking-logs)
14. [Backups](#backups)
15. [Common issues](#common-issues)
16. [Expert section: what the install actually does](#expert-section-what-the-install-actually-does)

---

## What you need before you start

1. **A credit card.** Hetzner needs one to verify your account. You will be charged about 5 EUR per month.
2. **An LLM API key.** This guide uses OpenAI because it is the simplest path (one key gets you text chat, voice, and voice-to-voice out of the box). But OASIS is provider-agnostic. You can use Scaleway, Anthropic Claude, Google Gemini, Azure OpenAI, GCP Vertex, OpenRouter, or any OpenAI-compatible endpoint instead, and you can mix providers per agent. See the [FAQ](../FAQ.md#which-ai-providers-does-oasis-support-can-i-use-openrouter) for the full list. For the rest of this guide we assume OpenAI for simplicity.

   Get an OpenAI API key at [platform.openai.com/api-keys](https://platform.openai.com/api-keys). It must start with `sk-`. Your account needs at least 5 USD of credit, otherwise interviews will fail with `insufficient_quota`.

3. **An SSH key on your laptop.** This is how you log in to the server. If you do not already have one, generate it now from your laptop's terminal:
   ```bash
   ssh-keygen -t ed25519 -C "your-email@example.com" -f ~/.ssh/hetzner
   ```
   Press Enter twice when it asks for a passphrase (no passphrase is fine for a demo, set one in production). This writes two files. The private one (`~/.ssh/hetzner`) stays on your laptop. The public one (`~/.ssh/hetzner.pub`) gets pasted into Hetzner in step 2.

   <details>
   <summary>Why a separate SSH key just for Hetzner?</summary>

   You can reuse an existing key if you have one. A dedicated key per service makes it easier to revoke access later (you delete the key on Hetzner without touching the rest of your setup) and makes it obvious in your `.ssh` folder which key goes where. SSH keys are free, having a few of them costs nothing.

   </details>

4. **(Optional) A domain name.** OASIS works fine without one. The installer falls back to a free `*.sslip.io` hostname so you still get real HTTPS. See [Step 5](#step-5-get-a-domain-optional) for details.

---

## Step 1: Sign up for Hetzner Cloud

1. Go to [hetzner.com/cloud](https://www.hetzner.com/cloud).
2. Click **Sign up** (top right).
3. Enter your email and password, confirm the email link, fill in your address. Hetzner will ask for a phone number and may ask for ID verification. This is normal, they do it for fraud prevention.
4. Once your account is active, go to [console.hetzner.cloud](https://console.hetzner.cloud/). You will land on a screen that says "You don't have any projects yet."
5. Click the **+ New Project** button. Name it `oasis` (or anything you like). Click **Create Project**.
6. Click on the project tile to open it. You should now be inside the project, with a left sidebar showing **Servers, Volumes, Networks, Load Balancers, Firewalls, ...**.

<details>
<summary>What is a Hetzner project?</summary>

A project is just a folder for grouping resources (servers, firewalls, snapshots, etc.). Billing is per-account, not per-project, so you can use one project for everything or split them per client / experiment. We use one project here for clarity.

</details>

---

## Step 2: Add your SSH key to Hetzner

1. In the left sidebar of your project, click **Security**.
2. Click the **SSH Keys** tab at the top.
3. Click **+ Add SSH Key**.
4. From your laptop's terminal, print the public key:
   ```bash
   cat ~/.ssh/hetzner.pub
   ```
   It will look like `ssh-ed25519 AAAAC3Nz...xyz your-email@example.com`. Copy the entire line.
5. Paste the key into the Hetzner **SSH key** text area.
6. Give it a name like `Hetzner` so you recognise it later.
7. Click **Add SSH Key**. You should see it listed.

<details>
<summary>Why upload the SSH key now instead of using a password?</summary>

Hetzner offers password login as a fallback, but it is much weaker (passwords are guessable, keys are not). When you upload an SSH key during server creation, Hetzner disables password login by default and only allows your key to log in as `root`. This is the right setup. The installer also enables `fail2ban` later, which automatically bans IPs that try to brute-force SSH.

</details>

---

## Step 3: Create the server

1. In the left sidebar, click **Servers**.
2. Click **+ Add Server**.
3. Fill in the form like this:

   | Field | What to pick | Why |
   |---|---|---|
   | **Location** | Falkenstein, Helsinki, or Nuremberg (any EU region) | Keeps participant data in the EU. Pick the one closest to your participants. |
   | **Image** | Ubuntu 24.04 | The installer is tested on Ubuntu 24.04. Other distros may work but are not supported. |
   | **Type** | **CX22** (Shared vCPU > Intel) | 4 GB RAM, 2 vCPU, 40 GB SSD, around 4.51 EUR per month. This is the minimum that works. |
   | **Networking** | Public IPv4 + IPv6 (default) | Leave both ticked. You need IPv4 for participants to reach you. |
   | **SSH key** | Tick the `Hetzner` key from step 2 | This is how the installer-and-you log into the server. |
   | **Volume** | Skip / None | The 40 GB disk is plenty for the demo. You can attach more disk later if you fill it up. |
   | **Firewall** | Skip / None for now | We add the firewall in step 4. |
   | **Backups** | Optional, +20% cost | Adds Hetzner-managed weekly snapshots. Recommended once you have real participant data. |
   | **Placement group** | None | Only relevant for multi-server setups. |
   | **Labels** | None | For advanced filtering. Skip. |
   | **Cloud config** | None | Skip. |
   | **Name** | `oasis-prod` (or anything) | Just a label, change it any time. |

   Do not pick **CX11** or **CAX11** (2 GB RAM). The frontend Docker build needs around 1.5 GB and will run out of memory before it finishes. CX22 is the smallest size that works.

4. Click **Create & Buy Now** at the bottom. Hetzner provisions the server in about 15 seconds.

5. You will land on the server's overview page. **Find the IPv4 address** at the top (it looks like `128.140.86.182`). Write it down or copy it. You will need it for SSH.

<details>
<summary>Why CX22 specifically?</summary>

The frontend image is built inside the container with `npm run build`, which spins up Vite + Rollup and peaks at around 1.5 GB of memory during the bundle step. CX11 (2 GB total) does not have enough headroom because the OS, Docker daemon, and the postgres + redis containers also need RAM. CX22 (4 GB) works comfortably. CPX11 (also 2 GB) has the same problem. If you already have a 2 GB instance and do not want to rescale, you can skip the in-container build and pre-build the image elsewhere, but that is more hassle than upgrading.

</details>

<details>
<summary>Why Ubuntu 24.04 and not Debian / Alpine / etc.?</summary>

The installer uses `apt`, `ufw`, `unattended-upgrades`, `fail2ban`, and `needrestart`. These all exist on Debian too, but the installer is only tested on Ubuntu 24.04 LTS. Patches to support Debian 12 are welcome.

</details>

---

## Step 4: Add a Cloud Firewall (recommended)

This is on top of the server-level UFW firewall the installer sets up later, so you have two layers of protection. Belt and braces.

1. In the left sidebar, click **Firewalls**.
2. Click **+ Create Firewall**.
3. Name it `oasis-firewall`.
4. Under **Inbound rules**, you will see one default rule for SSH. Add two more by clicking **+ Add rule** and filling them in:

   | Protocol | Port | Source IPs | Description |
   |---|---|---|---|
   | TCP | 22 | `0.0.0.0/0`, `::/0` (default) | SSH. Restrict to your home IP if you want. |
   | TCP | 80 | `0.0.0.0/0`, `::/0` | HTTP. Caddy uses this for Let's Encrypt certificate validation. |
   | TCP | 443 | `0.0.0.0/0`, `::/0` | HTTPS. This is how participants reach OASIS. |

   For each rule, paste `0.0.0.0/0` into the IPv4 source field and `::/0` into the IPv6 source field. This means "allow from anywhere".

5. Leave **Outbound rules** as default (allow everything). The backend needs to reach the AI provider APIs, your domain registrar, GitHub, Docker Hub, etc.

6. Under **Apply to**, select **Servers** and tick your `oasis-prod` server.

7. Click **Create Firewall**.

<details>
<summary>Why two firewalls (Cloud Firewall and UFW)?</summary>

The Cloud Firewall runs at Hetzner's network edge, before traffic ever touches your VM. UFW runs on the VM itself. Either one alone would be enough, but having both means a misconfiguration in one is caught by the other. The Cloud Firewall is also the only thing you can use to restrict traffic before the OS even boots (useful if you ever rebuild the server image).

</details>

<details>
<summary>Why do we need port 80 if everything runs over HTTPS?</summary>

Caddy (the reverse proxy in the OASIS stack) uses port 80 for the Let's Encrypt HTTP-01 challenge. Let's Encrypt issues SSL certificates for free, but to prove you own the domain, it makes a request to `http://yourdomain.com/.well-known/acme-challenge/<token>`. If port 80 is closed, Caddy cannot get a cert and HTTPS will not work. Caddy automatically redirects every other request from HTTP to HTTPS, so port 80 is only used for cert renewal traffic.

</details>

---

## Step 5: Get a domain (optional)

You can skip this entire step. If you do, the installer detects that and uses a free hostname like `oasis.128-140-86-182.sslip.io`. It works, you get real Let's Encrypt SSL, and participants can use the link. The only downside is that the URL is ugly.

<details>
<summary>What is sslip.io? Is it safe?</summary>

[sslip.io](https://sslip.io) is a free public DNS service that resolves any hostname containing an IP address back to that IP address. So `oasis.128-140-86-182.sslip.io` resolves to `128.140.86.182`. It is a long-running, well-known service used in the cloud-native ecosystem (Google's [Knative](https://knative.dev/docs/serving/services/setting-up-custom-domains/) docs reference it as a default domain for local testing, and Kubernetes tutorials use it constantly). It is open-source ([github.com/cunnie/sslip.io](https://github.com/cunnie/sslip.io)), runs on community-funded infrastructure, and has been online for years.

It is "just a DNS resolver", it does not see your traffic. Once DNS resolves, your browser talks directly to your server. Caddy still gets a real Let's Encrypt cert, so HTTPS is genuinely secure. The only thing you lose vs a real domain is a memorable URL.

If you prefer not to depend on a third-party DNS service, just buy a real domain (next part of this step) and the installer never touches sslip.io.

</details>

If you want a real domain (around 10 EUR per year):

1. Buy one anywhere. Some good options:
   - [Hetzner Online](https://konsoleh.your-server.de) (EU-based, dated UI but works)
   - [Cloudflare Registrar](https://dash.cloudflare.com) (at-cost pricing, free DNS)
   - [Namecheap](https://namecheap.com) (friendly UI, US-based)
   - Any other registrar works.
2. Once you own the domain, find the **DNS settings** page on your registrar.
3. Add an **A record**:

   | Type | Name | Value | TTL | Proxy (Cloudflare only) |
   |---|---|---|---|---|
   | A | `oasis` | `<your-server-ip>` (the IPv4 from step 3) | Auto / 300 | OFF (DNS only, grey cloud) |

   The `Name` field is the subdomain part. If you want OASIS at `oasis.yourdomain.com`, type `oasis`. If you want it at the root (`yourdomain.com`), type `@`.

4. **Cloudflare users only**: the proxy toggle MUST be OFF (grey cloud, not orange). If it is ON, Cloudflare intercepts the Let's Encrypt validation request and Caddy cannot get an SSL certificate.

5. Wait 1 to 5 minutes for DNS to propagate. Test from your laptop:
   ```bash
   dig +short oasis.yourdomain.com
   ```
   You should see your server IP. If you see nothing, wait another minute and try again.

---

## Step 6: SSH into your server

From your laptop's terminal:

```bash
ssh -i ~/.ssh/hetzner root@<your-server-ip>
```

Replace `<your-server-ip>` with the IPv4 address from step 3. The `-i ~/.ssh/hetzner` flag tells SSH to use the key you generated in the prerequisites.

The first time you connect, SSH asks you to confirm the host fingerprint:

```
The authenticity of host '128.140.86.182' can't be established.
ED25519 key fingerprint is SHA256:abc123...
Are you sure you want to continue connecting (yes/no/[fingerprint])?
```

Type `yes` and press Enter. You should land at a root prompt:

```
root@oasis-prod:~#
```

If it hangs forever or times out, the firewall is the cause. Double-check that the Cloud Firewall in step 4 actually allows port 22 and is attached to the server.

<details>
<summary>Why log in as root? Is that not bad practice?</summary>

For a single-purpose VM where you are the only admin, root over SSH with a key is fine. The installer locks down SSH (key-only login, no passwords) and adds fail2ban (auto-ban brute-force attempts). The deeper concern about "do not log in as root" is mostly about multi-user systems where you do not want one slipped-up command to take everything down. For a fresh VM where you are the only person on it, the convenience trade-off is worth it.

If you really want to harden further, you can create a non-root user, add it to the `sudo` group, copy your authorized_keys into its home folder, and set `PermitRootLogin no` in `/etc/ssh/sshd_config`. The installer does not do this for you because it adds friction without much real-world benefit on a single-tenant box.

</details>

---

## Step 7: Run the installer

At the `root@oasis-prod:~#` prompt, paste this single line and press Enter:

```bash
curl -fsSL https://raw.githubusercontent.com/oasis-surveys/oasis-platform/main/scripts/install.sh | bash
```

> **Heads up about a possible reboot.** Early on (Step 2/9, "Checking for pending kernel reboot") the installer may detect that the system needs to reboot to load a new kernel from the `apt upgrade` step. If it does, it will ask `Reboot now? [Y/n]:`. Press Enter to accept (Y is the default).
>
> When the server reboots, **your SSH connection will drop**. You will see something like `client_loop: send disconnect: Broken pipe` or the terminal will just freeze. **This is normal. Do not panic.** Wait about 30 seconds for the server to come back up, then reconnect and re-run the same install command:
>
> ```bash
> ssh -i ~/.ssh/hetzner root@<your-server-ip>
> curl -fsSL https://raw.githubusercontent.com/oasis-surveys/oasis-platform/main/scripts/install.sh | bash
> ```
>
> The installer is idempotent. It detects that the system update is already done and resumes from where it left off. You will only ever see the reboot prompt once per VM, after that it skips straight to the Docker install.

The script then runs 9 steps and tells you what it is doing as it goes. Steps 1-6 take about 5 minutes and need no input from you (apart from the optional reboot above). Then it asks you 3 questions:

### Question 1: Domain

```
Enter the domain you want OASIS to run on.
  - Real domain like oasis.example.com (DNS A-record must point to <your-ip>)
  - Or just press Enter to use the free fallback: oasis.128-140-86-182.sslip.io
Domain [oasis.128-140-86-182.sslip.io]:
```

If you set up a domain in step 5, type it (for example `oasis.yourdomain.com`) and press Enter. Otherwise just press Enter to use the sslip.io fallback.

### Question 2: OpenAI API key

```
Enter your OpenAI API key (required, get one at https://platform.openai.com/api-keys).
Input is hidden for security.
OPENAI_API_KEY:
```

Paste your `sk-...` key. **The input does not show on screen**. This is intentional, the script reads it like a password so it does not get recorded in your terminal scrollback. Press Enter when you have pasted it. The script confirms with a masked version like:

```
  Captured: sk-proj...xb4A
```

If you see "Empty key, try again" or "Key should start with 'sk-', try again", paste it again carefully (no leading/trailing whitespace).

### Question 3: Admin password

```
Choose an admin password for the OASIS dashboard (or press Enter to auto-generate).
AUTH_PASSWORD:
```

Type a password for the OASIS dashboard (it is also hidden), or just press Enter and the script will auto-generate one. **If you let it auto-generate, copy the password it prints**. You will need it to log in.

After that, the installer:

- Generates a random `SECRET_KEY` and `POSTGRES_PASSWORD` (so each install has unique secrets).
- Writes everything to `/opt/oasis/.env` with mode 600 (only root can read it).
- Patches the Caddyfile to use your domain so HTTPS Just Works on first request.
- Builds the frontend and backend Docker images. This is the slow part, around 5 minutes.
- Starts all 5 containers.

Total runtime is about 8 minutes on a fresh CX22. Most of it is the frontend build. Be patient. When it finishes, you will see a green banner with your URL.

<details>
<summary>What does the installer actually do under the hood?</summary>

Short version: it brings the VM from "fresh Ubuntu" to "production-ready Docker host", clones the repo, generates secrets, and starts the stack. It runs as root, uses official packages, is idempotent (safe to re-run), and does not download anything sketchy. The full breakdown (every package, every config file, every iptables rule) is in the [Expert section](#expert-section-what-the-install-actually-does) at the bottom.

</details>

---

## Step 8: Open OASIS in your browser

When the installer finishes, you will see something like:

```
[ ok ] OASIS is starting up.
  Open in your browser: https://oasis.yourdomain.com
  Login: admin / (the AUTH_PASSWORD from .env)
```

Open the URL in your browser. The first page load can take 30 to 60 seconds because Caddy is provisioning the SSL certificate from Let's Encrypt in the background.

If you see a TLS error ("your connection isn't private", "ERR_CERT_AUTHORITY_INVALID", etc.) on the very first load, wait a minute and reload. If it persists for more than 5 minutes, see [Common issues](#common-issues).

Once the page loads, log in:

- Username: `admin`
- Password: the `AUTH_PASSWORD` from the installer (either the one you typed or the auto-generated one)

You are in. Click **+ New Study**, give it a name, then **From Template** and pick one of the research templates. Open the agent's share link in a new tab to take an interview yourself, or send it to a participant.

---

## Adding more API keys later

All API keys live in `/opt/oasis/.env`. To add Deepgram, ElevenLabs, Cartesia, Anthropic, Google, Scaleway, OpenRouter, etc., edit that file:

```bash
nano /opt/oasis/.env
```

Press `Ctrl+O` then Enter to save, then `Ctrl+X` to exit. The full list of supported variables is in `.env.example` in the same directory (`cat /opt/oasis/.env.example`).

Apply the changes:

```bash
cd /opt/oasis
docker compose up -d
```

This restarts only the containers whose environment changed. Postgres and Redis data is preserved.

You can also set most keys directly through the dashboard at **Settings**. Keys set in the dashboard live in Redis and override the `.env` value at runtime.

---

## Updating OASIS

```bash
bash /opt/oasis/scripts/update.sh
```

That pulls the latest code from `main`, rebuilds the backend and frontend images, restarts the stack, and prunes old Docker build cache. Postgres and Redis data is preserved.

For a safer update that dumps the database first:

```bash
bash /opt/oasis/scripts/update.sh --backup
```

The dump is written to `/opt/oasis/backups/oasis-<timestamp>.sql.gz`.

To restore from a backup later:

```bash
gunzip -c /opt/oasis/backups/oasis-<timestamp>.sql.gz | \
  docker compose -f /opt/oasis/docker-compose.yml exec -T postgres psql -U oasis -d oasis
```

If you only changed a config file and do not need a rebuild:

```bash
bash /opt/oasis/scripts/update.sh --no-build
```

---

## Restarting services

The 5 services are `caddy`, `frontend`, `backend`, `postgres`, `redis`. To restart:

```bash
cd /opt/oasis
docker compose restart backend       # restart backend only
docker compose restart frontend      # restart frontend only
docker compose restart caddy         # restart caddy (rarely needed)
docker compose restart               # restart everything
```

To rebuild a single service after editing its source:

```bash
cd /opt/oasis
docker compose up -d --build backend
```

To stop everything:

```bash
cd /opt/oasis
docker compose down
```

To start everything again:

```bash
cd /opt/oasis
docker compose up -d
```

---

## Checking logs

```bash
cd /opt/oasis
docker compose logs -f                 # tail logs from all services, live
docker compose logs -f backend         # backend only
docker compose logs -f frontend        # frontend only
docker compose logs -f caddy           # caddy (useful for SSL cert issues)
docker compose logs --tail=200 backend # last 200 lines, no live tail
```

`Ctrl+C` stops tailing. Logs persist until the container is removed.

To see the status of all containers:

```bash
docker compose ps
```

Healthy containers show `Up X minutes (healthy)`. If a container is restart-looping, you will see `Restarting (1)` and need to check its logs.

---

## Backups

The simplest option is **Hetzner snapshots**: in the Cloud Console go to **Servers > your server > Snapshots > Create Snapshot**. That snapshots the entire VM disk. Cost is small (around 1 cent per GB per month). You can restore the entire VM from a snapshot in about 5 minutes.

For database-only dumps, use the update script's backup flag (described above) or run `pg_dump` manually:

```bash
docker compose -f /opt/oasis/docker-compose.yml exec -T postgres \
  pg_dump -U oasis oasis | gzip > /opt/oasis/backups/manual-$(date +%F).sql.gz
```

For automatic daily backups, add a cron job:

```bash
crontab -e
# Add this line (runs at 3am every day):
0 3 * * * cd /opt/oasis && docker compose exec -T postgres pg_dump -U oasis oasis | gzip > /opt/oasis/backups/oasis-$(date +\%F).sql.gz
```

---

## Common issues

### My SSH connection died mid-install ("Broken pipe", terminal froze)

The installer rebooted the server because there was a pending kernel update. SSH always drops on reboot. Wait about 30 seconds for the server to come back, then reconnect and re-run the same install command:

```bash
ssh -i ~/.ssh/hetzner root@<your-server-ip>
curl -fsSL https://raw.githubusercontent.com/oasis-surveys/oasis-platform/main/scripts/install.sh | bash
```

The script is idempotent. It detects what was already done and resumes from where it left off. The reboot only happens once per VM.

If 30 seconds is not enough, give it 2-3 minutes. Hetzner sometimes takes a moment to come back up.

### The browser shows "your connection isn't private" or a TLS error

Caddy is still provisioning the Let's Encrypt certificate. Wait 60 seconds and reload. If it persists for more than 5 minutes, check Caddy logs:

```bash
docker compose logs -f caddy
```

The most common cause is DNS not pointing at the server yet. Run `dig +short yourdomain.com` from your laptop and confirm it returns your server IP. If it returns nothing or the wrong IP, fix your DNS A record and wait for propagation.

The second most common cause is Cloudflare proxy being ON (orange cloud). Switch it to DNS only (grey cloud).

### "Connection timed out" when opening the dashboard

Something is blocking ports 80 or 443.

1. Check the Hetzner Cloud Firewall is attached to the server and has 80 and 443 open.
2. SSH in and check UFW:
   ```bash
   ufw status
   ```
   You should see `80/tcp ALLOW` and `443/tcp ALLOW`. If not, run `ufw allow 80/tcp && ufw allow 443/tcp`.
3. Check Caddy is actually running: `docker compose ps`. If it crashed, `docker compose logs caddy`.

### "Sorry, I encountered an issue. Please try again." in the chat

Almost always one of:

- Wrong OpenAI API key. Open `/opt/oasis/.env`, check `OPENAI_API_KEY` starts with `sk-` and has no trailing whitespace. After fixing, run `cd /opt/oasis && docker compose up -d --force-recreate backend` to make the backend pick up the new key.
- Out of OpenAI credits. Check your usage at [platform.openai.com/usage](https://platform.openai.com/usage).
- Invalid model ID set on the agent. The most common mistake is typing a model that does not exist. Open the agent in the dashboard and pick a model from the dropdown rather than typing it. The dropdown is verified against the provider's docs.
- Check `docker compose logs -f backend` for the actual error. It will tell you which provider rejected the request.

### `docker compose build` hangs or fails with "Killed"

The VM ran out of memory. Make sure you are on CX22 (4 GB) or larger. If you accidentally created a CX11 (2 GB), upgrade in the Hetzner Console (Servers > your server > Rescaling > pick CX22 > Rescale & Power on).

### "FATAL: password authentication failed" in postgres logs

You changed `POSTGRES_PASSWORD` in `.env` after the database volume was already created. Postgres only reads `POSTGRES_PASSWORD` on first init. Two options:

- Reset the volume (this wipes all your data, only do this if you have nothing in the database yet):
  ```bash
  cd /opt/oasis
  docker compose down -v
  docker compose up -d
  ```
- Or revert the password in `.env` to the original value and restart: `docker compose up -d`.

### Backend container exits with "alembic upgrade head" failure

Migrations failed. Usually means Postgres is not ready yet (transient, fix with a restart) or you have a schema mismatch (someone ran SQL by hand, or you switched between branches with conflicting migrations).

```bash
cd /opt/oasis
docker compose logs postgres
docker compose logs backend
docker compose exec backend env | grep -E 'POSTGRES|DATABASE_URL'
```

If it is transient: `docker compose restart backend`. If it is a schema mismatch: restore from a backup.

### "no space left on device"

Docker images and build cache eat disk. Check usage:

```bash
df -h
docker system df
```

Clean up unused images and build cache:

```bash
docker system prune -af --filter "until=168h"
```

That removes everything older than 7 days that is not currently in use. Safe.

If you are still tight on disk, attach a Hetzner Volume (Cloud Console > Volumes > Add Volume) and mount it. Or rescale the VM to a type with a larger disk.

### The installer hangs on "apt install"

A previous `apt upgrade` left a pending kernel update and `needrestart` is blocking the install.

```bash
killall needrestart || true
killall apt apt-get || true
rm -f /var/lib/apt/lists/lock /var/lib/dpkg/lock /var/lib/dpkg/lock-frontend
dpkg --configure -a
reboot
```

After the reboot, SSH back in and re-run the installer. It is idempotent and resumes from where it left off.

### I want to start completely from scratch

Nuke the install and re-run:

```bash
cd /opt/oasis
docker compose down -v   # -v deletes the data volumes
cd /
rm -rf /opt/oasis
curl -fsSL https://raw.githubusercontent.com/oasis-surveys/oasis-platform/main/scripts/install.sh | bash
```

This deletes all interview transcripts, agents, and uploaded knowledge base files. Make sure that is what you want.

---

## Expert section: what the install actually does

This section is for people who want to understand the security posture, the network plumbing, and the file system layout before pointing real participants at the box. None of it is required reading to operate OASIS.

### Source of truth

The installer is at [`scripts/install.sh`](../scripts/install.sh), about 280 lines of plain bash with `set -euo pipefail`. The updater is at [`scripts/update.sh`](../scripts/update.sh). Read either before running it. There is no compiled binary, no curl-pipe-to-shell magic that you cannot inspect. Both scripts use only `apt`, `curl`, `git`, `openssl`, `sed`, `docker`, and `ufw`.

### The 9 steps in install.sh

1. **Sanity checks**: must be root, detect Ubuntu version, set `DEBIAN_FRONTEND=noninteractive`, `NEEDRESTART_MODE=a`, `NEEDRESTART_SUSPEND=1` so apt does not prompt mid-install.
2. **System update**: `apt update && apt upgrade -y`, then install `curl git nano openssl ca-certificates gnupg lsb-release jq`.
3. **Reboot if a new kernel was installed** (checks `/var/run/reboot-required`). The script then exits and asks you to re-run after reconnecting. The next run picks up where it left off.
4. **Docker install** via the official `https://get.docker.com` script (the one Docker Inc. publishes). Then `systemctl enable --now docker`.
5. **UFW firewall** (described below).
6. **Hardening packages** `fail2ban` and `unattended-upgrades` (described below).
7. **Clone the repo** to `/opt/oasis` (or `git fetch && git reset --hard origin/main` if it already exists).
8. **Configure `.env`**: copies `.env.example` to `.env`, prompts for domain / OpenAI key / admin password, generates random `SECRET_KEY` and `POSTGRES_PASSWORD` via `openssl rand -hex`, `chmod 600 .env`.
9. **Patch Caddyfile** with the chosen domain, then `docker compose pull && docker compose build && docker compose up -d`.

### UFW firewall configuration

The installer runs:

```bash
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp  comment 'SSH'
ufw allow 80/tcp  comment 'HTTP'
ufw allow 443/tcp comment 'HTTPS'
ufw --force enable
```

Result: every inbound port except 22, 80, 443 is dropped. Outbound is unrestricted (the backend needs to reach AI provider APIs, GitHub, Docker Hub, etc.). Docker's `iptables` rules sit underneath UFW, so containers on the internal `oasis_net` Docker network can talk to each other but cannot be reached from outside without an explicit `ports:` mapping in `docker-compose.yml`. Only Caddy publishes ports to the host (80 and 443).

To inspect:

```bash
ufw status verbose
iptables -L -n
```

### fail2ban: what it actually does

`fail2ban` watches `/var/log/auth.log` for SSH brute-force patterns. The installer enables the default config, which means:

| Setting | Default value | What it does |
|---|---|---|
| `bantime` | 10 minutes | How long a banned IP is blocked. |
| `findtime` | 10 minutes | The window in which failures are counted. |
| `maxretry` | 5 | Failed logins within `findtime` before the IP is banned. |
| `backend` | `systemd` | Where to read auth events from (`journald` on modern Ubuntu). |
| Action | `iptables-multiport` | Inserts a DROP rule for the offending IP. |

Translation: an attacker who tries to brute-force your SSH gets 5 attempts, then their IP is dropped at the kernel level for 10 minutes. With password auth disabled (key-only login), brute-force is already nearly impossible, but fail2ban is cheap insurance.

To inspect fail2ban activity:

```bash
fail2ban-client status            # which jails are active
fail2ban-client status sshd       # currently banned IPs for the SSH jail
journalctl -u fail2ban -n 50      # recent fail2ban log lines
```

To unban an IP (e.g., your own if you locked yourself out):

```bash
fail2ban-client set sshd unbanip <ip>
```

### unattended-upgrades

This applies security patches automatically. The installer enables it and writes one extra config file:

```
/etc/apt/apt.conf.d/52unattended-upgrades-local
  Unattended-Upgrade::Automatic-Reboot "false";
```

This means: install security patches automatically, but never reboot the VM unsupervised. Reboots can interrupt active interviews, so you decide when to reboot. To check what was applied:

```bash
cat /var/log/unattended-upgrades/unattended-upgrades.log
```

To reboot when convenient (after a kernel update):

```bash
[ -f /var/run/reboot-required ] && reboot
```

### Caddy and Let's Encrypt

Caddy is configured via [`docker/Caddyfile`](../docker/Caddyfile). The installer patches the first line to use your domain. On first request to your domain, Caddy:

1. Solves the Let's Encrypt HTTP-01 challenge on port 80.
2. Receives a 90-day SSL certificate and stores it in the `caddy_data` Docker volume.
3. Serves all subsequent requests over HTTPS, redirecting HTTP to HTTPS.
4. Auto-renews the cert in the background (~30 days before expiry). No cron, no manual action.

If you ever change your domain, edit `docker/Caddyfile`, change the first line, then `docker compose restart caddy`. Caddy will get a new cert on first request to the new domain.

### Docker compose architecture

The 5 services on a single internal network (`oasis_net`):

```
                 host: ports 80, 443 published
                            │
                       ┌────▼────┐
                       │  caddy  │  (reverse proxy, TLS termination)
                       └────┬────┘
                ┌───────────┼───────────┐
                │                       │
          ┌─────▼────┐           ┌──────▼───┐
          │ frontend │           │  backend │
          │  (nginx) │           │ (FastAPI)│
          └──────────┘           └────┬─────┘
                                      │
                          ┌───────────┼───────────┐
                          │                       │
                    ┌─────▼─────┐          ┌──────▼─────┐
                    │ postgres  │          │   redis    │
                    │ (pgvector)│          │            │
                    └───────────┘          └────────────┘
```

Only `caddy` is reachable from the public internet. The other 4 services have no `ports:` mapping in `docker-compose.yml`, only `expose:`, so they are reachable only from within `oasis_net`. Postgres and Redis are not exposed to the internet at all.

### File system layout

```
/opt/oasis/                     # repo clone
├── .env                        # secrets (mode 600, root only)
├── .env.example                # documented template
├── docker-compose.yml          # service definitions
├── docker/
│   └── Caddyfile               # patched at install time
├── backend/                    # FastAPI source (built into the backend image)
├── frontend/                   # React source (built into the frontend image)
├── scripts/
│   ├── install.sh              # this installer
│   └── update.sh               # update script
└── backups/                    # pg_dump output (created on demand)
```

Docker volumes (data that survives container rebuilds):

| Volume | Mounted at | Contents |
|---|---|---|
| `oasis_pgdata` | `/var/lib/postgresql/data` in postgres container | All app data: studies, agents, transcripts, embeddings |
| `oasis_redisdata` | `/data` in redis container | Sessions, dashboard-set API keys |
| `oasis_caddy_data` | `/data` in caddy container | Let's Encrypt certs and ACME state |
| `oasis_caddy_config` | `/config` in caddy container | Caddy's auto-generated runtime config |

Volumes are project-prefixed (`oasis_`) by Docker Compose because the install dir is `/opt/oasis`. You can list them with `docker volume ls`.

### How to fully wipe the install

```bash
cd /opt/oasis
docker compose down -v          # stops containers AND deletes volumes (data is gone)
cd /
rm -rf /opt/oasis               # removes code and .env
ufw disable                     # if you want UFW gone too
apt remove --purge fail2ban unattended-upgrades docker-ce docker-ce-cli containerd.io
```

### What the installer does NOT do

- It does not create non-root users.
- It does not change `sshd_config` (key-only login is already the default when you upload a key during server creation).
- It does not set up off-site backups. Use Hetzner snapshots or set up `restic`/`borg` yourself.
- It does not configure log shipping (Loki, Datadog, etc.). Logs live in Docker's local JSON driver.
- It does not enable HSTS preload, CSP headers, or other web hardening beyond what Caddy does by default. Add those in the Caddyfile if you need them.
- It does not configure outbound proxy / egress filtering. The backend can reach any IP on the internet.

If you need any of the above for compliance reasons, do them after the basic install works.

---

## Getting help

- [Open a GitHub issue](https://github.com/oasis-surveys/oasis-platform/issues) for bugs.
- Check the [project FAQ](../FAQ.md) for common questions about providers, models, EU data residency, RAG, and so on.
- For research groups that want hands-on help: [pilot program](mailto:max.lang@stx.ox.ac.uk?subject=OASIS%20pilot%20program).
