"""Rampas de cor do mapa, geradas a partir da cor de cada seleção.

O mapa deixou de usar uma rampa azul fixa: quando você escolhe uma seleção, o
coroplético de confronto direto passa a ser pintado **na cor daquela seleção** —
Brasil em amarelo, Itália em azzurro, Holanda em laranja.

Para isso, uma cor de camisa precisa virar uma **rampa sequencial**: uma
sequência de passos que vai de "quase nada" até "muito", com a claridade subindo
ou descendo de forma monótona. Claridade monótona é o que faz a rampa continuar
legível para quem tem daltonismo — o dado está codificado em claro/escuro, e o
matiz só carrega a identidade.

Fazer isso em RGB dá lama: interpolar `#FFDF00` (amarelo do Brasil) até o branco
em sRGB passa por bege sujo. Por isso o trabalho acontece em **OKLab/OKLCH**, um
espaço perceptualmente uniforme — a mesma diferença numérica de claridade parece
a mesma diferença para o olho, em qualquer matiz.

**Por que isto está em Python e não no JavaScript.** O front-end poderia gerar as
rampas em tempo de execução, mas isso significaria portar a matemática do OKLab
para o `map.js` — uma segunda implementação para manter em sincronia. Em vez
disso, os passos de cada rampa são calculados aqui e vão prontos no
`web/data/colors.json`; o navegador só interpola entre passos vizinhos, o que em
sRGB é seguro porque eles já estão perto um do outro.

Referência do OKLab: Björn Ottosson, https://bottosson.github.io/posts/oklab/
"""

from __future__ import annotations

import math

# Quantos passos cada rampa carrega. Nove é o suficiente para o navegador
# interpolar linearmente entre vizinhos sem que a curva apareça: a distância
# entre dois passos fica abaixo do limiar em que o olho percebe a quebra.
STOPS = 9

# As bandas de claridade de cada modo, em L do OKLab (0 = preto, 1 = branco).
#
# No claro a rampa vai de quase-branco a escuro; no escuro, o contrário. Em
# ambos, o passo que significa "quase nada" é o mais próximo da superfície da
# página, para o vazio recuar em vez de saltar. Os extremos não encostam em 1.0
# nem em 0.0: uma seleção pintada de branco puro sumiria dentro do continente
# vizinho, e o preto puro comeria as fronteiras.
BANDS = {
    "light": (0.965, 0.430),
    "dark": (0.235, 0.880),
}

# Croma mínimo para um matiz existir. Abaixo disto a cor lê como cinza — e cinza
# é a cor de "sem dado" no mapa, então uma rampa cinzenta seria ambígua.
MIN_CHROMA = 0.045

# Fração do croma que sobra no passo mais fraco da rampa, para "zero" não virar
# cinza e se confundir com "sem dado". Ver `ramp`.
CHROMA_FLOOR = 0.10


def _srgb_to_linear(channel: float) -> float:
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def _linear_to_srgb(channel: float) -> float:
    return 12.92 * channel if channel <= 0.0031308 else 1.055 * channel ** (1 / 2.4) - 0.055


def _cbrt(value: float) -> float:
    # `value ** (1/3)` levanta erro para negativo em Python (ao contrário do
    # `Math.cbrt` do JavaScript), e o `a`/`b` do OKLab são frequentemente
    # negativos.
    return math.copysign(abs(value) ** (1 / 3), value)


def hex_to_oklch(value: str) -> tuple[float, float, float]:
    """`#RRGGBB` -> (claridade, croma, matiz em graus)."""
    value = value.lstrip("#")
    rgb = [_srgb_to_linear(int(value[i:i + 2], 16) / 255) for i in (0, 2, 4)]
    red, green, blue = rgb

    long_ = _cbrt(0.4122214708 * red + 0.5363325363 * green + 0.0514459929 * blue)
    medium = _cbrt(0.2119034982 * red + 0.6806995451 * green + 0.1073969566 * blue)
    short = _cbrt(0.0883024619 * red + 0.2817188376 * green + 0.6299787005 * blue)

    lightness = 0.2104542553 * long_ + 0.7936177850 * medium - 0.0040720468 * short
    green_red = 1.9779984951 * long_ - 2.4285922050 * medium + 0.4505937099 * short
    blue_yellow = 0.0259040371 * long_ + 0.7827717662 * medium - 0.8086757660 * short

    chroma = math.hypot(green_red, blue_yellow)
    hue = math.degrees(math.atan2(blue_yellow, green_red)) % 360
    return lightness, chroma, hue


def _oklch_to_rgb(lightness: float, chroma: float, hue: float) -> tuple[float, float, float]:
    green_red = chroma * math.cos(math.radians(hue))
    blue_yellow = chroma * math.sin(math.radians(hue))

    long_ = (lightness + 0.3963377774 * green_red + 0.2158037573 * blue_yellow) ** 3
    medium = (lightness - 0.1055613458 * green_red - 0.0638541728 * blue_yellow) ** 3
    short = (lightness - 0.0894841775 * green_red - 1.2914855480 * blue_yellow) ** 3

    return (
        4.0767416621 * long_ - 3.3077115913 * medium + 0.2309699292 * short,
        -1.2684380046 * long_ + 2.6097574011 * medium - 0.3413193965 * short,
        -0.0041960863 * long_ - 0.7034186147 * medium + 1.7076147010 * short,
    )


def oklch_to_hex(lightness: float, chroma: float, hue: float) -> str:
    """OKLCH -> `#RRGGBB`, reduzindo o croma até a cor caber em sRGB.

    Nem todo par (claridade, croma) existe em sRGB: um amarelo muito escuro e
    muito saturado não tem representação. Clampar os canais direto distorceria o
    matiz — um amarelo viraria laranja. Reduzir o croma preserva matiz e
    claridade, que são justamente o que a rampa precisa manter: identidade e
    ordem.
    """
    low, high = 0.0, chroma
    for _ in range(24):
        middle = (low + high) / 2
        if all(-1e-4 <= channel <= 1 + 1e-4 for channel in _oklch_to_rgb(lightness, middle, hue)):
            low = middle
        else:
            high = middle

    channels = _oklch_to_rgb(lightness, low, hue)
    return "#" + "".join(
        f"{round(255 * min(1.0, max(0.0, _linear_to_srgb(channel)))):02X}"
        for channel in channels
    )


def ramp(base: str, mode: str, stops: int = STOPS) -> list[str]:
    """Uma cor de camisa -> uma rampa sequencial de `stops` passos.

    A claridade percorre a banda do modo linearmente — é ela que carrega o dado.
    O croma sobe junto, do fraco ao cheio, sem passar do croma da própria cor da
    seleção: é isso que mantém a rampa reconhecível como *aquela* seleção.

    O croma da ponta vazia não é zero, e o motivo é o mapa. Zero é uma cor e
    "sem dado" é outra — a seleção que jogou e não marcou não pode parecer a
    seleção que nunca jogou. Se o passo mais fraco fosse acromático, ele viraria
    um cinza quase igual ao cinza de fora do dado. Com um traço do matiz, o zero
    lê como "quase nada *desta* seleção" e o cinza continua significando "nada".
    """
    _, chroma, hue = hex_to_oklch(base)
    first, last = BANDS[mode]

    out = []
    for index in range(stops):
        position = index / (stops - 1)
        lightness = first + (last - first) * position
        weight = max(CHROMA_FLOOR, min(1.0, position * 1.45) ** 0.85)
        out.append(oklch_to_hex(lightness, chroma * weight, hue))
    return out
