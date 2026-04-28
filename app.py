# =============================================================================
# MOTOSCLUB - Red Social para Moteros | Versión 3.0 - Production Ready
# =============================================================================
import os, re, html, psycopg2
from flask import Flask, request, redirect, render_template_string, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from functools import wraps
from flask_wtf.csrf import CSRFProtect

# -----------------------------------------------------------------------------
# CONFIGURACIÓN
# -----------------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))
app.config['WTF_CSRF_TIME_LIMIT'] = None
csrf = CSRFProtect(app)
DATABASE_URL = os.environ.get('DATABASE_URL')

# -----------------------------------------------------------------------------
# BASE DE DATOS
# -----------------------------------------------------------------------------
def get_db():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn, cur = get_db(), get_db().cursor()
    
    cur.execute("""CREATE TABLE IF NOT EXISTS usuarios (
        id SERIAL PRIMARY KEY, nombre TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
        email TEXT DEFAULT '', bio TEXT DEFAULT '', moto TEXT DEFAULT '',
        avatar_color TEXT DEFAULT '', racha INTEGER DEFAULT 0,
        ultima_actividad DATE, creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP);""")
    
    cur.execute("""CREATE TABLE IF NOT EXISTS posts (
        id SERIAL PRIMARY KEY, usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
        contenido TEXT NOT NULL, imagen_url TEXT DEFAULT '', categoria TEXT DEFAULT 'General',
        fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP, reportes INTEGER DEFAULT 0);""")
    
    cur.execute("""CREATE TABLE IF NOT EXISTS seguidores (
        seguidor_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
        seguido_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
        fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (seguidor_id, seguido_id), CHECK (seguidor_id != seguido_id));""")
    
    cur.execute("""CREATE TABLE IF NOT EXISTS likes (
        usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
        post_id INTEGER REFERENCES posts(id) ON DELETE CASCADE,
        PRIMARY KEY (usuario_id, post_id));""")
    
    cur.execute("""CREATE TABLE IF NOT EXISTS comentarios (
        id SERIAL PRIMARY KEY, post_id INTEGER REFERENCES posts(id) ON DELETE CASCADE,
        usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
        contenido TEXT NOT NULL, fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP);""")
    
    cur.execute("""CREATE TABLE IF NOT EXISTS notificaciones (
        id SERIAL PRIMARY KEY, usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
        tipo TEXT NOT NULL, mensaje TEXT NOT NULL, url TEXT,
        leido BOOLEAN DEFAULT FALSE, fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP);""")
    
    cur.execute("""CREATE TABLE IF NOT EXISTS bookmarks (
        usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
        post_id INTEGER REFERENCES posts(id) ON DELETE CASCADE,
        PRIMARY KEY (usuario_id, post_id));""")
    
    conn.commit(); cur.close(); conn.close()

# -----------------------------------------------------------------------------
# HELPERS
# -----------------------------------------------------------------------------
def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if 'user_id' not in session:
            flash("Inicia sesión para continuar", "error")
            return redirect('/')
        return f(*args, **kwargs)
    return wrapped

def procesar(texto):
    t = html.escape(texto)
    t = re.sub(r'(https?://[^\s]+?\.(png|jpg|jpeg|gif|webp))', r'<img src="\1" class="post-img" loading="lazy">', t)
    t = re.sub(r'@(\w+)', r'<a href="/perfil/\1" class="link">@\1</a>', t)
    t = re.sub(r'#(\w+)', r'<a href="/buscar?tag=\1" class="link">#\1</a>', t)
    return t

def color_de(s): return f"hsl({sum(ord(c) for c in s)%360}, 70%, 50%)"
def hace(dt):
    if not dt: return "ahora"
    d = datetime.now() - dt
    if d.days>365: return f"hace {d.days//365}a"
    if d.days>0: return f"hace {d.days}d"
    if d.seconds>=3600: return f"hace {d.seconds//3600}h"
    if d.seconds>=60: return f"hace {d.seconds//60}m"
    return "ahora"

def notif(user_id, tipo, msg, url=None):
    try:
        conn, cur = get_db(), get_db().cursor()
        cur.execute("INSERT INTO notificaciones (usuario_id,tipo,mensaje,url) VALUES (%s,%s,%s,%s)", (user_id,tipo,msg,url))
        conn.commit(); cur.close(); conn.close()
    except: pass

def contar_notifs(uid):
    try:
        conn, cur = get_db(), get_db().cursor()
        cur.execute("SELECT COUNT(*) FROM notificaciones WHERE usuario_id=%s AND leido=FALSE", (uid,))
        c = cur.fetchone()[0]; cur.close(); conn.close()
        return c
    except: return 0

