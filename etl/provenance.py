"""Registro de proveniência dos arquivos brutos.

Toda vez que um arquivo entra em `data/raw/`, uma entrada é gravada em
`data/raw/metadata.json` com origem, data/hora do download e hash do conteúdo.
Isso permite auditar depois de onde veio cada dado e detectar se a fonte mudou
entre duas execuções do pipeline.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from etl.paths import METADATA, ROOT


def sha256(path: Path) -> str:
    """Hash SHA-256 do arquivo, lido em blocos para não carregar tudo na RAM."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc_now() -> str:
    """Timestamp ISO-8601 em UTC, para não depender do fuso da máquina."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load() -> dict[str, Any]:
    """Lê o metadata.json existente, ou devolve um registro vazio."""
    if not METADATA.exists():
        return {"generated_at": None, "files": {}}
    with METADATA.open(encoding="utf-8") as handle:
        return json.load(handle)


def record(
    registry: dict[str, Any],
    path: Path,
    *,
    source: str,
    url: str,
    license_: str,
    attribution: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Adiciona (ou atualiza) a entrada de um arquivo no registro.

    A chave é o caminho relativo à raiz do repositório, em formato POSIX, para
    que o metadata.json fique idêntico no Windows e no Linux (o pipeline pode
    rodar tanto na máquina local quanto no GitHub Actions).

    `extra` carrega campos específicos da fonte. Para a Wikipédia é onde vai o
    `revision_id`: a licença CC BY-SA exige atribuir a revisão exata usada, e
    um artigo pode mudar entre duas execuções do scraping.
    """
    key = path.relative_to(ROOT).as_posix()
    entry = {
        "source": source,
        "url": url,
        "license": license_,
        "attribution": attribution,
        "downloaded_at": utc_now(),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }
    if extra:
        entry.update(extra)
    registry["files"][key] = entry
    return entry


def save(registry: dict[str, Any]) -> None:
    """Grava o registro, ordenado por caminho para gerar diffs limpos no git."""
    registry["generated_at"] = utc_now()
    registry["files"] = dict(sorted(registry["files"].items()))
    METADATA.parent.mkdir(parents=True, exist_ok=True)
    with METADATA.open("w", encoding="utf-8") as handle:
        json.dump(registry, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
