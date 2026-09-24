"""
Estilos visuales compartidos de Hadar POS.

Un solo lugar con la paleta de colores y la hoja de estilo (QSS) base que
usan las distintas pestañas, para que la app se sienta como una sola cosa
y no como pantallas pegadas con estilos distintos. Si el azul aciano de
Hadar cambia algún día, se cambia acá y se actualiza toda la app.

Semántica de color, igual en toda la app (no solo en Fiado):
  - Azul aciano (ACENTO): identidad de marca / acciones neutras (abrir
    caja, cobrar de forma genérica, seleccionar)
  - Verde: algo que "entra" o confirma positivamente (cobrar, abonar,
    depositar, un cuadre de caja que sobra o cuadra exacto)
  - Naranja: algo que "sale", resta, o necesita atención (fiar, retirar,
    quitar del carrito, un cuadre de caja que falta)
  - Rojo: alerta fuerte / deuda / diferencia negativa

NOTA: fiado.py ya tenía su propio estilo (ESTILO_FIADO) antes de crear
este archivo y usa los mismos colores -- a propósito no se tocó, porque
ya funciona y no vale la pena arriesgarlo. Este archivo es para las
pantallas nuevas que se vayan vistiendo con el mismo lenguaje visual.
"""

from config import COLOR_ACENTO_HADAR

ACENTO = COLOR_ACENTO_HADAR        # #6366F1 -- azul aciano de Hadar
ACENTO_HOVER = "#4F46E5"
ACENTO_SUAVE = "#EEF0FE"

VERDE = "#16A34A"
VERDE_HOVER = "#15803D"
VERDE_SUAVE = "#DCFCE7"

NARANJA = "#D97706"
NARANJA_HOVER = "#B45309"
NARANJA_SUAVE = "#FEF3C7"

ROJO = "#DC2626"
ROJO_HOVER = "#B91C1C"
ROJO_SUAVE = "#FEE2E2"

GRIS_TEXTO = "#1F2430"
GRIS_MUTED = "#6B7280"
BORDE = "#E5E7EB"
FONDO_TARJETA = "#F8F9FC"


def estilo_pestanas(color_activo: str = ACENTO) -> str:
    """Hoja de estilo para un QTabWidget (pestañas redondeadas, activa en
    color). La usan tanto la ventana principal como los sub-tabs internos
    (ej. categorías de productos en Venta), para que se vean como parte
    de la misma familia visual."""
    return f"""
    QTabWidget::pane {{
        border: none;
        background: #FFFFFF;
    }}
    QTabBar::tab {{
        background: #F1F2F6;
        color: #3A3A3A;
        padding: 10px 22px;
        margin-right: 6px;
        border-radius: 8px;
        font-size: 13px;
        font-weight: 600;
    }}
    QTabBar::tab:hover {{
        background: #E4E6F5;
    }}
    QTabBar::tab:selected {{
        background: {color_activo};
        color: #FFFFFF;
    }}
    """


# Hoja de estilo base para el resto de los controles: campos de texto,
# combos, tablas, listas, grupos y botones. Se aplica con
# self.setStyleSheet(ESTILO_BASE) en el widget raíz de cada pantalla, y
# Qt la propaga sola a todos los widgets hijos por tipo/objectName.
ESTILO_BASE = f"""
QLineEdit, QComboBox, QDoubleSpinBox {{
    padding: 8px 10px;
    border: 1px solid {BORDE};
    border-radius: 8px;
    font-size: 13px;
    background: white;
}}
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus {{
    border: 1.5px solid {ACENTO};
}}

QTableWidget, QListWidget {{
    background: white;
    border: 1px solid {BORDE};
    border-radius: 10px;
    gridline-color: {BORDE};
}}
QHeaderView::section {{
    background: #F8F9FC;
    color: {GRIS_MUTED};
    border: none;
    border-bottom: 1px solid {BORDE};
    padding: 6px;
    font-weight: 600;
    font-size: 12px;
}}

QGroupBox {{
    border: 1px solid {BORDE};
    border-radius: 10px;
    margin-top: 12px;
    padding-top: 16px;
    font-weight: 600;
    color: {GRIS_TEXTO};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: {GRIS_MUTED};
    font-size: 12px;
    font-weight: 700;
}}

QPushButton {{
    border-radius: 8px;
    padding: 10px 16px;
    font-weight: 600;
    font-size: 13px;
}}

QPushButton#botonPrimario {{
    background: {ACENTO}; color: white; border: none;
}}
QPushButton#botonPrimario:hover {{ background: {ACENTO_HOVER}; }}

QPushButton#botonExito {{
    background: {VERDE}; color: white; border: none;
}}
QPushButton#botonExito:hover {{ background: {VERDE_HOVER}; }}

QPushButton#botonAdvertencia {{
    background: {NARANJA}; color: white; border: none;
}}
QPushButton#botonAdvertencia:hover {{ background: {NARANJA_HOVER}; }}

QPushButton#botonSecundario {{
    background: white; color: {GRIS_TEXTO}; border: 1px solid {BORDE};
}}
QPushButton#botonSecundario:hover {{ background: #F3F4F6; }}

QCheckBox {{
    font-size: 13px;
    color: {GRIS_TEXTO};
}}
"""


def seleccionar_texto_al_enfocar(spin_box):
    """Deja el texto de un QDoubleSpinBox seleccionado, para que al
    empezar a escribir se reemplace el valor por defecto (normalmente 0)
    en vez de tener que borrarlo primero. Mismo arreglo que se hizo en
    fiado.py, disponible acá para reusar en cualquier diálogo nuevo."""
    spin_box.setFocus()
    spin_box.lineEdit().selectAll()


def badge_estado(texto: str, color_fondo: str, color_texto: str) -> str:
    """Devuelve el QSS inline para pintar un QLabel como una 'píldora' de
    estado (ej. 'Caja abierta' en verde). Uso:
        etiqueta.setText(texto)
        etiqueta.setStyleSheet(badge_estado(texto, VERDE_SUAVE, VERDE))
    """
    return (
        f"background: {color_fondo}; color: {color_texto}; font-weight: 700; "
        f"font-size: 12px; padding: 4px 12px; border-radius: 10px;"
    )