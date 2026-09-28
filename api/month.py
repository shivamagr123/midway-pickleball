from http.server import BaseHTTPRequestHandler
import urllib.parse
import json
from datetime import datetime
from .common import get_month_data, EDT

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        
        now = datetime.now(EDT)
        year = int(params.get("year", [now.year])[0])
        month = int(params.get("month", [now.month])[0])
        
        data = get_month_data(year, month)
        
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))
