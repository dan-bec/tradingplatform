#!/bin/bash

# Navigate to the repository root
cd /Volumes/T7-2TB/GitHub/tradingplatform/

# Stash any uncommitted changes
# git stash

# Fetch the latest from origin
# git fetch origin

# Checkout the remote main branch (detached HEAD)
# git checkout origin/main

# Run the Python script with provided arguments
python3 scripts/main.py

# Checkout the data-features branch
# git checkout data-features

# Apply stashed changes if any
# git stash pop