import os
import re
import html
import psycopg2
from flask import Flask, request, redirect, render_template_string, session, flash, url_for, get_flashed_messages
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.urandom(24)

# --- CONFIGURACIÓN DB ---
DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Tabla Usuarios (Añadimos bio y rol)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id SERIAL PRIMARY KEY,
            nombre TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            bio TEXT DEFAULT '',
            moto TEXT DEFAULT '',
            rol TEXT DEFAULT 'user'
        );
    """)
    # Tabla Posts (Añadimos categoria)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id SERIAL PRIMARY KEY,
            usuario_id INTEGER REFERENCES usuarios(id),
            contenido TEXT NOT NULL,
            categoria TEXT DEFAULT 'General',
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    # Tabla Likes (Gas)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS likes (
            usuario_id INTEGER REFERENCES usuarios(id),
            post_id INTEGER REFERENCES posts(id),
            PRIMARY KEY (usuario_id, post_id)
        );
    """)
    # Tabla Grupos y Comentarios (Mantenemos lo anterior)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS grupos (id SERIAL PRIMARY KEY, nombre TEXT UNIQUE, descripcion TEXT, creador_id INTEGER);
        CREATE TABLE IF NOT EXISTS grupo_miembros (grupo_id INTEGER, usuario_id INTEGER);
        CREATE TABLE IF NOT EXISTS comentarios (id SERIAL PRIMARY KEY, post_id INTEGER, usuario_id INTEGER, contenido TEXT, fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
    """)

    # Migraciones suaves (Añadir columnas si no existen)
    try: cur.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS bio TEXT;")
    except: pass
    try: cur.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS moto TEXT;")
    except: pass
    try: cur.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS rol TEXT DEFAULT 'user';")
    except: pass
    try: cur.execute("ALTER TABLE posts ADD COLUMN IF NOT EXISTS categoria TEXT;")
    except: pass

    conn.commit()
    cur.close()
    conn.close()

# --- ESTILO RACING PRO ---
STYLE = """
:root { 
    --bg: #050505; --card: #111111; --text: #ffffff; 
    --accent-red: #FF0F0F; --accent-blue: #0074D9; --border: #222222;
}
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: var(--bg); color: var(--text); line-height: 1.5; margin: 0; padding: 0; }
a { color: var(--accent-blue); text-decoration: none; }
.navbar { background: #000; border-bottom: 1px solid var(--border); padding: 15px 20px; display: flex; align-items: center; justify-content: space-between; position: sticky; top: 0; z-index: 1000; }
.nav-brand { font-size: 1.2rem; font-weight: 800; color: white; }
.nav-links { display: flex; gap: 15px; align-items: center; }
.nav-btn { padding: 8px 16px; border-radius: 6px; background: transparent; color: #ccc; border: 1px solid #333; font-weight: 600; text-decoration: none; transition: 0.2s; }
.nav-btn.active { background: var(--accent-red); color: white; border-color: var(--accent-red); }
.container { max-width: 800px; margin: 20px auto; padding: 0 20px; }
.card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 20px; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
input, textarea, select { width: 100%; background: #0a0a0a; border: 1px solid #333; color: white; padding: 12px; border-radius: 8px; box-sizing: border-box; margin-bottom: 10px; font-family: inherit; }
button.btn-main { background: var(--accent-red); color: white; border: none; padding: 12px 24px; border-radius: 6px; font-weight: 700; cursor: pointer; width: 100%; }
button.btn-main:hover { background: #cc0000; }
.btn-secondary { background: #222; border: 1px solid #444; color: white; padding: 5px 10px; border-radius: 4px; font-size: 12px; cursor: pointer; }

/* Posts */
.post-header { display: flex; justify-content: space-between; margin-bottom: 10px; }
.post-actions { display: flex; gap: 10px; align-items: center; margin-top: 10px; font-size: 13px; }
.badge { font-size: 10px; padding: 2px 6px; border-radius: 4px; text-transform: uppercase; font-weight: bold; }
.badge-route { background: #1e3a5f; color: #4da6ff; }
.badge-mech { background: #4a1e1e; color: #ff4d4d; }
.badge-sale { background: #2e4a1e; color: #4dff4d; }
.avatar { width: 40px; height: 40px; border-radius: 50%; background: var(--accent-blue); color: white; display: flex; align-items: center; justify-content: center; font-weight: bold; flex-shrink: 0; }
.post-image { max-width: 100%; border-radius: 8px; margin-top: 10px; }

/* Buscador */
.search-box { display: flex; gap: 10px; margin-bottom: 20px; }

/* Modal Edición */
.modal-bg { position: fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.8); display:none; justify-content:center; align-items:center; z-index: 2000; }
.modal-content { background: #111; padding: 20px; border-radius: 10px; width: 400px; max-width: 90%; }
"""

# --- FILTROS JINJA ---
def url_to_image(text):
    # Seguro: Escapamos HTML primero
    text = html.escape(text)
    # Regex para imágenes
    pattern = r'(https?://[^\s]+?\.(png|jpg|jpeg|gif|webp))'
    return re.sub(pattern, r'<img src="\1" class="post-image">', text)

def string_to_color(s):
    hash = 0
    for char in s: hash = ord(char) + ((hash << 5) - hash)
    h = hash % 360
    return f"hsl({h}, 70%, 40%)"

def time_ago(dt):
    delta = datetime.now() - dt
    if delta.days > 0: return f"hace {delta.days}d"
    if delta.seconds >= 3600: return f"hace {delta.seconds // 3600}h"
    if delta.seconds >= 60: return f"hace {delta.seconds // 60}m"
    return "ahora"

# --- PLANTILLAS ---

BASE = """
<!DOCTYPE html><html><head><title>MotosClub Pro</title><style>{{ style }}</style></head>
<body>
    <nav class="navbar">
        <div class="nav-brand">🏍️ MotosClub</div>
        <div class="nav-links">
            <a href="/foro" class="nav-btn {% if active=='foro' %}active{% endif %}">Muro</a>
            <a href="/grupos" class="nav-btn {% if active=='grupos' %}active{% endif %}">Grupos</a>
            <a href="/perfil" class="nav-btn {% if active=='perfil' %}active{% endif %}">Perfil</a>
            {% if session.get('rol') == 'admin' %}
                <a href="/admin" class="nav-btn" style="border-color:gold; color:gold;">👑 Admin</a>
            {% endif %}
            <a href="/logout" class="nav-btn" style="border:none; color:#666;">Salir</a>
        </div>
    </nav>
    <div class="container">
        {% with messages = get_flashed_messages() %} {% if messages %} <div style="background:#ff453a; color:white; padding:10px; border-radius:5px; margin-bottom:10px;">{{ messages[0] }}</div> {% endif %} {% endwith %}
        {% block content %}{% endblock %}
    </div>
</body></html>
"""

LOGIN_PAGE = BASE.replace("{% block content %}", """
<div class="card" style="max-width:400px; margin:50px auto;">
    <h2 style="text-align:center;">Iniciar Sesión</h2>
    <form method="POST">
        <input type="text" name="nombre" placeholder="Usuario" required>
        <input type="password" name="password" placeholder="Contraseña" required>
        <button type="submit" name="login" class="btn-main">Entrar</button>
        <button type="submit" name="register" class="btn-main" style="background:#333; margin-top:5px;">Registrar</button>
    </form>
</div>
""")

FORO_PAGE = BASE.replace("{% block content %}", """
<!-- Buscador -->
<form action="/buscar" method="GET" class="search-box">
    <input type="text" name="q" placeholder="Buscar rutas, motos, piezas..." style="margin-bottom:0;">
    <button type="submit" class="btn-main" style="width:auto;">🔍</button>
</form>

<!-- Publicar -->
<div class="card">
    <form method="POST" action="/post">
        <textarea name="contenido" rows="2" placeholder="¿Qué rutas vas a hacer hoy?"></textarea>
        <select name="categoria" style="width:auto; display:inline-block;">
            <option value="General">General</option>
            <option value="Ruta">🛣️ Ruta</option>
            <option value="Mecanica">🔧 Mecánica</option>
            <option value="Venta">💰 Compra/Venta</option>
        </select>
        <button type="submit" class="btn-main" style="width:auto; display:inline-block; vertical-align:top;">Publicar</button>
    </form>
</div>

<!-- Posts -->
{% for p in posts %}
<div class="card" id="post-{{ p[0] }}">
    <div class="post-header">
        <div style="display:flex; gap:10px; align-items:center;">
            <div class="avatar" style="background:{{ p[6] }}">{{ p[1][0] }}</div>
            <div>
                <strong>{{ p[1] }}</strong> 
                {% if p[4] == 'Ruta' %}<span class="badge badge-route">Ruta</span>{% endif %}
                {% if p[4] == 'Mecanica' %}<span class="badge badge-mech">Mecánica</span>{% endif %}
                {% if p[4] == 'Venta' %}<span class="badge badge-sale">Venta</span>{% endif %}
                <div style="font-size:12px; color:#555;">{{ p[5] }}</div>
            </div>
        </div>
        {% if session.get('user_id') == p[7] or session.get('rol') == 'admin' %}
        <div style="display:flex; gap:5px;">
            {% if session.get('user_id') == p[7] %}<button onclick="openEdit({{ p[0] }}, '{{ p[2] }}')" class="btn-secondary">✏️ Editar</button>{% endif %}
            <form action="/delete/{{ p[0] }}" method="POST" onsubmit="return confirm('¿Borrar post?');"><button class="btn-secondary">🗑️</button></form>
        </div>
        {% endif %}
    </div>
    <div>{{ p[3] | safe }}</div>
    
    <!-- Acciones -->
    <div class="post-actions">
        <form action="/like/{{ p[0] }}" method="POST"><button class="btn-secondary" style="background:#222; border:none;">⛽ Gas ({{ p[8] }})</button></form>
        <button class="btn-secondary" onclick="toggleComments({{ p[0] }})">💬 {{ p[9] }}</button>
    </div>

    <!-- Comentarios -->
    <div id="comments-{{ p[0] }}" style="display:none; margin-top:10px; border-top:1px solid #222; padding-top:10px;">
        <form action="/comment/{{ p[0] }}" method="POST" style="display:flex; gap:5px;">
            <input type="text" name="contenido" placeholder="Respuesta..." required>
            <button class="btn-secondary">Enviar</button>
        </form>
        {% for c in p[10] %}
        <div style="background:#1a1a1a; padding:8px; margin-top:5px; border-radius:5px; font-size:14px;">
            <strong style="color:{{ c[3] }}">{{ c[0] }}</strong>: {{ c[1] }}
        </div>
        {% endfor %}
    </div>
</div>
{% endfor %}

<script>
function toggleComments(id) { var x = document.getElementById('comments-' + id); x.style.display = (x.style.display === 'none') ? 'block' : 'none'; }
function openEdit(id, text) { var newTxt = prompt("Editar publicación:", text.replace(/<br>/g, '\n')); if(newTxt){ window.location.href = "/edit/" + id + "?txt=" + encodeURIComponent(newTxt); } }
</script>
""")

PERFIL_PAGE = BASE.replace("{% block content %}", """
<div class="card">
    <h2>Tu Perfil</h2>
    <div style="display:flex; align-items:center; gap:15px; margin-bottom:20px;">
        <div class="avatar" style="width:60px; height:60px; font-size:24px;">{{ session.get('user_name')[0] }}</div>
        <div>
            <h3 style="margin:0;">@{{ session.get('user_name') }}</h3>
            <span style="color:#555;">{{ session.get('moto', 'Sin moto definida') }}</span>
        </div>
    </div>
    <form method="POST" action="/perfil">
        <label>Tu Moto:</label>
        <input type="text" name="moto" placeholder="Ej: Yamaha MT-07" value="{{ session.get('moto', '') }}">
        <label>Tu Bio:</label>
        <textarea name="bio" rows="3" placeholder="Cuéntanos sobre ti...">{{ session.get('bio', '') }}</textarea>
        <button class="btn-main">Guardar Perfil</button>
    </form>
</div>
""")

ADMIN_PAGE = BASE.replace("{% block content %}", """
<h2>Panel de Administración 🛡️</h2>
<p>Usuarios Registrados: {{ stats[0] }} | Total Posts: {{ stats[1] }}</p>
<div class="card" style="background:#1a0000; border-color:var(--accent-red);">
    <h3>Últimas actividades sospechosas o reportes (Simulación)</h3>
    <p>Aquí podrías ver posts reportados. Por ahora tienes poder total para borrar cualquier post desde el muro principal.</p>
</div>
""")

# --- RUTAS ---

@app.route('/', methods=['GET', 'POST'])
def login():
    if 'user_id' in session: return redirect('/foro')
    
    if request.method == 'POST':
        nombre = request.form['nombre'].strip()
        passw = request.form['password']
        conn = get_db_connection()
        cur = conn.cursor()

        if 'register' in request.form:
            try:
                hash_p = generate_password_hash(passw)
                # El primer usuario es ADMIN
                cur.execute("SELECT COUNT(*) FROM usuarios")
                count = cur.fetchone()[0]
                rol = 'admin' if count == 0 else 'user'
                
                cur.execute("INSERT INTO usuarios (nombre, password, rol) VALUES (%s, %s, %s)", (nombre, hash_p, rol))
                conn.commit()
                flash(f"¡Registrado como {rol}! Ahora entra.")
            except: flash("Error: Usuario ya existe.")
        
        elif 'login' in request.form:
            cur.execute("SELECT id, password, bio, moto, rol FROM usuarios WHERE nombre = %s", (nombre,))
            u = cur.fetchone()
            if u and check_password_hash(u[1], passw):
                session['user_id'] = u[0]
                session['user_name'] = nombre
                session['bio'] = u[2] or ''
                session['moto'] = u[3] or ''
                session['rol'] = u[4] or 'user'
                cur.close(); conn.close()
                return redirect('/foro')
            else: flash("Datos incorrectos.")
        
        cur.close(); conn.close()
    
    return render_template_string(LOGIN_PAGE, style=STYLE)

@app.route('/foro')
def foro():
    if 'user_id' not in session: return redirect('/')
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT p.id, u.nombre, p.contenido, p.fecha, p.categoria, u.moto, u.nombre, p.usuario_id,
               (SELECT COUNT(*) FROM likes l WHERE l.post_id = p.id),
               (SELECT COUNT(*) FROM comentarios c WHERE c.post_id = p.id)
        FROM posts p JOIN usuarios u ON p.usuario_id = u.id
        ORDER BY p.fecha DESC LIMIT 50
    """)
    raw = cur.fetchall()
    
    posts = []
    for p in raw:
        # ID, Autor, ContenidoHTML, Fecha, Categoria, TimeAgo, Color, UserID, Likes, Comments, ListaComs
        # P[2] es contenido crudo -> lo limpiamos y convertimos
        safe_content = url_to_image(p[2])
        
        # Cargar comentarios
        cur.execute("SELECT u.nombre, c.contenido, c.fecha, '' FROM comentarios c JOIN usuarios u ON c.usuario_id = u.id WHERE c.post_id = %s ORDER BY c.fecha ASC LIMIT 5", (p[0],))
        raw_c = cur.fetchall()
        coms = [(c[0], c[1], time_ago(c[2]), string_to_color(c[0])) for c in raw_c]
        
        posts.append((p[0], p[1], safe_content, p[3], p[4], time_ago(p[3]), string_to_color(p[1]), p[7], p[8], p[9], coms))

    cur.close(); conn.close()
    return render_template_string(FORO_PAGE, style=STYLE, posts=posts, active='foro')

@app.route('/post', methods=['POST'])
def post():
    if 'user_id' not in session: return redirect('/')
    txt = request.form['contenido']
    cat = request.form.get('categoria', 'General')
    if len(txt) > 0:
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("INSERT INTO posts (usuario_id, contenido, categoria) VALUES (%s, %s, %s)", (session['user_id'], txt, cat))
        conn.commit(); cur.close(); conn.close()
    return redirect('/foro')

@app.route('/delete/<int:pid>', methods=['POST'])
def delete(pid):
    conn = get_db_connection(); cur = conn.cursor()
    # Verificar permiso
    cur.execute("SELECT usuario_id FROM posts WHERE id = %s", (pid,))
    p = cur.fetchone()
    if p and (p[0] == session['user_id'] or session.get('rol') == 'admin'):
        cur.execute("DELETE FROM posts WHERE id = %s", (pid,))
        cur.execute("DELETE FROM likes WHERE post_id = %s", (pid,))
        cur.execute("DELETE FROM comentarios WHERE post_id = %s", (pid,))
        conn.commit()
    cur.close(); conn.close()
    return redirect('/foro')

@app.route('/edit/<int:pid>')
def edit(pid):
    txt = request.args.get('txt')
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("SELECT usuario_id FROM posts WHERE id = %s", (pid,))
    p = cur.fetchone()
    if p and p[0] == session['user_id'] and txt:
        cur.execute("UPDATE posts SET contenido = %s WHERE id = %s", (txt, pid))
        conn.commit()
    cur.close(); conn.close()
    return redirect('/foro')

@app.route('/like/<int:pid>', methods=['POST'])
def like(pid):
    if 'user_id' not in session: return redirect('/')
    conn = get_db_connection(); cur = conn.cursor()
    try:
        cur.execute("INSERT INTO likes (usuario_id, post_id) VALUES (%s, %s)", (session['user_id'], pid))
        conn.commit()
    except:
        # Ya le dio like, entonces se quita (unlike)
        cur.execute("DELETE FROM likes WHERE usuario_id = %s AND post_id = %s", (session['user_id'], pid))
        conn.commit()
    cur.close(); conn.close()
    return redirect('/foro')

@app.route('/comment/<int:pid>', methods=['POST'])
def comment(pid):
    txt = request.form['contenido']
    if len(txt) > 0:
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("INSERT INTO comentarios (post_id, usuario_id, contenido) VALUES (%s, %s, %s)", (pid, session['user_id'], txt))
        conn.commit(); cur.close(); conn.close()
    return redirect('/foro')

@app.route('/buscar')
def buscar():
    q = request.args.get('q', '')
    if not q: return redirect('/foro')
    conn = get_db_connection(); cur = conn.cursor()
    # Búsqueda simple
    cur.execute("SELECT p.id, u.nombre, p.contenido, p.fecha, p.categoria, u.moto, u.nombre, p.usuario_id, 0, 0 FROM posts p JOIN usuarios u ON p.usuario_id = u.id WHERE p.contenido ILIKE %s ORDER BY p.fecha DESC", (f'%{q}%',))
    raw = cur.fetchall()
    # Reutilizamos la plantilla del foro pero con resultados
    posts = []
    for p in raw:
        posts.append((p[0], p[1], url_to_image(p[2]), p[3], p[4], time_ago(p[3]), string_to_color(p[1]), p[7], 0, 0, []))
    
    cur.close(); conn.close()
    flash(f"Resultados para: {q}")
    return render_template_string(FORO_PAGE, style=STYLE, posts=posts, active='foro')

@app.route('/perfil', methods=['GET', 'POST'])
def perfil():
    if 'user_id' not in session: return redirect('/')
    if request.method == 'POST':
        bio = request.form['bio']
        moto = request.form['moto']
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("UPDATE usuarios SET bio = %s, moto = %s WHERE id = %s", (bio, moto, session['user_id']))
        conn.commit(); cur.close(); conn.close()
        session['bio'] = bio
        session['moto'] = moto
        flash("Perfil actualizado")
    return render_template_string(PERFIL_PAGE, style=STYLE, active='perfil')

@app.route('/admin')
def admin():
    if session.get('rol') != 'admin': return redirect('/')
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM usuarios")
    users = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM posts")
    posts = cur.fetchone()[0]
    cur.close(); conn.close()
    return render_template_string(ADMIN_PAGE, style=STYLE, stats=(users, posts))

@app.route('/grupos')
def grupos():
    # Mantenemos funcionalidad anterior simplificada
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("SELECT id, nombre, descripcion FROM grupos")
    grupos = cur.fetchall()
    cur.close(); conn.close()
    return "<h1>Grupos</h1><p>Funcionalidad en mantenimiento.</p>" # Placeholder simple

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000)
