# Deployment Guide

## Prerequisites

- Ubuntu 20.04+ or Debian 11+
- Python 3.8+
- Redis 6.0+
- Root access on target servers

## 1. Panel Deployment (Control Server)

### Install Dependencies

```bash
# Update system
apt-get update && apt-get upgrade -y

# Install Python and Redis
apt-get install -y python3 python3-pip redis-server

# Install Python packages
cd /opt/provisioning-platform
pip3 install -r requirements.txt
```

### Configure Redis

```bash
# Edit Redis config
nano /etc/redis/redis.conf

# Set:
# bind 0.0.0.0  # Or specific IP
# requirepass YOUR_STRONG_PASSWORD

# Restart Redis
systemctl restart redis
```

### Configure Panel

```bash
# Generate secret key
export SECRET_KEY=$(openssl rand -hex 32)

# Create environment file
cat > /opt/provisioning-platform/panel/.env <<EOF
SECRET_KEY=$SECRET_KEY
REDIS_URL=redis://:YOUR_REDIS_PASSWORD@localhost:6379/0
FLASK_ENV=production
EOF
```

### Run Panel (Production)

```bash
# Install gunicorn
pip3 install gunicorn

# Create systemd service
cat > /etc/systemd/system/provisioning-panel.service <<EOF
[Unit]
Description=Provisioning Panel
After=network.target redis.service

[Service]
Type=notify
User=www-data
WorkingDirectory=/opt/provisioning-platform/panel
EnvironmentFile=/opt/provisioning-platform/panel/.env
ExecStart=/usr/local/bin/gunicorn -w 4 -b 0.0.0.0:5000 --timeout 120 app:app
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# Start service
systemctl daemon-reload
systemctl enable provisioning-panel
systemctl start provisioning-panel
```

### Setup Nginx Reverse Proxy

```bash
# Install Nginx
apt-get install -y nginx

# Create config
cat > /etc/nginx/sites-available/provisioning <<EOF
server {
    listen 80;
    server_name provisioning.example.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    # WebSocket support
    location /ws {
        proxy_pass http://127.0.0.1:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
EOF

# Enable site
ln -s /etc/nginx/sites-available/provisioning /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx

# Setup SSL with Let's Encrypt
apt-get install -y certbot python3-certbot-nginx
certbot --nginx -d provisioning.example.com
```

## 2. Agent Deployment (Target Servers)

### Install Agent

```bash
# Create directory
mkdir -p /opt/provisioning

# Copy files (from control server)
scp -r /opt/provisioning-platform/agent root@target-server:/opt/provisioning/
scp -r /opt/provisioning-platform/installers root@target-server:/opt/provisioning/
scp -r /opt/provisioning-platform/shared root@target-server:/opt/provisioning/

# Or clone from Git
cd /opt/provisioning
git clone https://github.com/your-org/provisioning-platform.git .
```

### Install Dependencies

```bash
# Install Python packages
pip3 install redis pyyaml

# Create log directory
mkdir -p /var/log/provisioning
mkdir -p /var/lib/provisioning
```

### Configure Agent

```bash
# Set unique agent ID
AGENT_ID="agent-$(hostname)"

# Create environment file
cat > /opt/provisioning/agent/.env <<EOF
AGENT_ID=$AGENT_ID
REDIS_URL=redis://:YOUR_REDIS_PASSWORD@PANEL_SERVER_IP:6379/0
SECRET_KEY=SAME_AS_PANEL_SECRET_KEY
EOF
```

### Install Systemd Service

```bash
# Copy service file
cp /opt/provisioning/agent/provisioning-agent.service /etc/systemd/system/

# Edit service to load .env
nano /etc/systemd/system/provisioning-agent.service

# Add:
# EnvironmentFile=/opt/provisioning/agent/.env

# Start service
systemctl daemon-reload
systemctl enable provisioning-agent
systemctl start provisioning-agent

# Check status
systemctl status provisioning-agent
journalctl -u provisioning-agent -f
```

## 3. Installer Repository Setup

### Option A: Git Repository

```bash
# Create Git repo for installers
cd /opt/provisioning/installers
git init
git add .
git commit -m "Initial installers"
git remote add origin https://github.com/your-org/installers.git
git push -u origin main

# On agents, setup auto-update
cat > /etc/cron.d/provisioning-update <<EOF
*/15 * * * * root cd /opt/provisioning/installers && git pull --quiet
EOF
```

### Option B: S3/Object Storage

```bash
# Upload installers to S3
aws s3 sync /opt/provisioning/installers s3://your-bucket/installers/

# On agents, setup sync
cat > /etc/cron.d/provisioning-update <<EOF
*/15 * * * * root aws s3 sync s3://your-bucket/installers/ /opt/provisioning/installers/
EOF
```

## 4. Security Hardening

### Firewall Rules

```bash
# Panel server
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP
ufw allow 443/tcp   # HTTPS
ufw allow 6379/tcp from AGENT_IP  # Redis (restrict to agent IPs)
ufw enable

# Agent servers
ufw allow 22/tcp    # SSH only
ufw allow from PANEL_IP to any port 6379  # Redis connection
ufw enable
```

### Redis Security

```bash
# On panel server
nano /etc/redis/redis.conf

# Set:
requirepass STRONG_PASSWORD
bind 127.0.0.1 PANEL_PRIVATE_IP
maxmemory 256mb
maxmemory-policy allkeys-lru

# Restart
systemctl restart redis
```

### File Permissions

```bash
# Panel
chown -R www-data:www-data /opt/provisioning-platform/panel
chmod 600 /opt/provisioning-platform/panel/.env

# Agent
chown -R root:root /opt/provisioning
chmod 700 /opt/provisioning/installers
chmod 600 /opt/provisioning/agent/.env
chmod +x /opt/provisioning/installers/*/install.sh
```