# -----------------------------------------------------------------------------
# CSS PROFESIONAL
# -----------------------------------------------------------------------------
CSS = """
:root{--f:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
--bg:#0a0a0a;--bg2:#161618;--surf:#1c1c1e;--surf2:#2a2a2c;
--txt:#f5f5f7;--txtd:#aeaeb2;--bor:#3a3a3c;--acc:#ff453a;--acc2:#ff6055;
--azul:#0a84ff;--verde:#30d158;--som:0 4px 20px rgba(0,0,0,.4);--rad:14px;--rad2:10px;--tr:180ms ease}
[data-theme="light"]{--bg:#f5f5f7;--bg2:#fff;--surf:#fff;--surf2:#f0f0f2;
--txt:#1d1d1f;--txtd:#6e6e73;--bor:#d2d2d7;--som:0 4px 20px rgba(0,0,0,.08)}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:var(--f);background:var(--bg);color:var(--txt);line-height:1.5;font-size:15px;transition:background var(--tr),color var(--tr)}
h1,h2,h3{font-weight:700;line-height:1.2}h1{font-size:clamp(24px,5vw,32px)}h2{font-size:clamp(20px,4vw,24px)}
a{color:var(--azul);text-decoration:none;transition:opacity var(--tr)}a:hover{opacity:.85}
.container{max-width:680px;margin:0 auto;padding:0 16px}
.nav{position:sticky;top:0;z-index:100;background:rgba(22,22,24,.85);backdrop-filter:blur(20px);
border-bottom:1px solid var(--bor);padding:10px 0}
.nav-inner{display:flex;align-items:center;justify-content:space-between;max-width:680px;margin:0 auto;padding:0 16px}
.nav-brand{font-weight:800;font-size:20px;color:var(--txt);display:flex;align-items:center;gap:6px}
.nav-acts{display:flex;align-items:center;gap:4px}
.nav-btn,.icon{background:transparent;border:none;color:var(--txt);padding:8px 12px;border-radius:10px;
font-size:14px;font-weight:500;cursor:pointer;display:flex;align-items:center;gap:6px;transition:background var(--tr)}
.nav-btn:hover,.icon:hover{background:var(--surf2)}.nav-btn.active{background:var(--acc);color:#fff}
.icon{width:38px;height:38px;padding:0;justify-content:center;font-size:18px;position:relative}
.badge{position:absolute;top:2px;right:2px;background:var(--acc);color:#fff;font-size:10px;font-weight:700;
min-width:18px;height:18px;border-radius:9px;display:flex;align-items:center;justify-content:center}
.card{background:var(--surf);border:1px solid var(--bor);border-radius:var(--rad);padding:16px;margin-bottom:12px;transition:border-color var(--tr)}
.card:hover{border-color:var(--txtd)}
input,textarea,select{width:100%;background:var(--bg2);border:1px solid var(--bor);border-radius:var(--rad2);
color:var(--txt);padding:12px 14px;font-size:15px;font-family:inherit;outline:none;transition:border-color var(--tr),box-shadow var(--tr)}
input:focus,textarea:focus{border-color:var(--acc);box-shadow:0 0 0 3px rgba(255,69,58,.15)}
textarea{resize:vertical;min-height:100px}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;padding:12px 20px;
border-radius:var(--rad2);font-weight:600;font-size:14px;cursor:pointer;border:none;transition:transform var(--tr),background var(--tr)}
.btn:active{transform:scale(.98)}.btn-p{background:var(--acc);color:#fff;width:100%}.btn-p:hover{background:var(--acc2)}
.btn-s{background:var(--surf2);color:var(--txt)}.btn-s:hover{background:var(--bor)}
.btn-g{background:transparent;color:var(--txtd);padding:6px 10px}.btn-g:hover{color:var(--txt);background:var(--surf2)}
.btn-sm{padding:6px 12px;font-size:13px;border-radius:8px}
.av{width:40px;height:40px;border-radius:50%;display:flex;align-items:center;justify-content:center;
font-weight:600;font-size:16px;color:#fff;flex-shrink:0;text-transform:uppercase}.av-lg{width:72px;height:72px;font-size:28px}
.post-h{display:flex;align-items:flex-start;gap:10px;margin-bottom:10px}
.post-a{display:flex;flex-direction:column;gap:2px}.post-an{font-weight:600;color:var(--txt);font-size:15px}
.post-an:hover{text-decoration:underline}.post-m{font-size:13px;color:var(--txtd);display:flex;align-items:center;gap:4px}
.post-cat{font-size:11px;padding:2px 8px;border-radius:6px;background:var(--surf2);color:var(--txtd);font-weight:500}
.post-c{font-size:15px;line-height:1.5;white-space:pre-wrap;word-break:break-word;margin:8px 0 12px}
.post-c .link{color:var(--azul);font-weight:500}
.post-img{width:100%;border-radius:var(--rad2);margin:8px 0;border:1px solid var(--bor);display:block;max-height:500px;object-fit:cover}
.post-acts{display:flex;align-items:center;gap:4px;padding-top:10px;border-top:1px solid var(--bor)}
.act{display:flex;align-items:center;gap:4px;padding:8px 12px;border-radius:8px;background:transparent;border:none;
color:var(--txtd);font-size:14px;font-weight:500;cursor:pointer;transition:background var(--tr),color var(--tr)}
.act:hover{background:var(--surf2);color:var(--txt)}.act.active{color:var(--acc)}.act .n{font-weight:600}
.coms{margin-top:12px;padding-top:12px;border-top:1px solid var(--bor);display:none}.coms.show{display:block}
.com-f{display:flex;gap:8px;margin-bottom:12px}.com-f input{margin:0;flex:1;padding:10px 12px;font-size:14px}
.com{background:var(--bg2);border-radius:var(--rad2);padding:10px 12px;margin-bottom:8px;font-size:14px}
.com-au{font-weight:600;margin-right:4px}.com-ti{color:var(--txtd);font-size:12px;margin-left:4px}
.banner{height:120px;background:linear-gradient(135deg,var(--acc),var(--azul));border-radius:var(--rad) var(--rad) 0 0;margin:-16px -16px 0}
.prof-h{display:flex;align-items:center;gap:14px;padding-top:36px;margin-bottom:16px}
.prof-i{flex:1;min-width:0}.prof-n{font-size:20px;font-weight:700;margin-bottom:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.prof-m{color:var(--txtd);font-size:14px}.prof-b{margin:12px 0;font-size:14px;line-height:1.4;white-space:pre-wrap}
.prof-s{display:flex;gap:20px;padding:12px 0;border-top:1px solid var(--bor);margin-top:12px}
.st{text-align:center}.st-v{font-weight:700;font-size:16px;display:block}.st-l{font-size:12px;color:var(--txtd)}
.auth{display:flex;align-items:center;justify-content:center;min-height:calc(100vh - 100px);padding:20px}
.auth-c{width:100%;max-width:400px;text-align:center}.auth-t{font-size:32px;font-weight:800;margin-bottom:8px;display:flex;align-items:center;justify-content:center;gap:8px}
.auth-sub{color:var(--txtd);margin-bottom:24px;font-size:14px}.auth-f{display:flex;flex-direction:column;gap:12px}
.auth-sw{margin-top:16px;font-size:14px;color:var(--txtd)}.auth-sw button{background:none;border:none;color:var(--azul);font-weight:500;cursor:pointer;padding:0;font-size:inherit}
.flash{padding:12px 16px;border-radius:var(--rad2);margin-bottom:12px;font-size:14px;font-weight:500;animation:si 200ms ease}
@keyframes si{from{opacity:0;transform:translateY(-10px)}to{opacity:1;transform:translateY(0)}}
.flash-e{background:rgba(255,69,58,.12);color:#ff6b61;border:1px solid rgba(255,69,58,.3)}
.flash-s{background:rgba(48,209,88,.12);color:#4fd676;border:1px solid rgba(48,209,88,.3)}
.nl{display:flex;flex-direction:column;gap:8px}.ni{display:flex;gap:10px;padding:12px;border-radius:var(--rad2);background:var(--bg2);transition:background var(--tr)}
.ni.unread{background:rgba(10,132,255,.08);border-left:3px solid var(--azul)}.ni:hover{background:var(--surf2)}
.ni-ic{font-size:18px;margin-top:2px}.ni-c{flex:1;min-width:0}.ni-m{font-size:14px;margin-bottom:4px}.ni-t{font-size:12px;color:var(--txtd)}
.footer{text-align:center;padding:30px 16px 60px;color:var(--txtd);font-size:13px}.footer a{color:var(--txtd)}
.hidden{display:none!important}.tc{text-align:center}.mt1{margin-top:8px}.mt2{margin-top:16px}.mb1{margin-bottom:8px}.mb2{margin-bottom:16px}
.fx{display:flex}.fxc{flex-direction:column}.aic{align-items:center}.jcb{justify-content:space-between}.g1{gap:8px}.g2{gap:12px}.w100{width:100%}
@media(max-width:480px){.container{padding:0 12px}.nav-btn span{display:none}.prof-s{gap:14px}.st-v{font-size:14px}.st-l{font-size:11px}
.btn{padding:11px 18px;font-size:14px}.act{padding:7px 10px;font-size:13px}}
:focus-visible{outline:2px solid var(--azul);outline-offset:2px}
"""

