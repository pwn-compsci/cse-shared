#! /usr/bin/env bash

BASEDIR="$(dirname "$(readlink -f "$0")")/.."

tmpfile=/tmp/tmp.yml
outfile=${BASEDIR}/dojo.yml

echo "" > ${tmpfile}

cat >> ${tmpfile} <<EOF
id: cse240fall2023

name: CSE240 Programming Assignments

description: |
  This is the dojo for CSE240 Introduction to Programming Languages.

type: course

award:
  emoji: 😀

modules:

EOF

latest=""

for assignmentdir in $(ls -d ${BASEDIR}/*-??-*); do
    cd $assignmentdir

    cat >> ${tmpfile} <<EOF

  - id: $(basename $assignmentdir)
$(awk '{ print "    " $0 }' assignment_info.yml)

    challenges:

EOF

    for f in $(ls -d ?*-??-*); do
        latest=${f}
        cat >> ${tmpfile} <<EOF
      - id: $f
        name: $(grep -oh "Level.*" $f/README.md|rev|cut -c5-| rev | sed 's/[[:space:]]*$//')
        $(grep "description: " $f/README.md || echo 'description: From the terminal for this challenge, read the login message or `cat /challenge/README.md` for details.')

EOF

    done

done

cd $BASEDIR

if diff ${tmpfile} ${outfile} > /dev/null ; then # there is no difference
    echo "No difference between files, skipping"
else
    echo "Copying new dojo file"
    cp dojo.yml /tmp/prior-dojo.yml
    cp ${tmpfile} ${outfile}
fi

if git status | grep "nothing to commit"; then
    echo "Nothing to commit or push"
else
    echo "Committing and pushing to repo"
    set -e
    git add . > /dev/null 2> /dev/null
    git commit -m "$latest WiP - auto" > /dev/null 2> /dev/null
    git push > /dev/null 2> /dev/null
    echo "Completed push."
fi
