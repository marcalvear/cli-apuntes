"""Tests del proveedor Gemini y de la elección de proveedor. Sin red ni coste.

El cliente de google-genai se sustituye por uno falso que imita
`client.models.generate_content`: se comprueba qué se enviaría y cómo se
traduce cada respuesta o error.
"""

from types import SimpleNamespace
from typing import Any

import pytest
from google.genai import errors

from apuntes.config import Asignatura
from apuntes.errores import ErrorIA, IANoDisponible
from apuntes.ia import entorno, gemini
from apuntes.ia.cache import ProveedorConCache
from apuntes.ia.claude import ProveedorClaude
from apuntes.ia.documento import Documento
from apuntes.ia.gemini import ProveedorGemini

PDF = Documento("t.pdf", "pdf", b"%PDF-1.4 tema de SQL")
ASIGNATURAS = [Asignatura(nombre="Programacion"), Asignatura(nombre="Bases de Datos")]
MODELOS = ("modelo-a", "modelo-b")


def respuesta(texto: str | None, final: str = "STOP") -> SimpleNamespace:
    return SimpleNamespace(
        text=texto, candidates=[SimpleNamespace(finish_reason=SimpleNamespace(name=final))]
    )


def error_cliente(codigo: int, mensaje: str = "fallo") -> errors.ClientError:
    return errors.ClientError(codigo, {"error": {"code": codigo, "message": mensaje}})


def error_servidor(codigo: int = 503) -> errors.ServerError:
    return errors.ServerError(codigo, {"error": {"code": codigo, "message": "high demand"}})


class ClienteFalso:
    """Devuelve, por orden, lo indicado en `resultados` (una respuesta o una excepción)."""

    def __init__(self, *resultados: Any) -> None:
        self._resultados = list(resultados)
        self.peticiones: list[dict[str, Any]] = []
        self.models = SimpleNamespace(generate_content=self._generar)

    def _generar(self, **peticion: Any) -> Any:
        self.peticiones.append(peticion)
        resultado = self._resultados.pop(0)
        if isinstance(resultado, Exception):
            raise resultado
        return resultado


def proveedor(*resultados: Any) -> tuple[ProveedorGemini, ClienteFalso]:
    cliente = ClienteFalso(*resultados)
    return ProveedorGemini(modelos=MODELOS, cliente=cliente), cliente


# --- Peticiones ---------------------------------------------------------------


def test_clasificar_envia_el_pdf_y_un_esquema_cerrado() -> None:
    gem, cliente = proveedor(
        respuesta('{"asignatura": "Bases de Datos", "confianza": "alta", "motivo": "SQL"}')
    )

    resultado = gem.clasificar(PDF, ASIGNATURAS)

    assert resultado.asignatura == "Bases de Datos"
    assert resultado.fiable
    (peticion,) = cliente.peticiones
    assert peticion["model"] == "modelo-a"
    parte_pdf, _instrucciones = peticion["contents"]
    assert parte_pdf.inline_data.mime_type == "application/pdf"
    config = peticion["config"]
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema["properties"]["asignatura"]["enum"] == [
        "Programacion",
        "Bases de Datos",
        "ninguna",
    ]


def test_resumir_no_pide_json() -> None:
    gem, cliente = proveedor(respuesta("# Resumen\n- idea"))
    assert gem.resumir(PDF) == "# Resumen\n- idea"
    assert cliente.peticiones[0]["config"].response_mime_type is None


def test_un_documento_de_texto_se_envia_como_texto() -> None:
    gem, cliente = proveedor(respuesta("# ok"))
    gem.resumir(Documento("notas.md", "texto", b"# Notas de SQL"))
    parte, _ = cliente.peticiones[0]["contents"]
    assert "# Notas de SQL" in parte.text


def test_una_confianza_inesperada_se_trata_como_baja() -> None:
    gem, _ = proveedor(respuesta('{"asignatura": "Programacion", "confianza": "?", "motivo": "x"}'))
    assert not gem.clasificar(PDF, ASIGNATURAS).fiable


# --- Modelos de reserva --------------------------------------------------------


@pytest.mark.parametrize("fallo", [error_servidor(503), error_cliente(429), error_cliente(404)])
def test_si_un_modelo_falla_se_usa_el_siguiente(fallo: Exception) -> None:
    gem, cliente = proveedor(fallo, respuesta("# Resumen"))
    assert gem.resumir(PDF) == "# Resumen"
    assert [p["model"] for p in cliente.peticiones] == ["modelo-a", "modelo-b"]