# -----------------------------------------------------------------------------
# LAYOUT BASE
# -----------------------------------------------------------------------------
LAYOUT = """<!DOCTYPE html><html lang="es"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0,viewport-fit=cover">
<title>MOTOSCLUB</title><style>{{css}}</style></head><body>
<nav class="nav"><div class="nav-inner">
<a href="/foro" class="nav-brand">🏍️ MOTOSCLUB</a><div class="nav-acts">
<button class="icon" id="themeT" aria-label="Tema">🌙</button>
<a href="/buscar" class="icon" aria-label="Buscar">🔍</a>
<a href="/notifs" class="icon" aria-label="Notifs">🔔{%if nc>0%}<span class="badge">{{nc}}</span>{%endif%}</a>
<a href="/perfil" class="nav-btn{%if act=='perfil'%} active{%endif%}"><span>Yo</span></a>
<a href="/logout" class="nav-btn"><span>Salir</span></a></div></div></nav>
<main class="container" style="padding-top:16px">
{%with msgs=get_flashed_messages(with_categories=true)%}{%if msgs%}{%for cat,msg in msgs%}
<div class="flash flash-{{cat}}">{{msg}}</div>{%endfor%}{%endif%}{%endwith%}
{{cont|safe}}</main>
<footer class="footer"><p>🏍️ MOTOSCLUB © {{year}} • <a href="#">Privacidad</a> • <a href="#">Términos</a></p></footer>
<script>
(function(){const r=document.documentElement,t=document.getElementById('themeT'),s=localStorage.getItem('theme'),p=window.matchMedia('(prefers-color-scheme:dark)').matches;
function a(th){r.setAttribute('data-theme',th);localStorage.setItem('theme',th);t.textContent=th==='light'?'☀️':'🌙'}
a(s||(p?'dark':'light'));t.addEventListener('click',()=>a(r.getAttribute('data-theme')==='light'?'dark':'light'))})();
function toggleC(id){const e=document.getElementById('c-'+id),b=document.getElementById('b-'+id);
if(e&&b){const sh=e.classList.toggle('show');b.innerHTML=sh?'▲':'💬 '+b.dataset.n}}
function confDel(e){if(!confirm('¿Eliminar? No se puede deshacer.'))e.preventDefault()}
</script></body></html>"""

