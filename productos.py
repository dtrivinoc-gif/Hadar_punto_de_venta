"""
Módulo de productos.

Contiene:
  - Funciones de acceso a datos (listar, crear, editar, desactivar productos)
  - DialogoProducto: formulario de alta/edición rápida
  - VentanaProductos: pantalla con tabla de productos + botones de gestión

Diseñado para que agregar un producto nuevo (ej. el dueño trae juguetes)
tome 10-15 segundos: solo nombre y precio son obligatorios, el resto
tiene valores por defecto razonables.
"""

from PySide6.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QComboBox, QDoubleSpinBox, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QCheckBox,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor

from db import conectar
from estilos import ESTILO_BASE, VERDE, GRIS_MUTED, seleccionar_texto_al_enfocar


TIPOS_VENTA = [
    ("unidad", "Precio fijo (unidad)"),
    ("variable", "Precio variable (se escribe al vender)"),
    ("peso", "Por peso"),
]

CATEGORIAS_SUGERIDAS = [
    "General", "Dulces", "Verduras", "Frutas", "Cigarros",
    "Panadería", "Bebidas", "Juguetes", "Abarrotes",
]


# ---------------------------------------------------------------------------
# Acceso a datos
# ---------------------------------------------------------------------------

def listar_productos(solo_activos: bool = True):
    """Devuelve la lista de productos como sqlite3.Row, ordenados por categoría y nombre."""
    with conectar() as con:
        if solo_activos:
            cur = con.execute(
                "SELECT * FROM productos WHERE activo = 1 "
                "ORDER BY categoria, nombre"
            )
        else:
            cur = con.execute("SELECT * FROM productos ORDER BY categoria, nombre")
        return cur.fetchall()


def obtener_producto(producto_id: int):
    with conectar() as con:
        cur = con.execute("SELECT * FROM productos WHERE id = ?", (producto_id,))
        return cur.fetchone()


def buscar_por_codigo_barra(codigo: str):
    """Busca un producto activo por su código de barra exacto. Devuelve None si no existe."""
    codigo = (codigo or "").strip()
    if not codigo:
        return None
    with conectar() as con:
        cur = con.execute(
            "SELECT * FROM productos WHERE codigo_barra = ? AND activo = 1",
            (codigo,),
        )
        return cur.fetchone()


