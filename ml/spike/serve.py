"""하네스 로컬 서버 — python ml/spike/serve.py → http://localhost:8080 (localhost 는 WebGPU 보안 문맥)."""

import functools
import http.server
import pathlib

HERE = pathlib.Path(__file__).parent


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "credentialless")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


if __name__ == "__main__":
    handler = functools.partial(Handler, directory=str(HERE))
    with http.server.ThreadingHTTPServer(("127.0.0.1", 8080), handler) as srv:
        print("http://localhost:8080")
        srv.serve_forever()
