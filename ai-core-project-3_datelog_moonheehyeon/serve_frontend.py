"""프론트엔드 전용 서버: 프로젝트의 설정·DB·소스는 제공하지 않는다."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

INDEX = Path(__file__).resolve().with_name('index.html')


class FrontendHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if urlsplit(self.path).path not in {'/', '/index.html'}:
            self.send_error(404, 'Not Found')
            return
        body = INDEX.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


if __name__ == '__main__':
    print('DateLog 화면: http://localhost:5500')
    server = ThreadingHTTPServer(('127.0.0.1', 5500), FrontendHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
