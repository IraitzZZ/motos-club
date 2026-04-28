# =============================================================================
# MOTOSCLUB - Red Social para Moteros (Versión Profesional)
# Deploy-ready para Render.com
# =============================================================================
import os
import re
import html
import psycopg2
from flask import Flask, request, redirect, render_template_string, session, flash, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from functools import wraps
from flask_wtf.csrf import CSRFProtect

# -----------------------------------------------------------------------------
# CONFIGURACIÓN GLOBAL
# -----------------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))
app.config['WTF_CSRF_ENABLED'] = True
csrf = CSRFProtect(app)

DATABASE_URL = os.environ.get('DATABASE_URL')

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

    cur.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id SERIAL PRIMARY KEY,
            nombre TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            email TEXT DEFAULT '',
            bio TEXT DEFAULT '',
            moto TEXT DEFAULT '',
            avatar_color TEXT DEFAULT '',
            racha INTEGER DEFAULT 0,
            ultima_actividad DATE,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

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

    cur.execute("""
        CREATE TABLE IF NOT EXISTS seguidores (
            seguidor_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
            seguido_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (seguidor_id, seguido_id),
            CHECK (seguidor_id != seguido_id)
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS likes (
            usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
            post_id INTEGER REFERENCES posts(id) ON DELETE CASCADE,
            PRIMARY KEY (usuario_id, post_id)
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS comentarios (
            id SERIAL PRIMARY KEY,
            post_id INTEGER REFERENCES posts(id) ON DELETE CASCADE,
            usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
            contenido TEXT NOT NULL,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS notificaciones (
            id SERIAL PRIMARY KEY,
            usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
            tipo TEXT NOT NULL,
            mensaje TEXT NOT NULL,
            url TEXT,
            leido BOOLEAN DEFAULT FALSE,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS bookmarks (
            usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
            post_id INTEGER REFERENCES posts(id) ON DELETE CASCADE,
            PRIMARY KEY (usuario_id, post_id)
        );
    """)

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
            flash("Inicia sesión para continuar", "error")
            return redirect('/')
        return f(*args, **kwargs)
    return decorated_function


def procesar_texto(text):
    """Convierte @menciones, #hashtags y URLs de imagen en HTML seguro."""
    text = html.escape(text)
    
    # Imágenes: solo URLs que terminen en extensión de imagen
    pattern_img = r'(https?://[^\s]+?\.(png|jpg|jpeg|gif|webp)(\?[^\s]*)?)'
    text = re.sub(pattern_img, r'<img src="\1" class="post-image" loading="lazy" alt="Imagen">', text)
    
    # Menciones @usuario
    text = re.sub(r'@(\w+)', r'<a href="/perfil/\1" class="mention">@\1</a>', text)
    
    # Hashtags #tema
    text = re.sub(r'#(\w+)', r'<a href="/buscar?tag=\1" class="hashtag">#\1</a>', text)
    
    return text


def string_to_color(s):
    """Genera color HSL único y accesible desde string."""
    h = sum(ord(c) for c in s) % 360
    return f"hsl({h}, 70%, 50%)"


def time_ago(dt):
    """Convierte timestamp a formato relativo legible."""
    if not dt:
        return "hace poco"
    delta = datetime.now() - dt if isinstance(dt, datetime) else datetime.now() - datetime.now()
    if delta.days > 365:
        return f"hace {delta.days // 365}a"
    if delta.days > 0:
        return f"hace {delta.days}d"
    if delta.seconds >= 3600:
        return f"hace {delta.seconds // 3600}h"
    if delta.seconds >= 60:
        return f"hace {delta.seconds // 60}m"
    return "ahora"


def crear_notificacion(user_id, tipo, mensaje, url=None):
    """Crea una notificación para un usuario de forma segura."""
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
    except Exception:
        pass  # Fail silently in production


def get_notif_count(user_id):
    """Obtiene el número de notificaciones no leídas."""
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


