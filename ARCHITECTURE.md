# Production-Grade Server Provisioning Platform - Architecture

## 1. System Architecture

### Components

```
┌─────────────────────────────────────────────────────────────┐
│                     Web Panel (Flask)                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  Manifest    │  │   Dynamic    │  │     Job      │      │
│  │  Registry    │  │    Form      │  │   Manager    │      │
│  │              │  │  Generator   │  │              │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│                                                               │
│  ┌──────────────────────────────────────────────────┐       │
│  │         Input Validator (Schema-based)           │       │
│  └──────────────────────────────────────────────────┘       │
└────────────────────────┬─────────────────────────────────────┘
                         │ REST API + HMAC Signatures
                         │
                    ┌────▼────┐
                    │  Redis  │ Job Queue + PubSub
                    └────┬────┘
                         │
┌────────────────────────▼─────────────────────────────────────┐
│                   Agent Daemon (systemd)                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │     Job      │  │  Execution   │  │    State     │       │
│  │    Poller    │  │   Engine     │  │   Manager    │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
│                                                                │
│  ┌──────────────────────────────────────────────────┐        │
│  │    Security: Signature Validation, Sandboxing    │        │
│  └──────────────────────────────────────────────────┘        │
└────────────────────────┬───────────────────────────────────────┘
                         │
                    ┌────▼────┐
                    │Installer│ Whitelisted Scripts
                    │Repository│ (manifest.yml + install.sh)
                    └─────────┘
```

## 2. Installer Contract Specification

### Manifest Schema (manifest.yml)

Every application MUST provide a manifest.yml with:

**Required Fields:**
- `id`: Unique identifier (lowercase, hyphens)
- `name`: Human-readable name
- `version`: Application version
- `description`: Brief description
- `category`: Application category
- `author`: Maintainer information
- `os_requirements`: Supported OS families and versions
- `install_script`: Name of installation script (default: install.sh)
- `timeout_seconds`: Maximum execution time
- `idempotent`: Whether script can be run multiple times safely

**Input Definition:**
- `name`: Variable name (snake_case)
- `type`: string|integer|boolean|password|select|email|port
- `label`: Display label
- `description`: Help text
- `required`: Boolean
- `default`: Default value
- `validation`: Rules (pattern, min/max length/value, allowed_values)
- `visible_if`: Conditional visibility based on other inputs
- `sensitive`: Mask in logs (for passwords)

**Example:**
```yaml
id: nginx
name: Nginx Web Server
version: 1.24.0
description: High-performance HTTP server
category: web-servers
author: Platform Team

os_requirements:
  family: [ubuntu, debian]
  min_version: "20.04"

resource_requirements:
  min_ram_mb: 512
  min_disk_mb: 100

inputs:
  - name: server_name
    type: string
    label: Server Name
    required: true
    validation:
      pattern: '^[a-z0-9\-\.]+$'
      max_length: 253

install_script: install.sh
timeout_seconds: 600
idempotent: true
```

### Installation Script Contract (install.sh)

**Requirements:**
1. Must be non-interactive (no stdin reads)
2. Receives configuration via environment variables
3. Must use `set -euo pipefail` for error handling
4. Must log to stdout/stderr
5. Must return proper exit codes:
   - 0: Success
   - 1: Validation error
   - 2: Installation error
   - 3: Configuration error
   - 124: Timeout

**Environment Variables:**
- All manifest inputs converted to UPPERCASE
- `DEBIAN_FRONTEND=noninteractive` automatically set
- `PROVISIONING_JOB=true` flag

**Example:**
```bash
#!/bin/bash
set -euo pipefail

# Logging
log() { echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*"; }
error() { log "ERROR: $*"; exit "${2:-2}"; }

# Validate required variables
[[ -z "${SERVER_NAME:-}" ]] && error "SERVER_NAME not set" 1

# Check idempotency
if command -v nginx &> /dev/null; then
    log "Already installed, updating config only"
fi

# Non-interactive installation
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq nginx

# Configuration (no prompts)
cat > /etc/nginx/sites-available/default <<EOF
server {
    server_name $SERVER_NAME;
    # ...
}
EOF

# Validation
nginx -t || error "Config test failed" 3

# Service management
systemctl enable nginx
systemctl restart nginx

log "Installation completed"
exit 0
```

