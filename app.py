# =============================================================================
# MOTOSCLUB - Versión 3.2 (Sintaxis SQL Corregida)
# =============================================================================
import os
import re
import html
import psycopg2
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, redirect, render_template_string, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf.csrf import CSRFProtect, generate_csrf

# -----------------------------------------------------------------------------
# CONFIGURACIÓN
# -----------------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-key-fallback')
app.config['WTF_CSRF_TIME_LIMIT'] = None
csrf = CSRFProtect(app)
DATABASE_URL = os.environ.get('DATABASE_URL')

# -----------------------------------------------------------------------------
# BASE DE DATOS (SQL CORREGIDO)
# -----------------------------------------------------------------------------
def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Tabla Usuarios
    cur.execute("""CREATE TABLE IF NOT EXISTS usuarios (
        id SERIAL PRIMARY KEY, nombre TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
        email TEXT DEFAULT '', bio TEXT DEFAULT '', moto TEXT DEFAULT '',
        avatar_color TEXT DEFAULT '', racha INTEGER DEFAULT 0,
        ultima_actividad DATE, creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP);""")
    
    # Tabla Posts
    cur.execute("""CREATE TABLE IF NOT EXISTS posts (
        id SERIAL PRIMARY KEY, usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
        contenido TEXT NOT NULL, imagen_url TEXT DEFAULT '', categoria TEXT DEFAULT 'General',
        fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP, reportes INTEGER DEFAULT 0);""")
    
    # Tabla Seguidores
    cur.execute("""CREATE TABLE IF NOT EXISTS seguidores (
        seguidor_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
        seguido_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
        PRIMARY KEY (seguidor_id, seguido_id));""")
    
    # Tabla Likes
    cur.execute("""CREATE TABLE IF NOT EXISTS likes (
        usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
        post_id INTEGER REFERENCES posts(id) ON DELETE CASCADE,
        PRIMARY KEY (usuario_id, post_id));""")
    
    # Tabla Comentarios
    cur.execute("""CREATE TABLE IF NOT EXISTS comentarios (
        id SERIAL PRIMARY KEY, post_id INTEGER REFERENCES posts(id) ON DELETE CASCADE,
        usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
        contenido TEXT NOT NULL, fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP);""")
    
    # Tabla Notificaciones
    cur.execute("""CREATE TABLE IF NOT EXISTS notificaciones (
        id SERIAL PRIMARY KEY, usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
        tipo TEXT NOT NULL, mensaje TEXT NOT NULL, url TEXT,
        leido BOOLEAN DEFAULT FALSE, fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP);""")
    
    # Tabla Bookmarks (CORREGIDO: Añadido paréntesis de cierre)
    cur.execute("""CREATE TABLE IF NOT EXISTS bookmarks (
        usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
        post_id INTEGER REFERENCES posts(id) ON DELETE CASCADE,
        PRIMARY KEY (usuario_id, post_id));""")

    # Migraciones: Añadir columnas si faltan (para no borrar datos)
    cols = [("avatar_color", "TEXT DEFAULT ''"), ("bio", "TEXT DEFAULT ''"), ("moto", "TEXT DEFAULT ''"), ("racha", "INTEGER DEFAULT 0")]
    for c, t in cols:
        try:
            cur.execute(f"ALTER TABLE usuarios ADD COLUMN {c} {t}")
            conn.commit()
        except: conn.rollback()

    conn.commit()
    cur.close()
    conn.close()

# -----------------------------------------------------------------------------
# HELPERS
# -----------------------------------------------------------------------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Inicia sesión", "error")
            return redirect('/')
        return f(*args, **kwargs)
    return decorated_function

def procesar_texto(text):
    text = html.escape(text)
    text = re.sub(r'(https?://[^\s]+?\.(png|jpg|jpeg|gif|webp)(\?[^\s]*)?)', r'<img src="\1" class="post-image" loading="lazy">', text)
    text = re.sub(r'@(\w+)', r'<a href="/perfil/\1">@\1</a>', text)
    text = re.sub(r'#(\w+)', r'<a href="/buscar?tag=\1">#\1</a>', text)
    return text

def string_to_color(s):
    return f"hsl({sum(ord(c) for c in s) % 360}, 70%, 50%)"

def time_ago(dt):
    if not dt: return "?"
    delta = datetime.now() - dt
    if delta.days > 0: return f"{delta.days}d"
    if delta.seconds >= 3600: return f"{delta.seconds//3600}h"
    if delta.seconds >= 60: return f"{delta.seconds//60}m"
    return "ahora"

def get_notif_count(user_id):
    try:
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM notificaciones WHERE usuario_id=%s AND leido=FALSE", (user_id,))
        c = cur.fetchone()[0]; cur.close(); conn.close(); return c
    except: return 0

