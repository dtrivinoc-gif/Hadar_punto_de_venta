"""
Capa de base de datos del POS.

Todo lo que toca SQLite directamente vive acá. El resto de los módulos
(productos.py, venta.py, caja_vecina.py, arqueo.py, fiado.py) usan estas
funciones en vez de escribir SQL por su cuenta, para que si algún día
cambia el motor de base de datos, solo haya que tocar este archivo.
"""

import sqlite3
from contextlib import contextmanager

from config import RUTA_BASE_DATOS, asegurar_carpetas


# ---------------------------------------------------------------------------
# Conexión
# ---------------------------------------------------------------------------

@contextmanager
def conectar():
    """
    Entrega una conexión a la base de datos, con foreign keys activadas
    y row_factory configurado para que las filas se puedan leer como
    diccionarios (fila["nombre"] en vez de fila[2]).

    Uso:
        with conectar() as con:
            con.execute(...)
    """
    asegurar_carpetas()
    con = sqlite3.connect(RUTA_BASE_DATOS)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Esquema
# ---------------------------------------------------------------------------

ESQUEMA = """
-- Productos catalogados (incluye los que se venden sueltos: dulces,
-- verduras, cigarros, pan, etc.)
CREATE TABLE IF NOT EXISTS productos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre          TEXT NOT NULL,
    precio          REAL NOT NULL DEFAULT 0,
    -- 'unidad'  -> precio fijo por unidad (cigarro, dulce individual)
    -- 'variable'-> precio se escribe al momento de vender (pan a ojo)
    -- 'peso'    -> se vende por peso (fruta/verdura, si algún día hay balanza)
    tipo_venta      TEXT NOT NULL DEFAULT 'unidad'
                        CHECK (tipo_venta IN ('unidad', 'variable', 'peso')),
    categoria       TEXT NOT NULL DEFAULT 'General',
    codigo_barra    TEXT,               -- puede ser NULL si es producto suelto
    codigo_plu      TEXT,               -- código corto interno para botón rápido
    activo          INTEGER NOT NULL DEFAULT 1,   -- 0 = dado de baja, no se borra
    creado_en       TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- Una sesión de caja = desde que se abre hasta que se cierra (normalmente un día)
CREATE TABLE IF NOT EXISTS caja_sesion (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_apertura          TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    monto_apertura_negocio  REAL NOT NULL DEFAULT 0,
    monto_apertura_vecina   REAL NOT NULL DEFAULT 0,
    fecha_cierre            TEXT,
    monto_cierre_negocio    REAL,       -- monto contado físicamente al cerrar
    monto_cierre_vecina     REAL,
    cerrada                 INTEGER NOT NULL DEFAULT 0
);

-- Encabezado de cada venta
-- NOTA: metodo_pago incluye 'fiado' y cliente_id fue agregado por migración
-- (ver _migrar_ventas_agregar_fiado más abajo) porque la tabla ya existía
-- en instalaciones previas y SQLite no permite modificar un CHECK con ALTER.
CREATE TABLE IF NOT EXISTS ventas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    caja_sesion_id  INTEGER NOT NULL REFERENCES caja_sesion(id),
    fecha_hora      TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    -- de qué caja sale/entra el dinero de esta venta
    origen          TEXT NOT NULL DEFAULT 'venta_negocio'
                        CHECK (origen IN ('venta_negocio', 'caja_vecina')),
    total           REAL NOT NULL DEFAULT 0,
    metodo_pago     TEXT NOT NULL DEFAULT 'efectivo'
                        CHECK (metodo_pago IN ('efectivo', 'debito', 'credito', 'transferencia', 'fiado')),
    anulada         INTEGER NOT NULL DEFAULT 0,
    cliente_id      INTEGER REFERENCES clientes(id)  -- NULL salvo que metodo_pago = 'fiado'
);

-- Detalle línea por línea de cada venta
CREATE TABLE IF NOT EXISTS detalle_venta (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    venta_id        INTEGER NOT NULL REFERENCES ventas(id) ON DELETE CASCADE,
    producto_id     INTEGER REFERENCES productos(id),  -- NULL si es venta libre
    nombre_producto TEXT NOT NULL,      -- copia del nombre al momento de vender
    cantidad        REAL NOT NULL DEFAULT 1,
    precio_unitario REAL NOT NULL DEFAULT 0,
    subtotal        REAL NOT NULL DEFAULT 0,
    -- marca las ventas de cosas no catalogadas (botón "Otro"), para que
    -- el dueño las revise después y decida si las agrega al catálogo
    es_venta_libre  INTEGER NOT NULL DEFAULT 0
);

-- Movimientos de caja vecina (depósitos, retiros, comisión del negocio)
CREATE TABLE IF NOT EXISTS movimientos_caja_vecina (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    caja_sesion_id  INTEGER NOT NULL REFERENCES caja_sesion(id),
    fecha_hora      TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    tipo            TEXT NOT NULL CHECK (tipo IN ('deposito', 'retiro', 'comision')),
    monto           REAL NOT NULL,
    descripcion     TEXT
);

-- Clientes a los que se les fía
CREATE TABLE IF NOT EXISTS clientes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre          TEXT NOT NULL,
    telefono        TEXT,
    notas           TEXT,
    activo          INTEGER NOT NULL DEFAULT 1,
    creado_en       TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- Abonos (pagos) que un cliente hace contra su deuda acumulada de fiado.
-- No se descuentan de una venta puntual: se restan del total adeudado
-- (suma de ventas 'fiado' de ese cliente).
CREATE TABLE IF NOT EXISTS abonos_fiado (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id      INTEGER NOT NULL REFERENCES clientes(id),
    -- sesión de caja en la que se recibió el abono: como es plata real que
    -- entra, arqueo.py debería sumarla al efectivo contado de esa sesión
    caja_sesion_id  INTEGER NOT NULL REFERENCES caja_sesion(id),
    fecha_hora      TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    monto           REAL NOT NULL,
    nota            TEXT
);

CREATE INDEX IF NOT EXISTS idx_ventas_caja_sesion ON ventas(caja_sesion_id);
CREATE INDEX IF NOT EXISTS idx_ventas_cliente ON ventas(cliente_id);
CREATE INDEX IF NOT EXISTS idx_detalle_venta_venta ON detalle_venta(venta_id);
CREATE INDEX IF NOT EXISTS idx_movimientos_caja_sesion ON movimientos_caja_vecina(caja_sesion_id);
CREATE INDEX IF NOT EXISTS idx_productos_activo ON productos(activo);
CREATE INDEX IF NOT EXISTS idx_abonos_cliente ON abonos_fiado(cliente_id);

-- Fila única con la corrección manual de hora (ver tiempo.py / ajustes.py).
-- El CHECK (id = 1) obliga a que exista como máximo una fila.
CREATE TABLE IF NOT EXISTS configuracion_reloj (
    id                  INTEGER PRIMARY KEY CHECK (id = 1),
    desfase_segundos    INTEGER NOT NULL DEFAULT 0
);
"""


