# =============================================================================
# MOTOSCLUB - RED SOCIAL PROFESIONAL PARA MOTEROS
# Versión: 3.0 "The Monolith"
# Arquitectura: Single-File Production Ready
# =============================================================================

import os
import re
import html
import logging
import psycopg2
import requests
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, redirect, render_template_string, session, flash, jsonify, g
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf.csrf import CSRFProtect, generate_csrf

# -----------------------------------------------------------------------------
# CONFIGURACIÓN DE LOGGING Y APP
# -----------------------------------------------------------------------------
# Configuración de logging para producción
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'default-dev-key-change-in-prod')
app.config['WTF_CSRF_TIME_LIMIT'] = None
app.config['SESSION_COOKIE_SECURE'] = False # True si tienes HTTPS configurado en custom domain
app.config['SESSION_COOKIE_HTTPONLY'] = True

# Inicialización CSRF
csrf = CSRFProtect(app)

# Configuración de Base de Datos
DATABASE_URL = os.environ.get('DATABASE_URL')

# Configuración externa (ImgBB)
IMGBB_API_KEY = "27a447d71db292f6c1296f509a06b09e"

# -----------------------------------------------------------------------------
# CONEXIÓN A BASE DE DATOS (POSTGRESQL)
# -----------------------------------------------------------------------------
def get_db_connection():
    """Establece una nueva conexión a la base de datos."""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        logger.error(f"Error conectando a la base de datos: {e}")
        raise