# -----------------------------------------------------------------------------
# CSS
# -----------------------------------------------------------------------------
STYLE = """
:root{--bg:#050505;--surface:#1C1C1E;--text:#F5F5F7;--text-dim:#8E8E93;--border:#3A3A3C;--accent:#FF3B30;--blue:#0A84FF;--radius:16px}
[data-theme="light"]{--bg:#F2F2F7;--surface:#FFFFFF;--text:#1D1D1F;--text-dim:#636366;--border:#D1D1D6}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;background:var(--bg);color:var(--text);margin:0;line-height:1.5;font-size:15px}
.container{max-width:720px;margin:0 auto;padding:0 16px}
.navbar{position:sticky;top:0;background:rgba(5,5,5,0.8);backdrop-filter:blur(20px);border-bottom:1px solid var(--border);padding:12px 0}
.nav-inner{display:flex;justify-content:space-between;align-items:center;max-width:720px;margin:0 auto;padding:0 16px}
.nav-brand{font-weight:800;font-size:20px;color:var(--text)}
.nav-btn{background:transparent;border:1px solid var(--border);color:var(--text);padding:8px 14px;border-radius:20px;font-size:13px;font-weight:600;cursor:pointer;text-decoration:none}
.nav-btn.active{background:var(--accent);border-color:var(--accent);color:white}
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:20px;margin-bottom:16px}
input,textarea{width:100%;background:var(--bg);border:1px solid var(--border);color:var(--text);padding:12px;border-radius:12px;font-family:inherit;font-size:15px;outline:none}
.btn{background:var(--accent);color:white;border:none;padding:12px 20px;border-radius:12px;font-weight:600;cursor:pointer;width:100%}
.avatar{width:40px;height:40px;border-radius:50%;background:var(--surface);display:flex;align-items:center;justify-content:center;font-weight:600;color:white;flex-shrink:0}
.post-content{white-space:pre-wrap;word-break:break-word}
.post-image{width:100%;border-radius:12px;margin-top:10px}
.post-actions{display:flex;gap:8px;border-top:1px solid var(--border);padding-top:12px;margin-top:12px}
.action-btn{background:transparent;border:none;color:var(--text-dim);padding:6px 12px;border-radius:8px;cursor:pointer;font-size:14px}
.action-btn.active{color:var(--accent)}
.comments{display:none;margin-top:12px;padding-top:12px;border-top:1px solid var(--border)}
.comments.show{display:block}
.flash{padding:12px;border-radius:12px;margin-bottom:16px;font-weight:500}
.flash-error{background:rgba(255,59,48,0.1);color:#ff6b61;border:1px solid rgba(255,59,48,0.3)}
.flash-success{background:rgba(48,209,88,0.1);color:#4fd676;border:1px solid rgba(48,209,88,0.3)}
"""

# -----------------------------------------------------------------------------
# LAYOUT
# -----------------------------------------------------------------------------
BASE_LAYOUT = """
<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>MOTOSCLUB</title><style>{{ style }}</style></head>
<body>
<nav class="navbar"><div class="nav-inner">
<a href="/foro" class="nav-brand">🏍️ MOTOSCLUB</a>
<div style="display:flex;gap:8px">
<button class="nav-btn" id="th" onclick="document.documentElement.setAttribute('data-theme',document.documentElement.getAttribute('data-theme')==='light'?'dark':'light')">🌙</button>
<a href="/buscar" class="nav-btn">🔍</a>
<a href="/notificaciones" class="nav-btn">🔔{% if n>0 %}({{ n }}){% endif %}</a>
<a href="/perfil" class="nav-btn active">Yo</a>
<a href="/logout" class="nav-btn">Salir</a>
</div></div></nav>
<div class="container" style="padding-top:20px">
{% with m=get_flashed_messages(with_categories=true)%}{%if m%}{%for c,msg in m%}<div class="flash flash-{{c}}">{{msg}}</div>{%endfor%}{%endif%}{%endwith%}
{{ content|safe }}
</div><script>function toggleComments(id){document.getElementById('c'+id).classList.toggle('show')}</script>
</body></html>"""

def render_page(content, n=0):
    return render_template_string(BASE_LAYOUT, style=STYLE, content=content, n=n)

