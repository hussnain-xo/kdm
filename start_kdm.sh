#!/bin/bash
# KDM Start Script

echo "🚀 Starting Kalupura Download Manager (KDM)..."
echo ""

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: python3 not found. Please install Python 3."
    exit 1
fi

# Change to script directory
cd "$(dirname "$0")"

# Start KDM
echo "📱 Opening KDM GUI window..."
python3 kdm.py

echo ""
echo "✅ KDM started! GUI window should be visible."
echo "💡 If window doesn't appear, check terminal for errors."
