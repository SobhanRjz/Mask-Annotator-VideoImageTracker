CATALOG = {
    'tiny': {
        'key': 'tiny',
        'label': 'Tiny',
        'model_id': 'facebook/sam2.1-hiera-tiny',
        'filename': 'sam2.1_hiera_tiny.pt',
        'note': None,
    },
    'small': {
        'key': 'small',
        'label': 'Small',
        'model_id': 'facebook/sam2.1-hiera-small',
        'filename': 'sam2.1_hiera_small.pt',
        'note': None,
    },
    'balanced': {
        'key': 'balanced',
        'label': 'Balanced',
        'model_id': 'facebook/sam2.1-hiera-base-plus',
        'filename': 'sam2.1_hiera_base_plus.pt',
        'note': None,
    },
    'large': {
        'key': 'large',
        'label': 'Large',
        'model_id': 'facebook/sam2.1-hiera-large',
        'filename': 'sam2.1_hiera_large.pt',
        'note': 'May not fit 8 GB GPUs.',
    },
}

DEFAULT_KEY = 'small'


def catalog_entry(key: str):
    entry = CATALOG.get(key)
    if not entry:
        raise ValueError(f'Unknown model: {key}')
    return entry


def key_for_model_id(model_id: str):
    for key, entry in CATALOG.items():
        if entry['model_id'] == model_id:
            return key
    return DEFAULT_KEY


def resolve_saved(saved: str | None, fallback_id: str | None = None):
    if saved:
        try:
            entry = catalog_entry(saved)
            return entry['key'], entry['model_id']
        except ValueError:
            pass
    key = key_for_model_id(fallback_id or CATALOG[DEFAULT_KEY]['model_id'])
    return key, catalog_entry(key)['model_id']


def checkpoint_cached(key: str):
    from huggingface_hub import try_to_load_from_cache

    entry = catalog_entry(key)
    path = try_to_load_from_cache(entry['model_id'], entry['filename'])
    return isinstance(path, str)


def ensure_checkpoint(key: str, progress=None):
    from huggingface_hub import hf_hub_download, try_to_load_from_cache
    from huggingface_hub.utils import tqdm as hf_tqdm

    entry = catalog_entry(key)
    cached = try_to_load_from_cache(entry['model_id'], entry['filename'])
    if isinstance(cached, str):
        if progress:
            progress(1, 1)
        return cached

    class ProgressBar(hf_tqdm):
        def update(self, n=1):
            super().update(n)
            if progress and self.total:
                progress(self.n, self.total)

    kwargs = {
        'repo_id': entry['model_id'],
        'filename': entry['filename'],
    }
    try:
        path = hf_hub_download(tqdm_class=ProgressBar, **kwargs)
    except TypeError:
        path = hf_hub_download(**kwargs)
        if progress:
            progress(1, 1)
    return path
