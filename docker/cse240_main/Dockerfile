
# syntax=docker/dockerfile:1-labs

# -------- Stage 1: Build landrun --------
############################## Build landrun ####################################################
    FROM golang:1.21 AS landrunbuilder

    RUN go install github.com/zouuup/landrun/cmd/landrun@latest

######################## Build base cse240 container ##############################################
FROM ubuntu:24.04 AS essentials

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


FROM essentials AS vscoder

RUN mkdir -p /run/challenge/share/code/extensions

COPY pwn-cpmate-0.0.2.vsix /run/challenge/share/code/extensions

RUN curl -fsSL https://code-server.dev/install.sh | bash
RUN  /bin/wget -P /run/challenge/share/code/extensions 'https://github.com/microsoft/vscode-cpptools/releases/download/v1.20.5/cpptools-linux.vsix'

RUN <<EOF    
    
    $(which code-server) \
    --auth=none \
    --disable-telemetry \
    --extensions-dir=/run/challenge/share/code/extensions \
    --install-extension /run/challenge/share/code/extensions/cpptools-linux.vsix \
    --install-extension /run/challenge/share/code/extensions/pwn-cpmate-0.0.2.vsix

EOF

################################################################################

FROM essentials AS builder

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
        manpages
        manpages-posix
        manpages-posix-dev
        glibc-doc
        gcc-doc
        binutils-doc
        cpp-doc
        make-doc
        libc6-dev
        linux-doc
        tldr
        tzdata 
        unminimize 
        nasm
        python-is-python3
        python3-dev
        python3-pip
        libseccomp2         
EOF

# Run unminimize immediately after package installation
RUN printf 'y\n' | /usr/local/sbin/unminimize || printf 'y\n' | unminimize || true

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
        openjdk-17-jdk        
EOF

################# Install Land Run ############################################
# Copy compiled landrun binary only
COPY --from=landrunbuilder /go/bin/landrun /usr/local/bin/landrun

################################################################################

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
RUN pip install psutil 
# RUN python3 -c "import gevent; print(gevent.__version__)" 

# Build and update man database for offline operation
RUN echo "Rebuilding man database for offline operation..." \
 && mandb -c \
 && echo "Man database rebuilt successfully"

ENV LC_CTYPE=C.UTF-8

RUN <<EOF
    if id ubuntu; then userdel -f -r ubuntu; fi 
    useradd -s /bin/bash -m hacker 
    passwd -d hacker 
    
    # Ensure hacker user has proper shell configuration for offline tools
    echo 'export MANPAGER="less"' >> /home/hacker/.bashrc
    echo 'export TLDR_AUTO_UPDATE_DISABLED=1' >> /home/hacker/.bashrc
    echo 'export TLDR_CACHE_DIR="/usr/share/tldr"' >> /home/hacker/.bashrc
    
    # Also set for root
    echo 'export TLDR_AUTO_UPDATE_DISABLED=1' >> /root/.bashrc
    echo 'export TLDR_CACHE_DIR="/usr/share/tldr"' >> /root/.bashrc
    
    # Create hacker's tldr cache directory if it doesn't exist
    mkdir -p /home/hacker/.local/share/tldr
    chown -R hacker:hacker /home/hacker/.local
    
    # Ensure man database is accessible to hacker user
    chown -R root:root /var/cache/man
    chmod -R 755 /var/cache/man
EOF

# Configure tldr for offline operation
RUN mkdir -p /root/.local/share/tldr /usr/share/tldr /home/hacker/.local/share/tldr \
 && (for i in 1 2 3; do \
      echo "Attempt $i to download tldr pages..." \
      && rm -rf /root/.local/share/tldr/* \
      && cd /tmp \
      && curl -L -o tldr.zip https://github.com/tldr-pages/tldr/archive/refs/heads/main.zip \
      && unzip -q tldr.zip \
      && cp -r tldr-main/pages/* /root/.local/share/tldr/ \
      && rm -rf tldr.zip tldr-main \
      && break \
      || ([ $i -eq 3 ] && echo "Failed to download tldr pages after 3 attempts" && exit 1 || sleep 5); \
    done) \
 && cp -r /root/.local/share/tldr/* /usr/share/tldr/ \
 && cp -r /root/.local/share/tldr/* /home/hacker/.local/share/tldr/ \
 && chown -R root:root /usr/share/tldr \
 && chown -R hacker:hacker /home/hacker/.local/share/tldr \
 && ls -la /usr/share/tldr/ | head -20 \
 && echo "tldr pages successfully installed" \
 && echo "Configuring tldr for offline operation..." \
 && echo 'export TLDR_CACHE_DIR="/usr/share/tldr"' >> /etc/bash.bashrc \
 && echo 'export TLDR_AUTO_UPDATE_DISABLED=1' >> /etc/bash.bashrc

# Set environment variables for offline tldr operation
ENV TLDR_CACHE_DIR=/usr/share/tldr
ENV TLDR_AUTO_UPDATE_DISABLED=1

######################################################################
# Install racket-langserver

RUN raco pkg install --auto --scope installation racket-langserver

# ensure racket-langserver is visible under collects for `racket --lib`
RUN mkdir -p /usr/share/racket/collects && \
    cp -a /usr/share/racket/pkgs/racket-langserver /usr/share/racket/collects/racket-langserver && \
    chmod -R a+rX /usr/share/racket/collects/racket-langserver || true

RUN mkdir -p /cse240_v83 && touch "/cse240_v83/$(date +%Y-%m-%d_%H-%M-%S).dat"

# -------- Final stage: inherit everything from builder and fix collects perms --------
FROM builder AS final

# Ensure the racket-langserver collects are readable by any runtime user
# (safe no-op if the directory already exists)
RUN if [ -d /usr/share/racket/collects/racket-langserver ]; then chmod -R a+rX /usr/share/racket/collects/racket-langserver || true; fi

# keep current user behavior: do not change USER, CMD or ENTRYPOINT
# this stage intentionally does not add or remove other files