def page(cont, act='', nc=0):
    return render_template_string(LAYOUT, css=CSS, cont=cont, act=act, nc=nc, year=datetime.now().year)

# -----------------------------------------------------------------------------
# AUTH
# -----------------------------------------------------------------------------
@app.route('/', methods=['GET','POST'])
def auth():
    if 'user_id' in session: return redirect('/foro')
    login = request.args.get('reg') != '1'
    
    html_auth = f"""
    <div class="auth"><div class="card auth-c">
    <div class="auth-t">🏍️ MOTOSCLUB</div><p class="auth-sub">{"Conecta con moteros" if login else "Únete a la comunidad"}</p>
    <form method="POST" class="auth-f"><input type="hidden" name="csrf_token" value="{{{{ csrf_token() }}}}"/>
    <input type="text" name="nombre" placeholder="Usuario" required minlength="3" maxlength="30" pattern="[a-zA-Z0-9_]+" autocomplete="username">
    <div style="position:relative"><input type="password" name="password" placeholder="Contraseña" required minlength="6" id="pw">
    <button type="button" class="btn-g" style="position:absolute;right:4px;top:50%;transform:translateY(-50%)" onclick="document.getElementById('pw').type=document.getElementById('pw').type==='password'?'text':'password">👁️</button></div>
    {"<label style='display:flex;align-items:center;gap:6px;font-size:13px;color:var(--txtd)'><input type='checkbox' required> Acepto <a href='#' style='color:var(--azul)'>Términos</a></label>" if not login else ""}
    <button type="submit" name="act" value="{"login" if login else "reg"}" class="btn btn-p">{"ENTRAR" if login else "CREAR"}</button></form>
    <p class="auth-sw">{"¿Sin cuenta?" if login else "¿Ya tienes?"} <button type="button" onclick="location.href='/?{"reg=1" if login else ""}'">{"Regístrate" if login else "Entra"}</button></p></div></div>
    <script>document.querySelector('input[name="nombre"]').addEventListener('input',e=>e.target.value=e.target.value.replace(/[^a-zA-Z0-9_]/g,''));</script>"""
    
    if request.method == 'POST':
        nom, pwd, act = request.form.get('nombre','').strip(), request.form.get('password',''), request.form.get('act')
        if len(nom)<3: flash("Mínimo 3 caracteres","e")
        elif len(pwd)<6: flash("Mínimo 6 caracteres","e")
        elif not re.match(r'^[a-zA-Z0-9_]+$',nom): flash("Solo letras, números y _","e")
        else:
            conn, cur = get_db(), get_db().cursor()
            if act=='reg':
                try:
                    cur.execute("INSERT INTO usuarios (nombre,password,avatar_color) VALUES (%s,%s,%s)",(nom,generate_password_hash(pwd),color_de(nom)))
                    conn.commit(); flash("¡Cuenta creada! Entra","s"); login=True
                except psycopg2.IntegrityError: conn.rollback(); flash("Usuario existe","e")
                finally: cur.close(); conn.close()
            elif act=='login':
                cur.execute("SELECT id,password,avatar_color,bio,moto,racha FROM usuarios WHERE nombre=%s",(nom,))
                u=cur.fetchone(); cur.close(); conn.close()
                if u and check_password_hash(u[1],pwd):
                    session.update({'user_id':u[0],'user_name':nom,'avatar_color':u[2],'bio':u[3] or '','moto':u[4] or '','racha':u[5] or 0})
                    return redirect('/foro')
                else: flash("Credenciales incorrectas","e")
    return page(html_auth, nc=0)

