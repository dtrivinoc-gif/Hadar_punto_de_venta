"""
Ventana principal del POS.

Une las pantallas en pestañas y conecta las señales entre ellas:

  - Cuando cambia el catálogo (productos.py) -> la grilla de venta se recarga
  - Cuando se abre o cierra la caja (arqueo.py) -> se recargan arqueo y
    caja vecina, para que muestren el estado correcto
  - Cuando cambian los cajeros (dentro de Ajustes) -> se recarga el
    selector en venta
"""

from PySide6.QtWidgets import QMainWindow, QTabWidget

from config import NOMBRE_APP, NOMBRE_NEGOCIO
from estilos import estilo_pestanas
from venta import PantallaVenta
from productos import VentanaProductos
from arqueo import WidgetArqueo
from caja_vecina import WidgetCajaVecina
from fiado import WidgetFiado
from panel_ajustes import WidgetAjustesGeneral


class VentanaPrincipal(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{NOMBRE_APP} — {NOMBRE_NEGOCIO}")
        self.resize(1100, 700)

        self.pantalla_venta = PantallaVenta()
        self.pantalla_productos = VentanaProductos()
        self.pantalla_arqueo = WidgetArqueo()
        self.pantalla_caja_vecina = WidgetCajaVecina()
        self.pantalla_fiado = WidgetFiado()
        self.pantalla_ajustes = WidgetAjustesGeneral()

        # catálogo cambia -> se recarga la grilla de venta
        self.pantalla_productos.productos_cambiaron.connect(
            self.pantalla_venta.recargar_grilla
        )

        # se abre/cierra caja -> se actualiza el estado en arqueo y caja vecina
        self.pantalla_arqueo.caja_cambio.connect(self.pantalla_caja_vecina.recargar)

        # cambian los cajeros (adentro de Ajustes) -> se recarga el selector en venta
        self.pantalla_ajustes.cajeros_cambiaron.connect(self.pantalla_venta.recargar_cajeros)

        pestanas = QTabWidget()
        pestanas.setStyleSheet(estilo_pestanas())
        pestanas.addTab(self.pantalla_venta, "Venta")
        pestanas.addTab(self.pantalla_productos, "Productos")
        pestanas.addTab(self.pantalla_arqueo, "Arqueo")
        pestanas.addTab(self.pantalla_caja_vecina, "Caja vecina")
        pestanas.addTab(self.pantalla_fiado, "Fiado")
        pestanas.addTab(self.pantalla_ajustes, "Ajustes")

        # recargar Fiado cada vez que se entra a la pestaña, para que una
        # venta recién fiada en la pestaña Venta aparezca al tiro
        pestanas.currentChanged.connect(
            lambda indice: self.pantalla_fiado.recargar()
            if pestanas.widget(indice) is self.pantalla_fiado else None
        )

        self.setCentralWidget(pestanas)