def _migrar_ventas_agregar_fiado(con):
    """
    Instalaciones que ya tenían la tabla `ventas` de antes del fiado no
    tienen la columna cliente_id ni 'fiado' en el CHECK de metodo_pago.
    SQLite permite agregar columnas con ALTER TABLE, pero no modificar un
    CHECK existente -- para eso hay que reconstruir la tabla.

    Esta función es segura de llamar siempre: si ya está migrada, no hace
    nada. Si la tabla ventas se acaba de crear con el ESQUEMA de arriba
    (instalación nueva), tampoco hace nada porque ya viene con todo.
    """
    fila = con.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='ventas'"
    ).fetchone()
    if fila is None or "'fiado'" in fila["sql"]:
        return  # no existe todavía (se creará con el esquema nuevo) o ya migrada

    con.execute("PRAGMA foreign_keys = OFF")
    con.executescript("""
        ALTER TABLE ventas RENAME TO ventas_old;

        CREATE TABLE ventas (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            caja_sesion_id  INTEGER NOT NULL REFERENCES caja_sesion(id),
            fecha_hora      TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            origen          TEXT NOT NULL DEFAULT 'venta_negocio'
                                CHECK (origen IN ('venta_negocio', 'caja_vecina')),
            total           REAL NOT NULL DEFAULT 0,
            metodo_pago     TEXT NOT NULL DEFAULT 'efectivo'
                                CHECK (metodo_pago IN ('efectivo', 'debito', 'credito', 'transferencia', 'fiado')),
            anulada         INTEGER NOT NULL DEFAULT 0,
            cliente_id      INTEGER REFERENCES clientes(id)
        );

        INSERT INTO ventas (id, caja_sesion_id, fecha_hora, origen, total, metodo_pago, anulada, cliente_id)
            SELECT id, caja_sesion_id, fecha_hora, origen, total, metodo_pago, anulada, NULL
            FROM ventas_old;

        DROP TABLE ventas_old;

        CREATE INDEX IF NOT EXISTS idx_ventas_caja_sesion ON ventas(caja_sesion_id);
        CREATE INDEX IF NOT EXISTS idx_ventas_cliente ON ventas(cliente_id);
    """)
    con.execute("PRAGMA foreign_keys = ON")


def inicializar_base_datos():
    """
    Crea todas las tablas si no existen, y corre las migraciones necesarias
    sobre tablas que ya existían de versiones anteriores del POS.
    Se puede llamar cada vez que arranca el programa sin problema.
    """
    with conectar() as con:
        # las tablas nuevas (clientes, abonos_fiado) deben existir antes de
        # migrar ventas, porque ventas.cliente_id las referencia
        con.executescript("""
            CREATE TABLE IF NOT EXISTS clientes (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre          TEXT NOT NULL,
                telefono        TEXT,
                notas           TEXT,
                activo          INTEGER NOT NULL DEFAULT 1,
                creado_en       TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            );
        """)
        _migrar_ventas_agregar_fiado(con)
        con.executescript(ESQUEMA)
        con.execute(
            "INSERT OR IGNORE INTO configuracion_reloj (id, desfase_segundos) VALUES (1, 0)"
        )


if __name__ == "__main__":
    # Permite correr "python db.py" directo para inicializar la base
    # sin tener que abrir toda la aplicación.
    inicializar_base_datos()
    print(f"Base de datos lista en: {RUTA_BASE_DATOS}")