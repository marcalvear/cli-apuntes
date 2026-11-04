"""Tests del esquema de acciones.json: qué se acepta y cómo se explica lo que no."""

import json
from pathlib import Path
from typing import Any

import pytest

from apuntes.config import (
    AccionBorrar,
    AccionMover,
    Configuracion,
    localizar,
)
from apuntes.errores import AccionNoValida, ConfigError

RAIZ = Path(__file__).parent.parent
PLANTILLA = RAIZ / "src" / "apuntes" / "plantillas" / "acciones.json"


def config(*acciones: dict[str, Any], **extra: Any) -> str:
    """Construye el texto de un acciones.json mínimo con las acciones dadas."""
    return json.dumps({"version": 1, "acciones": list(acciones), **extra})


def mover(**cambios: Any) -> dict[str, Any]:
    return {"nombre": "mover-pdf", "descripcion": "d", "tipo": "mover", "destino": "PDF"} | cambios


def problemas_de(texto: str) -> list[str]:
    with pytest.raises(ConfigError) as error:
        Configuracion.desde_texto(texto)
    assert error.value.codigo_salida == 3
    return error.value.problemas


# --- Camino feliz -----------------------------------------------------------


def test_la_plantilla_de_ejemplo_es_valida() -> None:
    configuracion = Configuracion.desde_fichero(PLANTILLA)
    assert len(configuracion.acciones) >= 5
    assert sum(a.USA_IA for a in configuracion.acciones) >= 2


def test_el_acciones_json_del_repo_es_la_plantilla() -> None:
    """El acciones.json de la raíz y el que crea `apuntes init` no deben divergir."""
    assert (RAIZ / "acciones.json").read_text("utf-8") == PLANTILLA.read_text("utf-8")


def test_el_tipo_decide_el_modelo() -> None:
    texto = config(mover(), {"nombre": "b", "descripcion": "d", "tipo": "borrar"})
    primera, segunda = Configuracion.desde_texto(texto).acciones
    assert isinstance(primera, AccionMover)
    assert isinstance(segunda, AccionBorrar)


def test_las_extensiones_se_normalizan() -> None:
    texto = config(mover(filtro={"extensiones": ["PDF", ".Docx", " txt "]}))
    accion = Configuracion.desde_texto(texto).acciones[0]
    assert accion.filtro.extensiones == [".pdf", ".docx", ".txt"]


def test_las_destructivas_confirman_por_defecto_y_se_puede_desactivar() -> None:
    texto = config(
        {"nombre": "a", "descripcion": "d", "tipo": "borrar"},
        {"nombre": "b", "descripcion": "d", "tipo": "borrar", "confirmar": False},
        mover(),
    )
    a, b, c = Configuracion.desde_texto(texto).acciones
    assert a.debe_confirmar is True
    assert b.debe_confirmar is False
    assert c.debe_confirmar is False


def test_archivar_solo_es_destructiva_si_borra_los_originales() -> None:
    base = {"descripcion": "d", "tipo": "archivar", "destino": "a.zip"}
    texto = config({"nombre": "a", **base}, {"nombre": "b", **base, "borrar_originales": True})
    a, b = Configuracion.desde_texto(texto).acciones
    assert (a.debe_confirmar, b.debe_confirmar) == (False, True)


def test_pipeline_se_expande_en_sus_pasos() -> None:
    texto = config(
        mover(),
        {"nombre": "b", "descripcion": "d", "tipo": "borrar"},
        {"nombre": "todo", "descripcion": "d", "tipo": "pipeline", "pasos": ["b", "mover-pdf"]},
    )
    configuracion = Configuracion.desde_texto(texto)
    pasos = list(configuracion.pasos_de(configuracion.accion("todo")))
    assert [p.nombre for p in pasos] == ["b", "mover-pdf"]


# --- Casos feos: cada error dice qué campo falla ----------------------------


def test_json_mal_escrito_indica_linea_y_columna() -> None:
    with pytest.raises(ConfigError, match=r"falta una coma \(línea 3, columna 3\)"):
        Configuracion.desde_texto('{\n  "version": 1\n  "acciones": []\n}')


def test_version_desconocida_se_rechaza_con_mensaje_claro() -> None:
    with pytest.raises(ConfigError, match="versión de esquema 2"):
        Configuracion.desde_texto('{"version": 2, "acciones": []}')


def test_la_raiz_debe_ser_un_objeto() -> None:
    with pytest.raises(ConfigError, match="objeto JSON"):
        Configuracion.desde_texto("[]")


def test_errata_en_un_campo_se_detecta() -> None:
    accion = mover()
    accion["destnio"] = accion.pop("destino")
    assert problemas_de(config(accion)) == [
        "acciones[0] (mover-pdf).destino: falta este campo obligatorio",
        "acciones[0] (mover-pdf).destnio: campo desconocido (¿una errata?)",
    ]


