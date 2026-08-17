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

E por uma segunda linha, que custou uma tarde: `Cache-Control: no-store`.

O `SimpleHTTPRequestHandler` manda `Last-Modified` e mais nada. Sem
`Cache-Control`, o navegador cai na heurística do RFC 9111 e reaproveita o
arquivo por cerca de 10% do tempo desde a última modificação, **sem revalidar**
— num `style.css` salvo há três horas, quase vinte minutos servindo a versão
velha. O efeito é o pior possível numa ferramenta de desenvolvimento: você
edita, recarrega, e vê exatamente o que via antes. O bug parece não ter sido
corrigido; o que não foi atualizado é o arquivo.

`no-store` só vale aqui. Em produção o site é estático no GitHub Pages, que
manda o cabeçalho dele e não passa por este arquivo.
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

    def end_headers(self) -> None:
        # Recarregar tem que mostrar o arquivo que está no disco agora. Ver a
        # nota no topo: sem isto o navegador serve a versão anterior por vários
        # minutos e a edição parece não ter surtido efeito.
        self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()

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
