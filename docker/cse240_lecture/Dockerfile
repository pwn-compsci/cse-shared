# syntax=docker/dockerfile:1

FROM python:3.13-slim

RUN pip install --no-cache-dir flask gunicorn

RUN apt-get update && apt-get install -y jq && rm -rf /var/lib/apt/lists/*

ADD wsgi.py /opt/lecture/
ADD templates/ /opt/lecture/templates/

COPY <<EOF /opt/lecture/gunicorn.conf.py
wsgi_app = 'wsgi:application'
bind = "0.0.0.0:8080"
loglevel = "info"
accesslog = "/var/log/gunicorn/access.log"
errorlog = "/var/log/gunicorn/error.log"
EOF

COPY --chmod=755 <<EOF /challenge/.init
#!/bin/sh
export PYTHONDONTWRITEBYTECODE=1
mkdir -p /var/log/gunicorn
cd /opt/lecture
gunicorn --daemon
EOF

RUN mkdir /lec_v4
