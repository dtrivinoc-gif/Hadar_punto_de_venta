"""
Contenedor de la pestaña "Ajustes".

Agrupa en sub-pestañas todo lo que es configuración/administración del
POS, en vez de tener una pestaña de nivel superior para cada cosa:

  - General: tu WidgetAjustes de siempre (corrección de hora, etc.)
  - Cajeros: alta/baja de cajeros
  - Exportar: copiar la base de datos o exportar a Excel para Hadar

Así el usuario ve "Ajustes" como un solo lugar para todo lo administrativo,
y la barra de pestañas principal no crece cada vez que se agrega una
función de este tipo.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QTabWidget

from ajustes import WidgetAjustes
from cajeros import VentanaCajeros
from exportar import WidgetExportar


class WidgetAjustesGeneral(QWidget):

    # se reemite hacia afuera para que main_window pueda conectarla igual
    # que antes, sin que main_window necesite saber que ahora vive adentro
    # de un contenedor con sub-pestañas
    def __init__(self, parent=None):
        super().__init__(parent)

        self.pantalla_ajustes = WidgetAjustes()
        self.pantalla_cajeros = VentanaCajeros()
        self.pantalla_exportar = WidgetExportar()

        sub_pestanas = QTabWidget()
        sub_pestanas.addTab(self.pantalla_ajustes, "General")
        sub_pestanas.addTab(self.pantalla_cajeros, "Cajeros")
        sub_pestanas.addTab(self.pantalla_exportar, "Exportar")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.addWidget(sub_pestanas)

    @property
    def cajeros_cambiaron(self):
        """Expone la señal de cajeros.py tal cual, para que main_window.py
        pueda conectarla exactamente igual que si Cajeros siguiera siendo
        una pestaña de nivel superior."""
        return self.pantalla_cajeros.cajeros_cambiaron