# -----------------------------------------------------------------------------
# RUTAS
# -----------------------------------------------------------------------------
@app.route('/', methods=['GET', 'POST'])
def login():
    if 'user_id' in session: return redirect('/foro')
    tk = generate_csrf()
    reg = request.args.get('register') == '1'
    html = f"""
    <div style="min-height:80vh;display:flex;align-items:center;justify-content:center">
    <div class="card" style="width:100%;max-width:400px;text-align:center">
    <h1 style="font-size:32px;margin-bottom:20px">🏍️ MOTOSCLUB</h1>
    <form method="POST">
    <input type="hidden" name="csrf_token" value="{tk}"/>
    <input type="text" name="nombre" placeholder="Usuario" required minlength="3" autocomplete="username">
    <input type="password" name="password" placeholder="Contraseña" required minlength="6">
    <button class="btn" name="btn" value="{'reg' if reg else 'log'}">{'CREAR CUENTA' if reg else 'ENTRAR'}</button>
    </form>
    <p style="margin-top:16px;color:var(--text-dim)">{'<a href="/">Entrar</a>' if reg else '<a href="/?register=1">Registrar</a>'}</p>
    </div></div>"""
    
    if request.method == 'POST':
        nom = request.form.get('nombre','').strip()
        pwd = request.form.get('password','')
        btn = request.form.get('btn')
        if len(nom)<3 or len(pwd)<6: flash("Mín 3 caracs y 6 pass", "error")
        else:
            conn = get_db_connection(); cur = conn.cursor()
            if btn == 'reg':
                try:
                    cur.execute("INSERT INTO usuarios (nombre,password,avatar_color) VALUES (%s,%s,%s)", (nom, generate_password_hash(pwd), string_to_color(nom)))
                    conn.commit(); flash("¡Creado! Entra ahora.", "success")
                except: flash("Usuario ya existe", "error")
            else:
                cur.execute("SELECT id,password,avatar_color FROM usuarios WHERE nombre=%s", (nom,))
                u = cur.fetchone()
                if u and check_password_hash(u[1], pwd):
                    session['user_id']=u[0]; session['user_name']=nom; session['avatar_color']=u[2]
                    return redirect('/foro')
                flash("Datos incorrectos", "error")
            cur.close(); conn.close()
    return render_page(html)

@app.route('/foro')
@login_required
def foro():
    tk = generate_csrf()
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("SELECT seguido_id FROM seguidores WHERE seguidor_id=%s", (session['user_id'],))
    fids = [r[0] for r in cur.fetchall()] + [session['user_id']]
    
    cur.execute("""SELECT p.id,u.nombre,u.avatar_color,p.contenido,p.imagen_url,p.fecha,p.usuario_id,
    (SELECT COUNT(*) FROM likes WHERE post_id=p.id), EXISTS(SELECT 1 FROM likes WHERE post_id=p.id AND usuario_id=%s)
    FROM posts p JOIN usuarios u ON p.usuario_id=u.id WHERE p.usuario_id=ANY(%s) ORDER BY p.fecha DESC LIMIT 20""",
    (session['user_id'], tuple(fids)))
    
    rows = cur.fetchall(); cur.close(); conn.close()
    
    posts = ""
    for p in rows:
        pid, nom, col, txt, img, fecha, uid, lks, liked = p
        del_btn = f'<form action="/del/{pid}" method="POST" style="display:inline"><input type="hidden" name="csrf_token" value="{tk}"/><button class="action-btn">🗑️</button></form>' if uid == session['user_id'] else ""
        posts += f"""
        <div class="card"><div style="display:flex;gap:10px;margin-bottom:10px">
        <div class="avatar" style="background:{col}">{nom[0].upper()}</div>
        <div style="flex:1"><b>{nom}</b><br><span style="font-size:12px;color:var(--text-dim)">{time_ago(fecha)}</span></div>{del_btn}</div>
        <div class="post-content">{procesar_texto(txt)}</div>
        {f'<img src="{img}" class="post-image">' if img else ''}
        <div class="post-actions">
        <form action="/like/{pid}" method="POST" style="display:inline"><input type="hidden" name="csrf_token" value="{tk}"/><button class="action-btn {'active' if liked else ''}">⛽ {lks}</button></form>
        <button class="action-btn" onclick="toggleComments({pid})">💬</button>
        </div>
        <div class="comments" id="c{pid}"><form action="/comment/{pid}" method="POST" style="display:flex;gap:5px">
        <input type="hidden" name="csrf_token" value="{tk}"/>
        <input type="text" name="txt" placeholder="Comentar..." style="flex:1"><button class="btn" style="width:auto">Env</button>
        </form></div></div>"""

    form = f"""<div class="card"><form method="POST" action="/post">
    <input type="hidden" name="csrf_token" value="{tk}"/>
    <textarea name="txt" placeholder="¿Qué ruta haces?"></textarea>
    <input type="url" name="img" placeholder="URL imagen (opcional)">
    <button class="btn">PUBLICAR</button></form></div>"""
    
    return render_page(form + (posts if rows else "<div class='card text-center'>Sin publicaciones</div>"), n=get_notif_count(session['user_id']))

