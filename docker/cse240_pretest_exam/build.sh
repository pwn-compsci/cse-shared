#!/bin/bash


docker build -t tricke/cse240-pretest "$(dirname "$0")"

docker push tricke/cse240-pretest

