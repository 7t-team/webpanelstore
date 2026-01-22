#!/bin/bash
# Quick Start Script for Provisioning Platform
# This script sets up a local development environment

set -e

echo "=========================================="
echo "Provisioning Platform - Quick Start"
echo "=========================================="
echo ""

# Check prerequisites
echo "[1/7] Checking prerequisites..."

if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not installed"
    exit 1
fi

if ! command -v redis-server &> /dev/null; then
    echo "⚠️  Redis not found. Installing..."
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        sudo apt-get update -qq
        sudo apt-get install -y redis-server python3-venv
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        brew install redis
    else
        echo "❌ Please install Redis manually"
        exit 1
    fi
fi

echo "✅ Prerequisites OK"
echo ""

# Create virtual environment
echo "[2/7] Setting up virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "✅ Virtual environment created"
else
    echo "✅ Virtual environment already exists"
fi
echo ""

# Activate virtual environment and install dependencies
echo "[3/7] Installing Python dependencies..."
source venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt
echo "✅ Dependencies installed"
echo ""

# Start Redis
echo "[4/7] Starting Redis..."
if ! pgrep -x "redis-server" > /dev/null; then
    redis-server --daemonize yes --port 6379
    sleep 2
fi
echo "✅ Redis running on port 6379"
echo ""

# Generate secret key
echo "[5/7] Generating secret key..."
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
export SECRET_KEY
echo "✅ Secret key generated"
echo ""

# Get admin credentials
echo "[5.5/7] Setup admin credentials..."
read -p "Enter admin username: " ADMIN_USER
read -sp "Enter admin password: " ADMIN_PASS
echo ""
export ADMIN_USER
export ADMIN_PASS
echo "✅ Admin credentials set"
echo ""

# Start Panel
echo "[6/7] Starting Web Panel..."
cd panel
export REDIS_URL="redis://localhost:6379/0"
export FLASK_ENV="development"

../venv/bin/python app.py &
PANEL_PID=$!
cd ..

sleep 3
echo "✅ Panel running on http://localhost:5000 (PID: $PANEL_PID)"
echo ""

# Start Agent
echo "[7/7] Starting Agent..."
cd agent
export AGENT_ID="agent-001"
export REDIS_URL="redis://localhost:6379/0"

# Create log directories
sudo mkdir -p /var/log/provisioning
sudo mkdir -p /var/lib/provisioning
sudo chmod 777 /var/log/provisioning /var/lib/provisioning

../venv/bin/python daemon.py &
AGENT_PID=$!
cd ..

sleep 2
echo "✅ Agent running (PID: $AGENT_PID)"
echo ""

# Summary
echo "=========================================="
echo "✅ Platform is running!"
echo "=========================================="
echo ""
echo "Web Panel:  http://localhost:5000"
echo "API Docs:   http://localhost:5000/api/health"
echo ""
echo "Panel PID:  $PANEL_PID"
echo "Agent PID:  $AGENT_PID"
echo ""
echo "To stop:"
echo "  kill $PANEL_PID $AGENT_PID"
echo "  redis-cli shutdown"
echo ""
echo "Test installation:"
echo "  curl -X POST http://localhost:5000/api/apps/nginx/install \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"server_id\": \"agent-001\", \"inputs\": {\"server_name\": \"test.local\", \"admin_email\": \"admin@test.local\"}}'"
echo ""
echo "View logs:"
echo "  tail -f /var/log/provisioning/agent.log"
echo ""
echo "=========================================="

# Save PIDs for cleanup
echo "$PANEL_PID" > .panel.pid
echo "$AGENT_PID" > .agent.pid

echo ""
echo "Press Ctrl+C to stop all services"
echo ""

# Wait for interrupt
trap "echo ''; echo 'Stopping services...'; kill $PANEL_PID $AGENT_PID 2>/dev/null; redis-cli shutdown 2>/dev/null; echo 'Done'; exit 0" INT TERM

wait
