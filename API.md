# API Documentation

## Base URL

```
http://localhost:5000/api
```

## Authentication

Currently uses server_id and user_id for identification. In production, implement JWT/OAuth2.

## Endpoints

### 1. List Applications

**GET** `/apps`

List all available applications with optional filtering.

**Query Parameters:**
- `q` (string, optional): Search query
- `category` (string, optional): Filter by category
- `tags` (array, optional): Filter by tags

**Response:**
```json
{
  "success": true,
  "count": 3,
  "apps": [
    {
      "id": "nginx",
      "name": "Nginx Web Server",
      "version": "1.24.0",
      "description": "High-performance HTTP server",
      "category": "web-servers",
      "tags": ["web-server", "reverse-proxy"],
      "inputs": [...]
    }
  ]
}
```

**Example:**
```bash
curl http://localhost:5000/api/apps
curl http://localhost:5000/api/apps?category=databases
curl http://localhost:5000/api/apps?q=nginx
```

---

### 2. Get Application Details

**GET** `/apps/{app_id}`

Get detailed information about a specific application including its manifest.

**Path Parameters:**
- `app_id` (string, required): Application identifier

**Response:**
```json
{
  "success": true,
  "app": {
    "id": "nginx",
    "name": "Nginx Web Server",
    "version": "1.24.0",
    "description": "High-performance HTTP server",
    "category": "web-servers",
    "os_requirements": {
      "family": ["ubuntu", "debian"],
      "min_version": "20.04"
    },
    "resource_requirements": {
      "min_ram_mb": 512,
      "min_disk_mb": 100,
      "min_cpu_cores": 1
    },
    "inputs": [
      {
        "name": "server_name",
        "type": "string",
        "label": "Server Name",
        "description": "Primary domain name",
        "required": true,
        "validation": {
          "pattern": "^[a-z0-9\\-\\.]+$",
          "max_length": 253
        }
      }
    ],
    "install_script": "install.sh",
    "timeout_seconds": 600,
    "idempotent": true,
    "tags": ["web-server"]
  }
}
```

**Example:**
```bash
curl http://localhost:5000/api/apps/nginx
```

---

### 3. Install Application

**POST** `/apps/{app_id}/install`

Create an installation job for an application.

**Path Parameters:**
- `app_id` (string, required): Application identifier

**Request Body:**
```json
{
  "server_id": "agent-001",
  "user_id": "admin",
  "inputs": {
    "server_name": "example.com",
    "admin_email": "admin@example.com",
    "enable_ssl": "true",
    "http_port": "80",
    "https_port": "443"
  }
}
```

**Response (Success):**
```json
{
  "success": true,
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Installation job created"
}
```

**Response (Validation Error):**
```json
{
  "success": false,
  "error": "Input validation failed",
  "errors": [
    "Server Name is required",
    "Port must be between 1 and 65535"
  ]
}
```

**Example:**
```bash
curl -X POST http://localhost:5000/api/apps/nginx/install \
  -H "Content-Type: application/json" \
  -d '{
    "server_id": "agent-001",
    "user_id": "admin",
    "inputs": {
      "server_name": "example.com",
      "admin_email": "admin@example.com",
      "enable_ssl": "true"
    }
  }'
```

---

### 4. Get Job Status

**GET** `/jobs/{job_id}`

Get the status and result of a job.

**Path Parameters:**
- `job_id` (string, required): Job identifier

**Response:**
```json
{
  "success": true,
  "job": {
    "job_id": "550e8400-e29b-41d4-a716-446655440000",
    "app_id": "nginx",
    "server_id": "agent-001",
    "user_id": "admin",
    "inputs": {
      "server_name": "example.com"
    },
    "created_at": "2024-01-15T10:30:00Z",
    "status": "queued"
  },
  "result": {
    "job_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "success",
    "exit_code": 0,
    "output": "[2024-01-15 10:30:05] Starting Nginx installation\n...",
    "started_at": "2024-01-15T10:30:05Z",
    "completed_at": "2024-01-15T10:32:15Z",
    "error": null
  }
}
```

**Job Statuses:**
- `queued`: Job created, waiting for agent
- `running`: Agent is executing the job
- `success`: Job completed successfully (exit code 0)
- `failed`: Job failed (exit code != 0)

**Example:**
```bash
curl http://localhost:5000/api/jobs/550e8400-e29b-41d4-a716-446655440000
```

---

### 5. List Jobs

**GET** `/jobs`

List all jobs with optional filtering.

**Query Parameters:**
- `user_id` (string, optional): Filter by user
- `server_id` (string, optional): Filter by server

**Response:**
```json
{
  "success": true,
  "count": 10,
  "jobs": [
    {
      "job_id": "550e8400-e29b-41d4-a716-446655440000",
      "app_id": "nginx",
      "server_id": "agent-001",
      "user_id": "admin",
      "created_at": "2024-01-15T10:30:00Z",
      "status": "success"
    }
  ]
}
```

**Example:**
```bash
curl http://localhost:5000/api/jobs
curl http://localhost:5000/api/jobs?user_id=admin
curl http://localhost:5000/api/jobs?server_id=agent-001
```