## 3. Agent Execution Flow

```
1. Poll Queue
   └─> BLPOP agent:{agent_id}:jobs (blocking)

2. Receive Job
   └─> Parse JSON payload

3. Validate Signature
   └─> HMAC-SHA256 verification
   └─> Reject if invalid

4. Validate Installer
   └─> Check if app_id exists in whitelist
   └─> Load manifest.yml

5. Validate Inputs
   └─> Type checking
   └─> Pattern matching
   └─> Range validation
   └─> Required field check

6. Prepare Environment
   └─> Convert inputs to env vars
   └─> Set DEBIAN_FRONTEND=noninteractive

7. Execute Script
   └─> subprocess.Popen with timeout
   └─> Capture stdout/stderr
   └─> Monitor exit code

8. Handle Result
   ├─> Success (exit 0)
   │   └─> Publish result to Redis
   │   └─> Update job status
   │
   └─> Failure (exit != 0)
       └─> Log error
       └─> Publish failure result
       └─> Preserve logs for debugging

9. Cleanup
   └─> Release resources
   └─> Continue polling
```

## 4. Failure Handling & Retry Strategy

### Failure Categories

**1. Validation Failures (Exit 1)**
- Invalid inputs
- Missing required fields
- Pattern mismatches
- Action: Reject immediately, no retry

**2. Installation Failures (Exit 2)**
- Package not found
- Network errors
- Dependency conflicts
- Action: Retry with exponential backoff (max 3 attempts)

**3. Configuration Failures (Exit 3)**
- Invalid config syntax
- Service start failures
- Action: Manual intervention required

**4. Timeout (Exit 124)**
- Script exceeded timeout_seconds
- Action: Kill process group, mark as failed

### Retry Logic

```python
def execute_with_retry(job, max_retries=3):
    for attempt in range(max_retries):
        result = execute_job(job)
        
        if result['exit_code'] == 0:
            return result  # Success
        
        if result['exit_code'] == 1:
            return result  # Validation error, don't retry
        
        if result['exit_code'] == 2 and attempt < max_retries - 1:
            delay = 2 ** attempt * 10  # Exponential backoff
            time.sleep(delay)
            continue
        
        return result  # Other errors or max retries reached
```

### Idempotency

All installers MUST be idempotent:
- Check if already installed before proceeding
- Update configuration if already exists
- Don't fail if service already running
- Use `systemctl reload` instead of `restart` when possible

## 5. Logging & Observability

### Log Levels

**Agent Logs:**
- `/var/log/provisioning/agent.log` - Daemon activity
- `/var/log/provisioning/{job_id}.log` - Per-job execution logs

**Panel Logs:**
- Application logs (Flask)
- API access logs
- Job creation audit trail

### Structured Logging

```python
{
    "timestamp": "2024-01-15T10:30:00Z",
    "level": "INFO",
    "job_id": "uuid",
    "app_id": "nginx",
    "event": "execution_started",
    "metadata": {
        "server_id": "agent-001",
        "user_id": "user123"
    }
}
```

### Metrics

**Key Metrics:**
- Job success rate (by app_id)
- Average execution time
- Queue depth
- Agent health status
- Failed jobs by error type

**Monitoring Endpoints:**
- `GET /api/health` - Panel health
- `GET /api/metrics` - Prometheus-compatible metrics
- Agent heartbeat via Redis

### Real-time Updates

**WebSocket/Server-Sent Events:**
```javascript
// Subscribe to job updates
const eventSource = new EventSource('/api/jobs/{job_id}/stream');
eventSource.onmessage = (event) => {
    const update = JSON.parse(event.data);
    console.log(update.status, update.output);
};
```

**Redis PubSub:**
```python
# Agent publishes
redis.publish(f'job:{job_id}:updates', json.dumps({
    'status': 'running',
    'progress': 50,
    'message': 'Installing packages...'
}))

# Panel subscribes
pubsub = redis.pubsub()
pubsub.subscribe(f'job:{job_id}:updates')
```

## 6. Security Model

### Defense in Depth

