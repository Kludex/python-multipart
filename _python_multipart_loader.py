from __future__ import annotations

# The purpose of this file is to allow `import multipart` to continue to work
# unless `multipart` (the PyPI package) is also installed, in which case
# a collision is avoided, and `import multipart` is no longer injected.
import importlib
import importlib.abc
import importlib.machinery
import importlib.util
import sys
import warnings


class PythonMultipartCompatFinder(importlib.abc.MetaPathFinder):
    def find_spec(
        self, fullname: str, path: object = None, target: object = None
    ) -> importlib.machinery.ModuleSpec | None:
        if fullname != "multipart":
            return None
        old_sys_meta_path = sys.meta_path
        try:
            sys.meta_path = [p for p in sys.meta_path if not isinstance(p, type(self))]
            if multipart := importlib.util.find_spec("multipart"):
                return multipart

            warnings.warn("Please use `import python_multipart` instead.", FutureWarning, stacklevel=2)
            sys.modules["multipart"] = importlib.import_module("python_multipart")
            return importlib.util.find_spec("python_multipart")
        finally:
            sys.meta_path = old_sys_meta_path


def install() -> None:
    sys.meta_path.insert(0, PythonMultipartCompatFinder())


install()
