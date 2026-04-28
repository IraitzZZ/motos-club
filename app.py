# =============================================================================
# MOTOSCLUB — Red Social para Moteros  |  v2.0
# =============================================================================
import os, re, html, json, requests, psycopg2
from flask import (Flask, request, redirect, render_template_string,
                   session, flash, jsonify, get_flashed_messages)
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from functools import wraps

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(32))

DATABASE_URL = os.environ.get('DATABASE_URL', '')
IMGBB_API_KEY = os.environ.get('IMGBB_API_KEY', '27a447d71db292f6c1296f509a06b09e')

# ─────────────────────────────────────────────────────────────────────────────
# BASE DE DATOS
# ─────────────────────────────────────────────────────────────────────────────
def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id SERIAL PRIMARY KEY,
            nombre TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            email TEXT DEFAULT '',
            bio TEXT DEFAULT '',
            moto TEXT DEFAULT '',
            ubicacion TEXT DEFAULT '',
            web TEXT DEFAULT '',
            avatar_url TEXT DEFAULT '',
            banner_url TEXT DEFAULT '',
            rol TEXT DEFAULT 'user',
            racha INTEGER DEFAULT 0,
            ultima_actividad DATE,
            verificado BOOLEAN DEFAULT FALSE,
            fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
            reportes INTEGER DEFAULT 0,
            pineado BOOLEAN DEFAULT FALSE,
            vistas INTEGER DEFAULT 0
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS seguidores (
            seguidor_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
            seguido_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (seguidor_id, seguido_id)
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
            tipo TEXT,
            mensaje TEXT,
            url TEXT,
            leido BOOLEAN DEFAULT FALSE,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS bookmarks (
            usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
            post_id INTEGER REFERENCES posts(id) ON DELETE CASCADE,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (usuario_id, post_id)
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS mensajes (
            id SERIAL PRIMARY KEY,
            remitente_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
            destinatario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
            contenido TEXT NOT NULL,
            leido BOOLEAN DEFAULT FALSE,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS rutas (
            id SERIAL PRIMARY KEY,
            usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
            titulo TEXT NOT NULL,
            descripcion TEXT DEFAULT '',
            distancia FLOAT DEFAULT 0,
            duracion TEXT DEFAULT '',
            dificultad TEXT DEFAULT 'Media',
            imagen_url TEXT DEFAULT '',
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            likes INTEGER DEFAULT 0
        );
    """)

    # Migraciones seguras
    migraciones = [
        "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS verificado BOOLEAN DEFAULT FALSE;",
        "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS ubicacion TEXT DEFAULT '';",
        "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS web TEXT DEFAULT '';",
        "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP;",
        "ALTER TABLE posts ADD COLUMN IF NOT EXISTS pineado BOOLEAN DEFAULT FALSE;",
        "ALTER TABLE posts ADD COLUMN IF NOT EXISTS vistas INTEGER DEFAULT 0;",
    ]
    for sql in migraciones:
        try:
            cur.execute(sql)
        except Exception:
            conn.rollback()

    conn.commit()
    cur.close()
    conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def deco(*args, **kwargs):
        if 'user_id' not in session:
            flash("Inicia sesión para continuar.", "error")
            return redirect('/')
        return f(*args, **kwargs)
    return deco


def admin_required(f):
    @wraps(f)
    def deco(*args, **kwargs):
        if session.get('rol') != 'admin':
            flash("Sin permisos.", "error")
            return redirect('/foro')
        return f(*args, **kwargs)
    return deco


def upload_to_imgbb(image_file):
    if not image_file:
        return None
    try:
        resp = requests.post(
            "https://api.imgbb.com/1/upload",
            files={"image": image_file.read()},
            data={"key": IMGBB_API_KEY},
            timeout=15
        )
        if resp.status_code == 200:
            return resp.json()['data']['url']
    except Exception as e:
        print(f"ImgBB error: {e}")
    return None


def procesar_texto(text):
    text = html.escape(text)
    # YouTube embed
    text = re.sub(
        r'https?://(?:www\.)?youtu(?:be\.com/watch\?v=|\.be/)([\w\-]+)',
        r'<div class="video-embed"><iframe src="https://www.youtube.com/embed/\1" allowfullscreen loading="lazy"></iframe></div>',
        text
    )
    # Images
    text = re.sub(
        r'(https?://[^\s]+?\.(png|jpg|jpeg|gif|webp)(\?[^\s]*)?)',
        r'<img src="\1" class="post-image" loading="lazy">',
        text
    )
    # URLs
    text = re.sub(
        r'(?<!["\'])https?://[^\s<>"\']+((?<![.,:;!?\'\)])\b)',
        r'<a href="\g<0>" target="_blank" rel="noopener" class="post-link">\g<0></a>',
        text
    )
    # @menciones
    text = re.sub(r'@(\w+)', r'<a href="/perfil/\1" class="mention">@\1</a>', text)
    # #hashtags
    text = re.sub(r'#(\w+)', r'<a href="/buscar?tag=\1" class="hashtag">#\1</a>', text)
    return text


def string_to_color(s):
    h = sum(ord(c) for c in s) % 360
    return f"hsl({h}, 65%, 50%)"


def time_ago(dt):
    if not dt:
        return ''
    delta = datetime.now() - dt
    if delta.days > 365:
        return f"hace {delta.days // 365}a"
    if delta.days > 30:
        return f"hace {delta.days // 30}m"
    if delta.days > 0:
        return f"hace {delta.days}d"
    if delta.seconds >= 3600:
        return f"hace {delta.seconds // 3600}h"
    if delta.seconds >= 60:
        return f"hace {delta.seconds // 60}m"
    return "ahora"


def notif_count_for(user_id):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM notificaciones WHERE usuario_id=%s AND leido=FALSE", (user_id,))
        c = cur.fetchone()[0]
        cur.close()
        conn.close()
        return c
    except Exception:
        return 0


def msg_count_for(user_id):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM mensajes WHERE destinatario_id=%s AND leido=FALSE", (user_id,))
        c = cur.fetchone()[0]
        cur.close()
        conn.close()
        return c
    except Exception:
        return 0


def crear_notificacion(user_id, tipo, mensaje, url):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO notificaciones (usuario_id, tipo, mensaje, url) VALUES (%s,%s,%s,%s)",
            (user_id, tipo, mensaje, url)
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception:
        pass


def insignia_racha(racha):
    if racha >= 100: return "🏆"
    if racha >= 30:  return "💎"
    if racha >= 14:  return "🥇"
    if racha >= 7:   return "🔥"
    if racha >= 3:   return "⚡"
    return ""


CATEGORIA_ICONOS = {
    'General': '🏍️',
    'Ruta':    '🛣️',
    'Mecanica':'🔧',
    'Venta':   '💰',
    'Evento':  '📅',
    'Consejo': '💡',
    'Foto':    '📷',
}


# ─────────────────────────────────────────────────────────────────────────────
# ESTILOS CSS
# ─────────────────────────────────────────────────────────────────────────────
STYLE = """
@import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:ital,wght@0,400;0,600;0,700;0,800;1,700&family=DM+Sans:wght@400;500;600&family=Space+Mono:wght@400;700&display=swap');

:root {
    --bg:        #0A0A0C;
    --bg2:       #111115;
    --surface:   #18181F;
    --surface2:  #222230;
    --border:    #2A2A38;
    --accent:    #FF4500;
    --accent2:   #FF6B35;
    --blue:      #3B82F6;
    --green:     #22C55E;
    --yellow:    #F59E0B;
    --text:      #F0F0F5;
    --muted:     #70707A;
    --shadow:    0 8px 32px rgba(0,0,0,0.6);
    --r:         14px;
}
:root[data-theme="light"] {
    --bg:        #F4F4F8;
    --bg2:       #FFFFFF;
    --surface:   #FFFFFF;
    --surface2:  #F0F0F5;
    --border:    #E0E0E8;
    --text:      #111118;
    --muted:     #888896;
    --shadow:    0 4px 20px rgba(0,0,0,0.08);
}

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

html { scroll-behavior: smooth; }

body {
    font-family: 'DM Sans', sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
    min-height: 100vh;
    transition: background 0.3s, color 0.3s;
}

/* ── TIPOGRAFÍA ── */
h1, h2, h3, .display {
    font-family: 'Barlow Condensed', sans-serif;
    letter-spacing: 0.5px;
    text-transform: uppercase;
}
.mono { font-family: 'Space Mono', monospace; }

/* ── LAYOUT ── */
.wrap { max-width: 680px; margin: 0 auto; padding: 0 16px; }

/* ── NAVBAR ── */
.navbar {
    position: sticky; top: 0; z-index: 100;
    background: rgba(10,10,12,0.88);
    backdrop-filter: blur(24px) saturate(1.4);
    border-bottom: 1px solid var(--border);
    padding: 0;
}
[data-theme="light"] .navbar { background: rgba(255,255,255,0.9); }
.nav-inner {
    display: flex; align-items: center; justify-content: space-between;
    max-width: 680px; margin: 0 auto; padding: 12px 16px; gap: 12px;
}
.nav-brand {
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 26px; font-weight: 800; letter-spacing: 1px;
    text-decoration: none; color: var(--text);
    display: flex; align-items: center; gap: 6px;
}
.nav-brand span { color: var(--accent); }
.nav-links { display: flex; align-items: center; gap: 6px; }
.nav-icon {
    width: 38px; height: 38px; border-radius: 10px;
    display: flex; align-items: center; justify-content: center;
    background: transparent; border: 1px solid var(--border);
    color: var(--text); font-size: 18px; cursor: pointer;
    text-decoration: none; position: relative;
    transition: all 0.2s; line-height: 1;
}
.nav-icon:hover { background: var(--surface2); border-color: var(--accent); }
.nav-badge {
    position: absolute; top: -4px; right: -4px;
    background: var(--accent); color: #fff;
    font-size: 9px; font-weight: 700; font-family: 'Space Mono', monospace;
    width: 16px; height: 16px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    border: 2px solid var(--bg);
}
.nav-btn {
    padding: 7px 14px; border-radius: 10px;
    background: var(--surface); border: 1px solid var(--border);
    color: var(--text); font-weight: 600; font-size: 13px;
    cursor: pointer; text-decoration: none;
    transition: all 0.2s; white-space: nowrap;
}
.nav-btn:hover { border-color: var(--accent); color: var(--accent); }
.nav-btn.active { background: var(--accent); border-color: var(--accent); color: #fff; }

/* ── TABS ── */
.tabs {
    display: flex; gap: 4px; margin-bottom: 20px;
    background: var(--surface); border-radius: var(--r);
    padding: 4px; border: 1px solid var(--border);
}
.tab {
    flex: 1; padding: 9px; border-radius: 10px; border: none;
    background: transparent; color: var(--muted);
    font-weight: 600; font-size: 13px; cursor: pointer;
    transition: all 0.2s; text-decoration: none;
    text-align: center; display: block;
}
.tab.active, .tab:hover { background: var(--accent); color: #fff; }

/* ── CARDS ── */
.card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--r);
    padding: 20px;
    margin-bottom: 14px;
    box-shadow: var(--shadow);
    transition: border-color 0.2s;
}
.card:hover { border-color: var(--surface2); }
.card-tight { padding: 14px; }

/* ── FORMULARIOS ── */
input, textarea, select {
    width: 100%;
    background: var(--bg2);
    border: 1.5px solid var(--border);
    color: var(--text);
    padding: 12px 16px;
    border-radius: 10px;
    font-family: 'DM Sans', sans-serif;
    font-size: 15px;
    outline: none;
    margin-bottom: 10px;
    transition: border-color 0.2s;
    -webkit-appearance: none;
}
input:focus, textarea:focus, select:focus { border-color: var(--accent); }
textarea { resize: vertical; min-height: 90px; }
label { font-size: 13px; font-weight: 600; color: var(--muted); display: block; margin-bottom: 5px; }

/* ── BOTONES ── */
.btn {
    display: inline-flex; align-items: center; justify-content: center; gap: 6px;
    padding: 12px 22px; border-radius: 10px; border: none;
    font-family: 'DM Sans', sans-serif; font-weight: 600; font-size: 15px;
    cursor: pointer; transition: all 0.2s; text-decoration: none;
    white-space: nowrap;
}
.btn-primary { background: var(--accent); color: #fff; width: 100%; }
.btn-primary:hover { background: var(--accent2); transform: translateY(-1px); }
.btn-secondary {
    background: var(--surface2); border: 1px solid var(--border);
    color: var(--text); padding: 7px 14px; font-size: 13px;
}
.btn-secondary:hover { border-color: var(--accent); color: var(--accent); }
.btn-follow {
    background: var(--blue); color: #fff; padding: 7px 16px;
    border-radius: 20px; font-size: 13px;
}
.btn-follow.following {
    background: transparent; border: 1.5px solid var(--border); color: var(--text);
}
.btn-sm { padding: 5px 12px; font-size: 12px; border-radius: 8px; }

/* ── AVATAR ── */
.av {
    border-radius: 50%; overflow: hidden;
    display: flex; align-items: center; justify-content: center;
    font-weight: 700; color: #fff; flex-shrink: 0;
    background: var(--surface2);
}
.av img { width: 100%; height: 100%; object-fit: cover; }
.av-lg { width: 80px; height: 80px; font-size: 30px; border: 3px solid var(--bg); }
.av-md { width: 46px; height: 46px; font-size: 18px; }
.av-sm { width: 34px; height: 34px; font-size: 14px; }

/* ── POST ── */
.post-header { display: flex; gap: 12px; margin-bottom: 12px; align-items: flex-start; }
.post-meta { flex: 1; min-width: 0; }
.post-meta strong { font-size: 15px; }
.post-meta small { color: var(--muted); font-size: 12px; }
.post-body { font-size: 15px; line-height: 1.7; word-break: break-word; }
.post-body a { color: var(--accent); text-decoration: none; }
.post-body a:hover { text-decoration: underline; }
.post-image {
    width: 100%; border-radius: 12px; margin-top: 12px;
    border: 1px solid var(--border); display: block;
}
.video-embed {
    margin-top: 12px; border-radius: 12px; overflow: hidden;
    aspect-ratio: 16/9;
}
.video-embed iframe { width: 100%; height: 100%; border: none; }
.cat-badge {
    display: inline-flex; align-items: center; gap: 4px;
    font-size: 11px; font-weight: 600; padding: 3px 8px;
    background: var(--surface2); border-radius: 20px;
    color: var(--muted); margin-bottom: 8px;
}
.cat-badge.Ruta    { color: var(--green); }
.cat-badge.Mecanica{ color: var(--blue); }
.cat-badge.Venta   { color: var(--yellow); }
.cat-badge.Evento  { color: var(--accent); }

/* ── ACCIONES ── */
.post-actions {
    display: flex; gap: 4px; margin-top: 14px;
    padding-top: 12px; border-top: 1px solid var(--border);
    flex-wrap: wrap;
}
.act-btn {
    display: flex; align-items: center; gap: 5px;
    padding: 6px 12px; border-radius: 8px; border: none;
    background: transparent; color: var(--muted);
    font-size: 13px; font-weight: 600; cursor: pointer;
    transition: all 0.15s;
}
.act-btn:hover { background: var(--surface2); color: var(--text); }
.act-btn.on { color: var(--accent); }
.act-btn.on-blue { color: var(--blue); }

/* ── COMMENTS ── */
.comments-box {
    margin-top: 12px; border-top: 1px solid var(--border);
    padding-top: 12px; display: none;
}
.comment-item {
    display: flex; gap: 8px; margin-bottom: 10px; align-items: flex-start;
}
.comment-bubble {
    background: var(--bg2); border-radius: 0 10px 10px 10px;
    padding: 8px 12px; flex: 1; font-size: 13px;
    border: 1px solid var(--border);
}
.comment-bubble strong { display: block; font-size: 12px; margin-bottom: 2px; }

/* ── PERFIL ── */
.banner {
    height: 180px; border-radius: var(--r) var(--r) 0 0;
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    background-size: cover; background-position: center;
    position: relative; overflow: hidden;
}
.banner::after {
    content: ''; position: absolute; inset: 0;
    background: linear-gradient(to bottom, transparent 50%, rgba(0,0,0,0.4) 100%);
}
.profile-card { padding: 0; overflow: hidden; }
.profile-body { padding: 0 20px 20px; }
.profile-av {
    position: relative; margin-top: -44px;
    width: 80px; height: 80px; z-index: 2;
}
.profile-row {
    display: flex; justify-content: space-between; align-items: flex-end;
    margin-bottom: 12px; flex-wrap: wrap; gap: 10px;
}
.profile-stats {
    display: flex; gap: 24px; margin: 14px 0;
}
.stat span { display: block; font-size: 20px; font-weight: 700; }
.stat small { color: var(--muted); font-size: 12px; }

/* ── BADGE / VERIFY ── */
.verified { color: var(--blue); font-size: 14px; }
.racha-badge {
    display: inline-flex; align-items: center; gap: 4px;
    font-size: 12px; background: rgba(255,69,0,0.12);
    color: var(--accent); padding: 2px 8px; border-radius: 20px;
    border: 1px solid rgba(255,69,0,0.25); font-weight: 600;
}

/* ── SEARCH ── */
.search-bar {
    display: flex; gap: 8px; margin-bottom: 16px; align-items: center;
}
.search-bar input { margin: 0; }
.search-bar button { flex-shrink: 0; width: auto; padding: 12px 18px; border-radius: 10px; }

/* ── NOTIFICACIONES ── */
.notif-item {
    display: flex; gap: 12px; align-items: flex-start;
    padding: 14px; border-bottom: 1px solid var(--border);
    text-decoration: none; color: var(--text);
    transition: background 0.15s;
}
.notif-item:last-child { border-bottom: none; }
.notif-item:hover { background: var(--surface2); }
.notif-item.unread { background: rgba(59,130,246,0.06); }
.notif-dot {
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--blue); flex-shrink: 0; margin-top: 6px;
}

/* ── MENSAJES ── */
.msg-list { display: flex; flex-direction: column; gap: 8px; }
.msg-bubble {
    max-width: 75%; padding: 10px 14px;
    border-radius: 14px; font-size: 14px; line-height: 1.5;
}
.msg-bubble.me {
    background: var(--accent); color: #fff; align-self: flex-end;
    border-radius: 14px 14px 4px 14px;
}
.msg-bubble.them {
    background: var(--surface2); align-self: flex-start;
    border-radius: 14px 14px 14px 4px;
}
.msg-meta { font-size: 10px; color: var(--muted); margin-top: 2px; }
.conversation-header {
    display: flex; align-items: center; gap: 10px;
    padding-bottom: 14px; border-bottom: 1px solid var(--border); margin-bottom: 16px;
}

/* ── TRENDING ── */
.trending-item {
    display: flex; align-items: center; justify-content: space-between;
    padding: 10px 0; border-bottom: 1px solid var(--border);
}
.trending-item:last-child { border-bottom: none; }
.trending-num {
    font-family: 'Space Mono', monospace;
    font-size: 11px; color: var(--muted); width: 18px;
}
.trending-tag { font-weight: 600; color: var(--accent); }
.trending-count { font-size: 12px; color: var(--muted); }

/* ── RUTAS ── */
.ruta-card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--r); overflow: hidden; margin-bottom: 14px;
}
.ruta-img { width: 100%; height: 180px; object-fit: cover; display: block; }
.ruta-body { padding: 16px; }
.ruta-stats { display: flex; gap: 16px; margin-top: 10px; }
.ruta-stat { text-align: center; }
.ruta-stat span { display: block; font-weight: 700; }
.ruta-stat small { color: var(--muted); font-size: 11px; }
.dif-badge {
    font-size: 11px; padding: 2px 8px; border-radius: 20px; font-weight: 600;
}
.dif-Fácil   { background: rgba(34,197,94,0.15); color: var(--green); }
.dif-Media   { background: rgba(245,158,11,0.15); color: var(--yellow); }
.dif-Difícil { background: rgba(255,69,0,0.15); color: var(--accent); }
.dif-Extrema { background: rgba(255,0,0,0.2); color: #ff2222; }

/* ── LOGIN ── */
.login-wrap {
    min-height: calc(100vh - 70px);
    display: flex; align-items: center; justify-content: center;
    padding: 20px 16px;
}
.login-box { width: 100%; max-width: 420px; }
.login-title {
    font-family: 'Barlow Condensed', sans-serif;
    font-size: 52px; font-weight: 800;
    text-align: center; margin-bottom: 6px; letter-spacing: 2px;
}
.login-title span { color: var(--accent); }
.login-sub { text-align: center; color: var(--muted); margin-bottom: 28px; font-size: 14px; }
.login-tabs { display: flex; gap: 0; margin-bottom: 20px; border-radius: 10px; overflow: hidden; border: 1px solid var(--border); }
.login-tab {
    flex: 1; padding: 11px; text-align: center; cursor: pointer;
    background: var(--surface); color: var(--muted);
    border: none; font-weight: 600; font-size: 14px;
    font-family: 'DM Sans', sans-serif; transition: all 0.2s;
}
.login-tab.active { background: var(--accent); color: #fff; }

/* ── FLASH ── */
.flash {
    padding: 12px 16px; border-radius: 10px; margin-bottom: 14px;
    font-weight: 600; font-size: 14px; text-align: center;
    animation: slideDown 0.3s ease;
}
.flash-error   { background: rgba(255,69,0,0.12); border: 1px solid rgba(255,69,0,0.3); color: var(--accent); }
.flash-success { background: rgba(34,197,94,0.12); border: 1px solid rgba(34,197,94,0.3); color: var(--green); }
@keyframes slideDown { from { opacity:0; transform: translateY(-8px); } to { opacity:1; transform: translateY(0); } }

/* ── RESPONSIVE ── */
@media (max-width: 600px) {
    .nav-btn span { display: none; }
    .login-title { font-size: 42px; }
    .profile-stats { gap: 14px; }
}

/* ── MISC ── */
.divider { border: none; border-top: 1px solid var(--border); margin: 16px 0; }
.text-muted { color: var(--muted); font-size: 13px; }
.empty-state { text-align: center; padding: 40px 20px; color: var(--muted); }
.empty-state .icon { font-size: 48px; display: block; margin-bottom: 12px; }
.mention { color: var(--blue) !important; }
.hashtag { color: var(--accent) !important; }
.post-link { color: var(--blue) !important; font-size: 13px; }
.section-title { font-size: 22px; margin: 20px 0 12px; color: var(--text); }
.pill {
    display: inline-block; padding: 3px 10px; border-radius: 20px;
    font-size: 12px; font-weight: 600;
    background: var(--surface2); color: var(--muted);
}
"""


# ─────────────────────────────────────────────────────────────────────────────
# BASE LAYOUT
# ─────────────────────────────────────────────────────────────────────────────
def render_page(content, active='', notif_count=0, msg_count=0):
    uid = session.get('user_id', 0)
    uname = session.get('user_name', '')
    flash_html = ''
    for cat, msg in session.pop('_flashes', []) if False else []:
        pass

    nav = f"""
    <nav class="navbar">
      <div class="nav-inner">
        <a href="/foro" class="nav-brand">MOTOS<span>CLUB</span></a>
        <div class="nav-links">
          <button onclick="toggleTheme()" class="nav-icon" id="thbtn" title="Tema">🌙</button>
          <a href="/buscar" class="nav-icon {'nav-btn active' if active=='buscar' else ''}" title="Explorar">🔍</a>
          <a href="/mensajes" class="nav-icon" title="Mensajes" style="position:relative;">
            ✉️{'<span class="nav-badge">' + str(msg_count) + '</span>' if msg_count > 0 else ''}
          </a>
          <a href="/notificaciones" class="nav-icon" title="Notificaciones" style="position:relative;">
            🔔{'<span class="nav-badge">' + str(notif_count) + '</span>' if notif_count > 0 else ''}
          </a>
          <a href="/perfil/{uname}" class="nav-btn {'active' if active=='perfil' else ''}" title="Mi perfil">Yo</a>
          <a href="/logout" class="nav-btn" title="Salir">Salir</a>
        </div>
      </div>
    </nav>
    """ if uid else """
    <nav class="navbar">
      <div class="nav-inner">
        <a href="/" class="nav-brand">MOTOS<span>CLUB</span></a>
      </div>
    </nav>
    """

    template = f"""<!DOCTYPE html>
<html lang="es" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="description" content="MOTOSCLUB — La red social de los moteros. Comparte rutas, fotos y conecta con otros moteros.">
  <title>MOTOSCLUB</title>
  <style>{STYLE}</style>
</head>
<body>
{nav}
<div class="wrap" style="padding-top:20px; padding-bottom:60px;">
  {{% with messages = get_flashed_messages(with_categories=true) %}}
  {{% if messages %}}
  {{% for cat, msg in messages %}}
  <div class="flash flash-{{{{ cat }}}}">{{{{ msg }}}}</div>
  {{% endfor %}}
  {{% endif %}}
  {{% endwith %}}
  {content}
</div>
<script>
function applyTheme(t){{
  document.documentElement.setAttribute('data-theme', t);
  localStorage.setItem('theme', t);
  const btn = document.getElementById('thbtn');
  if(btn) btn.textContent = t==='light'?'☀️':'🌙';
}}
function toggleTheme(){{
  applyTheme(localStorage.getItem('theme')==='light'?'dark':'light');
}}
(function(){{ applyTheme(localStorage.getItem('theme')||'dark'); }})();

function toggleCom(id){{
  const el = document.getElementById('com-'+id);
  if(el){{ el.style.display = el.style.display==='none'?'block':'none'; }}
}}

// Character counter
document.querySelectorAll('textarea[data-max]').forEach(function(ta){{
  const max = parseInt(ta.dataset.max);
  const counter = document.createElement('div');
  counter.className = 'text-muted';
  counter.style.cssText = 'text-align:right;margin-top:-6px;margin-bottom:10px;font-size:12px;';
  ta.after(counter);
  function update(){{
    const left = max - ta.value.length;
    counter.textContent = left + ' caracteres restantes';
    counter.style.color = left < 20 ? 'var(--accent)' : 'var(--muted)';
  }}
  ta.addEventListener('input', update);
  update();
}});

// Auto-dismiss flash messages
setTimeout(function(){{
  document.querySelectorAll('.flash').forEach(function(el){{
    el.style.transition='opacity 0.4s';
    el.style.opacity='0';
    setTimeout(function(){{ el.remove(); }}, 400);
  }});
}}, 4000);
</script>
</body>
</html>"""

    from flask import get_flashed_messages as gfm
    return render_template_string(template)


# ─────────────────────────────────────────────────────────────────────────────
# RUTAS: AUTH
# ─────────────────────────────────────────────────────────────────────────────
@app.route('/', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect('/foro')

    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        passw  = request.form.get('password', '')
        action = request.form.get('action', 'login')

        if not nombre or not passw:
            flash("Completa todos los campos.", "error")
            return redirect('/')

        conn = get_db()
        cur  = conn.cursor()

        if action == 'register':
            if len(nombre) < 3:
                flash("El nombre debe tener al menos 3 caracteres.", "error")
            elif len(nombre) > 30:
                flash("Nombre demasiado largo.", "error")
            elif not re.match(r'^[\w\-\.]+$', nombre):
                flash("Solo letras, números, guiones y puntos.", "error")
            elif len(passw) < 6:
                flash("La contraseña debe tener al menos 6 caracteres.", "error")
            else:
                try:
                    cur.execute(
                        "INSERT INTO usuarios (nombre, password) VALUES (%s, %s)",
                        (nombre, generate_password_hash(passw))
                    )
                    conn.commit()
                    flash("¡Cuenta creada! Entra ahora.", "success")
                except Exception:
                    conn.rollback()
                    flash("Ese usuario ya existe.", "error")
        else:
            cur.execute(
                "SELECT id, password, avatar_url, banner_url, bio, moto, rol FROM usuarios WHERE nombre=%s",
                (nombre,)
            )
            u = cur.fetchone()
            if u and check_password_hash(u[1], passw):
                session.update({
                    'user_id': u[0], 'user_name': nombre,
                    'avatar_url': u[2] or '', 'banner_url': u[3] or '',
                    'bio': u[4] or '', 'moto': u[5] or '', 'rol': u[6] or 'user'
                })
                cur.close(); conn.close()
                return redirect('/foro')
            else:
                flash("Usuario o contraseña incorrectos.", "error")

        cur.close(); conn.close()
        return redirect('/')

    html_content = """
    <div class="login-wrap">
      <div class="login-box">
        <div class="login-title">MOTOS<span style="color:var(--accent)">CLUB</span></div>
        <p class="login-sub">La comunidad de los que viven sobre dos ruedas 🏍️</p>
        <div class="card">
          <div class="login-tabs">
            <button class="login-tab active" onclick="switchTab('login',this)">ENTRAR</button>
            <button class="login-tab" onclick="switchTab('reg',this)">REGISTRARSE</button>
          </div>
          <form method="POST" id="form-login">
            <input type="hidden" name="action" value="login">
            <label>Usuario</label>
            <input type="text" name="nombre" placeholder="Tu nombre de usuario" required autocomplete="username">
            <label>Contraseña</label>
            <input type="password" name="password" placeholder="••••••••" required autocomplete="current-password">
            <button class="btn btn-primary" type="submit">ENTRAR AL CLUB</button>
          </form>
          <form method="POST" id="form-reg" style="display:none;">
            <input type="hidden" name="action" value="register">
            <label>Elige un nombre de usuario</label>
            <input type="text" name="nombre" placeholder="solo letras, números y guiones" required autocomplete="username" pattern="[\w\-\.]+" minlength="3" maxlength="30">
            <label>Contraseña (mín. 6 caracteres)</label>
            <input type="password" name="password" placeholder="••••••••" required minlength="6" autocomplete="new-password">
            <button class="btn btn-primary" type="submit">CREAR CUENTA</button>
          </form>
        </div>
        <p style="text-align:center; color:var(--muted); font-size:12px; margin-top:16px;">
          Al unirte aceptas compartir tu pasión por las motos 🔥
        </p>
      </div>
    </div>
    <script>
    function switchTab(tab, btn){
      document.querySelectorAll('.login-tab').forEach(b=>b.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById('form-login').style.display = tab==='login'?'block':'none';
      document.getElementById('form-reg').style.display  = tab==='reg'?'block':'none';
    }
    </script>
    """

    return render_template_string(
        _base_layout(html_content), style=STYLE, notif_count=0
    )


# ─────────────────────────────────────────────────────────────────────────────
# RUTAS: FORO
# ─────────────────────────────────────────────────────────────────────────────
@app.route('/foro')
@login_required
def foro():
    filtro = request.args.get('filtro', 'siguiendo')
    conn = get_db()
    cur  = conn.cursor()

    if filtro == 'siguiendo':
        cur.execute("SELECT seguido_id FROM seguidores WHERE seguidor_id=%s", (session['user_id'],))
        ids = [r[0] for r in cur.fetchall()] + [session['user_id']]
        where = f"p.usuario_id = ANY(ARRAY{ids}) AND"
    elif filtro == 'categoria':
        cat = request.args.get('cat', 'General')
        where = f"p.categoria='{cat}' AND"
    else:
        where = ""

    cur.execute(f"""
        SELECT p.id, u.nombre, p.contenido, p.fecha, p.categoria,
               u.avatar_url, p.usuario_id, p.imagen_url, p.pineado,
               (SELECT COUNT(*) FROM likes WHERE post_id=p.id),
               (SELECT COUNT(*) FROM comentarios WHERE post_id=p.id),
               (EXISTS(SELECT 1 FROM likes WHERE post_id=p.id AND usuario_id=%s)),
               (EXISTS(SELECT 1 FROM bookmarks WHERE post_id=p.id AND usuario_id=%s)),
               u.verificado, u.moto
        FROM posts p JOIN usuarios u ON p.usuario_id=u.id
        WHERE {where} p.reportes < 5
        ORDER BY p.pineado DESC, p.fecha DESC LIMIT 40
    """, (session['user_id'], session['user_id']))

    raw = cur.fetchall()
    posts = []
    for p in raw:
        cur.execute("""
            SELECT u.nombre, c.contenido, c.fecha, u.avatar_url, u.verificado
            FROM comentarios c JOIN usuarios u ON c.usuario_id=u.id
            WHERE c.post_id=%s ORDER BY c.fecha ASC LIMIT 5
        """, (p[0],))
        coms = cur.fetchall()
        posts.append({
            'id': p[0], 'autor': p[1], 'contenido_raw': p[2],
            'contenido': procesar_texto(p[2]), 'fecha': time_ago(p[3]),
            'categoria': p[4], 'avatar': p[5] or string_to_color(p[1]),
            'autor_id': p[6], 'img': p[7], 'pineado': p[8],
            'likes': p[9], 'coms_count': p[10],
            'liked': p[11], 'bookmarked': p[12],
            'verificado': p[13], 'moto': p[14] or 'Motero',
            'coms': coms
        })

    # Trending hashtags
    cur.execute("""
        SELECT regexp_matches(contenido, '#(\\w+)', 'g') as tag, COUNT(*) as cnt
        FROM posts WHERE fecha > NOW() - INTERVAL '7 days'
        GROUP BY tag ORDER BY cnt DESC LIMIT 6
    """)
    trending = cur.fetchall()

    # Sugerencias de usuarios
    cur.execute("""
        SELECT u.nombre, u.avatar_url, u.moto FROM usuarios u
        WHERE u.id != %s
          AND u.id NOT IN (SELECT seguido_id FROM seguidores WHERE seguidor_id=%s)
        ORDER BY RANDOM() LIMIT 4
    """, (session['user_id'], session['user_id']))
    sugerencias = cur.fetchall()

    nc = notif_count_for(session['user_id'])
    mc = msg_count_for(session['user_id'])
    cur.close(); conn.close()

    cat_icons = CATEGORIA_ICONOS
    foro_html = f"""
    <!-- Composer -->
    <div class="card">
      <form method="POST" action="/post" enctype="multipart/form-data">
        <div style="display:flex;gap:10px;align-items:flex-start;">
          <div class="av av-md" style="background:{session.get('avatar_url') or string_to_color(session['user_name'])};flex-shrink:0;">
            {'<img src="' + session['avatar_url'] + '">' if session.get('avatar_url','').startswith('http') else session['user_name'][0].upper()}
          </div>
          <div style="flex:1;">
            <textarea name="contenido" placeholder="¿Qué ruedas hoy? Usa @menciones y #hashtags…" data-max="500" style="margin-bottom:10px;"></textarea>
            <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
              <select name="categoria" style="width:auto;margin:0;font-size:13px;padding:8px 12px;">
                {''.join(f'<option value="{k}">{v} {k}</option>' for k,v in CATEGORIA_ICONOS.items())}
              </select>
              <label style="display:flex;align-items:center;gap:6px;cursor:pointer;
                            background:var(--surface2);border:1px solid var(--border);
                            border-radius:8px;padding:8px 12px;margin:0;color:var(--muted);
                            font-size:13px;font-weight:600;">
                📷 Foto
                <input type="file" name="foto" accept="image/*" style="display:none;">
              </label>
              <button class="btn btn-primary" type="submit" style="width:auto;padding:8px 20px;margin:0;">PUBLICAR</button>
            </div>
          </div>
        </div>
      </form>
    </div>

    <!-- Filtros -->
    <div class="tabs">
      <a href="/foro?filtro=siguiendo" class="tab {'active' if filtro=='siguiendo' else ''}">🏠 Feed</a>
      <a href="/foro?filtro=todo" class="tab {'active' if filtro=='todo' else ''}">🌐 Global</a>
      <a href="/foro?filtro=categoria&cat=Ruta" class="tab {'active' if filtro=='categoria' else ''}">🛣️ Rutas</a>
      <a href="/rutas" class="tab">🗺️ Mapa Rutas</a>
    </div>
    """

    if trending:
        foro_html += """<div class="card card-tight" style="margin-bottom:14px;">
          <div style="font-size:12px;font-weight:700;color:var(--muted);margin-bottom:8px;text-transform:uppercase;letter-spacing:1px;">🔥 Trending</div>
          <div style="display:flex;flex-wrap:wrap;gap:6px;">"""
        for t in trending:
            foro_html += f'<a href="/buscar?tag={t[0][0]}" class="pill"># {t[0][0]}</a>'
        foro_html += "</div></div>"

    if not posts:
        foro_html += """<div class="card empty-state">
          <span class="icon">🏍️</span>
          <strong>¡Sin posts todavía!</strong><br>
          <p class="text-muted">Sigue a otros moteros o publica el primero.</p>
          <a href="/buscar" class="btn btn-secondary btn-sm" style="display:inline-flex;margin-top:12px;">Explorar moteros</a>
        </div>"""

    for p in posts:
        cat_icon = CATEGORIA_ICONOS.get(p['categoria'], '🏍️')
        av_html  = (f'<img src="{p["avatar"]}">' if p['avatar'].startswith('http')
                    else p['autor'][0].upper())
        ver_badge = ' <span class="verified">✓</span>' if p['verificado'] else ''
        pin_badge = ' 📌' if p['pineado'] else ''

        coms_html = ''
        for c in p['coms']:
            cav = f'<img src="{c[3]}">' if c[3] and c[3].startswith('http') else c[0][0].upper()
            coms_html += f"""
            <div class="comment-item">
              <div class="av av-sm" style="background:{string_to_color(c[0])}">{cav}</div>
              <div class="comment-bubble">
                <strong><a href="/perfil/{c[0]}" style="color:var(--text);text-decoration:none;">{c[0]}</a>
                  {' <span class="verified">✓</span>' if c[4] else ''}
                  <span style="color:var(--muted);font-weight:400;">{time_ago(c[2])}</span>
                </strong>
                {html.escape(c[1])}
              </div>
            </div>"""

        foro_html += f"""
        <div class="card" id="post-{p['id']}">
          <div class="post-header">
            <a href="/perfil/{p['autor']}">
              <div class="av av-md" style="background:{p['avatar'] if not p['avatar'].startswith('http') else string_to_color(p['autor'])}">{av_html}</div>
            </a>
            <div class="post-meta">
              <div>
                <a href="/perfil/{p['autor']}" style="text-decoration:none;color:var(--text);">
                  <strong>{p['autor']}</strong>{ver_badge}{pin_badge}
                </a>
              </div>
              <small>{p['fecha']} · {p['moto']}</small>
            </div>
            <div style="display:flex;gap:6px;align-items:center;">
              {'<form action="/delete/' + str(p["id"]) + '" method="POST" onsubmit="return confirm(\'¿Borrar este post?\')"><button class="btn btn-secondary btn-sm">🗑️</button></form>' if p["autor_id"]==session["user_id"] else ''}
              <form action="/report/{p['id']}" method="POST" onsubmit="return confirm('¿Reportar?')">
                <button class="btn btn-secondary btn-sm">⚠️</button>
              </form>
            </div>
          </div>
          <span class="cat-badge {p['categoria']}">{cat_icon} {p['categoria']}</span>
          <div class="post-body">{p['contenido']}</div>
          {'<img src="' + p["img"] + '" class="post-image" loading="lazy">' if p['img'] else ''}
          <div class="post-actions">
            <form action="/like/{p['id']}" method="POST" style="display:inline;">
              <button class="act-btn {'on' if p['liked'] else ''}">⛽ {p['likes']}</button>
            </form>
            <button class="act-btn" onclick="toggleCom({p['id']})">💬 {p['coms_count']}</button>
            <form action="/bookmark/{p['id']}" method="POST" style="display:inline;">
              <button class="act-btn {'on-blue' if p['bookmarked'] else ''}">🔖</button>
            </form>
            <a href="/post/{p['id']}" class="act-btn" style="margin-left:auto;">🔗</a>
          </div>
          <div class="comments-box" id="com-{p['id']}">
            <form action="/comment/{p['id']}" method="POST" style="display:flex;gap:8px;margin-bottom:12px;">
              <input type="text" name="contenido" placeholder="Escribe un comentario…" required style="margin:0;flex:1;">
              <button class="btn btn-secondary" type="submit" style="width:auto;padding:10px 14px;margin:0;">↩</button>
            </form>
            {coms_html}
          </div>
        </div>
        """

    if sugerencias:
        foro_html += """<div class="card">
          <div style="font-size:12px;font-weight:700;color:var(--muted);margin-bottom:12px;text-transform:uppercase;letter-spacing:1px;">👥 Moteros que quizás conozcas</div>"""
        for s in sugerencias:
            sav = f'<img src="{s[1]}">' if s[1] and s[1].startswith('http') else s[0][0].upper()
            foro_html += f"""
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;">
              <a href="/perfil/{s[0]}">
                <div class="av av-sm" style="background:{s[1] if s[1] and s[1].startswith('http') else string_to_color(s[0])}">{sav}</div>
              </a>
              <div style="flex:1;">
                <a href="/perfil/{s[0]}" style="color:var(--text);text-decoration:none;font-weight:600;">{s[0]}</a>
                <div style="font-size:12px;color:var(--muted);">{s[2] or 'Motero'}</div>
              </div>
              <form action="/seguir/{s[0]}" method="POST">
                <button class="btn btn-follow btn-sm">Seguir</button>
              </form>
            </div>"""
        foro_html += "</div>"

    return render_template_string(
        _base_layout(foro_html), style=STYLE, active='foro',
        notif_count=nc, msg_count=mc
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST individual
# ─────────────────────────────────────────────────────────────────────────────
@app.route('/post/<int:pid>')
@login_required
def ver_post(pid):
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("UPDATE posts SET vistas=vistas+1 WHERE id=%s", (pid,))
    cur.execute("""
        SELECT p.id, u.nombre, p.contenido, p.fecha, p.categoria,
               u.avatar_url, p.usuario_id, p.imagen_url, u.verificado, p.vistas,
               (SELECT COUNT(*) FROM likes WHERE post_id=p.id),
               (EXISTS(SELECT 1 FROM likes WHERE post_id=p.id AND usuario_id=%s))
        FROM posts p JOIN usuarios u ON p.usuario_id=u.id
        WHERE p.id=%s
    """, (session['user_id'], pid))
    p = cur.fetchone()
    if not p:
        conn.commit(); cur.close(); conn.close()
        flash("Post no encontrado.", "error")
        return redirect('/foro')

    cur.execute("""
        SELECT u.nombre, c.contenido, c.fecha, u.avatar_url, u.verificado, c.id
        FROM comentarios c JOIN usuarios u ON c.usuario_id=u.id
        WHERE c.post_id=%s ORDER BY c.fecha ASC
    """, (pid,))
    coms = cur.fetchall()
    conn.commit()
    nc = notif_count_for(session['user_id'])
    mc = msg_count_for(session['user_id'])
    cur.close(); conn.close()

    cat_icon = CATEGORIA_ICONOS.get(p[4], '🏍️')
    av_html  = f'<img src="{p[5]}">' if p[5] and p[5].startswith('http') else p[1][0].upper()
    ver      = ' <span class="verified">✓</span>' if p[8] else ''

    coms_html = ''
    for c in coms:
        cav = f'<img src="{c[3]}">' if c[3] and c[3].startswith('http') else c[0][0].upper()
        coms_html += f"""
        <div class="comment-item">
          <div class="av av-sm" style="background:{string_to_color(c[0])}">{cav}</div>
          <div class="comment-bubble">
            <strong><a href="/perfil/{c[0]}" style="color:var(--text);text-decoration:none;">{c[0]}</a>
              {' <span class="verified">✓</span>' if c[4] else ''}
              <span style="color:var(--muted);font-weight:400;"> · {time_ago(c[2])}</span>
            </strong>
            {html.escape(c[1])}
          </div>
        </div>"""

    content = f"""
    <div class="card">
      <div class="post-header">
        <a href="/perfil/{p[1]}">
          <div class="av av-md" style="background:{string_to_color(p[1])}">{av_html}</div>
        </a>
        <div class="post-meta">
          <div><a href="/perfil/{p[1]}" style="text-decoration:none;color:var(--text);"><strong>{p[1]}</strong>{ver}</a></div>
          <small>{time_ago(p[3])} · {p[9]} vistas</small>
        </div>
      </div>
      <span class="cat-badge {p[4]}">{cat_icon} {p[4]}</span>
      <div class="post-body" style="font-size:17px;">{procesar_texto(p[2])}</div>
      {'<img src="' + p[7] + '" class="post-image">' if p[7] else ''}
      <div class="post-actions">
        <form action="/like/{p[0]}" method="POST" style="display:inline;">
          <button class="act-btn {'on' if p[11] else ''}">⛽ {p[10]}</button>
        </form>
      </div>
    </div>

    <h3 class="display section-title">💬 Comentarios ({len(coms)})</h3>
    <div class="card" style="margin-bottom:14px;">
      <form action="/comment/{pid}" method="POST" style="display:flex;gap:8px;">
        <input type="text" name="contenido" placeholder="Añade tu comentario…" required style="margin:0;flex:1;">
        <button class="btn btn-primary" type="submit" style="width:auto;padding:12px 18px;margin:0;">Enviar</button>
      </form>
    </div>
    {coms_html if coms_html else '<div class="card empty-state"><span class="icon">💬</span>Sé el primero en comentar</div>'}
    """

    return render_template_string(
        _base_layout(content), style=STYLE, notif_count=nc, msg_count=mc
    )


# ─────────────────────────────────────────────────────────────────────────────
# PERFIL
# ─────────────────────────────────────────────────────────────────────────────
@app.route('/perfil')
@app.route('/perfil/<username>')
@login_required
def perfil(username=None):
    target = username or session['user_name']
    conn = get_db(); cur = conn.cursor()

    cur.execute("""
        SELECT id, nombre, bio, moto, avatar_url, banner_url, racha,
               verificado, ubicacion, web, fecha_registro
        FROM usuarios WHERE nombre=%s
    """, (target,))
    u = cur.fetchone()
    if not u:
        flash("Usuario no encontrado.", "error")
        cur.close(); conn.close()
        return redirect('/foro')

    uid = u[0]
    cur.execute("SELECT COUNT(*) FROM posts WHERE usuario_id=%s", (uid,))
    posts_n = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM seguidores WHERE seguido_id=%s", (uid,))
    followers = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM seguidores WHERE seguidor_id=%s", (uid,))
    following = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM likes l JOIN posts p ON l.post_id=p.id WHERE p.usuario_id=%s", (uid,))
    total_likes = cur.fetchone()[0]

    is_following = False
    if uid != session['user_id']:
        cur.execute("SELECT 1 FROM seguidores WHERE seguidor_id=%s AND seguido_id=%s",
                    (session['user_id'], uid))
        is_following = cur.fetchone() is not None

    cur.execute("""
        SELECT id, contenido, fecha, imagen_url, categoria,
               (SELECT COUNT(*) FROM likes WHERE post_id=posts.id),
               (SELECT COUNT(*) FROM comentarios WHERE post_id=posts.id)
        FROM posts WHERE usuario_id=%s ORDER BY fecha DESC LIMIT 20
    """, (uid,))
    posts = cur.fetchall()

    tab = request.args.get('tab', 'posts')
    bookmarked = []
    if tab == 'guardados' and uid == session['user_id']:
        cur.execute("""
            SELECT p.id, u.nombre, p.contenido, p.fecha, p.imagen_url, p.categoria
            FROM bookmarks b
            JOIN posts p ON b.post_id=p.id
            JOIN usuarios u ON p.usuario_id=u.id
            WHERE b.usuario_id=%s ORDER BY b.fecha DESC
        """, (session['user_id'],))
        bookmarked = cur.fetchall()

    nc = notif_count_for(session['user_id'])
    mc = msg_count_for(session['user_id'])
    cur.close(); conn.close()

    av_html  = f'<img src="{u[4]}">' if u[4] and u[4].startswith('http') else u[1][0].upper()
    banner_s = f"background-image:url('{u[5]}');" if u[5] else ""
    ver_b    = ' <span class="verified">✓</span>' if u[7] else ''
    racha_b  = insignia_racha(u[6])
    is_own   = uid == session['user_id']

    action_btns = ''
    if is_own:
        action_btns = '<a href="/config" class="btn btn-secondary btn-sm">✏️ Editar perfil</a>'
    else:
        follow_class = 'following' if is_following else ''
        action_btns = f"""
        <form action="/seguir/{uid}" method="POST" style="display:inline;">
          <button class="btn btn-follow {'following' if is_following else ''} btn-sm">
            {'✓ Siguiendo' if is_following else '+ Seguir'}
          </button>
        </form>
        <a href="/mensajes/{username}" class="btn btn-secondary btn-sm">✉️ Mensaje</a>
        """

    content = f"""
    <div class="card profile-card">
      <div class="banner" style="{banner_s}"></div>
      <div class="profile-body">
        <div class="profile-row">
          <div class="profile-av">
            <div class="av av-lg" style="background:{string_to_color(u[1])}">{av_html}</div>
          </div>
          <div style="display:flex;gap:8px;flex-wrap:wrap;padding-top:10px;">
            {action_btns}
          </div>
        </div>
        <h1 class="display" style="font-size:30px;">{u[1]}{ver_b}</h1>
        <p style="color:var(--muted);font-size:14px;">{u[3] or 'Motero'}</p>
        {f'<p style="margin:10px 0;font-size:15px;">{html.escape(u[2])}</p>' if u[2] else ''}
        <div style="display:flex;gap:14px;flex-wrap:wrap;margin-top:8px;font-size:13px;color:var(--muted);">
          {f'<span>📍 {html.escape(u[8])}</span>' if u[8] else ''}
          {f'<a href="{html.escape(u[9])}" target="_blank" style="color:var(--blue);">🔗 Web</a>' if u[9] else ''}
          {f'<span>📅 Desde {u[10].strftime("%b %Y") if u[10] else ""}</span>'}
        </div>
        <div class="profile-stats">
          <div class="stat"><span>{posts_n}</span><small>Posts</small></div>
          <div class="stat"><span>{followers}</span><small>Seguidores</small></div>
          <div class="stat"><span>{following}</span><small>Siguiendo</small></div>
          <div class="stat"><span>{total_likes}</span><small>⛽ Likes</small></div>
          <div class="stat"><span>{racha_b} {u[6]}</span><small>Racha</small></div>
        </div>
      </div>
    </div>

    <div class="tabs">
      <a href="/perfil/{target}?tab=posts" class="tab {'active' if tab=='posts' else ''}">Posts</a>
      {'<a href="/perfil/' + target + '?tab=guardados" class="tab ' + ('active' if tab=='guardados' else '') + '">🔖 Guardados</a>' if is_own else ''}
    </div>
    """

    if tab == 'guardados' and is_own:
        if not bookmarked:
            content += '<div class="card empty-state"><span class="icon">🔖</span>No tienes posts guardados.</div>'
        for b in bookmarked:
            content += f"""
            <div class="card">
              <span class="cat-badge">{CATEGORIA_ICONOS.get(b[5],'🏍️')} {b[5]}</span>
              <div class="post-body">{procesar_texto(b[2])}</div>
              {'<img src="' + b[4] + '" class="post-image">' if b[4] else ''}
              <small class="text-muted">{time_ago(b[3])}</small>
            </div>"""
    else:
        if not posts:
            content += '<div class="card empty-state"><span class="icon">🏍️</span>Aún no hay publicaciones.</div>'
        for p in posts:
            content += f"""
            <div class="card">
              <span class="cat-badge {p[4]}">{CATEGORIA_ICONOS.get(p[4],'🏍️')} {p[4]}</span>
              <div class="post-body">{procesar_texto(p[1])}</div>
              {'<img src="' + p[3] + '" class="post-image">' if p[3] else ''}
              <div style="display:flex;align-items:center;gap:12px;margin-top:10px;font-size:13px;color:var(--muted);">
                <span>⛽ {p[5]}</span>
                <span>💬 {p[6]}</span>
                <span>{time_ago(p[2])}</span>
                <a href="/post/{p[0]}" style="margin-left:auto;color:var(--muted);">Ver →</a>
              </div>
            </div>"""

    return render_template_string(
        _base_layout(content), style=STYLE, active='perfil',
        notif_count=nc, msg_count=mc
    )


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────
@app.route('/config', methods=['GET', 'POST'])
@login_required
def config():
    if request.method == 'POST':
        bio      = request.form.get('bio', '')[:300]
        moto     = request.form.get('moto', '')[:80]
        ubicacion= request.form.get('ubicacion', '')[:60]
        web      = request.form.get('web', '')[:120]
        avatar   = request.files.get('avatar')
        banner   = request.files.get('banner')

        avatar_url = session.get('avatar_url', '')
        banner_url = session.get('banner_url', '')
        if avatar and avatar.filename:
            u = upload_to_imgbb(avatar)
            if u: avatar_url = u; session['avatar_url'] = u
        if banner and banner.filename:
            u = upload_to_imgbb(banner)
            if u: banner_url = u; session['banner_url'] = u

        conn = get_db(); cur = conn.cursor()
        cur.execute(
            "UPDATE usuarios SET bio=%s, moto=%s, ubicacion=%s, web=%s, avatar_url=%s, banner_url=%s WHERE id=%s",
            (bio, moto, ubicacion, web, avatar_url, banner_url, session['user_id'])
        )
        conn.commit(); cur.close(); conn.close()
        flash("Perfil actualizado ✓", "success")
        return redirect(f'/perfil/{session["user_name"]}')

    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT bio, moto, ubicacion, web FROM usuarios WHERE id=%s", (session['user_id'],))
    u = cur.fetchone() or ('','','','')
    nc = notif_count_for(session['user_id'])
    mc = msg_count_for(session['user_id'])
    cur.close(); conn.close()

    content = f"""
    <h2 class="display section-title">✏️ Editar Perfil</h2>
    <div class="card">
      <form method="POST" enctype="multipart/form-data">
        <label>Biografía (máx. 300 caracteres)</label>
        <textarea name="bio" data-max="300">{html.escape(u[0] or '')}</textarea>
        <label>Tu moto</label>
        <input type="text" name="moto" placeholder="Ej: Honda CB650R" value="{html.escape(u[1] or '')}">
        <label>Ubicación</label>
        <input type="text" name="ubicacion" placeholder="Ej: Madrid, España" value="{html.escape(u[2] or '')}">
        <label>Web / Instagram</label>
        <input type="url" name="web" placeholder="https://" value="{html.escape(u[3] or '')}">
        <hr class="divider">
        <label>📷 Foto de perfil</label>
        <input type="file" name="avatar" accept="image/*" style="padding:10px;">
        <label>🖼️ Foto de portada</label>
        <input type="file" name="banner" accept="image/*" style="padding:10px;">
        <button class="btn btn-primary" type="submit">GUARDAR CAMBIOS</button>
      </form>
    </div>

    <div class="card" style="margin-top:14px;">
      <h3 class="display" style="font-size:18px;margin-bottom:12px;">🔐 Cambiar contraseña</h3>
      <form method="POST" action="/cambiar-password">
        <label>Contraseña actual</label>
        <input type="password" name="actual" required>
        <label>Nueva contraseña</label>
        <input type="password" name="nueva" required minlength="6">
        <button class="btn btn-secondary" type="submit" style="width:100%;">ACTUALIZAR CONTRASEÑA</button>
      </form>
    </div>
    """
    return render_template_string(
        _base_layout(content), style=STYLE, notif_count=nc, msg_count=mc
    )


@app.route('/cambiar-password', methods=['POST'])
@login_required
def cambiar_password():
    actual = request.form.get('actual', '')
    nueva  = request.form.get('nueva', '')
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT password FROM usuarios WHERE id=%s", (session['user_id'],))
    u = cur.fetchone()
    if u and check_password_hash(u[0], actual):
        if len(nueva) >= 6:
            cur.execute("UPDATE usuarios SET password=%s WHERE id=%s",
                        (generate_password_hash(nueva), session['user_id']))
            conn.commit()
            flash("Contraseña actualizada ✓", "success")
        else:
            flash("La contraseña debe tener al menos 6 caracteres.", "error")
    else:
        flash("Contraseña actual incorrecta.", "error")
    cur.close(); conn.close()
    return redirect('/config')


# ─────────────────────────────────────────────────────────────────────────────
# BUSCAR / EXPLORAR
# ─────────────────────────────────────────────────────────────────────────────
@app.route('/buscar')
@login_required
def buscar():
    q   = request.args.get('q', '').strip()
    tag = request.args.get('tag', '').strip()
    modo= request.args.get('modo', 'posts')

    conn = get_db(); cur = conn.cursor()
    nc = notif_count_for(session['user_id'])
    mc = msg_count_for(session['user_id'])

    content = f"""
    <h2 class="display section-title">🔍 Explorar</h2>
    <form action="/buscar" method="GET" class="search-bar">
      <input type="text" name="q" placeholder="Buscar posts, usuarios, hashtags…" value="{html.escape(q)}" style="margin:0;">
      <button class="btn btn-primary" type="submit" style="width:auto;margin:0;">Buscar</button>
    </form>
    <div class="tabs" style="margin-bottom:16px;">
      <a href="/buscar?q={q}&modo=posts" class="tab {'active' if modo=='posts' else ''}">Posts</a>
      <a href="/buscar?q={q}&modo=usuarios" class="tab {'active' if modo=='usuarios' else ''}">Moteros</a>
    </div>
    """

    if tag:
        cur.execute("""
            SELECT p.id, u.nombre, p.contenido, p.fecha, u.avatar_url, p.imagen_url, p.categoria,
                   (SELECT COUNT(*) FROM likes WHERE post_id=p.id)
            FROM posts p JOIN usuarios u ON p.usuario_id=u.id
            WHERE p.contenido ILIKE %s AND p.reportes<5
            ORDER BY p.fecha DESC LIMIT 30
        """, (f'%#{tag}%',))
        results = cur.fetchall()
        content += f'<p class="text-muted" style="margin-bottom:12px;">Mostrando posts con <strong class="hashtag">#{tag}</strong></p>'
        for r in results:
            content += _mini_post(r)

    elif modo == 'usuarios' and q:
        cur.execute("""
            SELECT nombre, avatar_url, bio, moto,
                   (SELECT COUNT(*) FROM seguidores WHERE seguido_id=u.id) as followers
            FROM usuarios u WHERE nombre ILIKE %s ORDER BY followers DESC LIMIT 20
        """, (f'%{q}%',))
        users = cur.fetchall()
        if not users:
            content += '<div class="card empty-state"><span class="icon">🏍️</span>Sin resultados.</div>'
        for u in users:
            av  = f'<img src="{u[1]}">' if u[1] and u[1].startswith('http') else u[0][0].upper()
            content += f"""
            <div class="card" style="display:flex;align-items:center;gap:12px;">
              <a href="/perfil/{u[0]}">
                <div class="av av-md" style="background:{string_to_color(u[0])}">{av}</div>
              </a>
              <div style="flex:1;">
                <a href="/perfil/{u[0]}" style="color:var(--text);text-decoration:none;font-weight:700;">{u[0]}</a>
                <div style="font-size:12px;color:var(--muted);">{u[3] or 'Motero'} · {u[4]} seguidores</div>
                {f'<p style="font-size:13px;margin-top:4px;">{html.escape(u[2][:80])}</p>' if u[2] else ''}
              </div>
              <form action="/seguir/{u[0]}" method="POST">
                <button class="btn btn-follow btn-sm">Seguir</button>
              </form>
            </div>"""

    elif q:
        cur.execute("""
            SELECT p.id, u.nombre, p.contenido, p.fecha, u.avatar_url, p.imagen_url, p.categoria,
                   (SELECT COUNT(*) FROM likes WHERE post_id=p.id)
            FROM posts p JOIN usuarios u ON p.usuario_id=u.id
            WHERE (p.contenido ILIKE %s OR u.nombre ILIKE %s) AND p.reportes<5
            ORDER BY p.fecha DESC LIMIT 30
        """, (f'%{q}%', f'%{q}%'))
        results = cur.fetchall()
        if not results:
            content += '<div class="card empty-state"><span class="icon">🔍</span>Sin resultados.</div>'
        for r in results:
            content += _mini_post(r)
    else:
        # Trending / explorar por defecto
        cur.execute("""
            SELECT p.id, u.nombre, p.contenido, p.fecha, u.avatar_url, p.imagen_url, p.categoria,
                   (SELECT COUNT(*) FROM likes WHERE post_id=p.id) as lk
            FROM posts p JOIN usuarios u ON p.usuario_id=u.id
            WHERE p.reportes<5
            ORDER BY lk DESC, p.fecha DESC LIMIT 20
        """)
        results = cur.fetchall()
        content += '<p class="text-muted" style="margin-bottom:12px;">🔥 Posts más populares</p>'
        for r in results:
            content += _mini_post(r)

    cur.close(); conn.close()
    return render_template_string(
        _base_layout(content), style=STYLE, notif_count=nc, msg_count=mc
    )


def _mini_post(r):
    cat_icon = CATEGORIA_ICONOS.get(r[6], '🏍️') if len(r) > 6 else '🏍️'
    av = f'<img src="{r[4]}">' if r[4] and r[4].startswith('http') else r[1][0].upper()
    return f"""
    <div class="card">
      <div class="post-header" style="margin-bottom:8px;">
        <a href="/perfil/{r[1]}">
          <div class="av av-sm" style="background:{string_to_color(r[1])}">{av}</div>
        </a>
        <div class="post-meta">
          <a href="/perfil/{r[1]}" style="text-decoration:none;color:var(--text);font-weight:600;">{r[1]}</a>
          <br><small>{time_ago(r[3])}</small>
        </div>
        <span class="cat-badge">{cat_icon} {r[6] if len(r)>6 else ''}</span>
      </div>
      <div class="post-body">{procesar_texto(r[2])}</div>
      {'<img src="' + r[5] + '" class="post-image">' if r[5] else ''}
      <small class="text-muted" style="margin-top:8px;display:block;">⛽ {r[7] if len(r)>7 else 0} likes</small>
    </div>"""


# ─────────────────────────────────────────────────────────────────────────────
# MENSAJES
# ─────────────────────────────────────────────────────────────────────────────
@app.route('/mensajes')
@login_required
def mensajes():
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT ON (CASE WHEN remitente_id=%s THEN destinatario_id ELSE remitente_id END)
               CASE WHEN remitente_id=%s THEN destinatario_id ELSE remitente_id END as otro_id,
               u.nombre, u.avatar_url,
               m.contenido, m.fecha, m.leido, m.remitente_id
        FROM mensajes m
        JOIN usuarios u ON u.id = CASE WHEN m.remitente_id=%s THEN m.destinatario_id ELSE m.remitente_id END
        WHERE m.remitente_id=%s OR m.destinatario_id=%s
        ORDER BY otro_id, m.fecha DESC
    """, (session['user_id'],)*5)
    convs = cur.fetchall()
    nc = notif_count_for(session['user_id'])
    mc = msg_count_for(session['user_id'])
    cur.close(); conn.close()

    content = '<h2 class="display section-title">✉️ Mensajes</h2>'
    if not convs:
        content += '<div class="card empty-state"><span class="icon">✉️</span>No tienes conversaciones aún.</div>'
    for c in convs:
        av = f'<img src="{c[2]}">' if c[2] and c[2].startswith('http') else c[1][0].upper()
        unread_dot = '<span style="width:8px;height:8px;border-radius:50%;background:var(--blue);display:inline-block;margin-left:4px;"></span>' if not c[5] and c[6] != session['user_id'] else ''
        content += f"""
        <a href="/mensajes/{c[1]}" style="text-decoration:none;color:var(--text);">
          <div class="card" style="display:flex;gap:12px;align-items:center;">
            <div class="av av-md" style="background:{string_to_color(c[1])}">{av}</div>
            <div style="flex:1;min-width:0;">
              <strong>{c[1]}</strong>{unread_dot}
              <div style="font-size:13px;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{html.escape(c[3][:60])}</div>
            </div>
            <small class="text-muted">{time_ago(c[4])}</small>
          </div>
        </a>"""

    return render_template_string(
        _base_layout(content), style=STYLE, notif_count=nc, msg_count=mc
    )


@app.route('/mensajes/<username>', methods=['GET', 'POST'])
@login_required
def chat(username):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT id, nombre, avatar_url FROM usuarios WHERE nombre=%s", (username,))
    otro = cur.fetchone()
    if not otro:
        flash("Usuario no encontrado.", "error")
        cur.close(); conn.close()
        return redirect('/mensajes')

    if request.method == 'POST':
        texto = request.form.get('contenido', '').strip()
        if texto:
            cur.execute(
                "INSERT INTO mensajes (remitente_id, destinatario_id, contenido) VALUES (%s,%s,%s)",
                (session['user_id'], otro[0], texto[:1000])
            )
            conn.commit()
        cur.close(); conn.close()
        return redirect(f'/mensajes/{username}')

    cur.execute("UPDATE mensajes SET leido=TRUE WHERE destinatario_id=%s AND remitente_id=%s",
                (session['user_id'], otro[0]))
    cur.execute("""
        SELECT remitente_id, contenido, fecha FROM mensajes
        WHERE (remitente_id=%s AND destinatario_id=%s)
           OR (remitente_id=%s AND destinatario_id=%s)
        ORDER BY fecha ASC LIMIT 100
    """, (session['user_id'], otro[0], otro[0], session['user_id']))
    msgs = cur.fetchall()
    conn.commit()
    nc = notif_count_for(session['user_id'])
    mc = msg_count_for(session['user_id'])
    cur.close(); conn.close()

    av = f'<img src="{otro[2]}">' if otro[2] and otro[2].startswith('http') else otro[1][0].upper()
    msgs_html = '<div class="msg-list" style="min-height:200px;margin-bottom:16px;">'
    for m in msgs:
        is_me = m[0] == session['user_id']
        msgs_html += f"""
        <div style="display:flex;flex-direction:column;{'align-items:flex-end;' if is_me else ''}">
          <div class="msg-bubble {'me' if is_me else 'them'}">{html.escape(m[1])}</div>
          <div class="msg-meta">{time_ago(m[2])}</div>
        </div>"""
    msgs_html += '</div>'

    content = f"""
    <div class="conversation-header">
      <a href="/mensajes" style="color:var(--muted);text-decoration:none;font-size:20px;">←</a>
      <a href="/perfil/{otro[1]}">
        <div class="av av-md" style="background:{string_to_color(otro[1])}">{av}</div>
      </a>
      <a href="/perfil/{otro[1]}" style="text-decoration:none;color:var(--text);">
        <strong>{otro[1]}</strong>
      </a>
    </div>
    <div class="card">
      {msgs_html}
      <form method="POST" style="display:flex;gap:8px;">
        <input type="text" name="contenido" placeholder="Escribe un mensaje…" required style="margin:0;flex:1;" autocomplete="off">
        <button class="btn btn-primary" type="submit" style="width:auto;padding:12px 16px;margin:0;">↩</button>
      </form>
    </div>
    """

    return render_template_string(
        _base_layout(content), style=STYLE, notif_count=nc, msg_count=mc
    )


# ─────────────────────────────────────────────────────────────────────────────
# RUTAS (moto routes)
# ─────────────────────────────────────────────────────────────────────────────
@app.route('/rutas')
@login_required
def rutas():
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT r.id, u.nombre, r.titulo, r.descripcion, r.distancia,
               r.duracion, r.dificultad, r.imagen_url, r.fecha, r.likes
        FROM rutas r JOIN usuarios u ON r.usuario_id=u.id
        ORDER BY r.fecha DESC LIMIT 30
    """)
    rutas_list = cur.fetchall()
    nc = notif_count_for(session['user_id'])
    mc = msg_count_for(session['user_id'])
    cur.close(); conn.close()

    content = f"""
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
      <h2 class="display section-title" style="margin:0;">🗺️ Rutas</h2>
      <a href="/rutas/nueva" class="btn btn-primary" style="width:auto;padding:10px 18px;">+ Nueva ruta</a>
    </div>
    """

    if not rutas_list:
        content += '<div class="card empty-state"><span class="icon">🗺️</span>Sin rutas todavía. ¡Añade la primera!</div>'

    for r in rutas_list:
        dif_class = f'dif-{r[6]}'
        content += f"""
        <div class="ruta-card">
          {'<img src="' + r[7] + '" class="ruta-img" loading="lazy">' if r[7] else f'<div style="height:120px;background:linear-gradient(135deg,#1a1a2e,#0f3460);display:flex;align-items:center;justify-content:center;font-size:48px;">🛣️</div>'}
          <div class="ruta-body">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px;">
              <h3 class="display" style="font-size:22px;">{html.escape(r[2])}</h3>
              <span class="dif-badge {dif_class}">{r[6]}</span>
            </div>
            <p style="color:var(--muted);font-size:13px;margin-bottom:10px;">{html.escape(r[3][:120]) if r[3] else ''}</p>
            <div class="ruta-stats">
              <div class="ruta-stat"><span>📏 {r[4]:.0f} km</span><small>Distancia</small></div>
              <div class="ruta-stat"><span>⏱ {r[5] or '—'}</span><small>Duración</small></div>
              <div class="ruta-stat"><span>⛽ {r[9]}</span><small>Likes</small></div>
            </div>
            <div style="display:flex;justify-content:space-between;align-items:center;margin-top:10px;">
              <a href="/perfil/{r[1]}" style="color:var(--muted);font-size:13px;">por <strong>{r[1]}</strong> · {time_ago(r[8])}</a>
              <a href="/rutas/{r[0]}" class="btn btn-secondary btn-sm">Ver ruta →</a>
            </div>
          </div>
        </div>"""

    return render_template_string(
        _base_layout(content), style=STYLE, notif_count=nc, msg_count=mc
    )


@app.route('/rutas/nueva', methods=['GET', 'POST'])
@login_required
def nueva_ruta():
    if request.method == 'POST':
        titulo   = request.form.get('titulo', '').strip()[:100]
        desc     = request.form.get('descripcion', '').strip()[:500]
        dist     = float(request.form.get('distancia', 0) or 0)
        dur      = request.form.get('duracion', '')[:30]
        dif      = request.form.get('dificultad', 'Media')
        foto     = request.files.get('foto')
        img_url  = upload_to_imgbb(foto) if foto and foto.filename else ''

        if titulo:
            conn = get_db(); cur = conn.cursor()
            cur.execute(
                "INSERT INTO rutas (usuario_id,titulo,descripcion,distancia,duracion,dificultad,imagen_url) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (session['user_id'], titulo, desc, dist, dur, dif, img_url)
            )
            conn.commit(); cur.close(); conn.close()
            flash("¡Ruta publicada!", "success")
            return redirect('/rutas')
        else:
            flash("El título es obligatorio.", "error")

    nc = notif_count_for(session['user_id'])
    mc = msg_count_for(session['user_id'])
    content = """
    <h2 class="display section-title">🗺️ Nueva Ruta</h2>
    <div class="card">
      <form method="POST" enctype="multipart/form-data">
        <label>Título de la ruta *</label>
        <input type="text" name="titulo" placeholder="Ej: Puerto de Navacerrada" required>
        <label>Descripción</label>
        <textarea name="descripcion" placeholder="Cuéntanos sobre la ruta, puntos de interés, peligros…" data-max="500"></textarea>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
          <div>
            <label>Distancia (km)</label>
            <input type="number" name="distancia" placeholder="150" min="0" step="0.1">
          </div>
          <div>
            <label>Duración</label>
            <input type="text" name="duracion" placeholder="Ej: 3h 30min">
          </div>
        </div>
        <label>Dificultad</label>
        <select name="dificultad">
          <option value="Fácil">🟢 Fácil</option>
          <option value="Media" selected>🟡 Media</option>
          <option value="Difícil">🟠 Difícil</option>
          <option value="Extrema">🔴 Extrema</option>
        </select>
        <label>📷 Foto de la ruta</label>
        <input type="file" name="foto" accept="image/*" style="padding:10px;">
        <button class="btn btn-primary" type="submit">PUBLICAR RUTA</button>
      </form>
    </div>
    """
    return render_template_string(
        _base_layout(content), style=STYLE, notif_count=nc, msg_count=mc
    )


@app.route('/rutas/<int:rid>')
@login_required
def ver_ruta(rid):
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT r.id, u.nombre, r.titulo, r.descripcion, r.distancia,
               r.duracion, r.dificultad, r.imagen_url, r.fecha, r.likes, r.usuario_id
        FROM rutas r JOIN usuarios u ON r.usuario_id=u.id
        WHERE r.id=%s
    """, (rid,))
    r = cur.fetchone()
    if not r:
        flash("Ruta no encontrada.", "error")
        cur.close(); conn.close()
        return redirect('/rutas')
    nc = notif_count_for(session['user_id'])
    mc = msg_count_for(session['user_id'])
    cur.close(); conn.close()

    dif_class = f'dif-{r[6]}'
    content = f"""
    <div class="ruta-card">
      {'<img src="' + r[7] + '" class="ruta-img">' if r[7] else ''}
      <div class="ruta-body">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
          <h1 class="display" style="font-size:28px;">{html.escape(r[2])}</h1>
          <span class="dif-badge {dif_class}">{r[6]}</span>
        </div>
        <p style="color:var(--muted);font-size:14px;margin-bottom:16px;">por <a href="/perfil/{r[1]}" style="color:var(--accent);">{r[1]}</a> · {time_ago(r[8])}</p>
        <p style="font-size:15px;line-height:1.7;margin-bottom:16px;">{html.escape(r[3] or '')}</p>
        <div class="ruta-stats">
          <div class="ruta-stat"><span>📏 {r[4]:.0f} km</span><small>Distancia</small></div>
          <div class="ruta-stat"><span>⏱ {r[5] or '—'}</span><small>Duración</small></div>
          <div class="ruta-stat"><span>⛽ {r[9]}</span><small>Likes</small></div>
        </div>
        <div style="margin-top:14px;display:flex;gap:8px;">
          <form action="/rutas/{rid}/like" method="POST">
            <button class="btn btn-primary" style="width:auto;padding:10px 18px;">⛽ Me gusta</button>
          </form>
          {'<form action="/rutas/' + str(rid) + '/delete" method="POST" onsubmit="return confirm(\'¿Eliminar?\')"><button class="btn btn-secondary">🗑️ Eliminar</button></form>' if r[10]==session['user_id'] else ''}
        </div>
      </div>
    </div>
    """
    return render_template_string(
        _base_layout(content), style=STYLE, notif_count=nc, msg_count=mc
    )


@app.route('/rutas/<int:rid>/like', methods=['POST'])
@login_required
def like_ruta(rid):
    conn = get_db(); cur = conn.cursor()
    cur.execute("UPDATE rutas SET likes=likes+1 WHERE id=%s", (rid,))
    conn.commit(); cur.close(); conn.close()
    return redirect(f'/rutas/{rid}')


@app.route('/rutas/<int:rid>/delete', methods=['POST'])
@login_required
def delete_ruta(rid):
    conn = get_db(); cur = conn.cursor()
    cur.execute("DELETE FROM rutas WHERE id=%s AND usuario_id=%s", (rid, session['user_id']))
    conn.commit(); cur.close(); conn.close()
    flash("Ruta eliminada.", "success")
    return redirect('/rutas')


# ─────────────────────────────────────────────────────────────────────────────
# NOTIFICACIONES
# ─────────────────────────────────────────────────────────────────────────────
@app.route('/notificaciones')
@login_required
def notifs():
    conn = get_db(); cur = conn.cursor()
    cur.execute("UPDATE notificaciones SET leido=TRUE WHERE usuario_id=%s", (session['user_id'],))
    conn.commit()
    cur.execute("""
        SELECT tipo, mensaje, url, fecha, leido
        FROM notificaciones WHERE usuario_id=%s ORDER BY fecha DESC LIMIT 30
    """, (session['user_id'],))
    notifs_list = cur.fetchall()
    mc = msg_count_for(session['user_id'])
    cur.close(); conn.close()

    tipo_icons = {'like':'⛽','comentario':'💬','seguir':'👥','mencion':'@','sistema':'📢'}
    content = '<h2 class="display section-title">🔔 Notificaciones</h2>'

    if not notifs_list:
        content += '<div class="card empty-state"><span class="icon">🔔</span>Sin notificaciones nuevas.</div>'
    else:
        content += '<div class="card" style="padding:0;overflow:hidden;">'
        for n in notifs_list:
            icon = tipo_icons.get(n[0], '📢')
            content += f"""
            <a href="{n[2] or '#'}" class="notif-item {'unread' if not n[4] else ''}">
              <span style="font-size:20px;">{icon}</span>
              <div style="flex:1;">
                <div style="font-size:14px;">{html.escape(n[1])}</div>
                <div style="font-size:11px;color:var(--muted);">{time_ago(n[3])}</div>
              </div>
              {'<div class="notif-dot"></div>' if not n[4] else ''}
            </a>"""
        content += '</div>'

    return render_template_string(
        _base_layout(content), style=STYLE, notif_count=0, msg_count=mc
    )


# ─────────────────────────────────────────────────────────────────────────────
# ACCIONES (like, follow, bookmark, comment, delete, report)
# ─────────────────────────────────────────────────────────────────────────────
@app.route('/post', methods=['POST'])
@login_required
def new_post():
    contenido = request.form.get('contenido', '').strip()[:500]
    categoria = request.form.get('categoria', 'General')
    foto      = request.files.get('foto')
    img_url   = upload_to_imgbb(foto) if foto and foto.filename else ''

    if contenido or img_url:
        conn = get_db(); cur = conn.cursor()
        cur.execute(
            "INSERT INTO posts (usuario_id,contenido,categoria,imagen_url) VALUES (%s,%s,%s,%s)",
            (session['user_id'], contenido, categoria, img_url)
        )
        # racha
        cur.execute("SELECT ultima_actividad FROM usuarios WHERE id=%s", (session['user_id'],))
        last = cur.fetchone()[0]
        today = datetime.now().date()
        if last == today - timedelta(days=1):
            cur.execute("UPDATE usuarios SET racha=racha+1, ultima_actividad=%s WHERE id=%s", (today, session['user_id']))
        elif last != today:
            cur.execute("UPDATE usuarios SET racha=1, ultima_actividad=%s WHERE id=%s", (today, session['user_id']))

        conn.commit()
        # notificar menciones
        for m in re.findall(r'@(\w+)', contenido):
            cur.execute("SELECT id FROM usuarios WHERE nombre=%s", (m,))
            u = cur.fetchone()
            if u and u[0] != session['user_id']:
                crear_notificacion(u[0], 'mencion', f"{session['user_name']} te mencionó en un post", '/foro')
        cur.close(); conn.close()
        flash("¡Publicado! 🏍️", "success")
    return redirect('/foro')


@app.route('/like/<int:pid>', methods=['POST'])
@login_required
def like(pid):
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("INSERT INTO likes (usuario_id,post_id) VALUES (%s,%s)", (session['user_id'], pid))
        cur.execute("SELECT usuario_id FROM posts WHERE id=%s", (pid,))
        owner = cur.fetchone()
        if owner and owner[0] != session['user_id']:
            crear_notificacion(owner[0], 'like', f"A {session['user_name']} le gustó tu post ⛽", f"/post/{pid}")
        conn.commit()
    except Exception:
        conn.rollback()
        cur.execute("DELETE FROM likes WHERE usuario_id=%s AND post_id=%s", (session['user_id'], pid))
        conn.commit()
    cur.close(); conn.close()
    return redirect(request.referrer or '/foro')


@app.route('/bookmark/<int:pid>', methods=['POST'])
@login_required
def bookmark(pid):
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("INSERT INTO bookmarks (usuario_id,post_id) VALUES (%s,%s)", (session['user_id'], pid))
        conn.commit()
    except Exception:
        conn.rollback()
        cur.execute("DELETE FROM bookmarks WHERE usuario_id=%s AND post_id=%s", (session['user_id'], pid))
        conn.commit()
    cur.close(); conn.close()
    return redirect(request.referrer or '/foro')


@app.route('/seguir/<seguido>', methods=['POST'])
@login_required
def seguir(seguido):
    conn = get_db(); cur = conn.cursor()
    # acepta username o id
    if seguido.isdigit():
        cur.execute("SELECT id, nombre FROM usuarios WHERE id=%s", (int(seguido),))
    else:
        cur.execute("SELECT id, nombre FROM usuarios WHERE nombre=%s", (seguido,))
    u = cur.fetchone()
    if not u:
        cur.close(); conn.close()
        return redirect(request.referrer or '/foro')
    uid, uname = u
    try:
        cur.execute("INSERT INTO seguidores (seguidor_id,seguido_id) VALUES (%s,%s)", (session['user_id'], uid))
        crear_notificacion(uid, 'seguir', f"{session['user_name']} empezó a seguirte", f"/perfil/{session['user_name']}")
        conn.commit()
    except Exception:
        conn.rollback()
        cur.execute("DELETE FROM seguidores WHERE seguidor_id=%s AND seguido_id=%s", (session['user_id'], uid))
        conn.commit()
    cur.close(); conn.close()
    return redirect(request.referrer or '/foro')


@app.route('/comment/<int:pid>', methods=['POST'])
@login_required
def comment(pid):
    txt = request.form.get('contenido', '').strip()[:500]
    if txt:
        conn = get_db(); cur = conn.cursor()
        cur.execute("INSERT INTO comentarios (post_id,usuario_id,contenido) VALUES (%s,%s,%s)",
                    (pid, session['user_id'], txt))
        cur.execute("SELECT usuario_id FROM posts WHERE id=%s", (pid,))
        owner = cur.fetchone()
        if owner and owner[0] != session['user_id']:
            crear_notificacion(owner[0], 'comentario', f"{session['user_name']} comentó tu post", f"/post/{pid}")
        conn.commit(); cur.close(); conn.close()
    return redirect(request.referrer or f'/post/{pid}')


@app.route('/delete/<int:pid>', methods=['POST'])
@login_required
def delete(pid):
    conn = get_db(); cur = conn.cursor()
    cur.execute("DELETE FROM posts WHERE id=%s AND usuario_id=%s", (pid, session['user_id']))
    conn.commit(); cur.close(); conn.close()
    flash("Post eliminado.", "success")
    return redirect(request.referrer or '/foro')


@app.route('/report/<int:pid>', methods=['POST'])
@login_required
def report(pid):
    conn = get_db(); cur = conn.cursor()
    cur.execute("UPDATE posts SET reportes=reportes+1 WHERE id=%s", (pid,))
    conn.commit(); cur.close(); conn.close()
    flash("Contenido reportado. Gracias.", "success")
    return redirect(request.referrer or '/foro')


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN
# ─────────────────────────────────────────────────────────────────────────────
@app.route('/admin')
@login_required
@admin_required
def admin():
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM usuarios")
    total_users = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM posts")
    total_posts = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM posts WHERE reportes>=5")
    flagged = cur.fetchone()[0]
    cur.execute("SELECT id, nombre, contenido, reportes FROM posts WHERE reportes>=3 ORDER BY reportes DESC LIMIT 20")
    reported = cur.fetchall()
    cur.execute("SELECT id, nombre, rol, fecha_registro FROM usuarios ORDER BY fecha_registro DESC LIMIT 20")
    users = cur.fetchall()
    nc = notif_count_for(session['user_id'])
    cur.close(); conn.close()

    content = f"""
    <h2 class="display section-title">🔧 Panel de Administración</h2>
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:20px;">
      <div class="card card-tight" style="text-align:center;">
        <div style="font-size:32px;font-weight:700;">{total_users}</div>
        <div class="text-muted">Usuarios</div>
      </div>
      <div class="card card-tight" style="text-align:center;">
        <div style="font-size:32px;font-weight:700;">{total_posts}</div>
        <div class="text-muted">Posts</div>
      </div>
      <div class="card card-tight" style="text-align:center;">
        <div style="font-size:32px;font-weight:700;color:var(--accent);">{flagged}</div>
        <div class="text-muted">Reportados</div>
      </div>
    </div>

    <h3 class="display" style="font-size:18px;margin-bottom:10px;">⚠️ Posts reportados</h3>
    """
    for r in reported:
        content += f"""
        <div class="card" style="border-color:rgba(255,69,0,0.3);">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
            <span class="text-muted">Post #{r[0]} · {r[3]} reportes</span>
            <form action="/admin/delete-post/{r[0]}" method="POST" onsubmit="return confirm('¿Eliminar?')">
              <button class="btn btn-secondary btn-sm" style="color:var(--accent);">🗑️ Eliminar</button>
            </form>
          </div>
          <p style="font-size:13px;">{html.escape(r[2][:150])}</p>
        </div>"""

    content += '<h3 class="display" style="font-size:18px;margin:20px 0 10px;">👥 Usuarios recientes</h3>'
    for u in users:
        content += f"""
        <div class="card card-tight" style="display:flex;align-items:center;gap:10px;">
          <a href="/perfil/{u[1]}" style="flex:1;text-decoration:none;color:var(--text);">
            <strong>{u[1]}</strong>
            <span class="pill" style="margin-left:6px;">{u[2]}</span>
            <span class="text-muted" style="font-size:12px;margin-left:8px;">{u[3].strftime('%d/%m/%Y') if u[3] else ''}</span>
          </a>
          <form action="/admin/verify/{u[0]}" method="POST">
            <button class="btn btn-secondary btn-sm">✓ Verificar</button>
          </form>
        </div>"""

    return render_template_string(
        _base_layout(content), style=STYLE, notif_count=nc, msg_count=0
    )


@app.route('/admin/delete-post/<int:pid>', methods=['POST'])
@login_required
@admin_required
def admin_delete_post(pid):
    conn = get_db(); cur = conn.cursor()
    cur.execute("DELETE FROM posts WHERE id=%s", (pid,))
    conn.commit(); cur.close(); conn.close()
    flash("Post eliminado.", "success")
    return redirect('/admin')


@app.route('/admin/verify/<int:uid>', methods=['POST'])
@login_required
@admin_required
def admin_verify(uid):
    conn = get_db(); cur = conn.cursor()
    cur.execute("UPDATE usuarios SET verificado=NOT verificado WHERE id=%s", (uid,))
    conn.commit(); cur.close(); conn.close()
    return redirect('/admin')


# ─────────────────────────────────────────────────────────────────────────────
# LOGOUT / MISC
# ─────────────────────────────────────────────────────────────────────────────
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')


@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'version': '2.0'})