def crear_producto(nombre: str, precio: float, tipo_venta: str,
                    categoria: str, codigo_plu: str = None,
                    codigo_barra: str = None) -> int:
    """Crea un producto nuevo y devuelve su id."""
    with conectar() as con:
        cur = con.execute(
            """INSERT INTO productos
               (nombre, precio, tipo_venta, categoria, codigo_plu, codigo_barra)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (nombre.strip(), precio, tipo_venta, categoria.strip() or "General",
             codigo_plu, codigo_barra),
        )
        return cur.lastrowid


def actualizar_producto(producto_id: int, nombre: str, precio: float,
                         tipo_venta: str, categoria: str,
                         codigo_plu: str = None, codigo_barra: str = None):
    with conectar() as con:
        con.execute(
            """UPDATE productos
               SET nombre = ?, precio = ?, tipo_venta = ?, categoria = ?,
                   codigo_plu = ?, codigo_barra = ?
               WHERE id = ?""",
            (nombre.strip(), precio, tipo_venta, categoria.strip() or "General",
             codigo_plu, codigo_barra, producto_id),
        )


def desactivar_producto(producto_id: int):
    """No se borra nunca un producto (para no perder historial de ventas viejas);
    se marca inactivo y desaparece de la grilla de venta."""
    with conectar() as con:
        con.execute("UPDATE productos SET activo = 0 WHERE id = ?", (producto_id,))


def reactivar_producto(producto_id: int):
    with conectar() as con:
        con.execute("UPDATE productos SET activo = 1 WHERE id = ?", (producto_id,))


def categorias_existentes():
    """Categorías que ya se están usando, para ofrecerlas en el combo (más las sugeridas)."""
    with conectar() as con:
        cur = con.execute(
            "SELECT DISTINCT categoria FROM productos ORDER BY categoria"
        )
        existentes = [r["categoria"] for r in cur.fetchall()]
    todas = list(dict.fromkeys(CATEGORIAS_SUGERIDAS + existentes))  # sin duplicados, conserva orden
    return todas


# ---------------------------------------------------------------------------
# Diálogo de alta / edición rápida
# ---------------------------------------------------------------------------

class DialogoProducto(QDialog):
    """
    Formulario de alta o edición de un producto.
    Si se le pasa `producto` (una fila existente), edita; si no, crea uno nuevo.
    """

    def __init__(self, parent=None, producto=None, codigo_barra_inicial=None):
        super().__init__(parent)
        self.producto = producto
        self.producto_id = producto["id"] if producto else None
        self.setWindowTitle("Editar producto" if producto else "Agregar producto")
        self.setMinimumWidth(360)
        self._armar_ui()
        if producto:
            self._cargar_datos(producto)
        elif codigo_barra_inicial:
            self.campo_codigo_barra.setText(codigo_barra_inicial)
            self.campo_nombre.setFocus()

    def _armar_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.campo_nombre = QLineEdit()
        self.campo_nombre.setPlaceholderText("Ej: Chocolate Sahne-Nuss")
        form.addRow("Nombre*", self.campo_nombre)

        self.campo_precio = QDoubleSpinBox()
        self.campo_precio.setMaximum(1_000_000)
        self.campo_precio.setDecimals(0)
        self.campo_precio.setSingleStep(50)
        self.campo_precio.setPrefix("$ ")
        form.addRow("Precio*", self.campo_precio)

        self.combo_tipo = QComboBox()
        for valor, etiqueta in TIPOS_VENTA:
            self.combo_tipo.addItem(etiqueta, userData=valor)
        form.addRow("Tipo de venta", self.combo_tipo)

        self.combo_categoria = QComboBox()
        self.combo_categoria.setEditable(True)  # permite escribir una categoría nueva
        self.combo_categoria.addItems(categorias_existentes())
        form.addRow("Categoría", self.combo_categoria)

        self.campo_plu = QLineEdit()
        self.campo_plu.setPlaceholderText("Opcional")
        form.addRow("Código PLU", self.campo_plu)

        self.campo_codigo_barra = QLineEdit()
        self.campo_codigo_barra.setPlaceholderText("Escanea aquí o escribe (opcional)")
        form.addRow("Código de barra", self.campo_codigo_barra)

        layout.addLayout(form)

        botones = QHBoxLayout()
        boton_cancelar = QPushButton("Cancelar")
        boton_cancelar.setObjectName("botonSecundario")
        boton_cancelar.clicked.connect(self.reject)
        boton_guardar = QPushButton("Guardar")
        boton_guardar.setObjectName("botonPrimario")
        boton_guardar.setDefault(True)
        boton_guardar.clicked.connect(self._guardar)
        botones.addWidget(boton_cancelar)
        botones.addWidget(boton_guardar)
        layout.addLayout(botones)

        self.setStyleSheet(ESTILO_BASE)
        seleccionar_texto_al_enfocar(self.campo_precio)

    def _cargar_datos(self, producto):
        self.campo_nombre.setText(producto["nombre"])
        self.campo_precio.setValue(producto["precio"])
        indice_tipo = [v for v, _ in TIPOS_VENTA].index(producto["tipo_venta"])
        self.combo_tipo.setCurrentIndex(indice_tipo)
        self.combo_categoria.setCurrentText(producto["categoria"])
        self.campo_plu.setText(producto["codigo_plu"] or "")
        self.campo_codigo_barra.setText(producto["codigo_barra"] or "")

    def _guardar(self):
        nombre = self.campo_nombre.text().strip()
        if not nombre:
            QMessageBox.warning(self, "Falta el nombre", "Escribe el nombre del producto.")
            return

        precio = self.campo_precio.value()
        tipo_venta = self.combo_tipo.currentData()
        categoria = self.combo_categoria.currentText().strip() or "General"
        plu = self.campo_plu.text().strip() or None
        codigo_barra = self.campo_codigo_barra.text().strip() or None

        if self.producto:
            actualizar_producto(self.producto["id"], nombre, precio, tipo_venta,
                                 categoria, codigo_plu=plu, codigo_barra=codigo_barra)
            self.producto_id = self.producto["id"]
        else:
            self.producto_id = crear_producto(nombre, precio, tipo_venta, categoria,
                                               codigo_plu=plu, codigo_barra=codigo_barra)

        self.accept()


# ---------------------------------------------------------------------------
# Pantalla de gestión de productos (tabla + botones)
# ---------------------------------------------------------------------------

class VentanaProductos(QWidget):
    """
    Pantalla para que el dueño revise, agregue, edite o dé de baja productos.
    Se puede abrir como pestaña o como ventana aparte desde la pantalla de venta.
    """

    # se emite cuando cambia el catálogo, para que venta.py recargue la grilla
    productos_cambiaron = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._armar_ui()
        self.recargar()

    def _armar_ui(self):
        self.setStyleSheet(ESTILO_BASE)
        layout = QVBoxLayout(self)

        barra_botones = QHBoxLayout()
        self.checkbox_mostrar_inactivos = QCheckBox("Mostrar dados de baja")
        self.checkbox_mostrar_inactivos.stateChanged.connect(self.recargar)
        barra_botones.addWidget(self.checkbox_mostrar_inactivos)
        barra_botones.addStretch()

        boton_agregar = QPushButton("+ Agregar producto")
        boton_agregar.setObjectName("botonPrimario")
        boton_agregar.clicked.connect(self._agregar)
        barra_botones.addWidget(boton_agregar)

        boton_editar = QPushButton("Editar")
        boton_editar.setObjectName("botonSecundario")
        boton_editar.clicked.connect(self._editar)
        barra_botones.addWidget(boton_editar)

        self.boton_baja = QPushButton("Dar de baja")
        self.boton_baja.setObjectName("botonAdvertencia")
        self.boton_baja.clicked.connect(self._dar_de_baja)
        barra_botones.addWidget(self.boton_baja)

        layout.addLayout(barra_botones)

        self.tabla = QTableWidget(0, 5)
        self.tabla.setHorizontalHeaderLabels(
            ["Nombre", "Categoría", "Precio", "Tipo", "Estado"]
        )
        self.tabla.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tabla.setSelectionBehavior(QTableWidget.SelectRows)
        self.tabla.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabla.doubleClicked.connect(self._editar)
        layout.addWidget(self.tabla)

    def recargar(self):
        mostrar_inactivos = self.checkbox_mostrar_inactivos.isChecked()
        productos = listar_productos(solo_activos=not mostrar_inactivos)

        etiquetas_tipo = dict(TIPOS_VENTA)

        self.tabla.setRowCount(len(productos))
        for fila, producto in enumerate(productos):
            self.tabla.setItem(fila, 0, QTableWidgetItem(producto["nombre"]))
            self.tabla.setItem(fila, 1, QTableWidgetItem(producto["categoria"]))
            self.tabla.setItem(fila, 2, QTableWidgetItem(f"$ {producto['precio']:,.0f}"))
            self.tabla.setItem(fila, 3, QTableWidgetItem(etiquetas_tipo.get(producto["tipo_venta"], "")))
            estado = "Activo" if producto["activo"] else "De baja"
            item_estado = QTableWidgetItem(estado)
            item_estado.setForeground(QColor(VERDE if producto["activo"] else GRIS_MUTED))
            self.tabla.setItem(fila, 4, item_estado)
            # guardamos el id del producto en la primera celda para recuperarlo después
            self.tabla.item(fila, 0).setData(Qt.UserRole, producto["id"])

    def _fila_seleccionada_id(self):
        filas = self.tabla.selectionModel().selectedRows()
        if not filas:
            return None
        return self.tabla.item(filas[0].row(), 0).data(Qt.UserRole)

    def _agregar(self):
        dialogo = DialogoProducto(self)
        if dialogo.exec() == QDialog.Accepted:
            self.recargar()
            self.productos_cambiaron.emit()

    def _editar(self):
        producto_id = self._fila_seleccionada_id()
        if producto_id is None:
            QMessageBox.information(self, "Selecciona un producto", "Elige un producto de la tabla primero.")
            return
        producto = obtener_producto(producto_id)
        dialogo = DialogoProducto(self, producto=producto)
        if dialogo.exec() == QDialog.Accepted:
            self.recargar()
            self.productos_cambiaron.emit()

    def _dar_de_baja(self):
        producto_id = self._fila_seleccionada_id()
        if producto_id is None:
            QMessageBox.information(self, "Selecciona un producto", "Elige un producto de la tabla primero.")
            return
        respuesta = QMessageBox.question(
            self, "Confirmar",
            "¿Dar de baja este producto? Ya no aparecerá en la pantalla de venta, "
            "pero se conserva el historial de ventas anteriores."
        )
        if respuesta == QMessageBox.Yes:
            desactivar_producto(producto_id)
            self.recargar()
            self.productos_cambiaron.emit()