"""Tests del motor y de cada tipo de acción, de principio a fin, en carpetas temporales."""

import json
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from apuntes.acciones import tipos_ejecutables
from apuntes.config import TIPOS_ACCION, Configuracion
from apuntes.errores import CarpetaNoValida, EjecucionInterrumpida
from apuntes.motor import Motor, Plan
from apuntes.operaciones import EnviarAPapelera, Mover
from tests.conftest import PapeleraFalsa, crear_fichero

AHORA = datetime(2026, 11, 4, 12, 0)
ASIGNATURAS = [
    {"nombre": "Programacion", "palabras_clave": ["java", "poo"]},
    {"nombre": "Bases de Datos", "palabras_clave": ["sql", "bd"]},
]


def motor(papelera: PapeleraFalsa, *acciones: dict[str, Any]) -> Motor:
    texto = json.dumps({"version": 1, "asignaturas": ASIGNATURAS, "acciones": list(acciones)})
    return Motor(Configuracion.desde_texto(texto), papelera=papelera, ahora=AHORA)


def accion(nombre: str, tipo: str, **campos: Any) -> dict[str, Any]:
    return {"nombre": nombre, "descripcion": "d", "tipo": tipo, **campos}


def dias(n: int) -> datetime:
    return AHORA - timedelta(days=n)


def relativos(carpeta: Path) -> list[str]:
    return sorted(p.relative_to(carpeta).as_posix() for p in carpeta.rglob("*") if p.is_file())


def ejecutar(m: Motor, nombre: str, carpeta: Path) -> Plan:
    plan = m.planificar(nombre, carpeta)
    m.aplicar(plan)
    return plan


def test_todos_los_tipos_tienen_clase_salvo_pipeline() -> None:
    """pipeline no se ejecuta: el motor lo expande en sus pasos."""
    assert tipos_ejecutables() == set(TIPOS_ACCION) - {"pipeline"}


# --- Planificar no toca nada ------------------------------------------------


def test_planificar_no_modifica_el_disco(tmp_path: Path, papelera: PapeleraFalsa) -> None:
    crear_fichero(tmp_path / "a.tmp")
    crear_fichero(tmp_path / "Tema_java.pdf")
    antes = relativos(tmp_path)
    m = motor(
        papelera,
        accion("borrar", "borrar"),
        accion("mover", "mover", destino="Apuntes/{asignatura}"),
    )

    m.planificar("borrar", tmp_path)
    m.planificar("mover", tmp_path)

    assert relativos(tmp_path) == antes
    assert papelera.recibidos == []


# --- Filtro -----------------------------------------------------------------


def test_filtro_combina_extension_patron_y_antiguedad(
    tmp_path: Path, papelera: PapeleraFalsa
) -> None:
    crear_fichero(tmp_path / "viejo.tmp", fecha=dias(40))
    crear_fichero(tmp_path / "nuevo.tmp", fecha=dias(1))
    crear_fichero(tmp_path / "viejo.pdf", fecha=dias(40))
    crear_fichero(tmp_path / "~$viejo.docx", fecha=dias(40))
    crear_fichero(tmp_path / ".oculto.tmp", fecha=dias(40))  # los ocultos nunca se tocan
    m = motor(
        papelera,
        accion("a", "borrar", filtro={"patron": r"(\.tmp$|^~\$)", "mas_antiguo_que_dias": 30}),
    )

    ejecutar(m, "a", tmp_path)

    assert sorted(papelera.recibidos) == ["viejo.tmp", "~$viejo.docx"]


def test_filtro_recursivo(tmp_path: Path, papelera: PapeleraFalsa) -> None:
    crear_fichero(tmp_path / "a.tmp")
    crear_fichero(tmp_path / "sub" / "b.tmp")
    plano = motor(papelera, accion("a", "borrar")).planificar("a", tmp_path)
    recursivo = motor(papelera, accion("a", "borrar", filtro={"recursivo": True})).planificar(
        "a", tmp_path
    )
    assert len(plano.operaciones) == 1
    assert len(recursivo.operaciones) == 2


