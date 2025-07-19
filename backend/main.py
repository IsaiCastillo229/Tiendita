from fastapi import FastAPI, HTTPException, Depends, Body
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, DateTime, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

app = FastAPI()

# Configurar CORS para permitir peticiones del frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Configuración de la base de datos en archivo local (persistente durante desarrollo) ---
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- Modelo Producto ---
class ProductoDB(Base):
    __tablename__ = "productos"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, index=True)
    codigo_barras = Column(String, unique=True, index=True)
    precio = Column(Float)
    cantidad = Column(Integer)

# --- Modelo Venta ---
class VentaDB(Base):
    __tablename__ = "ventas"
    id = Column(Integer, primary_key=True, index=True)
    fecha = Column(DateTime, default=func.now())
    total = Column(Float)
    detalles = relationship("DetalleVentaDB", back_populates="venta")

# --- Modelo DetalleVenta ---
class DetalleVentaDB(Base):
    __tablename__ = "detalles_venta"
    id = Column(Integer, primary_key=True, index=True)
    venta_id = Column(Integer, ForeignKey("ventas.id"))
    producto_id = Column(Integer, ForeignKey("productos.id"))
    cantidad = Column(Integer)
    precio_unitario = Column(Float)
    producto = relationship("ProductoDB")
    venta = relationship("VentaDB", back_populates="detalles")

# --- Modelo CuentaPendiente ---
class CuentaPendienteDB(Base):
    __tablename__ = "cuentas_pendientes"
    id = Column(Integer, primary_key=True, index=True)
    nombre_cliente = Column(String, index=True)
    fecha_creacion = Column(DateTime, default=func.now())
    estado = Column(String, default="pendiente")  # pendiente o pagada
    detalles = relationship("DetalleCuentaPendienteDB", back_populates="cuenta")
    total = Column(Float)

class DetalleCuentaPendienteDB(Base):
    __tablename__ = "detalles_cuenta_pendiente"
    id = Column(Integer, primary_key=True, index=True)
    cuenta_id = Column(Integer, ForeignKey("cuentas_pendientes.id"))
    producto_id = Column(Integer, ForeignKey("productos.id"))
    cantidad = Column(Integer)
    precio_unitario = Column(Float)
    producto = relationship("ProductoDB")
    cuenta = relationship("CuentaPendienteDB", back_populates="detalles")

Base.metadata.create_all(bind=engine)

# --- Esquemas Pydantic ---
class Producto(BaseModel):
    id: Optional[int]
    nombre: str
    codigo_barras: str
    precio: float
    cantidad: int
    class Config:
        orm_mode = True

class ProductoCreate(BaseModel):
    nombre: str
    codigo_barras: str
    precio: float
    cantidad: int

# --- Esquemas Pydantic para ventas ---
class DetalleVenta(BaseModel):
    producto_id: int
    cantidad: int
    precio_unitario: float
    nombre_producto: Optional[str] = None
    class Config:
        orm_mode = True

class Venta(BaseModel):
    id: int
    fecha: datetime
    total: float
    detalles: List[DetalleVenta]
    class Config:
        orm_mode = True

class DetalleVentaCreate(BaseModel):
    producto_id: int
    cantidad: int

class VentaCreate(BaseModel):
    detalles: List[DetalleVentaCreate]

# --- Esquemas Pydantic para cuentas pendientes ---
class DetalleCuentaPendiente(BaseModel):
    producto_id: int
    cantidad: int
    precio_unitario: float
    nombre_producto: Optional[str] = None
    class Config:
        orm_mode = True

class CuentaPendiente(BaseModel):
    id: int
    nombre_cliente: str
    fecha_creacion: datetime
    estado: str
    total: float
    detalles: List[DetalleCuentaPendiente]
    class Config:
        orm_mode = True

class DetalleCuentaPendienteCreate(BaseModel):
    producto_id: int
    cantidad: int

class CuentaPendienteCreate(BaseModel):
    nombre_cliente: str
    detalles: List[DetalleCuentaPendienteCreate]

class AgregarProductosCuentaRequest(BaseModel):
    detalles: List[DetalleCuentaPendienteCreate]

# --- Dependencia para obtener sesión de BD ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Endpoints de productos ---
@app.post("/api/productos", response_model=Producto)
def crear_producto(producto: ProductoCreate, db: Session = Depends(get_db)):
    db_producto = ProductoDB(**producto.dict())
    db.add(db_producto)
    try:
        db.commit()
        db.refresh(db_producto)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail="Código de barras ya registrado")
    return db_producto