# -----------------------------------------------------------------------------
# FORO
# -----------------------------------------------------------------------------
@app.route('/foro')
@login_required
def foro():
    conn, cur = get_db(), get_db().cursor()
    cur.execute("SELECT seguido_id FROM seguidores WHERE seguidor_id=%s",(session['user_id'],))
    follow = [r[0] for r in cur.fetchall()] + [session['user_id']]
    
    cur.execute("""SELECT p.id,u.nombre,u.avatar_color,p.contenido,p.imagen_url,p.categoria,p.fecha,p.usuario_id,
        (SELECT COUNT(*) FROM likes WHERE post_id=p.id),(SELECT COUNT(*) FROM comentarios WHERE post_id=p.id),
        EXISTS(SELECT 1 FROM likes WHERE post_id=p.id AND usuario_id=%s),
        EXISTS(SELECT 1 FROM bookmarks WHERE post_id=p.id AND usuario_id=%s)
        FROM posts p JOIN usuarios u ON p.usuario_id=u.id WHERE p.usuario_id=ANY(%s) AND p.reportes<5 ORDER BY p.fecha DESC LIMIT 30""",
        (session['user_id'],session['user_id'],tuple(follow)))
    
    posts=[]
    for row in cur.fetchall():
        pid,aut,col,cont,img,cat,fecha,uid,likes,ccnt,liked,bk = row
        cur.execute("SELECT u.nombre,u.avatar_color,c.contenido,c.fecha FROM comentarios c JOIN usuarios u ON c.usuario_id=u.id WHERE c.post_id=%s ORDER BY c.fecha ASC LIMIT 3",(pid,))
        coms=[(n,c,txt,hace(f)) for n,c,txt,f in cur.fetchall()]
        posts.append({'id':pid,'aut':aut,'col':col,'cont':procesar(cont),'img':img,'cat':cat,'fecha':hace(fecha),
                      'uid':uid,'likes':likes,'ccnt':ccnt,'liked':liked,'bk':bk,'coms':coms})
    cur.close(); conn.close()
    
    form = """
    <div class="card"><form method="POST" action="/post"><input type="hidden" name="csrf_token" value="{{ csrf_token() }}"/>
    <textarea name="cont" placeholder="¿Qué ruta hoy? Usa @menciones y #hashtags" required maxlength="500"></textarea>
    <div class="fx aic g1 mb1" style="flex-wrap:wrap"><select name="cat" style="width:auto;margin:0"><option>General</option><option value="Ruta">🛣️ Ruta</option><option value="Mecanica">🔧 Mecánica</option><option value="Venta">💰 Venta</option></select>
    <input type="url" name="img" placeholder="URL de imagen (opcional)" style="flex:1;min-width:150px;margin:0" pattern="https?://.+\\.(png|jpg|jpeg|gif|webp).*"></div>
    <small style="color:var(--txtd);display:block;margin-bottom:10px">💡 Pega enlace de imagen o deja vacío</small>
    <button type="submit" class="btn btn-p">PUBLICAR</button></form></div>"""
    
    posts_html=""
    for p in posts:
        posts_html += f"""
        <article class="card" id="p-{p['id']}"><div class="post-h">
        <div class="av" style="background:{p['col']}">{p['aut'][0].upper()}</div>
        <div class="post-a"><a href="/perfil/{p['aut']}" class="post-an">{p['aut']}</a>
        <div class="post-m"><span>{p['fecha']}</span><span>•</span><span class="post-cat">{p['cat']}</span></div></div>
        {"<button class='btn-g btn-sm' style='margin-left:auto' onclick=\"confDel(event);fetch('/del/'+{p['id']},{{method:'POST'}}).then(()=>location.reload())\">🗑️</button>" if p['uid']==session['user_id'] else ""}
        </div><div class="post-c">{p['cont']}</div>{f'<img src="{p["img"]}" class="post-img">' if p['img'] else ''}
        <div class="post-acts">
        <form action="/like/{p['id']}" method="POST" style="display:contents"><input type="hidden" name="csrf_token" value="{{{{ csrf_token() }}}}"/><button type="submit" class="act{' active' if p['liked'] else ''}" aria-label="Gas">⛽ <span class="n">{p['likes']}</span></button></form>
        <button type="button" class="act" id="b-{p['id']}" data-n="{p['ccnt']}" onclick="toggleC({p['id']})" aria-label="Coments">💬 <span class="n">{p['ccnt']}</span></button>
        <form action="/bk/{p['id']}" method="POST" style="display:contents"><input type="hidden" name="csrf_token" value="{{{{ csrf_token() }}}}"/><button type="submit" class="act{' active' if p['bk'] else ''}" aria-label="Guardar">🔖</button></form>
        <button class="act" style="margin-left:auto" aria-label="Más">⋯</button></div>
        <div class="coms" id="c-{p['id']}">
        <form action="/com/{p['id']}" method="POST" class="com-f"><input type="hidden" name="csrf_token" value="{{{{ csrf_token() }}}}"/><input type="text" name="txt" placeholder="Responder..." required maxlength="200" style="margin:0;flex:1"><button type="submit" class="btn btn-sm btn-s">Enviar</button></form>
        {"" if not p['coms'] else "".join(f"<div class='com'><span class='com-au' style='color:{c}'>{n}</span><span class='com-tx'>{html.escape(t)}</span><span class='com-ti'>{ta}</span></div>" for n,c,t,ta in p['coms'])}
        </div></article>"""
    
    cont = form + (posts_html or """<div class="card tc" style="padding:30px"><p style="color:var(--txtd)">Sin publicaciones aún<br>¡Sé el primero!</p></div>""")
    return page(cont, act='foro', nc=contar_notifs(session['user_id']))

