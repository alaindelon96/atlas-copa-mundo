"""Caminhos do projeto, resolvidos a partir da raiz do repositório.

Centralizar isso aqui evita caminhos relativos frágeis espalhados pelos scripts:
qualquer módulo do ETL funciona independentemente de onde foi invocado.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DATA = ROOT / "data"
RAW = DATA / "raw"
RAW_FJELSTUL = RAW / "fjelstul"
RAW_KAGGLE = RAW / "kaggle"
RAW_SCRAPED = RAW / "scraped"
RAW_NATURALEARTH = RAW / "naturalearth"
INTERIM = DATA / "interim"
PROCESSED = DATA / "processed"

REFERENCE = ROOT / "reference"

WEB = ROOT / "web"
WEB_DATA = WEB / "data"

METADATA = RAW / "metadata.json"

# Cache das respostas do Nominatim. Fica em `interim/` mas é versionado (ver
# .gitignore): sem ele, quem clonar o repositório precisa de ~5 minutos de
# requisições a um serviço público e gratuito só para reproduzir o mesmo
# resultado.
GEOCODE_CACHE = INTERIM / "geocode_cache.json"


def ensure_dirs() -> None:
    """Cria os diretórios de dados, caso ainda não existam."""
    for directory in (
        RAW_FJELSTUL,
        RAW_KAGGLE,
        RAW_SCRAPED,
        RAW_NATURALEARTH,
        INTERIM,
        PROCESSED,
        WEB_DATA,
    ):
        directory.mkdir(parents=True, exist_ok=True)
