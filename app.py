# =============================================================================
# MOTOSCLUB - Red Social para Moteros
# =============================================================================
import os
import re
import html
import requests
import psycopg2
from flask import Flask, request, redirect, render_template_string, session, flash, jsonify, get_flashed_messages
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from functools import wraps

# -----------------------------------------------------------------------------
# CONFIGURACIÓN GLOBAL
# -----------------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.urandom(24)

DATABASE_URL = os.environ.get('DATABASE_URL')
IMGBB_API_KEY = "27a447d71db292f6c1296f509a06b09e"

# -----------------------------------------------------------------------------
# CONEXIÓN Y BASE DE DATOS
# -----------------------------------------------------------------------------
def get_db_connection():
    """Establece conexión con PostgreSQL."""
    return psycopg2.connect(DATABASE_URL)


def init_db():
    """Inicializa tablas y aplica migraciones."""
    conn = get_db_connection()
    cur = conn.cursor()

    # Tabla: Usuarios
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
            rol TEXT DEFAULT 'user',
            racha INTEGER DEFAULT 0,
            ultima_actividad DATE,
            redes TEXT DEFAULT '{}'
        );
    """)

    # Tabla: Posts
    cur.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id SERIAL PRIMARY KEY,
            usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
            contenido TEXT NOT NULL,
            imagen_url TEXT DEFAULT '',
            categoria TEXT DEFAULT 'General',
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reportes INTEGER DEFAULT 0
        );
    """)

    # Tabla: Seguidores
    cur.execute("""
        CREATE TABLE IF NOT EXISTS seguidores (
            seguidor_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
            seguido_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (seguidor_id, seguido_id)
        );
    """)

    # Tabla: Likes
    cur.execute("""
        CREATE TABLE IF NOT EXISTS likes (
            usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
            post_id INTEGER REFERENCES posts(id) ON DELETE CASCADE,
            PRIMARY KEY (usuario_id, post_id)
        );
    """)

    # Tabla: Comentarios
    cur.execute("""
        CREATE TABLE IF NOT EXISTS comentarios (
            id SERIAL PRIMARY KEY,
            post_id INTEGER REFERENCES posts(id) ON DELETE CASCADE,
            usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
            contenido TEXT,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Tabla: Notificaciones
    cur.execute("""
        CREATE TABLE IF NOT EXISTS notificaciones (
            id SERIAL PRIMARY KEY,
            usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
            tipo TEXT,
            mensaje TEXT,
            url TEXT,
            leido BOOLEAN DEFAULT FALSE,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Tabla: Bookmarks
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bookmarks (
            usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
            post_id INTEGER REFERENCES posts(id) ON DELETE CASCADE,
            PRIMARY KEY (usuario_id, post_id)
        );
    """)

    # Migraciones: Añadir columnas si no existen
    migraciones = [
        "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS avatar_url TEXT;",
        "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS banner_url TEXT;",
        "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS racha INTEGER DEFAULT 0;",
        "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS ultima_actividad DATE;",
        "ALTER TABLE posts ADD COLUMN IF NOT EXISTS imagen_url TEXT;",
        "ALTER TABLE posts ADD COLUMN IF NOT EXISTS reportes INTEGER DEFAULT 0;",
    ]
    for sql in migraciones:
        try:
            cur.execute(sql)
        except:
            pass

    conn.commit()
    cur.close()
    conn.close()


# -----------------------------------------------------------------------------
# DECORADORES Y HELPERS
# -----------------------------------------------------------------------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Inicia sesión para continuar.", "error")
            return redirect('/')
        return f(*args, **kwargs)
    return decorated_function


def upload_to_imgbb(image_file):
    """Sube imagen a ImgBB y devuelve URL."""
    if not image_file:
        return None
    try:
        url = "https://api.imgbb.com/1/upload"
        payload = {"key": IMGBB_API_KEY}
        files = {"image": image_file.read()}
        response = requests.post(url, files=files, data=payload)
        if response.status_code == 200:
            return response.json()['data']['url']
    except Exception as e:
        print(f"Error subiendo imagen: {e}")
    return None


def procesar_texto(text):
    """Convierte @menciones, #hashtags y URLs en HTML seguro."""
    text = html.escape(text)

    # Imágenes automáticas
    pattern_img = r'(https?://[^\s]+?\.(png|jpg|jpeg|gif|webp))'
    text = re.sub(pattern_img, r'<img src="\1" class="post-image" loading="lazy">', text)

    # Menciones @usuario
    pattern_mention = r'@(\w+)'
    text = re.sub(pattern_mention, r'<a href="/perfil/\1">@\1</a>', text)

    # Hashtags #tema
    pattern_hash = r'#(\w+)'
    text = re.sub(pattern_hash, r'<a href="/buscar?tag=\1">#\1</a>', text)

    return text


def string_to_color(s):
    """Genera color HSL único desde string."""
    h = sum(ord(c) for c in s) % 360
    return f"hsl({h}, 60%, 45%)"


def time_ago(dt):
    """Convierte timestamp a formato relativo."""
    delta = datetime.now() - dt
    if delta.days > 365:
        return f"hace {delta.days // 365} años"
    if delta.days > 0:
        return f"hace {delta.days}d"
    if delta.seconds >= 3600:
        return f"hace {delta.seconds // 3600}h"
    if delta.seconds >= 60:
        return f"hace {delta.seconds // 60}m"
    return "ahora"


def crear_notificacion(user_id, tipo, mensaje, url):
    """Crea una notificación para un usuario."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO notificaciones (usuario_id, tipo, mensaje, url) VALUES (%s, %s, %s, %s)",
            (user_id, tipo, mensaje, url)
        )
        conn.commit()
        cur.close()
        conn.close()
    except:
        pass


# -----------------------------------------------------------------------------
# ESTILOS CSS
# -----------------------------------------------------------------------------
STYLE = """
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Inter:wght@400;500;600;700&family=Montserrat:wght@500;600;700&display=swap');

:root {
    --bg-color: #000000; --bg-secondary: #111111;
    --surface: #1C1C1E; --surface-hover: #2C2C2E;
    --text-primary: #FFFFFF; --text-secondary: #8E8E93;
    --border-color: #38383A; --accent: #FF3B30;
    --blue: #0A84FF; --green: #30D158; --shadow: 0 10px 30px rgba(0,0,0,0.5);
}
:root[data-theme="light"] {
    --bg-color: #F2F2F7; --bg-secondary: #FFFFFF;
    --surface: #FFFFFF; --surface-hover: #F2F2F7;
    --text-primary: #000000; --text-secondary: #8E8E93;
    --border-color: #C6C6C8; --shadow: 0 10px 30px rgba(0,0,0,0.08);
}

* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Inter', sans-serif; background: var(--bg-color); color: var(--text-primary); line-height: 1.5; transition: 0.3s; }
h1, h2, h3, .title-font { font-family: 'Bebas Neue', sans-serif; letter-spacing: 1px; }
button, .btn-font { font-family: 'Montserrat', sans-serif; }

.container { max-width: 720px; margin: 0 auto; padding: 0 16px; }

/* NAVBAR */
.navbar { position: sticky; top: 0; z-index: 1000; background: rgba(28, 28, 30, 0.8); backdrop-filter: blur(20px); border-bottom: 0.5px solid var(--border-color); padding: 12px 0; }
.nav-inner { display: flex; justify-content: space-between; align-items: center; max-width: 720px; margin: 0 auto; padding: 0 16px; }
.nav-brand { font-size: 28px; color: var(--text-primary); text-decoration: none; }
.nav-links { display: flex; gap: 10px; align-items: center; }
.nav-btn { padding: 8px 14px; border-radius: 20px; background: transparent; color: var(--text-primary); border: 1px solid var(--border-color); font-weight: 600; font-size: 13px; cursor: pointer; text-decoration: none; }
.nav-btn.active { background: var(--accent); border-color: var(--accent); color: white; }
.icon-btn { background: transparent; border: none; font-size: 20px; cursor: pointer; position: relative; color: var(--text-primary); padding: 5px; text-decoration: none; }
.badge-notif { position: absolute; top: -2px; right: -2px; background: var(--accent); color: white; font-size: 10px; width: 16px; height: 16px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: bold; }

/* CARDS & FORMS */
.card { background: var(--surface); border: 1px solid var(--border-color); border-radius: 16px; padding: 20px; margin-bottom: 16px; box-shadow: var(--shadow); }
input, textarea, select { width: 100%; background: var(--bg-secondary); border: 1px solid var(--border-color); color: var(--text-primary); padding: 14px; border-radius: 12px; font-family: inherit; font-size: 15px; outline: none; margin-bottom: 12px; }
input:focus { border-color: var(--accent); }
button.btn-main { background: var(--accent); color: white; border: none; padding: 14px 24px; border-radius: 12px; font-weight: 600; cursor: pointer; width: 100%; transition: 0.2s; }
button.btn-main:hover { background: #ff453a; }
.btn-sec { background: var(--surface-hover); border: 1px solid var(--border-color); color: var(--text-primary); padding: 6px 12px; border-radius: 8px; font-size: 13px; cursor: pointer; }
.btn-follow { background: var(--blue); color: white; border: none; padding: 6px 14px; border-radius: 20px; font-weight: 600; font-size: 13px; cursor: pointer; }
.btn-follow.following { background: transparent; border: 1px solid var(--border-color); color: var(--text-primary); }

/* PROFILE */
.banner { height: 150px; background: #333; border-radius: 16px 16px 0 0; margin-bottom: 16px; background-size: cover; background-position: center; position: relative; }
.avatar { width: 80px; height: 80px; border-radius: 50%; background: var(--surface); border: 4px solid var(--surface); position: absolute; bottom: -40px; left: 16px; overflow: hidden; display: flex; align-items: center; justify-content: center; font-weight: bold; color: white; }
.avatar img { width: 100%; height: 100%; object-fit: cover; }
.avatar-small { width: 44px; height: 44px; font-size: 18px; }
.profile-stats { display: flex; gap: 20px; margin-top: 30px; margin-bottom: 16px; font-weight: 600; }
.stat-item span { display: block; font-size: 18px; }
.stat-item small { color: var(--text-secondary); font-weight: 400; }

/* POST */
.post-header { display: flex; gap: 12px; margin-bottom: 12px; position: relative; }
.post-content { font-size: 16px; white-space: pre-wrap; word-wrap: break-word; }
.post-image { width: 100%; border-radius: 12px; margin-top: 10px; border: 1px solid var(--border-color); }
.post-actions { display: flex; gap: 10px; border-top: 1px solid var(--border-color); padding-top: 12px; margin-top: 12px; }
.action-btn { background: transparent; border: none; color: var(--text-secondary); cursor: pointer; font-weight: 600; font-size: 14px; display: flex; align-items: center; gap: 6px; }
.action-btn.liked { color: var(--accent); }

/* NOTIFICACIONES */
.notif-item { padding: 12px; border-bottom: 1px solid var(--border-color); display: flex; align-items: center; gap: 10px; }
.notif-item.unread { background: rgba(10, 132, 255, 0.1); }

/* RESPONSIVE */
@media (max-width: 600px) {
    .container { padding: 0 8px; }
    .nav-btn span { display: none; }
}
"""


# -----------------------------------------------------------------------------
# PLANTILLAS HTML
# -----------------------------------------------------------------------------
BASE_LAYOUT = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MOTOSCLUB</title>
    <style>{{ style }}</style>
</head>
<body>
    <nav class="navbar">
        <div class="nav-inner">
            <a href="/foro" class="nav-brand">🏍️ MOTOSCLUB</a>
            <div class="nav-links">
                <button onclick="toggleTheme()" class="icon-btn" id="theme-toggle">🌙</button>
                <a href="/buscar" class="icon-btn">🔍</a>
                <a href="/notificaciones" class="icon-btn">
                    🔔
                    {% if notif_count > 0 %}<span class="badge-notif">{{ notif_count }}</span>{% endif %}
                </a>
                <a href="/perfil" class="nav-btn {% if active=='perfil' %}active{% endif %}">Yo</a>
                <a href="/logout" class="nav-btn">Salir</a>
            </div>
        </div>
    </nav>

    <div class="container" style="padding-top: 20px;">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="card" style="background: {% if category=='error' %}rgba(255,59,48,0.1){% else %}rgba(48,209,88,0.1){% endif %}; border: 1px solid {% if category=='error' %}#FF3B30{% else %}#30D158{% endif %}; color: {% if category=='error' %}#FF3B30{% else %}#30D158{% endif %}; padding: 12px; border-radius: 12px; margin-bottom: 16px; font-weight: 600; text-align: center;">
                        {{ message }}
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        __CONTENT__
    </div>

    <script>
        function applyTheme(theme) {
            document.documentElement.setAttribute('data-theme', theme);
            localStorage.setItem('theme', theme);
            document.getElementById('theme-toggle').textContent = theme === 'light' ? '☀️' : '🌙';
        }
        function toggleTheme() {
            const current = localStorage.getItem('theme') || 'dark';
            applyTheme(current === 'dark' ? 'light' : 'dark');
        }
        (function() { applyTheme(localStorage.getItem('theme') || 'dark'); })();
        function toggleCom(id) {
            const el = document.getElementById('com-' + id);
            if (el) el.style.display = el.style.display === 'none' ? 'block' : 'none';
        }
    </script>
</body>
</html>
"""


# -----------------------------------------------------------------------------
# RUTAS PRINCIPALES
# -----------------------------------------------------------------------------
@app.route('/', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect('/foro')

    login_html = """
    <div style="display:flex; justify-content:center; align-items:center; min-height:80vh;">
        <div class="card" style="width:100%; max-width:420px;">
            <h1 class="title-font" style="text-align:center; font-size:40px; margin-bottom:20px;">MOTOSCLUB</h1>
            <form method="POST">
                <input type="text" name="nombre" placeholder="Usuario" required autocomplete="off">
                <input type="password" name="password" placeholder="Contraseña" required>
                <button name="login" class="btn-main btn-font">ENTRAR</button>
                <button name="register" class="btn-main btn-font" style="background:#333; margin-top:8px;">REGISTRAR</button>
            </form>
        </div>
    </div>
    """

    if request.method == 'POST':
        nombre = request.form['nombre'].strip()
        passw = request.form['password']
        conn = get_db_connection()
        cur = conn.cursor()

        if 'register' in request.form:
            try:
                hash_p = generate_password_hash(passw)
                cur.execute("INSERT INTO usuarios (nombre, password) VALUES (%s, %s)", (nombre, hash_p))
                conn.commit()
                flash("¡Cuenta creada! Entra ahora.", "success")
            except:
                flash("Ese usuario ya existe.", "error")

        elif 'login' in request.form:
            cur.execute("SELECT id, password, avatar_url, banner_url, bio, moto FROM usuarios WHERE nombre = %s", (nombre,))
            u = cur.fetchone()
            if u and check_password_hash(u[1], passw):
                session['user_id'] = u[0]
                session['user_name'] = nombre
                session['avatar_url'] = u[2] or ''
                session['banner_url'] = u[3] or ''
                session['bio'] = u[4] or ''
                session['moto'] = u[5] or ''
                cur.close()
                conn.close()
                return redirect('/foro')
            else:
                flash("Datos incorrectos.", "error")

        cur.close()
        conn.close()

    return render_template_string(BASE_LAYOUT.replace("__CONTENT__", login_html), style=STYLE, notif_count=0)


@app.route('/foro')
@login_required
def foro():
    conn = get_db_connection()
    cur = conn.cursor()

    # Obtener usuarios que sigo + yo mismo
    cur.execute("SELECT seguido_id FROM seguidores WHERE seguidor_id = %s", (session['user_id'],))
    following_ids = [row[0] for row in cur.fetchall()]
    following_ids.append(session['user_id'])

    # Query principal de posts
    cur.execute("""
        SELECT p.id, u.nombre, p.contenido, p.fecha, p.categoria, u.moto, u.avatar_url, p.usuario_id,
               (SELECT COUNT(*) FROM likes l WHERE l.post_id = p.id),
               (SELECT COUNT(*) FROM comentarios c WHERE c.post_id = p.id),
               (EXISTS(SELECT 1 FROM likes WHERE post_id=p.id AND usuario_id=%s)),
               (EXISTS(SELECT 1 FROM bookmarks WHERE post_id=p.id AND usuario_id=%s)),
               p.imagen_url, p.reportes
        FROM posts p JOIN usuarios u ON p.usuario_id = u.id
        WHERE p.reportes < 5 AND p.usuario_id IN %s
        ORDER BY p.fecha DESC LIMIT 30
    """, (session['user_id'], session['user_id'], tuple(following_ids)))

    posts = []
    for p in cur.fetchall():
        # Comentarios del post
        cur.execute("""
            SELECT u.nombre, c.contenido, c.fecha, u.avatar_url
            FROM comentarios c JOIN usuarios u ON c.usuario_id = u.id
            WHERE c.post_id = %s ORDER BY c.fecha ASC LIMIT 5
        """, (p[0],))
        coms = [(c[0], c[1], time_ago(c[2]), string_to_color(c[0]) if not c[3] else c[3]) for c in cur.fetchall()]

        posts.append((
            p[0], p[1], p[2], procesar_texto(p[2]), p[4], time_ago(p[3]),
            string_to_color(p[1]) if not p[6] else p[6], p[7], p[8], p[9],
            coms, p[10], p[12], p[11]  # id, autor, contenido, safe, cat, fecha, avatar, uid, likes, comments, coms_list, liked, img, bookmarked
        ))

    cur.close()
    conn.close()

    foro_html = """
    <div class="card">
        <form method="POST" action="/post" enctype="multipart/form-data">
            <textarea name="contenido" placeholder="¿Qué ruta haces hoy? Usa @menciones y #hashtags" required></textarea>
            <div style="display:flex; gap:10px; align-items:center; margin-bottom:10px; flex-wrap:wrap;">
                <select name="categoria" style="width:auto; margin-bottom:0;">
                    <option value="General">General</option>
                    <option value="Ruta">🛣️ Ruta</option>
                    <option value="Mecanica">🔧 Mecánica</option>
                    <option value="Venta">💰 Venta</option>
                </select>
                <input type="file" name="foto" accept="image/*" style="padding:5px; font-size:12px; width:auto; margin:0;">
            </div>
            <button class="btn-main btn-font">PUBLICAR</button>
        </form>
    </div>

    {% for p in posts %}
    <div class="card" id="post-{{ p[0] }}">
        <div class="post-header">
            <a href="/perfil/{{ p[1] }}">
                {% if p[6].startswith('http') %}
                    <img src="{{ p[6] }}" class="avatar avatar-small" onerror="this.parentElement.innerHTML='<div class=\\'avatar avatar-small\\' style=\\'background:{{ p[6] }}\\'>{{ p[1][0] }}</div>'">
                {% else %}
                    <div class="avatar avatar-small" style="background:{{ p[6] }}">{{ p[1][0] }}</div>
                {% endif %}
            </a>
            <div style="flex:1;">
                <a href="/perfil/{{ p[1] }}"><strong>{{ p[1] }}</strong></a>
                <small style="color:var(--text-secondary)">{{ p[5] }} • {{ p[4] }}</small>
            </div>
            {% if session.get('user_id') == p[7] %}
                <form action="/delete/{{ p[0] }}" method="POST" onsubmit="return confirm('¿Borrar?')">
                    <button class="btn-sec">🗑️</button>
                </form>
            {% endif %}
            <form action="/report/{{ p[0] }}" method="POST" onsubmit="return confirm('¿Reportar contenido?')">
                <button class="btn-sec">⚠️</button>
            </form>
        </div>

        <div class="post-content">{{ p[3] | safe }}</div>
        {% if p[12] %}<img src="{{ p[12] }}" class="post-image">{% endif %}

        <div class="post-actions">
            <form action="/like/{{ p[0] }}" method="POST" style="display:inline;">
                <button class="action-btn {% if p[10] %}liked{% endif %}">⛽ {{ p[8] }}</button>
            </form>
            <button class="action-btn" onclick="toggleCom({{ p[0] }})">💬 {{ p[9] }}</button>
            <form action="/bookmark/{{ p[0] }}" method="POST" style="display:inline;">
                <button class="action-btn {% if p[13] %}liked{% endif %}">🔖</button>
            </form>
        </div>

        <div id="com-{{ p[0] }}" style="display:none; margin-top:10px; border-top:1px solid var(--border-color); padding-top:10px;">
            <form action="/comment/{{ p[0] }}" method="POST" style="display:flex; gap:5px; margin-bottom:10px;">
                <input type="text" name="contenido" placeholder="Responder..." required style="margin:0; flex:1;">
                <button class="btn-sec" type="submit">Enviar</button>
            </form>
            {% for c in p[10] %}
            <div style="background:var(--bg-secondary); padding:8px 12px; border-radius:8px; margin-bottom:5px; font-size:14px;">
                <b>{{ c[0] }}</b>: {{ c[1] }}
            </div>
            {% endfor %}
        </div>
    </div>
    {% endfor %}
    """

    # Contar notificaciones no leídas
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM notificaciones WHERE usuario_id=%s AND leido=FALSE", (session['user_id'],))
    notif_count = cur.fetchone()[0]
    cur.close()
    conn.close()

    return render_template_string(BASE_LAYOUT.replace("__CONTENT__", foro_html), style=STYLE, posts=posts, active='foro', notif_count=notif_count)


@app.route('/post', methods=['POST'])
@login_required
def post():
    contenido = request.form['contenido']
    categoria = request.form.get('categoria', 'General')
    foto_file = request.files.get('foto')

    imagen_url = ""
    if foto_file and foto_file.filename:
        imagen_url = upload_to_imgbb(foto_file)

    if len(contenido) > 0 or imagen_url:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO posts (usuario_id, contenido, categoria, imagen_url) VALUES (%s, %s, %s, %s)",
            (session['user_id'], contenido, categoria, imagen_url)
        )

        # Gamificación: Actualizar racha
        cur.execute("SELECT ultima_actividad FROM usuarios WHERE id = %s", (session['user_id'],))
        last = cur.fetchone()[0]
        today = datetime.now().date()
        if last == today - timedelta(days=1):
            cur.execute("UPDATE usuarios SET racha = racha + 1, ultima_actividad = %s WHERE id = %s", (today, session['user_id']))
        elif last != today:
            cur.execute("UPDATE usuarios SET racha = 1, ultima_actividad = %s WHERE id = %s", (today, session['user_id']))

        conn.commit()
        cur.close()
        conn.close()
        flash("¡Publicado!", "success")

        # Notificar menciones
        menciones = re.findall(r'@(\w+)', contenido)
        for m in menciones:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT id FROM usuarios WHERE nombre = %s", (m,))
            user = cur.fetchone()
            if user and user[0] != session['user_id']:
                crear_notificacion(user[0], 'mencion', f"{session['user_name']} te mencionó", f"/foro")
            cur.close()
            conn.close()

    return redirect('/foro')


@app.route('/perfil')
@app.route('/perfil/<username>')
@login_required
def perfil(username=None):
    target_user = username or session['user_name']
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT id, nombre, bio, moto, avatar_url, banner_url, racha FROM usuarios WHERE nombre = %s", (target_user,))
    user_data = cur.fetchone()

    if not user_data:
        flash("Usuario no encontrado", "error")
        return redirect('/foro')

    user_id = user_data[0]

    # Estadísticas
    cur.execute("SELECT COUNT(*) FROM posts WHERE usuario_id = %s", (user_id,))
    posts_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM seguidores WHERE seguido_id = %s", (user_id,))
    followers = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM seguidores WHERE seguidor_id = %s", (user_id,))
    following = cur.fetchone()[0]

    # ¿Sigo a este usuario?
    is_following = False
    if user_id != session['user_id']:
        cur.execute("SELECT 1 FROM seguidores WHERE seguidor_id = %s AND seguido_id = %s", (session['user_id'], user_id))
        is_following = cur.fetchone() is not None

    # Posts del usuario
    cur.execute("SELECT id, contenido, fecha, imagen_url FROM posts WHERE usuario_id = %s ORDER BY fecha DESC", (user_id,))
    posts = cur.fetchall()

    cur.close()
    conn.close()

    # Avatar fallback
    avatar_display = f"<img src='{user_data[4]}' onerror=\"this.style.display='none'; this.parentElement.innerHTML='{user_data[1][0]}'\">" if user_data[4] else user_data[1][0]
    banner_style = f"background-image:url('{user_data[5]}');" if user_data[5] else ""

    perfil_html = f"""
    <div class="card" style="padding:0; overflow:hidden;">
        <div class="banner" style="{banner_style}background-color:#333;"></div>
        <div style="padding: 0 20px 20px;">
            <div class="avatar" style="bottom:-50px;">{avatar_display}</div>
            <div style="margin-top:50px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
                <div>
                    <h1 class="title-font" style="font-size:28px;">{user_data[1]}</h1>
                    <p style="color:var(--text-secondary)">{user_data[3] or 'Motero'}</p>
                </div>
                {"<form action='/seguir/" + str(user_id) + "' method='POST'><button class='btn-follow btn-font'>" + ('Dejar de seguir' if is_following else 'Seguir') + "</button></form>" if user_id != session['user_id'] else "<a href='/config' class='btn-sec'>Editar Perfil</a>"}
            </div>
            <p style="margin:15px 0; white-space:pre-wrap;">{user_data[2]}</p>
            <div class="profile-stats">
                <div class="stat-item"><span>{posts_count}</span><small>Posts</small></div>
                <div class="stat-item"><span>{followers}</span><small>Seguidores</small></div>
                <div class="stat-item"><span>{following}</span><small>Siguiendo</small></div>
                <div class="stat-item"><span>🔥 {user_data[6]}</span><small>Racha</small></div>
            </div>
        </div>
    </div>

    <h3 class="title-font" style="margin:20px 0 10px;">PUBLICACIONES</h3>
    """

    for p in posts:
        perfil_html += f"""
        <div class="card">
            <p style="white-space:pre-wrap;">{procesar_texto(p[1])}</p>
            {f'<img src="{p[3]}" class="post-image">' if p[3] else ''}
            <small style="color:var(--text-secondary)">{time_ago(p[2])}</small>
        </div>
        """

    # Contar notificaciones
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM notificaciones WHERE usuario_id=%s AND leido=FALSE", (session['user_id'],))
    notif_count = cur.fetchone()[0]
    cur.close()
    conn.close()

    return render_template_string(BASE_LAYOUT.replace("__CONTENT__", perfil_html), style=STYLE, active='perfil', notif_count=notif_count)


@app.route('/config', methods=['GET', 'POST'])
@login_required
def config():
    if request.method == 'POST':
        bio = request.form['bio']
        moto = request.form['moto']
        avatar = request.files.get('avatar')
        banner = request.files.get('banner')

        avatar_url = session.get('avatar_url', '')
        banner_url = session.get('banner_url', '')

        if avatar and avatar.filename:
            avatar_url = upload_to_imgbb(avatar)
            session['avatar_url'] = avatar_url
        if banner and banner.filename:
            banner_url = upload_to_imgbb(banner)
            session['banner_url'] = banner_url

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE usuarios SET bio=%s, moto=%s, avatar_url=%s, banner_url=%s WHERE id=%s",
            (bio, moto, avatar_url, banner_url, session['user_id'])
        )
        conn.commit()
        cur.close()
        conn.close()
        flash("Perfil actualizado", "success")
        return redirect('/perfil')

    config_html = """
    <div class="card">
        <h2 class="title-font">Editar Perfil</h2>
        <form method="POST" enctype="multipart/form-data">
            <textarea name="bio" placeholder="Biografía">{{ session.get('bio', '') }}</textarea>
            <input type="text" name="moto" placeholder="Tu moto" value="{{ session.get('moto', '') }}">
            <label style="font-weight:600; margin:10px 0 5px; display:block;">Foto de Perfil</label>
            <input type="file" name="avatar" accept="image/*">
            <label style="font-weight:600; margin:10px 0 5px; display:block;">Foto de Portada</label>
            <input type="file" name="banner" accept="image/*">
            <button class="btn-main" style="margin-top:15px;">Guardar Cambios</button>
        </form>
    </div>
    """

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM notificaciones WHERE usuario_id=%s AND leido=FALSE", (session['user_id'],))
    notif_count = cur.fetchone()[0]
    cur.close()
    conn.close()

    return render_template_string(BASE_LAYOUT.replace("__CONTENT__", config_html), style=STYLE, notif_count=notif_count)


# -----------------------------------------------------------------------------
# RUTAS AUXILIARES
# -----------------------------------------------------------------------------
@app.route('/like/<int:pid>', methods=['POST'])
@login_required
def like(pid):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO likes (usuario_id, post_id) VALUES (%s, %s)", (session['user_id'], pid))
        cur.execute("SELECT usuario_id FROM posts WHERE id=%s", (pid,))
        owner = cur.fetchone()
        if owner and owner[0] != session['user_id']:
            crear_notificacion(owner[0], 'like', f"A {session['user_name']} le gustó tu post", f"/post/{pid}")
        conn.commit()
    except:
        conn.rollback()
        cur.execute("DELETE FROM likes WHERE usuario_id = %s AND post_id = %s", (session['user_id'], pid))
        conn.commit()
    cur.close()
    conn.close()
    return redirect('/foro')


@app.route('/bookmark/<int:pid>', methods=['POST'])
@login_required
def bookmark(pid):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO bookmarks (usuario_id, post_id) VALUES (%s, %s)", (session['user_id'], pid))
        conn.commit()
    except:
        conn.rollback()
        cur.execute("DELETE FROM bookmarks WHERE usuario_id = %s AND post_id = %s", (session['user_id'], pid))
        conn.commit()
    cur.close()
    conn.close()
    return redirect('/foro')


@app.route('/seguir/<int:uid>', methods=['POST'])
@login_required
def seguir(uid):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO seguidores (seguidor_id, seguido_id) VALUES (%s, %s)", (session['user_id'], uid))
        crear_notificacion(uid, 'seguir', f"{session['user_name']} empezó a seguirte", f"/perfil/{session['user_name']}")
        conn.commit()
    except:
        conn.rollback()
        cur.execute("DELETE FROM seguidores WHERE seguidor_id = %s AND seguido_id = %s", (session['user_id'], uid))
        conn.commit()
    cur.close()
    conn.close()
    return redirect(request.referrer or '/foro')


@app.route('/delete/<int:pid>', methods=['POST'])
@login_required
def delete(pid):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM posts WHERE id = %s AND usuario_id = %s", (pid, session['user_id']))
    conn.commit()
    cur.close()
    conn.close()
    return redirect('/foro')


@app.route('/report/<int:pid>', methods=['POST'])
@login_required
def report(pid):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE posts SET reportes = reportes + 1 WHERE id = %s", (pid,))
    conn.commit()
    cur.close()
    conn.close()
    flash("Contenido reportado.", "success")
    return redirect('/foro')


@app.route('/comment/<int:pid>', methods=['POST'])
@login_required
def comment(pid):
    txt = request.form['contenido'].strip()
    if len(txt) > 0:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO comentarios (post_id, usuario_id, contenido) VALUES (%s, %s, %s)", (pid, session['user_id'], txt))
        cur.execute("SELECT usuario_id FROM posts WHERE id=%s", (pid,))
        owner = cur.fetchone()
        if owner and owner[0] != session['user_id']:
            crear_notificacion(owner[0], 'comentario', f"{session['user_name']} comentó tu post", f"/post/{pid}")
        conn.commit()
        cur.close()
        conn.close()
    return redirect('/foro')


@app.route('/notificaciones')
@login_required
def notifs():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE notificaciones SET leido=TRUE WHERE usuario_id=%s", (session['user_id'],))
    conn.commit()
    cur.execute("SELECT tipo, mensaje, url, fecha FROM notificaciones WHERE usuario_id=%s ORDER BY fecha DESC LIMIT 20", (session['user_id'],))
    notifs_list = cur.fetchall()
    cur.close()
    conn.close()

    html_content = """
    <h2 class="title-font">NOTIFICACIONES</h2>
    {% if notifs %}
        {% for n in notifs %}
        <a href="{{ n[2] }}" class="card" style="display:block; margin-bottom:10px; text-decoration:none; color:inherit;">
            <strong>{{ n[1] }}</strong><br>
            <small style="color:var(--text-secondary)">{{ n[3] }}</small>
        </a>
        {% endfor %}
    {% else %}
        <div class="card" style="text-align:center; color:var(--text-secondary);">Sin notificaciones nuevas 🎉</div>
    {% endif %}
    """

    return render_template_string(BASE_LAYOUT.replace("__CONTENT__", html_content), style=STYLE, notifs=notifs_list, notif_count=0)


@app.route('/buscar')
@login_required
def buscar():
    query = request.args.get('q', '')
    tag = request.args.get('tag', '')

    conn = get_db_connection()
    cur = conn.cursor()

    if tag:
        cur.execute("""
            SELECT p.id, u.nombre, p.contenido, p.fecha, u.avatar_url, p.imagen_url
            FROM posts p JOIN usuarios u ON p.usuario_id = u.id
            WHERE p.contenido ILIKE %s AND p.reportes < 5
            ORDER BY p.fecha DESC LIMIT 30
        """, (f'%#{tag}%',))
        titulo = f"Posts con #{tag}"
    elif query:
        cur.execute("""
            SELECT p.id, u.nombre, p.contenido, p.fecha, u.avatar_url, p.imagen_url
            FROM posts p JOIN usuarios u ON p.usuario_id = u.id
            WHERE (p.contenido ILIKE %s OR u.nombre ILIKE %s) AND p.reportes < 5
            ORDER BY p.fecha DESC LIMIT 30
        """, (f'%{query}%', f'%{query}%'))
        titulo = f"Resultados para '{query}'"
    else:
        cur.execute("""
            SELECT p.id, u.nombre, p.contenido, p.fecha, u.avatar_url, p.imagen_url
            FROM posts p JOIN usuarios u ON p.usuario_id = u.id
            WHERE p.reportes < 5
            ORDER BY p.fecha DESC LIMIT 30
        """)
        titulo = "Explorar"

    posts = [(p[0], p[1], procesar_texto(p[2]), time_ago(p[3]), string_to_color(p[1]) if not p[4] else p[4], p[5]) for p in cur.fetchall()]
    cur.close()
    conn.close()

    buscar_html = f"""
    <h2 class="title-font">{titulo}</h2>
    <form action="/buscar" method="GET" style="margin:15px 0;">
        <input type="text" name="q" placeholder="🔍 Buscar usuarios o posts..." value="{query}" style="margin:0;">
    </form>
    """

    for p in posts:
        buscar_html += f"""
        <div class="card">
            <div style="display:flex; gap:10px; margin-bottom:10px;">
                <div class="avatar avatar-small" style="background:{p[4]}">{p[1][0]}</div>
                <div>
                    <a href="/perfil/{p[1]}"><strong>{p[1]}</strong></a>
                    <small style="color:var(--text-secondary)">{p[3]}</small>
                </div>
            </div>
            <p style="white-space:pre-wrap;">{p[2]}</p>
            {f'<img src="{p[5]}" class="post-image">' if p[5] else ''}
        </div>
        """

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM notificaciones WHERE usuario_id=%s AND leido=FALSE", (session['user_id'],))
    notif_count = cur.fetchone()[0]
    cur.close()
    conn.close()

    return render_template_string(BASE_LAYOUT.replace("__CONTENT__", buscar_html), style=STYLE, notif_count=notif_count)


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')


# -----------------------------------------------------------------------------
# ENTRY POINT
# -----------------------------------------------------------------------------
if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=False)
