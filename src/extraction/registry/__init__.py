"""Bootstrap the extraction registry with default document definitions."""

from importlib import import_module
from pkgutil import iter_modules


def _import_registration_modules() -> None:
    # Import every module in this package so their module-level side effects run.
    prefix = f'{__name__}.'
    for module_info in iter_modules(__path__, prefix):  # type: ignore[name-defined]
        module_name = module_info.name
        if module_name.endswith('.registry'):
            continue
        import_module(module_name)


_import_registration_modules()
