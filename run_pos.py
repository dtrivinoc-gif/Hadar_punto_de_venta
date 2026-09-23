"""
Punto de entrada del POS.

Correr con:  python run_pos.py
(o el .exe generado con PyInstaller una vez empaquetado)
"""

import sys
from PySide6.QtWidgets import QApplication

from db import inicializar_base_datos, cerrar_conexion_turso
from main_window import VentanaPrincipal
from sincronizacion import iniciar_sincronizacion_periodica


def main():
    inicializar_base_datos()
    app = QApplication(sys.argv)
    ventana = VentanaPrincipal()
    ventana.show()

    # Referencia guardada en la propia ventana para que el temporizador
    # no se destruya apenas termina esta función (ver nota en
    # sincronizacion.py) -- si USAR_TURSO está apagado, esto no hace nada.
    ventana._temporizador_sync = iniciar_sincronizacion_periodica(ventana)

    # Cierra bien la conexión persistente a Turso al salir (si estaba
    # abierta). Con sqlite3 puro esto no hace nada -- cada conexión ya
    # se cierra sola después de cada consulta.
    app.aboutToQuit.connect(cerrar_conexion_turso)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()