# -----------------------------------------------------------------------------
# ESTILOS CSS - PROFESIONAL Y RESPONSIVE
# -----------------------------------------------------------------------------
STYLE = """
/* Fuentes del sistema con fallbacks - sin dependencias externas */
:root {
    --font-stack: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    
    /* Tema oscuro por defecto */
    --bg: #0a0a0a;
    --bg-elev: #161618;
    --surface: #1c1c1e;
    --surface-hover: #2a2a2c;
    --text: #f5f5f7;
    --text-dim: #aeaeb2;
    --border: #3a3a3c;
    --accent: #ff453a;
    --accent-hover: #ff6055;
    --blue: #0a84ff;
    --green: #30d158;
    --warning: #ff9f0a;
    --shadow: 0 4px 20px rgba(0,0,0,0.4);
    --radius: 14px;
    --radius-sm: 10px;
    --transition: 180ms ease;
}

/* Tema claro */
[data-theme="light"] {
    --bg: #f5f5f7;
    --bg-elev: #ffffff;
    --surface: #ffffff;
    --surface-hover: #f0f0f2;
    --text: #1d1d1f;
    --text-dim: #6e6e73;
    --border: #d2d2d7;
    --shadow: 0 4px 20px rgba(0,0,0,0.08);
}

/* Reset y base */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html { scroll-behavior: smooth; }
body {
    font-family: var(--font-stack);
    background: var(--bg);
    color: var(--text);
    line-height: 1.5;
    font-size: 15px;
    -webkit-font-smoothing: antialiased;
    transition: background var(--transition), color var(--transition);
}

/* Tipografía */
h1, h2, h3, .title { 
    font-weight: 700; 
    line-height: 1.2; 
    letter-spacing: -0.02em;
}
h1 { font-size: clamp(24px, 5vw, 32px); }
h2 { font-size: clamp(20px, 4vw, 24px); }
h3 { font-size: clamp(16px, 3vw, 18px); }
p { margin-bottom: 12px; }
a { color: var(--blue); text-decoration: none; transition: opacity var(--transition); }
a:hover { opacity: 0.85; }

/* Layout */
.container { 
    max-width: 680px; 
    margin: 0 auto; 
    padding: 0 16px; 
    padding-top: env(safe-area-inset-top);
}

/* Navbar */
.navbar {
    position: sticky;
    top: 0;
    z-index: 100;
    background: rgba(22, 22, 24, 0.85);
    backdrop-filter: saturate(180%) blur(20px);
    border-bottom: 1px solid var(--border);
    padding: 10px 0;
    transition: background var(--transition), border-color var(--transition);
}
[data-theme="light"] .navbar { background: rgba(255, 255, 255, 0.85); }

.nav-inner {
    display: flex;
    align-items: center;
    justify-content: space-between;
    max-width: 680px;
    margin: 0 auto;
    padding: 0 16px;
}

.nav-brand {
    font-weight: 800;
    font-size: 20px;
    color: var(--text);
    display: flex;
    align-items: center;
    gap: 6px;
}

.nav-actions {
    display: flex;
    align-items: center;
    gap: 4px;
}

.nav-btn, .icon-btn {
    background: transparent;
    border: none;
    color: var(--text);
    padding: 8px 12px;
    border-radius: 10px;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 6px;
    transition: background var(--transition);
}
.nav-btn:hover, .icon-btn:hover { background: var(--surface-hover); }
.nav-btn.active { background: var(--accent); color: white; }

.icon-btn {
    width: 38px;
    height: 38px;
    padding: 0;
    justify-content: center;
    font-size: 18px;
    position: relative;
}

.badge {
    position: absolute;
    top: 2px;
    right: 2px;
    background: var(--accent);
    color: white;
    font-size: 10px;
    font-weight: 700;
    min-width: 18px;
    height: 18px;
    border-radius: 9px;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0 4px;
}

/* Cards */
.card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 16px;
    margin-bottom: 12px;
    transition: background var(--transition), border-color var(--transition);
}
.card:hover { border-color: var(--text-dim); }

/* Formularios */
input, textarea, select {
    width: 100%;
    background: var(--bg-elev);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    color: var(--text);
    padding: 12px 14px;
    font-size: 15px;
    font-family: inherit;
    outline: none;
    transition: border-color var(--transition), box-shadow var(--transition);
}
input:focus, textarea:focus, select:focus {
    border-color: var(--accent);
    box-shadow: 0 0 0 3px rgba(255, 69, 58, 0.15);
}
input::placeholder, textarea::placeholder { color: var(--text-dim); }
textarea { resize: vertical; min-height: 100px; }

/* Botones */
.btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    padding: 12px 20px;
    border-radius: var(--radius-sm);
    font-weight: 600;
    font-size: 14px;
    cursor: pointer;
    border: none;
    transition: transform var(--transition), background var(--transition);
    text-align: center;
}
.btn:active { transform: scale(0.98); }
.btn-primary { background: var(--accent); color: white; width: 100%; }
.btn-primary:hover { background: var(--accent-hover); }
.btn-secondary { background: var(--surface-hover); color: var(--text); }
.btn-secondary:hover { background: var(--border); }
.btn-ghost { background: transparent; color: var(--text-dim); padding: 6px 10px; }
.btn-ghost:hover { color: var(--text); background: var(--surface-hover); }
.btn-sm { padding: 6px 12px; font-size: 13px; border-radius: 8px; }

/* Avatar */
.avatar {
    width: 40px;
    height: 40px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 600;
    font-size: 16px;
    color: white;
    flex-shrink: 0;
    text-transform: uppercase;
}
.avatar-lg { width: 72px; height: 72px; font-size: 28px; }

/* Post */
.post { position: relative; }
.post-header {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    margin-bottom: 10px;
}
.post-author {
    display: flex;
    flex-direction: column;
    gap: 2px;
}
.post-author-name {
    font-weight: 600;
    color: var(--text);
    font-size: 15px;
}
.post-author-name:hover { text-decoration: underline; }
.post-meta {
    font-size: 13px;
    color: var(--text-dim);
    display: flex;
    align-items: center;
    gap: 4px;
}
.post-category {
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 6px;
    background: var(--surface-hover);
    color: var(--text-dim);
    font-weight: 500;
}
.post-content {
    font-size: 15px;
    line-height: 1.5;
    white-space: pre-wrap;
    word-break: break-word;
    margin: 8px 0 12px;
}
.post-content a.mention,
.post-content a.hashtag {
    color: var(--blue);
    font-weight: 500;
}
.post-image {
    width: 100%;
    border-radius: var(--radius-sm);
    margin: 8px 0;
    border: 1px solid var(--border);
    display: block;
    max-height: 500px;
    object-fit: cover;
}

/* Acciones del post */
.post-actions {
    display: flex;
    align-items: center;
    gap: 4px;
    padding-top: 10px;
    border-top: 1px solid var(--border);
}
.action-btn {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 8px 12px;
    border-radius: 8px;
    background: transparent;
    border: none;
    color: var(--text-dim);
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: background var(--transition), color var(--transition);
}
.action-btn:hover { background: var(--surface-hover); color: var(--text); }
.action-btn.active { color: var(--accent); }
.action-btn .count { font-weight: 600; }

/* Comentarios */
.comments-toggle { margin-top: 8px; }
.comments {
    margin-top: 12px;
    padding-top: 12px;
    border-top: 1px solid var(--border);
    display: none;
}
.comments.show { display: block; }
.comment-form {
    display: flex;
    gap: 8px;
    margin-bottom: 12px;
}
.comment-form input {
    margin: 0;
    flex: 1;
    padding: 10px 12px;
    font-size: 14px;
}
.comment {
    background: var(--bg-elev);
    border-radius: var(--radius-sm);
    padding: 10px 12px;
    margin-bottom: 8px;
    font-size: 14px;
}
.comment-author { font-weight: 600; margin-right: 4px; }
.comment-time { color: var(--text-dim); font-size: 12px; margin-left: 4px; }

/* Perfil */
.profile-banner {
    height: 120px;
    background: linear-gradient(135deg, var(--accent), var(--blue));
    border-radius: var(--radius) var(--radius) 0 0;
    margin: -16px -16px 0;
    position: relative;
}
.profile-header {
    display: flex;
    align-items: center;
    gap: 14px;
    padding-top: 36px;
    margin-bottom: 16px;
}
.profile-info { flex: 1; min-width: 0; }
.profile-name {
    font-size: 20px;
    font-weight: 700;
    margin-bottom: 4px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.profile-moto { color: var(--text-dim); font-size: 14px; }
.profile-bio { 
    margin: 12px 0; 
    font-size: 14px; 
    line-height: 1.4;
    white-space: pre-wrap;
}
.profile-stats {
    display: flex;
    gap: 20px;
    padding: 12px 0;
    border-top: 1px solid var(--border);
    margin-top: 12px;
}
.stat { text-align: center; }
.stat-val { font-weight: 700; font-size: 16px; display: block; }
.stat-label { font-size: 12px; color: var(--text-dim); }

/* Login / Registro */
.auth-container {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: calc(100vh - 100px);
    padding: 20px;
}
.auth-card {
    width: 100%;
    max-width: 400px;
    text-align: center;
}
.auth-logo {
    font-size: 32px;
    font-weight: 800;
    margin-bottom: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
}
.auth-subtitle {
    color: var(--text-dim);
    margin-bottom: 24px;
    font-size: 14px;
}
.auth-form { display: flex; flex-direction: column; gap: 12px; }
.auth-switch {
    margin-top: 16px;
    font-size: 14px;
    color: var(--text-dim);
}
.auth-switch button {
    background: none;
    border: none;
    color: var(--blue);
    font-weight: 500;
    cursor: pointer;
    padding: 0;
    font-size: inherit;
}

/* Flash messages */
.flash {
    padding: 12px 16px;
    border-radius: var(--radius-sm);
    margin-bottom: 12px;
    font-size: 14px;
    font-weight: 500;
    animation: slideIn 200ms ease;
}
@keyframes slideIn {
    from { opacity: 0; transform: translateY(-10px); }
    to { opacity: 1; transform: translateY(0); }
}
.flash-error {
    background: rgba(255, 69, 58, 0.12);
    color: #ff6b61;
    border: 1px solid rgba(255, 69, 58, 0.3);
}
.flash-success {
    background: rgba(48, 209, 88, 0.12);
    color: #4fd676;
    border: 1px solid rgba(48, 209, 88, 0.3);
}

/* Notificaciones */
.notif-list { display: flex; flex-direction: column; gap: 8px; }
.notif-item {
    display: flex;
    gap: 10px;
    padding: 12px;
    border-radius: var(--radius-sm);
    background: var(--bg-elev);
    transition: background var(--transition);
}
.notif-item.unread { background: rgba(10, 132, 255, 0.08); border-left: 3px solid var(--blue); }
.notif-item:hover { background: var(--surface-hover); }
.notif-icon { font-size: 18px; margin-top: 2px; }
.notif-content { flex: 1; min-width: 0; }
.notif-msg { font-size: 14px; margin-bottom: 4px; }
.notif-time { font-size: 12px; color: var(--text-dim); }

/* Footer */
.footer {
    text-align: center;
    padding: 30px 16px 60px;
    color: var(--text-dim);
    font-size: 13px;
}
.footer a { color: var(--text-dim); }

/* Utilidades */
.hidden { display: none !important; }
.text-center { text-align: center; }
.mt-1 { margin-top: 8px; }
.mt-2 { margin-top: 16px; }
.mb-1 { margin-bottom: 8px; }
.mb-2 { margin-bottom: 16px; }
.flex { display: flex; }
.flex-col { flex-direction: column; }
.items-center { align-items: center; }
.justify-between { justify-content: space-between; }
.gap-1 { gap: 8px; }
.gap-2 { gap: 12px; }
.w-full { width: 100%; }

/* Responsive */
@media (max-width: 480px) {
    .container { padding: 0 12px; }
    .nav-btn span { display: none; }
    .profile-stats { gap: 14px; }
    .stat-val { font-size: 14px; }
    .stat-label { font-size: 11px; }
    .btn { padding: 11px 18px; font-size: 14px; }
    .action-btn { padding: 7px 10px; font-size: 13px; }
}

/* Accesibilidad */
@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.01ms !important;
    }
    html { scroll-behavior: auto; }
}

/* Focus visible para navegación con teclado */
:focus-visible {
    outline: 2px solid var(--blue);
    outline-offset: 2px;
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
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
    <meta name="theme-color" content="#0a0a0a" media="(prefers-color-scheme: dark)">
    <meta name="theme-color" content="#f5f5f7" media="(prefers-color-scheme: light)">
    <title>MOTOSCLUB</title>
    <style>{{ style|safe }}</style>
</head>
<body>
    <nav class="navbar">
        <div class="nav-inner">
            <a href="/foro" class="nav-brand">🏍️ MOTOSCLUB</a>
            <div class="nav-actions">
                <button class="icon-btn" id="themeToggle" aria-label="Cambiar tema">🌙</button>
                <a href="/buscar" class="icon-btn" aria-label="Buscar">🔍</a>
                <a href="/notificaciones" class="icon-btn" aria-label="Notificaciones">
                    🔔
                    {% if notif_count > 0 %}<span class="badge">{{ notif_count }}</span>{% endif %}
                </a>
                <a href="/perfil" class="nav-btn{% if active=='perfil' %} active{% endif %}"><span>Yo</span></a>
                <a href="/logout" class="nav-btn"><span>Salir</span></a>
            </div>
        </div>
    </nav>

    <main class="container" style="padding-top: 16px;">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="flash flash-{{ category }}">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        {{ content|safe }}
    </main>

    <footer class="footer">
        <p>🏍️ MOTOSCLUB &copy; {{ year }} • <a href="#">Privacidad</a> • <a href="#">Términos</a></p>
    </footer>

    <script>
        // Tema oscuro/claro con persistencia
        (function() {
            const root = document.documentElement;
            const toggle = document.getElementById('themeToggle');
            const saved = localStorage.getItem('theme');
            const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
            
            function apply(theme) {
                root.setAttribute('data-theme', theme);
                localStorage.setItem('theme', theme);
                toggle.textContent = theme === 'light' ? '☀️' : '🌙';
                // Actualizar meta theme-color
                const meta = document.querySelector('meta[name="theme-color"]');
                if (meta) {
                    meta.setAttribute('content', theme === 'light' ? '#f5f5f7' : '#0a0a0a');
                }
            }
            
            apply(saved || (prefersDark ? 'dark' : 'light'));
            toggle.addEventListener('click', () => {
                const current = root.getAttribute('data-theme');
                apply(current === 'light' ? 'dark' : 'light');
            });
        })();

        // Toggle comentarios
        function toggleComments(postId) {
            const el = document.getElementById('comments-' + postId);
            const btn = document.getElementById('toggle-' + postId);
            if (el && btn) {
                const showing = el.classList.toggle('show');
                btn.innerHTML = showing ? '▲ Ocultar' : '💬 ' + btn.dataset.count;
            }
        }

        // Confirmación antes de borrar
        function confirmDelete(e) {
            if (!confirm('¿Estás seguro? Esta acción no se puede deshacer.')) {
                e.preventDefault();
            }
        }
    </script>
</body>
</html>
"""


