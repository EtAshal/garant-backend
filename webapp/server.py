from http.server import HTTPServer, SimpleHTTPRequestHandler
import os

class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('ngrok-skip-browser-warning', 'true')
        self.send_header('Access-Control-Allow-Origin', '*')
        super().end_headers()
    
    def log_message(self, format, *args):
        pass

os.chdir(os.path.dirname(os.path.abspath(__file__)))

if __name__ == '__main__':
    server = HTTPServer(('', 8000), Handler)
    print('Сервер запущен на порту 8000')
    server.serve_forever()