---

### 6. Health Check

**GET** `/health`

Check panel health and status.

**Response:**
```json
{
  "success": true,
  "status": "healthy",
  "apps_loaded": 3
}
```

**Example:**
```bash
curl http://localhost:5000/api/health
```

---

## Error Responses

All endpoints return consistent error responses:

```json
{
  "success": false,
  "error": "Error message",
  "errors": ["Detailed error 1", "Detailed error 2"]
}
```

**HTTP Status Codes:**
- `200 OK`: Success
- `201 Created`: Resource created (job)
- `400 Bad Request`: Validation error
- `404 Not Found`: Resource not found
- `500 Internal Server Error`: Server error

---

## Input Validation

### Field Types

| Type | Description | Example |
|------|-------------|---------|
| `string` | Text input | "example.com" |
| `integer` | Whole number | "100" |
| `boolean` | True/false | "true" or "false" |
| `password` | Sensitive text | "SecurePass123!" |
| `select` | Dropdown choice | "production" |
| `email` | Email address | "user@example.com" |
| `port` | Port number | "80" |

### Validation Rules

```json
{
  "validation": {
    "pattern": "^[a-z0-9]+$",
    "min_length": 3,
    "max_length": 64,
    "min_value": 1,
    "max_value": 100,
    "allowed_values": ["dev", "staging", "prod"]
  }
}
```

### Conditional Inputs

Fields can be conditionally required based on other inputs:

```json
{
  "name": "ssl_port",
  "type": "port",
  "label": "SSL Port",
  "required": true,
  "visible_if": {
    "enable_ssl": "true"
  }
}
```

---

## WebSocket API (Future)

Real-time job updates via WebSocket:

```javascript
const ws = new WebSocket('ws://localhost:5000/ws/jobs/JOB_ID');

ws.onmessage = (event) => {
  const update = JSON.parse(event.data);
  console.log(update.status, update.message);
};
```

---

## Rate Limiting (Production)

Implement rate limiting in production:

```python
from flask_limiter import Limiter

limiter = Limiter(app, key_func=get_remote_address)

@app.route('/api/apps/<app_id>/install', methods=['POST'])
@limiter.limit("10 per minute")
def install_app(app_id):
    # ...
```

---

## Authentication (Production)

Implement JWT authentication:

```bash
# Login
curl -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "secret"}'

# Response
{
  "success": true,
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}

# Use token
curl http://localhost:5000/api/apps \
  -H "Authorization: Bearer TOKEN"
```

---

## Pagination (Production)

For large datasets, implement pagination:

```bash
curl http://localhost:5000/api/jobs?page=1&per_page=20
```

Response:
```json
{
  "success": true,
  "page": 1,
  "per_page": 20,
  "total": 150,
  "pages": 8,
  "jobs": [...]
}
```

---

## Examples

### Complete Installation Flow

```bash
# 1. List available apps
curl http://localhost:5000/api/apps

# 2. Get app details
curl http://localhost:5000/api/apps/nginx

# 3. Install app
JOB_ID=$(curl -X POST http://localhost:5000/api/apps/nginx/install \
  -H "Content-Type: application/json" \
  -d '{
    "server_id": "agent-001",
    "inputs": {
      "server_name": "example.com",
      "admin_email": "admin@example.com"
    }
  }' | jq -r '.job_id')

# 4. Poll job status
while true; do
  STATUS=$(curl -s http://localhost:5000/api/jobs/$JOB_ID | jq -r '.result.status')
  echo "Status: $STATUS"
  [[ "$STATUS" == "success" || "$STATUS" == "failed" ]] && break
  sleep 5
done

# 5. Get final result
curl http://localhost:5000/api/jobs/$JOB_ID | jq '.result'
```

### Python Client Example

```python
import requests
import time

class ProvisioningClient:
    def __init__(self, base_url):
        self.base_url = base_url
    
    def list_apps(self, category=None):
        params = {'category': category} if category else {}
        r = requests.get(f'{self.base_url}/apps', params=params)
        return r.json()['apps']
    
    def install_app(self, app_id, server_id, inputs):
        data = {
            'server_id': server_id,
            'inputs': inputs
        }
        r = requests.post(f'{self.base_url}/apps/{app_id}/install', json=data)
        return r.json()['job_id']
    
    def wait_for_job(self, job_id, timeout=600):
        start = time.time()
        while time.time() - start < timeout:
            r = requests.get(f'{self.base_url}/jobs/{job_id}')
            result = r.json().get('result')
            if result and result['status'] in ['success', 'failed']:
                return result
            time.sleep(5)
        raise TimeoutError('Job did not complete')

# Usage
client = ProvisioningClient('http://localhost:5000/api')

# Install Nginx
job_id = client.install_app('nginx', 'agent-001', {
    'server_name': 'example.com',
    'admin_email': 'admin@example.com'
})

result = client.wait_for_job(job_id)
print(f"Status: {result['status']}")
print(f"Output: {result['output']}")
```
