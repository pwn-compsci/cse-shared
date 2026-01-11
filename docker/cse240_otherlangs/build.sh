#!/bin/bash
docker build -t tricke/cse240-otherlangs "$(dirname "$0")"
docker push tricke/cse240-otherlangs