def render_page(content, active='', notif_count=0):
    """Renderiza una página con el layout base."""
    return render_template_string(
        BASE_LAYOUT,
        style=STYLE,
        content=content,
        active=active,
        notif_count=notif_count,
        year=datetime.now().year
    )


# -----------------------------------------------------------------------------
# RUTAS: AUTH
# -----------------------------------------------------------------------------
@app.route('/', methods=['GET', 'POST'])
def login_register():
    if 'user_id' in session:
        return redirect('/foro')
    
    is_login = request.args.get('register') != '1'
    
    auth_html = f"""
    <div class="auth-container">
        <div class="card auth-card">
            <div class="auth-logo">🏍️ MOTOSCLUB</div>
            <p class="auth-subtitle">{"Conecta con moteros de verdad" if is_login else "Únete a la comunidad"}</p>
            
            <form method="POST" class="auth-form" id="authForm">
                <input type="text" name="nombre" placeholder="Nombre de usuario" 
                       required minlength="3" maxlength="30" pattern="[a-zA-Z0-9_]+" 
                       autocomplete="username" aria-label="Nombre de usuario">
                
                <div style="position: relative;">
                    <input type="password" name="password" placeholder="Contraseña" 
                           required minlength="6" autocomplete="{'current-password' if is_login else 'new-password'}" 
                           aria-label="Contraseña" id="passwordInput">
                    <button type="button" class="btn-ghost" 
                            style="position: absolute; right: 4px; top: 50%; transform: translateY(-50%);"
                            onclick="togglePassword()" aria-label="Mostrar contraseña">👁️</button>
                </div>
                
                {"<label style='display:flex; align-items:center; gap:6px; font-size:13px; color:var(--text-dim);'><input type='checkbox' required> Acepto los <a href='#' style='color:var(--blue);'>Términos</a></label>" if not is_login else ""}
                
                <button type="submit" name="action" value="{"login" if is_login else "register"}" 
                        class="btn btn-primary">{"ENTRAR" if is_login else "CREAR CUENTA"}</button>
            </form>
            
            <p class="auth-switch">
                {"¿No tienes cuenta?" if is_login else "¿Ya tienes cuenta?"}
                <button type="button" onclick="window.location.href='/?{"register=1" if is_login else ""}'">
                    {"Regístrate" if is_login else "Inicia sesión"}
                </button>
            </p>
        </div>
    </div>
    
    <script>
    function togglePassword() {{
        const input = document.getElementById('passwordInput');
        input.type = input.type === 'password' ? 'text' : 'password';
    }}
    // Validación en tiempo real del nombre de usuario
    document.querySelector('input[name="nombre"]').addEventListener('input', function(e) {{
        this.value = this.value.replace(/[^a-zA-Z0-9_]/g, '');
    }});
    </script>
    """
    
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        password = request.form.get('password', '')
        action = request.form.get('action')
        
        # Validaciones básicas
        if len(nombre) < 3:
            flash("El nombre debe tener al menos 3 caracteres", "error")
        elif len(password) < 6:
            flash("La contraseña debe tener al menos 6 caracteres", "error")
        elif not re.match(r'^[a-zA-Z0-9_]+$', nombre):
            flash("Solo letras, números y guiones bajos", "error")
        else:
            conn = get_db_connection()
            cur = conn.cursor()
            
            if action == 'register':
                try:
                    hashed = generate_password_hash(password)
                    color = string_to_color(nombre)
                    cur.execute(
                        "INSERT INTO usuarios (nombre, password, avatar_color) VALUES (%s, %s, %s)",
                        (nombre, hashed, color)
                    )
                    conn.commit()
                    flash("¡Cuenta creada! Ahora puedes entrar", "success")
                    is_login = True
                except psycopg2.IntegrityError:
                    flash("Ese nombre ya está en uso", "error")
                    conn.rollback()
                finally:
                    cur.close()
                    conn.close()
                    
            elif action == 'login':
                cur.execute(
                    "SELECT id, password, avatar_color, bio, moto, racha FROM usuarios WHERE nombre = %s",
                    (nombre,)
                )
                user = cur.fetchone()
                cur.close()
                conn.close()
                
                if user and check_password_hash(user[1], password):
                    session['user_id'] = user[0]
                    session['user_name'] = nombre
                    session['avatar_color'] = user[2]
                    session['bio'] = user[3] or ''
                    session['moto'] = user[4] or ''
                    session['racha'] = user[5] or 0
                    return redirect('/foro')
                else:
                    flash("Nombre o contraseña incorrectos", "error")
    
    return render_page(auth_html, notif_count=0)


