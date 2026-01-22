"""
Integration tests for the provisioning platform
"""

import pytest
import json
import yaml
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from panel.app import ManifestRegistry, InputValidator, JobManager
from shared.schema import AppManifest, InputField


class TestManifestRegistry:
    """Test manifest loading and validation"""
    
    def test_load_nginx_manifest(self):
        installers_path = Path(__file__).parent.parent / 'installers'
        registry = ManifestRegistry(installers_path)
        
        nginx = registry.get('nginx')
        assert nginx is not None
        assert nginx['id'] == 'nginx'
        assert nginx['name'] == 'Nginx Web Server'
        assert len(nginx['inputs']) > 0
    
    def test_search_by_category(self):
        installers_path = Path(__file__).parent.parent / 'installers'
        registry = ManifestRegistry(installers_path)
        
        web_servers = registry.search(category='web-servers')
        assert len(web_servers) > 0
        assert any(app['id'] == 'nginx' for app in web_servers)
    
    def test_search_by_tags(self):
        installers_path = Path(__file__).parent.parent / 'installers'
        registry = ManifestRegistry(installers_path)
        
        databases = registry.search(tags=['database'])
        assert len(databases) > 0


class TestInputValidator:
    """Test input validation logic"""
    
    def test_validate_required_field(self):
        field = {
            'name': 'server_name',
            'type': 'string',
            'label': 'Server Name',
            'required': True
        }
        
        valid, error = InputValidator.validate_field(field, '')
        assert not valid
        assert 'required' in error.lower()
        
        valid, error = InputValidator.validate_field(field, 'example.com')
        assert valid
    
    def test_validate_pattern(self):
        field = {
            'name': 'domain',
            'type': 'string',
            'label': 'Domain',
            'required': True,
            'validation': {
                'pattern': '^[a-z0-9\-\.]+$'
            }
        }
        
        valid, error = InputValidator.validate_field(field, 'example.com')
        assert valid
        
        valid, error = InputValidator.validate_field(field, 'INVALID_DOMAIN!')
        assert not valid
    
    def test_validate_port(self):
        field = {
            'name': 'port',
            'type': 'port',
            'label': 'Port',
            'required': True
        }
        
        valid, error = InputValidator.validate_field(field, '80')
        assert valid
        
        valid, error = InputValidator.validate_field(field, '99999')
        assert not valid
        
        valid, error = InputValidator.validate_field(field, 'not-a-port')
        assert not valid
    
    def test_validate_email(self):
        field = {
            'name': 'email',
            'type': 'email',
            'label': 'Email',
            'required': True
        }
        
        valid, error = InputValidator.validate_field(field, 'user@example.com')
        assert valid
        
        valid, error = InputValidator.validate_field(field, 'invalid-email')
        assert not valid
    
    def test_validate_integer(self):
        field = {
            'name': 'count',
            'type': 'integer',
            'label': 'Count',
            'required': True,
            'validation': {
                'min_value': 1,
                'max_value': 100
            }
        }
        
        valid, error = InputValidator.validate_field(field, '50')
        assert valid
        
        valid, error = InputValidator.validate_field(field, '0')
        assert not valid
        
        valid, error = InputValidator.validate_field(field, '200')
        assert not valid
    
    def test_validate_select(self):
        field = {
            'name': 'mode',
            'type': 'select',
            'label': 'Mode',
            'required': True,
            'validation': {
                'allowed_values': ['dev', 'staging', 'production']
            }
        }
        
        valid, error = InputValidator.validate_field(field, 'production')
        assert valid
        
        valid, error = InputValidator.validate_field(field, 'invalid')
        assert not valid
    
    def test_validate_password_length(self):
        field = {
            'name': 'password',
            'type': 'password',
            'label': 'Password',
            'required': True,
            'validation': {
                'min_length': 12,
                'max_length': 64
            }
        }
        
        valid, error = InputValidator.validate_field(field, 'short')
        assert not valid
        
        valid, error = InputValidator.validate_field(field, 'ValidPassword123!')
        assert valid


class TestManifestSchema:
    """Test Pydantic schema validation"""
    
    def test_valid_manifest(self):
        manifest_data = {
            'id': 'test-app',
            'name': 'Test Application',
            'version': '1.0.0',
            'description': 'Test description',
            'category': 'testing',
            'author': 'Test Author',
            'os_requirements': {
                'family': ['ubuntu']
            },
            'install_script': 'install.sh',
            'timeout_seconds': 600,
            'idempotent': True,
            'tags': ['test']
        }
        
        from shared.schema import AppManifest
        manifest = AppManifest(**manifest_data)
        assert manifest.id == 'test-app'
    
    def test_invalid_app_id(self):
        manifest_data = {
            'id': 'Invalid_ID!',  # Invalid characters
            'name': 'Test',
            'version': '1.0.0',
            'description': 'Test',
            'category': 'test',
            'author': 'Test',
            'os_requirements': {'family': ['ubuntu']},
            'install_script': 'install.sh',
            'timeout_seconds': 600,
            'idempotent': True
        }
        
        from shared.schema import AppManifest
        from pydantic import ValidationError
        
        with pytest.raises(ValidationError):
            AppManifest(**manifest_data)


class TestJobSecurity:
    """Test job signature and security"""
    
    def test_signature_generation(self):
        import hmac
        import hashlib
        
        secret = 'test-secret'
        job = {
            'job_id': '123',
            'app_id': 'nginx',
            'inputs': {'server_name': 'example.com'}
        }
        
        payload = json.dumps(job, sort_keys=True).encode()
        signature = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        
        assert len(signature) == 64  # SHA256 hex digest
    
    def test_signature_verification(self):
        import hmac
        
        secret = 'test-secret'
        job = {
            'job_id': '123',
            'app_id': 'nginx',
            'inputs': {}
        }
        
        payload = json.dumps(job, sort_keys=True).encode()
        signature1 = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        signature2 = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        
        # Same input should produce same signature
        assert hmac.compare_digest(signature1, signature2)
        
        # Different input should produce different signature
        job['app_id'] = 'mysql'
        payload2 = json.dumps(job, sort_keys=True).encode()
        signature3 = hmac.new(secret.encode(), payload2, hashlib.sha256).hexdigest()
        
        assert not hmac.compare_digest(signature1, signature3)


class TestConditionalInputs:
    """Test conditional input visibility"""
    
    def test_visible_if_condition(self):
        manifest = {
            'inputs': [
                {
                    'name': 'enable_ssl',
                    'type': 'boolean',
                    'label': 'Enable SSL',
                    'required': False,
                    'default': 'false'
                },
                {
                    'name': 'ssl_port',
                    'type': 'port',
                    'label': 'SSL Port',
                    'required': True,
                    'visible_if': {
                        'enable_ssl': 'true'
                    }
                }
            ]
        }
        
        # SSL disabled - ssl_port not required
        inputs = {'enable_ssl': 'false'}
        valid, errors = InputValidator.validate_inputs(manifest, inputs)
        assert valid
        
        # SSL enabled - ssl_port required
        inputs = {'enable_ssl': 'true'}
        valid, errors = InputValidator.validate_inputs(manifest, inputs)
        assert not valid  # ssl_port missing
        
        # SSL enabled with port
        inputs = {'enable_ssl': 'true', 'ssl_port': '443'}
        valid, errors = InputValidator.validate_inputs(manifest, inputs)
        assert valid


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
