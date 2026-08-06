"""Comprobaciones de que el proyecto corre igual en Windows, Linux y macOS.

No se puede ejecutar el programa en los tres sistemas desde aquí, así que
se verifican las cosas que suelen romperse al cambiar de plataforma y que
sí son comprobables de forma estática o local.
"""

import ast
import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
FUENTES = sorted((RAIZ / "src").rglob("*.py"))

# Rutas absolutas atadas a un sistema: unidades de Windows y raíces de
# usuario de Unix. Se buscan en el código, no en los comentarios.
RUTAS_DE_SISTEMA = re.compile(r"""["'](?:[A-Za-z]:[\\/]|/home/|/Users/|/tmp/)""")


def test_no_hay_rutas_absolutas_atadas_a_un_sistema():
    culpables = [
        f"{f.relative_to(RAIZ)}"
        for f in FUENTES
        if RUTAS_DE_SISTEMA.search(f.read_text(encoding="utf-8"))
    ]
    assert not culpables, f"rutas absolutas en: {culpables}"


def test_no_se_construyen_rutas_concatenando_separadores():
    """Las rutas se arman con `pathlib`, nunca pegando '\\' o '/' a mano."""
    sospechosas = []
    for f in FUENTES:
        for numero, linea in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"""["'][^"']*\\\\[^"']*["']\s*\+""", linea):
                sospechosas.append(f"{f.relative_to(RAIZ)}:{numero}")
    assert not sospechosas, f"concatenación de rutas en: {sospechosas}"


def test_toda_lectura_y_escritura_de_texto_declara_encoding():
    """Sin `encoding` explícito, Python usa el del sistema: UTF-8 en Linux y
    macOS pero cp1252 en Windows, y los acentos se corromperían al cruzar.
    """
    faltantes = []
    for f in FUENTES:
        arbol = ast.parse(f.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.Call):
                continue
            nombre = getattr(nodo.func, "attr", None) or getattr(nodo.func, "id", None)
            if nombre not in {"read_text", "write_text"}:
                continue
            if "encoding" not in {k.arg for k in nodo.keywords}:
                faltantes.append(f"{f.relative_to(RAIZ)}:{nodo.lineno}")
    assert not faltantes, f"sin encoding explícito: {faltantes}"


def test_los_filtros_de_archivo_evitan_el_comodin_de_windows():
    """`*.*` solo casa archivos con punto fuera de Windows; el comodín
    portable es `*`.

    Se inspeccionan solo las cadenas del código: el comentario que explica
    esta misma regla menciona `*.*` a propósito y no debe hacer fallar.
    """
    ruta = RAIZ / "src/taller_cultura/infrastructure/gui/app.py"
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))

    # Las docstrings son texto explicativo, no configuración: solo los nodos
    # que pueden llevarlas (módulo, clase, función) se descartan.
    con_docstring = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    docstrings = {
        ast.get_docstring(n) for n in ast.walk(arbol) if isinstance(n, con_docstring)
    }
    patrones = [
        nodo.value
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.Constant)
        and isinstance(nodo.value, str)
        and nodo.value not in docstrings
    ]

    assert "*.*" not in patrones, "usar '*' como comodín, no '*.*'"
    assert "filetypes=[" not in ruta.read_text(
        encoding="utf-8"
    ), "usar las constantes FILTROS_* compartidas"


def test_el_tema_de_la_interfaz_no_asume_windows():
    """`vista` solo existe en Windows y `aqua` solo en macOS: la selección
    debe probar varios y aceptar el que haya.
    """
    gui = (RAIZ / "src/taller_cultura/infrastructure/gui/app.py").read_text(encoding="utf-8")

    assert "aqua" in gui and "clam" in gui, "faltan los temas de macOS/Linux"
    assert "theme_names()" in gui, "hay que consultar qué temas existen antes de aplicarlos"


def test_la_cli_avisa_como_instalar_tkinter_si_falta():
    """En muchas distribuciones de Linux tkinter es un paquete aparte."""
    main = (RAIZ / "src/taller_cultura/main.py").read_text(encoding="utf-8")

    assert "python3-tk" in main
    assert "ImportError" in main


@pytest.mark.parametrize("modulo", ["main", "domain.services", "application.use_cases"])
def test_los_modulos_centrales_no_importan_nada_especifico_del_sistema(modulo):
    ruta = RAIZ / "src/taller_cultura" / (modulo.replace(".", "/") + ".py")
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))

    importados = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            importados.update(alias.name.split(".")[0] for alias in nodo.names)
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            importados.add(nodo.module.split(".")[0])

    assert not importados & {"winreg", "msvcrt", "fcntl", "pwd", "grp"}
