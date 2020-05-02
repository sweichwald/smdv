import importlib


class limport:

    def __init__(self, package):
        self._package = package

    def __getattr__(self, get):
        if isinstance(self._package, str):
            self._package = importlib.import_module(self._package)
        return getattr(self._package, get)
