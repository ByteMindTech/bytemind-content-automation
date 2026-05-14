#!/usr/bin/env bash

################################################################################
# VPS Hardening Setup Script for OVH VPS (Ubuntu 22.04+)
# 
# This script sets up a secure baseline for the ByteMind content automation
# application. It installs and configures security tools, firewall, Docker,
# and creates necessary users and directories.
#
# Usage: sudo bash vps-setup.sh
# 
# WARNING: Run this script as root (via sudo). Do not run as a regular user.
################################################################################

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $*"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $*"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*" >&2
}

# Check if running as root
if [[ $EUID -ne 0 ]]; then
    log_error "This script must be run as root (use: sudo bash vps-setup.sh)"
    exit 1
fi

log_info "Starting VPS hardening setup..."

################################################################################
# 1. Update System Packages
################################################################################
log_info "Updating system packages..."
apt-get update
apt-get upgrade -y
apt-get install -y curl wget gnupg2 lsb-release apt-transport-https ca-certificates

log_success "System packages updated"

################################################################################
# 2. Install and Configure UFW (Firewall)
################################################################################
log_info "Setting up UFW firewall..."

# Install UFW
apt-get install -y ufw

# Set default policies
ufw --force enable
ufw default deny incoming
ufw default allow outgoing

# Allow SSH (port 22) - CRITICAL: do this before enabling firewall
ufw allow 22/tcp comment "SSH"

# Allow HTTP and HTTPS
ufw allow 80/tcp comment "HTTP"
ufw allow 443/tcp comment "HTTPS"

# Enable UFW
ufw reload

log_success "UFW firewall configured (SSH: 22, HTTP: 80, HTTPS: 443)"

################################################################################
# 3. Install and Configure fail2ban
################################################################################
log_info "Installing fail2ban..."

apt-get install -y fail2ban

# Start and enable fail2ban
systemctl start fail2ban
systemctl enable fail2ban

log_success "fail2ban installed and enabled (default configuration)"

################################################################################
# 4. Install Docker and Docker Compose Plugin
################################################################################
log_info "Installing Docker and Docker Compose..."

# Remove any existing Docker installations
apt-get remove -y docker docker-engine docker.io containerd runc 2>/dev/null || true

# Add Docker's official GPG key
mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# Add Docker repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker and Compose plugin
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Start and enable Docker
systemctl start docker
systemctl enable docker

log_success "Docker and Docker Compose plugin installed"

################################################################################
# 5. Create bytemind System User
################################################################################
log_info "Creating bytemind system user..."

# Check if user already exists
if id "bytemind" &>/dev/null; then
    log_warning "User 'bytemind' already exists, skipping creation"
else
    # Create system user with home directory
    useradd -r -s /usr/sbin/nologin -d /opt/bytemind -m -c "ByteMind Application User" bytemind
    log_success "System user 'bytemind' created"
fi

################################################################################
# 6. SSH Hardening Recommendations
################################################################################
log_info "SSH Hardening Instructions"
cat << 'EOF'

================================================================================
IMPORTANT: SSH Hardening Setup Instructions
================================================================================

To complete SSH hardening, manually edit /etc/ssh/sshd_config and make these
changes. This requires human verification to avoid locking yourself out.

1. DISABLE PASSWORD AUTHENTICATION:
   Find this line: #PasswordAuthentication yes
   Change to:      PasswordAuthentication no

2. DISABLE ROOT LOGIN:
   Find this line: #PermitRootLogin prohibit-password
   Change to:      PermitRootLogin no

3. DISABLE EMPTY PASSWORDS:
   Find this line: #PermitEmptyPasswords no
   Ensure it is:   PermitEmptyPasswords no

4. OPTIONAL - CHANGE SSH PORT (for additional security):
   Find this line: #Port 22
   Change to:      Port 2222  (or any port > 1024)
   Then update UFW: ufw allow 2222/tcp

STEPS TO APPLY:
   1. sudo nano /etc/ssh/sshd_config
   2. Make the changes above
   3. Save and exit (Ctrl+X, Y, Enter)
   4. Validate the config: sudo sshd -t
   5. Restart SSH: sudo systemctl restart ssh

IMPORTANT: 
   - Keep an SSH session open while testing to avoid being locked out
   - Only restart SSH after validating with 'sshd -t'
   - Ensure you have key-based authentication set up before disabling passwords

================================================================================

EOF

log_warning "SSH hardening is manual to prevent lockout. Follow instructions above."

################################################################################
# 7. Create Necessary Directories
################################################################################
log_info "Creating application directories..."

# Create main app directory
mkdir -p /opt/bytemind

# Create subdirectories for the application
mkdir -p /opt/bytemind/config
mkdir -p /opt/bytemind/data
mkdir -p /opt/bytemind/logs
mkdir -p /opt/bytemind/docker-compose

# Set proper ownership
chown -R bytemind:bytemind /opt/bytemind
chmod 755 /opt/bytemind
chmod 755 /opt/bytemind/config
chmod 755 /opt/bytemind/data
chmod 755 /opt/bytemind/logs
chmod 755 /opt/bytemind/docker-compose

log_success "Application directories created at /opt/bytemind"

################################################################################
# Summary
################################################################################
cat << 'EOF'

================================================================================
VPS Hardening Setup Complete!
================================================================================

✓ System packages updated
✓ UFW firewall configured (allowing: SSH 22, HTTP 80, HTTPS 443)
✓ fail2ban installed (default configuration active)
✓ Docker and Docker Compose installed
✓ System user 'bytemind' created
✓ Application directories created at /opt/bytemind

NEXT STEPS:
1. Configure SSH hardening (see instructions above) - IMPORTANT!
2. Set up SSH key authentication on your local machine
3. Create docker-compose.yml in /opt/bytemind/docker-compose
4. Deploy your ByteMind application

SECURITY REMINDERS:
- Regularly update system packages: sudo apt-get update && apt-get upgrade
- Monitor fail2ban logs: sudo tail -f /var/log/fail2ban.log
- Check UFW status: sudo ufw status
- Keep SSH keys secure and backed up
- Only use SSH key authentication (no passwords)

================================================================================

EOF

log_success "VPS hardening setup completed successfully!"

# Exit with success
exit 0