# -----------------------------------------------------------------------------
# ACCIONES
# -----------------------------------------------------------------------------
@app.route('/post', methods=['POST'])
@login_required
def nuevo_post():
    cont, cat, img = request.form.get('cont','').strip(), request.form.get('cat','General'), request.form.get('img','').strip()
    if img and not re.match(r'^https?://.+\.(png|jpg|jpeg|gif|webp)',img,re.I): flash("URL de imagen inválida","e"); return redirect('/foro')
    if not cont and not img: flash("Escribe algo o añade imagen","e"); return redirect('/foro')
    
    conn, cur = get_db(), get_db().cursor()
    cur.execute("INSERT INTO posts (usuario_id,contenido,categoria,imagen_url) VALUES (%s,%s,%s,%s)",(session['user_id'],cont,cat,img[:500] if img else ''))
    
    hoy = datetime.now().date()
    cur.execute("SELECT ultima_actividad FROM usuarios WHERE id=%s",(session['user_id'],)); last=cur.fetchone()[0]
    if last==hoy-timedelta(days=1): cur.execute("UPDATE usuarios SET racha=racha+1,ultima_actividad=%s WHERE id=%s",(hoy,session['user_id']))
    elif last!=hoy: cur.execute("UPDATE usuarios SET racha=1,ultima_actividad=%s WHERE id=%s",(hoy,session['user_id']))
    
    for m in set(re.findall(r'@(\w+)',cont)):
        cur.execute("SELECT id FROM usuarios WHERE nombre=%s AND id!=%s",(m,session['user_id'])); u=cur.fetchone()
        if u: notif(u[0],'mention',f"{session['user_name']} te mencionó",f"/post/{cur.lastrowid}")
    
    conn.commit(); cur.close(); conn.close(); flash("¡Publicado! 🏍️","s"); return redirect('/foro')

@app.route('/like/<int:pid>', methods=['POST'])
@login_required
def like(pid):
    conn, cur = get_db(), get_db().cursor()
    try:
        cur.execute("INSERT INTO likes (usuario_id,post_id) VALUES (%s,%s)",(session['user_id'],pid))
        cur.execute("SELECT usuario_id FROM posts WHERE id=%s",(pid,)); ow=cur.fetchone()
        if ow and ow[0]!=session['user_id']: notif(ow[0],'like',f"A {session['user_name']} le gustó tu post",f"/post/{pid}")
        conn.commit()
    except psycopg2.IntegrityError: conn.rollback(); cur.execute("DELETE FROM likes WHERE usuario_id=%s AND post_id=%s",(session['user_id'],pid)); conn.commit()
    finally: cur.close(); conn.close()
    return redirect(request.referrer or '/foro')

@app.route('/bk/<int:pid>', methods=['POST'])
@login_required
def bk(pid):
    conn, cur = get_db(), get_db().cursor()
    try: cur.execute("INSERT INTO bookmarks (usuario_id,post_id) VALUES (%s,%s)",(session['user_id'],pid)); conn.commit()
    except psycopg2.IntegrityError: conn.rollback(); cur.execute("DELETE FROM bookmarks WHERE usuario_id=%s AND post_id=%s",(session['user_id'],pid)); conn.commit()
    finally: cur.close(); conn.close()
    return redirect(request.referrer or '/foro')

@app.route('/com/<int:pid>', methods=['POST'])
@login_required
def com(pid):
    txt = request.form.get('txt','').strip()
    if not txt: return redirect(request.referrer or '/foro')
    conn, cur = get_db(), get_db().cursor()
    cur.execute("INSERT INTO comentarios (post_id,usuario_id,contenido) VALUES (%s,%s,%s)",(pid,session['user_id'],txt[:200]))
    cur.execute("SELECT usuario_id FROM posts WHERE id=%s",(pid,)); ow=cur.fetchone()
    if ow and ow[0]!=session['user_id']: notif(ow[0],'comment',f"{session['user_name']} comentó tu post",f"/post/{pid}")
    conn.commit(); cur.close(); conn.close()
    return redirect(request.referrer or '/foro')

@app.route('/del/<int:pid>', methods=['POST'])
@login_required
def del_post(pid):
    conn, cur = get_db(), get_db().cursor()
    cur.execute("DELETE FROM posts WHERE id=%s AND usuario_id=%s",(pid,session['user_id']))
    conn.commit(); cur.close(); conn.close(); flash("Eliminado","s"); return redirect('/foro')