def init_db():
    """Inicializa el esquema de la base de datos con tablas y relaciones completas."""
    logger.info("Inicializando base de datos...")
    conn = get_db_connection()
    cur = conn.cursor()

    # Tabla de Usuarios
    cur.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id SERIAL PRIMARY KEY,
            nombre TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            email TEXT DEFAULT '',
            bio TEXT DEFAULT '',
            moto TEXT DEFAULT '',
            avatar_url TEXT DEFAULT '',
            banner_url TEXT DEFAULT '',
            avatar_color TEXT DEFAULT '',
            racha INTEGER DEFAULT 0,
            ultima_actividad DATE,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Tabla de Publicaciones (Posts)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id SERIAL PRIMARY KEY,
            usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
            contenido TEXT NOT NULL,
            imagen_url TEXT DEFAULT '',
            categoria TEXT DEFAULT 'General',
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reportes INTEGER DEFAULT 0,
            editado BOOLEAN DEFAULT FALSE
        );
    """)

    # Tabla de Relaciones (Seguidores)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS seguidores (
            seguidor_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
            seguido_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (seguidor_id, seguido_id),
            CHECK (seguidor_id != seguido_id)
        );
    """)

    # Tabla de Interacciones (Likes/Gas)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS likes (
            usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
            post_id INTEGER REFERENCES posts(id) ON DELETE CASCADE,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (usuario_id, post_id)
        );
    """)

    # Tabla de Comentarios
    cur.execute("""
        CREATE TABLE IF NOT EXISTS comentarios (
            id SERIAL PRIMARY KEY,
            post_id INTEGER REFERENCES posts(id) ON DELETE CASCADE,
            usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
            contenido TEXT NOT NULL,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Tabla de Notificaciones
    cur.execute("""
        CREATE TABLE IF NOT EXISTS notificaciones (
            id SERIAL PRIMARY KEY,
            usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
            actor_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
            tipo TEXT NOT NULL,
            mensaje TEXT NOT NULL,
            url TEXT,
            leido BOOLEAN DEFAULT FALSE,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Tabla de Bookmarks (Guardados)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bookmarks (
            usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
            post_id INTEGER REFERENCES posts(id) ON DELETE CASCADE,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (usuario_id, post_id)
        );
    """)

    # Tabla de Mensajes Privados (Chat Básico)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS mensajes (
            id SERIAL PRIMARY KEY,
            emisor_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
            receptor_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
            contenido TEXT NOT NULL,
            leido BOOLEAN DEFAULT FALSE,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    conn.commit()
    cur.close()
    conn.close()
    logger.info("Base de datos inicializada correctamente.")

# -----------------------------------------------------------------------------
# DECORADORES Y FUNCIONES AUXILIARES
# -----------------------------------------------------------------------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Debes iniciar sesión para acceder a esta sección.", "error")
            return redirect('/')
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('rol') != 'admin':
            flash("Acceso denegado.", "error")
            return redirect('/foro')
        return f(*args, **kwargs)
    return decorated_function

def procesar_texto(text):
    """Limpia HTML y convierte menciones/hashtags/urls en enlaces seguros."""
    text = html.escape(text)
    
    # Imágenes seguras
    pattern_img = r'(https?://[^\s]+?\.(png|jpg|jpeg|gif|webp)(\?[^\s]*)?)'
    text = re.sub(pattern_img, r'<img src="\1" class="post-image" loading="lazy" alt="Imagen">', text)
    
    # Menciones
    text = re.sub(r'@(\w+)', r'<a href="/perfil/\1" class="mention">@\1</a>', text)
    
    # Hashtags
    text = re.sub(r'#(\w+)', r'<a href="/buscar?tag=\1" class="hashtag">#\1</a>', text)
    
    return text

def string_to_color(s):
    """Genera un color HSL único basado en el string."""
    h = sum(ord(c) for c in s) % 360
    return f"hsl({h}, 70%, 50%)"

def time_ago(dt):
    """Formato relativo de tiempo."""
    if not dt: return "Desconocido"
    delta = datetime.now() - dt if isinstance(dt, datetime) else timedelta(0)
    if delta.days > 365: return f"hace {delta.days // 365} años"
    if delta.days > 30: return f"hace {delta.days // 30} meses"
    if delta.days > 0: return f"hace {delta.days} días"
    if delta.seconds >= 3600: return f"hace {delta.seconds // 3600} horas"
    if delta.seconds >= 60: return f"hace {delta.seconds // 60} minutos"
    return "ahora mismo"

def crear_notificacion(user_id, actor_id, tipo, mensaje, url=None):
    """Crea una notificación si el usuario no se notifica a sí mismo."""
    if user_id == actor_id:
        return
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO notificaciones (usuario_id, actor_id, tipo, mensaje, url) VALUES (%s, %s, %s, %s, %s)",
            (user_id, actor_id, tipo, mensaje, url)
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logger.error(f"Error creando notificación: {e}")

def get_notif_count(user_id):
    """Obtiene contador de notificaciones no leídas."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM notificaciones WHERE usuario_id=%s AND leido=FALSE", (user_id,))
        count = cur.fetchone()[0]
        cur.close()
        conn.close()
        return count
    except:
        return 0

def upload_to_imgbb(image_file):
    """Sube imagen a ImgBB y devuelve la URL."""
    if not image_file:
        return None
    try:
        url = "https://api.imgbb.com/1/upload"
        payload = {"key": IMGBB_API_KEY, "image": image_file.read()}
        response = requests.post(url, files=payload)
        if response.status_code == 200:
            return response.json()['data']['url']
    except Exception as e:
        logger.error(f"Error subiendo a ImgBB: {e}")
    return None

# -----------------------------------------------------------------------------
# ESTILOS CSS - DISEÑO PROFESIONAL Y RESPONSIVE
# -----------------------------------------------------------------------------
STYLE = """
/* Variables del Sistema de Diseño */
:root {
    --font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    --bg: #050505;
    --bg-elev: #111111;
    --surface: #1C1C1E;
    --surface-hover: #2C2C2E;
    --text: #F5F5F7;
    --text-dim: #8E8E93;
    --border: #3A3A3C;
    --accent: #FF3B30;
    --accent-hover: #FF6961;
    --blue: #0A84FF;
    --green: #30D158;
    --orange: #FF9F0A;
    --shadow: 0 8px 30px rgba(0,0,0,0.4);
    --radius: 16px;
    --radius-sm: 12px;
    --transition: 200ms ease;
}

/* Tema Claro */
[data-theme="light"] {
    --bg: #F2F2F7;
    --bg-elev: #FFFFFF;
    --surface: #FFFFFF;
    --surface-hover: #E5E5EA;
    --text: #1D1D1F;
    --text-dim: #636366;
    --border: #D1D1D6;
    --shadow: 0 8px 30px rgba(0,0,0,0.08);
}

/* Reset y Base */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html { scroll-behavior: smooth; }
body {
    font-family: var(--font);
    background: var(--bg);
    color: var(--text);
    line-height: 1.5;
    font-size: 15px;
    -webkit-font-smoothing: antialiased;
    transition: background var(--transition), color var(--transition);
    padding-bottom: 80px; /* Espacio para navbar móvil */
}

/* Tipografía */
h1, h2, h3 { font-weight: 700; line-height: 1.2; letter-spacing: -0.02em; }
h1 { font-size: 28px; }
h2 { font-size: 22px; }
h3 { font-size: 18px; }
a { color: var(--blue); text-decoration: none; transition: opacity 0.2s; }
a:hover { opacity: 0.8; }

/* Layout */
.container { max-width: 720px; margin: 0 auto; padding: 0 16px; }

/* Navbar */
.navbar {
    position: sticky; top: 0; z-index: 1000;
    background: rgba(17, 17, 17, 0.8);
    backdrop-filter: saturate(180%) blur(20px);
    border-bottom: 1px solid var(--border);
    padding: 12px 0;
}
[data-theme="light"] .navbar { background: rgba(255, 255, 255, 0.8); }
.nav-inner {
    display: flex; align-items: center; justify-content: space-between;
    max-width: 720px; margin: 0 auto; padding: 0 16px;
}
.nav-brand { font-weight: 800; font-size: 20px; color: var(--text); display: flex; align-items: center; gap: 6px; }
.nav-actions { display: flex; gap: 8px; }
.nav-btn {
    background: transparent; border: 1px solid var(--border); color: var(--text);
    padding: 8px 14px; border-radius: 20px; font-size: 13px; font-weight: 600;
    cursor: pointer; text-decoration: none; transition: all 0.2s;
}
.nav-btn.active { background: var(--accent); border-color: var(--accent); color: white; }
.icon-btn { border: none; padding: 8px; border-radius: 50%; min-width: 36px; text-align: center; font-size: 18px; }
.badge { position: absolute; top: 0; right: 0; background: var(--accent); color: white; font-size: 10px; padding: 2px 5px; border-radius: 10px; font-weight: bold; }

/* Cards */
.card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 20px; margin-bottom: 16px;
    box-shadow: var(--shadow); transition: transform 0.1s;
}
.card:active { transform: scale(0.99); }

