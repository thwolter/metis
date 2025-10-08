__all__ = [
    'pg_connect',
    'get_collection_uuid',
    'get_vectorstore',
]


def __getattr__(name):
    if name in __all__:
        from . import vstore
        return getattr(vstore, name)
    raise AttributeError(name)