@app.route('/post', methods=['POST'])
@login_required
def post():
    txt = request.form.get('txt','').strip()
    img = request.form.get('img','')
    if txt or img:
        conn=get_db_connection(); cur=conn.cursor()
        cur.execute("INSERT INTO posts (usuario_id,contenido,imagen_url) VALUES (%s,%s,%s)", (session['user_id'],txt,img))
        conn.commit(); cur.close(); conn.close()
        flash("¡Publicado!", "success")
    return redirect('/foro')

@app.route('/like/<int:pid>', methods=['POST'])
@login_required
def like(pid):
    conn=get_db_connection(); cur=conn.cursor()
    try: cur.execute("INSERT INTO likes (usuario_id,post_id) VALUES (%s,%s)", (session['user_id'],pid)); conn.commit()
    except: conn.rollback(); cur.execute("DELETE FROM likes WHERE usuario_id=%s AND post_id=%s", (session['user_id'],pid)); conn.commit()
    cur.close(); conn.close()
    return redirect('/foro')

@app.route('/del/<int:pid>', methods=['POST'])
@login_required
def delete(pid):
    conn=get_db_connection(); cur=conn.cursor()
    cur.execute("DELETE FROM posts WHERE id=%s AND usuario_id=%s", (pid, session['user_id']))
    conn.commit(); cur.close(); conn.close()
    return redirect('/foro')

@app.route('/comment/<int:pid>', methods=['POST'])
@login_required
def comment(pid):
    t = request.form.get('txt','').strip()
    if t:
        conn=get_db_connection(); cur=conn.cursor()
        cur.execute("INSERT INTO comentarios (post_id,usuario_id,contenido) VALUES (%s,%s,%s)", (pid,session['user_id'],t))
        conn.commit(); cur.close(); conn.close()
    return redirect('/foro')

@app.route('/perfil')
@login_required
def perfil():
    conn=get_db_connection(); cur=conn.cursor()
    cur.execute("SELECT bio,moto,avatar_color,racha FROM usuarios WHERE id=%s", (session['user_id'],))
    u = cur.fetchone()
    bio, moto, col, racha = u
    cur.execute("SELECT COUNT(*) FROM posts WHERE usuario_id=%s", (session['user_id'],)); pc=cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM seguidores WHERE seguido_id=%s", (session['user_id'],)); fl=cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM seguidores WHERE seguidor_id=%s", (session['user_id'],)); fg=cur.fetchone()[0]
    cur.close(); conn.close()
    
    html = f"""<div class="card" style="padding:0;overflow:hidden">
    <div style="height:100px;background:linear-gradient(45deg, var(--accent), var(--blue))"></div>
    <div style="padding:20px">
    <div class="avatar" style="width:60px;height:60px;font-size:24px;background:{col}">{session['user_name'][0].upper()}</div>
    <h2>{session['user_name']}</h2><p style="color:var(--text-dim)">{moto or 'Sin moto'}</p>
    <p style="margin:16px 0">{bio or 'Sin bio'}</p>
    <div style="display:flex;gap:20px;text-align:center;border-top:1px solid var(--border);padding-top:16px">
    <div><b>{pc}</b><br><small>Posts</small></div>
    <div><b>{fl}</b><br><small>Seguidores</small></div>
    <div><b>{fg}</b><br><small>Siguiendo</small></div>
    <div><b>🔥{racha}</b><br><small>Racha</small></div>
    </div></div></div>"""
    return render_page(html, n=get_notif_count(session['user_id']))

@app.route('/buscar')
@login_required
def search():
    q = request.args.get('q','')
    conn=get_db_connection(); cur=conn.cursor()
    cur.execute("SELECT p.id,u.nombre,p.contenido FROM posts p JOIN usuarios u ON p.usuario_id=u.id WHERE p.contenido ILIKE %s LIMIT 10", (f'%{q}%',))
    rows = cur.fetchall(); cur.close(); conn.close()
    res = "".join([f"<div class='card'><b>{n}</b><p>{c[:100]}</p></div>" for i,n,c in rows])
    return render_page(f"<h2>Buscar: {q}</h2>{res}")

@app.route('/notificaciones')
@login_required
def notifs():
    conn=get_db_connection(); cur=conn.cursor()
    cur.execute("UPDATE notificaciones SET leido=TRUE WHERE usuario_id=%s", (session['user_id'],))
    conn.commit()
    cur.execute("SELECT mensaje FROM notificaciones WHERE usuario_id=%s ORDER BY fecha DESC LIMIT 20", (session['user_id'],))
    rows = cur.fetchall(); cur.close(); conn.close()
    res = "".join([f"<div class='card'>{r[0]}</div>" for r in rows])
    return render_page(f"<h2>Notificaciones</h2>{res if rows else '<p>No tienes notis</p>'}", n=0)

@app.route('/logout')
def out(): session.clear(); return redirect('/')

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT',5000)), debug=False)
