"""
Pantalla principal de venta.

Es la pantalla que usa la cajera todo el día: una grilla de botones con
los productos (agrupados por categoría en pestañas), un carrito a la
derecha, y botones para cobrar. Incluye:

  - Botón "Otro" para venta libre (algo que no está catalogado todavía)
  - Selector de origen: venta del negocio o caja vecina
  - Selector de cajero: quién está vendiendo, para atribuir cada venta
  - Precio variable: si el producto es tipo 'variable' o 'peso', pide el
    monto/cantidad en un diálogo antes de agregarlo al carrito
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QLabel,
    QTabWidget, QScrollArea, QTableWidget, QTableWidgetItem, QHeaderView,
    QDialog, QFormLayout, QLineEdit, QDoubleSpinBox, QMessageBox, QComboBox,
    QGroupBox, QCheckBox,
)
from PySide6.QtCore import Qt

from db import conectar
from productos import listar_productos, buscar_por_codigo_barra, obtener_producto, DialogoProducto
from arqueo import sesion_abierta
from fiado import DialogoSeleccionarCliente
from tiempo import ahora_texto
from cajeros import listar_cajeros, DialogoCajero
from estilos import ESTILO_BASE, estilo_pestanas, ACENTO, seleccionar_texto_al_enfocar


# ---------------------------------------------------------------------------
# Diálogo para precio variable / por peso
# ---------------------------------------------------------------------------

class DialogoPrecioVariable(QDialog):
    """Se abre cuando el producto es de tipo 'variable' o 'peso': pide el
    monto o la cantidad antes de agregarlo al carrito."""

    def __init__(self, parent, nombre_producto: str, tipo_venta: str, precio_referencia: float):
        super().__init__(parent)
        self.tipo_venta = tipo_venta
        self.setWindowTitle(nombre_producto)
        layout = QVBoxLayout(self)
        form = QFormLayout()

        if tipo_venta == "variable":
            self.campo = QDoubleSpinBox()
            self.campo.setMaximum(1_000_000)
            self.campo.setDecimals(0)
            self.campo.setPrefix("$ ")
            self.campo.setValue(precio_referencia)
            form.addRow("Monto a cobrar", self.campo)
        else:  # 'peso'
            self.campo = QDoubleSpinBox()
            self.campo.setMaximum(1000)
            self.campo.setDecimals(3)
            self.campo.setSuffix(" kg")
            form.addRow("Peso", self.campo)
            self.precio_por_kilo = precio_referencia
            self.etiqueta_total = QLabel("$ 0")
            form.addRow("Total", self.etiqueta_total)
            self.campo.valueChanged.connect(self._actualizar_total)

        layout.addLayout(form)

        botones = QHBoxLayout()
        boton_cancelar = QPushButton("Cancelar")
        boton_cancelar.setObjectName("botonSecundario")
        boton_cancelar.clicked.connect(self.reject)
        boton_ok = QPushButton("Agregar")
        boton_ok.setObjectName("botonPrimario")
        boton_ok.setDefault(True)
        boton_ok.clicked.connect(self.accept)
        botones.addWidget(boton_cancelar)
        botones.addWidget(boton_ok)
        layout.addLayout(botones)

        self.setStyleSheet(ESTILO_BASE)
        seleccionar_texto_al_enfocar(self.campo)

    def _actualizar_total(self, valor):
        self.etiqueta_total.setText(f"$ {valor * self.precio_por_kilo:,.0f}")

    def resultado(self):
        """Devuelve (cantidad, precio_unitario, subtotal) según el tipo."""
        if self.tipo_venta == "variable":
            monto = self.campo.value()
            return 1, monto, monto
        else:
            kilos = self.campo.value()
            subtotal = kilos * self.precio_por_kilo
            return kilos, self.precio_por_kilo, subtotal


# ---------------------------------------------------------------------------
# Diálogo de venta libre (producto no catalogado)
# ---------------------------------------------------------------------------

class DialogoVentaLibre(QDialog):
    """Para vender algo que todavía no está en el catálogo (ej. el dueño
    trajo juguetes nuevos esta mañana). Queda marcado como venta libre para
    que después se revise y, si corresponde, se agregue al catálogo."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Venta libre (no catalogado)")
        self.setMinimumWidth(320)
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.campo_nombre = QLineEdit()
        self.campo_nombre.setPlaceholderText("Ej: Auto de juguete")
        form.addRow("¿Qué es?", self.campo_nombre)

        self.campo_precio = QDoubleSpinBox()
        self.campo_precio.setMaximum(1_000_000)
        self.campo_precio.setDecimals(0)
        self.campo_precio.setPrefix("$ ")
        form.addRow("Precio", self.campo_precio)

        layout.addLayout(form)

        botones = QHBoxLayout()
        boton_cancelar = QPushButton("Cancelar")
        boton_cancelar.setObjectName("botonSecundario")
        boton_cancelar.clicked.connect(self.reject)
        boton_ok = QPushButton("Agregar")
        boton_ok.setObjectName("botonPrimario")
        boton_ok.setDefault(True)
        boton_ok.clicked.connect(self._validar_y_aceptar)
        botones.addWidget(boton_cancelar)
        botones.addWidget(boton_ok)
        layout.addLayout(botones)

        self.setStyleSheet(ESTILO_BASE)
        seleccionar_texto_al_enfocar(self.campo_precio)

    def _validar_y_aceptar(self):
        if not self.campo_nombre.text().strip():
            QMessageBox.warning(self, "Falta el nombre", "Escribe qué se está vendiendo.")
            return
        self.accept()

    def resultado(self):
        return self.campo_nombre.text().strip(), self.campo_precio.value()