# -----------------------------------------------------------------------------
# RUTAS: FORO / FEED
# -----------------------------------------------------------------------------
@app.route('/foro')
@login_required
def foro():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Usuarios que sigo + yo
    cur.execute("SELECT seguido_id FROM seguidores WHERE seguidor_id = %s", (session['user_id'],))
    following = [row[0] for row in cur.fetchall()] + [session['user_id']]
    
    # Posts con datos esenciales
    cur.execute("""
        SELECT p.id, u.nombre, u.avatar_color, p.contenido, p.imagen_url, 
               p.categoria, p.fecha, p.usuario_id,
               (SELECT COUNT(*) FROM likes WHERE post_id = p.id),
               (SELECT COUNT(*) FROM comentarios WHERE post_id = p.id),
               EXISTS(SELECT 1 FROM likes WHERE post_id = p.id AND usuario_id = %s),
               EXISTS(SELECT 1 FROM bookmarks WHERE post_id = p.id AND usuario_id = %s)
        FROM posts p
        JOIN usuarios u ON p.usuario_id = u.id
        WHERE p.usuario_id = ANY(%s) AND p.reportes < 5
        ORDER BY p.fecha DESC
        LIMIT 30
    """, (session['user_id'], session['user_id'], following))
    
    posts = []
    for row in cur.fetchall():
        pid, autor, color, contenido, img_url, cat, fecha, uid, likes, comments, liked, bookmarked = row
        
        # Comentarios recientes
        cur.execute("""
            SELECT u.nombre, u.avatar_color, c.contenido, c.fecha
            FROM comentarios c
            JOIN usuarios u ON c.usuario_id = u.id
            WHERE c.post_id = %s
            ORDER BY c.fecha ASC
            LIMIT 3
        """, (pid,))
        coms = [(n, col, txt, time_ago(fecha)) for n, col, txt, fecha in cur.fetchall()]
        
        posts.append({
            'id': pid, 'autor': autor, 'color': color,
            'contenido': procesar_texto(contenido), 'imagen': img_url,
            'categoria': cat, 'fecha': time_ago(fecha), 'uid': uid,
            'likes': likes, 'comments': comments, 'liked': liked,
            'bookmarked': bookmarked, 'comentarios': coms
        })
    
    cur.close()
    conn.close()
    
    # Formulario de publicación
    form_html = """
    <div class="card">
        <form method="POST" action="/post" enctype="multipart/form-data">
            <textarea name="contenido" placeholder="¿Qué ruta haces hoy? Usa @menciones y #hashtags" 
                      required maxlength="500"></textarea>
            
            <div class="flex items-center gap-1 mb-1" style="flex-wrap: wrap;">
                <select name="categoria" style="width: auto; margin: 0;">
                    <option value="General">General</option>
                    <option value="Ruta">🛣️ Ruta</option>
                    <option value="Mecanica">🔧 Mecánica</option>
                    <option value="Venta">💰 Venta</option>
                    <option value="Evento">📅 Evento</option>
                </select>
                <input type="url" name="imagen_url" placeholder="URL de imagen (opcional)" 
                       style="flex: 1; min-width: 150px; margin: 0;"
                       pattern="https?://.+\\.(png|jpg|jpeg|gif|webp).*">
            </div>
            <small style="color: var(--text-dim); display: block; margin-bottom: 10px;">
                💡 Pega un enlace de imagen o deja vacío
            </small>
            
            <button type="submit" class="btn btn-primary">PUBLICAR</button>
        </form>
    </div>
    """
    
    # Lista de posts
    posts_html = ""
    for p in posts:
        posts_html += f"""
        <article class="card post" id="post-{p['id']}">
            <div class="post-header">
                <div class="avatar" style="background: {p['color']}">{p['autor'][0].upper()}</div>
                <div class="post-author">
                    <a href="/perfil/{p['autor']}" class="post-author-name">{p['autor']}</a>
                    <div class="post-meta">
                        <span>{p['fecha']}</span>
                        <span>•</span>
                        <span class="post-category">{p['categoria']}</span>
                    </div>
                </div>
                {"<button class='btn-ghost btn-sm' style='margin-left: auto;' onclick=\"confirmDelete(event); fetch('/delete/' + {p['id']}, {{method: 'POST'}}).then(() => location.reload())\">🗑️</button>" if p['uid'] == session['user_id'] else ""}
            </div>
            
            <div class="post-content">{p['contenido']}</div>
            {f'<img src="{p["imagen"]}" class="post-image" alt="Imagen del post">' if p['imagen'] else ''}
            
            <div class="post-actions">
                <form action="/like/{p['id']}" method="POST" style="display: contents;">
                    <button type="submit" class="action-btn{' active' if p['liked'] else ''}" aria-label="Dar gas">
                        ⛽ <span class="count">{p['likes']}</span>
                    </button>
                </form>
                <button type="button" class="action-btn" id="toggle-{p['id']}" 
                        data-count="{p['comments']}" onclick="toggleComments({p['id']})" aria-label="Comentarios">
                    💬 <span class="count">{p['comments']}</span>
                </button>
                <form action="/bookmark/{p['id']}" method="POST" style="display: contents;">
                    <button type="submit" class="action-btn{' active' if p['bookmarked'] else ''}" aria-label="Guardar">
                        🔖
                    </button>
                </form>
                <button class="action-btn" style="margin-left: auto;" aria-label="Más opciones">⋯</button>
            </div>
            
            <div class="comments" id="comments-{p['id']}">
                <form action="/comment/{p['id']}" method="POST" class="comment-form">
                    <input type="text" name="contenido" placeholder="Escribe un comentario..." 
                           required maxlength="200">
                    <button type="submit" class="btn btn-secondary btn-sm">Enviar</button>
                </form>
                {"<p style='color: var(--text-dim); font-size: 13px; text-align: center;'>Sé el primero en comentar</p>" if not p['comentarios'] else ""}
                {"".join(f"<div class='comment'><span class='comment-author' style='color: {col}'>{n}</span><span class='comment-text'>{html.escape(t)}</span><span class='comment-time'>{t_ago}</span></div>" for n, col, t, t_ago in p['comentarios'])}
            </div>
        </article>
        """
    
    content = form_html + posts_html if posts else form_html + """
        <div class="card text-center" style="padding: 30px;">
            <p style="color: var(--text-dim);">Aún no hay publicaciones.<br>¡Sé el primero en compartir!</p>
        </div>
    """
    
    return render_page(content, active='foro', notif_count=get_notif_count(session['user_id']))


