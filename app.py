import os
import re
import html
import psycopg2
from flask import Flask, request, redirect, render_template_string, session, flash, url_for, get_flashed_messages
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from functools import wraps

# --- CONFIGURACIÓN DE LA APP ---
app = Flask(__name__)
app.secret_key = os.urandom(24)

# --- CONFIGURACIÓN BASE DE DATOS ---
DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db_connection():
    """Establece conexión con la base de datos PostgreSQL."""
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def init_db():
    """Inicializa la base de datos y aplica migraciones si es necesario."""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Tabla Usuarios
    cur.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id SERIAL PRIMARY KEY,
            nombre TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            bio TEXT DEFAULT '',
            moto TEXT DEFAULT '',
            fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    
    # Tabla Posts
    cur.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id SERIAL PRIMARY KEY,
            usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
            contenido TEXT NOT NULL,
            categoria TEXT DEFAULT 'General',
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    
    # Tabla Likes (Gas)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS likes (
            usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
            post_id INTEGER REFERENCES posts(id) ON DELETE CASCADE,
            PRIMARY KEY (usuario_id, post_id)
        );
    """)
    
    # Tabla Comentarios
    cur.execute("""
        CREATE TABLE IF NOT EXISTS comentarios (
            id SERIAL PRIMARY KEY, 
            post_id INTEGER REFERENCES posts(id) ON DELETE CASCADE, 
            usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE, 
            contenido TEXT, 
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Migraciones (Añadir columnas si no existen para versiones antiguas)
    try: cur.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS bio TEXT;")
    except: pass
    try: cur.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS moto TEXT;")
    except: pass
    try: cur.execute("ALTER TABLE posts ADD COLUMN IF NOT EXISTS categoria TEXT;")
    except: pass

    conn.commit()
    cur.close()
    conn.close()

# --- DECORADORES Y FILTROS ---

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Debes iniciar sesión para acceder.", "error")
            return redirect('/')
        return f(*args, **kwargs)
    return decorated_function

def url_to_image(text):
    """Convierte URLs de imagen en etiquetas <img> seguras."""
    # Escapamos HTML primero para evitar XSS
    text = html.escape(text)
    # Regex para imágenes
    pattern = r'(https?://[^\s]+?\.(png|jpg|jpeg|gif|webp|avif))'
    return re.sub(pattern, r'<img src="\1" class="post-image" loading="lazy">', text)

def string_to_color(s):
    """Genera un color HSL único basado en el string."""
    h = sum(ord(c) for c in s) % 360
    return f"hsl({h}, 60%, 45%)"

def time_ago(dt):
    """Convierte timestamp a formato relativo (ej: hace 5m)."""
    delta = datetime.now() - dt
    if delta.days > 365: return f"hace {delta.days // 365} años"
    if delta.days > 30: return f"hace {delta.days // 30} meses"
    if delta.days > 0: return f"hace {delta.days}d"
    if delta.seconds >= 3600: return f"hace {delta.seconds // 3600}h"
    if delta.seconds >= 60: return f"hace {delta.seconds // 60}m"
    return "ahora mismo"

# --- ESTILO CSS (DARK/LIGHT MODE PREMIUM) ---
STYLE = """
/* VARIABLES DE COLOR MODO OSCURO (POR DEFECTO) */
:root {
    --bg-color: #000000;
    --bg-secondary: #1c1c1e;
    --surface: #111111;
    --surface-hover: #1c1c1e;
    --text-primary: #ffffff;
    --text-secondary: #8e8e93;
    --border-color: #38383a;
    --accent-color: #FF3B30; /* Rojo Moto */
    --accent-hover: #ff453a;
    --blue: #0A84FF;
    --green: #30D158;
    --shadow: 0 10px 30px rgba(0,0,0,0.5);
    --radius: 16px;
    --font-main: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}

/* VARIABLES MODO CLARO */
:root[data-theme="light"] {
    --bg-color: #f2f2f7;
    --bg-secondary: #ffffff;
    --surface: #ffffff;
    --surface-hover: #f2f2f7;
    --text-primary: #000000;
    --text-secondary: #8e8e93;
    --border-color: #c6c6c8;
    --accent-color: #FF3B30;
    --shadow: 0 10px 30px rgba(0,0,0,0.08);
}

/* RESET Y BASE */
* { box-sizing: border-box; margin: 0; padding: 0; }
body { 
    font-family: var(--font-main); 
    background-color: var(--bg-color); 
    color: var(--text-primary); 
    line-height: 1.5; 
    transition: background-color 0.3s ease, color 0.3s ease;
    -webkit-font-smoothing: antialiased;
}
a { color: var(--blue); text-decoration: none; transition: opacity 0.2s; }
a:hover { opacity: 0.8; }

/* CONTENEDOR PRINCIPAL */
.container { max-width: 720px; margin: 0 auto; padding: 0 16px; }

/* NAVEGACIÓN FLUIDA */
.navbar { 
    position: sticky; top: 0; z-index: 1000; 
    background: rgba(28, 28, 30, 0.8); 
    backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
    border-bottom: 0.5px solid var(--border-color);
    padding: 12px 0;
}
.nav-inner { display: flex; justify-content: space-between; align-items: center; max-width: 720px; margin: 0 auto; padding: 0 16px; }
.nav-brand { font-size: 20px; font-weight: 700; color: var(--text-primary); display: flex; align-items: center; gap: 8px; }
.nav-links { display: flex; align-items: center; gap: 12px; }
.nav-btn { 
    padding: 8px 14px; border-radius: 20px; 
    background: transparent; color: var(--text-primary); 
    border: 1px solid var(--border-color); font-weight: 600; 
    font-size: 14px; cursor: pointer; transition: all 0.2s;
}
.nav-btn.active { background: var(--accent-color); border-color: var(--accent-color); color: white; }
.nav-btn:hover { background: var(--surface-hover); }

/* Interruptor de tema (Toggle) */
.theme-switch { 
    background: var(--surface-hover); border: none; 
    width: 36px; height: 36px; border-radius: 50%; 
    display: flex; align-items: center; justify-content: center; 
    cursor: pointer; font-size: 18px;
}

/* TARJETAS (CARDS) */
.card { 
    background: var(--surface); border: 1px solid var(--border-color); 
    border-radius: var(--radius); padding: 20px; margin-bottom: 16px; 
    box-shadow: var(--shadow); transition: transform 0.2s;
}
.card:hover { transform: translateY(-1px); }

/* FORMULARIOS */
input, textarea, select { 
    width: 100%; background: var(--bg-secondary); border: 1px solid var(--border-color); 
    color: var(--text-primary); padding: 14px; border-radius: 12px; 
    font-family: inherit; font-size: 16px; outline: none; margin-bottom: 12px;
    transition: border-color 0.2s;
}
input:focus, textarea:focus { border-color: var(--accent-color); }
textarea { resize: vertical; min-height: 80px; }
select { cursor: pointer; appearance: none; background-image: url("data:image/svg+xml;utf8,<svg fill='%23fff' height='24' viewBox='0 0 24 24' width='24' xmlns='http://www.w3.org/2000/svg'><path d='M7 10l5 5 5-5z'/></svg>"); background-repeat: no-repeat; background-position: right 10px center; }

/* BOTONES */
button.btn-main { 
    background: var(--accent-color); color: white; border: none; 
    padding: 14px 24px; border-radius: 12px; font-weight: 700; 
    cursor: pointer; width: 100%; font-size: 16px;
    transition: transform 0.1s, background 0.2s;
}
button.btn-main:active { transform: scale(0.98); }
button.btn-main:hover { background: var(--accent-hover); }
.btn-sec { 
    background: var(--surface-hover); border: 1px solid var(--border-color); 
    color: var(--text-primary); padding: 6px 12px; 
    border-radius: 8px; font-size: 13px; cursor: pointer;
}

/* AVATAR */
.avatar { 
    width: 44px; height: 44px; border-radius: 50%; 
    display: flex; align-items: center; justify-content: center; 
    font-weight: 700; color: white; flex-shrink: 0; font-size: 18px;
}

/* POST DETALLE */
.post-header { display: flex; justify-content: space-between; margin-bottom: 12px; }
.post-user { display: flex; align-items: center; gap: 12px; }
.post-meta { font-size: 13px; color: var(--text-secondary); margin-top: 2px; }
.post-content { font-size: 17px; margin-bottom: 16px; line-height: 1.4; }
.post-image { width: 100%; border-radius: 12px; margin-top: 10px; border: 1px solid var(--border-color); }

/* ACCIONES POST (GAS/COMENTARIOS) */
.post-actions { display: flex; border-top: 1px solid var(--border-color); padding-top: 12px; gap: 10px; }
.action-btn { 
    background: transparent; border: none; color: var(--text-secondary); 
    cursor: pointer; font-weight: 600; font-size: 14px; 
    display: flex; align-items: center; gap: 6px; padding: 4px;
}
.action-btn.active { color: var(--accent-color); }
.action-btn:hover { color: var(--text-primary); }

/* COMENTARIOS */
.comments-section { margin-top: 16px; border-top: 1px solid var(--border-color); padding-top: 16px; }
.comment-box { display: flex; gap: 8px; margin-bottom: 12px; }
.comment-card { background: var(--bg-secondary); padding: 10px 14px; border-radius: 12px; margin-bottom: 8px; }
.comment-text { font-size: 14px; }
.comment-author { font-weight: 700; font-size: 13px; margin-right: 6px; }

/* CATEGORÍAS BADGES */
.badge { 
    font-size: 11px; padding: 3px 8px; border-radius: 6px; 
    font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;
}
.badge-route { background: rgba(10, 132, 255, 0.15); color: var(--blue); }
.badge-mech { background: rgba(255, 59, 48, 0.15); color: var(--accent-color); }
.badge-sale { background: rgba(48, 209, 88, 0.15); color: var(--green); }

/* MENSAJES FLASH */
.flash-msg { 
    padding: 12px; border-radius: 12px; margin-bottom: 16px; 
    font-weight: 600; font-size: 14px; text-align: center;
}
.flash-error { background: rgba(255, 59, 48, 0.1); color: var(--accent-color); border: 1px solid var(--accent-color); }
.flash-success { background: rgba(48, 209, 88, 0.1); color: var(--green); border: 1px solid var(--green); }

/* PERFIL */
.profile-header { display: flex; align-items: center; gap: 20px; margin-bottom: 24px; }
.profile-avatar { width: 80px; height: 80px; font-size: 32px; }
.profile-info h2 { margin-bottom: 4px; }
.danger-zone { border: 1px solid var(--accent-color); background: rgba(255, 59, 48, 0.05); }

/* RESPONSIVE */
@media (max-width: 600px) {
    .container { padding: 0 8px; }
    .post-content { font-size: 15px; }
    .nav-btn span { display: none; } /* Ocultar texto en móvil */
    .nav-btn { padding: 8px 12px; }
}
"""

# --- PLANTILLAS HTML ---

# Layout Base
BASE_LAYOUT = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MotosClub - Comunidad Racing</title>
    <style>{{ style }}</style>
</head>
<body>
    <nav class="navbar">
        <div class="nav-inner">
            <a href="/foro" class="nav-brand">🏍️ MotosClub</a>
            <div class="nav-links">
                <button onclick="toggleTheme()" class="theme-switch" id="theme-toggle">🌙</button>
                <a href="/foro" class="nav-btn {% if active=='foro' %}active{% endif %}"><span>Muro</span></a>
                <a href="/perfil" class="nav-btn {% if active=='perfil' %}active{% endif %}"><span>Perfil</span></a>
                <a href="/logout" class="nav-btn">Salir</a>
            </div>
        </div>
    </nav>

    <div class="container" style="padding-top: 20px;">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="flash-msg flash-{{ category }}">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        
        __CONTENT__
    </div>

    <script>
        // Lógica del Tema Oscuro/Claro
        function applyTheme(theme) {
            document.documentElement.setAttribute('data-theme', theme);
            localStorage.setItem('theme', theme);
            document.getElementById('theme-toggle').textContent = theme === 'light' ? '☀️' : '🌙';
        }
        
        function toggleTheme() {
            const current = localStorage.getItem('theme') || 'dark';
            const next = current === 'dark' ? 'light' : 'dark';
            applyTheme(next);
        }

        // Cargar tema guardado al iniciar
        (function() {
            const savedTheme = localStorage.getItem('theme') || 'dark';
            applyTheme(savedTheme);
        })();

        // Función simple para toggle de comentarios
        function toggleComments(id) {
            const el = document.getElementById('comments-' + id);
            if (el) el.style.display = el.style.display === 'none' ? 'block' : 'none';
        }
    </script>
</body>
</html>
"""

# Página de Login
LOGIN_PAGE = """
<div style="display: flex; justify-content: center; align-items: center; min-height: 80vh;">
    <div class="card" style="width: 100%; max-width: 420px;">
        <div style="text-align: center; margin-bottom: 30px;">
            <h1 style="font-size: 32px; margin-bottom: 8px;">Bienvenido</h1>
            <p style="color: var(--text-secondary);">Únete a la comunidad más rápida.</p>
        </div>
        <form method="POST">
            <input type="text" name="nombre" placeholder="Nombre de usuario" required autocomplete="off">
            <input type="password" name="password" placeholder="Contraseña" required>
            <button type="submit" name="login" class="btn-main">Iniciar Sesión</button>
            <button type="submit" name="register" class="btn-main" style="background: #333; margin-top: 8px;">Crear Cuenta</button>
        </form>
    </div>
</div>
"""

# Página del Muro
FEED_PAGE = """
<!-- Buscador -->
<form action="/buscar" method="GET" style="margin-bottom: 20px;">
    <input type="text" name="q" placeholder="🔍 Buscar rutas, motos, piezas..." style="margin-bottom: 0;">
</form>

<!-- Publicar -->
<div class="card">
    <form method="POST" action="/post">
        <textarea name="contenido" placeholder="¿Qué ruta vas a hacer hoy? (Pega enlaces de fotos si quieres)"></textarea>
        <div style="display: flex; gap: 10px; align-items: center;">
            <select name="categoria" style="width: auto; margin-bottom: 0;">
                <option value="General">General</option>
                <option value="Ruta">🛣️ Ruta</option>
                <option value="Mecanica">🔧 Mecánica</option>
                <option value="Venta">💰 Venta</option>
            </select>
            <button class="btn-main" style="width: 100%; margin-bottom: 0;">Publicar</button>
        </div>
    </form>
</div>

<!-- Lista de Posts -->
{% for p in posts %}
<div class="card" id="post-{{ p[0] }}">
    <div class="post-header">
        <div class="post-user">
            <div class="avatar" style="background: {{ p[6] }};">{{ p[1][0] }}</div>
            <div>
                <div style="font-weight: 700;">{{ p[1] }}</div>
                <div class="post-meta">
                    {{ p[5] }} &bull; 
                    {% if p[4] == 'Ruta' %}<span class="badge badge-route">Ruta</span>{% endif %}
                    {% if p[4] == 'Mecanica' %}<span class="badge badge-mech">Mecánica</span>{% endif %}
                    {% if p[4] == 'Venta' %}<span class="badge badge-sale">Venta</span>{% endif %}
                </div>
            </div>
        </div>
        
        {% if session.get('user_id') == p[7] %}
        <div style="display: flex; gap: 8px;">
            <button onclick="editPost({{ p[0] }})" class="btn-sec">✏️</button>
            <form action="/delete/{{ p[0] }}" method="POST" onsubmit="return confirm('¿Seguro que quieres borrar esta publicación?');">
                <button class="btn-sec">🗑️</button>
            </form>
        </div>
        {% endif %}
    </div>

    <div class="post-content">{{ p[3] | safe }}</div>

    <div class="post-actions">
        <form action="/like/{{ p[0] }}" method="POST" style="display:inline;">
            <button type="submit" class="action-btn {% if p[11] %}active{% endif %}">⛽ Gas <b>{{ p[8] }}</b></button>
        </form>
        <button onclick="toggleComments({{ p[0] }})" class="action-btn">💬 {{ p[9] }}</button>
    </div>

    <!-- Sección Comentarios -->
    <div id="comments-{{ p[0] }}" class="comments-section" style="display:none;">
        <div class="comment-box">
            <form action="/comment/{{ p[0] }}" method="POST" style="width:100%; display:flex; gap:10px;">
                <input type="text" name="contenido" placeholder="Escribe una respuesta..." required style="margin-bottom:0; flex:1;">
                <button class="btn-sec">Enviar</button>
            </form>
        </div>
        {% for c in p[10] %}
        <div class="comment-card">
            <span style="color: {{ c[3] }}; font-weight:700;">{{ c[0] }}</span>
            <span class="comment-text">{{ c[1] }}</span>
            <div style="font-size:11px; color:var(--text-secondary); margin-top:4px;">{{ c[2] }}</div>
        </div>
        {% endfor %}
    </div>
</div>
{% endfor %}

<script>
function editPost(id) {
    // En una app real esto abriría un modal, aquí usamos prompt simple para simplicidad
    const newTxt = prompt("Editar publicación:");
    if(newTxt) window.location.href = "/edit/" + id + "?txt=" + encodeURIComponent(newTxt);
}
</script>
"""

# Página de Perfil
PROFILE_PAGE = """
<div class="card">
    <div class="profile-header">
        <div class="avatar profile-avatar" style="background: var(--accent-color);">{{ session.get('user_name')[0] }}</div>
        <div class="profile-info">
            <h2>@{{ session.get('user_name') }}</h2>
            <p style="color: var(--text-secondary);">{{ session.get('moto', 'Motero sin moto') }}</p>
        </div>
    </div>
    
    <h3 style="margin-bottom: 10px; font-size: 16px;">Editar Perfil</h3>
    <form method="POST" action="/perfil">
        <input type="text" name="moto" placeholder="Tu moto actual (ej: Yamaha MT-07)" value="{{ session.get('moto', '') }}">
        <textarea name="bio" placeholder="Cuéntanos un poco sobre ti...">{{ session.get('bio', '') }}</textarea>
        <button class="btn-main" style="margin-bottom: 0;">Guardar Cambios</button>
    </form>
</div>

<div class="card danger-zone">
    <h3 style="color: var(--accent-color); margin-bottom: 10px;">Zona de Peligro</h3>
    <p style="font-size: 14px; margin-bottom: 15px;">Una vez borres tu cuenta, no hay vuelta atrás. Se eliminarán todos tus datos.</p>
    <form action="/delete_account" method="POST" onsubmit="return confirm('¿ESTÁS TOTALMENTE SEGURO? Se borrará tu usuario y todos tus posts.');">
        <button class="btn-main" style="background: transparent; border: 1px solid var(--accent-color); color: var(--accent-color);">Borrar Mi Cuenta Definitivamente</button>
    </form>
</div>
"""

# --- RUTAS DE LA APLICACIÓN ---

@app.route('/', methods=['GET', 'POST'])
def login():
    # Si ya está logueado, ir al muro
    if 'user_id' in session:
        return redirect('/foro')
    
    if request.method == 'POST':
        nombre = request.form['nombre'].strip()
        password = request.form['password']
        conn = get_db_connection()
        cur = conn.cursor()

        if 'register' in request.form:
            # Lógica de registro
            if len(nombre) < 3:
                flash("El nombre debe tener al menos 3 caracteres.", "error")
            elif len(password) < 4:
                flash("La contraseña es muy corta.", "error")
            else:
                try:
                    hash_p = generate_password_hash(password)
                    cur.execute("INSERT INTO usuarios (nombre, password) VALUES (%s, %s)", (nombre, hash_p))
                    conn.commit()
                    flash("¡Cuenta creada! Ahora inicia sesión.", "success")
                except:
                    flash("Ese nombre de usuario ya existe.", "error")
        
        elif 'login' in request.form:
            # Lógica de login
            cur.execute("SELECT id, password, bio, moto FROM usuarios WHERE nombre = %s", (nombre,))
            user = cur.fetchone()
            if user and check_password_hash(user[1], password):
                # Guardar en sesión
                session['user_id'] = user[0]
                session['user_name'] = nombre
                session['bio'] = user[2] or ''
                session['moto'] = user[3] or ''
                cur.close(); conn.close()
                return redirect('/foro')
            else:
                flash("Usuario o contraseña incorrectos.", "error")
        
        cur.close(); conn.close()

    # Renderizar login
    page = BASE_LAYOUT.replace("__CONTENT__", LOGIN_PAGE)
    return render_template_string(page, style=STYLE)

@app.route('/foro')
@login_required
def foro():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Query principal: Posts + Info Usuario + Conteos
    # p[10] indicará si el usuario actual dio like
    cur.execute("""
        SELECT p.id, u.nombre, p.contenido, p.fecha, p.categoria, u.moto, u.nombre, p.usuario_id,
               (SELECT COUNT(*) FROM likes l WHERE l.post_id = p.id),
               (SELECT COUNT(*) FROM comentarios c WHERE c.post_id = p.id)
        FROM posts p JOIN usuarios u ON p.usuario_id = u.id
        ORDER BY p.fecha DESC
        LIMIT 50
    """)
    raw_posts = cur.fetchall()
    
    posts = []
    for p in raw_posts:
        # Verificar si el usuario actual dio like a este post
        cur.execute("SELECT 1 FROM likes WHERE post_id = %s AND usuario_id = %s", (p[0], session['user_id']))
        liked = cur.fetchone() is not None
        
        # Obtener comentarios
        cur.execute("""
            SELECT u.nombre, c.contenido, c.fecha 
            FROM comentarios c JOIN usuarios u ON c.usuario_id = u.id 
            WHERE c.post_id = %s ORDER BY c.fecha ASC LIMIT 10
        """, (p[0],))
        raw_c = cur.fetchall()
        
        # Formatear comentarios
        comments = []
        for c in raw_c:
            comments.append((c[0], c[1], time_ago(c[2]), string_to_color(c[0])))
            
        # Formatear post
        # Estructura tuple: (id, autor, raw_contenido, safe_contenido, categoria, fecha_str, color, autor_id, likes, num_comments, comments_list, liked_by_me)
        safe_content = url_to_image(p[2])
        posts.append((p[0], p[1], p[2], safe_content, p[4], time_ago(p[3]), string_to_color(p[1]), p[7], p[8], p[9], comments, liked))

    cur.close(); conn.close()
    
    page = BASE_LAYOUT.replace("__CONTENT__", FEED_PAGE)
    return render_template_string(page, style=STYLE, posts=posts, active='foro')

@app.route('/post', methods=['POST'])
@login_required
def post():
    txt = request.form['contenido'].strip()
    cat = request.form.get('categoria', 'General')
    
    if len(txt) > 0:
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("INSERT INTO posts (usuario_id, contenido, categoria) VALUES (%s, %s, %s)", (session['user_id'], txt, cat))
        conn.commit(); cur.close(); conn.close()
        flash("¡Publicación creada!", "success")
    else:
        flash("No puedes publicar algo vacío.", "error")
        
    return redirect('/foro')

@app.route('/delete/<int:pid>', methods=['POST'])
@login_required
def delete_post(pid):
    conn = get_db_connection(); cur = conn.cursor()
    # Verificar propiedad
    cur.execute("SELECT usuario_id FROM posts WHERE id = %s", (pid,))
    post = cur.fetchone()
    
    if post and post[0] == session['user_id']:
        # PostgreSQL elimina en cascada gracias a ON DELETE CASCADE en las tablas likes/comentarios
        cur.execute("DELETE FROM posts WHERE id = %s", (pid,))
        conn.commit()
        flash("Publicación eliminada.", "success")
    else:
        flash("No tienes permiso para hacer eso.", "error")
        
    cur.close(); conn.close()
    return redirect('/foro')

@app.route('/edit/<int:pid>')
@login_required
def edit_post(pid):
    txt = request.args.get('txt')
    if not txt: return redirect('/foro')
    
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("SELECT usuario_id FROM posts WHERE id = %s", (pid,))
    post = cur.fetchone()
    
    if post and post[0] == session['user_id']:
        cur.execute("UPDATE posts SET contenido = %s WHERE id = %s", (txt, pid))
        conn.commit()
        flash("Publicación editada.", "success")
    
    cur.close(); conn.close()
    return redirect('/foro')

@app.route('/like/<int:pid>', methods=['POST'])
@login_required
def like_post(pid):
    conn = get_db_connection(); cur = conn.cursor()
    try:
        # Intentar insertar like
        cur.execute("INSERT INTO likes (usuario_id, post_id) VALUES (%s, %s)", (session['user_id'], pid))
        conn.commit()
    except:
        # Si ya existe (PK violation), eliminar like
        conn.rollback() # Importante hacer rollback del error
        cur.execute("DELETE FROM likes WHERE usuario_id = %s AND post_id = %s", (session['user_id'], pid))
        conn.commit()
    cur.close(); conn.close()
    return redirect('/foro')

@app.route('/comment/<int:pid>', methods=['POST'])
@login_required
def add_comment(pid):
    txt = request.form['contenido'].strip()
    if len(txt) > 0:
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("INSERT INTO comentarios (post_id, usuario_id, contenido) VALUES (%s, %s, %s)", (pid, session['user_id'], txt))
        conn.commit(); cur.close(); conn.close()
    return redirect('/foro')

@app.route('/buscar')
@login_required
def search():
    query = request.args.get('q', '')
    if not query: return redirect('/foro')
    
    conn = get_db_connection(); cur = conn.cursor()
    # Búsqueda case-insensitive (ILIKE)
    cur.execute("""
        SELECT p.id, u.nombre, p.contenido, p.fecha, p.categoria, u.moto, u.nombre, p.usuario_id
        FROM posts p JOIN usuarios u ON p.usuario_id = u.id
        WHERE p.contenido ILIKE %s
        ORDER BY p.fecha DESC
    """, (f'%{query}%',))
    
    raw_posts = cur.fetchall()
    
    # Reutilizamos la lógica de formateo simplificada para búsqueda
    posts = []
    for p in raw_posts:
         # Estructura simplificada para búsqueda (sin comentarios cargados para ahorrar recursos)
         posts.append((p[0], p[1], p[2], url_to_image(p[2]), p[4], time_ago(p[3]), string_to_color(p[1]), p[7], 0, 0, [], False))
         
    cur.close(); conn.close()
    
    flash(f"Mostrando resultados para: '{query}'", "success")
    page = BASE_LAYOUT.replace("__CONTENT__", FEED_PAGE)
    return render_template_string(page, style=STYLE, posts=posts, active='foro')

@app.route('/perfil', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        bio = request.form['bio']
        moto = request.form['moto']
        
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("UPDATE usuarios SET bio = %s, moto = %s WHERE id = %s", (bio, moto, session['user_id']))
        conn.commit(); cur.close(); conn.close()
        
        session['bio'] = bio
        session['moto'] = moto
        flash("Perfil actualizado correctamente.", "success")
        
    page = BASE_LAYOUT.replace("__CONTENT__", PROFILE_PAGE)
    return render_template_string(page, style=STYLE, active='perfil')

@app.route('/delete_account', methods=['POST'])
@login_required
def delete_account():
    user_id = session['user_id']
    
    # Cerrar sesión primero
    session.clear()
    
    conn = get_db_connection(); cur = conn.cursor()
    
    # Borrar datos relacionados (por si acaso no funciona ON DELETE CASCADE)
    cur.execute("DELETE FROM likes WHERE usuario_id = %s", (user_id,))
    cur.execute("DELETE FROM comentarios WHERE usuario_id = %s", (user_id,))
    cur.execute("DELETE FROM posts WHERE usuario_id = %s", (user_id,))
    
    # Borrar usuario
    cur.execute("DELETE FROM usuarios WHERE id = %s", (user_id,))
    conn.commit(); cur.close(); conn.close()
    
    flash("Tu cuenta ha sido eliminada definitivamente.", "success")
    return redirect('/')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000)
