#!/usr/bin/env bash


if [ -z "$1" ]; then 
    echo "You must include the grouplab number"
    exit 99
fi 

glnum=$(printf "%02d" "$1")

mkdir -p /home/.config 

jq '{
    hwdir: "/home/",
    source_dir: "/home",
    createHWDir: .createHWDir,
    testdir: "/home/system_tests/",
    labid: .labid,
    level: .level,
    requiredUserTests: .requiredUserTests
}' "/course/grouplab$glnum/.config/level.json" > /home/.config/level.json

cp -a /course/grouplab$glnum/group_template/*" /home 

cp -a "/course/grouplab$glnum/system_tests" /home 

echo "Copy from '/course/grouplab$glnum' completed"