# -----------------------------------------------------------------------------
# RUTAS: ACCIONES EN POSTS
# -----------------------------------------------------------------------------
@app.route('/post', methods=['POST'])
@login_required
def crear_post():
    contenido = request.form.get('contenido', '').strip()
    categoria = request.form.get('categoria', 'General')
    imagen_url = request.form.get('imagen_url', '').strip()
    
    # Validar URL de imagen si se proporciona
    if imagen_url and not re.match(r'^https?://.+\. (png|jpg|jpeg|gif|webp)', imagen_url, re.I):
        flash("URL de imagen no válida", "error")
        return redirect('/foro')
    
    if not contenido and not imagen_url:
        flash("Escribe algo o añade una imagen", "error")
        return redirect('/foro')
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute(
        "INSERT INTO posts (usuario_id, contenido, categoria, imagen_url) VALUES (%s, %s, %s, %s)",
        (session['user_id'], contenido, categoria, imagen_url[:500] if imagen_url else '')
    )
    
    # Actualizar racha de actividad
    hoy = datetime.now().date()
    cur.execute("SELECT ultima_actividad FROM usuarios WHERE id = %s", (session['user_id'],))
    last = cur.fetchone()[0]
    
    if last == hoy - timedelta(days=1):
        cur.execute("UPDATE usuarios SET racha = racha + 1, ultima_actividad = %s WHERE id = %s", (hoy, session['user_id']))
    elif last != hoy:
        cur.execute("UPDATE usuarios SET racha = 1, ultima_actividad = %s WHERE id = %s", (hoy, session['user_id']))
    
    # Notificar menciones
    menciones = re.findall(r'@(\w+)', contenido)
    for mencionado in set(menciones):
        cur.execute("SELECT id FROM usuarios WHERE nombre = %s AND id != %s", (mencionado, session['user_id']))
        user = cur.fetchone()
        if user:
            crear_notificacion(user[0], 'mention', f"{session['user_name']} te mencionó", f"/post/{cur.lastrowid}")
    
    conn.commit()
    cur.close()
    conn.close()
    
    flash("¡Publicado! 🏍️", "success")
    return redirect('/foro')