def test_si_todos_los_modelos_estan_saturados_lo_explica() -> None:
    gem, _ = proveedor(error_servidor(), error_cliente(429))
    with pytest.raises(ErrorIA, match=r"modelo-a \(saturado\), modelo-b \(sin cuota\)") as error:
        gem.resumir(PDF)
    assert "caché" in (error.value.pista or "")


# --- Errores -------------------------------------------------------------------


def test_clave_invalida() -> None:
    gem, cliente = proveedor(error_cliente(400, "API key not valid. Please pass a valid API key."))
    with pytest.raises(IANoDisponible, match="no es válida"):
        gem.resumir(PDF)
    assert len(cliente.peticiones) == 1  # con la clave mal no tiene sentido probar otro modelo


def test_otro_error_400_nombra_el_documento() -> None:
    gem, _ = proveedor(error_cliente(400, "Request payload size exceeds the limit"))
    with pytest.raises(ErrorIA, match=r"no ha aceptado «t\.pdf»"):
        gem.resumir(PDF)


def test_sin_conexion(monkeypatch: pytest.MonkeyPatch) -> None:
    gem, _ = proveedor(ConnectionError("sin red"))
    with pytest.raises(IANoDisponible, match="perdido la conexión"):
        gem.resumir(PDF)


@pytest.mark.parametrize(
    ("final", "texto"),
    [("SAFETY", "negado"), ("PROHIBITED_CONTENT", "negado"), ("MAX_TOKENS", "cortada")],
)
def test_respuestas_bloqueadas_o_cortadas(final: str, texto: str) -> None:
    gem, _ = proveedor(respuesta("a medias", final=final))
    with pytest.raises(ErrorIA, match=texto):
        gem.resumir(PDF)


def test_respuesta_vacia() -> None:
    gem, _ = proveedor(respuesta(None))
    with pytest.raises(ErrorIA, match="no ha devuelto texto"):
        gem.resumir(PDF)


def test_comprobar_sin_clave() -> None:
    with pytest.raises(IANoDisponible, match="falta la clave GEMINI_API_KEY"):
        ProveedorGemini().comprobar()


def test_comprobar_sin_red(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "clave-de-prueba")
    monkeypatch.setattr(gemini, "_hay_red", lambda: False)
    with pytest.raises(IANoDisponible, match="No hay conexión con la API de Gemini"):
        ProveedorGemini().comprobar()


# --- Elección de proveedor -----------------------------------------------------


def _interno(proveedor: Any) -> Any:
    assert isinstance(proveedor, ProveedorConCache)  # siempre con caché
    return proveedor._proveedor


def test_sin_ninguna_clave_se_elige_gemini_que_es_gratis() -> None:
    assert isinstance(_interno(entorno.crear_proveedor()), ProveedorGemini)
    assert entorno.variable_clave() == "GEMINI_API_KEY"


def test_con_solo_clave_de_claude_se_elige_claude(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    assert isinstance(_interno(entorno.crear_proveedor()), ProveedorClaude)


def test_apuntes_proveedor_manda(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setenv("APUNTES_PROVEEDOR", "Claude")
    assert isinstance(_interno(entorno.crear_proveedor()), ProveedorClaude)


def test_apuntes_modelo_va_primero_y_los_demas_quedan_de_reserva(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APUNTES_MODELO", "gemini-3.6-flash")
    interno = _interno(entorno.crear_proveedor())
    assert interno.modelo == "gemini-3.6-flash"
    assert interno._modelos[0] == "gemini-3.6-flash"
    assert len(interno._modelos) == len(set(interno._modelos)) == 3


def test_proveedor_desconocido(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APUNTES_PROVEEDOR", "chatgpt")
    with pytest.raises(IANoDisponible, match="desconocido") as error:
        entorno.crear_proveedor()
    assert "gemini, claude" in (error.value.pista or "")


def test_un_modelo_saturado_no_se_reintenta_en_la_misma_ejecucion() -> None:
    gem, cliente = proveedor(error_servidor(), respuesta("# 1"), respuesta("# 2"))
    gem.resumir(PDF)
    gem.resumir(PDF)
    assert [p["model"] for p in cliente.peticiones] == ["modelo-a", "modelo-b", "modelo-b"]
