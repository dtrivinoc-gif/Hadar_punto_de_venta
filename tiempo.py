"""
Hora "corregida" del POS.

El POS usa siempre la hora del PC (no depende de internet, igual que el
resto del sistema). El problema real que esto resuelve es otro: en
computadores modestos el reloj interno a veces se atrasa o adelanta (pila
de respaldo vieja, alguien lo cambió sin querer, etc.). En vez de tocar el
reloj de Windows (que requiere permisos de administrador), guardamos acá
un "desfase" en segundos: la diferencia entre lo que el reloj del PC dice
y lo que realmente es. Todo el POS pide la hora a través de este módulo
en vez de usar datetime.now() directo, para que la corrección se aplique
en todos lados por igual (ventas, fiado, caja vecina, etc.).

Se corrige desde la pestaña Ajustes (ver ajustes.py).
"""

from datetime import datetime, timedelta

from db import conectar

FORMATO_SQLITE = "%Y-%m-%d %H:%M:%S"


def _desfase_segundos() -> int:
    with conectar() as con:
        fila = con.execute(
            "SELECT desfase_segundos FROM configuracion_reloj WHERE id = 1"
        ).fetchone()
        return fila["desfase_segundos"] if fila else 0


def ahora() -> datetime:
    """La hora que debe usar el POS (hora del PC + corrección guardada)."""
    return datetime.now() + timedelta(seconds=_desfase_segundos())


def ahora_texto() -> str:
    """Igual que ahora(), pero como texto en el mismo formato que usa
    SQLite (datetime('now','localtime')), para guardar en las tablas."""
    return ahora().strftime(FORMATO_SQLITE)


def desfase_actual_segundos() -> int:
    return _desfase_segundos()


def establecer_hora_correcta(fecha_hora_correcta: datetime):
    """Se llama desde Ajustes cuando el usuario indica la hora real.
    Calcula y guarda el desfase necesario para que ahora() la refleje."""
    desfase = round((fecha_hora_correcta - datetime.now()).total_seconds())
    with conectar() as con:
        con.execute(
            """INSERT INTO configuracion_reloj (id, desfase_segundos) VALUES (1, ?)
               ON CONFLICT(id) DO UPDATE SET desfase_segundos = excluded.desfase_segundos""",
            (desfase,),
        )
