#!/usr/bin/env bash

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cd $SCRIPTS_DIR
vsce package 
ret=$?
if [ $? -ne 0 ]; then 
    echo "Failed to package extension" 
    exit 1
fi

DOCKER_DIR="$SCRIPTS_DIR/../../docker"
cp $SCRIPTS_DIR/pwn-cpmate-0.0.1.vsix $DOCKER_DIR

current_version=$(grep -oP 'RUN mkdir /cse240_v\K[0-9]+' "$DOCKER_DIR/Dockerfile")
next_version=$((current_version + 1))
sed -i "s|RUN mkdir /cse240_v$current_version|RUN mkdir /cse240_v$next_version|" "$DOCKER_DIR/Dockerfile"

#cd $DOCKER_DIR
docker build -t tricke/cse240 "$DOCKER_DIR"
ret=$?
if [ $ret -ne 0 ]; then 
    echo "Failed to build image" 
    exit $ret
else
    echo "Finished building image on : $(date)" 
    echo "Finished: $(date)" >> /tmp/push.log 
fi

docker push -q tricke/cse240 
ret=$?
if [ $ret -ne 0 ]; then 
    echo "Failed to push image" 
    exit $ret
else
    echo "Finished pushing image on : $(date)" 
    echo "Finished: $(date)" >> /tmp/push.log 
fi

echo "pushing updated extension into current dojo."
cd $SCRIPTS_DIR/../.. ; git pull ; git add .; git commit -m 'wip2'; git push 





