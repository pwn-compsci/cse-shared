
# syntax=docker/dockerfile:1-labs

# -------- Stage 1: Build landrun --------
############################## Build landrun ####################################################
    FROM golang:1.21 AS landrunbuilder

    RUN go install github.com/zouuup/landrun/cmd/landrun@latest

######################## Build base cse240 container ##############################################
FROM ubuntu:24.04 as essentials

# SHELL ["/bin/bash", "-ceov", "pipefail"]

ENV DEBIAN_FRONTEND=noninteractive
ENV LC_CTYPE=C.UTF-8

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && xargs apt-get install --no-install-recommends -yqq <<EOF && \
    apt-get clean && rm -rf /var/lib/apt/lists/*
        build-essential
        ca-certificates
        curl
        python-is-python3
        wget
        unzip
EOF

RUN rm -f /usr/lib/python3.*/EXTERNALLY-MANAGED


FROM essentials as vscoder

RUN mkdir -p /run/challenge/share/code/extensions

COPY pwn-cpmate-0.0.1.vsix /run/challenge/share/code/extensions
COPY AmauryRabouan.new-vsc-prolog-1.1.12.vsix /run/challenge/share/code/extensions

RUN curl -fsSL https://code-server.dev/install.sh | bash
RUN  /bin/wget -P /run/challenge/share/code/extensions 'https://github.com/microsoft/vscode-cpptools/releases/download/v1.20.5/cpptools-linux.vsix'

RUN <<EOF    
    
    $(which code-server) \
    --auth=none \
    --disable-telemetry \
    --extensions-dir=/run/challenge/share/code/extensions \
    --install-extension ms-python.python \
    --install-extension /run/challenge/share/code/extensions/cpptools-linux.vsix \
    --install-extension /run/challenge/share/code/extensions/pwn-cpmate-0.0.1.vsix \
    --install-extension evzen-wybitul.magic-racket \
    --install-extension /run/challenge/share/code/extensions/AmauryRabouan.new-vsc-prolog-1.1.12.vsix

EOF

################################################################################

FROM essentials as builder

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && xargs apt-get install --no-install-recommends -yqq <<EOF && \
    apt-get clean && rm -rf /var/lib/apt/lists/*
        autoconf
        bc
        cpio
        flex
        git
        libedit-dev
        libelf-dev
        libffi-dev
        libglib2.0-dev
        libgmp-dev
        libini-config-dev
        man-db
        manpages-dev
        nasm
        python-is-python3
        python3-dev
        python3-pip
        libseccomp2         
EOF

RUN pip install fastecdsa

################################################################################

RUN <<EOF
    
    git clone --depth 1 https://github.com/hugsy/gef /opt/gef

    ln -sf /home/hacker/.gdbinit /root/.gdbinit
EOF

################################################################################
SHELL ["/bin/bash", "-c"]
RUN <<EOF
    VERSION="1.5.1"
    DEB_NAME="glow_${VERSION}_amd64.deb"
    pushd /tmp
    wget -q "https://github.com/charmbracelet/glow/releases/download/v${VERSION}/${DEB_NAME}"
    apt install "./${DEB_NAME}"
    rm "${DEB_NAME}"
    popd
EOF

RUN <<EOF
    VERSION="busybox-1.33.2"
    mkdir /opt/busybox && cd "$_"
    wget -q -O - "https://busybox.net/downloads/${VERSION}.tar.bz2" | tar xvj
    pushd "${VERSION}"
    make defconfig
    sed -e 's/.*CONFIG_STATIC .*/CONFIG_STATIC=y/' -i .config
    make -j$(nproc) install
    popd
    ln -s "${VERSION}/_install" /opt/busybox/fs
EOF

################################################################################

RUN apt-get update && xargs apt-get install --no-install-recommends -yqq <<EOF \
        bash-builtins
        bsdmainutils
        bsdutils
        debianutils
        emacs
        gcc
        g++
        gdb        
        vim
EOF
# --mount=type=cache,target=/var/cache/apt,sharing=locked \
#     --mount=type=cache,target=/var/lib/apt,sharing=locked \
#     apt-get update && xargs apt-get install --no-install-recommends -yqq <<EOF && \
#     apt-get clean && rm -rf /var/lib/apt/lists/*

RUN apt-get update && xargs apt-get install --no-install-recommends -yqq <<EOF \
        bat
        gprolog
        hexedit
        icdiff
        ipython3
        jq
        racket
        rsync
        strace
        tmux
        valgrind
        zip
        zsh
        sqlite3
        xvfb
        gcc-13 g++-13 
        gcc-13-plugin-dev 
        file
        passwd
        nginx 
EOF

################# Install Land Rune ############################################
# Copy compiled landrun binary only
COPY --from=landrunbuilder /go/bin/landrun /usr/local/bin/landrun

################################################################################

RUN raco pkg install --auto --scope installation racket-langserver

RUN ln -sf /usr/bin/ipython3 /usr/bin/ipython

RUN mkdir -p /challenge/bin

################################################################################

RUN mkdir -p /run/challenge/share/code/extensions
COPY --link --from=vscoder /run/challenge/share/code/extensions /run/challenge/share/code/extensions

# COPYING exec-suid from pwncollege docker image
ADD --chown=0:0 --chmod=6755 http://github.com/pwncollege/exec-suid/releases/latest/download/exec-suid /usr/bin/exec-suid

################################################################################

RUN <<EOF
    mkdir -p /opt/pwn.college
    ln -sf /run/dojo/bin/python-suid /opt/pwn.college/python
    ln -sf /run/dojo/bin/bash-suid /opt/pwn.college/bash
    ln -sf /run/dojo/bin/sh-suid /opt/pwn.college/sh    
    ln -s /etc/bash.bashrc /etc/bashrc 
EOF
# link from /etc/bash.bashrc to /etc/bashrc is because /bin/bash uses /etc/bash.bashrc but /run/dojo/bin/bash uses /etc/bash
################################################################################

RUN pip install flask requests gevent gevent-websocket
RUN pip install --user flask requests gevent gevent-websocket

# RUN python3 -c "import gevent; print(gevent.__version__)" 

ENV LC_CTYPE=C.UTF-8

RUN <<EOF
    if id ubuntu; then userdel -f -r ubuntu; fi 
    useradd -s /bin/bash -m hacker 
    passwd -d hacker 
EOF

RUN mkdir /cse240_v4