**Layer 1: Input Validation**
- Schema-based validation (Pydantic)
- Regex pattern matching
- Type coercion
- Length/range limits
- SQL injection prevention

**Layer 2: Signature Verification**
- HMAC-SHA256 signatures
- Prevents job tampering
- Shared secret between panel and agent

**Layer 3: Whitelist Enforcement**
- Only manifests in `/opt/provisioning/installers/` can run
- No arbitrary script execution
- Path traversal prevention

**Layer 4: Sandboxing**
- Process isolation (subprocess with timeout)
- Resource limits (timeout_seconds)
- Process group management (SIGTERM/SIGKILL)

**Layer 5: Privilege Management**
- Agent runs as root (required for system changes)
- Panel runs as unprivileged user
- No direct shell access from web

**Layer 6: Audit Trail**
- All jobs logged with user_id
- Immutable log storage
- Job history retention

### OWASP Top 10 Compliance

1. **Injection**: Parameterized inputs, no shell interpolation
2. **Broken Authentication**: JWT/session tokens (not shown in minimal code)
3. **Sensitive Data Exposure**: Passwords marked as sensitive, masked in logs
4. **XML External Entities**: YAML parser configured safely
5. **Broken Access Control**: User/server authorization (extend as needed)
6. **Security Misconfiguration**: Secure defaults, no debug in production
7. **XSS**: Input sanitization, CSP headers
8. **Insecure Deserialization**: JSON schema validation
9. **Components with Known Vulnerabilities**: Dependency scanning
10. **Insufficient Logging**: Comprehensive audit trail

## 7. Scalability

### Horizontal Scaling

**Panel:**
- Stateless design
- Multiple instances behind load balancer
- Shared Redis for job queue

**Agents:**
- One agent per server
- Independent execution
- No inter-agent communication required

**Queue:**
- Redis for simplicity
- Can replace with RabbitMQ/SQS for higher scale
- Separate queues per agent

### Performance Optimization

**Manifest Caching:**
- Load manifests at startup
- Reload on SIGHUP
- In-memory registry

**Job Batching:**
- Support bulk installations
- Parallel execution (future enhancement)

**Database:**
- Current: Redis (ephemeral)
- Production: PostgreSQL for job history
- Elasticsearch for log aggregation

## 8. Deployment

### Panel Deployment

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment
export SECRET_KEY="$(openssl rand -hex 32)"
export REDIS_URL="redis://localhost:6379/0"

# Run with gunicorn (production)
gunicorn -w 4 -b 0.0.0.0:5000 panel.app:app
```

### Agent Deployment

```bash
# Copy files
cp -r provisioning-platform /opt/provisioning
cp agent/provisioning-agent.service /etc/systemd/system/

# Set permissions
chmod +x /opt/provisioning/installers/*/install.sh

# Configure
export AGENT_ID="agent-$(hostname)"
export SECRET_KEY="same-as-panel"

# Start service
systemctl daemon-reload
systemctl enable provisioning-agent
systemctl start provisioning-agent
```

### Installer Repository

```bash
# Git-based (recommended)
cd /opt/provisioning
git clone https://github.com/company/installers.git

# Auto-update
*/15 * * * * cd /opt/provisioning/installers && git pull
```

## 9. Adding New Applications

### Process

1. Create directory: `/installers/{app_id}/`
2. Write `manifest.yml` following schema
3. Write `install.sh` (non-interactive)
4. Test locally: `bash install.sh` with env vars
5. Commit to repository
6. Panel auto-discovers on next scan

### Testing Checklist

- [ ] Script runs without stdin
- [ ] All inputs validated
- [ ] Idempotent (can run multiple times)
- [ ] Proper exit codes
- [ ] Logs to stdout
- [ ] Completes within timeout
- [ ] Service starts successfully
- [ ] Cleanup on failure

## 10. Future Enhancements

- **Rollback**: Uninstall scripts + state snapshots
- **Dependencies**: App dependency graph
- **Webhooks**: Notify external systems on completion
- **Multi-server**: Deploy to multiple servers simultaneously
- **Templates**: Pre-configured app bundles
- **Marketplace**: Community-contributed installers
- **Monitoring Integration**: Auto-configure Prometheus exporters
- **Backup**: Pre-installation snapshots
