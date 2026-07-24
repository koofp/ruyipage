"""Load reg-factory get_graph_token() without mutating sys.path."""

import importlib.util
import os

_REG_FACTORY = os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "..", "reg-factory", "extract_graph_tokens.py",
))

if not os.path.isfile(_REG_FACTORY):
    raise ImportError("reg-factory extractor was not found: {}".format(_REG_FACTORY))

_spec = importlib.util.spec_from_file_location(
    "_reg_factory_extract_graph_tokens", _REG_FACTORY
)
if _spec is None or _spec.loader is None:
    raise ImportError("could not create module spec for: {}".format(_REG_FACTORY))

_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

get_graph_token = _mod.get_graph_token
