# Production-Grade Server Provisioning Platform

A declarative, config-driven platform for installing and managing 100+ server applications without interactive terminals. Built for SaaS providers, hosting companies, and infrastructure teams.

## 🎯 Core Features

- **Declarative Configuration**: YAML manifests define application contracts
- **Dynamic Form Generation**: UI automatically generated from manifests
- **Non-Interactive Execution**: No stdin, no pseudo-terminals, no SSH streaming
- **Security First**: Input validation, HMAC signatures, sandboxed execution
- **Scalable Architecture**: Support 100+ apps without core logic changes
- **Production Ready**: Fault-tolerant, idempotent, with comprehensive logging

## 🏗️ Architecture

```
Web Panel (Flask)          Agent Daemon (systemd)
     │                            │
     ├─ Manifest Registry         ├─ Job Poller
     ├─ Form Generator            ├─ Execution Engine
     ├─ Input Validator           ├─ State Manager
     └─ Job Manager               └─ Log Streamer
           │                            │
           └────────► Redis ◄───────────┘
                   (Job Queue)
```

### Components

1. **Web Panel**: REST API + Web UI for managing applications
2. **Agent Daemon**: Runs on target servers, executes whitelisted installers
3. **Manifest System**: YAML-based contracts defining app requirements
4. **Job Queue**: Redis-backed async job processing
5. **Installer Repository**: Git/S3 storage for application scripts

## 📋 Installer Contract

Every application consists of:

### 1. manifest.yml

```yaml
id: nginx
name: Nginx Web Server
version: 1.24.0
description: High-performance HTTP server
category: web-servers

os_requirements:
  family: [ubuntu, debian]
  min_version: "20.04"

inputs:
  - name: server_name
    type: string
    label: Server Name
    required: true
    validation:
      pattern: '^[a-z0-9\-\.]+$'
  
  - name: enable_ssl
    type: boolean
    label: Enable SSL
    default: "true"
  
  - name: https_port
    type: port
    label: HTTPS Port
    default: "443"
    visible_if:
      enable_ssl: "true"

install_script: install.sh
timeout_seconds: 600
idempotent: true
```

### 2. install.sh (Non-Interactive)

```bash
#!/bin/bash
set -euo pipefail

# Configuration from environment variables
SERVER_NAME="${SERVER_NAME}"
ENABLE_SSL="${ENABLE_SSL:-true}"

# Non-interactive installation
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq nginx

# Configuration (no prompts)
cat > /etc/nginx/sites-available/default <<EOF
server {
    server_name $SERVER_NAME;
    listen 80;
}
EOF

# Validation
nginx -t || exit 3

# Service management
systemctl enable nginx
systemctl restart nginx

exit 0
```

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Start Redis

```bash
redis-server
```

### 3. Start Panel

```bash
cd panel
python app.py
```

Access at: http://localhost:5000

### 4. Start Agent (on target server)

```bash
export AGENT_ID=agent-001
export SECRET_KEY=your-secret-key
export REDIS_URL=redis://localhost:6379/0

cd agent
python daemon.py
```

### 5. Install an Application

```bash
curl -X POST http://localhost:5000/api/apps/nginx/install \
  -H "Content-Type: application/json" \
  -d '{
    "server_id": "agent-001",
    "inputs": {
      "server_name": "example.com",
      "admin_email": "admin@example.com",
      "enable_ssl": "true"
    }
  }'
```

## 📚 Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) - Detailed system design
- [DEPLOYMENT.md](DEPLOYMENT.md) - Production deployment guide
- [shared/schema.py](shared/schema.py) - Manifest schema specification

## 🔒 Security Features

### Input Validation
- Schema-based validation (Pydantic)
- Regex pattern matching
- Type coercion and range checks
- SQL injection prevention

### Execution Security
- HMAC-SHA256 job signatures
- Whitelisted installers only
- Sandboxed subprocess execution
- Process timeout enforcement
- No arbitrary command execution

### Access Control
- Agent runs as root (required for system changes)
- Panel runs as unprivileged user
- No direct shell access from web
- Audit trail for all operations

## 📊 Supported Input Types

| Type | Description | Validation |
|------|-------------|------------|
| `string` | Text input | pattern, min/max length |
| `integer` | Numeric input | min/max value |
| `boolean` | Yes/No | true/false |
| `password` | Sensitive text | masked in logs |
| `select` | Dropdown | allowed_values |
| `email` | Email address | RFC 5322 pattern |
| `port` | Port number | 1-65535 range |

