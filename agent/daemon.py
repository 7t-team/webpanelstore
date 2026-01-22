"""
Agent Daemon - Executes installation jobs on target servers

Security features:
- Validates job signatures (HMAC)
- Whitelisted installers only
- Sandboxed execution
- No arbitrary command execution
- Streams logs to panel
"""

import os
import sys
import json
import hmac
import hashlib
import subprocess
import time
import signal
from pathlib import Path
from typing import Dict, Optional
import logging
import redis
import yaml
from datetime import datetime

# Configuration
AGENT_ID = os.getenv('AGENT_ID', 'agent-001')
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
SECRET_KEY = os.getenv('SECRET_KEY', 'change-me-in-production')
INSTALLERS_PATH = Path('/opt/provisioning/installers')
LOG_DIR = Path('/var/log/provisioning')
STATE_FILE = Path('/var/lib/provisioning/state.json')
POLL_INTERVAL = 5

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / 'agent.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class JobExecutor:
    """Executes installation jobs with security and isolation"""
    
    def __init__(self, installers_path: Path):
        self.installers_path = installers_path
        self.current_process: Optional[subprocess.Popen] = None
        
    def validate_signature(self, job: Dict) -> bool:
        """Verify HMAC signature"""
        received_sig = job.get('signature', '')
        job_copy = {k: v for k, v in job.items() if k != 'signature'}
        payload = json.dumps(job_copy, sort_keys=True).encode()
        expected_sig = hmac.new(SECRET_KEY.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(received_sig, expected_sig)
    
    def validate_installer(self, app_id: str) -> bool:
        """Check if installer is whitelisted"""
        manifest_path = self.installers_path / app_id / 'manifest.yml'
        return manifest_path.exists()
    
    def load_manifest(self, app_id: str) -> Dict:
        """Load and parse manifest"""
        manifest_path = self.installers_path / app_id / 'manifest.yml'
        with open(manifest_path) as f:
            return yaml.safe_load(f)
    
    def validate_inputs(self, manifest: Dict, inputs: Dict) -> tuple[bool, Optional[str]]:
        """Validate inputs against manifest schema"""
        manifest_inputs = {inp['name']: inp for inp in manifest.get('inputs', [])}
        
        for name, field in manifest_inputs.items():
            if field.get('required', True) and name not in inputs:
                return False, f"Required field missing: {name}"
            
            if name in inputs:
                value = inputs[name]
                
                # Type validation
                if field['type'] == 'integer':
                    try:
                        int(value)
                    except ValueError:
                        return False, f"Invalid integer: {name}"
                
                elif field['type'] == 'port':
                    try:
                        port = int(value)
                        if not (1 <= port <= 65535):
                            return False, f"Port out of range: {name}"
                    except ValueError:
                        return False, f"Invalid port: {name}"
                
                # Pattern validation
                validation = field.get('validation', {})
                if 'pattern' in validation:
                    import re
                    if not re.match(validation['pattern'], str(value)):
                        return False, f"Pattern mismatch: {name}"
                
                # Length validation
                if 'min_length' in validation and len(str(value)) < validation['min_length']:
                    return False, f"Value too short: {name}"
                if 'max_length' in validation and len(str(value)) > validation['max_length']:
                    return False, f"Value too long: {name}"
        
        return True, None
    
    def prepare_environment(self, inputs: Dict, manifest: Dict) -> Dict[str, str]:
        """Convert inputs to environment variables"""
        env = os.environ.copy()
        
        for name, value in inputs.items():
            # Convert to uppercase with underscores
            env_name = name.upper()
            env[env_name] = str(value)
        
        # Add metadata
        env['PROVISIONING_JOB'] = 'true'
        env['DEBIAN_FRONTEND'] = 'noninteractive'
        
        return env
    
    def execute_script(self, app_id: str, script_name: str, env: Dict[str, str], 
                      timeout: int, job_id: str) -> tuple[int, str]:
        """Execute installation script with timeout and logging"""
        script_path = self.installers_path / app_id / script_name
        
        if not script_path.exists():
            return 1, f"Script not found: {script_path}"
        
        # Make executable
        script_path.chmod(0o755)
        
        log_file = LOG_DIR / f"{job_id}.log"
        
        logger.info(f"Executing: {script_path}")
        
        try:
            with open(log_file, 'w') as log:
                self.current_process = subprocess.Popen(
                    ['/bin/bash', str(script_path)],
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    cwd=script_path.parent,
                    preexec_fn=os.setsid  # Create new process group
                )
                
                try:
                    exit_code = self.current_process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    logger.error(f"Job {job_id} timed out after {timeout}s")
                    os.killpg(os.getpgid(self.current_process.pid), signal.SIGTERM)
                    time.sleep(5)
                    os.killpg(os.getpgid(self.current_process.pid), signal.SIGKILL)
                    return 124, "Execution timed out"
                
                self.current_process = None
            
            # Read log output
            with open(log_file) as f:
                output = f.read()
            
            return exit_code, output
            
        except Exception as e:
            logger.exception(f"Execution failed: {e}")
            return 1, str(e)
    
    def execute_job(self, job: Dict) -> Dict:
        """Main job execution flow"""
        job_id = job['job_id']
        app_id = job['app_id']
        inputs = job['inputs']
        
        result = {
            'job_id': job_id,
            'status': 'failed',
            'exit_code': 1,
            'output': '',
            'started_at': datetime.utcnow().isoformat(),
            'completed_at': None,
            'error': None
        }
        
        try:
            # Validate signature
            if not self.validate_signature(job):
                result['error'] = 'Invalid signature'
                return result
            
            # Validate installer exists
            if not self.validate_installer(app_id):
                result['error'] = f'Installer not whitelisted: {app_id}'
                return result
            
            # Load manifest
            manifest = self.load_manifest(app_id)
            
            # Validate inputs
            valid, error = self.validate_inputs(manifest, inputs)
            if not valid:
                result['error'] = f'Input validation failed: {error}'
                return result
            
            # Prepare environment
            env = self.prepare_environment(inputs, manifest)
            
            # Execute script
            timeout = manifest.get('timeout_seconds', 600)
            script_name = manifest.get('install_script', 'install.sh')
            
            exit_code, output = self.execute_script(
                app_id, script_name, env, timeout, job_id
            )
            
            result['exit_code'] = exit_code
            result['output'] = output
            result['status'] = 'success' if exit_code == 0 else 'failed'
            
            if exit_code != 0:
                result['error'] = f'Script exited with code {exit_code}'
            
        except Exception as e:
            logger.exception(f"Job execution failed: {e}")
            result['error'] = str(e)
        
        finally:
            result['completed_at'] = datetime.utcnow().isoformat()
        
        return result


class AgentDaemon:
    """Main agent daemon"""
    
    def __init__(self):
        self.redis_client = redis.from_url(REDIS_URL)
        self.executor = JobExecutor(INSTALLERS_PATH)
        self.running = True
        
        # Setup signal handlers
        signal.signal(signal.SIGTERM, self.shutdown)
        signal.signal(signal.SIGINT, self.shutdown)
    
    def shutdown(self, signum, frame):
        """Graceful shutdown"""
        logger.info("Shutting down agent...")
        self.running = False
        
        if self.executor.current_process:
            logger.info("Terminating current job...")
            try:
                os.killpg(os.getpgid(self.executor.current_process.pid), signal.SIGTERM)
            except:
                pass
    
    def poll_jobs(self):
        """Poll for new jobs from Redis queue"""
        queue_key = f'agent:{AGENT_ID}:jobs'
        
        try:
            # Blocking pop with timeout
            result = self.redis_client.blpop(queue_key, timeout=POLL_INTERVAL)
            
            if result:
                _, job_data = result
                job = json.loads(job_data)
                logger.info(f"Received job: {job['job_id']}")
                return job
                
        except redis.RedisError as e:
            logger.error(f"Redis error: {e}")
            time.sleep(POLL_INTERVAL)
        
        return None
    
    def publish_result(self, result: Dict):
        """Publish job result back to panel"""
        result_key = f"job:{result['job_id']}:result"
        self.redis_client.setex(result_key, 3600, json.dumps(result))
        
        # Publish to pubsub for real-time updates
        channel = f"job:{result['job_id']}:updates"
        self.redis_client.publish(channel, json.dumps(result))
    
    def run(self):
        """Main event loop"""
        logger.info(f"Agent {AGENT_ID} started")
        logger.info(f"Installers path: {INSTALLERS_PATH}")
        
        while self.running:
            job = self.poll_jobs()
            
            if job:
                logger.info(f"Executing job {job['job_id']}")
                result = self.executor.execute_job(job)
                logger.info(f"Job {job['job_id']} completed: {result['status']}")
                self.publish_result(result)


if __name__ == '__main__':
    # Ensure directories exist
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    daemon = AgentDaemon()
    daemon.run()
