#!/bin/bash


docker build -t tricke/cse240 "$(dirname "$0")"

docker push tricke/cse240