/* Forms */
input, textarea, select {
    width: 100%; background: var(--bg); border: 1px solid var(--border);
    color: var(--text); padding: 12px; border-radius: var(--radius-sm);
    font-family: inherit; font-size: 15px; outline: none;
    transition: border-color 0.2s;
}
input:focus { border-color: var(--accent); }
textarea { resize: vertical; min-height: 80px; }

/* Buttons */
.btn {
    background: var(--accent); color: white; border: none;
    padding: 12px 20px; border-radius: var(--radius-sm); font-weight: 600;
    font-size: 14px; cursor: pointer; width: 100%; transition: background 0.2s;
}
.btn:hover { background: var(--accent-hover); }
.btn-secondary { background: var(--surface-hover); color: var(--text); border: 1px solid var(--border); }
.btn-ghost { background: transparent; color: var(--text-dim); border: none; }

/* Avatar */
.avatar {
    width: 40px; height: 40px; border-radius: 50%;
    background: var(--surface-hover); display: flex;
    align-items: center; justify-content: center;
    font-weight: 600; color: white; font-size: 16px;
    flex-shrink: 0; overflow: hidden;
}
.avatar img { width: 100%; height: 100%; object-fit: cover; }
.avatar-lg { width: 80px; height: 80px; font-size: 32px; }

/* Post */
.post-header { display: flex; gap: 10px; margin-bottom: 12px; }
.post-author { display: flex; flex-direction: column; gap: 2px; }
.post-author-name { font-weight: 600; color: var(--text); font-size: 15px; }
.post-meta { font-size: 13px; color: var(--text-dim); }
.post-category { font-size: 11px; padding: 2px 8px; border-radius: 6px; background: var(--surface-hover); }
.post-content { white-space: pre-wrap; word-break: break-word; margin-bottom: 12px; line-height: 1.6; }
.post-image { width: 100%; border-radius: 12px; margin-bottom: 12px; }
.post-actions { display: flex; gap: 8px; border-top: 1px solid var(--border); padding-top: 12px; margin-top: 8px; }
.action-btn {
    background: transparent; border: none; color: var(--text-dim);
    padding: 6px 12px; border-radius: 8px; cursor: pointer;
    display: flex; align-items: center; gap: 4px; font-size: 14px; font-weight: 500;
}
.action-btn:hover { background: var(--surface-hover); color: var(--text); }
.action-btn.active { color: var(--accent); }

