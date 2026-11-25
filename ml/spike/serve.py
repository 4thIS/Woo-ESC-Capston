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

    def translate_path(self, path: str) -> str:
        # WebLLM 은 모델 주소 뒤에 HF 형식 'resolve/main/' 을 붙인다(cleanModelUrl).
        # 로컬 변환본(models/<폴더>/)을 그대로 쓰도록 그 조각을 지운다.
        return super().translate_path(path.replace("/resolve/main/", "/", 1))


if __name__ == "__main__":
    handler = functools.partial(Handler, directory=str(HERE))
    with http.server.ThreadingHTTPServer(("127.0.0.1", 8080), handler) as srv:
        print("http://localhost:8080")
        srv.serve_forever()
