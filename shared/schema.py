"""
Manifest Schema Specification v1.0

Defines the contract for application installers.
All installers MUST provide a manifest.yml conforming to this schema.
"""

from typing import Dict, List, Optional, Literal
from pydantic import BaseModel, Field, validator
import re


class InputValidation(BaseModel):
    """Validation rules for input fields"""
    pattern: Optional[str] = None  # Regex pattern
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    allowed_values: Optional[List[str]] = None  # Enum


class InputField(BaseModel):
    """Input field definition"""
    name: str = Field(..., pattern=r'^[a-z_][a-z0-9_]*$')
    type: Literal['string', 'integer', 'boolean', 'password', 'select', 'email', 'port']
    label: str
    description: Optional[str] = None
    required: bool = True
    default: Optional[str] = None
    validation: Optional[InputValidation] = None
    visible_if: Optional[Dict[str, str]] = None  # Conditional visibility
    sensitive: bool = False  # Mask in logs


class OSRequirement(BaseModel):
    """Operating system requirements"""
    family: List[Literal['debian', 'ubuntu', 'centos', 'rhel', 'fedora', 'alpine']]
    min_version: Optional[str] = None


class ResourceRequirements(BaseModel):
    """Minimum resource requirements"""
    min_ram_mb: Optional[int] = None
    min_disk_mb: Optional[int] = None
    min_cpu_cores: Optional[int] = None


class AppManifest(BaseModel):
    """Complete application manifest"""
    id: str = Field(..., pattern=r'^[a-z0-9-]+$')
    name: str
    version: str
    description: str
    category: str
    author: str
    homepage: Optional[str] = None
    
    os_requirements: OSRequirement
    resource_requirements: Optional[ResourceRequirements] = None
    
    inputs: List[InputField] = []
    
    install_script: str = Field(default='install.sh')
    uninstall_script: Optional[str] = None
    
    timeout_seconds: int = Field(default=600, ge=60, le=3600)
    idempotent: bool = True
    
    tags: List[str] = []
    
    @validator('install_script')
    def validate_script_path(cls, v):
        if not re.match(r'^[a-zA-Z0-9_\-\.]+\.sh$', v):
            raise ValueError('Script must be a .sh file with safe characters')
        return v


class JobConfig(BaseModel):
    """Job configuration passed to agent"""
    job_id: str
    app_id: str
    inputs: Dict[str, str]
    server_id: str
    user_id: str
    signature: str  # HMAC signature for verification
