# syntax=docker/dockerfile:1

FROM python:3.13-slim

RUN pip install --no-cache-dir flask gunicorn requests

RUN apt-get update && apt-get install -y jq && rm -rf /var/lib/apt/lists/*
ADD redirector.py /opt/redirector.py
RUN chmod +x /opt/redirector.py

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
python3 /opt/redirector.py -d -p 7681 >> /var/log/redirector.log 2>&1
python3 /opt/redirector.py -d -p 6080 >> /var/log/redirector.log 2>&1

export PYTHONDONTWRITEBYTECODE=1
mkdir -p /var/log/gunicorn
cd /opt/lecture
gunicorn --daemon --reload
EOF


# COPYING exec-suid from pwncollege docker image
ADD --chown=0:0 --chmod=6755 http://github.com/pwncollege/exec-suid/releases/latest/download/exec-suid /usr/bin/exec-suid


RUN mkdir /lec_v11
