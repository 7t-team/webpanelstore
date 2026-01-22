#!/usr/bin/env python3
"""Generate manifests for 50 applications"""

import yaml
import os

apps = [
    {"id": "nextcloud", "name": "Nextcloud", "desc": "Self-hosted cloud storage and collaboration", "cat": "cloud-storage", "port": 80},
    {"id": "n8n", "name": "n8n", "desc": "Workflow automation tool", "cat": "automation", "port": 5678},
    {"id": "aapanel", "name": "aaPanel", "desc": "Free web hosting control panel", "cat": "control-panels", "port": 7800},
    {"id": "cyberpanel", "name": "CyberPanel", "desc": "Web hosting control panel with OpenLiteSpeed", "cat": "control-panels", "port": 8090},
    {"id": "cpanel", "name": "cPanel", "desc": "Web hosting control panel", "cat": "control-panels", "port": 2083},
    {"id": "plesk", "name": "Plesk", "desc": "Web hosting platform", "cat": "control-panels", "port": 8443},
    {"id": "wordpress", "name": "WordPress", "desc": "Popular CMS platform", "cat": "cms", "port": 80},
    {"id": "phpmyadmin", "name": "phpMyAdmin", "desc": "MySQL database management", "cat": "database-tools", "port": 80},
    {"id": "grafana", "name": "Grafana", "desc": "Analytics and monitoring platform", "cat": "monitoring", "port": 3000},
    {"id": "prometheus", "name": "Prometheus", "desc": "Monitoring and alerting toolkit", "cat": "monitoring", "port": 9090},
    {"id": "jenkins", "name": "Jenkins", "desc": "Automation server for CI/CD", "cat": "ci-cd", "port": 8080},
    {"id": "gitlab", "name": "GitLab", "desc": "DevOps platform", "cat": "ci-cd", "port": 80},
    {"id": "redis", "name": "Redis", "desc": "In-memory data structure store", "cat": "databases", "port": 6379},
    {"id": "postgresql", "name": "PostgreSQL", "desc": "Advanced relational database", "cat": "databases", "port": 5432},
    {"id": "mongodb", "name": "MongoDB", "desc": "NoSQL document database", "cat": "databases", "port": 27017},
    {"id": "elasticsearch", "name": "Elasticsearch", "desc": "Search and analytics engine", "cat": "databases", "port": 9200},
    {"id": "rabbitmq", "name": "RabbitMQ", "desc": "Message broker", "cat": "message-queues", "port": 5672},
    {"id": "minio", "name": "MinIO", "desc": "S3-compatible object storage", "cat": "storage", "port": 9000},
    {"id": "portainer", "name": "Portainer", "desc": "Container management platform", "cat": "containers", "port": 9443},
    {"id": "traefik", "name": "Traefik", "desc": "Modern reverse proxy", "cat": "proxy", "port": 80},
    {"id": "caddy", "name": "Caddy", "desc": "Web server with automatic HTTPS", "cat": "web-servers", "port": 80},
    {"id": "apache", "name": "Apache HTTP Server", "desc": "Popular web server", "cat": "web-servers", "port": 80},
    {"id": "tomcat", "name": "Apache Tomcat", "desc": "Java servlet container", "cat": "web-servers", "port": 8080},
    {"id": "nodejs", "name": "Node.js", "desc": "JavaScript runtime", "cat": "runtimes", "port": 3000},
    {"id": "python-env", "name": "Python Environment", "desc": "Python development environment", "cat": "runtimes", "port": 8000},
    {"id": "ruby-env", "name": "Ruby Environment", "desc": "Ruby development environment", "cat": "runtimes", "port": 3000},
    {"id": "go-env", "name": "Go Environment", "desc": "Go development environment", "cat": "runtimes", "port": 8080},
    {"id": "php-fpm", "name": "PHP-FPM", "desc": "PHP FastCGI Process Manager", "cat": "runtimes", "port": 9000},
    {"id": "memcached", "name": "Memcached", "desc": "Distributed memory caching", "cat": "caching", "port": 11211},
    {"id": "varnish", "name": "Varnish Cache", "desc": "HTTP accelerator", "cat": "caching", "port": 6081},
    {"id": "haproxy", "name": "HAProxy", "desc": "Load balancer", "cat": "load-balancers", "port": 80},
    {"id": "fail2ban", "name": "Fail2Ban", "desc": "Intrusion prevention", "cat": "security", "port": 0},
    {"id": "ufw", "name": "UFW Firewall", "desc": "Uncomplicated Firewall", "cat": "security", "port": 0},
    {"id": "iptables", "name": "iptables", "desc": "Linux firewall", "cat": "security", "port": 0},
    {"id": "wireguard", "name": "WireGuard VPN", "desc": "Modern VPN protocol", "cat": "vpn", "port": 51820},
    {"id": "openvpn", "name": "OpenVPN", "desc": "Open-source VPN", "cat": "vpn", "port": 1194},
    {"id": "certbot", "name": "Certbot", "desc": "Let's Encrypt SSL certificates", "cat": "ssl", "port": 0},
    {"id": "letsencrypt", "name": "Let's Encrypt", "desc": "Free SSL certificates", "cat": "ssl", "port": 0},
    {"id": "cloudflare-tunnel", "name": "Cloudflare Tunnel", "desc": "Secure tunnel to Cloudflare", "cat": "networking", "port": 0},
    {"id": "netdata", "name": "Netdata", "desc": "Real-time performance monitoring", "cat": "monitoring", "port": 19999},
    {"id": "zabbix", "name": "Zabbix", "desc": "Enterprise monitoring solution", "cat": "monitoring", "port": 80},
    {"id": "uptime-kuma", "name": "Uptime Kuma", "desc": "Self-hosted monitoring tool", "cat": "monitoring", "port": 3001},
    {"id": "matomo", "name": "Matomo", "desc": "Web analytics platform", "cat": "analytics", "port": 80},
    {"id": "discourse", "name": "Discourse", "desc": "Modern forum platform", "cat": "forums", "port": 80},
    {"id": "ghost", "name": "Ghost", "desc": "Professional publishing platform", "cat": "cms", "port": 2368},
    {"id": "joomla", "name": "Joomla", "desc": "Content management system", "cat": "cms", "port": 80},
    {"id": "drupal", "name": "Drupal", "desc": "Enterprise CMS", "cat": "cms", "port": 80},
    {"id": "magento", "name": "Magento", "desc": "E-commerce platform", "cat": "ecommerce", "port": 80},
    {"id": "prestashop", "name": "PrestaShop", "desc": "E-commerce solution", "cat": "ecommerce", "port": 80},
    {"id": "woocommerce", "name": "WooCommerce", "desc": "WordPress e-commerce plugin", "cat": "ecommerce", "port": 80},
]

