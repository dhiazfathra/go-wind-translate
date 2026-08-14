"""Offline zh->en. No network, no quota, no cost. Quality below DeepL."""
from __future__ import annotations


class ArgosEngine:
    name = "argos"

    def __init__(self) -> None:
        import argostranslate.package as pkg
        import argostranslate.translate as tr
        installed = {lang.code for lang in tr.get_installed_languages()}
        if "zh" not in installed or "en" not in installed:
            pkg.update_package_index()
            cand = [p for p in pkg.get_available_packages()
                    if p.from_code == "zh" and p.to_code == "en"]
            if not cand:
                raise RuntimeError("no zh->en Argos package available")
            pkg.install_from_path(cand[0].download())
        self._tr = tr

    def translate(self, texts: list[str]) -> list[str]:
        return [self._tr.translate(t, "zh", "en") for t in texts]