### Audit Logging

```bash
# Enable auditd
apt-get install -y auditd

# Monitor installer execution
auditctl -w /opt/provisioning/installers -p x -k provisioning_exec

# View logs
ausearch -k provisioning_exec
```

## 5. Monitoring Setup

### Prometheus Metrics

```bash
# Install prometheus client
pip3 install prometheus-client

# Add to panel/app.py:
from prometheus_client import Counter, Histogram, generate_latest

job_counter = Counter('provisioning_jobs_total', 'Total jobs', ['app_id', 'status'])
job_duration = Histogram('provisioning_job_duration_seconds', 'Job duration', ['app_id'])

@app.route('/metrics')
def metrics():
    return generate_latest()
```

### Log Aggregation

```bash
# Install Filebeat
curl -L -O https://artifacts.elastic.co/downloads/beats/filebeat/filebeat-8.11.0-amd64.deb
dpkg -i filebeat-8.11.0-amd64.deb

# Configure
cat > /etc/filebeat/filebeat.yml <<EOF
filebeat.inputs:
- type: log
  paths:
    - /var/log/provisioning/*.log
  fields:
    service: provisioning-agent

output.elasticsearch:
  hosts: ["elasticsearch:9200"]
EOF

systemctl enable filebeat
systemctl start filebeat
```

## 6. Testing

### Test Panel

```bash
# Health check
curl http://localhost:5000/api/health

# List apps
curl http://localhost:5000/api/apps

# Get specific app
curl http://localhost:5000/api/apps/nginx
```

### Test Agent

```bash
# Check logs
tail -f /var/log/provisioning/agent.log

# Manual job test
python3 <<EOF
import redis
import json

r = redis.Redis(host='localhost', port=6379, password='YOUR_PASSWORD')
job = {
    'job_id': 'test-123',
    'app_id': 'nginx',
    'inputs': {
        'server_name': 'test.example.com',
        'admin_email': 'admin@example.com'
    },
    'server_id': 'agent-001',
    'user_id': 'test',
    'signature': 'test'
}
r.rpush('agent:agent-001:jobs', json.dumps(job))
EOF

# Check execution
tail -f /var/log/provisioning/test-123.log
```

### Integration Test

```bash
# Install test app
curl -X POST http://localhost:5000/api/apps/nginx/install \
  -H "Content-Type: application/json" \
  -d '{
    "server_id": "agent-001",
    "user_id": "admin",
    "inputs": {
      "server_name": "test.example.com",
      "admin_email": "admin@example.com",
      "http_port": "80",
      "enable_ssl": "false",
      "worker_processes": "auto"
    }
  }'

# Get job status
curl http://localhost:5000/api/jobs/JOB_ID
```

## 7. Backup & Recovery

### Backup

```bash
# Backup Redis data
redis-cli --rdb /backup/redis-$(date +%Y%m%d).rdb

# Backup installers
tar -czf /backup/installers-$(date +%Y%m%d).tar.gz /opt/provisioning/installers

# Backup logs
tar -czf /backup/logs-$(date +%Y%m%d).tar.gz /var/log/provisioning
```

### Recovery

```bash
# Restore Redis
systemctl stop redis
cp /backup/redis-YYYYMMDD.rdb /var/lib/redis/dump.rdb
chown redis:redis /var/lib/redis/dump.rdb
systemctl start redis

# Restore installers
tar -xzf /backup/installers-YYYYMMDD.tar.gz -C /
systemctl restart provisioning-agent
```

## 8. Scaling

### Multiple Panel Instances

```bash
# Use external Redis
# Deploy multiple panel instances behind load balancer
# Share same Redis and SECRET_KEY

# HAProxy config
backend panel_backend
    balance roundrobin
    server panel1 10.0.1.10:5000 check
    server panel2 10.0.1.11:5000 check
```

### Multiple Agents

```bash
# Each server gets unique AGENT_ID
# All connect to same Redis
# Jobs routed by server_id
```

## 9. Troubleshooting

### Panel Issues

```bash
# Check logs
journalctl -u provisioning-panel -f

# Test Redis connection
redis-cli -h localhost -p 6379 -a PASSWORD ping

# Check Python errors
python3 -c "from panel.app import app; print('OK')"
```

### Agent Issues

```bash
# Check agent status
systemctl status provisioning-agent

# View logs
tail -f /var/log/provisioning/agent.log

# Test installer manually
cd /opt/provisioning/installers/nginx
export SERVER_NAME=test.com
export ADMIN_EMAIL=admin@test.com
bash install.sh
```

### Common Issues

**Issue: Jobs not executing**
- Check agent is running: `systemctl status provisioning-agent`
- Verify Redis connection: `redis-cli ping`
- Check SECRET_KEY matches between panel and agent

**Issue: Installation fails**
- Check installer logs: `/var/log/provisioning/JOB_ID.log`
- Verify OS compatibility in manifest
- Test script manually with env vars

**Issue: Signature validation fails**
- Ensure SECRET_KEY is identical on panel and agent
- Check for whitespace in .env files
- Verify job JSON is not corrupted

## 10. Production Checklist

- [ ] SECRET_KEY is strong and unique
- [ ] Redis has password authentication
- [ ] Firewall rules configured
- [ ] SSL certificates installed
- [ ] Monitoring and alerting setup
- [ ] Log rotation configured
- [ ] Backup strategy implemented
- [ ] Agent auto-update enabled
- [ ] Security audit completed
- [ ] Documentation updated