@app.get("/api/productos", response_model=List[Producto])
def listar_productos(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return db.query(ProductoDB).offset(skip).limit(limit).all()

@app.get("/api/productos/buscar/{codigo_barras}", response_model=Producto)
def buscar_producto_codigo(codigo_barras: str, db: Session = Depends(get_db)):
    producto = db.query(ProductoDB).filter(ProductoDB.codigo_barras == codigo_barras).first()
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return producto

@app.put("/api/productos/{producto_id}", response_model=Producto)
def editar_producto(producto_id: int, producto: ProductoCreate, db: Session = Depends(get_db)):
    db_producto = db.query(ProductoDB).filter(ProductoDB.id == producto_id).first()
    if not db_producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    for key, value in producto.dict().items():
        setattr(db_producto, key, value)
    try:
        db.commit()
        db.refresh(db_producto)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail="Error al actualizar el producto")
    return db_producto

@app.delete("/api/productos/{producto_id}")
def eliminar_producto(producto_id: int, db: Session = Depends(get_db)):
    db_producto = db.query(ProductoDB).filter(ProductoDB.id == producto_id).first()
    if not db_producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    db.delete(db_producto)
    db.commit()
    return {"mensaje": "Producto eliminado"}

# --- Endpoints de ventas ---
@app.post("/api/ventas", response_model=Venta)
def crear_venta(venta: VentaCreate, db: Session = Depends(get_db)):
    total = 0
    detalles_db = []
    for item in venta.detalles:
        producto = db.query(ProductoDB).filter(ProductoDB.id == item.producto_id).first()
        if not producto:
            raise HTTPException(status_code=404, detail=f"Producto con id {item.producto_id} no encontrado")
        if producto.cantidad < item.cantidad:
            raise HTTPException(status_code=400, detail=f"Stock insuficiente para {producto.nombre}")
        producto.cantidad -= item.cantidad
        subtotal = producto.precio * item.cantidad
        total += subtotal
        detalles_db.append(DetalleVentaDB(producto_id=producto.id, cantidad=item.cantidad, precio_unitario=producto.precio))
    venta_db = VentaDB(total=total, detalles=detalles_db)
    db.add(venta_db)
    db.commit()
    db.refresh(venta_db)
    # Agregar nombre del producto al detalle para la respuesta
    detalles = []
    for d in venta_db.detalles:
        detalles.append(DetalleVenta(
            producto_id=d.producto_id,
            cantidad=d.cantidad,
            precio_unitario=d.precio_unitario,
            nombre_producto=d.producto.nombre
        ))
    return Venta(
        id=venta_db.id,
        fecha=venta_db.fecha,
        total=venta_db.total,
        detalles=detalles
    )

@app.get("/api/ventas", response_model=List[Venta])
def listar_ventas(db: Session = Depends(get_db)):
    ventas = db.query(VentaDB).all()
    resultado = []
    for v in ventas:
        detalles = [
            DetalleVenta(
                producto_id=d.producto_id,
                cantidad=d.cantidad,
                precio_unitario=d.precio_unitario,
                nombre_producto=d.producto.nombre
            ) for d in v.detalles
        ]
        resultado.append(Venta(
            id=v.id,
            fecha=v.fecha,
            total=v.total,
            detalles=detalles
        ))
    return resultado

@app.get("/api/ventas/{venta_id}", response_model=Venta)
def obtener_venta(venta_id: int, db: Session = Depends(get_db)):
    v = db.query(VentaDB).filter(VentaDB.id == venta_id).first()
    if not v:
        raise HTTPException(status_code=404, detail="Venta no encontrada")
    detalles = [
        DetalleVenta(
            producto_id=d.producto_id,
            cantidad=d.cantidad,
            precio_unitario=d.precio_unitario,
            nombre_producto=d.producto.nombre
        ) for d in v.detalles
    ]
    return Venta(
        id=v.id,
        fecha=v.fecha,
        total=v.total,
        detalles=detalles
    )

# --- Endpoints de cuentas pendientes ---
@app.post("/api/cuentas_pendientes", response_model=CuentaPendiente)
def crear_cuenta_pendiente(cuenta: CuentaPendienteCreate, db: Session = Depends(get_db)):
    total = 0
    detalles_db = []
    for item in cuenta.detalles:
        producto = db.query(ProductoDB).filter(ProductoDB.id == item.producto_id).first()
        if not producto:
            raise HTTPException(status_code=404, detail=f"Producto con id {item.producto_id} no encontrado")
        if producto.cantidad < item.cantidad:
            raise HTTPException(status_code=400, detail=f"Stock insuficiente para {producto.nombre}")
        producto.cantidad -= item.cantidad
        subtotal = producto.precio * item.cantidad
        total += subtotal
        detalles_db.append(DetalleCuentaPendienteDB(producto_id=producto.id, cantidad=item.cantidad, precio_unitario=producto.precio))
    cuenta_db = CuentaPendienteDB(nombre_cliente=cuenta.nombre_cliente, total=total, detalles=detalles_db)
    db.add(cuenta_db)
    db.commit()
    db.refresh(cuenta_db)
    detalles = []
    for d in cuenta_db.detalles:
        detalles.append(DetalleCuentaPendiente(
            producto_id=d.producto_id,
            cantidad=d.cantidad,
            precio_unitario=d.precio_unitario,
            nombre_producto=d.producto.nombre
        ))
    return CuentaPendiente(
        id=cuenta_db.id,
        nombre_cliente=cuenta_db.nombre_cliente,
        fecha_creacion=cuenta_db.fecha_creacion,
        estado=cuenta_db.estado,
        total=cuenta_db.total,
        detalles=detalles
    )

