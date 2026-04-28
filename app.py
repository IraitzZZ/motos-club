import os
import psycopg2
from flask import Flask, request, redirect, url_for, render_template_string, session, flash
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.urandom(24)

# CONFIGURACIÓN DE BASE DE DATOS
DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id SERIAL PRIMARY KEY,
            nombre TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS posts (
            id SERIAL PRIMARY KEY,
            usuario_id INTEGER REFERENCES usuarios(id),
            contenido TEXT NOT NULL,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    cur.close()
    conn.close()

# --- CSS Y HTML ---

STYLE = """
:root { --bg: #000; --card: #1c1c1e; --text: #f5f5f7; --accent: #ff3b30; --border: #38383a; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: var(--bg); color: var(--text); line-height: 1.5; margin: 0; padding: 20px; max-width: 600px; margin: 0 auto; }
a { color: #0a84ff; text-decoration: none; }
.header { padding: 20px 0; border-bottom: 1px solid var(--border); margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; }
.btn { background: var(--accent); color: white; border: none; padding: 10px 20px; border-radius: 980px; cursor: pointer; font-weight: 600; font-size: 14px; }
.btn-sec { background: #2c2c2e; color: var(--text); }
input, textarea { width: 100%; background: #1c1c1e; border: 1px solid var(--border); color: white; padding: 12px; border-radius: 12px; box-sizing: border-box; margin-bottom: 10px; font-family: inherit; }
.post-card { background: var(--card); padding: 16px; border-radius: 12px; margin-bottom: 12px; border: 1px solid var(--border); }
.post-meta { font-size: 12px; color: #8e8e93; margin-bottom: 4px; display: flex; justify-content: space-between; }
.auth-box { background: var(--card); padding: 30px; border-radius: 20px; margin-top: 50px; }
.flash { background: #2c2c2e; padding: 10px; border-radius: 8px; margin-bottom: 10px; font-size: 14px; }
"""

LOGIN_HTML = """
<!DOCTYPE html><html><head><title>MotosClub - Login</title><style>{{ style }}</style></head>
<body>
    <div class="header"><h1>🏍️ MotosClub</h1></div>
    <div class="auth-box">
        <h2> Bienvenido </h2>
        <p style="color:#8e8e93">La comunidad de moteros infinita.</p>
        <form method="POST">
            <input type="text" name="nombre" placeholder="Usuario" required><br>
            <input type="password" name="password" placeholder="Contraseña" required><br>
            <button type="submit" name="login" class="btn">Iniciar Sesión</button>
            <button type="submit" name="register" class="btn btn-sec" style="margin-left:5px;">Registrar</button>
        </form>
        {% with messages = get_flashed_messages() %} 
            {% if messages %} 
                <div class="flash">{{ messages[0] }}</div> 
            {% endif %} 
        {% endwith %}
    </div>
</body></html>
"""

FORO_HTML = """
<!DOCTYPE html><html><head><title>MotosClub - Foro</title><style>{{ style }}</style></head>
<body>
    <div class="header">
        <h1>🏍️ MotosClub</h1>
        <a href="/logout" class="btn btn-sec">Cerrar Sesión</a>
    </div>
    
    <div class="post-card">
        <form method="POST" action="/post">
            <textarea name="contenido" rows="2" placeholder="¿Qué ruta vas a hacer hoy?" required></textarea>
            <button type="submit" class="btn">Publicar</button>
        </form>
    </div>

    <div id="feed">
    {% for post in posts %}
        <div class="post-card">
            <div class="post-meta">
                <span><strong>{{ post[1] }}</strong></span>
                <span>{{ post[3].strftime('%d/%m %H:%M') }}</span>
            </div>
            <p>{{ post[2] }}</p>
        </div>
    {% endfor %}
    </div>
</body></html>
"""

# --- RUTAS ---

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        nombre = request.form['nombre']
        password = request.form['password']
        conn = get_db_connection()
        cur = conn.cursor()

        if 'register' in request.form:
            try:
                hash_pass = generate_password_hash(password)
                cur.execute("INSERT INTO usuarios (nombre, password) VALUES (%s, %s)", (nombre, hash_pass))
                conn.commit()
                flash("¡Registrado! Ahora inicia sesión.")
            except:
                flash("Ese usuario ya existe.")
        
        elif 'login' in request.form:
            cur.execute("SELECT id, password FROM usuarios WHERE nombre = %s", (nombre,))
            user = cur.fetchone()
            if user and check_password_hash(user[1], password):
                session['user_id'] = user[0]
                session['user_name'] = nombre
                cur.close()
                conn.close()
                return redirect('/foro')
            else:
                flash("Usuario o contraseña incorrectos.")
        
        cur.close()
        conn.close()

    if 'user_id' in session:
        return redirect('/foro')
    return render_template_string(LOGIN_HTML, style=STYLE)

@app.route('/foro')
def foro():
    if 'user_id' not in session:
        return redirect('/')
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT posts.id, usuarios.nombre, posts.contenido, posts.fecha 
        FROM posts JOIN usuarios ON posts.usuario_id = usuarios.id 
        ORDER BY posts.fecha DESC
    """)
    posts = cur.fetchall()
    cur.close()
    conn.close()
    
    return render_template_string(FORO_HTML, posts=posts, style=STYLE)

@app.route('/post', methods=['POST'])
def post():
    if 'user_id' not in session:
        return redirect('/')
    
    contenido = request.form['contenido']
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO posts (usuario_id, contenido) VALUES (%s, %s)", (session['user_id'], contenido))
    conn.commit()
    cur.close()
    conn.close()
    return redirect('/foro')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000)