def test_tipo_desconocido_lista_los_validos() -> None:
    (problema,) = problemas_de(config(mover(tipo="teletransportar")))
    assert problema.startswith("acciones[0] (mover-pdf): tipo desconocido; válidos: mover,")


def test_extensiones_que_no_son_lista() -> None:
    (problema,) = problemas_de(config(mover(filtro={"extensiones": ".pdf"})))
    assert problema == "acciones[0] (mover-pdf).filtro.extensiones: debe ser una lista [ ... ]"


def test_regex_invalida() -> None:
    (problema,) = problemas_de(config(mover(filtro={"patron": "(["})))
    assert "filtro.patron: no es una expresión regular válida" in problema


def test_dias_negativos() -> None:
    (problema,) = problemas_de(config(mover(filtro={"mas_antiguo_que_dias": -1})))
    assert problema.endswith("filtro.mas_antiguo_que_dias: no puede ser negativo")


def test_nombre_con_mayusculas_o_espacios() -> None:
    (problema,) = problemas_de(config(mover(nombre="Mover PDF")))
    assert problema.startswith("acciones[0] (Mover PDF).nombre: solo minúsculas")


def test_marcador_desconocido_en_plantilla() -> None:
    accion = {"nombre": "r", "descripcion": "d", "tipo": "renombrar", "plantilla": "{autor}{ext}"}
    (problema,) = problemas_de(config(accion))
    assert "marcador desconocido {autor}" in problema


def test_nombres_repetidos() -> None:
    (problema,) = problemas_de(config(mover(), mover()))
    assert problema == "general: nombres de acción repetidos: mover-pdf"


def test_pipeline_con_paso_inexistente() -> None:
    pipeline = {"nombre": "p", "descripcion": "d", "tipo": "pipeline", "pasos": ["mover-pdf", "x"]}
    (problema,) = problemas_de(config(mover(), pipeline))
    assert "usa 'x', que no existe" in problema


def test_asignatura_en_destino_sin_lista_de_asignaturas() -> None:
    (problema,) = problemas_de(config(mover(destino="Apuntes/{asignatura}")))
    assert "falta la lista 'asignaturas'" in problema


def test_lista_de_acciones_vacia() -> None:
    assert problemas_de(config()) == ["acciones: no puede estar vacío"]


def test_se_informan_todos_los_problemas_a_la_vez() -> None:
    malo = mover(nombre="MAL", descripcion="", filtro={"extensiones": "pdf"})
    assert len(problemas_de(config(malo))) == 3


# --- Fichero y búsqueda -----------------------------------------------------


def test_fichero_inexistente_sugiere_init(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="No encuentro") as error:
        Configuracion.desde_fichero(tmp_path / "acciones.json")
    assert "apuntes init" in (error.value.pista or "")


def test_fichero_que_no_es_utf8(tmp_path: Path) -> None:
    ruta = tmp_path / "acciones.json"
    ruta.write_bytes(b"\xff\xfe\x00basura")
    with pytest.raises(ConfigError, match="UTF-8"):
        Configuracion.desde_fichero(ruta)


def test_accion_inexistente_sugiere_las_disponibles() -> None:
    configuracion = Configuracion.desde_texto(config(mover()))
    with pytest.raises(AccionNoValida) as error:
        configuracion.accion("volar")
    assert "mover-pdf" in (error.value.pista or "")


def test_localizar_respeta_la_prioridad(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))  # Windows
    monkeypatch.delenv("APUNTES_CONFIG", raising=False)
    trabajo = tmp_path / "trabajo"
    trabajo.mkdir()

    # Sin nada: apunta a ./acciones.json (para que el error lo nombre).
    assert localizar(cwd=trabajo) == trabajo / "acciones.json"

    # La del usuario se usa si no hay local.
    usuario = tmp_path / "home" / ".config" / "apuntes" / "acciones.json"
    usuario.parent.mkdir(parents=True)
    usuario.write_text("{}", encoding="utf-8")
    assert localizar(cwd=trabajo) == usuario

    # La local gana a la del usuario.
    (trabajo / "acciones.json").write_text("{}", encoding="utf-8")
    assert localizar(cwd=trabajo) == trabajo / "acciones.json"

    # La variable de entorno gana a la local, y --config gana a todo.
    monkeypatch.setenv("APUNTES_CONFIG", str(tmp_path / "entorno.json"))
    assert localizar(cwd=trabajo) == tmp_path / "entorno.json"
    assert localizar(tmp_path / "explicita.json", cwd=trabajo) == tmp_path / "explicita.json"
