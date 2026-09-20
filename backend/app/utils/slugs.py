import re
import unicodedata


def slugify(name: str) -> str:
    text = unicodedata.normalize('NFKD', name or '')
    text = text.encode('ascii', 'ignore').decode('ascii').lower()
    text = re.sub(r'[^a-z0-9]+', '-', text).strip('-')
    return text[:80] or 'project'


def allocate_slug(existing, name: str) -> str:
    used = {item for item in existing if item}
    base = slugify(name)
    slug = base
    index = 2
    while slug in used:
        slug = f'{base}-{index}'
        index += 1
    return slug


def allocate_name(existing, name: str) -> str:
    used = {(item or '').casefold() for item in existing if item}
    text = (name or '').strip() or 'Project'
    if text.casefold() not in used:
        return text
    base = f'{text} (recovered)'
    candidate = base
    index = 2
    while candidate.casefold() in used:
        candidate = f'{text} (recovered {index})'
        index += 1
    return candidate
