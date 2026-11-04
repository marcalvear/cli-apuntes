"""Tests de la capa de IA. Ninguno usa la red ni gasta dinero.

- Documento y caché se prueban directamente.
- ProveedorClaude se prueba con un cliente falso que imita al SDK: se
  comprueba qué petición se enviaría y cómo se traducen sus errores.
- Las acciones de IA se prueban con IAFalsa (tests/ia_falsa.py).
"""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2 as httpx
import pytest

from apuntes.config import Asignatura, Configuracion
from apuntes.errores import DocumentoNoSoportado, ErrorIA, IANoDisponible
from apuntes.ia import claude
from apuntes.ia.cache import ProveedorConCache
from apuntes.ia.claude import ProveedorClaude
from apuntes.ia.documento import Documento
from apuntes.motor import Motor
from apuntes.operaciones import GenerarConIA
from tests.conftest import PapeleraFalsa, crear_fichero
from tests.ia_falsa import IAFalsa

PDF = b"%PDF-1.4 contenido de prueba"
ASIGNATURAS = [
    Asignatura(nombre="Programacion", palabras_clave=["java"]),
    Asignatura(nombre="Bases de Datos", palabras_clave=["sql"]),
]


# --- Documento --------------------------------------------------------------


def test_documento_pdf_y_texto(tmp_path: Path) -> None:
    pdf = crear_fichero(tmp_path / "t.pdf", PDF)
    txt = crear_fichero(tmp_path / "n.md", b"# Notas de clase")
    assert Documento.desde_fichero(pdf).formato == "pdf"
    assert Documento.desde_fichero(txt).texto == "# Notas de clase"


@pytest.mark.parametrize(
    ("nombre", "contenido", "motivo"),
    [
        ("diapos.pptx", b"PK", "solo lee PDF"),
        ("falso.pdf", b"no soy un pdf", "no es un PDF"),
        ("raro.txt", b"\xff\xfe\xfa", "UTF-8"),
        ("vacio.md", b"   \n", "vacío"),
    ],
)
def test_documento_no_soportado(tmp_path: Path, nombre: str, contenido: bytes, motivo: str) -> None:
    ruta = crear_fichero(tmp_path / nombre, contenido)
    with pytest.raises(DocumentoNoSoportado, match=motivo):
        Documento.desde_fichero(ruta)


def test_la_huella_depende_del_contenido_no_del_nombre(tmp_path: Path) -> None:
    a = Documento.desde_fichero(crear_fichero(tmp_path / "a.pdf", PDF))
    b = Documento.desde_fichero(crear_fichero(tmp_path / "b.pdf", PDF))
    assert a.huella == b.huella


# --- Caché ------------------------------------------------------------------


def test_la_cache_evita_repetir_llamadas_incluso_entre_ejecuciones(tmp_path: Path) -> None:
    documento = Documento("t.pdf", "pdf", PDF)
    falsa = IAFalsa()
    ruta = tmp_path / "cache.json"

    primera = ProveedorConCache(falsa, ruta)
    assert primera.resumir(documento) == falsa.resumir(documento)
    falsa.llamadas.clear()

    segunda = ProveedorConCache(falsa, ruta)  # otra ejecución: lee del disco
    segunda.resumir(documento)
    segunda.clasificar(documento, ASIGNATURAS)
    segunda.clasificar(documento, ASIGNATURAS)

    assert falsa.llamadas == [("clasificar", "t.pdf")]  # resumir y la 2.ª clasificación, gratis
    assert segunda.aciertos == 2


def test_cambiar_las_asignaturas_invalida_la_clasificacion(tmp_path: Path) -> None:
    documento = Documento("t.pdf", "pdf", PDF)
    falsa = IAFalsa()
    cache = ProveedorConCache(falsa, tmp_path / "cache.json")
    cache.clasificar(documento, ASIGNATURAS)
    cache.clasificar(documento, ASIGNATURAS[:1])
    assert len(falsa.llamadas) == 2


def test_una_cache_danada_no_es_un_error(tmp_path: Path) -> None:
    ruta = tmp_path / "cache.json"
    ruta.write_text("{esto no es json")
    cache = ProveedorConCache(IAFalsa(), ruta)
    assert cache.resumir(Documento("t.pdf", "pdf", PDF)).startswith("# Resumen")
    assert json.loads(ruta.read_text())  # se ha reescrito bien


# --- ProveedorClaude con un cliente falso ------------------------------------


class ClienteFalso:
    """Imita client.beta.messages.create: guarda la petición y devuelve o lanza lo indicado."""

    def __init__(self, respuesta: Any = None, error: Exception | None = None) -> None:
        self.peticiones: list[dict[str, Any]] = []
        self._respuesta, self._error = respuesta, error
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **peticion: Any) -> Any:
        self.peticiones.append(peticion)
        if self._error is not None:
            raise self._error
        return self._respuesta