# --- Mover y copiar ---------------------------------------------------------


def test_mover_por_asignatura_y_dejar_los_dudosos(tmp_path: Path, papelera: PapeleraFalsa) -> None:
    crear_fichero(tmp_path / "Tema1 java.pdf")
    crear_fichero(tmp_path / "consultas sql.pdf")
    crear_fichero(tmp_path / "java y sql.pdf")  # empate
    crear_fichero(tmp_path / "documento.pdf")  # sin pistas
    m = motor(papelera, accion("ordenar", "mover", destino="Apuntes/{asignatura}"))

    plan = ejecutar(m, "ordenar", tmp_path)

    assert relativos(tmp_path) == [
        "Apuntes/Bases de Datos/consultas sql.pdf",
        "Apuntes/Programacion/Tema1 java.pdf",
        "documento.pdf",
        "java y sql.pdf",
    ]
    (paso,) = plan.pasos
    assert len(paso.avisos) == 2


def test_mover_con_nombre_ocupado_renombra_por_defecto(
    tmp_path: Path, papelera: PapeleraFalsa
) -> None:
    crear_fichero(tmp_path / "a.pdf", b"nuevo")
    crear_fichero(tmp_path / "PDF" / "a.pdf", b"viejo")
    m = motor(papelera, accion("m", "mover", destino="PDF"))

    ejecutar(m, "m", tmp_path)

    assert (tmp_path / "PDF" / "a.pdf").read_bytes() == b"viejo"
    assert (tmp_path / "PDF" / "a (2).pdf").read_bytes() == b"nuevo"


def test_mover_con_si_existe_saltar(tmp_path: Path, papelera: PapeleraFalsa) -> None:
    crear_fichero(tmp_path / "a.pdf", b"nuevo")
    crear_fichero(tmp_path / "PDF" / "a.pdf", b"viejo")
    m = motor(papelera, accion("m", "mover", destino="PDF", si_existe="saltar"))

    plan = ejecutar(m, "m", tmp_path)

    assert plan.vacio
    assert (tmp_path / "a.pdf").exists()
    assert "se salta" in plan.pasos[0].avisos[0]


def test_sobrescribir_es_destructivo_y_pide_confirmacion(
    tmp_path: Path, papelera: PapeleraFalsa
) -> None:
    crear_fichero(tmp_path / "a.pdf", b"nuevo")
    crear_fichero(tmp_path / "PDF" / "a.pdf", b"viejo")
    m = motor(papelera, accion("m", "mover", destino="PDF", si_existe="sobrescribir"))

    plan = m.planificar("m", tmp_path)

    assert plan.debe_confirmar  # mover no es destructivo... salvo que sobrescriba
    m.aplicar(plan)
    assert (tmp_path / "PDF" / "a.pdf").read_bytes() == b"nuevo"
    assert papelera.recibidos == ["a.pdf"]


def test_dos_ficheros_al_mismo_destino_no_chocan(tmp_path: Path, papelera: PapeleraFalsa) -> None:
    crear_fichero(tmp_path / "x" / "tema.pdf", b"1")
    crear_fichero(tmp_path / "y" / "tema.pdf", b"2")
    m = motor(papelera, accion("m", "mover", destino="Todo", filtro={"recursivo": True}))

    ejecutar(m, "m", tmp_path)

    assert sorted(p.name for p in (tmp_path / "Todo").iterdir()) == ["tema (2).pdf", "tema.pdf"]


def test_copiar_por_tipo(tmp_path: Path, papelera: PapeleraFalsa) -> None:
    crear_fichero(tmp_path / "a.pdf")
    crear_fichero(tmp_path / "b.pptx")
    m = motor(papelera, accion("c", "copiar", destino="Copia/{tipo}"))

    ejecutar(m, "c", tmp_path)

    assert relativos(tmp_path) == [
        "Copia/pdf/a.pdf",
        "Copia/presentación/b.pptx",
        "a.pdf",
        "b.pptx",
    ]