## 🎨 Example Applications

### Included Installers

1. **Nginx** - Web server with SSL support
2. **MySQL** - Database with user creation
3. **Docker** - Container runtime with compose

### Adding New Applications

```bash
# 1. Create directory
mkdir installers/myapp

# 2. Create manifest
cat > installers/myapp/manifest.yml <<EOF
id: myapp
name: My Application
version: 1.0.0
# ... (see examples)
EOF

# 3. Create installer
cat > installers/myapp/install.sh <<EOF
#!/bin/bash
set -euo pipefail
# Non-interactive installation
EOF

# 4. Test
chmod +x installers/myapp/install.sh
export MY_VAR=value
bash installers/myapp/install.sh
```

## 🧪 Testing

```bash
# Run tests
cd tests
pytest test_platform.py -v

# Test specific component
pytest test_platform.py::TestInputValidator -v
```

## 📈 Monitoring

### Health Check

```bash
curl http://localhost:5000/api/health
```

### Job Status

```bash
curl http://localhost:5000/api/jobs/JOB_ID
```

### Logs

```bash
# Agent logs
tail -f /var/log/provisioning/agent.log

# Job-specific logs
tail -f /var/log/provisioning/JOB_ID.log
```

## 🔧 Configuration

### Panel Environment Variables

```bash
SECRET_KEY=your-secret-key-here
REDIS_URL=redis://localhost:6379/0
FLASK_ENV=production
```

### Agent Environment Variables

```bash
AGENT_ID=agent-001
SECRET_KEY=same-as-panel
REDIS_URL=redis://panel-server:6379/0
```

## 🚦 Exit Codes

| Code | Meaning | Action |
|------|---------|--------|
| 0 | Success | Job completed |
| 1 | Validation error | Fix inputs, no retry |
| 2 | Installation error | Retry with backoff |
| 3 | Configuration error | Manual intervention |
| 124 | Timeout | Increase timeout_seconds |

## 🔄 Idempotency

All installers MUST be idempotent:

```bash
# Check if already installed
if command -v nginx &> /dev/null; then
    echo "Already installed, updating config"
    # Update configuration only
else
    # Full installation
fi
```

## 📦 Production Deployment

### Panel (Control Server)

```bash
# Install with gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 panel.app:app

# Or use systemd service
systemctl start provisioning-panel
```

### Agent (Target Servers)

```bash
# Install systemd service
cp agent/provisioning-agent.service /etc/systemd/system/
systemctl enable provisioning-agent
systemctl start provisioning-agent
```

### Nginx Reverse Proxy

```nginx
server {
    listen 80;
    server_name provisioning.example.com;
    
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
    }
}
```

## 🛠️ Troubleshooting

### Jobs Not Executing

1. Check agent is running: `systemctl status provisioning-agent`
2. Verify Redis connection: `redis-cli ping`
3. Check SECRET_KEY matches

### Installation Fails

1. View logs: `/var/log/provisioning/JOB_ID.log`
2. Test manually: `bash installers/app/install.sh`
3. Check OS compatibility in manifest

### Signature Validation Fails

1. Ensure SECRET_KEY is identical
2. Check for whitespace in .env files
3. Verify job JSON integrity

## 🎯 Design Principles

1. **Declarative over Imperative**: Manifests define "what", not "how"
2. **State-Driven Execution**: Jobs are data, not code
3. **Idempotent Operations**: Safe to run multiple times
4. **Fault-Tolerant**: Graceful failure handling
5. **Scalable**: Add apps without changing core logic

## 🚫 What This Platform Does NOT Do

- ❌ Interactive terminal emulation
- ❌ Parsing stdout to detect questions
- ❌ SSH streaming from web interface
- ❌ Arbitrary command execution
- ❌ Root access from web layer

## 🔮 Future Enhancements

- [ ] Rollback support with state snapshots
- [ ] Application dependency graphs
- [ ] Webhook notifications
- [ ] Multi-server deployments
- [ ] Application templates/bundles
- [ ] Community marketplace
- [ ] Monitoring integration
- [ ] Pre-installation backups

## 📄 License

MIT License - See LICENSE file

## 🤝 Contributing

1. Fork the repository
2. Create feature branch
3. Add tests for new features
4. Submit pull request

## 📞 Support

- Documentation: See ARCHITECTURE.md and DEPLOYMENT.md
- Issues: GitHub Issues
- Security: security@example.com

---

**Built for production. Designed for scale. Secured by default.**