@app.get("/api/cuentas_pendientes", response_model=List[CuentaPendiente])
def listar_cuentas_pendientes(db: Session = Depends(get_db)):
    cuentas = db.query(CuentaPendienteDB).filter(CuentaPendienteDB.estado == "pendiente").all()
    resultado = []
    for c in cuentas:
        detalles = [
            DetalleCuentaPendiente(
                producto_id=d.producto_id,
                cantidad=d.cantidad,
                precio_unitario=d.precio_unitario,
                nombre_producto=d.producto.nombre
            ) for d in c.detalles
        ]
        resultado.append(CuentaPendiente(
            id=c.id,
            nombre_cliente=c.nombre_cliente,
            fecha_creacion=c.fecha_creacion,
            estado=c.estado,
            total=c.total,
            detalles=detalles
        ))
    return resultado

@app.post("/api/cuentas_pendientes/{cuenta_id}/pagar", response_model=CuentaPendiente)
def pagar_cuenta_pendiente(cuenta_id: int, db: Session = Depends(get_db)):
    cuenta = db.query(CuentaPendienteDB).filter(CuentaPendienteDB.id == cuenta_id, CuentaPendienteDB.estado == "pendiente").first()
    if not cuenta:
        raise HTTPException(status_code=404, detail="Cuenta pendiente no encontrada")
    # Crear venta en historial
    detalles_venta = [
        DetalleVentaDB(producto_id=d.producto_id, cantidad=d.cantidad, precio_unitario=d.precio_unitario)
        for d in cuenta.detalles
    ]
    venta_db = VentaDB(total=cuenta.total, detalles=detalles_venta)
    db.add(venta_db)
    cuenta.estado = "pagada"
    db.commit()
    db.refresh(cuenta)
    detalles = [
        DetalleCuentaPendiente(
            producto_id=d.producto_id,
            cantidad=d.cantidad,
            precio_unitario=d.precio_unitario,
            nombre_producto=d.producto.nombre
        ) for d in cuenta.detalles
    ]
    return CuentaPendiente(
        id=cuenta.id,
        nombre_cliente=cuenta.nombre_cliente,
        fecha_creacion=cuenta.fecha_creacion,
        estado=cuenta.estado,
        total=cuenta.total,
        detalles=detalles
    )

@app.post("/api/cuentas_pendientes/{cuenta_id}/agregar_productos", response_model=CuentaPendiente)
def agregar_productos_cuenta_pendiente(
    cuenta_id: int,
    req: AgregarProductosCuentaRequest,
    db: Session = Depends(get_db)
):
    cuenta = db.query(CuentaPendienteDB).filter(CuentaPendienteDB.id == cuenta_id, CuentaPendienteDB.estado == "pendiente").first()
    if not cuenta:
        raise HTTPException(status_code=404, detail="Cuenta pendiente no encontrada")
    total_agregado = 0
    for item in req.detalles:
        producto = db.query(ProductoDB).filter(ProductoDB.id == item.producto_id).first()
        if not producto:
            raise HTTPException(status_code=404, detail=f"Producto con id {item.producto_id} no encontrado")
        if producto.cantidad < item.cantidad:
            raise HTTPException(status_code=400, detail=f"Stock insuficiente para {producto.nombre}")
        producto.cantidad -= item.cantidad
        subtotal = producto.precio * item.cantidad
        total_agregado += subtotal
        detalle = DetalleCuentaPendienteDB(
            cuenta_id=cuenta.id,
            producto_id=producto.id,
            cantidad=item.cantidad,
            precio_unitario=producto.precio
        )
        db.add(detalle)
    cuenta.total += total_agregado
    db.commit()
    db.refresh(cuenta)
    detalles = [
        DetalleCuentaPendiente(
            producto_id=d.producto_id,
            cantidad=d.cantidad,
            precio_unitario=d.precio_unitario,
            nombre_producto=d.producto.nombre
        ) for d in cuenta.detalles
    ]
    return CuentaPendiente(
        id=cuenta.id,
        nombre_cliente=cuenta.nombre_cliente,
        fecha_creacion=cuenta.fecha_creacion,
        estado=cuenta.estado,
        total=cuenta.total,
        detalles=detalles
    )

# Endpoint de prueba
@app.get("/api/hola")
def leer_mensaje():
    return {"mensaje": "Hola desde FastAPI"}