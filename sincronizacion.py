"""
Sincronización con Turso Cloud.

Manda (push) los cambios locales a la nube y trae (pull) los que haya de
otros lados, usando la conexión persistente que vive en db.py.

Filosofía: esto NUNCA debe poder tumbar una venta. Si no hay internet, o
Turso no responde, push()/pull() simplemente fallan en silencio -- las
ventas quedan guardadas en el archivo local de todos modos, y se
sincronizan solas la próxima vez que haya conexión.
"""

from PySide6.QtCore import QTimer

from config import USAR_TURSO, INTERVALO_SINCRONIZACION_MS
import db


def sincronizar_ahora():
    """Un intento de sincronizar. No hace nada si USAR_TURSO está
    apagado. Nunca lanza una excepción hacia afuera."""
    if not USAR_TURSO:
        return
    try:
        con = db._obtener_conexion_turso()
        con.push()
        con.pull()
    except Exception:
        # sin internet, o Turso no disponible en este momento -- no pasa
        # nada, las ventas siguen guardadas localmente y se sube todo
        # junto la próxima vez que haya conexión
        pass


def iniciar_sincronizacion_periodica(parent):
    """
    Arranca un temporizador que sincroniza cada INTERVALO_SINCRONIZACION_MS
    mientras el programa esté abierto. Se llama UNA sola vez, desde
    run_pos.py, justo después de crear la ventana principal.

    Devuelve el QTimer -- hay que guardar la referencia en una variable
    que no se destruya (ver run_pos.py), o Python lo recolecta como
    basura y el temporizador deja de sonar sin avisar.
    """
    if not USAR_TURSO:
        return None
    timer = QTimer(parent)
    timer.timeout.connect(sincronizar_ahora)
    timer.start(INTERVALO_SINCRONIZACION_MS)
    sincronizar_ahora()  # un intento apenas arranca, sin esperar el primer intervalo
    return timer
