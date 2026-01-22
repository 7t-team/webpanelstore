#!/bin/bash
set -euo pipefail

LOG_FILE="/var/log/provisioning/pterodactyl-install-$(date +%s).log"
mkdir -p "$(dirname "$LOG_FILE")"
exec > >(tee -a "$LOG_FILE") 2>&1

log() { echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*"; }
error() { log "ERROR: $*"; exit "${2:-2}"; }

log "Starting Pterodactyl Panel installation"

[[ -z "${DOMAIN:-}" ]] && error "DOMAIN not set" 1
[[ -z "${ADMIN_EMAIL:-}" ]] && error "ADMIN_EMAIL not set" 1
[[ -z "${ADMIN_USERNAME:-}" ]] && error "ADMIN_USERNAME not set" 1
[[ -z "${ADMIN_PASSWORD:-}" ]] && error "ADMIN_PASSWORD not set" 1
[[ -z "${MYSQL_ROOT_PASSWORD:-}" ]] && error "MYSQL_ROOT_PASSWORD not set" 1

INSTALL_WINGS="${INSTALL_WINGS:-false}"

export DEBIAN_FRONTEND=noninteractive

if [ -d "/var/www/pterodactyl" ]; then
    log "Pterodactyl already installed"
    exit 0
fi

log "Installing dependencies"
apt-get update -qq
apt-get install -y -qq software-properties-common curl apt-transport-https ca-certificates gnupg

add-apt-repository -y ppa:ondrej/php
apt-get update -qq

apt-get install -y -qq php8.1 php8.1-{cli,gd,mysql,pdo,mbstring,tokenizer,bcmath,xml,fpm,curl,zip} \
    mariadb-server nginx tar unzip git redis-server

log "Configuring MariaDB"
mysql -e "ALTER USER 'root'@'localhost' IDENTIFIED BY '${MYSQL_ROOT_PASSWORD}';"
mysql -uroot -p"${MYSQL_ROOT_PASSWORD}" -e "CREATE DATABASE IF NOT EXISTS panel;"
mysql -uroot -p"${MYSQL_ROOT_PASSWORD}" -e "CREATE USER IF NOT EXISTS 'pterodactyl'@'127.0.0.1' IDENTIFIED BY '${MYSQL_ROOT_PASSWORD}';"
mysql -uroot -p"${MYSQL_ROOT_PASSWORD}" -e "GRANT ALL PRIVILEGES ON panel.* TO 'pterodactyl'@'127.0.0.1';"
mysql -uroot -p"${MYSQL_ROOT_PASSWORD}" -e "FLUSH PRIVILEGES;"

log "Installing Composer"
curl -sS https://getcomposer.org/installer | php -- --install-dir=/usr/local/bin --filename=composer

log "Downloading Pterodactyl Panel"
mkdir -p /var/www/pterodactyl
cd /var/www/pterodactyl
curl -Lo panel.tar.gz https://github.com/pterodactyl/panel/releases/latest/download/panel.tar.gz
tar -xzvf panel.tar.gz
chmod -R 755 storage/* bootstrap/cache/

log "Installing Panel dependencies"
cp .env.example .env
composer install --no-dev --optimize-autoloader --no-interaction

log "Configuring Panel"
php artisan key:generate --force
php artisan p:environment:setup --new-salt --author="${ADMIN_EMAIL}" --url="https://${DOMAIN}" \
    --timezone=UTC --cache=redis --session=redis --queue=redis --redis-host=127.0.0.1 \
    --redis-pass= --redis-port=6379 --no-interaction

php artisan p:environment:database --host=127.0.0.1 --port=3306 --database=panel \
    --username=pterodactyl --password="${MYSQL_ROOT_PASSWORD}" --no-interaction

php artisan migrate --seed --force
php artisan p:user:make --email="${ADMIN_EMAIL}" --username="${ADMIN_USERNAME}" \
    --name-first=Admin --name-last=User --password="${ADMIN_PASSWORD}" --admin=1 --no-interaction

chown -R www-data:www-data /var/www/pterodactyl/*

log "Configuring Nginx"
cat > /etc/nginx/sites-available/pterodactyl.conf <<EOF
server {
    listen 80;
    server_name ${DOMAIN};
    return 301 https://\$server_name\$request_uri;
}

server {
    listen 443 ssl http2;
    server_name ${DOMAIN};

    root /var/www/pterodactyl/public;
    index index.php;

    location / {
        try_files \$uri \$uri/ /index.php?\$query_string;
    }

    location ~ \.php$ {
        fastcgi_split_path_info ^(.+\.php)(/.+)$;
        fastcgi_pass unix:/run/php/php8.1-fpm.sock;
        fastcgi_index index.php;
        include fastcgi_params;
        fastcgi_param PHP_VALUE "upload_max_filesize = 100M \n post_max_size=100M";
        fastcgi_param SCRIPT_FILENAME \$document_root\$fastcgi_script_name;
        fastcgi_param HTTP_PROXY "";
        fastcgi_intercept_errors off;
        fastcgi_buffer_size 16k;
        fastcgi_buffers 4 16k;
        fastcgi_connect_timeout 300;
        fastcgi_send_timeout 300;
        fastcgi_read_timeout 300;
    }

    location ~ /\.ht {
        deny all;
    }
}
EOF

ln -sf /etc/nginx/sites-available/pterodactyl.conf /etc/nginx/sites-enabled/pterodactyl.conf
rm -f /etc/nginx/sites-enabled/default

log "Setting up cron"
(crontab -l 2>/dev/null; echo "* * * * * php /var/www/pterodactyl/artisan schedule:run >> /dev/null 2>&1") | crontab -

log "Setting up queue worker"
cat > /etc/systemd/system/pteroq.service <<EOF
[Unit]
Description=Pterodactyl Queue Worker
After=redis-server.service

[Service]
User=www-data
Group=www-data
Restart=always
ExecStart=/usr/bin/php /var/www/pterodactyl/artisan queue:work --queue=high,standard,low --sleep=3 --tries=3
StartLimitInterval=180
StartLimitBurst=30
RestartSec=5s

[Install]
WantedBy=multi-user.target
EOF

systemctl enable pteroq
systemctl start pteroq

systemctl restart php8.1-fpm
systemctl restart nginx

log "Installation completed successfully"
log "Access panel at: https://${DOMAIN}"
log "Admin username: ${ADMIN_USERNAME}"

exit 0
