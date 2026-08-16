"""Servidor local para `web/`.

    python serve.py            # http://localhost:8000
    python serve.py 8080

Existe por uma linha só: `protocol_version = "HTTP/1.1"`.

O `python -m http.server --directory web` do README funcionava para tudo,
menos para o arquivo que mais importa. O `SimpleHTTPRequestHandler` fala
HTTP/1.0 por padrão e fecha a conexão a cada resposta; o navegador pede os oito
JSONs em paralelo e reaproveita conexões, e no Windows a combinação derrubava o
`countries.geojson` (1,7 MB) no meio da transferência — `ERR_CONNECTION_RESET`
depois de ~19 s, com o arquivo truncado. O mapa abria sem nenhum país e sem
nenhum erro que apontasse para o servidor.

Em HTTP/1.1 o `Content-Length` delimita a resposta e a conexão sobrevive à
próxima requisição, que é o que os oito `fetch()` do `map.js` esperam.

Isto é ferramenta de desenvolvimento. Em produção o site é estático no GitHub
Pages e não passa por aqui.
"""

from __future__ import annotations

import contextlib
import http.server
import socket
import sys
from functools import partial

from etl.paths import ROOT

WEB = ROOT / "web"


class Handler(http.server.SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:  # noqa: A002
        # O padrão imprime IP e data em toda requisição, e uma página que baixa
        # 80 bandeiras vira 80 linhas de ruído.
        if args and str(args[1]).startswith(("2", "3")):
            return
        super().log_message(fmt, *args)


class Server(http.server.ThreadingHTTPServer):
    # Sem isto, reiniciar o servidor logo depois de parar esbarra no TIME_WAIT
    # da porta e falha com "address already in use".
    allow_reuse_address = True
    daemon_threads = True


def main(argv: list[str]) -> int:
    port = int(argv[0]) if argv else 8000
    handler = partial(Handler, directory=str(WEB))
    with Server(("", port), handler) as httpd:
        host = socket.gethostname()
        print(f"Atlas da Copa do Mundo — servindo {WEB.relative_to(ROOT)}/")
        print(f"  http://localhost:{port}/   (também em {host}:{port}, para testar no celular)")
        print("  Ctrl+C para parar.")
        with contextlib.suppress(KeyboardInterrupt):
            httpd.serve_forever()
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