# ─────────────────────────────────────────────────────────────────────────────
# TEMPLATE HELPER
# ─────────────────────────────────────────────────────────────────────────────
def _base_layout(content: str) -> str:
    uid   = session.get('user_id', 0)
    uname = session.get('user_name', '')
    return f"""<!DOCTYPE html>
<html lang="es" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="description" content="MOTOSCLUB — La red social de los moteros. Comparte rutas, fotos y conecta.">
  <title>MOTOSCLUB</title>
  <style>{{{{ style }}}}</style>
</head>
<body>
  {{% if session.get('user_id') %}}
  <nav class="navbar">
    <div class="nav-inner">
      <a href="/foro" class="nav-brand">MOTOS<span>CLUB</span></a>
      <div class="nav-links">
        <button onclick="toggleTheme()" class="nav-icon" id="thbtn" title="Tema">🌙</button>
        <a href="/buscar" class="nav-icon" title="Explorar">🔍</a>
        <a href="/mensajes" class="nav-icon" title="Mensajes" style="position:relative;">
          ✉️
          {{% if msg_count > 0 %}}<span class="nav-badge">{{{{ msg_count }}}}</span>{{% endif %}}
        </a>
        <a href="/notificaciones" class="nav-icon" title="Notificaciones" style="position:relative;">
          🔔
          {{% if notif_count > 0 %}}<span class="nav-badge">{{{{ notif_count }}}}</span>{{% endif %}}
        </a>
        <a href="/perfil/{{{{ session.get('user_name') }}}}" class="nav-btn {{% if active=='perfil' %}}active{{% endif %}}" title="Mi perfil">Yo</a>
        <a href="/logout" class="nav-btn">Salir</a>
      </div>
    </div>
  </nav>
  {{% endif %}}
  <div class="wrap" style="padding-top:20px;padding-bottom:60px;">
    {{% with messages = get_flashed_messages(with_categories=true) %}}
    {{% if messages %}}
    {{% for cat, msg in messages %}}
    <div class="flash flash-{{{{ cat }}}}">{{{{ msg }}}}</div>
    {{% endfor %}}
    {{% endif %}}
    {{% endwith %}}
    {content}
  </div>
  <script>
  function applyTheme(t){{
    document.documentElement.setAttribute('data-theme',t);
    localStorage.setItem('theme',t);
    var btn=document.getElementById('thbtn');
    if(btn)btn.textContent=t==='light'?'☀️':'🌙';
  }}
  function toggleTheme(){{
    applyTheme(localStorage.getItem('theme')==='light'?'dark':'light');
  }}
  (function(){{ applyTheme(localStorage.getItem('theme')||'dark'); }})();

  function toggleCom(id){{
    var el=document.getElementById('com-'+id);
    if(el)el.style.display=el.style.display==='none'?'block':'none';
  }}

  document.querySelectorAll('textarea[data-max]').forEach(function(ta){{
    var max=parseInt(ta.dataset.max);
    var ctr=document.createElement('div');
    ctr.className='text-muted';
    ctr.style.cssText='text-align:right;margin-top:-6px;margin-bottom:8px;font-size:12px;';
    ta.insertAdjacentElement('afterend',ctr);
    function upd(){{
      var left=max-ta.value.length;
      ctr.textContent=left+' caracteres restantes';
      ctr.style.color=left<20?'var(--accent)':'var(--muted)';
      if(ta.value.length>max) ta.value=ta.value.substring(0,max);
    }}
    ta.addEventListener('input',upd); upd();
  }});

  setTimeout(function(){{
    document.querySelectorAll('.flash').forEach(function(el){{
      el.style.transition='opacity 0.5s';
      el.style.opacity='0';
      setTimeout(function(){{el.remove();}},500);
    }});
  }},4000);

  // Image file preview
  document.querySelectorAll('input[type=file][accept*=image]').forEach(function(inp){{
    inp.addEventListener('change',function(){{
      var label=inp.closest('label');
      if(label && inp.files[0]){{
        label.style.borderColor='var(--green)';
        label.style.color='var(--green)';
        label.querySelector('span') && (label.querySelector('span').textContent=inp.files[0].name);
      }}
    }});
  }});
  </script>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT  (Render.com usa gunicorn, pero esto permite también `python app.py`)
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

# Para Render.com con gunicorn: gunicorn necesita init_db al arrancar
# Se llama aquí al importar el módulo
try:
    if DATABASE_URL:
        init_db()
except Exception as e:
    print(f"[init_db] {e}")
