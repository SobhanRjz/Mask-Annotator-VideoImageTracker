PALETTE = [
    '#51B56D', '#E45B5B', '#F29D49', '#9A73E8', '#4FA3E3',
    '#D85883', '#D4B03D', '#5FC6B0', '#F06292', '#26A69A',
    '#FF8A65', '#7E57C2', '#29B6F6', '#9CCC65', '#FF7043',
    '#5C6BC0', '#26C6DA', '#EC407A', '#8D6E63', '#42A5F5',
    '#66BB6A', '#FFA726', '#AB47BC', '#78909C',
]


def normalize_hex(color: str) -> str:
    value = (color or '').strip().lstrip('#')
    if len(value) == 3:
        value = ''.join(ch * 2 for ch in value)
    if len(value) != 6:
        raise ValueError('Color must be a 6-digit hex value')
    int(value, 16)
    return f'#{value.upper()}'


def _hsl_hex(hue: float, saturation: float, lightness: float) -> str:
    hue = hue % 360
    chroma = (1 - abs(2 * lightness - 1)) * saturation
    x = chroma * (1 - abs((hue / 60) % 2 - 1))
    m = lightness - chroma / 2
    if hue < 60:
        r, g, b = chroma, x, 0
    elif hue < 120:
        r, g, b = x, chroma, 0
    elif hue < 180:
        r, g, b = 0, chroma, x
    elif hue < 240:
        r, g, b = 0, x, chroma
    elif hue < 300:
        r, g, b = x, 0, chroma
    else:
        r, g, b = chroma, 0, x
    return '#{:02X}{:02X}{:02X}'.format(
        round((r + m) * 255),
        round((g + m) * 255),
        round((b + m) * 255),
    )


def unique_color(existing: list[str]) -> str:
    used = set()
    for color in existing:
        try:
            used.add(normalize_hex(color))
        except ValueError:
            continue
    for color in PALETTE:
        if color not in used:
            return color
    index = 0
    while index < 720:
        candidate = _hsl_hex(index * 137.508, 0.62, 0.52)
        if candidate not in used:
            return candidate
        index += 1
    return _hsl_hex(index * 137.508, 0.62, 0.52)


def ensure_unique(color: str, existing: list[str]) -> str:
    used = set()
    for item in existing:
        try:
            used.add(normalize_hex(item))
        except ValueError:
            continue
    try:
        candidate = normalize_hex(color)
    except ValueError:
        return unique_color(list(used))
    if candidate not in used:
        return candidate
    hue = 0
    while hue < 360:
        shifted = _hsl_hex(hue, 0.62, 0.52)
        if shifted not in used:
            return shifted
        hue += 11
    return unique_color(list(used))
