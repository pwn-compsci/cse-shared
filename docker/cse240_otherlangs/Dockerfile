# syntax=docker/dockerfile:1-labs
FROM tricke/cse240

ENV DEBIAN_FRONTEND=noninteractive
ENV LC_CTYPE=C.UTF-8

RUN mkdir -p /run/challenge/share/code/extensions

COPY ../pwn-cpmate-0.0.2.vsix /run/challenge/share/code/extensions
COPY ../AmauryRabouan.new-vsc-prolog-1.1.12.vsix /run/challenge/share/code/extensions

# Install code-server
RUN curl -fsSL https://code-server.dev/install.sh | bash

# Install Racket and Prolog extensions for other language modules
RUN <<EOF    
    
    $(which code-server) \
    --auth=none \
    --disable-telemetry \
    --extensions-dir=/run/challenge/share/code/extensions \
    --install-extension /run/challenge/share/code/extensions/pwn-cpmate-0.0.2.vsix \
    --install-extension evzen-wybitul.magic-racket \
    --install-extension /run/challenge/share/code/extensions/AmauryRabouan.new-vsc-prolog-1.1.12.vsix

EOF

RUN mkdir /cse240_otherlangs_v1