/* Comments */
.comments { display: none; margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--border); }
.comments.show { display: block; }
.comment { background: var(--bg); padding: 10px; border-radius: 12px; margin-bottom: 8px; font-size: 14px; }
.comment-author { font-weight: 600; margin-right: 6px; }

/* Profile */
.profile-banner { height: 150px; background: linear-gradient(45deg, var(--accent), var(--blue)); border-radius: 16px 16px 0 0; margin: -20px -20px 0 -20px; position: relative; overflow: hidden; }
.profile-banner img { width: 100%; height: 100%; object-fit: cover; opacity: 0.8; }
.profile-stats { display: flex; justify-content: space-around; padding: 16px 0; border-top: 1px solid var(--border); margin-top: 16px; }
.stat { text-align: center; }
.stat-val { font-size: 18px; font-weight: 700; }
.stat-label { font-size: 12px; color: var(--text-dim); }

/* Auth */
.auth-container { min-height: 80vh; display: flex; align-items: center; justify-content: center; }
.auth-card { width: 100%; max-width: 400px; text-align: center; }
.auth-logo { font-size: 40px; font-weight: 800; margin-bottom: 8px; }

/* Utils */
.flash { padding: 12px; border-radius: 12px; margin-bottom: 16px; font-weight: 500; animation: slideIn 0.3s; }
.flash-error { background: rgba(255,59,48,0.1); color: #ff6b61; border: 1px solid rgba(255,59,48,0.3); }
.flash-success { background: rgba(48,209,88,0.1); color: #4fd676; border: 1px solid rgba(48,209,88,0.3); }
@keyframes slideIn { from { transform: translateY(-10px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
.hidden { display: none; }
.text-center { text-align: center; }
.text-dim { color: var(--text-dim); }
.mt-1 { margin-top: 8px; } .mt-2 { margin-top: 16px; } .mb-2 { margin-bottom: 16px; }
.flex { display: flex; } .items-center { align-items: center; } .gap-1 { gap: 8px; }

/* Responsive */
@media (max-width: 480px) {
    .nav-btn span { display: none; }
    .profile-stats { gap: 12px; }
    .btn { padding: 12px 16px; }
}
"""

# -----------------------------------------------------------------------------
# PLANTILLAS HTML BASE
# -----------------------------------------------------------------------------
BASE_LAYOUT = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
    <meta name="theme-color" content="#050505" media="(prefers-color-scheme: dark)">
    <meta name="theme-color" content="#F2F2F7" media="(prefers-color-scheme: light)">
    <title>MOTOSCLUB | Red Social de Moteros</title>
    <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🏍️</text></svg>">
    <style>{{ style }}</style>
</head>
<body>
    <nav class="navbar">
        <div class="nav-inner">
            <a href="/foro" class="nav-brand">🏍️ MOTOSCLUB</a>
            <div class="nav-actions">
                <button class="nav-btn icon-btn" id="themeToggle" aria-label="Tema">🌙</button>
                <a href="/buscar" class="nav-btn icon-btn" aria-label="Buscar">🔍</a>
                <a href="/notificaciones" class="nav-btn icon-btn" style="position:relative" aria-label="Notificaciones">
                    🔔 {% if notif_count > 0 %}<span class="badge">{{ notif_count }}</span>{% endif %}
                </a>
                <a href="/perfil" class="nav-btn {% if active == 'perfil' %}active{% endif %}"><span>Yo</span></a>
                <a href="/logout" class="nav-btn"><span>Salir</span></a>
            </div>
        </div>
    </nav>

    <main class="container" style="padding-top: 24px;">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="flash flash-{{ category }}">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        
        {{ content|safe }}
    </main>

    <footer style="text-align: center; padding: 40px 0; color: var(--text-dim); font-size: 12px;">
        <p>© {{ year }} MOTOSCLUB. Hecho con ❤️ para moteros.</p>
        <p><a href="#">Privacidad</a> • <a href="#">Términos</a></p>
    </footer>

    <script>
        // Sistema de Tema Oscuro/Claro
        (function() {
            const root = document.documentElement;
            const toggle = document.getElementById('themeToggle');
            
            function applyTheme(theme) {
                root.setAttribute('data-theme', theme);
                localStorage.setItem('theme', theme);
                toggle.textContent = theme === 'light' ? '☀️' : '🌙';
            }
            
            const saved = localStorage.getItem('theme');
            const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
            applyTheme(saved || (prefersDark ? 'dark' : 'light'));
            
            toggle.addEventListener('click', () => {
                const next = root.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
                applyTheme(next);
            });
        })();

        // Toggle comentarios
        function toggleComments(id) {
            const el = document.getElementById('comments-' + id);
            if(el) el.classList.toggle('show');
        }
    </script>
</body>
</html>
"""

def render_page(content, active='', notif_count=0):
    """Renderiza la página con el layout base inyectando el contenido dinámico."""
    return render_template_string(
        BASE_LAYOUT, 
        style=STYLE, 
        content=content, 
        active=active, 
        notif_count=notif_count, 
        year=datetime.now().year
    )

# -----------------------------------------------------------------------------
# RUTAS DE AUTENTICACIÓN
# -----------------------------------------------------------------------------
@app.route('/', methods=['GET', 'POST'])
def login_register():
    if 'user_id' in session:
        return redirect('/foro')
    
    # Generar token CSRF para formularios
    token = generate_csrf()
    is_login = request.args.get('register') != '1'
    
    # Renderizamos HTML directamente con el token inyectado
    auth_html = f"""
    <div class="auth-container">
        <div class="card auth-card">
            <div class="auth-logo">🏍️ MOTOSCLUB</div>
            <p class="text-dim mb-2">{"Conecta con la comunidad" if is_login else "Únete a la manada"}</p>
            
            <form method="POST" action="/?action={'login' if is_login else 'register'}">
                <input type="hidden" name="csrf_token" value="{token}"/>
                
                <input type="text" name="nombre" placeholder="Nombre de usuario" required minlength="3" maxlength="20" pattern="[a-zA-Z0-9_]+" autocomplete="username">
                <input type="password" name="password" placeholder="Contraseña" required minlength="6" autocomplete="current-password">
                
                {"<label style='font-size:13px; color:var(--text-dim); margin-bottom:12px; display:block'><input type='checkbox' required> Acepto los términos</label>" if not is_login else ""}
                
                <button type="submit" class="btn">{"ENTRAR" if is_login else "CREAR CUENTA"}</button>
            </form>
            
            <div class="mt-2 text-dim" style="font-size: 14px;">
                {"¿No tienes cuenta?" if is_login else "¿Ya tienes cuenta?"}
                <a href="/?{'register=1' if is_login else ''}">{"Regístrate" if is_login else "Entra aquí"}</a>
            </div>
        </div>
    </div>
    """
    
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        password = request.form.get('password', '')
        
        # Validaciones
        if len(nombre) < 3: flash("Nombre muy corto", "error")
        elif len(password) < 6: flash("Contraseña muy corta (mín 6)", "error")
        elif not re.match(r'^[a-zA-Z0-9_]+$', nombre): flash("Nombre inválido (solo letras, nums, _)", "error")
        else:
            conn = get_db_connection()
            cur = conn.cursor()
            
            if 'register' in request.args:
                try:
                    hashed = generate_password_hash(password)
                    color = string_to_color(nombre)
                    cur.execute(
                        "INSERT INTO usuarios (nombre, password, avatar_color) VALUES (%s, %s, %s)",
                        (nombre, hashed, color)
                    )
                    conn.commit()
                    flash("¡Cuenta creada! Ya puedes entrar.", "success")
                except psycopg2.IntegrityError:
                    flash("Ese usuario ya existe.", "error")
                    conn.rollback()
                finally:
                    cur.close(); conn.close()
            else:
                cur.execute("SELECT id, password, avatar_color, bio, moto FROM usuarios WHERE nombre=%s", (nombre,))
                user = cur.fetchone()
                cur.close(); conn.close()
                
                if user and check_password_hash(user[1], password):
                    session['user_id'] = user[0]
                    session['user_name'] = nombre
                    session['avatar_color'] = user[2]
                    session['bio'] = user[3] or ''
                    session['moto'] = user[4] or ''
                    return redirect('/foro')
                else:
                    flash("Usuario o contraseña incorrectos.", "error")

    return render_page(auth_html, notif_count=0)

# -----------------------------------------------------------------------------
# RUTAS DEL FORO / FEED
# -----------------------------------------------------------------------------
@app.route('/foro')
@login_required
def foro():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Obtener lista de seguidos + yo
    cur.execute("SELECT seguido_id FROM seguidores WHERE seguidor_id = %s", (session['user_id'],))
    following_ids = [r[0] for r in cur.fetchall()] + [session['user_id']]
    
    # Query principal de posts
    cur.execute("""
        SELECT p.id, u.nombre, u.avatar_color, p.contenido, p.imagen_url, p.categoria, p.fecha, p.usuario_id,
               (SELECT COUNT(*) FROM likes WHERE post_id = p.id),
               (SELECT COUNT(*) FROM comentarios WHERE post_id = p.id),
               EXISTS(SELECT 1 FROM likes WHERE post_id = p.id AND usuario_id = %s),
               EXISTS(SELECT 1 FROM bookmarks WHERE post_id = p.id AND usuario_id = %s)
        FROM posts p JOIN usuarios u ON p.usuario_id = u.id
        WHERE p.usuario_id = ANY(%s) AND p.reportes < 5
        ORDER BY p.fecha DESC LIMIT 25
    """, (session['user_id'], session['user_id'], following_ids))
    
    posts_data = cur.fetchall()
    
    posts_html = ""
    token = generate_csrf() # Token para formularios de acción
    
    for p in posts_data:
        pid, autor, color, contenido, img, cat, fecha, uid, likes, comments, liked, bookmarked = p
        
        # Procesar contenido
        safe_content = procesar_texto(contenido)
        time_str = time_ago(fecha)
        
        # Botón de borrar si es propio
        delete_btn = f"""
        <form action="/delete/{pid}" method="POST" style="display:inline">
            <input type="hidden" name="csrf_token" value="{token}"/>
            <button class="action-btn" onclick="return confirm('¿Borrar?')">🗑️</button>
        </form>
        """ if uid == session['user_id'] else ""
        
        posts_html += f"""
        <article class="card post">
            <div class="post-header">
                <div class="avatar" style="background:{color}">{autor[0].upper()}</div>
                <div class="post-author">
                    <a href="/perfil/{autor}" class="post-author-name">{autor}</a>
                    <div class="post-meta">
                        <span>{time_str}</span>
                        <span>•</span>
                        <span class="post-category">{cat}</span>
                    </div>
                </div>
                {delete_btn}
            </div>
            
            <div class="post-content">{safe_content}</div>
            {f'<img src="{img}" class="post-image">' if img else ''}
            
            <div class="post-actions">
                <form action="/like/{pid}" method="POST" style="display:inline">
                    <input type="hidden" name="csrf_token" value="{token}"/>
                    <button class="action-btn {'active' if liked else ''}">⛽ <span class="count">{likes}</span></button>
                </form>
                
                <button class="action-btn" onclick="toggleComments({pid})">💬 <span class="count">{comments}</span></button>
                
                <form action="/bookmark/{pid}" method="POST" style="display:inline">
                    <input type="hidden" name="csrf_token" value="{token}"/>
                    <button class="action-btn {'active' if bookmarked else ''}">🔖</button>
                </form>
            </div>
            
            <div class="comments" id="comments-{pid}">
                <form action="/comment/{pid}" method="POST" class="flex gap-1 mb-2">
                    <input type="hidden" name="csrf_token" value="{token}"/>
                    <input type="text" name="contenido" placeholder="Comentar..." required style="flex:1">
                    <button class="btn btn-secondary" style="width:auto">Enviar</button>
                </form>
            </div>
        </article>
        """
    
    # Formulario de publicación
    form_html = f"""
    <div class="card">
        <form method="POST" action="/post">
            <input type="hidden" name="csrf_token" value="{token}"/>
            <textarea name="contenido" placeholder="¿Qué ruta haces hoy?" required></textarea>
            <div class="flex gap-1 items-center mb-2" style="flex-wrap:wrap">
                <select name="categoria" style="width:auto; margin:0">
                    <option>General</option>
                    <option>Ruta</option>
                    <option>Mecanica</option>
                    <option>Venta</option>
                </select>
                <input type="url" name="imagen_url" placeholder="URL Imagen (opcional)" style="flex:1; min-width:150px; margin:0">
            </div>
            <button type="submit" class="btn">PUBLICAR</button>
        </form>
    </div>
    """
    
    content = form_html + (posts_html if posts_data else "<div class='card text-center text-dim'>No hay posts todavía. ¡Sé el primero!</div>")
    
    cur.close()
    conn.close()
    
    return render_page(content, active='foro', notif_count=get_notif_count(session['user_id']))

# -----------------------------------------------------------------------------
# RUTAS DE ACCIONES
# -----------------------------------------------------------------------------
@app.route('/post', methods=['POST'])
@login_required
def crear_post():
    contenido = request.form.get('contenido', '').strip()
    categoria = request.form.get('categoria', 'General')
    img_url = request.form.get('imagen_url', '').strip()
    
    if not contenido and not img_url:
        flash("Publicación vacía", "error")
        return redirect('/foro')
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO posts (usuario_id, contenido, categoria, imagen_url) VALUES (%s, %s, %s, %s)",
        (session['user_id'], contenido, categoria, img_url[:500])
    )
    
    # Lógica de racha
    hoy = datetime.now().date()
    cur.execute("SELECT ultima_actividad FROM usuarios WHERE id=%s", (session['user_id'],))
    last = cur.fetchone()[0]
    if last == hoy - timedelta(days=1):
        cur.execute("UPDATE usuarios SET racha=racha+1, ultima_actividad=%s WHERE id=%s", (hoy, session['user_id']))
    elif last != hoy:
        cur.execute("UPDATE usuarios SET racha=1, ultima_actividad=%s WHERE id=%s", (hoy, session['user_id']))
    
    conn.commit()
    cur.close()
    conn.close()
    flash("¡Publicado!", "success")
    return redirect('/foro')

@app.route('/like/<int:pid>', methods=['POST'])
@login_required
def like(pid):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO likes (usuario_id, post_id) VALUES (%s, %s)", (session['user_id'], pid))
        conn.commit()
    except:
        conn.rollback()
        cur.execute("DELETE FROM likes WHERE usuario_id=%s AND post_id=%s", (session['user_id'], pid))
        conn.commit()
    finally:
        cur.close()
        conn.close()
    return redirect(request.referrer or '/foro')

@app.route('/delete/<int:pid>', methods=['POST'])
@login_required
def delete(pid):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM posts WHERE id=%s AND usuario_id=%s", (pid, session['user_id']))
    conn.commit()
    cur.close()
    conn.close()
    flash("Eliminado", "success")
    return redirect('/foro')

@app.route('/comment/<int:pid>', methods=['POST'])
@login_required
def comment(pid):
    txt = request.form.get('contenido', '').strip()
    if txt:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO comentarios (post_id, usuario_id, contenido) VALUES (%s, %s, %s)", (pid, session['user_id'], txt))
        conn.commit()
        cur.close()
        conn.close()
    return redirect(request.referrer or '/foro')

# -----------------------------------------------------------------------------
# RUTAS DE PERFIL Y CONFIGURACIÓN
# -----------------------------------------------------------------------------
@app.route('/perfil')
@app.route('/perfil/<username>')
@login_required
def perfil(username=None):
    target = username or session['user_name']
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT id, nombre, bio, moto, avatar_color, racha FROM usuarios WHERE nombre=%s", (target,))
    user = cur.fetchone()
    if not user:
        flash("Usuario no encontrado", "error")
        return redirect('/foro')
    
    uid, nombre, bio, moto, color, racha = user
    
    cur.execute("SELECT COUNT(*) FROM posts WHERE usuario_id=%s", (uid,))
    posts_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM seguidores WHERE seguido_id=%s", (uid,))
    followers = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM seguidores WHERE seguidor_id=%s", (uid,))
    following = cur.fetchone()[0]
    
    cur.execute("SELECT id, contenido, imagen_url, fecha FROM posts WHERE usuario_id=%s ORDER BY fecha DESC LIMIT 10", (uid,))
    posts = cur.fetchall()
    
    cur.close()
    conn.close()
    
    # HTML del perfil
    content = f"""
    <div class="card" style="padding:0; overflow:hidden;">
        <div class="profile-banner"></div>
        <div style="padding:20px;">
            <div class="flex items-center gap-2" style="margin-bottom:16px;">
                <div class="avatar avatar-lg" style="background:{color}">{nombre[0].upper()}</div>
                <div style="flex:1">
                    <h1>{nombre}</h1>
                    <p class="text-dim">{moto or 'Motero'}</p>
                </div>
                {"<a href='/config' class='btn btn-secondary' style='width:auto'>Editar</a>" if uid == session['user_id'] else f"<form action='/seguir/{uid}' method='POST'><input type='hidden' name='csrf_token' value='{generate_csrf()}'/><button class='btn btn-secondary' style='width:auto'>Seguir</button></form>"}
            </div>
            <p style="margin-bottom:16px">{bio or 'Sin biografía'}</p>
            <div class="profile-stats">
                <div class="stat"><span class="stat-val">{posts_count}</span><span class="stat-label">Posts</span></div>
                <div class="stat"><span class="stat-val">{followers}</span><span class="stat-label">Seguidores</span></div>
                <div class="stat"><span class="stat-val">{following}</span><span class="stat-label">Siguiendo</span></div>
                <div class="stat"><span class="stat-val">🔥{racha}</span><span class="stat-label">Racha</span></div>
            </div>
        </div>
    </div>
    <h3 class="mb-2">Publicaciones recientes</h3>
    {"".join([f"<div class='card'><div class='text-dim' style='font-size:13px'>{time_ago(f)}</div><div class='mt-1'>{procesar_texto(c)}</div>{f'<img src=\"{img}\" class=\"post-image\">' if img else ''}</div>" for i,c,img,f in posts])}
    """
    
    return render_page(content, active='perfil', notif_count=get_notif_count(session['user_id']))

@app.route('/config', methods=['GET', 'POST'])
@login_required
def config():
    if request.method == 'POST':
        bio = request.form.get('bio', '')[:200]
        moto = request.form.get('moto', '')[:50]
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE usuarios SET bio=%s, moto=%s WHERE id=%s", (bio, moto, session['user_id']))
        conn.commit()
        cur.close()
        conn.close()
        
        session['bio'] = bio
        session['moto'] = moto
        flash("Perfil actualizado", "success")
        return redirect('/perfil')
    
    token = generate_csrf()
    content = f"""
    <div class="card">
        <h2>Configuración</h2>
        <form method="POST">
            <input type="hidden" name="csrf_token" value="{token}"/>
            <label>Tu moto</label>
            <input type="text" name="moto" value="{session.get('moto', '')}" placeholder="Ej: Yamaha MT-07">
            <label>Biografía</label>
            <textarea name="bio" placeholder="Cuéntanos...">{session.get('bio', '')}</textarea>
            <button class="btn">Guardar</button>
        </form>
    </div>
    """
    return render_page(content, active='perfil', notif_count=get_notif_count(session['user_id']))

# -----------------------------------------------------------------------------
# OTRAS RUTAS
# -----------------------------------------------------------------------------
@app.route('/seguir/<int:uid>', methods=['POST'])
@login_required
def seguir(uid):
    if uid == session['user_id']: return redirect('/perfil')
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO seguidores (seguidor_id, seguido_id) VALUES (%s, %s)", (session['user_id'], uid))
        conn.commit()
    except:
        conn.rollback()
        cur.execute("DELETE FROM seguidores WHERE seguidor_id=%s AND seguido_id=%s", (session['user_id'], uid))
        conn.commit()
    finally:
        cur.close()
        conn.close()
    return redirect(request.referrer or '/foro')

@app.route('/notificaciones')
@login_required
def notificaciones():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE notificaciones SET leido=TRUE WHERE usuario_id=%s", (session['user_id'],))
    conn.commit()
    cur.execute("SELECT tipo, mensaje, url, fecha FROM notificaciones WHERE usuario_id=%s ORDER BY fecha DESC LIMIT 30", (session['user_id'],))
    
    items = ""
    for t, m, u, f in cur.fetchall():
        icon = {'like': '⛽', 'comment': '💬', 'follow': '👤'}.get(t, '🔔')
        items += f"<a href='{u or '#'}' class='card' style='padding:12px; margin-bottom:8px'><span>{icon} {m}</span><span class='text-dim' style='font-size:12px; margin-top:4px; display:block'>{time_ago(f)}</span></a>"
    
    cur.close()
    conn.close()
    
    return render_page(f"<h2 class='mb-2'>Notificaciones</h2>{items if items else '<p class=\"text-center text-dim\">Sin notificaciones</p>'}", active='notif', notif_count=0)

@app.route('/buscar')
@login_required
def buscar():
    q = request.args.get('q', '')
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT p.id, u.nombre, p.contenido FROM posts p JOIN usuarios u ON p.usuario_id=u.id WHERE p.contenido ILIKE %s LIMIT 10", (f'%{q}%',))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    res = "".join([f"<div class='card'><b>{n}</b><p>{c[:100]}...</p></div>" for i,n,c in rows])
    return render_page(f"<h2>Resultados para '{q}'</h2>{res}", active='buscar')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

# -----------------------------------------------------------------------------
# ENTRY POINT
# -----------------------------------------------------------------------------
if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
