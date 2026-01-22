#!/bin/bash
# Simple setup script for virtual environment

echo "Setting up Provisioning Platform..."

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate and install
echo "Installing dependencies..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "✅ Setup complete!"
echo ""
echo "To start the platform:"
echo "  bash start.sh"
echo ""
echo "Or manually:"
echo "  source venv/bin/activate"
echo "  cd panel && python app.py"