def respuesta(texto: str, stop_reason: str = "end_turn") -> SimpleNamespace:
    return SimpleNamespace(
        stop_reason=stop_reason, content=[SimpleNamespace(type="text", text=texto)]
    )


def error_http(clase: type[anthropic.APIStatusError], codigo: int) -> anthropic.APIStatusError:
    peticion = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return clase("fallo", response=httpx.Response(codigo, request=peticion), body=None)


def test_clasificar_envia_el_pdf_y_un_esquema_cerrado() -> None:
    cliente = ClienteFalso(
        respuesta('{"asignatura": "Programacion", "confianza": "alta", "motivo": "habla de POO"}')
    )
    proveedor = ProveedorClaude(cliente=cliente)

    resultado = proveedor.clasificar(Documento("t.pdf", "pdf", PDF), ASIGNATURAS)

    assert resultado.asignatura == "Programacion"
    assert resultado.fiable
    (peticion,) = cliente.peticiones
    assert peticion["model"] == "claude-opus-5-5"
    assert peticion["fallbacks"] == "default"
    documento, _ = peticion["messages"][0]["content"]
    assert documento["source"]["media_type"] == "application/pdf"
    esquema = peticion["output_config"]["format"]["schema"]
    assert esquema["properties"]["asignatura"]["enum"] == [
        "Programacion",
        "Bases de Datos",
        "ninguna",
    ]


def test_clasificar_ninguna_no_es_fiable() -> None:
    cliente = ClienteFalso(
        respuesta('{"asignatura": "ninguna", "confianza": "alta", "motivo": "x"}')
    )
    resultado = ProveedorClaude(cliente=cliente).clasificar(
        Documento("t.pdf", "pdf", PDF), ASIGNATURAS
    )
    assert resultado.asignatura is None
    assert not resultado.fiable


@pytest.mark.parametrize(
    ("error", "esperado", "texto"),
    [
        (error_http(anthropic.AuthenticationError, 401), IANoDisponible, "no es válida"),
        (error_http(anthropic.RateLimitError, 429), ErrorIA, "límite de uso"),
        (error_http(anthropic.InternalServerError, 500), ErrorIA, "código 500"),
        (
            anthropic.APIConnectionError(
                request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")
            ),
            IANoDisponible,
            "conexión",
        ),
    ],
)
def test_los_errores_del_sdk_se_traducen(error: Exception, esperado: type, texto: str) -> None:
    proveedor = ProveedorClaude(cliente=ClienteFalso(error=error))
    with pytest.raises(esperado, match=texto):
        proveedor.resumir(Documento("t.pdf", "pdf", PDF))


@pytest.mark.parametrize(("stop", "texto"), [("refusal", "negado"), ("max_tokens", "cortada")])
def test_respuestas_incompletas_son_error(stop: str, texto: str) -> None:
    proveedor = ProveedorClaude(cliente=ClienteFalso(respuesta("a medias", stop_reason=stop)))
    with pytest.raises(ErrorIA, match=texto):
        proveedor.resumir(Documento("t.pdf", "pdf", PDF))