# ---------------------------------------------------------------------------
# Pantalla principal
# ---------------------------------------------------------------------------

class PantallaVenta(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.carrito = []  # lista de dicts: producto_id, nombre, cantidad, precio_unitario, subtotal, es_venta_libre
        self._armar_ui()
        self.recargar_grilla()
        self.recargar_cajeros()
        self.campo_escaner.setFocus()

    # -- construcción de la interfaz -----------------------------------

    def _armar_ui(self):
        self.setStyleSheet(ESTILO_BASE)
        layout_principal = QHBoxLayout(self)

        # --- columna izquierda: escaneo + grilla de productos por categoría ---
        columna_izquierda = QVBoxLayout()

        fila_escaner = QHBoxLayout()
        self.campo_escaner = QLineEdit()
        self.campo_escaner.setPlaceholderText("Escanea el código de barra aquí…")
        self.campo_escaner.setMinimumHeight(40)
        self.campo_escaner.returnPressed.connect(self._procesar_escaneo)
        fila_escaner.addWidget(self.campo_escaner, stretch=1)

        self.checkbox_modo_consulta = QCheckBox("Solo consultar precio")
        self.checkbox_modo_consulta.setToolTip(
            "Si está activo, escanear muestra el precio pero no agrega al carrito."
        )
        fila_escaner.addWidget(self.checkbox_modo_consulta)

        columna_izquierda.addLayout(fila_escaner)

        self.tabs_categorias = QTabWidget()
        self.tabs_categorias.setStyleSheet(estilo_pestanas())
        columna_izquierda.addWidget(self.tabs_categorias, stretch=1)

        boton_venta_libre = QPushButton("+ Otro (no catalogado)")
        boton_venta_libre.setObjectName("botonSecundario")
        boton_venta_libre.setMinimumHeight(48)
        boton_venta_libre.clicked.connect(self._abrir_venta_libre)
        columna_izquierda.addWidget(boton_venta_libre)

        layout_principal.addLayout(columna_izquierda, stretch=2)

        # --- columna derecha: carrito + cobro ---
        columna_derecha = QVBoxLayout()

        grupo_origen = QGroupBox("Caja")
        layout_origen = QHBoxLayout(grupo_origen)
        self.combo_origen = QComboBox()
        self.combo_origen.addItem("Venta del negocio", userData="venta_negocio")
        self.combo_origen.addItem("Caja vecina", userData="caja_vecina")
        layout_origen.addWidget(self.combo_origen)
        columna_derecha.addWidget(grupo_origen)

        grupo_cajero = QGroupBox("Cajero")
        layout_cajero = QHBoxLayout(grupo_cajero)
        self.combo_cajero = QComboBox()
        layout_cajero.addWidget(self.combo_cajero, stretch=1)
        boton_nuevo_cajero = QPushButton("+")
        boton_nuevo_cajero.setObjectName("botonSecundario")
        boton_nuevo_cajero.setMaximumWidth(32)
        boton_nuevo_cajero.setToolTip("Agregar cajero nuevo")
        boton_nuevo_cajero.clicked.connect(self._agregar_cajero)
        layout_cajero.addWidget(boton_nuevo_cajero)
        columna_derecha.addWidget(grupo_cajero)

        self.tabla_carrito = QTableWidget(0, 4)
        self.tabla_carrito.setHorizontalHeaderLabels(["Producto", "Cant.", "Precio", "Subtotal"])
        self.tabla_carrito.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tabla_carrito.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabla_carrito.setSelectionBehavior(QTableWidget.SelectRows)
        columna_derecha.addWidget(self.tabla_carrito, stretch=1)

        boton_quitar = QPushButton("Quitar seleccionado")
        boton_quitar.setObjectName("botonAdvertencia")
        boton_quitar.clicked.connect(self._quitar_del_carrito)
        columna_derecha.addWidget(boton_quitar)

        self.etiqueta_total = QLabel("Total: $ 0")
        self.etiqueta_total.setStyleSheet(f"font-size: 22px; font-weight: bold; color: {ACENTO};")
        self.etiqueta_total.setAlignment(Qt.AlignRight)
        columna_derecha.addWidget(self.etiqueta_total)

        self.combo_pago = QComboBox()
        self.combo_pago.addItems(["efectivo", "debito", "credito", "transferencia", "fiado"])
        columna_derecha.addWidget(self.combo_pago)

        boton_cobrar = QPushButton("Cobrar")
        boton_cobrar.setObjectName("botonExito")
        boton_cobrar.setMinimumHeight(56)
        boton_cobrar.setStyleSheet("QPushButton#botonExito { font-size: 18px; }")
        boton_cobrar.clicked.connect(self._confirmar_venta)
        columna_derecha.addWidget(boton_cobrar)

        layout_principal.addLayout(columna_derecha, stretch=1)

    # -- cajero --------------------------------------------------------------

    def recargar_cajeros(self):
        """Reconstruye el combo de cajeros, tratando de mantener el que
        estaba seleccionado (útil cuando se llama tras agregar uno nuevo)."""
        cajero_actual_id = self.combo_cajero.currentData()
        self.combo_cajero.clear()
        for cajero in listar_cajeros(solo_activos=True):
            self.combo_cajero.addItem(cajero["nombre"], userData=cajero["id"])
        if cajero_actual_id is not None:
            indice = self.combo_cajero.findData(cajero_actual_id)
            if indice >= 0:
                self.combo_cajero.setCurrentIndex(indice)

    def _agregar_cajero(self):
        dialogo = DialogoCajero(self)
        if dialogo.exec() == QDialog.Accepted:
            self.recargar_cajeros()
            indice = self.combo_cajero.findData(dialogo.cajero_id)
            if indice >= 0:
                self.combo_cajero.setCurrentIndex(indice)

    # -- grilla de productos ---------------------------------------------

    def recargar_grilla(self):
        """Reconstruye las pestañas y botones según el catálogo actual.
        Se llama al abrir la pantalla y cada vez que cambia el catálogo
        (conectar productos_cambiaron a este método desde la ventana principal)."""
        self.tabs_categorias.clear()
        productos = listar_productos(solo_activos=True)

        por_categoria = {}
        for producto in productos:
            por_categoria.setdefault(producto["categoria"], []).append(producto)

        for categoria, lista_productos in por_categoria.items():
            self.tabs_categorias.addTab(self._crear_pestana(lista_productos), categoria)

    def _crear_pestana(self, lista_productos):
        contenedor = QWidget()
        grilla = QGridLayout(contenedor)
        columnas = 4
        for indice, producto in enumerate(lista_productos):
            boton = QPushButton(f"{producto['nombre']}\n$ {producto['precio']:,.0f}")
            boton.setMinimumSize(120, 70)
            boton.clicked.connect(lambda _checked=False, p=producto: self._click_producto(p))
            grilla.addWidget(boton, indice // columnas, indice % columnas)

        scroll = QScrollArea()
        scroll.setWidget(contenedor)
        scroll.setWidgetResizable(True)
        return scroll

    # -- lógica del carrito -----------------------------------------------

    def _agregar_al_carrito(self, producto_id, nombre, cantidad, precio_unitario, es_venta_libre):
        """
        Agrega una línea al carrito. Si ya hay una línea del MISMO producto
        al MISMO precio unitario, le suma la cantidad en vez de crear una
        fila repetida -- así "2 cafés" sale como una sola línea con
        cantidad 2, no como dos líneas de café separadas.
        """
        for linea in self.carrito:
            es_el_mismo = (
                linea["producto_id"] == producto_id
                and linea["es_venta_libre"] == es_venta_libre
                and linea["precio_unitario"] == precio_unitario
                # para venta libre no hay producto_id -- ahí comparamos
                # también por nombre, para no mezclar dos "Otro" distintos
                # que por casualidad quedaron al mismo precio
                and (producto_id is not None or linea["nombre"] == nombre)
            )
            if es_el_mismo:
                linea["cantidad"] += cantidad
                linea["subtotal"] = linea["cantidad"] * linea["precio_unitario"]
                self._refrescar_carrito()
                return

        self.carrito.append({
            "producto_id": producto_id,
            "nombre": nombre,
            "cantidad": cantidad,
            "precio_unitario": precio_unitario,
            "subtotal": cantidad * precio_unitario,
            "es_venta_libre": es_venta_libre,
        })
        self._refrescar_carrito()

    def _click_producto(self, producto):
        if producto["tipo_venta"] in ("variable", "peso"):
            dialogo = DialogoPrecioVariable(
                self, producto["nombre"], producto["tipo_venta"], producto["precio"]
            )
            if dialogo.exec() != QDialog.Accepted:
                return
            cantidad, precio_unitario, _subtotal = dialogo.resultado()
        else:
            cantidad, precio_unitario = 1, producto["precio"]

        self._agregar_al_carrito(producto["id"], producto["nombre"], cantidad, precio_unitario, 0)

    def _procesar_escaneo(self):
        """Se llama cuando la pistola (o el teclado) manda Enter después del código."""
        codigo = self.campo_escaner.text().strip()
        self.campo_escaner.clear()
        if not codigo:
            return

        producto = buscar_por_codigo_barra(codigo)

        # --- modo consulta: solo mostrar precio, no tocar el carrito ---
        if self.checkbox_modo_consulta.isChecked():
            if producto is None:
                QMessageBox.information(self, "No encontrado", f"Código {codigo}: no está en el catálogo.")
            else:
                QMessageBox.information(
                    self, producto["nombre"],
                    f"{producto['nombre']}\nPrecio: $ {producto['precio']:,.0f}"
                )
            self.campo_escaner.setFocus()
            return

        # --- modo venta normal ---
        if producto is not None:
            self._click_producto(producto)
            self.campo_escaner.setFocus()
            return

        # código no encontrado: ofrecer agregarlo al catálogo ahí mismo
        respuesta = QMessageBox.question(
            self, "Código no encontrado",
            f"No hay ningún producto con el código {codigo}.\n"
            "¿Quieres agregarlo al catálogo ahora?"
        )
        if respuesta == QMessageBox.Yes:
            dialogo = DialogoProducto(self, codigo_barra_inicial=codigo)
            if dialogo.exec() == QDialog.Accepted:
                self.recargar_grilla()
                nuevo_producto = obtener_producto(dialogo.producto_id)
                self._click_producto(nuevo_producto)
        self.campo_escaner.setFocus()

    def _abrir_venta_libre(self):
        dialogo = DialogoVentaLibre(self)
        if dialogo.exec() != QDialog.Accepted:
            return
        nombre, precio = dialogo.resultado()
        self._agregar_al_carrito(None, nombre, 1, precio, 1)

    def _quitar_del_carrito(self):
        filas = self.tabla_carrito.selectionModel().selectedRows()
        if not filas:
            return
        indice = filas[0].row()
        del self.carrito[indice]
        self._refrescar_carrito()

    def _refrescar_carrito(self):
        self.tabla_carrito.setRowCount(len(self.carrito))
        total = 0
        for fila, linea in enumerate(self.carrito):
            nombre = linea["nombre"] + (" (libre)" if linea["es_venta_libre"] else "")
            self.tabla_carrito.setItem(fila, 0, QTableWidgetItem(nombre))
            self.tabla_carrito.setItem(fila, 1, QTableWidgetItem(f"{linea['cantidad']:g}"))
            self.tabla_carrito.setItem(fila, 2, QTableWidgetItem(f"$ {linea['precio_unitario']:,.0f}"))
            self.tabla_carrito.setItem(fila, 3, QTableWidgetItem(f"$ {linea['subtotal']:,.0f}"))
            total += linea["subtotal"]
        self.etiqueta_total.setText(f"Total: $ {total:,.0f}")

    # -- cobro --------------------------------------------------------------

    def _confirmar_venta(self):
        if not self.carrito:
            QMessageBox.information(self, "Carrito vacío", "Agrega al menos un producto antes de cobrar.")
            return

        sesion = sesion_abierta()
        if sesion is None:
            QMessageBox.warning(
                self, "Caja cerrada",
                "No hay una caja abierta. Ábrela primero en la pestaña Arqueo."
            )
            return

        cajero_id = self.combo_cajero.currentData()
        if cajero_id is None:
            QMessageBox.warning(
                self, "Falta el cajero",
                "Selecciona quién está vendiendo (o agrega un cajero con el botón +)."
            )
            return

        total = sum(linea["subtotal"] for linea in self.carrito)
        origen = self.combo_origen.currentData()
        metodo_pago = self.combo_pago.currentText()
        sesion_id = sesion["id"]

        # si es fiado, hay que saber a nombre de quién queda la deuda antes
        # de guardar nada -- si cancela el diálogo, se aborta el cobro
        cliente_id = None
        if metodo_pago == "fiado":
            dialogo_cliente = DialogoSeleccionarCliente(self)
            if dialogo_cliente.exec() != QDialog.Accepted:
                return
            cliente_id = dialogo_cliente.cliente_id

        with conectar() as con:
            cursor_venta = con.execute(
                """INSERT INTO ventas
                   (caja_sesion_id, fecha_hora, origen, total, metodo_pago, cliente_id, cajero_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (sesion_id, ahora_texto(), origen, total, metodo_pago, cliente_id, cajero_id),
            )
            venta_id = cursor_venta.lastrowid

            for linea in self.carrito:
                con.execute(
                    """INSERT INTO detalle_venta
                       (venta_id, producto_id, nombre_producto, cantidad,
                        precio_unitario, subtotal, es_venta_libre)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (venta_id, linea["producto_id"], linea["nombre"], linea["cantidad"],
                     linea["precio_unitario"], linea["subtotal"], linea["es_venta_libre"]),
                )

        QMessageBox.information(self, "Venta registrada", f"Total cobrado: $ {total:,.0f}")
        self.carrito = []
        self._refrescar_carrito()
        self.campo_escaner.setFocus()

        # intento de sincronizar apenas se cierra la venta -- si no hay
        # internet, no hace nada (ver sincronizacion.py); el temporizador
        # de fondo igual la va a subir más tarde
        try:
            from sincronizacion import sincronizar_ahora
            sincronizar_ahora()
        except Exception:
            pass