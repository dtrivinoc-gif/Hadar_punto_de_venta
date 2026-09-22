"""
Punto de entrada del POS.

Correr con:  python run_pos.py
(o el .exe generado con PyInstaller una vez empaquetado)
"""

import sys
from PySide6.QtWidgets import QApplication

from db import inicializar_base_datos
from main_window import VentanaPrincipal


def main():
    inicializar_base_datos()
    app = QApplication(sys.argv)
    ventana = VentanaPrincipal()
    ventana.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