# --- Renombrar --------------------------------------------------------------


def test_renombrar_con_fecha_y_contador_en_orden_cronologico(
    tmp_path: Path, papelera: PapeleraFalsa
) -> None:
    crear_fichero(tmp_path / "zeta.pdf", fecha=datetime(2026, 10, 1))
    crear_fichero(tmp_path / "alfa.pdf", fecha=datetime(2026, 10, 2))
    m = motor(papelera, accion("r", "renombrar", plantilla="{fecha:%Y-%m-%d}_{n:02}_{nombre}{ext}"))

    ejecutar(m, "r", tmp_path)

    assert relativos(tmp_path) == ["2026-10-01_01_zeta.pdf", "2026-10-02_02_alfa.pdf"]


def test_renombrar_dos_veces_no_cambia_nada(tmp_path: Path, papelera: PapeleraFalsa) -> None:
    crear_fichero(tmp_path / "a.pdf", fecha=datetime(2026, 10, 1))
    m = motor(papelera, accion("r", "renombrar", plantilla="{fecha:%Y-%m-%d}{ext}"))
    ejecutar(m, "r", tmp_path)
    assert m.planificar("r", tmp_path).vacio


def test_renombrar_a_un_nombre_ocupado(tmp_path: Path, papelera: PapeleraFalsa) -> None:
    crear_fichero(tmp_path / "a.pdf", fecha=datetime(2026, 10, 1))
    crear_fichero(tmp_path / "b.pdf", fecha=datetime(2026, 10, 1))
    m = motor(papelera, accion("r", "renombrar", plantilla="{fecha:%Y-%m-%d}{ext}"))

    ejecutar(m, "r", tmp_path)

    assert relativos(tmp_path) == ["2026-10-01 (2).pdf", "2026-10-01.pdf"]


# --- Deduplicar -------------------------------------------------------------


def test_deduplicar_conserva_el_mas_antiguo(tmp_path: Path, papelera: PapeleraFalsa) -> None:
    crear_fichero(tmp_path / "tema.pdf", b"igual", fecha=dias(10))
    crear_fichero(tmp_path / "tema (1).pdf", b"igual", fecha=dias(1))
    crear_fichero(tmp_path / "sub" / "copia.pdf", b"igual", fecha=dias(5))
    crear_fichero(tmp_path / "otro.pdf", b"disti", fecha=dias(1))  # mismo tamaño, distinto
    m = motor(papelera, accion("d", "deduplicar", filtro={"recursivo": True}))

    plan = ejecutar(m, "d", tmp_path)

    assert relativos(tmp_path) == ["otro.pdf", "tema.pdf"]
    assert sorted(papelera.recibidos) == ["copia.pdf", "tema (1).pdf"]
    assert all(isinstance(op, EnviarAPapelera) for op in plan.operaciones)


# --- Archivar e índice ------------------------------------------------------


def test_archivar_y_quitar_originales(tmp_path: Path, papelera: PapeleraFalsa) -> None:
    crear_fichero(tmp_path / "viejo.pdf", b"V", fecha=dias(400))
    crear_fichero(tmp_path / "nuevo.pdf", b"N", fecha=dias(1))
    m = motor(
        papelera,
        accion(
            "arch",
            "archivar",
            destino="Archivo/antiguo-{fecha:%Y}.zip",
            filtro={"mas_antiguo_que_dias": 180},
            borrar_originales=True,
        ),
    )

    plan = ejecutar(m, "arch", tmp_path)

    assert plan.debe_confirmar
    assert relativos(tmp_path) == ["Archivo/antiguo-2026.zip", "nuevo.pdf"]
    with zipfile.ZipFile(tmp_path / "Archivo" / "antiguo-2026.zip") as zf:
        assert zf.read("viejo.pdf") == b"V"