@app.route('/like/<int:pid>', methods=['POST'])
@login_required
def like_post(pid):
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("INSERT INTO likes (usuario_id, post_id) VALUES (%s, %s)", (session['user_id'], pid))
        cur.execute("SELECT usuario_id FROM posts WHERE id = %s", (pid,))
        owner = cur.fetchone()
        if owner and owner[0] != session['user_id']:
            crear_notificacion(owner[0], 'like', f"A {session['user_name']} le gustó tu publicación", f"/post/{pid}")
        conn.commit()
    except psycopg2.IntegrityError:
        conn.rollback()
        cur.execute("DELETE FROM likes WHERE usuario_id = %s AND post_id = %s", (session['user_id'], pid))
        conn.commit()
    finally:
        cur.close()
        conn.close()
    
    return redirect(request.referrer or '/foro')


@app.route('/bookmark/<int:pid>', methods=['POST'])
@login_required
def bookmark_post(pid):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO bookmarks (usuario_id, post_id) VALUES (%s, %s)", (session['user_id'], pid))
        conn.commit()
    except psycopg2.IntegrityError:
        conn.rollback()
        cur.execute("DELETE FROM bookmarks WHERE usuario_id = %s AND post_id = %s", (session['user_id'], pid))
        conn.commit()
    finally:
        cur.close()
        conn.close()
    return redirect(request.referrer or '/foro')


@app.route('/comment/<int:pid>', methods=['POST'])
@login_required
def comentar(pid):
    txt = request.form.get('contenido', '').strip()
    if not txt:
        return redirect(request.referrer or '/foro')
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO comentarios (post_id, usuario_id, contenido) VALUES (%s, %s, %s)", (pid, session['user_id'], txt[:200]))
    
    cur.execute("SELECT usuario_id FROM posts WHERE id = %s", (pid,))
    owner = cur.fetchone()
    if owner and owner[0] != session['user_id']:
        crear_notificacion(owner[0], 'comment', f"{session['user_name']} comentó en tu publicación", f"/post/{pid}")
    
    conn.commit()
    cur.close()
    conn.close()
    return redirect(request.referrer or '/foro')


@app.route('/delete/<int:pid>', methods=['POST'])
@login_required
def borrar_post(pid):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM posts WHERE id = %s AND usuario_id = %s", (pid, session['user_id']))
    conn.commit()
    cur.close()
    conn.close()
    flash("Publicación eliminada", "success")
    return redirect('/foro')


