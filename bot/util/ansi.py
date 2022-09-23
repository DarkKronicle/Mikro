# https://gist.github.com/kkrypt0nn/a02506f3712ff2d1c8ca7c9e0aed7c06


ESCAPE = '\u001b'
NORMAL = 0
BOLD = 1
UNDERLINE = 4

FORMAT_STR = '\u001b[{values}m'

GRAY = 30
RED = 31
GREEN = 32
YELLOW = 33
BLUE = 34
PINK = 35
CYAN = 36
WHITE = 37

BG_FIREFLY_DARK_BLUE = 40
BG_ORANGE = 41
BG_MARBLE_BLUE = 42
BG_GRAYISH_TURQUOISE = 43
BG_GRAY = 44
BG_INDIGO = 45
BG_LIGHT_GRAY = 46
BG_WHITE = 47

RESET = ESCAPE + '[0m'


def format_attributes(*attributes: int):
    new_attrs = []
    found_base = False
    for attr in attributes:
        if attr is None:
            continue
        if attr < 5:
            found_base = True
            new_attrs.insert(0, str(attr))
        elif attr < 37:
            new_attrs.insert(1, str(attr))
        else:
            new_attrs.append(str(attr))
    if not found_base:
        new_attrs.insert(0, str(NORMAL))
    return FORMAT_STR.format(values=';'.join(new_attrs))
