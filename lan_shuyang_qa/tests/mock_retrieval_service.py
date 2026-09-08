"""Temporary contract-test server for POST /search; not production retrieval."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        if self.path not in {"/search", "/api/retrieval"}:
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        response = {"results": [
            {"id": "cisa-apt29-1", "text": "CISA reports APT29 used valid accounts (T1078) for initial access.",
             "source": "CISA", "url": "https://www.cisa.gov/", "score": 0.93,
             "entities": {"actors": ["APT29"], "techniques": ["T1078"]},
             "graph_paths": ["APT29 -> T1078 -> valid accounts"]},
            {"id": "mitre-apt29-2", "text": "MITRE ATT&CK associates APT29 with Valid Accounts technique T1078.",
             "source": "MITRE ATT&CK", "url": "https://attack.mitre.org/", "score": 0.88,
             "entities": {"actors": ["APT29"], "techniques": ["T1078"]},
             "graph_paths": ["APT29 -> T1078"]},
        ]}
        body = json.dumps(response).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 8001), Handler).serve_forever()
