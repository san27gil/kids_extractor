"""IA local (Ollama) para lo que no tiene formato fijo en el KID: el nombre
del fondo (cada gestora lo escribe a su manera) y el resumen de en qué invierte.

Todo se ejecuta con `ollama pull gemma4:12b`, o el que se indique con --modelo.
"""

from __future__ import annotations

import json
import urllib.request

URL = "http://localhost:11434"
MODELO = "gemma4:12b"
TIEMPO_MAXIMO = 180  # s por consulta (la primera tarda más: carga el modelo)


class IANoDisponible(Exception):
    pass


def _pedir(ruta: str, tiempo: float, datos: dict | None = None) -> dict:
    """GET (o POST con `datos` en JSON) a Ollama; devuelve el JSON de la
    respuesta. Lanza OSError si no responde y ValueError si no es JSON."""
    cuerpo = json.dumps(datos).encode() if datos is not None else None
    peticion = urllib.request.Request(f"{URL}{ruta}", data=cuerpo, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(peticion, timeout=tiempo) as r:
        return json.load(r)


def disponible(modelo: str = MODELO) -> bool:
    """¿Está Ollama abierto y con el modelo descargado?"""
    try:
        etiquetas = _pedir("/api/tags", 3)
    except (OSError, ValueError):
        return False
    nombres = {m.get("name") for m in etiquetas.get("models", [])}
    # "gemma4" equivale a "gemma4:latest".
    return modelo in nombres or f"{modelo}:latest" in nombres


def extraer_json(prompt: str, esquema: dict, modelo: str = MODELO) -> dict:
    """Respuesta de la IA ajustada al esquema JSON dado ({} si contesta algo
    que no es JSON). Temperatura 0 (el mismo PDF da siempre la misma
    respuesta) y sin "razonar" en voz alta (más rápido). Lanza IANoDisponible
    si Ollama no responde."""
    try:
        contenido = _pedir("/api/chat", TIEMPO_MAXIMO, {
            "model": modelo, "stream": False, "think": False, "format": esquema,
            "options": {"temperature": 0},
            "messages": [{"role": "user", "content": prompt}],
        })["message"]["content"]
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise IANoDisponible(str(e)) from e
    try:
        respuesta = json.loads(contenido)
    except ValueError:
        return {}
    return respuesta if isinstance(respuesta, dict) else {}
