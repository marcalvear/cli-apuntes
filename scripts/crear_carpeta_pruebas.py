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

# (nombre, contenido, días de antigüedad)
FICHEROS: list[tuple[str, bytes, int]] = [
    ("Tema3_POO.pdf", b"%PDF-1.4 programacion orientada a objetos" * 50, 10),
    ("Tema3_POO (1).pdf", b"%PDF-1.4 programacion orientada a objetos" * 50, 2),  # duplicado
    ("UD2 - Excepciones en Java.pdf", b"%PDF-1.4 excepciones" * 80, 20),
    ("BBDD - Normalizacion 3FN.pdf", b"%PDF-1.4 normalizacion" * 60, 15),
    ("consultas_sql_ejercicios.docx", b"PK docx sql" * 30, 5),
    ("SI_tema2_redes.pptx", b"PK pptx redes" * 90, 30),
    ("Practica HTML y CSS.pdf", b"%PDF-1.4 html css" * 40, 8),
    ("Git y UML - Entornos.pdf", b"%PDF-1.4 git uml" * 45, 12),
    ("java y sql.pdf", b"%PDF-1.4 dudoso" * 20, 3),  # ambiguo: no se mueve
    ("documento(3).pdf", b"%PDF-1.4 sin pistas" * 25, 4),  # sin pistas: para la IA
    ("apuntes-antiguos-1ESO.pdf", b"%PDF-1.4 muy viejo" * 10, 400),
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