# -----------------------------------------------------------------------------
# PERFIL
# -----------------------------------------------------------------------------
@app.route('/perfil')
@app.route('/perfil/<username>')
@login_required
def perfil(username=None):
    target = username or session['user_name']
    conn, cur = get_db(), get_db().cursor()
    cur.execute("SELECT id,nombre,bio,moto,avatar_color,racha,creado_en FROM usuarios WHERE nombre=%s",(target,)); u=cur.fetchone()
    if not u: flash("Usuario no encontrado","e"); return redirect('/foro')
    
    uid,nom,bio,moto,col,racha,creado = u
    mio = uid==session['user_id']
    
    cur.execute("SELECT COUNT(*) FROM posts WHERE usuario_id=%s",(uid,)); pc=cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM seguidores WHERE seguido_id=%s",(uid,)); flw=cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM seguidores WHERE seguidor_id=%s",(uid,)); flg=cur.fetchone()[0]
    
    sigo=False
    if not mio: cur.execute("SELECT 1 FROM seguidores WHERE seguidor_id=%s AND seguido_id=%s",(session['user_id'],uid)); sigo=cur.fetchone() is not None
    
    cur.execute("SELECT id,contenido,imagen_url,categoria,fecha FROM posts WHERE usuario_id=%s ORDER BY fecha DESC LIMIT 12",(uid,))
    posts=[(pid,procesar(txt),img,cat,hace(f)) for pid,txt,img,cat,f in cur.fetchall()]; cur.close(); conn.close()
    
    btn = "<a href='/config' class='btn btn-sm btn-s'>Editar</a>" if mio else f"<form action='/seguir/{uid}' method='POST' style='display:inline'><input type='hidden' name='csrf_token' value='{{{{ csrf_token() }}}}'/><button class='btn btn-sm btn-s'>{'Dejar de seguir' if sigo else 'Seguir'}</button></form>"
    
    html_prof = f"""
    <div class="card" style="padding:0;overflow:hidden"><div class="banner"></div>
    <div style="padding:0 16px 16px"><div class="prof-h">
    <div class="av av-lg" style="background:{col};border:4px solid var(--surf)">{nom[0].upper()}</div>
    <div class="prof-i"><h1 class="prof-n">{nom}</h1><p class="prof-m">{moto or 'Motero/a'}</p></div>{btn}
    </div>{f"<p class='prof-b'>{html.escape(bio)}</p>" if bio else ""}
    <div class="prof-s"><div class="st"><span class="st-v">{pc}</span><span class="st-l">Posts</span></div>
    <div class="st"><span class="st-v">{flw}</span><span class="st-l">Seguidores</span></div>
    <div class="st"><span class="st-v">{flg}</span><span class="st-l">Siguiendo</span></div>
    <div class="st"><span class="st-v">🔥{racha}</span><span class="st-l">Racha</span></div></div>
    <p style="font-size:12px;color:var(--txtd);margin-top:8px">Desde {creado.strftime('%b %Y') if creado else '2024'}</p></div></div>
    <h3 style="margin:20px 0 12px">Publicaciones</h3>
    {"".join(f"<div class='card'><div class='fx g1 mb1'><span class='post-cat'>{cat}</span><span style='color:var(--txtd);font-size:13px;margin-left:auto'>{fecha}</span></div><div class='post-c'>{cont}</div>{f'<img src=\"{img}\" class=\"post-img\">' if img else ''}</div>" for pid,cont,img,cat,fecha in posts) if posts else "<div class='card tc' style='padding:24px;color:var(--txtd)'>Sin publicaciones</div>"}"""
    return page(html_prof, act='perfil', nc=contar_notifs(session['user_id']))

@app.route('/config', methods=['GET','POST'])
@login_required
def config():
    if request.method=='POST':
        bio, moto = request.form.get('bio','')[:200], request.form.get('moto','')[:50]
        conn, cur = get_db(), get_db().cursor()
        cur.execute("UPDATE usuarios SET bio=%s,moto=%s WHERE id=%s",(bio,moto,session['user_id']))
        conn.commit(); cur.close(); conn.close()
        session['bio'],session['moto']=bio,moto; flash("Actualizado ✓","s"); return redirect('/perfil')
    
    html_cfg = f"""
    <div class="card"><h2 style="margin-bottom:16px">Editar perfil</h2>
    <form method="POST"><input type="hidden" name="csrf_token" value="{{{{ csrf_token() }}}}"/>
    <label style="display:block;margin-bottom:6px;font-weight:500">Tu moto</label>
    <input type="text" name="moto" placeholder="Ej: Yamaha MT-07" value="{html.escape(session.get('moto',''))}" maxlength="50">
    <label style="display:block;margin:16px 0 6px;font-weight:500">Biografía</label>
    <textarea name="bio" placeholder="Sobre ti..." maxlength="200">{html.escape(session.get('bio',''))}</textarea>
    <small style="color:var(--txtd);display:block;margin-bottom:16px">Máx. 200 caracteres</small>
    <button type="submit" class="btn btn-p">Guardar</button><a href="/perfil" class="btn btn-s" style="margin-top:8px">Cancelar</a></form></div>"""
    return page(html_cfg, act='perfil', nc=contar_notifs(session['user_id']))

# -----------------------------------------------------------------------------
# SEGUIR / NOTIFS / BUSCAR
# -----------------------------------------------------------------------------
@app.route('/seguir/<int:uid>', methods=['POST'])
@login_required
def seguir(uid):
    if uid==session['user_id']: return redirect('/perfil')
    conn, cur = get_db(), get_db().cursor()
    try:
        cur.execute("INSERT INTO seguidores (seguidor_id,seguido_id) VALUES (%s,%s)",(session['user_id'],uid))
        notif(uid,'follow',f"{session['user_name']} te sigue",f"/perfil/{session['user_name']}"); conn.commit()
    except psycopg2.IntegrityError: conn.rollback(); cur.execute("DELETE FROM seguidores WHERE seguidor_id=%s AND seguido_id=%s",(session['user_id'],uid)); conn.commit()
    finally: cur.close(); conn.close()
    return redirect(request.referrer or f'/perfil/{uid}')

