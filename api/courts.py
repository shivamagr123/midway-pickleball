from http.server import BaseHTTPRequestHandler
import urllib.parse
import json
from .common import get_courts_for_date

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        date_str = params.get("date", [None])[0]
        
        data = get_courts_for_date(date_str)
        
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))
