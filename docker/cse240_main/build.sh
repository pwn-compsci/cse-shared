#!/bin/bash

set -e

SCRIPT_DIR="$(dirname "$0")"
DOCKERFILE="${SCRIPT_DIR}/Dockerfile"

# Extract current version number from Dockerfile (pattern: /cse240_vXX)
current_version=$(grep -oP 'cse240_v\K[0-9]+' "$DOCKERFILE" | head -n1)

if [ -z "$current_version" ]; then
    echo "Warning: Could not find version number in Dockerfile, using v1"
    current_version=0
fi

# Increment version
new_version=$((current_version + 1))

echo "Updating Dockerfile version: v${current_version} -> v${new_version}"

# Update version in Dockerfile
sed -i "s|cse240_v${current_version}|cse240_v${new_version}|g" "$DOCKERFILE"

echo "Building Docker image tricke/cse240 with version v${new_version}..."
docker build -t tricke/cse240 "$SCRIPT_DIR"

echo "Pushing Docker image to registry..."
docker push tricke/cse240

echo "Build complete! Version: v${new_version}"