@app.route('/notifs')
@login_required
def notifs():
    conn, cur = get_db(), get_db().cursor()
    cur.execute("UPDATE notificaciones SET leido=TRUE WHERE usuario_id=%s",(session['user_id'],))
    cur.execute("SELECT tipo,mensaje,url,fecha FROM notificaciones WHERE usuario_id=%s ORDER BY fecha DESC LIMIT 30",(session['user_id'],))
    icons={'like':'⛽','comment':'💬','follow':'👤','mention':'@'}
    nl=[{'ic':icons.get(t,'🔔'),'msg':m,'url':u,'ti':hace(f)} for t,m,u,f in cur.fetchall()]; cur.close(); conn.close()
    
    html_n = f"""
    <h2 style="margin-bottom:16px">Notificaciones</h2><div class="nl">
    {"".join(f"<a href='{n['url'] or '#'}' class='ni{' unread' if i==0 else ''}'><span class='ni-ic'>{n['ic']}</span><div class='ni-c'><div class='ni-m'>{html.escape(n['msg'])}</div><div class='ni-t'>{n['ti']}</div></div></a>" for i,n in enumerate(nl)) if nl else "<div class='card tc' style='padding:30px;color:var(--txtd)'>🎉 Sin notifs nuevas</div>"}
    </div>"""
    return page(html_n, act='notifs', nc=0)

@app.route('/buscar')
@login_required
def buscar():
    q, tag = request.args.get('q','').strip(), request.args.get('tag','').strip()
    conn, cur = get_db(), get_db().cursor()
    
    if tag: cur.execute("SELECT p.id,u.nombre,u.avatar_color,p.contenido,p.imagen_url,p.fecha FROM posts p JOIN usuarios u ON p.usuario_id=u.id WHERE p.contenido ILIKE %s AND p.reportes<5 ORDER BY p.fecha DESC LIMIT 20",(f'%#{tag}%',)); tit=f'Posts con #{tag}'
    elif q: cur.execute("SELECT p.id,u.nombre,u.avatar_color,p.contenido,p.imagen_url,p.fecha FROM posts p JOIN usuarios u ON p.usuario_id=u.id WHERE (p.contenido ILIKE %s OR u.nombre ILIKE %s) AND p.reportes<5 ORDER BY p.fecha DESC LIMIT 20",(f'%{q}%',f'%{q}%')); tit=f'Resultados: "{q}"'
    else: cur.execute("SELECT p.id,u.nombre,u.avatar_color,p.contenido,p.imagen_url,p.fecha FROM posts p JOIN usuarios u ON p.usuario_id=u.id WHERE p.reportes<5 ORDER BY p.fecha DESC LIMIT 20"); tit='Explorar'
    
    res=[{'id':pid,'aut':a,'col':c,'cont':procesar(txt),'img':img,'fecha':hace(f)} for pid,a,c,txt,img,f in cur.fetchall()]; cur.close(); conn.close()
    
    html_bus = f"""
    <h2 style="margin-bottom:12px">{tit}</h2><form action="/buscar" method="GET" style="margin-bottom:16px"><input type="search" name="q" placeholder="Buscar..." value="{html.escape(q)}" style="margin:0"></form>
    {"".join(f"<div class='card'><div class='fx g1 mb1'><div class='av' style='background:{r['col']};width:32px;height:32px;font-size:14px'>{r['aut'][0].upper()}</div><div><a href='/perfil/{r['aut']}' style='font-weight:500'>{r['aut']}</a> <span style='color:var(--txtd);font-size:13px'>· {r['fecha']}</span></div></div><div class='post-c'>{r['cont']}</div>{f'<img src=\"{r['img']}\" class=\"post-img\">' if r['img'] else ''}</div>" for r in res) if res else "<div class='card tc' style='padding:30px;color:var(--txtd)'>Sin resultados</div>"}"""
    return page(html_bus, act='buscar', nc=contar_notifs(session['user_id']))

# -----------------------------------------------------------------------------
# UTILS
# -----------------------------------------------------------------------------
@app.route('/logout')
def logout(): session.clear(); return redirect('/')

@app.errorhandler(404)
def e404(e): return page("""<div class="card tc" style="padding:40px 20px"><div style="font-size:48px;margin-bottom:16px">🔧</div><h2 style="margin-bottom:8px">404</h2><p style="color:var(--txtd);margin-bottom:20px">Página no encontrada</p><a href="/foro" class="btn btn-p" style="width:auto;padding:10px 24px">Volver</a></div>""", nc=contar_notifs(session['user_id']) if 'user_id' in session else 0), 404

@app.errorhandler(500)
def e500(e): return page("""<div class="card tc" style="padding:40px 20px"><div style="font-size:48px;margin-bottom:16px">⚠️</div><h2 style="margin-bottom:8px">Error</h2><p style="color:var(--txtd);margin-bottom:20px">Intenta recargar</p><button onclick="location.reload()" class="btn btn-p" style="width:auto;padding:10px 24px">Recargar</button></div>""", nc=0), 500

# -----------------------------------------------------------------------------
# ENTRY
# -----------------------------------------------------------------------------
if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
