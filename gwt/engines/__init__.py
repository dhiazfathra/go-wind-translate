"""Translation engines behind one protocol."""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Engine(Protocol):
    name: str

    def translate(self, texts: list[str]) -> list[str]:
        """Return one output per input. Empty string means 'no translation'."""
        ...


def get_engine(name: str, **kwargs) -> Engine:
    if name == "dictionary":
        from gwt.engines.dictionary import DictionaryEngine
        return DictionaryEngine(**kwargs)
    if name == "deepl":
        from gwt.engines.deepl_engine import DeepLEngine
        return DeepLEngine(**kwargs)
    if name == "argos":
        from gwt.engines.argos_engine import ArgosEngine
        return ArgosEngine(**kwargs)
    raise ValueError(f"unknown engine: {name}")
