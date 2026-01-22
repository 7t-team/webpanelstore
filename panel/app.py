"""
Web Panel - Manages applications and generates dynamic forms

Features:
- Reads manifests from installer repository
- Generates forms dynamically based on manifest inputs
- Validates user input before job creation
- Manages job queue
- Provides WebSocket for real-time log streaming
"""

from flask import Flask, request, jsonify, render_template_string, session
from flask_cors import CORS
import redis
import yaml
import json
import hmac
import hashlib
import uuid
import os
from pathlib import Path
from typing import Dict, List, Optional
import re
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'change-me-in-production')
CORS(app)

# Configuration
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
SECRET_KEY = os.getenv('SECRET_KEY', 'change-me-in-production')
INSTALLERS_PATH = Path(__file__).parent.parent / 'installers'
ADMIN_USER = os.getenv('ADMIN_USER', 'admin')
ADMIN_PASS = os.getenv('ADMIN_PASS', 'admin123')

redis_client = redis.from_url(REDIS_URL)

# Authentication
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

ADMIN_PASS_HASH = hash_password(ADMIN_PASS)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return jsonify({'success': False, 'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function


class ManifestRegistry:
    """Loads and manages application manifests"""
    
    def __init__(self, installers_path: Path):
        self.installers_path = installers_path
        self.manifests: Dict[str, Dict] = {}
        self.load_all()
    
    def load_all(self):
        """Load all manifests from installers directory"""
        if not self.installers_path.exists():
            return
        
        for app_dir in self.installers_path.iterdir():
            if app_dir.is_dir():
                manifest_file = app_dir / 'manifest.yml'
                if manifest_file.exists():
                    try:
                        with open(manifest_file) as f:
                            manifest = yaml.safe_load(f)
                            self.manifests[manifest['id']] = manifest
                    except Exception as e:
                        print(f"Failed to load {manifest_file}: {e}")
    
    def get(self, app_id: str) -> Optional[Dict]:
        """Get manifest by app ID"""
        return self.manifests.get(app_id)
    
    def list_all(self) -> List[Dict]:
        """List all available applications"""
        return list(self.manifests.values())
    
    def search(self, query: str = None, category: str = None, tags: List[str] = None) -> List[Dict]:
        """Search applications"""
        results = self.list_all()
        
        if query:
            query = query.lower()
            results = [m for m in results if 
                      query in m['name'].lower() or 
                      query in m['description'].lower()]
        
        if category:
            results = [m for m in results if m.get('category') == category]
        
        if tags:
            results = [m for m in results if 
                      any(tag in m.get('tags', []) for tag in tags)]
        
        return results


class InputValidator:
    """Validates user inputs against manifest schema"""
    
    @staticmethod
    def validate_field(field: Dict, value: str) -> tuple[bool, Optional[str]]:
        """Validate a single field"""
        field_name = field['name']
        field_type = field['type']
        
        # Required check
        if field.get('required', True) and not value:
            return False, f"{field['label']} is required"
        
        if not value:
            return True, None
        
        # Type validation
        if field_type == 'integer':
            try:
                int_val = int(value)
            except ValueError:
                return False, f"{field['label']} must be an integer"
        
        elif field_type == 'port':
            try:
                port = int(value)
                if not (1 <= port <= 65535):
                    return False, f"{field['label']} must be between 1 and 65535"
            except ValueError:
                return False, f"{field['label']} must be a valid port number"
        
        elif field_type == 'email':
            if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', value):
                return False, f"{field['label']} must be a valid email"
        
        elif field_type == 'boolean':
            if value.lower() not in ['true', 'false', '1', '0', 'yes', 'no']:
                return False, f"{field['label']} must be true or false"
        
        # Validation rules
        validation = field.get('validation', {})
        
        if 'pattern' in validation:
            if not re.match(validation['pattern'], value):
                return False, f"{field['label']} format is invalid"
        
        if 'min_length' in validation and len(value) < validation['min_length']:
            return False, f"{field['label']} must be at least {validation['min_length']} characters"
        
        if 'max_length' in validation and len(value) > validation['max_length']:
            return False, f"{field['label']} must be at most {validation['max_length']} characters"
        
        if 'min_value' in validation:
            try:
                if float(value) < validation['min_value']:
                    return False, f"{field['label']} must be at least {validation['min_value']}"
            except ValueError:
                pass
        
        if 'max_value' in validation:
            try:
                if float(value) > validation['max_value']:
                    return False, f"{field['label']} must be at most {validation['max_value']}"
            except ValueError:
                pass
        
        if 'allowed_values' in validation:
            if value not in validation['allowed_values']:
                return False, f"{field['label']} must be one of: {', '.join(validation['allowed_values'])}"
        
        return True, None
    
    @staticmethod
    def validate_inputs(manifest: Dict, inputs: Dict) -> tuple[bool, List[str]]:
        """Validate all inputs"""
        errors = []
        
        for field in manifest.get('inputs', []):
            # Check conditional visibility
            visible_if = field.get('visible_if')
            if visible_if:
                condition_met = all(
                    inputs.get(k) == v for k, v in visible_if.items()
                )
                if not condition_met:
                    continue
            
            value = inputs.get(field['name'], '')
            valid, error = InputValidator.validate_field(field, value)
            
            if not valid:
                errors.append(error)
        
        return len(errors) == 0, errors


class InstalledAppsManager:
    """Manages installed applications"""
    
    def __init__(self, redis_client):
        self.redis = redis_client
    
    def mark_installed(self, app_id: str, server_id: str, job_id: str, inputs: Dict):
        """Mark app as installed"""
        key = f'installed:{server_id}:{app_id}'
        data = {
            'app_id': app_id,
            'server_id': server_id,
            'job_id': job_id,
            'inputs': inputs,
            'installed_at': datetime.utcnow().isoformat()
        }
        self.redis.set(key, json.dumps(data))
    
    def list_installed(self, server_id: str) -> List[Dict]:
        """List installed apps on server"""
        apps = []
        for key in self.redis.scan_iter(f'installed:{server_id}:*'):
            data = self.redis.get(key)
            if data:
                apps.append(json.loads(data))
        return apps
    
    def uninstall(self, app_id: str, server_id: str) -> bool:
        """Remove installed app record"""
        key = f'installed:{server_id}:{app_id}'
        return self.redis.delete(key) > 0


class JobManager:
    """Manages installation jobs"""
    
    def __init__(self, redis_client):
        self.redis = redis_client
    
    def create_job(self, app_id: str, inputs: Dict, server_id: str, user_id: str) -> str:
        """Create and queue a new job"""
        job_id = str(uuid.uuid4())
        
        job = {
            'job_id': job_id,
            'app_id': app_id,
            'inputs': inputs,
            'server_id': server_id,
            'user_id': user_id,
            'created_at': datetime.utcnow().isoformat(),
            'status': 'queued'
        }
        
        # Sign the job
        job_copy = {k: v for k, v in job.items() if k != 'signature'}
        payload = json.dumps(job_copy, sort_keys=True).encode()
        signature = hmac.new(SECRET_KEY.encode(), payload, hashlib.sha256).hexdigest()
        job['signature'] = signature
        
        # Store job metadata
        job_key = f'job:{job_id}'
        self.redis.setex(job_key, 86400, json.dumps(job))
        
        # Queue for agent
        queue_key = f'agent:{server_id}:jobs'
        self.redis.rpush(queue_key, json.dumps(job))
        
        return job_id
    
    def get_job(self, job_id: str) -> Optional[Dict]:
        """Get job details"""
        job_key = f'job:{job_id}'
        data = self.redis.get(job_key)
        return json.loads(data) if data else None
    
    def get_job_result(self, job_id: str) -> Optional[Dict]:
        """Get job execution result"""
        result_key = f'job:{job_id}:result'
        data = self.redis.get(result_key)
        return json.loads(data) if data else None
    
    def list_jobs(self, user_id: str = None, server_id: str = None) -> List[Dict]:
        """List jobs with optional filters"""
        # In production, use a proper database
        # This is a simplified implementation
        jobs = []
        for key in self.redis.scan_iter('job:*'):
            if b':result' not in key:
                data = self.redis.get(key)
                if data:
                    job = json.loads(data)
                    if user_id and job.get('user_id') != user_id:
                        continue
                    if server_id and job.get('server_id') != server_id:
                        continue
                    jobs.append(job)
        return jobs


# Initialize components
registry = ManifestRegistry(INSTALLERS_PATH)
job_manager = JobManager(redis_client)
installed_apps = InstalledAppsManager(redis_client)


# API Routes

@app.route('/api/login', methods=['POST'])
def login():
    """Login endpoint"""
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    if username == ADMIN_USER and hash_password(password) == ADMIN_PASS_HASH:
        session['user'] = username
        return jsonify({'success': True, 'message': 'Logged in successfully'})
    
    return jsonify({'success': False, 'error': 'Invalid credentials'}), 401

@app.route('/api/logout', methods=['POST'])
def logout():
    """Logout endpoint"""
    session.pop('user', None)
    return jsonify({'success': True, 'message': 'Logged out successfully'})

@app.route('/api/apps', methods=['GET'])
@login_required
def list_apps():
    """List all available applications"""
    query = request.args.get('q')
    category = request.args.get('category')
    tags = request.args.getlist('tags')
    
    apps = registry.search(query=query, category=category, tags=tags)
    
    return jsonify({
        'success': True,
        'count': len(apps),
        'apps': apps
    })


@app.route('/api/apps/<app_id>', methods=['GET'])
@login_required
def get_app(app_id):
    """Get application details and manifest"""
    manifest = registry.get(app_id)
    
    if not manifest:
        return jsonify({'success': False, 'error': 'Application not found'}), 404
    
    return jsonify({
        'success': True,
        'app': manifest
    })


@app.route('/api/apps/<app_id>/install', methods=['POST'])
@login_required
def install_app(app_id):
    """Install application on a server"""
    data = request.json
    
    # Get manifest
    manifest = registry.get(app_id)
    if not manifest:
        return jsonify({'success': False, 'error': 'Application not found'}), 404
    
    # Extract data
    inputs = data.get('inputs', {})
    server_id = data.get('server_id')
    user_id = data.get('user_id', 'anonymous')
    
    if not server_id:
        return jsonify({'success': False, 'error': 'server_id is required'}), 400
    
    # Validate inputs
    valid, errors = InputValidator.validate_inputs(manifest, inputs)
    if not valid:
        return jsonify({
            'success': False,
            'error': 'Input validation failed',
            'errors': errors
        }), 400
    
    # Create job
    job_id = job_manager.create_job(app_id, inputs, server_id, user_id)
    
    # Mark as installed
    installed_apps.mark_installed(app_id, server_id, job_id, inputs)
    
    return jsonify({
        'success': True,
        'job_id': job_id,
        'message': 'Installation job created'
    }), 201


@app.route('/api/installed', methods=['GET'])
@login_required
def list_installed():
    """List installed applications"""
    server_id = request.args.get('server_id', 'agent-001')
    apps = installed_apps.list_installed(server_id)
    
    # Enrich with manifest data
    for app in apps:
        manifest = registry.get(app['app_id'])
        if manifest:
            app['name'] = manifest['name']
            app['description'] = manifest['description']
            app['category'] = manifest['category']
    
    return jsonify({
        'success': True,
        'count': len(apps),
        'apps': apps
    })

@app.route('/api/installed/<app_id>', methods=['DELETE'])
@login_required
def uninstall_app(app_id):
    """Uninstall application"""
    server_id = request.args.get('server_id', 'agent-001')
    
    if installed_apps.uninstall(app_id, server_id):
        return jsonify({
            'success': True,
            'message': f'Application {app_id} uninstalled'
        })
    
    return jsonify({
        'success': False,
        'error': 'Application not found'
    }), 404

@app.route('/api/logs/<job_id>', methods=['GET'])
@login_required
def get_logs(job_id):
    """Get installation logs"""
    log_file = Path(f'/var/log/provisioning/{job_id}.log')
    
    if not log_file.exists():
        return jsonify({
            'success': False,
            'error': 'Log file not found'
        }), 404
    
    try:
        with open(log_file, 'r') as f:
            logs = f.read()
        
        return jsonify({
            'success': True,
            'logs': logs
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/jobs/<job_id>', methods=['GET'])
@login_required
def get_job(job_id):
    """Get job status and result"""
    job = job_manager.get_job(job_id)
    
    if not job:
        return jsonify({'success': False, 'error': 'Job not found'}), 404
    
    result = job_manager.get_job_result(job_id)
    
    return jsonify({
        'success': True,
        'job': job,
        'result': result
    })


@app.route('/api/jobs', methods=['GET'])
@login_required
def list_jobs():
    """List jobs"""
    user_id = request.args.get('user_id')
    server_id = request.args.get('server_id')
    
    jobs = job_manager.list_jobs(user_id=user_id, server_id=server_id)
    
    return jsonify({
        'success': True,
        'count': len(jobs),
        'jobs': jobs
    })


@app.route('/api/health', methods=['GET'])
def health():
    """Health check"""
    return jsonify({
        'success': True,
        'status': 'healthy',
        'apps_loaded': len(registry.manifests)
    })


@app.route('/')
def index():
    """Enhanced web UI with authentication and installed apps management"""
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Server Provisioning Platform</title>
        <meta charset="UTF-8">
        <style>
            * { box-sizing: border-box; margin: 0; padding: 0; }
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f5f5f5; }
            .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
            .header { background: #2c3e50; color: white; padding: 20px; margin: -20px -20px 20px -20px; }
            .header h1 { margin: 0; }
            .header .user-info { float: right; }
            .tabs { display: flex; gap: 10px; margin-bottom: 20px; border-bottom: 2px solid #ddd; }
            .tab { padding: 10px 20px; cursor: pointer; background: white; border: none; border-bottom: 3px solid transparent; }
            .tab.active { border-bottom-color: #007bff; color: #007bff; font-weight: bold; }
            .tab-content { display: none; }
            .tab-content.active { display: block; }
            .app-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 20px; }
            .app-card { background: white; border: 1px solid #ddd; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            .app-card h3 { margin: 0 0 10px 0; color: #2c3e50; }
            .app-card p { color: #666; margin: 5px 0; font-size: 14px; }
            .app-card .category { display: inline-block; background: #e3f2fd; color: #1976d2; padding: 4px 8px; border-radius: 4px; font-size: 12px; margin-top: 10px; }
            .app-card .installed-badge { background: #4caf50; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px; margin-left: 10px; }
            button { background: #007bff; color: white; border: none; padding: 10px 20px; cursor: pointer; border-radius: 4px; font-size: 14px; }
            button:hover { background: #0056b3; }
            button.danger { background: #dc3545; }
            button.danger:hover { background: #c82333; }
            button.secondary { background: #6c757d; }
            button.secondary:hover { background: #5a6268; }
            .form-group { margin: 15px 0; }
            label { display: block; margin-bottom: 5px; font-weight: bold; color: #333; }
            input, select, textarea { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; }
            .error { color: #dc3545; background: #f8d7da; padding: 10px; border-radius: 4px; margin: 10px 0; }
            .success { color: #155724; background: #d4edda; padding: 10px; border-radius: 4px; margin: 10px 0; }
            .login-form { max-width: 400px; margin: 100px auto; background: white; padding: 40px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
            .login-form h2 { margin-bottom: 20px; color: #2c3e50; text-align: center; }
            .search-box { width: 100%; padding: 12px; border: 1px solid #ddd; border-radius: 4px; margin-bottom: 20px; font-size: 14px; }
            .log-viewer { background: #1e1e1e; color: #d4d4d4; padding: 20px; border-radius: 4px; font-family: 'Courier New', monospace; font-size: 12px; max-height: 500px; overflow-y: auto; white-space: pre-wrap; }
            .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); z-index: 1000; }
            .modal.active { display: flex; align-items: center; justify-content: center; }
            .modal-content { background: white; padding: 30px; border-radius: 8px; max-width: 800px; width: 90%; max-height: 90vh; overflow-y: auto; }
            .modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
            .modal-header h2 { margin: 0; }
            .close-btn { background: none; border: none; font-size: 24px; cursor: pointer; color: #999; }
            .close-btn:hover { color: #333; }
        </style>
    </head>
    <body>
        <div id="app"></div>
        
        <script>
            let currentUser = null;
            let installedApps = [];
            
            // Check if logged in
            async function checkAuth() {
                try {
                    const res = await fetch('/api/apps');
                    if (res.status === 401) {
                        showLogin();
                        return false;
                    }
                    return true;
                } catch (e) {
                    showLogin();
                    return false;
                }
            }
            
            // Show login form
            function showLogin() {
                document.getElementById('app').innerHTML = `
                    <div class="login-form">
                        <h2>تسجيل الدخول</h2>
                        <form id="loginForm">
                            <div class="form-group">
                                <label>اسم المستخدم</label>
                                <input type="text" name="username" required autofocus>
                            </div>
                            <div class="form-group">
                                <label>كلمة المرور</label>
                                <input type="password" name="password" required>
                            </div>
                            <button type="submit" style="width: 100%;">دخول</button>
                            <div id="loginError"></div>
                        </form>
                    </div>
                `;
                
                document.getElementById('loginForm').onsubmit = async (e) => {
                    e.preventDefault();
                    const formData = new FormData(e.target);
                    
                    const res = await fetch('/api/login', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({
                            username: formData.get('username'),
                            password: formData.get('password')
                        })
                    });
                    
                    const data = await res.json();
                    if (data.success) {
                        currentUser = formData.get('username');
                        showDashboard();
                    } else {
                        document.getElementById('loginError').innerHTML = '<div class="error">بيانات الدخول غير صحيحة</div>';
                    }
                };
            }
            
            // Show main dashboard
            async function showDashboard() {
                document.getElementById('app').innerHTML = `
                    <div class="container">
                        <div class="header">
                            <h1>لوحة تحكم التطبيقات</h1>
                            <div class="user-info">
                                <span>مرحباً ${currentUser}</span>
                                <button onclick="logout()" class="secondary" style="margin-left: 10px;">خروج</button>
                            </div>
                            <div style="clear: both;"></div>
                        </div>
                        
                        <div class="tabs">
                            <button class="tab active" onclick="switchTab('available')">التطبيقات المتاحة</button>
                            <button class="tab" onclick="switchTab('installed')">التطبيقات المثبتة</button>
                            <button class="tab" onclick="switchTab('jobs')">سجل التثبيت</button>
                        </div>
                        
                        <div id="available" class="tab-content active">
                            <input type="text" class="search-box" placeholder="ابحث عن تطبيق..." onkeyup="searchApps(this.value)">
                            <div id="apps-grid" class="app-grid"></div>
                        </div>
                        
                        <div id="installed" class="tab-content">
                            <div id="installed-grid" class="app-grid"></div>
                        </div>
                        
                        <div id="jobs" class="tab-content">
                            <div id="jobs-list"></div>
                        </div>
                    </div>
                    
                    <div id="modal" class="modal">
                        <div class="modal-content">
                            <div class="modal-header">
                                <h2 id="modal-title"></h2>
                                <button class="close-btn" onclick="closeModal()">&times;</button>
                            </div>
                            <div id="modal-body"></div>
                        </div>
                    </div>
                `;
                
                loadApps();
                loadInstalled();
            }
            
            // Switch tabs
            function switchTab(tab) {
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
                event.target.classList.add('active');
                document.getElementById(tab).classList.add('active');
                
                if (tab === 'installed') loadInstalled();
                if (tab === 'jobs') loadJobs();
            }
            
            // Load available apps
            let allApps = [];
            async function loadApps() {
                const res = await fetch('/api/apps');
                const data = await res.json();
                allApps = data.apps;
                displayApps(allApps);
            }
            
            function displayApps(apps) {
                const container = document.getElementById('apps-grid');
                container.innerHTML = apps.map(app => `
                    <div class="app-card">
                        <h3>${app.name}</h3>
                        <p>${app.description}</p>
                        <span class="category">${app.category}</span>
                        <div style="margin-top: 15px;">
                            <button onclick="showInstallForm('${app.id}')">تثبيت</button>
                        </div>
                    </div>
                `).join('');
            }
            
            function searchApps(query) {
                if (!query) {
                    displayApps(allApps);
                    return;
                }
                const filtered = allApps.filter(app => 
                    app.name.toLowerCase().includes(query.toLowerCase()) ||
                    app.description.toLowerCase().includes(query.toLowerCase())
                );
                displayApps(filtered);
            }
            
            // Load installed apps
            async function loadInstalled() {
                const res = await fetch('/api/installed?server_id=agent-001');
                const data = await res.json();
                installedApps = data.apps;
                
                const container = document.getElementById('installed-grid');
                if (installedApps.length === 0) {
                    container.innerHTML = '<p style="text-align: center; color: #999; padding: 40px;">لا توجد تطبيقات مثبتة</p>';
                    return;
                }
                
                container.innerHTML = installedApps.map(app => `
                    <div class="app-card">
                        <h3>${app.name || app.app_id}</h3>
                        <p>${app.description || ''}</p>
                        <span class="category">${app.category || ''}</span>
                        <span class="installed-badge">مثبت</span>
                        <p style="font-size: 12px; color: #999; margin-top: 10px;">تاريخ التثبيت: ${new Date(app.installed_at).toLocaleString('ar')}</p>
                        <div style="margin-top: 15px; display: flex; gap: 10px;">
                            <button onclick="viewLogs('${app.job_id}')">عرض اللوجات</button>
                            <button class="danger" onclick="confirmUninstall('${app.app_id}')">حذف</button>
                        </div>
                    </div>
                `).join('');
            }
            
            // Show install form
            async function showInstallForm(appId) {
                const res = await fetch('/api/apps/' + appId);
                const data = await res.json();
                const app = data.app;
                
                const form = app.inputs.map(input => `
                    <div class="form-group">
                        <label>${input.label}${input.required ? ' *' : ''}</label>
                        ${input.description ? '<small style="color: #666;">' + input.description + '</small>' : ''}
                        ${generateInput(input)}
                    </div>
                `).join('');
                
                document.getElementById('modal-title').textContent = 'تثبيت ' + app.name;
                document.getElementById('modal-body').innerHTML = `
                    <form id="installForm">
                        ${form}
                        <div style="margin-top: 20px; display: flex; gap: 10px;">
                            <button type="submit">تثبيت الآن</button>
                            <button type="button" class="secondary" onclick="closeModal()">إلغاء</button>
                        </div>
                        <div id="install-result"></div>
                    </form>
                `;
                
                document.getElementById('modal').classList.add('active');
                
                document.getElementById('installForm').onsubmit = async (e) => {
                    e.preventDefault();
                    const formData = new FormData(e.target);
                    const inputs = {};
                    for (let [key, value] of formData.entries()) {
                        inputs[key] = value;
                    }
                    
                    const res = await fetch('/api/apps/' + appId + '/install', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({
                            server_id: 'agent-001',
                            user_id: currentUser,
                            inputs: inputs
                        })
                    });
                    
                    const result = await res.json();
                    const resultDiv = document.getElementById('install-result');
                    
                    if (result.success) {
                        resultDiv.innerHTML = '<div class="success">تم إنشاء مهمة التثبيت بنجاح! رقم المهمة: ' + result.job_id + '</div>';
                        setTimeout(() => {
                            closeModal();
                            loadInstalled();
                        }, 2000);
                    } else {
                        resultDiv.innerHTML = '<div class="error">خطأ: ' + (result.errors || [result.error]).join(', ') + '</div>';
                    }
                };
            }
            
            function generateInput(input) {
                if (input.type === 'select') {
                    const options = input.validation.allowed_values.map(v => 
                        `<option value="${v}" ${v === input.default ? 'selected' : ''}>${v}</option>`
                    ).join('');
                    return `<select name="${input.name}">${options}</select>`;
                } else if (input.type === 'boolean') {
                    return `<select name="${input.name}">
                        <option value="true" ${input.default === 'true' ? 'selected' : ''}>نعم</option>
                        <option value="false" ${input.default === 'false' ? 'selected' : ''}>لا</option>
                    </select>`;
                } else if (input.type === 'password') {
                    return `<input type="password" name="${input.name}" ${input.required ? 'required' : ''}>`;
                } else {
                    return `<input type="text" name="${input.name}" value="${input.default || ''}" ${input.required ? 'required' : ''}>`;
                }
            }
            
            // View logs
            async function viewLogs(jobId) {
                const res = await fetch('/api/logs/' + jobId);
                const data = await res.json();
                
                document.getElementById('modal-title').textContent = 'سجل التثبيت';
                
                if (data.success) {
                    document.getElementById('modal-body').innerHTML = `
                        <div class="log-viewer">${data.logs || 'لا توجد سجلات'}</div>
                        <div style="margin-top: 20px;">
                            <button class="secondary" onclick="closeModal()">إغلاق</button>
                        </div>
                    `;
                } else {
                    document.getElementById('modal-body').innerHTML = `
                        <div class="error">${data.error}</div>
                        <div style="margin-top: 20px;">
                            <button class="secondary" onclick="closeModal()">إغلاق</button>
                        </div>
                    `;
                }
                
                document.getElementById('modal').classList.add('active');
            }
            
            // Confirm uninstall
            function confirmUninstall(appId) {
                if (confirm('هل أنت متأكد من حذف هذا التطبيق؟')) {
                    uninstallApp(appId);
                }
            }
            
            // Uninstall app
            async function uninstallApp(appId) {
                const res = await fetch('/api/installed/' + appId + '?server_id=agent-001', {
                    method: 'DELETE'
                });
                
                const data = await res.json();
                if (data.success) {
                    alert('تم حذف التطبيق بنجاح');
                    loadInstalled();
                } else {
                    alert('فشل حذف التطبيق: ' + data.error);
                }
            }
            
            // Load jobs
            async function loadJobs() {
                const res = await fetch('/api/jobs');
                const data = await res.json();
                
                const container = document.getElementById('jobs-list');
                if (data.jobs.length === 0) {
                    container.innerHTML = '<p style="text-align: center; color: #999; padding: 40px;">لا توجد مهام</p>';
                    return;
                }
                
                container.innerHTML = data.jobs.map(job => `
                    <div class="app-card">
                        <h3>${job.app_id}</h3>
                        <p>رقم المهمة: ${job.job_id}</p>
                        <p>الحالة: ${job.status}</p>
                        <p>تاريخ الإنشاء: ${new Date(job.created_at).toLocaleString('ar')}</p>
                        <div style="margin-top: 15px;">
                            <button onclick="viewLogs('${job.job_id}')">عرض اللوجات</button>
                        </div>
                    </div>
                `).join('');
            }
            
            // Close modal
            function closeModal() {
                document.getElementById('modal').classList.remove('active');
            }
            
            // Logout
            async function logout() {
                await fetch('/api/logout', { method: 'POST' });
                currentUser = null;
                showLogin();
            }
            
            // Initialize
            checkAuth().then(loggedIn => {
                if (loggedIn) showDashboard();
            });
        </script>
    </body>
    </html>
    ''')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
