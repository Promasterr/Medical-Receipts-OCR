#!/bin/bash
# Create 8GB swap file to prevent OOM kills

set -e

echo "Creating 8GB swap space..."

# Check if swap already exists
if [ -f /swapfile ]; then
    echo "Swap file already exists at /swapfile"
    echo "Current swap status:"
    sudo swapon --show
    exit 0
fi

# Create swap file (requires sudo)
echo "Creating swap file (this may take a few minutes)..."
sudo fallocate -l 8G /swapfile

# Set permissions
sudo chmod 600 /swapfile

# Make it a swap file
sudo mkswap /swapfile

# Enable swap
sudo swapon /swapfile

# Verify
echo ""
echo "✓ Swap created successfully!"
echo ""
free -h

# Make it permanent (add to /etc/fstab)
if ! grep -q '/swapfile' /etc/fstab; then
    echo ""
    echo "Adding swap to /etc/fstab for persistence..."
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
    echo "✓ Swap will be enabled on boot"
fi

echo ""
echo "Swap setup complete!"