def test_comprobar_sin_clave(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    with pytest.raises(IANoDisponible, match="falta la clave"):
        ProveedorClaude().comprobar()


def test_comprobar_sin_red(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "clave-de-prueba")
    monkeypatch.setattr(claude, "_hay_red", lambda: False)
    with pytest.raises(IANoDisponible, match="No hay conexión"):
        ProveedorClaude().comprobar()


# --- Acciones con IA en el motor --------------------------------------------


def motor(papelera: PapeleraFalsa, ia: IAFalsa, *acciones: dict[str, Any]) -> Motor:
    texto = json.dumps(
        {
            "version": 1,
            "asignaturas": [{"nombre": "Programacion"}, {"nombre": "Bases de Datos"}],
            "acciones": list(acciones),
        }
    )
    return Motor(Configuracion.desde_texto(texto), papelera=papelera, ia=lambda: ia)


def test_ia_clasificar_mueve_segun_el_contenido(
    tmp_path: Path, papelera: PapeleraFalsa, ia: IAFalsa
) -> None:
    crear_fichero(tmp_path / "documento(3).pdf", b"%PDF tema de Bases de Datos: SQL")
    crear_fichero(tmp_path / "otro.pdf", b"%PDF receta de cocina")
    crear_fichero(tmp_path / "diapos.pptx", b"PK")
    m = motor(papelera, ia, {"nombre": "c", "descripcion": "d", "tipo": "ia-clasificar"})

    plan = m.planificar("c", tmp_path)
    m.aplicar(plan)

    assert (tmp_path / "Bases de Datos" / "documento(3).pdf").exists()
    assert (tmp_path / "otro.pdf").exists()  # la IA no lo tiene claro: no se toca
    avisos = " ".join(plan.pasos[0].avisos)
    assert "no lo tiene claro" in avisos
    assert "solo lee PDF" in avisos  # el .pptx se explica, no se rompe


def test_resumir_no_llama_a_la_ia_al_simular(
    tmp_path: Path, papelera: PapeleraFalsa, ia: IAFalsa
) -> None:
    crear_fichero(tmp_path / "tema1.pdf", PDF)
    m = motor(papelera, ia, {"nombre": "r", "descripcion": "d", "tipo": "ia-resumir"})

    plan = m.planificar("r", tmp_path)
    assert ia.llamadas == []  # planificar (y por tanto --simular) es gratis
    assert isinstance(plan.operaciones[0], GenerarConIA)

    m.aplicar(plan)
    assert ia.llamadas == [("resumir", "tema1.pdf")]
    assert (tmp_path / "tema1.resumen.md").read_text().startswith("# Resumen de tema1.pdf")


def test_resumir_no_regenera_lo_ya_hecho(
    tmp_path: Path, papelera: PapeleraFalsa, ia: IAFalsa
) -> None:
    crear_fichero(tmp_path / "tema1.pdf", PDF)
    crear_fichero(tmp_path / "tema1.resumen.md", b"ya estaba")
    m = motor(papelera, ia, {"nombre": "r", "descripcion": "d", "tipo": "ia-resumir"})
    assert m.planificar("r", tmp_path).vacio


def test_preguntas_en_carpeta_destino(tmp_path: Path, papelera: PapeleraFalsa, ia: IAFalsa) -> None:
    crear_fichero(tmp_path / "tema1.pdf", PDF)
    m = motor(
        papelera,
        ia,
        {
            "nombre": "p",
            "descripcion": "d",
            "tipo": "ia-preguntas",
            "destino": "Repaso",
            "numero": 5,
        },
    )
    m.aplicar(m.planificar("p", tmp_path))
    assert (tmp_path / "Repaso" / "tema1.preguntas.md").read_text().startswith("# 5 preguntas")


def test_sin_ia_una_accion_de_ia_falla_con_mensaje(tmp_path: Path, papelera: PapeleraFalsa) -> None:
    m = motor(
        papelera,
        IAFalsa(disponible=False),
        {"nombre": "r", "descripcion": "d", "tipo": "ia-resumir"},
    )
    with pytest.raises(IANoDisponible, match="No hay conexión"):
        m.planificar("r", tmp_path)


def test_sin_ia_el_pipeline_sigue_con_los_pasos_sin_ia(
    tmp_path: Path, papelera: PapeleraFalsa
) -> None:
    crear_fichero(tmp_path / "basura.tmp")
    crear_fichero(tmp_path / "tema1.pdf", PDF)
    m = motor(
        papelera,
        IAFalsa(disponible=False),
        {
            "nombre": "limpiar",
            "descripcion": "d",
            "tipo": "borrar",
            "filtro": {"extensiones": [".tmp"]},
        },
        {"nombre": "resumir", "descripcion": "d", "tipo": "ia-resumir"},
        {"nombre": "todo", "descripcion": "d", "tipo": "pipeline", "pasos": ["limpiar", "resumir"]},
    )

    plan = m.planificar("todo", tmp_path)
    m.aplicar(plan)

    _limpiar, resumir = plan.pasos
    assert resumir.omitido is not None and "No hay conexión" in resumir.omitido
    assert papelera.recibidos == ["basura.tmp"]  # el paso sin IA sí se ha hecho


def test_si_la_ia_falla_al_aplicar_se_detiene_y_lo_dice(
    tmp_path: Path, papelera: PapeleraFalsa, ia: IAFalsa, monkeypatch: pytest.MonkeyPatch
) -> None:
    crear_fichero(tmp_path / "a.pdf", PDF)
    crear_fichero(tmp_path / "b.pdf", PDF + b"2")
    m = motor(papelera, ia, {"nombre": "r", "descripcion": "d", "tipo": "ia-resumir"})
    plan = m.planificar("r", tmp_path)

    def resumir_que_falla(documento: Documento) -> str:
        if documento.nombre == "b.pdf":
            raise ErrorIA("Has superado el límite de uso de la API de Claude.")
        return "# ok"

    monkeypatch.setattr(ia, "resumir", resumir_que_falla)
    from apuntes.errores import EjecucionInterrumpida

    with pytest.raises(EjecucionInterrumpida, match="1 de 2"):
        m.aplicar(plan)
    assert (tmp_path / "a.resumen.md").exists()
    assert not (tmp_path / "b.resumen.md").exists()  # nada a medias