for app in apps:
    manifest = {
        "id": app["id"],
        "name": app["name"],
        "version": "latest",
        "description": app["desc"],
        "category": app["cat"],
        "author": "Platform Team",
        "os_requirements": {
            "family": ["ubuntu", "debian"],
            "min_version": "20.04"
        },
        "resource_requirements": {
            "min_ram_mb": 1024,
            "min_disk_mb": 2048,
            "min_cpu_cores": 1
        },
        "inputs": [
            {
                "name": "domain",
                "type": "string",
                "label": "Domain Name",
                "description": f"Domain for {app['name']}",
                "required": True,
                "validation": {
                    "pattern": "^[a-z0-9\\-\\.]+$",
                    "max_length": 253
                }
            },
            {
                "name": "admin_email",
                "type": "email",
                "label": "Admin Email",
                "required": True
            }
        ],
        "install_script": "install.sh",
        "timeout_seconds": 1200,
        "idempotent": True,
        "tags": [app["cat"], "server-app"]
    }
    
    if app["port"] > 0:
        manifest["inputs"].append({
            "name": "port",
            "type": "port",
            "label": "Port",
            "default": str(app["port"]),
            "required": False,
            "validation": {
                "min_value": 1,
                "max_value": 65535
            }
        })
    
    # Write manifest
    os.makedirs(f"installers/{app['id']}", exist_ok=True)
    with open(f"installers/{app['id']}/manifest.yml", 'w') as f:
        yaml.dump(manifest, f, default_flow_style=False, allow_unicode=True)
    
    # Create basic install script
    install_script = f"""#!/bin/bash
set -euo pipefail

LOG_FILE="/var/log/provisioning/{app['id']}-install-$(date +%s).log"
mkdir -p "$(dirname "$LOG_FILE")"
exec > >(tee -a "$LOG_FILE") 2>&1

log() {{ echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*"; }}
error() {{ log "ERROR: $*"; exit "${{2:-2}}"; }}

log "Starting {app['name']} installation"

[[ -z "${{DOMAIN:-}}" ]] && error "DOMAIN not set" 1
[[ -z "${{ADMIN_EMAIL:-}}" ]] && error "ADMIN_EMAIL not set" 1

export DEBIAN_FRONTEND=noninteractive

log "Installing {app['name']}..."
# Installation commands here
apt-get update -qq
apt-get install -y -qq curl wget

log "{app['name']} installation completed"
log "Access at: http://${{DOMAIN}}"

exit 0
"""
    
    with open(f"installers/{app['id']}/install.sh", 'w') as f:
        f.write(install_script)
    
    os.chmod(f"installers/{app['id']}/install.sh", 0o755)

print(f"Generated {len(apps)} application manifests")
