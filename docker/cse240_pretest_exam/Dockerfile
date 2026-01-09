
# syntax=docker/dockerfile:1-labs
FROM tricke/cse240

ENV DEBIAN_FRONTEND=noninteractive
ENV LC_CTYPE=C.UTF-8

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && xargs apt-get install --no-install-recommends -yqq <<EOF && \
    apt-get clean && rm -rf /var/lib/apt/lists/*
        openjdk-17-jdk
EOF

RUN rm -f /usr/lib/python3.*/EXTERNALLY-MANAGED

# Install code-server for pretest module
RUN curl -fsSL https://code-server.dev/install.sh | bash

RUN mkdir /cse240_test_v5





