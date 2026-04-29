#!/bin/bash
set -euo pipefail

docker build --progress=plain -t tricke/cse240 "$(dirname "$0")"
docker push tricke/cse240

