#!/usr/bin/env python3

from http.server import BaseHTTPRequestHandler, HTTPServer

class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.respond()

    def do_POST(self):
        self.respond()

    def do_HEAD(self):
        self.respond()

    def do_OPTIONS(self):
        self.respond()

    def respond(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Desktop not enabled")

    def log_message(self, format, *args):
        return  # Disable logging

def run():
    server_address = ("0.0.0.0", 6080)
    httpd = HTTPServer(server_address, SimpleHandler)
    print("Serving 'Desktop not enabled' on http://0.0.0.0:8080")
    httpd.serve_forever()

if __name__ == "__main__":
    run()