# -----------------------------------------------------------------------------
# RUTAS: PERFIL
# -----------------------------------------------------------------------------
@app.route('/perfil')
@app.route('/perfil/<username>')
@login_required
def perfil(username=None):
    target = username or session['user_name']
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT id, nombre, bio, moto, avatar_color, racha, creado_en
        FROM usuarios WHERE nombre = %s
    """, (target,))
    user = cur.fetchone()
    
    if not user:
        flash("Usuario no encontrado", "error")
        return redirect('/foro')
    
    uid, nombre, bio, moto, color, racha, creado = user
    es_mio = uid == session['user_id']
    
    # Stats
    cur.execute("SELECT COUNT(*) FROM posts WHERE usuario_id = %s", (uid,))
    posts_count = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM seguidores WHERE seguido_id = %s", (uid,))
    followers = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM seguidores WHERE seguidor_id = %s", (uid,))
    following = cur.fetchone()[0]
    
    # ¿Lo sigo?
    sigo = False
    if not es_mio:
        cur.execute("SELECT 1 FROM seguidores WHERE seguidor_id = %s AND seguido_id = %s", (session['user_id'], uid))
        sigo = cur.fetchone() is not None
    
    # Posts del usuario
    cur.execute("""
        SELECT id, contenido, imagen_url, categoria, fecha
        FROM posts WHERE usuario_id = %s
        ORDER BY fecha DESC LIMIT 12
    """, (uid,))
    posts = [(pid, procesar_texto(txt), img, cat, time_ago(f)) for pid, txt, img, cat, f in cur.fetchall()]
    
    cur.close()
    conn.close()
    
    # HTML del perfil
    perfil_html = f"""
    <div class="card" style="padding: 0; overflow: hidden;">
        <div class="profile-banner"></div>
        <div style="padding: 0 16px 16px;">
            <div class="profile-header">
                <div class="avatar avatar-lg" style="background: {color}; border: 4px solid var(--surface);">
                    {nombre[0].upper()}
                </div>
                <div class="profile-info">
                    <h1 class="profile-name">{nombre}</h1>
                    <p class="profile-moto">{moto or 'Motero/a'}</p>
                    {"<form action='/seguir/' + str(uid) + "' method='POST' style='display: inline;'><button class='btn btn-secondary btn-sm'>" + ("Dejar de seguir" if sigo else "Seguir") + "</button></form>" if not es_mio else "<a href='/config' class='btn btn-secondary btn-sm'>Editar perfil</a>"}
                </div>
            </div>
            
            {"<p class='profile-bio'>" + html.escape(bio) + "</p>" if bio else ""}
            
            <div class="profile-stats">
                <div class="stat"><span class="stat-val">{posts_count}</span><span class="stat-label">Posts</span></div>
                <div class="stat"><span class="stat-val">{followers}</span><span class="stat-label">Seguidores</span></div>
                <div class="stat"><span class="stat-val">{following}</span><span class="stat-label">Siguiendo</span></div>
                <div class="stat"><span class="stat-val">🔥 {racha}</span><span class="stat-label">Racha</span></div>
            </div>
            
            <p style="font-size: 12px; color: var(--text-dim); margin-top: 8px;">
                Miembro desde {creado.strftime('%b %Y') if creado else '2024'}
            </p>
        </div>
    </div>
    
    <h3 style="margin: 20px 0 12px;">Publicaciones</h3>
    {"".join(f"<div class='card'><div style='display: flex; gap: 8px; margin-bottom: 8px;'><span class='post-category'>{cat}</span><span style='color: var(--text-dim); font-size: 13px; margin-left: auto;'>{fecha}</span></div><div class='post-content'>{cont}</div>{f'<img src=\"{img}\" class=\"post-image\">' if img else ''}</div>" for pid, cont, img, cat, fecha in posts) if posts else "<div class='card text-center' style='padding: 24px; color: var(--text-dim);'>Aún no ha publicado nada</div>"}
    """
    
    return render_page(perfil_html, active='perfil', notif_count=get_notif_count(session['user_id']))


@app.route('/config', methods=['GET', 'POST'])
@login_required
def config():
    if request.method == 'POST':
        bio = request.form.get('bio', '')[:200]
        moto = request.form.get('moto', '')[:50]
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE usuarios SET bio = %s, moto = %s WHERE id = %s", (bio, moto, session['user_id']))
        conn.commit()
        cur.close()
        conn.close()
        
        session['bio'] = bio
        session['moto'] = moto
        flash("Perfil actualizado ✓", "success")
        return redirect('/perfil')
    
    config_html = f"""
    <div class="card">
        <h2 style="margin-bottom: 16px;">Editar perfil</h2>
        <form method="POST">
            <label style="display: block; margin-bottom: 6px; font-weight: 500;">Tu moto</label>
            <input type="text" name="moto" placeholder="Ej: Yamaha MT-07" 
                   value="{html.escape(session.get('moto', ''))}" maxlength="50">
            
            <label style="display: block; margin: 16px 0 6px; font-weight: 500;">Biografía</label>
            <textarea name="bio" placeholder="Cuéntanos sobre ti..." maxlength="200">{html.escape(session.get('bio', ''))}</textarea>
            <small style="color: var(--text-dim); display: block; margin-bottom: 16px;">Máx. 200 caracteres</small>
            
            <button type="submit" class="btn btn-primary">Guardar cambios</button>
            <a href="/perfil" class="btn btn-secondary" style="margin-top: 8px;">Cancelar</a>
        </form>
    </div>
    
    <div class="card" style="border-color: var(--warning);">
        <h3 style="color: var(--warning); margin-bottom: 8px;">Cerrar sesión en todos lados</h3>
        <p style="font-size: 14px; color: var(--text-dim); margin-bottom: 12px;">
            Útil si usaste un dispositivo compartido.
        </p>
        <form action="/logout-all" method="POST" onsubmit="return confirm('¿Cerrar sesión en todos tus dispositivos?')">
            <button type="submit" class="btn btn-secondary btn-sm">Cerrar todas las sesiones</button>
        </form>
    </div>
    """
    return render_page(config_html, active='perfil', notif_count=get_notif_count(session['user_id']))


# -----------------------------------------------------------------------------
# RUTAS: SEGUIR / NOTIFICACIONES / BUSCAR
# -----------------------------------------------------------------------------
@app.route('/seguir/<int:uid>', methods=['POST'])
@login_required
def seguir(uid):
    if uid == session['user_id']:
        return redirect('/perfil')
    
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO seguidores (seguidor_id, seguido_id) VALUES (%s, %s)", (session['user_id'], uid))
        crear_notificacion(uid, 'follow', f"{session['user_name']} empezó a seguirte", f"/perfil/{session['user_name']}")
        conn.commit()
    except psycopg2.IntegrityError:
        conn.rollback()
        cur.execute("DELETE FROM seguidores WHERE seguidor_id = %s AND seguido_id = %s", (session['user_id'], uid))
        conn.commit()
    finally:
        cur.close()
        conn.close()
    
    return redirect(request.referrer or f'/perfil/{uid}')


@app.route('/notificaciones')
@login_required
def notificaciones():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Marcar como leídas
    cur.execute("UPDATE notificaciones SET leido = TRUE WHERE usuario_id = %s", (session['user_id'],))
    
    # Obtener notificaciones
    cur.execute("""
        SELECT tipo, mensaje, url, fecha
        FROM notificaciones
        WHERE usuario_id = %s
        ORDER BY fecha DESC
        LIMIT 30
    """, (session['user_id'],))
    
    notifs = []
    icons = {'like': '⛽', 'comment': '💬', 'follow': '👤', 'mention': '@'}
    for tipo, msg, url, fecha in cur.fetchall():
        notifs.append({
            'icon': icons.get(tipo, '🔔'),
            'msg': msg,
            'url': url,
            'time': time_ago(fecha)
        })
    
    cur.close()
    conn.close()
    
    notif_html = f"""
    <h2 style="margin-bottom: 16px;">Notificaciones</h2>
    <div class="notif-list">
        {"".join(f"<a href='{n['url'] or '#'}' class='notif-item{' unread' if i==0 else ''}'><span class='notif-icon'>{n['icon']}</span><div class='notif-content'><div class='notif-msg'>{html.escape(n['msg'])}</div><div class='notif-time'>{n['time']}</div></div></a>" for i, n in enumerate(notifs)) if notifs else "<div class='card text-center' style='padding: 30px; color: var(--text-dim);'>🎉 Sin notificaciones nuevas</div>"}
    </div>
    """
    return render_page(notif_html, active='notifs', notif_count=0)


@app.route('/buscar')
@login_required
def buscar():
    query = request.args.get('q', '').strip()
    tag = request.args.get('tag', '').strip()
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    if tag:
        cur.execute("""
            SELECT p.id, u.nombre, u.avatar_color, p.contenido, p.imagen_url, p.fecha
            FROM posts p JOIN usuarios u ON p.usuario_id = u.id
            WHERE p.contenido ILIKE %s AND p.reportes < 5
            ORDER BY p.fecha DESC LIMIT 20
        """, (f'%#{tag}%',))
        titulo = f'Posts con #{tag}'
    elif query:
        cur.execute("""
            SELECT p.id, u.nombre, u.avatar_color, p.contenido, p.imagen_url, p.fecha
            FROM posts p JOIN usuarios u ON p.usuario_id = u.id
            WHERE (p.contenido ILIKE %s OR u.nombre ILIKE %s) AND p.reportes < 5
            ORDER BY p.fecha DESC LIMIT 20
        """, (f'%{query}%', f'%{query}%'))
        titulo = f'Resultados para "{query}"'
    else:
        # Trending: posts con más likes en las últimas 48h
        cur.execute("""
            SELECT p.id, u.nombre, u.avatar_color, p.contenido, p.imagen_url, p.fecha
            FROM posts p JOIN usuarios u ON p.usuario_id = u.id
            WHERE p.fecha > NOW() - INTERVAL '48 hours' AND p.reportes < 5
            ORDER BY (SELECT COUNT(*) FROM likes WHERE post_id = p.id) DESC, p.fecha DESC
            LIMIT 20
        """)
        titulo = '🔥 Tendencias'
    
    resultados = []
    for pid, autor, color, contenido, img, fecha in cur.fetchall():
        resultados.append({
            'id': pid, 'autor': autor, 'color': color,
            'contenido': procesar_texto(contenido),
            'imagen': img, 'fecha': time_ago(fecha)
        })
    
    cur.close()
    conn.close()
    
    buscar_html = f"""
    <h2 style="margin-bottom: 12px;">{titulo}</h2>
    <form action="/buscar" method="GET" style="margin-bottom: 16px;">
        <input type="search" name="q" placeholder="Buscar usuarios o posts..." 
               value="{html.escape(query)}" style="margin: 0;">
    </form>
    {"".join(f"<div class='card'><div style='display: flex; gap: 10px; margin-bottom: 8px;'><div class='avatar' style='background: {r['color']}; width: 32px; height: 32px; font-size: 14px;'>{r['autor'][0].upper()}</div><div><a href='/perfil/{r['autor']}' style='font-weight: 500;'>{r['autor']}</a> <span style='color: var(--text-dim); font-size: 13px;'>· {r['fecha']}</span></div></div><div class='post-content'>{r['contenido']}</div>{f'<img src=\"{r['imagen']}\" class=\"post-image\">' if r['imagen'] else ''}</div>" for r in resultados) if resultados else "<div class='card text-center' style='padding: 30px; color: var(--text-dim);'>No hay resultados</div>"}
    """
    return render_page(buscar_html, active='buscar', notif_count=get_notif_count(session['user_id']))


# -----------------------------------------------------------------------------
# RUTAS: UTILIDADES
# -----------------------------------------------------------------------------
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')


@app.route('/logout-all', methods=['POST'])
@login_required
def logout_all():
    # En una app real: invalidar sesión en BD
    session.clear()
    flash("Sesiones cerradas ✓", "success")
    return redirect('/')


@app.errorhandler(404)
def not_found(e):
    return render_page("""
    <div class="card text-center" style="padding: 40px 20px;">
        <div style="font-size: 48px; margin-bottom: 16px;">🔧</div>
        <h2 style="margin-bottom: 8px;">Página no encontrada</h2>
        <p style="color: var(--text-dim); margin-bottom: 20px;">
            Lo sentimos, esa ruta no existe o fue movida.
        </p>
        <a href="/foro" class="btn btn-primary" style="width: auto; padding: 10px 24px;">Volver al inicio</a>
    </div>
    """, notif_count=get_notif_count(session['user_id']) if 'user_id' in session else 0), 404


@app.errorhandler(500)
def server_error(e):
    return render_page("""
    <div class="card text-center" style="padding: 40px 20px; border-color: var(--warning);">
        <div style="font-size: 48px; margin-bottom: 16px;">⚠️</div>
        <h2 style="margin-bottom: 8px; color: var(--warning);">Algo salió mal</h2>
        <p style="color: var(--text-dim); margin-bottom: 20px;">
            Nuestro equipo ya está trabajando en ello. Intenta recargar la página.
        </p>
        <button onclick="location.reload()" class="btn btn-primary" style="width: auto; padding: 10px 24px;">Recargar</button>
    </div>
    """, notif_count=0), 500


# -----------------------------------------------------------------------------
# ENTRY POINT PARA RENDER
# -----------------------------------------------------------------------------
if __name__ == '__main__':
    init_db()
    # Para desarrollo local
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
