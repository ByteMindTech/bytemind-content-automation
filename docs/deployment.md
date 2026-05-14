# Deployment Guide

## Prerequisites

- OVH VPS with Ubuntu 22.04+ (min 2GB RAM)
- Domain pointing to VPS IP: `api.bytemind.fr`
- GitHub account with access to the repo

## 1. VPS Initial Setup

```bash
# SSH into your VPS
ssh root@your-vps-ip

# Run the hardening script
curl -sSL https://raw.githubusercontent.com/ByteMindTech/bytemind-content-automation/main/scripts/vps-setup.sh | sudo bash
```

This installs Docker, configures UFW, sets up fail2ban, and creates the `bytemind` user.

## 2. Deploy the Application

```bash
# Switch to bytemind user
su - bytemind
cd /opt/bytemind

# Clone the repo
git clone https://github.com/ByteMindTech/bytemind-content-automation.git app
cd app

# Create .env from example
cp .env.example .env
# Edit with your real values:
nano .env
```

### Required .env values:

```env
APP_ENV=production
JWT_SECRET_KEY=<openssl rand -hex 32>
ACTIONS_API_KEY=<openssl rand -hex 32>
DATABASE_URL=postgresql+asyncpg://bytemind:<password>@postgres:5432/bytemind_content
POSTGRES_PASSWORD=<strong password>
GEMINI_API_KEY=<your key>
OPENAI_API_KEY=<your key>
SMTP_USER=contact@bytemind.fr
SMTP_PASSWORD=<OVH email password>
APPROVAL_EMAIL=your-email@bytemind.fr
```

## 3. Start Services

```bash
# Build and start everything
docker compose up -d

# Run database migrations
docker compose exec app alembic upgrade head

# Verify
docker compose ps
curl -s https://api.bytemind.fr/health | jq
```

## 4. DNS Configuration

Add an A record in your OVH DNS zone:
```
api.bytemind.fr.  IN  A  <your-vps-ip>
```

Caddy will automatically obtain a Let's Encrypt certificate.

## 5. GitHub Secrets

Add these secrets to the `bytemind-content-automation` repo:
- `AUTOMATION_API_URL`: `https://api.bytemind.fr`
- `AUTOMATION_API_KEY`: Same as `ACTIONS_API_KEY` in .env

Add to ByteMindTech repo:
- `AUTOMATION_DISPATCH_TOKEN`: GitHub PAT with `repo` scope

## 6. Daily Backups

Run manual backup:
```bash
docker compose --profile backup run --rm backup
```

Set up cron for daily backups:
```bash
crontab -e
# Add:
0 3 * * * cd /opt/bytemind/app && docker compose --profile backup run --rm backup
```

## 7. Monitoring

Check application metrics:
```bash
curl -s https://api.bytemind.fr/metrics | jq
```

View logs:
```bash
docker compose logs -f app --tail 100
```

## Updating

```bash
cd /opt/bytemind/app
git pull
docker compose build app
docker compose up -d app
docker compose exec app alembic upgrade head
```
