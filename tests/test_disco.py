from pathlib import Path

import pytest

from apuntes import disco
from apuntes.disco import escribir_atomico


def test_escribe_y_crea_carpetas(tmp_path: Path) -> None:
    ruta = tmp_path / "a" / "b" / "nota.md"
    escribir_atomico(ruta, "hola")
    assert ruta.read_text("utf-8") == "hola"


def test_sobrescribe_el_contenido_anterior(tmp_path: Path) -> None:
    ruta = tmp_path / "nota.md"
    ruta.write_text("viejo", encoding="utf-8")
    escribir_atomico(ruta, b"nuevo")
    assert ruta.read_bytes() == b"nuevo"


def test_si_falla_a_medias_el_original_queda_intacto(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulamos un fallo justo antes de reemplazar: no debe perderse nada."""
    ruta = tmp_path / "importante.md"
    ruta.write_text("contenido original", encoding="utf-8")

    def replace_roto(*_: object) -> None:
        raise OSError("disco lleno")

    monkeypatch.setattr(disco.os, "replace", replace_roto)
    with pytest.raises(OSError, match="disco lleno"):
        escribir_atomico(ruta, "contenido nuevo")

    assert ruta.read_text(encoding="utf-8") == "contenido original"
    assert list(tmp_path.iterdir()) == [ruta]  # el temporal se ha limpiado
