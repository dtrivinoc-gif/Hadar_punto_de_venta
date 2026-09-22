"""
Ventana principal del POS.

Une las cuatro pantallas en pestañas y conecta las señales entre ellas:

  - Cuando cambia el catálogo (productos.py) -> la grilla de venta se recarga
  - Cuando se abre o cierra la caja (arqueo.py) -> se recargan arqueo y
    caja vecina, para que muestren el estado correcto
"""

from PySide6.QtWidgets import QMainWindow, QTabWidget

from config import NOMBRE_NEGOCIO
from venta import PantallaVenta
from productos import VentanaProductos
from arqueo import WidgetArqueo
from caja_vecina import WidgetCajaVecina


class VentanaPrincipal(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"POS - {NOMBRE_NEGOCIO}")
        self.resize(1100, 700)

        self.pantalla_venta = PantallaVenta()
        self.pantalla_productos = VentanaProductos()
        self.pantalla_arqueo = WidgetArqueo()
        self.pantalla_caja_vecina = WidgetCajaVecina()

        # catálogo cambia -> se recarga la grilla de venta
        self.pantalla_productos.productos_cambiaron.connect(
            self.pantalla_venta.recargar_grilla
        )

        # se abre/cierra caja -> se actualiza el estado en arqueo y caja vecina
        self.pantalla_arqueo.caja_cambio.connect(self.pantalla_caja_vecina.recargar)

        pestanas = QTabWidget()
        pestanas.addTab(self.pantalla_venta, "Venta")
        pestanas.addTab(self.pantalla_productos, "Productos")
        pestanas.addTab(self.pantalla_arqueo, "Arqueo")
        pestanas.addTab(self.pantalla_caja_vecina, "Caja vecina")
        self.setCentralWidget(pestanas)