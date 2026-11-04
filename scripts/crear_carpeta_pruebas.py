"""Crea una carpeta de pruebas con material de clase falso para probar `apuntes`.

Uso:
    uv run scripts/crear_carpeta_pruebas.py            # crea ~/pruebas-tareas
    uv run scripts/crear_carpeta_pruebas.py OTRA_RUTA
    uv run scripts/crear_carpeta_pruebas.py --rehacer   # la vacía y la vuelve a crear

Nunca toca una carpeta que no haya creado él (lo marca con un fichero oculto).
"""

from __future__ import annotations

import os
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

MARCA = ".creada-por-apuntes"
AHORA = datetime.now()


def pdf(*lineas: str) -> bytes:
    """Un PDF válido de una página con esas líneas de texto (para que la IA lo pueda leer)."""

    def escapar(texto: str) -> str:
        return texto.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    texto = (
        "BT /F1 12 Tf 50 780 Td 16 TL "
        + " ".join(f"({escapar(linea)}) '" for linea in lineas)
        + " ET"
    )
    flujo = texto.encode("latin-1")
    objetos = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]/Contents 4 0 R"
        b"/Resources<</Font<</F1 5 0 R>>>>>>",
        b"<</Length %d>>stream\n" % len(flujo) + flujo + b"\nendstream",
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica/Encoding/WinAnsiEncoding>>",
    ]
    salida = bytearray(b"%PDF-1.4\n")
    posiciones = []
    for numero, objeto in enumerate(objetos, start=1):
        posiciones.append(len(salida))
        salida += b"%d 0 obj\n" % numero + objeto + b"\nendobj\n"
    inicio_xref = len(salida)
    salida += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objetos) + 1)
    salida += b"".join(b"%010d 00000 n \n" % p for p in posiciones)
    salida += b"trailer<</Size %d/Root 1 0 R>>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objetos) + 1,
        inicio_xref,
    )
    return bytes(salida)


POO = pdf(
    "Tema 3. Programacion orientada a objetos en Java",
    "Una clase define atributos y metodos. Un objeto es una instancia de una clase.",
    "Encapsulacion: atributos private y metodos get/set. Herencia con extends.",
    "Polimorfismo: un metodo sobrescrito (@Override) se comporta segun el objeto.",
)

# (nombre, contenido, días de antigüedad)
FICHEROS: list[tuple[str, bytes, int]] = [
    ("Tema3_POO.pdf", POO, 10),
    ("Tema3_POO (1).pdf", POO, 2),  # duplicado exacto
    (
        "UD2 - Excepciones en Java.pdf",
        pdf(
            "UD2. Excepciones en Java",
            "try / catch / finally. Excepciones comprobadas y no comprobadas.",
            "throw lanza una excepcion; throws la declara en la firma del metodo.",
        ),
        20,
    ),
    (
        "BBDD - Normalizacion 3FN.pdf",
        pdf(
            "Normalizacion: 1FN, 2FN y 3FN",
            "Una tabla esta en 3FN si esta en 2FN y no hay dependencias transitivas.",
        ),
        15,
    ),
    ("consultas_sql_ejercicios.docx", b"PK docx sql" * 30, 5),
    ("SI_tema2_redes.pptx", b"PK pptx redes" * 90, 30),
    ("Practica HTML y CSS.pdf", pdf("Practica: maquetar una web con HTML5 y CSS"), 8),
    ("Git y UML - Entornos.pdf", pdf("Control de versiones con Git y diagramas UML"), 12),
    (
        "java y sql.pdf",  # el nombre es ambiguo; el contenido no: es de Bases de Datos
        pdf(
            "Conectar Java con MySQL mediante JDBC",
            "Ejercicios de consultas SQL: SELECT con JOIN, GROUP BY y HAVING.",
            "Diseno del modelo entidad-relacion de la base de datos de una biblioteca.",
        ),
        3,
    ),
    (
        "documento(3).pdf",  # nombre inútil: solo la IA puede saber de qué es
        pdf(
            "Tema 5. Comandos basicos de la terminal en Linux",
            "ls, cd, mkdir, chmod y chown. Permisos rwx para usuario, grupo y otros.",
            "Instalacion de paquetes con apt y gestion de procesos con ps y kill.",
        ),
        4,
    ),
    ("apuntes-antiguos-1ESO.pdf", pdf("Apuntes de matematicas de 1 ESO: fracciones"), 400),
    ("~$plantilla.docx", b"temporal de office", 30),
    ("video-clase.mp4.crdownload", b"descarga a medias", 9),
    ("notas.txt", b"apuntar: examen de prog el viernes\n", 1),
]


def _crear(carpeta: Path) -> None:
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / MARCA).write_text("Carpeta de pruebas de apuntes. Se puede borrar.\n")
    for nombre, contenido, dias in FICHEROS:
        ruta = carpeta / nombre
        ruta.write_bytes(contenido)
        marca = (AHORA - timedelta(days=dias)).timestamp()
        os.utime(ruta, (marca, marca))
    print(f"✓ {len(FICHEROS)} ficheros de prueba en {carpeta}")


def main(argumentos: list[str]) -> int:
    rehacer = "--rehacer" in argumentos
    rutas = [a for a in argumentos if not a.startswith("--")]
    carpeta = Path(rutas[0] if rutas else "~/pruebas-tareas").expanduser()

    if carpeta.exists() and any(carpeta.iterdir()):
        if not (carpeta / MARCA).exists():
            print(f"✗ {carpeta} tiene ficheros que no creé yo; no la toco.", file=sys.stderr)
            return 1
        if not rehacer:
            print(f"✗ {carpeta} ya existe. Usa --rehacer para empezar de cero.", file=sys.stderr)
            return 1
        shutil.rmtree(carpeta)
    _crear(carpeta)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
