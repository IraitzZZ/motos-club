import os
import re
import html
import psycopg2
from flask import Flask, request, redirect, render_template_string, session, flash, get_flashed_messages
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
    
    # Tabla Usuarios
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
    # Tabla Posts
    cur.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id SERIAL PRIMARY KEY,
            usuario_id INTEGER REFERENCES usuarios(id),
            contenido TEXT NOT NULL,
            categoria TEXT DEFAULT 'General',
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    # Tabla Likes
    cur.execute("""
        CREATE TABLE IF NOT EXISTS likes (
            usuario_id INTEGER REFERENCES usuarios(id),
            post_id INTEGER REFERENCES posts(id),
            PRIMARY KEY (usuario_id, post_id)
        );
    """)
    # Tabla Comentarios
    cur.execute("""
        CREATE TABLE IF NOT EXISTS comentarios (
            id SERIAL PRIMARY KEY, 
            post_id INTEGER REFERENCES posts(id), 
            usuario_id INTEGER REFERENCES usuarios(id), 
            contenido TEXT, 
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Migraciones (Añadir columnas si faltan)
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

# --- ESTILO ---
STYLE = """
:root { --bg: #050505; --card: #111; --text: #fff; --red: #FF0F0F; --blue: #0074D9; --border: #222; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: var(--bg); color: var(--text); margin: 0; line-height: 1.5; }
a { color: var(--blue); text-decoration: none; }
.navbar { background: #000; border-bottom: 1px solid var(--border); padding: 15px 20px; display: flex; justify-content: space-between; align-items: center; position: sticky; top: 0; z-index: 1000; }
.nav-brand { font-weight: 800; color: white; }
.nav-links { display: flex; gap: 10px; }
.nav-btn { padding: 8px 16px; border-radius: 6px; background: transparent; color: #ccc; border: 1px solid #333; font-weight: 600; text-decoration: none; }
.nav-btn.active { background: var(--red); border-color: var(--red); color: white; }
.container { max-width: 800px; margin: 20px auto; padding: 0 20px; }
.card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 20px; margin-bottom: 20px; }
input, textarea, select { width: 100%; background: #0a0a0a; border: 1px solid #333; color: white; padding: 12px; border-radius: 8px; box-sizing: border-box; margin-bottom: 10px; font-family: inherit; }
button.btn-main { background: var(--red); color: white; border: none; padding: 12px 24px; border-radius: 6px; font-weight: 700; cursor: pointer; width: 100%; }
.btn-sec { background: #222; border: 1px solid #444; color: white; padding: 5px 10px; border-radius: 4px; font-size: 12px; cursor: pointer; }
.post-header { display: flex; justify-content: space-between; margin-bottom: 10px; }
.post-actions { display: flex; gap: 10px; margin-top: 10px; }
.avatar { width: 40px; height: 40px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: bold; color: white; flex-shrink: 0; }
.badge { font-size: 10px; padding: 2px 6px; border-radius: 4px; margin-left: 5px; }
.badge-route { background: #1e3a5f; color: #4da6ff; }
.badge-mech { background: #4a1e1e; color: #ff4d4d; }
.badge-sale { background: #2e4a1e; color: #4dff4d; }
.post-image { max-width: 100%; border-radius: 8px; margin-top: 10px; }
.flash { background: rgba(255,0,0,0.1); border: 1px solid var(--red); color: #ffcccc; padding: 10px; border-radius: 6px; margin-bottom: 10px; }
"""

# --- PLANTILLAS (Usamos __CONTENT__ como marcador simple) ---

BASE_LAYOUT = """
<!DOCTYPE html>
<html>
<head><title>MotosClub</title><style>{{ style }}</style></head>
<body>
    <nav class="navbar">
        <div class="nav-brand">🏍️ MotosClub</div>
        <div class="nav-links">
            <a href="/foro" class="nav-btn {% if active == 'foro' %}active{% endif %}">Muro</a>
            <a href="/perfil" class="nav-btn {% if active == 'perfil' %}active{% endif %}">Perfil</a>
            {% if session.get('rol') == 'admin' %}
                <span style="color:gold; font-weight:bold; margin-left:10px;">👑 Admin</span>
            {% endif %}
            <a href="/logout" class="nav-btn">Salir</a>
        </div>
    </nav>
    <div class="container">
        {% with messages = get_flashed_messages() %} 
            {% if messages %} <div class="flash">{{ messages[0] }}</div> {% endif %} 
        {% endwith %}
        __CONTENT__
    </div>
</body>
</html>
"""

LOGIN_HTML = """
<div class="card" style="max-width: 400px; margin: 50px auto;">
    <h2 style="text-align:center;">Iniciar Sesión</h2>
    <form method="POST">
        <input type="text" name="nombre" placeholder="Usuario" required>
        <input type="password" name="password" placeholder="Contraseña" required>
        <button type="submit" name="login" class="btn-main">Entrar</button>
        <button type="submit" name="register" class="btn-main" style="background:#333; margin-top:5px;">Registrar</button>
    </form>
</div>
"""

PERFIL_HTML = """
<div class="card">
    <h2>Tu Perfil</h2>
    <div style="display:flex; gap:15px; align-items:center; margin-bottom:20px;">
        <div class="avatar" style="width:60px; height:60px; font-size:24px; background:var(--red);">{{ session.get('user_name')[0] }}</div>
        <div>
            <h3 style="margin:0;">@{{ session.get('user_name') }}</h3>
            <small style="color:#666;">{{ session.get('moto', 'Sin moto') }}</small>
        </div>
    </div>
    <form method="POST" action="/perfil">
        <input type="text" name="moto" placeholder="Tu Moto (ej: MT-07)" value="{{ session.get('moto', '') }}">
        <textarea name="bio" placeholder="Tu biografía...">{{ session.get('bio', '') }}</textarea>
        <button class="btn-main">Guardar</button>
    </form>
</div>
"""

FORO_HTML = """
<!-- Buscador -->
<form action="/buscar" method="GET" style="display:flex; gap:10px; margin-bottom:20px;">
    <input type="text" name="q" placeholder="Buscar..." style="margin-bottom:0;">
    <button class="btn-main" style="width:auto;">🔍</button>
</form>

<!-- Publicar -->
<div class="card">
    <form method="POST" action="/post">
        <textarea name="contenido" rows="2" placeholder="¿Qué ruta haces hoy?"></textarea>
        <div style="display:flex; gap:10px;">
            <select name="categoria" style="width:auto;">
                <option value="General">General</option>
                <option value="Ruta">🛣️ Ruta</option>
                <option value="Mecanica">🔧 Mecánica</option>
                <option value="Venta">💰 Venta</option>
            </select>
            <button class="btn-main" style="width:100%;">Publicar</button>
        </div>
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
        <div>
            {% if session.get('user_id') == p[7] %}
                <button onclick="editPost({{ p[0] }}, `{{ p[2] }}`)" class="btn-sec">✏️</button>
            {% endif %}
            <form action="/delete/{{ p[0] }}" method="POST" style="display:inline;" onsubmit="return confirm('¿Borrar?');">
                <button class="btn-sec">🗑️</button>
            </form>
        </div>
        {% endif %}
    </div>
    
    <div>{{ p[3] | safe }}</div>
    
    <div class="post-actions">
        <form action="/like/{{ p[0] }}" method="POST" style="display:inline;">
            <button class="btn-sec">⛽ Gas ({{ p[8] }})</button>
        </form>
        <button class="btn-sec" onclick="toggleCom({{ p[0] }})">💬 {{ p[9] }}</button>
    </div>
    
    <div id="com-{{ p[0] }}" style="display:none; margin-top:10px; border-top:1px solid #222; padding-top:10px;">
        <form action="/comment/{{ p[0] }}" method="POST" style="display:flex; gap:5px;">
            <input type="text" name="contenido" placeholder="Responder..." required>
            <button class="btn-sec">Enviar</button>
        </form>
        {% for c in p[10] %}
        <div style="background:#181818; padding:8px; border-radius:5px; margin-top:5px;">
            <strong style="color:{{ c[3] }}">{{ c[0] }}</strong>: {{ c[1] }}
        </div>
        {% endfor %}
    </div>
</div>
{% endfor %}

<script>
function toggleCom(id) { var x = document.getElementById('com-'+id); x.style.display = (x.style.display === 'none') ? 'block' : 'none'; }
function editPost(id, txt) { var n = prompt("Editar:", txt); if(n) window.location.href = "/edit/"+id+"?txt="+encodeURIComponent(n); }
</script>
"""

# --- FILTROS ---
def url_to_image(text):
    text = html.escape(text) # Seguridad
    pattern = r'(https?://[^\s]+?\.(png|jpg|jpeg|gif|webp))'
    return re.sub(pattern, r'<img src="\1" class="post-image">', text)

def string_to_color(s):
    h = sum(ord(c) for c in s) % 360
    return f"hsl({h}, 70%, 40%)"

def time_ago(dt):
    delta = datetime.now() - dt
    if delta.days > 0: return f"hace {delta.days}d"
    if delta.seconds >= 3600: return f"hace {delta.seconds // 3600}h"
    if delta.seconds >= 60: return f"hace {delta.seconds // 60}m"
    return "ahora"

# --- RUTAS ---

@app.route('/', methods=['GET', 'POST'])
def login():
    if 'user_id' in session: return redirect('/foro')
    
    if request.method == 'POST':
        nombre = request.form['nombre'].strip()
        passw = request.form['password']
        conn = get_db_connection(); cur = conn.cursor()

        if 'register' in request.form:
            try:
                hash_p = generate_password_hash(passw)
                cur.execute("SELECT COUNT(*) FROM usuarios")
                rol = 'admin' if cur.fetchone()[0] == 0 else 'user'
                cur.execute("INSERT INTO usuarios (nombre, password, rol) VALUES (%s, %s, %s)", (nombre, hash_p, rol))
                conn.commit()
                flash(f"¡Registrado como {rol}! Entra ahora.")
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

    # Aquí hacemos el reemplazo mágico para evitar errores de Jinja
    page = BASE_LAYOUT.replace("__CONTENT__", LOGIN_HTML)
    return render_template_string(page, style=STYLE)

@app.route('/foro')
def foro():
    if 'user_id' not in session: return redirect('/')
    
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("""
        SELECT p.id, u.nombre, p.contenido, p.fecha, p.categoria, u.moto, u.nombre, p.usuario_id,
               (SELECT COUNT(*) FROM likes l WHERE l.post_id = p.id),
               (SELECT COUNT(*) FROM comentarios c WHERE c.post_id = p.id)
        FROM posts p JOIN usuarios u ON p.usuario_id = u.id
        ORDER BY p.fecha DESC LIMIT 30
    """)
    raw = cur.fetchall()
    
    posts = []
    for p in raw:
        cur.execute("SELECT u.nombre, c.contenido, c.fecha FROM comentarios c JOIN usuarios u ON c.usuario_id = u.id WHERE c.post_id = %s ORDER BY c.fecha ASC LIMIT 5", (p[0],))
        raw_c = cur.fetchall()
        coms = [(c[0], c[1], time_ago(c[2]), string_to_color(c[0])) for c in raw_c]
        
        # Pasamos contenido crudo a la vista para que JS lo maneje o lo mostramos seguro
        # Pero en el HTML hacemos | safe después de haber escapado en url_to_image
        safe_content = url_to_image(p[2])
        
        posts.append((p[0], p[1], p[2], safe_content, p[4], time_ago(p[3]), string_to_color(p[1]), p[7], p[8], p[9], coms))

    cur.close(); conn.close()
    
    page = BASE_LAYOUT.replace("__CONTENT__", FORO_HTML)
    return render_template_string(page, style=STYLE, posts=posts, active='foro')

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
    cur.execute("SELECT p.id, u.nombre, p.contenido, p.fecha, p.categoria, u.moto, u.nombre, p.usuario_id, 0, 0 FROM posts p JOIN usuarios u ON p.usuario_id = u.id WHERE p.contenido ILIKE %s ORDER BY p.fecha DESC", (f'%{q}%',))
    raw = cur.fetchall()
    posts = [(p[0], p[1], p[2], url_to_image(p[2]), p[4], time_ago(p[3]), string_to_color(p[1]), p[7], 0, 0, []) for p in raw]
    cur.close(); conn.close()
    flash(f"Resultados para: {q}")
    page = BASE_LAYOUT.replace("__CONTENT__", FORO_HTML)
    return render_template_string(page, style=STYLE, posts=posts, active='foro')

@app.route('/perfil', methods=['GET', 'POST'])
def perfil():
    if 'user_id' not in session: return redirect('/')
    if request.method == 'POST':
        bio = request.form['bio']
        moto = request.form['moto']
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("UPDATE usuarios SET bio = %s, moto = %s WHERE id = %s", (bio, moto, session['user_id']))
        conn.commit(); cur.close(); conn.close()
        session['bio'] = bio; session['moto'] = moto
        flash("Perfil actualizado")
    
    page = BASE_LAYOUT.replace("__CONTENT__", PERFIL_HTML)
    return render_template_string(page, style=STYLE, active='perfil')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000)
