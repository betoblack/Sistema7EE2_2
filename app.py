from flask import Flask, redirect, url_for, session, render_template, request
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv
from functools import wraps
from database import get_db
from googleapiclient.discovery import build
from urllib import request as urlrequest, parse
import os
import secrets
import json
import base64
import ipaddress
from urllib import request as urlrequest
from urllib import parse
from urllib.error import HTTPError
from flask import jsonify
import pandas as pd
from flask import send_file

load_dotenv()

app = Flask(__name__)
app.secret_key = "super_secret_key"

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

# =========================
# GOOGLE OAUTH
# =========================

oauth = OAuth(app)

google = oauth.register(
    name='google',
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

# =========================
# DECORADOR ADMIN
# =========================

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "rol" not in session or session["rol"] != "admin":
            return "Acceso no autorizado"
        return f(*args, **kwargs)
    return decorated_function

# =========================
# RUTAS PRINCIPALES
# =========================

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/register")
def register():
    return render_template("register.html")

# =========================
# REGISTRO MANUAL
# =========================

@app.route("/register_user", methods=["POST"])
def register_user():
    correo = request.form["correo"]
    contraseña = request.form["password"]
    rol = request.form["rol"]

    conexion = get_db()
    cursor = conexion.cursor()

    cursor.execute("""
        INSERT INTO usuarios (correo, contraseña, rol, tipo_registro)
        VALUES (?, ?, ?, ?)
    """, (correo, contraseña, rol, "manual"))

    conexion.commit()
    cursor.close()
    conexion.close()

    return redirect("/")

# =========================
# LOGIN GOOGLE
# =========================

@app.route("/login", methods=["POST"])
def login():
    correo = request.form["correo"]
    contraseña = request.form["password"]

    conexion = get_db()
    cursor = conexion.cursor()

    cursor.execute("SELECT rol FROM usuarios WHERE correo = ? AND contraseña = ?", 
                   (correo, contraseña))
    usuario = cursor.fetchone()

    cursor.close()
    conexion.close()

    if usuario:
        session["correo"] = correo
        session["rol"] = usuario[0]
        return redirect(url_for("dashboard"))
    else:
        return "Credenciales incorrectas"

@app.route("/login/google")
def login_google():
    nonce = secrets.token_urlsafe(16)
    session["nonce"] = nonce

    redirect_uri = url_for("google_callback", _external=True)
    return oauth.google.authorize_redirect(
        redirect_uri,
        nonce=nonce
    )

@app.route("/login/google/callback")
def google_callback():
    token = oauth.google.authorize_access_token()
    nonce = session.get("nonce")
    user = oauth.google.parse_id_token(token, nonce=nonce)

    email = user["email"]
    nombre = user.get("name")

    if email.endswith("pro@gmail.com"):
        rol_detectado = "profesor"
    else:
        rol_detectado = "alumno"

    conexion = get_db()
    cursor = conexion.cursor()

    cursor.execute("SELECT rol FROM usuarios WHERE correo = ?", (email,))
    resultado = cursor.fetchone()

    if resultado:
        rol = resultado[0]
    else:
        cursor.execute("""
            INSERT INTO usuarios (correo, contraseña, rol, nombre, tipo_registro)
            VALUES (?, ?, ?, ?, ?)
        """, (email, "google_login", rol_detectado, nombre, "google"))
        conexion.commit()
        rol = rol_detectado

    cursor.close()
    conexion.close()

    session["correo"] = email
    session["rol"] = rol

    return redirect(url_for("dashboard"))

# =========================
# DASHBOARD (NO SE TOCA)
# =========================

@app.route("/dashboard")
def dashboard():
    if "rol" not in session:
        return redirect("/")

    rol = session.get("rol")
    correo = session.get("correo")

    if rol == "profesor":
        return render_template("profesor.html", correo=correo, rol=rol)

    elif rol == "alumno":
        return render_template("alumno.html", correo=correo, rol=rol)

    elif rol == "admin":
        return render_template("admin.html", correo=correo, rol=rol)

    return "Rol no válido"


# =========================
# RUTAS SISTEMA MATERIALES
# =========================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "rol" not in session:
            return redirect("/")
        return f(*args, **kwargs)
    return decorated_function

@app.route("/inicio")
@login_required
def index():
    return render_template("index.html")

@app.route("/prestamos")
@login_required
def prestamos():

    conexion = get_db()
    cursor = conexion.cursor()

    # 🔹 Obtener préstamos activos
    cursor.execute("""
        SELECT p.id,
               u.nombre AS usuario,
               m.nombre AS material,
               p.cantidad,
               p.fecha,
               p.estado
        FROM prestamos p
        JOIN usuarios u ON p.usuario_id = u.id
        JOIN materiales m ON p.material_id = m.id
        WHERE p.estado = 'Activo'
    """)
    prestamos = cursor.fetchall()

    # 🔹 Obtener usuarios para el select
    cursor.execute("SELECT id, nombre, rol FROM usuarios")
    usuarios = cursor.fetchall()

    # 🔹 Obtener materiales para el select
    cursor.execute("SELECT id, nombre, cantidad FROM materiales")
    materiales = cursor.fetchall()

    cursor.close()
    conexion.close()

    return render_template(
        "prestamos.html",
        prestamos=prestamos,
        usuarios=usuarios,
        materiales=materiales
    )

@app.route("/materiales")
@login_required
def materiales():

    conexion = get_db()
    cursor = conexion.cursor()

    cursor.execute("SELECT nombre, descripcion, cantidad, estado FROM materiales")
    materiales = cursor.fetchall()

    cursor.close()
    conexion.close()

    video_url = None
    video_watch_url = None

    if materiales:
        nombre_material = materiales[0][0]  # usa el primer material
        video_url, video_watch_url = buscar_video_tutorial(nombre_material)

    return render_template(
        "materiales.html",
        materiales=materiales,
        video_url=video_url,
        video_watch_url=video_watch_url
    )

@app.route("/usuarios")
@login_required
def usuarios():
    return render_template("admin.html")

@app.route("/pagos")
@login_required
def pagos():

    paypal_configured = bool(PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET)

    conexion = get_db()
    cursor = conexion.cursor()

    # usuarios
    cursor.execute("SELECT id, nombre, rol FROM usuarios")
    usuarios = cursor.fetchall()

    # prestamos
    cursor.execute("""
        SELECT p.id,
               u.nombre AS usuario,
               m.nombre AS material,
               p.estado
        FROM prestamos p
        JOIN usuarios u ON p.usuario_id = u.id
        JOIN materiales m ON p.material_id = m.id
    """)
    prestamos = cursor.fetchall()

    # pagos
    cursor.execute("""
        SELECT pm.id,
               u.nombre AS usuario,
               pm.motivo,
               pm.descripcion,
               pm.monto,
               pm.moneda,
               pm.estado,
               pm.paypal_order_id,
               pm.paypal_capture_id,
               pm.fecha_pago,
               pm.fecha_creacion
        FROM pagos_multa pm
        JOIN usuarios u ON pm.usuario_id = u.id
        ORDER BY pm.fecha_creacion DESC
    """)
    pagos = cursor.fetchall()

    cursor.close()
    conexion.close()

    return render_template(
        "pagos.html",
        usuarios=usuarios,
        prestamos=prestamos,
        pagos=pagos,
        paypal_configured=paypal_configured,
        paypal_mode=PAYPAL_MODE,
        paypal_currency=PAYPAL_CURRENCY,
        paypal_client_id=PAYPAL_CLIENT_ID
    )

@app.route("/geolocalizacion")
@login_required
def geolocalizacion():
    return render_template("geolocalizacion.html")


import pandas as pd

@app.route("/importar_materiales", methods=["POST"])
@login_required
def importar_materiales():

    archivo = request.files["archivo"]

    if not archivo:
        return "No se seleccionó archivo"

    # Leer Excel
    df = pd.read_excel(archivo)

    conexion = get_db()
    cursor = conexion.cursor()

    df.columns = df.columns.str.strip().str.lower()

    columnas_requeridas = ["nombre", "descripcion", "cantidad", "estado"]

    for col in columnas_requeridas:
        if col not in df.columns:
            return f"Falta la columna: {col}"

    for _, row in df.iterrows():
        cursor.execute("""
            INSERT INTO materiales (nombre, descripcion, cantidad, estado)
            VALUES (?, ?, ?, ?)
        """, (
            row["nombre"],
            row["descripcion"],
            int(row["cantidad"]),
            row["estado"]
        ))

    conexion.commit()
    cursor.close()
    conexion.close()

    return redirect("/estadisticas")


@app.route("/exportar_excel")
@login_required
def exportar_excel():

    conexion = get_db()

    # 🔹 Obtener datos
    prestamos = pd.read_sql("SELECT * FROM prestamos", conexion)
    pagos = pd.read_sql("SELECT * FROM pagos_multa", conexion)

    # 🔹 Crear archivo Excel
    archivo = "reporte.xlsx"
    with pd.ExcelWriter(archivo, engine="openpyxl") as writer:
        prestamos.to_excel(writer, sheet_name="Prestamos", index=False)
        pagos.to_excel(writer, sheet_name="Pagos", index=False)

    conexion.close()

    return send_file(archivo, as_attachment=True)

@app.route("/materialesP")
@login_required
def materialesP():

    conexion = get_db()
    cursor = conexion.cursor()

    cursor.execute("SELECT nombre, descripcion, cantidad, estado FROM materiales")
    materiales = cursor.fetchall()

    cursor.close()
    conexion.close()

    video_url = None
    video_watch_url = None

    if materiales:
        nombre_material = materiales[0][0]  # usa el primer material
        video_url, video_watch_url = buscar_video_tutorial(nombre_material)

    return render_template(
        "materialesP.html",
        materiales=materiales,
        video_url=video_url,
        video_watch_url=video_watch_url
    )

@app.route("/pagosP")
@login_required
def pagosP():

    paypal_configured = bool(PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET)

    conexion = get_db()
    cursor = conexion.cursor()

    # usuarios
    cursor.execute("SELECT id, nombre, rol FROM usuarios")
    usuarios = cursor.fetchall()

    # prestamos
    cursor.execute("""
        SELECT p.id,
               u.nombre AS usuario,
               m.nombre AS material,
               p.estado
        FROM prestamos p
        JOIN usuarios u ON p.usuario_id = u.id
        JOIN materiales m ON p.material_id = m.id
    """)
    prestamos = cursor.fetchall()

    # pagos
    cursor.execute("""
        SELECT pm.id,
               u.nombre AS usuario,
               pm.motivo,
               pm.descripcion,
               pm.monto,
               pm.moneda,
               pm.estado,
               pm.paypal_order_id,
               pm.paypal_capture_id,
               pm.fecha_pago,
               pm.fecha_creacion
        FROM pagos_multa pm
        JOIN usuarios u ON pm.usuario_id = u.id
        ORDER BY pm.fecha_creacion DESC
    """)
    pagos = cursor.fetchall()

    cursor.close()
    conexion.close()

    return render_template(
        "pagosP.html",
        usuarios=usuarios,
        prestamos=prestamos,
        pagos=pagos,
        paypal_configured=paypal_configured,
        paypal_mode=PAYPAL_MODE,
        paypal_currency=PAYPAL_CURRENCY,
        paypal_client_id=PAYPAL_CLIENT_ID
    )

@app.route("/geolocalizacionP")
@login_required
def geolocalizacionP():
    return render_template("geolocalizacionP.html")

@app.route("/prestamos")
@login_required
def prestamosP():

    conexion = get_db()
    cursor = conexion.cursor()

    # 🔹 Obtener préstamos activos
    cursor.execute("""
        SELECT p.id,
               u.nombre AS usuario,
               m.nombre AS material,
               p.cantidad,
               p.fecha,
               p.estado
        FROM prestamos p
        JOIN usuarios u ON p.usuario_id = u.id
        JOIN materiales m ON p.material_id = m.id
        WHERE p.estado = 'Activo'
    """)
    prestamos = cursor.fetchall()

    # 🔹 Obtener usuarios para el select
    cursor.execute("SELECT id, nombre, rol FROM usuarios")
    usuarios = cursor.fetchall()

    # 🔹 Obtener materiales para el select
    cursor.execute("SELECT id, nombre, cantidad FROM materiales")
    materiales = cursor.fetchall()

    cursor.close()
    conexion.close()

    return render_template(
        "prestamosP.html",
        prestamos=prestamos,
        usuarios=usuarios,
        materiales=materiales
    )

# =========================
# PANEL ADMIN
# =========================

@app.route("/admin")
@admin_required
def admin_panel():
    conexion = get_db()
    cursor = conexion.cursor()

    cursor.execute("SELECT id, correo, rol FROM usuarios")
    usuarios = cursor.fetchall()

    cursor.close()
    conexion.close()

    return render_template("admin.html", usuarios=usuarios)

@app.route("/cambiar_rol/<int:id>", methods=["POST"])
@admin_required
def cambiar_rol(id):
    nuevo_rol = request.form["rol"]

    conexion = get_db()
    cursor = conexion.cursor()

    cursor.execute("UPDATE usuarios SET rol = ? WHERE id = ?", (nuevo_rol, id))
    conexion.commit()

    cursor.close()
    conexion.close()

    return redirect(url_for("admin_panel"))

@app.route("/eliminar/<int:id>")
@admin_required
def eliminar_usuario(id):
    conexion = get_db()
    cursor = conexion.cursor()

    cursor.execute("DELETE FROM usuarios WHERE id = ?", (id,))
    conexion.commit()

    cursor.close()
    conexion.close()

    return redirect(url_for("admin_panel"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/profesor")
@login_required
def profesor():
    if session["rol"] != "profesor":
        return "Acceso no autorizado"
    return render_template("profesor.html")

@app.route("/alumno")
@login_required
def alumno():
    if session["rol"] != "alumno":
        return "Acceso no autorizado"
    return render_template("alumno.html")

@app.route("/guardar_prestamo", methods=["POST"]) 
@login_required 
def guardar_prestamo(): 
    usuario_id = request.form.get("usuario_id")
    material_id = request.form.get("material_id") 
    cantidad = request.form.get("cantidad") 
      
    if not usuario_id or not material_id or not cantidad: return "Datos incompletos" 
    conexion = get_db() 
    cursor = conexion.cursor() 
    # Verificar stock 
    cursor.execute("SELECT cantidad FROM materiales WHERE id = ?", (material_id,)) 
    material = cursor.fetchone() 
       
    if not material: return "Material no encontrado" 
        
    stock_actual = material[0] 
    if int(cantidad) > stock_actual: return "No hay suficiente stock" 

# Insertar préstamo 
    cursor.execute(""" INSERT INTO prestamos (usuario_id, material_id, cantidad, fecha, estado) VALUES (?, ?, ?, GETDATE(), 'Activo') """, (usuario_id, material_id, cantidad)) 
        
    # Descontar stock  
    cursor.execute(""" UPDATE materiales SET cantidad = cantidad - ? WHERE id = ? """, (cantidad, material_id)) 
        
    conexion.commit() 
    cursor.close() 
    conexion.close() 
    return redirect("/prestamos") 
            
    
@app.route("/guardar_prestamoP", methods=["POST"]) 
@login_required 
def guardar_prestamoP(): 
    usuario_id = request.form.get("usuario_id") 
    material_id = request.form.get("material_id") 
    cantidad = request.form.get("cantidad") 
        
    if not usuario_id or not material_id or not cantidad: return "Datos incompletos" 
    conexion = get_db() 
    cursor = conexion.cursor() 

    cursor.execute("SELECT cantidad FROM materiales WHERE id = ?", (material_id,)) 
    material = cursor.fetchone() 
        
    if not material: return "Material no encontrado" 
    stock_actual = material[0] 
    if int(cantidad) > stock_actual: return "No hay suficiente stock" 
        
    cursor.execute(""" INSERT INTO prestamos (usuario_id, material_id, cantidad, fecha, estado) VALUES (?, ?, ?, GETDATE(), 'Activo') """, (usuario_id, material_id, cantidad)) 
        
    cursor.execute(""" UPDATE materiales SET cantidad = cantidad - ? WHERE id = ? """, (cantidad, material_id)) 
        
    conexion.commit() 
    cursor.close() 
    conexion.close() 
    return redirect("/prestamosP")

def _load_dotenv(dotenv_path: str = ".env"):
    if not os.path.exists(dotenv_path):
        return

    try:
        with open(dotenv_path, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except OSError:
        return


_load_dotenv()

YOUTUBE_API_KEY = "AIzaSyAYcAPtR1c1Z_s0DJKJ17dw86aVNUUnvtQ"
VIDEO_FALLBACK = "https://www.youtube.com/embed/dQw4w9WgXcQ"
PAYPAL_MODE = os.getenv("PAYPAL_MODE", "sandbox").strip().lower()
PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID", "").strip()
PAYPAL_CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET", "").strip()
PAYPAL_CURRENCY = os.getenv("PAYPAL_CURRENCY", "MXN").strip().upper()


def buscar_video_tutorial(nombre_material: str):
    print("API key cargada:", bool(YOUTUBE_API_KEY))

    if not YOUTUBE_API_KEY:
        return None, None

    try:
        youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

        search_res = youtube.search().list(
            q=f"tutorial {nombre_material}",
            part="snippet",
            type="video",
            maxResults=10,
        ).execute()

        video_ids = [item["id"]["videoId"] for item in search_res.get("items", [])]
        print("Video IDs encontrados:", video_ids)

        if not video_ids:
            return None, None

        details = youtube.videos().list(
            part="status",
            id=",".join(video_ids),
        ).execute()

        embeddable_ids = {
            item["id"]
            for item in details.get("items", [])
            if item.get("status", {}).get("embeddable") is True
        }
        print("Embeddables:", embeddable_ids)

        for vid in video_ids:
            if vid in embeddable_ids:
                return (
                    f"https://www.youtube.com/embed/{vid}",
                    f"https://www.youtube.com/watch?v={vid}",
                )

    except Exception as e:
        print("Error YouTube:", e)

    return None, None


def _api_error(message: str, status_code: int = 400):
    return jsonify({"ok": False, "error": message}), status_code


def _paypal_api_base():
    return "https://api-m.paypal.com" if PAYPAL_MODE == "live" else "https://api-m.sandbox.paypal.com"


def _paypal_configured():
    return bool(PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET)


def _paypal_request(path: str, method: str = "GET", body: dict | None = None, token: str | None = None):
    url = f"{_paypal_api_base()}{path}"
    headers = {"Content-Type": "application/json"}

    if token:
        headers["Authorization"] = f"Bearer {token}"

    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")

    req = urlrequest.Request(url=url, data=data, headers=headers, method=method)

    try:
        with urlrequest.urlopen(req, timeout=15) as response:
            return response.getcode(), json.loads(response.read().decode("utf-8"))
    except HTTPError as e:
        raw = e.read().decode("utf-8") if e.fp else "{}"
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"message": raw}
        return e.code, payload


def _paypal_access_token():
    credentials = f"{PAYPAL_CLIENT_ID}:{PAYPAL_CLIENT_SECRET}"
    encoded_credentials = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")

    req = urlrequest.Request(
        url=f"{_paypal_api_base()}/v1/oauth2/token",
        data=b"grant_type=client_credentials",
        headers={
            "Authorization": f"Basic {encoded_credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )

    try:
        with urlrequest.urlopen(req, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return payload.get("access_token")
    except Exception:
        return None


def _ensure_pagos_table():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        IF OBJECT_ID('pagos_multa', 'U') IS NULL
        BEGIN
            CREATE TABLE pagos_multa (
                id INT IDENTITY(1,1) PRIMARY KEY,
                usuario_id INT NOT NULL,
                prestamo_id INT NULL,
                motivo VARCHAR(20) NOT NULL,
                descripcion VARCHAR(255) NULL,
                monto DECIMAL(10,2) NOT NULL,
                moneda VARCHAR(10) NOT NULL,
                estado VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE',
                paypal_order_id VARCHAR(64) NULL,
                paypal_capture_id VARCHAR(64) NULL,
                fecha_creacion DATETIME NOT NULL DEFAULT GETDATE(),
                fecha_pago DATETIME NULL,
                CONSTRAINT fk_pago_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id),
                CONSTRAINT fk_pago_prestamo FOREIGN KEY (prestamo_id) REFERENCES prestamos(id)
            );
        END
        """
    )
    conn.commit()
    conn.close()


def _cliente_ip():
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.remote_addr or ""


def _ip_valida(ip_texto: str):
    try:
        return str(ipaddress.ip_address(ip_texto))
    except ValueError:
        return None


@app.route("/api/v1/geolocalizacion/ip", methods=["GET"])
def geolocalizacion_por_ip():
    ip_entrada = (request.args.get("ip") or _cliente_ip()).strip()
    ip_limpia = _ip_valida(ip_entrada)

    if not ip_limpia:
        return _api_error("IP invalida. Usa IPv4 o IPv6.", 400)

    campos = "status,message,country,regionName,city,zip,lat,lon,timezone,isp,query"
    url = f"http://ip-api.com/json/{parse.quote(ip_limpia)}?fields={campos}"

    try:
        with urlrequest.urlopen(url, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return _api_error("No se pudo consultar el servicio de geolocalizacion por IP.", 502)

    if payload.get("status") != "success":
        return _api_error(payload.get("message", "No se encontro informacion para la IP."), 404)

    return jsonify(
        {
            "ok": True,
            "ip": payload.get("query"),
            "pais": payload.get("country"),
            "region": payload.get("regionName"),
            "ciudad": payload.get("city"),
            "codigo_postal": payload.get("zip"),
            "latitud": payload.get("lat"),
            "longitud": payload.get("lon"),
            "zona_horaria": payload.get("timezone"),
            "proveedor_internet": payload.get("isp"),
        }
    )


@app.route("/api/v1/geolocalizacion/direccion", methods=["POST"])
def geolocalizacion_por_direccion():
    data = request.get_json(silent=True) or {}
    direccion = str(data.get("direccion", "")).strip()

    if not direccion:
        return _api_error("Debes enviar 'direccion' en el body JSON.", 400)

    query_string = parse.urlencode({"format": "jsonv2", "limit": 1, "q": direccion})
    url = f"https://nominatim.openstreetmap.org/search?{query_string}"
    req = urlrequest.Request(
        url,
        headers={
            "User-Agent": "IntegradoraApp/1.0 (geolocalizacion)",
            "Accept": "application/json",
        },
    )

    try:
        with urlrequest.urlopen(req, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return _api_error("No se pudo consultar el servicio de geocodificacion.", 502)

    if not payload:
        return _api_error("No se encontraron coordenadas para esa direccion.", 404)

    resultado = payload[0]
    return jsonify(
        {
            "ok": True,
            "direccion_consultada": direccion,
            "direccion_formateada": resultado.get("display_name"),
            "latitud": float(resultado.get("lat")),
            "longitud": float(resultado.get("lon")),
        }
    )


@app.route("/api/v1/clima/actual", methods=["GET"])
def clima_actual():
    lat_texto = (request.args.get("lat") or "").strip()
    lon_texto = (request.args.get("lon") or "").strip()

    if not lat_texto or not lon_texto:
        return _api_error("Debes enviar 'lat' y 'lon' como query params.", 400)

    try:
        latitud = float(lat_texto)
        longitud = float(lon_texto)
    except ValueError:
        return _api_error("Los valores de 'lat' y 'lon' deben ser numericos.", 400)

    if not -90 <= latitud <= 90:
        return _api_error("La latitud debe estar entre -90 y 90.", 400)
    if not -180 <= longitud <= 180:
        return _api_error("La longitud debe estar entre -180 y 180.", 400)

    query_string = parse.urlencode(
        {
            "latitude": latitud,
            "longitude": longitud,
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,weather_code,wind_speed_10m",
            "timezone": "auto",
        }
    )
    url = f"https://api.open-meteo.com/v1/forecast?{query_string}"

    try:
        with urlrequest.urlopen(url, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return _api_error("No se pudo consultar el servicio de clima.", 502)

    clima = payload.get("current")
    unidades = payload.get("current_units", {})
    if not clima:
        return _api_error("No se encontro informacion de clima para esas coordenadas.", 404)

    return jsonify(
        {
            "ok": True,
            "latitud": payload.get("latitude"),
            "longitud": payload.get("longitude"),
            "zona_horaria": payload.get("timezone"),
            "hora_medicion": clima.get("time"),
            "temperatura": clima.get("temperature_2m"),
            "sensacion_termica": clima.get("apparent_temperature"),
            "humedad_relativa": clima.get("relative_humidity_2m"),
            "precipitacion": clima.get("precipitation"),
            "codigo_clima": clima.get("weather_code"),
            "velocidad_viento": clima.get("wind_speed_10m"),
            "unidades": {
                "temperatura": unidades.get("temperature_2m"),
                "sensacion_termica": unidades.get("apparent_temperature"),
                "humedad_relativa": unidades.get("relative_humidity_2m"),
                "precipitacion": unidades.get("precipitation"),
                "velocidad_viento": unidades.get("wind_speed_10m"),
            },
        }
    )

@app.route("/pagos/crear-orden", methods=["POST"])
@login_required
def crear_orden():

    data = request.get_json()

    monto = data.get("monto")

    if not monto:
        return _api_error("Monto requerido")

    token = _paypal_access_token()

    if not token:
        return _api_error("No se pudo obtener token PayPal", 500)

    body = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "amount": {
                    "currency_code": PAYPAL_CURRENCY,
                    "value": str(monto)
                }
            }
        ]
    }

    status, response = _paypal_request(
        "/v2/checkout/orders",
        method="POST",
        body=body,
        token=token
    )

    if status not in (200, 201):
        return jsonify({"ok": False, "error": response}), status

    return jsonify({
        "ok": True,
        "order_id": response["id"]
    })

@app.route("/pagos/capturar/<order_id>", methods=["POST"])
@login_required
def capturar_pago(order_id):

        token = _paypal_access_token()

        if not token:
            return _api_error("No se pudo autenticar con PayPal", 500)

        status, response = _paypal_request(
            f"/v2/checkout/orders/{order_id}/capture",
            method="POST",
            body={},
            token=token
        )

        if status not in (200, 201):
            return jsonify({"ok": False, "error": response}), status

        capture_id = None

        try:
            capture_id = response["purchase_units"][0]["payments"]["captures"][0]["id"]
        except:
            pass

        return jsonify({
            "ok": True,
            "capture_id": capture_id
        })

@app.route("/estadisticas")
@login_required
def estadisticas():

    conexion = get_db()
    cursor = conexion.cursor()

    cursor.execute("SELECT COUNT(*) FROM prestamos")
    total_prestamos = cursor.fetchone()[0]

    cursor.execute("""
    SELECT SUM(monto)
    FROM pagos_multa
    WHERE estado='COMPLETADO'
    """)
    total_pagos = cursor.fetchone()[0] or 0


    # ranking materiales
    cursor.execute("""
    SELECT m.nombre, COUNT(*)
    FROM prestamos p
    JOIN materiales m ON p.material_id = m.id
    GROUP BY m.nombre
    ORDER BY COUNT(*) DESC
    """)

    ranking = [(r[0], r[1]) for r in cursor.fetchall()]


    # procesos
    cursor.execute("""
    SELECT estado, COUNT(*)
    FROM prestamos
    GROUP BY estado
    """)

    procesos = [(p[0], p[1]) for p in cursor.fetchall()]


    cursor.close()
    conexion.close()

    return render_template(
        "dashboard_estadisticas.html",
        prestamos=total_prestamos,
        pagos=total_pagos,
        ranking=ranking,
        procesos=procesos
    )

if __name__ == "__main__":
    app.run(debug=True)