def test_indice_agrupa_por_carpeta_y_es_idempotente(
    tmp_path: Path, papelera: PapeleraFalsa
) -> None:
    crear_fichero(tmp_path / "suelto.txt")
    crear_fichero(tmp_path / "Apuntes" / "Prog" / "tema 1.pdf")
    m = motor(papelera, accion("i", "indice", filtro={"recursivo": True}, titulo="Mis apuntes"))

    ejecutar(m, "i", tmp_path)

    indice = (tmp_path / "INDICE.md").read_text("utf-8")
    assert indice.startswith("# Mis apuntes\n")
    assert "## Apuntes/Prog" in indice
    assert "[tema 1.pdf](Apuntes/Prog/tema%201.pdf)" in indice  # enlace válido con espacios
    assert m.planificar("i", tmp_path).vacio  # repetir no cambia nada


# --- Pipeline ---------------------------------------------------------------


def test_pipeline_cada_paso_ve_el_resultado_del_anterior(
    tmp_path: Path, papelera: PapeleraFalsa
) -> None:
    crear_fichero(tmp_path / "Tema java.pdf", b"igual", fecha=dias(3))
    crear_fichero(tmp_path / "Tema java (1).pdf", b"igual", fecha=dias(1))
    crear_fichero(tmp_path / "basura.tmp")
    m = motor(
        papelera,
        accion("limpiar", "borrar", filtro={"extensiones": [".tmp"]}),
        accion("dedup", "deduplicar"),
        accion("ordenar", "mover", destino="Apuntes/{asignatura}"),
        accion("indice", "indice", filtro={"recursivo": True}),
        accion("todo", "pipeline", pasos=["limpiar", "dedup", "ordenar", "indice"]),
    )

    plan = m.planificar("todo", tmp_path)

    # Al planificar, el duplicado ya no se mueve (el paso 2 lo quita) y el índice
    # enlaza el fichero en su carpeta nueva, aunque todavía no se ha movido nada.
    assert [len(p.operaciones) for p in plan.pasos] == [1, 1, 1, 1]
    escribir = plan.pasos[3].operaciones[0]
    assert "Apuntes/Programacion/Tema%20java.pdf" in escribir.contenido  # type: ignore[attr-defined]

    m.aplicar(plan)
    assert relativos(tmp_path) == ["Apuntes/Programacion/Tema java.pdf", "INDICE.md"]


# --- Casos feos -------------------------------------------------------------


def test_carpeta_inexistente(tmp_path: Path, papelera: PapeleraFalsa) -> None:
    m = motor(papelera, accion("a", "borrar"))
    with pytest.raises(CarpetaNoValida, match="no existe"):
        m.planificar("a", tmp_path / "fantasma")


def test_si_el_disco_cambia_tras_planificar_se_detiene_sin_perder_nada(
    tmp_path: Path, papelera: PapeleraFalsa
) -> None:
    crear_fichero(tmp_path / "a_java.pdf", b"A")
    crear_fichero(tmp_path / "b_java.pdf", b"B")
    m = motor(papelera, accion("m", "mover", destino="{asignatura}"))
    plan = m.planificar("m", tmp_path)

    # Entre planificar y aplicar, alguien crea un fichero justo donde iba el segundo.
    crear_fichero(tmp_path / "Programacion" / "b_java.pdf", b"de otra persona")

    with pytest.raises(EjecucionInterrumpida, match="1 de 2 operaciones") as error:
        m.aplicar(plan)

    assert error.value.aplicadas == 1
    assert (tmp_path / "Programacion" / "a_java.pdf").read_bytes() == b"A"
    assert (tmp_path / "Programacion" / "b_java.pdf").read_bytes() == b"de otra persona"
    assert (tmp_path / "b_java.pdf").read_bytes() == b"B"  # el que no se movió sigue intacto


def test_el_plan_se_aplica_en_orden(tmp_path: Path, papelera: PapeleraFalsa) -> None:
    crear_fichero(tmp_path / "a_java.pdf")
    m = motor(papelera, accion("m", "mover", destino="{asignatura}"))
    plan = m.planificar("m", tmp_path)
    vistas: list[str] = []
    m.aplicar(plan, al_aplicar=lambda op: vistas.append(type(op).__name__))
    assert vistas == [Mover.__name__]
