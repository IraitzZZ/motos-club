# =============================================================================
# MOTOSCLUB v2.0  —  funciona con Python 3.14+ (usa pg8000, puro Python)
# =============================================================================
import os, re, html, json, requests, pg8000.native as pg
from flask import (Flask, request, redirect, render_template_string,
                   session, flash, jsonify)
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from functools import wraps
from urllib.parse import urlparse

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'cambiar-en-produccion-abc123')

DATABASE_URL  = os.environ.get('DATABASE_URL', '')
IMGBB_API_KEY = os.environ.get('IMGBB_API_KEY', '27a447d71db292f6c1296f509a06b09e')

# ─── DB ───────────────────────────────────────────────────────────────────────
def parse_db_url(url):
    u = urlparse(url)
    return dict(host=u.hostname, port=u.port or 5432,
                database=u.path.lstrip('/'),
                user=u.username, password=u.password,
                ssl_context=True)

def get_db():
    params = parse_db_url(DATABASE_URL)
    conn = pg.Connection(**params)
    return conn

def run(conn, sql, params=()):
    return conn.run(sql, *params)

def one(conn, sql, params=()):
    rows = conn.run(sql, *params)
    return rows[0] if rows else None

def init_db():
    conn = get_db()
    tables = [
        """CREATE TABLE IF NOT EXISTS usuarios (
            id SERIAL PRIMARY KEY, nombre TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL, bio TEXT DEFAULT '',
            moto TEXT DEFAULT '', ubicacion TEXT DEFAULT '',
            web TEXT DEFAULT '', avatar_url TEXT DEFAULT '',
            banner_url TEXT DEFAULT '', rol TEXT DEFAULT 'user',
            racha INTEGER DEFAULT 0, ultima_actividad DATE,
            verificado BOOLEAN DEFAULT FALSE,
            fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
        """CREATE TABLE IF NOT EXISTS posts (
            id SERIAL PRIMARY KEY,
            usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
            contenido TEXT NOT NULL, imagen_url TEXT DEFAULT '',
            categoria TEXT DEFAULT 'General',
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reportes INTEGER DEFAULT 0, pineado BOOLEAN DEFAULT FALSE,
            vistas INTEGER DEFAULT 0)""",
        """CREATE TABLE IF NOT EXISTS seguidores (
            seguidor_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
            seguido_id  INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (seguidor_id, seguido_id))""",
        """CREATE TABLE IF NOT EXISTS likes (
            usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
            post_id    INTEGER REFERENCES posts(id)    ON DELETE CASCADE,
            PRIMARY KEY (usuario_id, post_id))""",
        """CREATE TABLE IF NOT EXISTS comentarios (
            id SERIAL PRIMARY KEY,
            post_id    INTEGER REFERENCES posts(id)    ON DELETE CASCADE,
            usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
            contenido TEXT NOT NULL,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
        """CREATE TABLE IF NOT EXISTS notificaciones (
            id SERIAL PRIMARY KEY,
            usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
            tipo TEXT, mensaje TEXT, url TEXT,
            leido BOOLEAN DEFAULT FALSE,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
        """CREATE TABLE IF NOT EXISTS bookmarks (
            usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
            post_id    INTEGER REFERENCES posts(id)    ON DELETE CASCADE,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (usuario_id, post_id))""",
        """CREATE TABLE IF NOT EXISTS mensajes (
            id SERIAL PRIMARY KEY,
            remitente_id    INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
            destinatario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
            contenido TEXT NOT NULL, leido BOOLEAN DEFAULT FALSE,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
        """CREATE TABLE IF NOT EXISTS rutas (
            id SERIAL PRIMARY KEY,
            usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
            titulo TEXT NOT NULL, descripcion TEXT DEFAULT '',
            distancia FLOAT DEFAULT 0, duracion TEXT DEFAULT '',
            dificultad TEXT DEFAULT 'Media', imagen_url TEXT DEFAULT '',
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP, likes INTEGER DEFAULT 0)""",
    ]
    for t in tables:
        conn.run(t)
    for idx in [
        "CREATE INDEX IF NOT EXISTS idx_posts_u ON posts(usuario_id)",
        "CREATE INDEX IF NOT EXISTS idx_posts_f ON posts(fecha DESC)",
        "CREATE INDEX IF NOT EXISTS idx_likes_p ON likes(post_id)",
        "CREATE INDEX IF NOT EXISTS idx_coms_p  ON comentarios(post_id)",
    ]:
        conn.run(idx)
    conn.close()

# ─── HELPERS ──────────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def d(*a, **kw):
        if 'user_id' not in session:
            flash("Inicia sesión.", "error"); return redirect('/')
        return f(*a, **kw)
    return d

def admin_required(f):
    @wraps(f)
    def d(*a, **kw):
        if session.get('rol') != 'admin':
            flash("Sin permisos.", "error"); return redirect('/foro')
        return f(*a, **kw)
    return d

def upload_imgbb(f):
    if not f: return ''
    try:
        r = requests.post("https://api.imgbb.com/1/upload",
                          files={"image": f.read()},
                          data={"key": IMGBB_API_KEY}, timeout=15)
        if r.status_code == 200: return r.json()['data']['url']
    except: pass
    return ''

def procesar(text):
    text = html.escape(text)
    text = re.sub(r'https?://(?:www\.)?youtu(?:be\.com/watch\?v=|\.be/)([\w-]+)',
        r'<div class="vid"><iframe src="https://www.youtube.com/embed/\1" allowfullscreen loading="lazy"></iframe></div>', text)
    text = re.sub(r'(https?://\S+?\.(?:png|jpg|jpeg|gif|webp)(?:\?\S*)?)',
        r'<img src="\1" class="pimg" loading="lazy">', text)
    text = re.sub(r'(?<!["\'])https?://\S+',
        r'<a href="\g<0>" target="_blank" rel="noopener" class="plink">\g<0></a>', text)
    text = re.sub(r'@(\w+)', r'<a href="/perfil/\1" class="mention">@\1</a>', text)
    text = re.sub(r'#(\w+)', r'<a href="/buscar?tag=\1" class="htag">#\1</a>', text)
    return text

def ago(dt):
    if not dt: return ''
    d = datetime.now() - dt
    if d.days > 365: return f"{d.days//365}a"
    if d.days > 30:  return f"{d.days//30}m"
    if d.days > 0:   return f"{d.days}d"
    if d.seconds >= 3600: return f"{d.seconds//3600}h"
    if d.seconds >= 60:   return f"{d.seconds//60}min"
    return "ahora"

def color(s):
    h = sum(ord(c) for c in s) % 360
    return f"hsl({h},60%,45%)"

def nc_for(uid):
    try:
        c = get_db()
        r = c.run("SELECT COUNT(*) FROM notificaciones WHERE usuario_id=$1 AND leido=FALSE", uid)
        c.close(); return r[0][0]
    except: return 0

def mc_for(uid):
    try:
        c = get_db()
        r = c.run("SELECT COUNT(*) FROM mensajes WHERE destinatario_id=$1 AND leido=FALSE", uid)
        c.close(); return r[0][0]
    except: return 0

def notif(uid, tipo, msg, url):
    try:
        c = get_db()
        c.run("INSERT INTO notificaciones(usuario_id,tipo,mensaje,url) VALUES($1,$2,$3,$4)", uid, tipo, msg, url)
        c.close()
    except: pass

CAT = {'General':'🏍️','Ruta':'🛣️','Mecanica':'🔧','Venta':'💰','Evento':'📅','Consejo':'💡','Foto':'📷'}

def racha_badge(r):
    if r>=100: return "🏆"
    if r>=30:  return "💎"
    if r>=14:  return "🥇"
    if r>=7:   return "🔥"
    if r>=3:   return "⚡"
    return ""

# ─── CSS ──────────────────────────────────────────────────────────────────────
CSS = """
@import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@700;800&family=DM+Sans:wght@400;500;600&family=Space+Mono:wght@700&display=swap');
:root{--bg:#0A0A0C;--bg2:#111115;--sur:#18181F;--sur2:#222230;--brd:#2A2A38;--acc:#FF4500;--acc2:#FF6B35;--blu:#3B82F6;--grn:#22C55E;--yel:#F59E0B;--txt:#F0F0F5;--mut:#70707A;--shd:0 8px 32px rgba(0,0,0,.6);--r:14px}
:root[data-theme=light]{--bg:#F4F4F8;--bg2:#fff;--sur:#fff;--sur2:#F0F0F5;--brd:#E0E0E8;--txt:#111118;--mut:#888896;--shd:0 4px 20px rgba(0,0,0,.08)}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{font-family:'DM Sans',sans-serif;background:var(--bg);color:var(--txt);line-height:1.6;min-height:100vh;transition:background .3s,color .3s}
h1,h2,h3,.disp{font-family:'Barlow Condensed',sans-serif;letter-spacing:.5px;text-transform:uppercase}
.wrap{max-width:680px;margin:0 auto;padding:0 16px}
.navbar{position:sticky;top:0;z-index:100;background:rgba(10,10,12,.88);backdrop-filter:blur(24px) saturate(1.4);border-bottom:1px solid var(--brd);padding:0}
[data-theme=light] .navbar{background:rgba(255,255,255,.92)}
.nav-inner{display:flex;align-items:center;justify-content:space-between;max-width:680px;margin:0 auto;padding:12px 16px;gap:12px}
.nav-brand{font-family:'Barlow Condensed',sans-serif;font-size:26px;font-weight:800;letter-spacing:1px;text-decoration:none;color:var(--txt);display:flex;align-items:center;gap:6px}
.nav-brand span{color:var(--acc)}
.nav-links{display:flex;align-items:center;gap:6px}
.ni{width:38px;height:38px;border-radius:10px;display:flex;align-items:center;justify-content:center;background:transparent;border:1px solid var(--brd);color:var(--txt);font-size:18px;cursor:pointer;text-decoration:none;position:relative;transition:all .2s;line-height:1}
.ni:hover{background:var(--sur2);border-color:var(--acc)}
.nbadge{position:absolute;top:-4px;right:-4px;background:var(--acc);color:#fff;font-size:9px;font-weight:700;width:16px;height:16px;border-radius:50%;display:flex;align-items:center;justify-content:center;border:2px solid var(--bg)}
.nbtn{padding:7px 14px;border-radius:10px;background:var(--sur);border:1px solid var(--brd);color:var(--txt);font-weight:600;font-size:13px;cursor:pointer;text-decoration:none;transition:all .2s;white-space:nowrap}
.nbtn:hover{border-color:var(--acc);color:var(--acc)}
.nbtn.on{background:var(--acc);border-color:var(--acc);color:#fff}
.tabs{display:flex;gap:4px;margin-bottom:20px;background:var(--sur);border-radius:var(--r);padding:4px;border:1px solid var(--brd)}
.tab{flex:1;padding:9px;border-radius:10px;border:none;background:transparent;color:var(--mut);font-weight:600;font-size:13px;cursor:pointer;transition:all .2s;text-decoration:none;text-align:center;display:block}
.tab.on,.tab:hover{background:var(--acc);color:#fff}
.card{background:var(--sur);border:1px solid var(--brd);border-radius:var(--r);padding:20px;margin-bottom:14px;box-shadow:var(--shd);transition:border-color .2s}
.ct{padding:14px}
input,textarea,select{width:100%;background:var(--bg2);border:1.5px solid var(--brd);color:var(--txt);padding:12px 16px;border-radius:10px;font-family:'DM Sans',sans-serif;font-size:15px;outline:none;margin-bottom:10px;transition:border-color .2s;-webkit-appearance:none;appearance:none}
input:focus,textarea:focus,select:focus{border-color:var(--acc)}
textarea{resize:vertical;min-height:90px}
label{font-size:13px;font-weight:600;color:var(--mut);display:block;margin-bottom:5px}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;padding:12px 22px;border-radius:10px;border:none;font-family:'DM Sans',sans-serif;font-weight:600;font-size:15px;cursor:pointer;transition:all .2s;text-decoration:none;white-space:nowrap}
.bp{background:var(--acc);color:#fff;width:100%}
.bp:hover{background:var(--acc2);transform:translateY(-1px)}
.bs{background:var(--sur2);border:1px solid var(--brd);color:var(--txt);padding:7px 14px;font-size:13px}
.bs:hover{border-color:var(--acc);color:var(--acc)}
.bsm{padding:5px 12px;font-size:12px;border-radius:8px}
.bf{background:var(--blu);color:#fff;padding:7px 16px;border-radius:20px;font-size:13px}
.bf.fol{background:transparent;border:1.5px solid var(--brd);color:var(--txt)}
.av{border-radius:50%;overflow:hidden;display:flex;align-items:center;justify-content:center;font-weight:700;color:#fff;flex-shrink:0;background:var(--sur2)}
.av img{width:100%;height:100%;object-fit:cover}
.avl{width:80px;height:80px;font-size:30px;border:3px solid var(--bg)}
.avm{width:46px;height:46px;font-size:18px}
.avs{width:34px;height:34px;font-size:14px}
.ph{display:flex;gap:12px;margin-bottom:12px;align-items:flex-start}
.pm{flex:1;min-width:0}
.pm strong{font-size:15px}
.pm small{color:var(--mut);font-size:12px}
.pb{font-size:15px;line-height:1.7;word-break:break-word}
.pb a{color:var(--acc);text-decoration:none}
.pimg{width:100%;border-radius:12px;margin-top:12px;border:1px solid var(--brd);display:block}
.vid{margin-top:12px;border-radius:12px;overflow:hidden;aspect-ratio:16/9}
.vid iframe{width:100%;height:100%;border:none}
.cbadge{display:inline-flex;align-items:center;gap:4px;font-size:11px;font-weight:600;padding:3px 8px;background:var(--sur2);border-radius:20px;color:var(--mut);margin-bottom:8px}
.cbadge.Ruta{color:var(--grn)}.cbadge.Mecanica{color:var(--blu)}.cbadge.Venta{color:var(--yel)}.cbadge.Evento{color:var(--acc)}
.pa{display:flex;gap:4px;margin-top:14px;padding-top:12px;border-top:1px solid var(--brd);flex-wrap:wrap}
.ab{display:flex;align-items:center;gap:5px;padding:6px 12px;border-radius:8px;border:none;background:transparent;color:var(--mut);font-size:13px;font-weight:600;cursor:pointer;transition:all .15s}
.ab:hover{background:var(--sur2);color:var(--txt)}
.ab.on{color:var(--acc)}.ab.onb{color:var(--blu)}
.cb{margin-top:12px;border-top:1px solid var(--brd);padding-top:12px;display:none}
.ci{display:flex;gap:8px;margin-bottom:10px;align-items:flex-start}
.cbub{background:var(--bg2);border-radius:0 10px 10px 10px;padding:8px 12px;flex:1;font-size:13px;border:1px solid var(--brd)}
.cbub strong{display:block;font-size:12px;margin-bottom:2px}
.banner{height:180px;border-radius:var(--r) var(--r) 0 0;background:linear-gradient(135deg,#1a1a2e,#0f3460);background-size:cover;background-position:center;position:relative}
.pcard{padding:0;overflow:hidden}
.pbody{padding:0 20px 20px}
.pav{position:relative;margin-top:-44px;width:80px;height:80px;z-index:2}
.prow{display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:12px;flex-wrap:wrap;gap:10px}
.pstats{display:flex;gap:24px;margin:14px 0}
.stat span{display:block;font-size:20px;font-weight:700}
.stat small{color:var(--mut);font-size:12px}
.ver{color:var(--blu);font-size:14px}
.rbadge{display:inline-flex;align-items:center;gap:4px;font-size:12px;background:rgba(255,69,0,.12);color:var(--acc);padding:2px 8px;border-radius:20px;border:1px solid rgba(255,69,0,.25);font-weight:600}
.sbar{display:flex;gap:8px;margin-bottom:16px;align-items:center}
.sbar input{margin:0}
.ni-item{display:flex;gap:12px;align-items:flex-start;padding:14px;border-bottom:1px solid var(--brd);text-decoration:none;color:var(--txt);transition:background .15s}
.ni-item:last-child{border-bottom:none}
.ni-item:hover{background:var(--sur2)}
.ni-item.unr{background:rgba(59,130,246,.06)}
.ndot{width:8px;height:8px;border-radius:50%;background:var(--blu);flex-shrink:0;margin-top:6px}
.mlist{display:flex;flex-direction:column;gap:8px}
.mbub{max-width:75%;padding:10px 14px;border-radius:14px;font-size:14px;line-height:1.5}
.mbub.me{background:var(--acc);color:#fff;align-self:flex-end;border-radius:14px 14px 4px 14px}
.mbub.them{background:var(--sur2);align-self:flex-start;border-radius:14px 14px 14px 4px}
.mmt{font-size:10px;color:var(--mut);margin-top:2px}
.chdr{display:flex;align-items:center;gap:10px;padding-bottom:14px;border-bottom:1px solid var(--brd);margin-bottom:16px}
.rcard{background:var(--sur);border:1px solid var(--brd);border-radius:var(--r);overflow:hidden;margin-bottom:14px}
.rimg{width:100%;height:180px;object-fit:cover;display:block}
.rbody{padding:16px}
.rstats{display:flex;gap:16px;margin-top:10px}
.rstat{text-align:center}
.rstat span{display:block;font-weight:700}
.rstat small{color:var(--mut);font-size:11px}
.dif{font-size:11px;padding:2px 8px;border-radius:20px;font-weight:600}
.dif-Facil,.dif-Easy{background:rgba(34,197,94,.15);color:var(--grn)}
.dif-Media{background:rgba(245,158,11,.15);color:var(--yel)}
.dif-Dificil{background:rgba(255,69,0,.15);color:var(--acc)}
.dif-Extrema{background:rgba(255,0,0,.2);color:#f00}
.lwrap{min-height:calc(100vh - 70px);display:flex;align-items:center;justify-content:center;padding:20px 16px}
.lbox{width:100%;max-width:420px}
.ltitle{font-family:'Barlow Condensed',sans-serif;font-size:52px;font-weight:800;text-align:center;margin-bottom:6px;letter-spacing:2px}
.ltitle span{color:var(--acc)}
.lsub{text-align:center;color:var(--mut);margin-bottom:28px;font-size:14px}
.ltabs{display:flex;gap:0;margin-bottom:20px;border-radius:10px;overflow:hidden;border:1px solid var(--brd)}
.ltab{flex:1;padding:11px;text-align:center;cursor:pointer;background:var(--sur);color:var(--mut);border:none;font-weight:600;font-size:14px;font-family:'DM Sans',sans-serif;transition:all .2s}
.ltab.on{background:var(--acc);color:#fff}
.flash{padding:12px 16px;border-radius:10px;margin-bottom:14px;font-weight:600;font-size:14px;text-align:center;animation:sld .3s ease}
.fe{background:rgba(255,69,0,.12);border:1px solid rgba(255,69,0,.3);color:var(--acc)}
.fs{background:rgba(34,197,94,.12);border:1px solid rgba(34,197,94,.3);color:var(--grn)}
@keyframes sld{from{opacity:0;transform:translateY(-8px)}to{opacity:1;transform:translateY(0)}}
.div{border:none;border-top:1px solid var(--brd);margin:16px 0}
.mut{color:var(--mut);font-size:13px}
.empty{text-align:center;padding:40px 20px;color:var(--mut)}
.empty .ic{font-size:48px;display:block;margin-bottom:12px}
.mention{color:var(--blu)!important}
.htag{color:var(--acc)!important}
.plink{color:var(--blu)!important;font-size:13px}
.pill{display:inline-block;padding:3px 10px;border-radius:20px;font-size:12px;font-weight:600;background:var(--sur2);color:var(--mut)}
.stitle{font-size:22px;margin:20px 0 12px;color:var(--txt)}
@media(max-width:600px){.ltitle{font-size:40px}.pstats{gap:14px}}
"""

# ─── LAYOUT ───────────────────────────────────────────────────────────────────
def layout(body, active='', nc=0, mc=0):
    uid   = session.get('user_id', 0)
    uname = session.get('user_name', '')
    nav   = ''
    if uid:
        nav = f'''<nav class="navbar"><div class="nav-inner">
  <a href="/foro" class="nav-brand">MOTOS<span>CLUB</span></a>
  <div class="nav-links">
    <button onclick="tglTheme()" class="ni" id="thbtn">🌙</button>
    <a href="/buscar" class="ni" title="Explorar">🔍</a>
    <a href="/mensajes" class="ni" style="position:relative;">✉️{'<span class="nbadge">'+str(mc)+'</span>' if mc else ''}</a>
    <a href="/notificaciones" class="ni" style="position:relative;">🔔{'<span class="nbadge">'+str(nc)+'</span>' if nc else ''}</a>
    <a href="/perfil/{uname}" class="nbtn {'on' if active=='perfil' else ''}">Yo</a>
    <a href="/logout" class="nbtn">Salir</a>
  </div>
</div></nav>'''
    else:
        nav = '<nav class="navbar"><div class="nav-inner"><a href="/" class="nav-brand">MOTOS<span>CLUB</span></a></div></nav>'

    return f'''<!DOCTYPE html>
<html lang="es" data-theme="dark"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MOTOSCLUB</title><style>{CSS}</style></head><body>
{nav}
<div class="wrap" style="padding-top:20px;padding-bottom:60px;">
{{% with messages=get_flashed_messages(with_categories=true) %}}{{% if messages %}}
{{% for cat,msg in messages %}}<div class="flash f{{{{cat}}}}">{{{{msg}}}}</div>{{% endfor %}}
{{% endif %}}{{% endwith %}}
{body}
</div>
<script>
function applyTheme(t){{document.documentElement.setAttribute('data-theme',t);localStorage.setItem('theme',t);var b=document.getElementById('thbtn');if(b)b.textContent=t==='light'?'☀️':'🌙';}}
function tglTheme(){{applyTheme(localStorage.getItem('theme')==='light'?'dark':'light');}}
(function(){{applyTheme(localStorage.getItem('theme')||'dark');}})();
function tglCom(id){{var e=document.getElementById('cb'+id);if(e)e.style.display=e.style.display==='none'?'block':'none';}}
document.querySelectorAll('textarea[data-max]').forEach(function(ta){{
  var mx=parseInt(ta.dataset.max),ct=document.createElement('div');
  ct.className='mut';ct.style.cssText='text-align:right;margin-top:-6px;margin-bottom:8px;font-size:12px;';
  ta.insertAdjacentElement('afterend',ct);
  function upd(){{var l=mx-ta.value.length;ct.textContent=l+' restantes';ct.style.color=l<20?'var(--acc)':'var(--mut)';if(ta.value.length>mx)ta.value=ta.value.substring(0,mx);}}
  ta.addEventListener('input',upd);upd();
}});
setTimeout(function(){{document.querySelectorAll('.flash').forEach(function(e){{e.style.transition='opacity .5s';e.style.opacity='0';setTimeout(function(){{e.remove();}},500);}});}},4000);
</script></body></html>'''

# ─── AUTH ─────────────────────────────────────────────────────────────────────
@app.route('/', methods=['GET','POST'])
def login():
    if 'user_id' in session: return redirect('/foro')
    if request.method == 'POST':
        nombre = request.form.get('nombre','').strip()
        passw  = request.form.get('password','')
        action = request.form.get('action','login')
        if not nombre or not passw:
            flash("Completa todos los campos.", "error"); return redirect('/')
        conn = get_db()
        if action == 'register':
            if len(nombre)<3: flash("Mínimo 3 caracteres.", "error")
            elif len(nombre)>30: flash("Nombre demasiado largo.", "error")
            elif not re.match(r'^[a-zA-Z0-9_.-]+$', nombre): flash("Solo letras, números, guiones y puntos.", "error")
            elif len(passw)<6: flash("Contraseña mínimo 6 caracteres.", "error")
            else:
                try:
                    conn.run("INSERT INTO usuarios(nombre,password) VALUES($1,$2)", nombre, generate_password_hash(passw))
                    flash("Cuenta creada. Entra ahora.", "success")
                except: flash("Ese usuario ya existe.", "error")
        else:
            rows = conn.run("SELECT id,password,avatar_url,banner_url,bio,moto,rol FROM usuarios WHERE nombre=$1", nombre)
            if rows and check_password_hash(rows[0][1], passw):
                u = rows[0]
                session.update({'user_id':u[0],'user_name':nombre,'avatar_url':u[2] or '','banner_url':u[3] or '','bio':u[4] or '','moto':u[5] or '','rol':u[6] or 'user'})
                conn.close(); return redirect('/foro')
            else: flash("Usuario o contraseña incorrectos.", "error")
        conn.close(); return redirect('/')

    body = '''<div class="lwrap"><div class="lbox">
<div class="ltitle">MOTOS<span>CLUB</span></div>
<p class="lsub">La comunidad de los que viven sobre dos ruedas 🏍️</p>
<div class="card">
  <div class="ltabs">
    <button class="ltab on" onclick="sw('l',this)">ENTRAR</button>
    <button class="ltab" onclick="sw('r',this)">REGISTRARSE</button>
  </div>
  <form method="POST" id="fl">
    <input type="hidden" name="action" value="login">
    <label>Usuario</label><input type="text" name="nombre" placeholder="Tu nombre de usuario" required autocomplete="username">
    <label>Contraseña</label><input type="password" name="password" placeholder="••••••••" required autocomplete="current-password">
    <button class="btn bp" type="submit">ENTRAR AL CLUB</button>
  </form>
  <form method="POST" id="fr" style="display:none">
    <input type="hidden" name="action" value="register">
    <label>Nombre de usuario</label><input type="text" name="nombre" placeholder="letras, números, guiones" required autocomplete="username" minlength="3" maxlength="30" pattern="[a-zA-Z0-9_.-]+">
    <label>Contraseña (mín. 6 caracteres)</label><input type="password" name="password" placeholder="••••••••" required minlength="6" autocomplete="new-password">
    <button class="btn bp" type="submit">CREAR CUENTA</button>
  </form>
</div>
<p style="text-align:center;color:var(--mut);font-size:12px;margin-top:16px;">Comparte tu pasión por las motos 🔥</p>
</div></div>
<script>function sw(t,b){document.querySelectorAll('.ltab').forEach(x=>x.classList.remove('on'));b.classList.add('on');document.getElementById('fl').style.display=t==='l'?'block':'none';document.getElementById('fr').style.display=t==='r'?'block':'none';}</script>'''
    return render_template_string(layout(body))

@app.route('/logout')
def logout():
    session.clear(); return redirect('/')

# ─── FORO ─────────────────────────────────────────────────────────────────────
@app.route('/foro')
@login_required
def foro():
    filtro = request.args.get('filtro','todo')
    cat    = request.args.get('cat','')
    conn   = get_db()
    uid    = session['user_id']

    if filtro == 'feed':
        ids = [r[0] for r in conn.run("SELECT seguido_id FROM seguidores WHERE seguidor_id=$1", uid)] + [uid]
        ids_str = ','.join(str(i) for i in ids)
        where = f"p.usuario_id IN ({ids_str}) AND" if ids_str else "FALSE AND"
    elif cat:
        where = f"p.categoria='{cat}' AND"
    else:
        where = ""

    posts_raw = conn.run(f"""
        SELECT p.id,u.nombre,p.contenido,p.fecha,p.categoria,u.avatar_url,p.usuario_id,
               p.imagen_url,p.pineado,u.verificado,u.moto,
               (SELECT COUNT(*) FROM likes WHERE post_id=p.id),
               (SELECT COUNT(*) FROM comentarios WHERE post_id=p.id),
               (CASE WHEN EXISTS(SELECT 1 FROM likes WHERE post_id=p.id AND usuario_id={uid}) THEN TRUE ELSE FALSE END),
               (CASE WHEN EXISTS(SELECT 1 FROM bookmarks WHERE post_id=p.id AND usuario_id={uid}) THEN TRUE ELSE FALSE END)
        FROM posts p JOIN usuarios u ON p.usuario_id=u.id
        WHERE {where} p.reportes<5
        ORDER BY p.pineado DESC,p.fecha DESC LIMIT 40""")

    # trending tags
    tr_raw = conn.run("SELECT contenido FROM posts WHERE fecha > NOW()-INTERVAL '7 days' LIMIT 200")
    tags = {}
    for r in tr_raw:
        for t in re.findall(r'#(\w+)', r[0]):
            tags[t] = tags.get(t,0)+1
    trending = sorted(tags.items(), key=lambda x:-x[1])[:6]

    # sugerencias
    sug = conn.run(f"""SELECT u.nombre,u.avatar_url,u.moto FROM usuarios u
        WHERE u.id!={uid} AND u.id NOT IN (SELECT seguido_id FROM seguidores WHERE seguidor_id={uid})
        ORDER BY RANDOM() LIMIT 4""")
    nc = nc_for(uid); mc = mc_for(uid)
    conn.close()

    # Composer
    cats_opts = ''.join(f'<option value="{k}">{v} {k}</option>' for k,v in CAT.items())
    av_me = f'<img src="{session["avatar_url"]}">' if session.get("avatar_url","").startswith("http") else session["user_name"][0].upper()
    av_col = color(session["user_name"])

    body = f'''<div class="card">
  <form method="POST" action="/post" enctype="multipart/form-data">
    <div style="display:flex;gap:10px;align-items:flex-start;">
      <a href="/perfil/{session['user_name']}"><div class="av avm" style="background:{av_col}">{av_me}</div></a>
      <div style="flex:1;">
        <textarea name="contenido" placeholder="¿Qué ruedas hoy? Usa @usuario y #hashtag…" data-max="500"></textarea>
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
          <select name="categoria" style="width:auto;margin:0;font-size:13px;padding:8px 12px;">{cats_opts}</select>
          <label style="display:flex;align-items:center;gap:6px;cursor:pointer;background:var(--sur2);border:1px solid var(--brd);border-radius:8px;padding:8px 12px;margin:0;color:var(--mut);font-size:13px;font-weight:600;">
            📷 Foto<input type="file" name="foto" accept="image/*" style="display:none;">
          </label>
          <button class="btn bp" type="submit" style="width:auto;padding:8px 20px;margin:0;">PUBLICAR</button>
        </div>
      </div>
    </div>
  </form>
</div>

<div class="tabs">
  <a href="/foro?filtro=todo" class="tab {'on' if filtro=='todo' else ''}">🌐 Global</a>
  <a href="/foro?filtro=feed" class="tab {'on' if filtro=='feed' else ''}">🏠 Feed</a>
  <a href="/foro?filtro=cat&cat=Ruta" class="tab {'on' if cat=='Ruta' else ''}">🛣️ Rutas</a>
  <a href="/rutas" class="tab">🗺️ Mapas</a>
</div>'''

    if trending:
        pills = ''.join(f'<a href="/buscar?tag={t}" class="pill" style="margin:2px;">#{t}</a>' for t,_ in trending)
        body += f'<div class="card ct" style="margin-bottom:14px;"><div class="mut" style="font-size:11px;font-weight:700;margin-bottom:8px;text-transform:uppercase;letter-spacing:1px;">🔥 Trending</div><div style="display:flex;flex-wrap:wrap;gap:4px;">{pills}</div></div>'

    if not posts_raw:
        body += '<div class="card empty"><span class="ic">🏍️</span><strong>¡Sin posts todavía!</strong><br><a href="/buscar" class="btn bs bsm" style="display:inline-flex;margin-top:12px;">Explorar moteros</a></div>'

    for p in posts_raw:
        pid,autor,cont,fecha,categ,av_url,p_uid,img,pineado,verif,moto,nlikes,ncoms,liked,bookmarked = p
        av_h = f'<img src="{av_url}">' if av_url and av_url.startswith('http') else autor[0].upper()
        coms_raw = conn.run(f"SELECT u.nombre,c.contenido,c.fecha,u.avatar_url FROM comentarios c JOIN usuarios u ON c.usuario_id=u.id WHERE c.post_id={pid} ORDER BY c.fecha LIMIT 5") if False else []
        # get comments
        try:
            conn2 = get_db()
            coms_raw = conn2.run("SELECT u.nombre,c.contenido,c.fecha,u.avatar_url FROM comentarios c JOIN usuarios u ON c.usuario_id=u.id WHERE c.post_id=$1 ORDER BY c.fecha LIMIT 5", pid)
            conn2.close()
        except: coms_raw = []

        coms_html = ''
        for c in coms_raw:
            cav = f'<img src="{c[3]}">' if c[3] and c[3].startswith('http') else c[0][0].upper()
            coms_html += f'<div class="ci"><div class="av avs" style="background:{color(c[0])}">{cav}</div><div class="cbub"><strong><a href="/perfil/{c[0]}" style="color:var(--txt);text-decoration:none;">{c[0]}</a> <span style="color:var(--mut);font-weight:400;">{ago(c[2])}</span></strong>{html.escape(c[1])}</div></div>'

        ver = ' <span class="ver">✓</span>' if verif else ''
        pin = ' 📌' if pineado else ''
        del_btn = f'<form action="/delete/{pid}" method="POST" onsubmit="return confirm(\'¿Borrar?\')"><button class="btn bs bsm">🗑️</button></form>' if p_uid==uid else ''
        body += f'''<div class="card" id="p{pid}">
  <div class="ph">
    <a href="/perfil/{autor}"><div class="av avm" style="background:{color(autor)}">{av_h}</div></a>
    <div class="pm">
      <div><a href="/perfil/{autor}" style="text-decoration:none;color:var(--txt);"><strong>{autor}</strong>{ver}{pin}</a></div>
      <small>{ago(fecha)} · {moto or "Motero"}</small>
    </div>
    <div style="display:flex;gap:6px;">
      {del_btn}
      <form action="/report/{pid}" method="POST" onsubmit="return confirm('¿Reportar?')"><button class="btn bs bsm">⚠️</button></form>
    </div>
  </div>
  <span class="cbadge {categ}">{CAT.get(categ,"🏍️")} {categ}</span>
  <div class="pb">{procesar(cont)}</div>
  {'<img src="'+img+'" class="pimg" loading="lazy">' if img else ''}
  <div class="pa">
    <form action="/like/{pid}" method="POST" style="display:inline;"><button class="ab {'on' if liked else ''}">⛽ {nlikes}</button></form>
    <button class="ab" onclick="tglCom({pid})">💬 {ncoms}</button>
    <form action="/bookmark/{pid}" method="POST" style="display:inline;"><button class="ab {'onb' if bookmarked else ''}">🔖</button></form>
    <a href="/post/{pid}" class="ab" style="margin-left:auto;">🔗</a>
  </div>
  <div class="cb" id="cb{pid}">
    <form action="/comment/{pid}" method="POST" style="display:flex;gap:8px;margin-bottom:12px;">
      <input type="text" name="contenido" placeholder="Comentar…" required style="margin:0;flex:1;">
      <button class="btn bs" type="submit" style="width:auto;padding:10px 14px;margin:0;">↩</button>
    </form>
    {coms_html}
  </div>
</div>'''

    if sug:
        body += '<div class="card ct"><div class="mut" style="font-size:11px;font-weight:700;margin-bottom:12px;text-transform:uppercase;letter-spacing:1px;">👥 Moteros que quizás conozcas</div>'
        for s in sug:
            sav = f'<img src="{s[1]}">' if s[1] and s[1].startswith('http') else s[0][0].upper()
            body += f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;"><a href="/perfil/{s[0]}"><div class="av avs" style="background:{color(s[0])}">{sav}</div></a><div style="flex:1;"><a href="/perfil/{s[0]}" style="color:var(--txt);text-decoration:none;font-weight:600;">{s[0]}</a><div style="font-size:12px;color:var(--mut);">{s[2] or "Motero"}</div></div><form action="/seguir/{s[0]}" method="POST"><button class="btn bf bsm">Seguir</button></form></div>'
        body += '</div>'

    return render_template_string(layout(body, nc=nc, mc=mc))

# ─── POST INDIVIDUAL ──────────────────────────────────────────────────────────
@app.route('/post/<int:pid>')
@login_required
def ver_post(pid):
    uid = session['user_id']
    conn = get_db()
    conn.run("UPDATE posts SET vistas=vistas+1 WHERE id=$1", pid)
    rows = conn.run(f"""SELECT p.id,u.nombre,p.contenido,p.fecha,p.categoria,u.avatar_url,
        p.usuario_id,p.imagen_url,u.verificado,p.vistas,
        (SELECT COUNT(*) FROM likes WHERE post_id=p.id),
        (CASE WHEN EXISTS(SELECT 1 FROM likes WHERE post_id={pid} AND usuario_id={uid}) THEN TRUE ELSE FALSE END)
        FROM posts p JOIN usuarios u ON p.usuario_id=u.id WHERE p.id={pid}""")
    if not rows:
        conn.close(); flash("Post no encontrado.","error"); return redirect('/foro')
    p = rows[0]
    coms = conn.run("SELECT u.nombre,c.contenido,c.fecha,u.avatar_url FROM comentarios c JOIN usuarios u ON c.usuario_id=u.id WHERE c.post_id=$1 ORDER BY c.fecha", pid)
    nc = nc_for(uid); mc = mc_for(uid)
    conn.close()

    av_h = f'<img src="{p[5]}">' if p[5] and p[5].startswith('http') else p[1][0].upper()
    coms_html = ''
    for c in coms:
        cav = f'<img src="{c[3]}">' if c[3] and c[3].startswith('http') else c[0][0].upper()
        coms_html += f'<div class="ci"><div class="av avs" style="background:{color(c[0])}">{cav}</div><div class="cbub"><strong><a href="/perfil/{c[0]}" style="color:var(--txt);text-decoration:none;">{c[0]}</a> <span style="color:var(--mut);font-weight:400;">{ago(c[2])}</span></strong>{html.escape(c[1])}</div></div>'

    ver = ' <span class="ver">✓</span>' if p[8] else ''
    body = f'''<div class="card">
  <div class="ph"><a href="/perfil/{p[1]}"><div class="av avm" style="background:{color(p[1])}">{av_h}</div></a>
  <div class="pm"><div><a href="/perfil/{p[1]}" style="text-decoration:none;color:var(--txt);"><strong>{p[1]}</strong>{ver}</a></div><small>{ago(p[3])} · {p[9]} vistas</small></div></div>
  <span class="cbadge {p[4]}">{CAT.get(p[4],"🏍️")} {p[4]}</span>
  <div class="pb" style="font-size:17px;">{procesar(p[2])}</div>
  {'<img src="'+p[7]+'" class="pimg">' if p[7] else ''}
  <div class="pa"><form action="/like/{p[0]}" method="POST" style="display:inline;"><button class="ab {'on' if p[11] else ''}">⛽ {p[10]}</button></form></div>
</div>
<h3 class="disp stitle">💬 Comentarios ({len(coms)})</h3>
<div class="card" style="margin-bottom:14px;">
  <form action="/comment/{pid}" method="POST" style="display:flex;gap:8px;">
    <input type="text" name="contenido" placeholder="Añade tu comentario…" required style="margin:0;flex:1;">
    <button class="btn bp" type="submit" style="width:auto;padding:12px 18px;margin:0;">Enviar</button>
  </form>
</div>
{coms_html if coms_html else '<div class="card empty"><span class="ic">💬</span>Sé el primero en comentar</div>'}'''
    return render_template_string(layout(body, nc=nc, mc=mc))

# ─── PERFIL ───────────────────────────────────────────────────────────────────
@app.route('/perfil')
@app.route('/perfil/<username>')
@login_required
def perfil(username=None):
    target = username or session['user_name']
    uid    = session['user_id']
    conn   = get_db()
    rows = conn.run("SELECT id,nombre,bio,moto,avatar_url,banner_url,racha,verificado,ubicacion,web,fecha_registro FROM usuarios WHERE nombre=$1", target)
    if not rows:
        conn.close(); flash("Usuario no encontrado.","error"); return redirect('/foro')
    u = rows[0]
    tuid = u[0]
    posts_n  = conn.run("SELECT COUNT(*) FROM posts WHERE usuario_id=$1", tuid)[0][0]
    followers= conn.run("SELECT COUNT(*) FROM seguidores WHERE seguido_id=$1", tuid)[0][0]
    following= conn.run("SELECT COUNT(*) FROM seguidores WHERE seguidor_id=$1", tuid)[0][0]
    tlikes   = conn.run("SELECT COUNT(*) FROM likes l JOIN posts p ON l.post_id=p.id WHERE p.usuario_id=$1", tuid)[0][0]
    is_fol   = bool(conn.run("SELECT 1 FROM seguidores WHERE seguidor_id=$1 AND seguido_id=$2", uid, tuid)) if tuid != uid else False
    posts    = conn.run("SELECT id,contenido,fecha,imagen_url,categoria,(SELECT COUNT(*) FROM likes WHERE post_id=posts.id),(SELECT COUNT(*) FROM comentarios WHERE post_id=posts.id) FROM posts WHERE usuario_id=$1 ORDER BY fecha DESC LIMIT 20", tuid)
    tab = request.args.get('tab','posts')
    bmarks = []
    if tab == 'guardados' and tuid == uid:
        bmarks = conn.run("SELECT p.id,u.nombre,p.contenido,p.fecha,p.imagen_url,p.categoria FROM bookmarks b JOIN posts p ON b.post_id=p.id JOIN usuarios u ON p.usuario_id=u.id WHERE b.usuario_id=$1 ORDER BY b.fecha DESC", uid)
    nc = nc_for(uid); mc = mc_for(uid)
    conn.close()

    av_h   = f'<img src="{u[4]}">' if u[4] and u[4].startswith('http') else u[1][0].upper()
    ban_s  = f"background-image:url('{u[5]}');" if u[5] else ""
    ver    = ' <span class="ver">✓</span>' if u[7] else ''
    rb     = racha_badge(u[6])
    is_own = tuid == uid

    if is_own:
        act = '<a href="/config" class="btn bs bsm">✏️ Editar</a>'
    else:
        act = f'<form action="/seguir/{target}" method="POST" style="display:inline;"><button class="btn bf bsm {"fol" if is_fol else ""}">'
        act += ('✓ Siguiendo' if is_fol else '+ Seguir') + '</button></form>'
        act += f'<a href="/mensajes/{target}" class="btn bs bsm">✉️</a>'

    body = f'''<div class="card pcard">
  <div class="banner" style="{ban_s}"></div>
  <div class="pbody">
    <div class="prow">
      <div class="pav"><div class="av avl" style="background:{color(u[1])}">{av_h}</div></div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;padding-top:10px;">{act}</div>
    </div>
    <h1 class="disp" style="font-size:30px;">{u[1]}{ver}</h1>
    <p style="color:var(--mut);font-size:14px;">{u[3] or "Motero"}</p>
    {'<p style="margin:10px 0;font-size:15px;">'+html.escape(u[2])+'</p>' if u[2] else ''}
    <div style="display:flex;gap:14px;flex-wrap:wrap;margin-top:8px;font-size:13px;color:var(--mut);">
      {'<span>📍 '+html.escape(u[8])+'</span>' if u[8] else ''}
      {'<a href="'+html.escape(u[9])+'" target="_blank" style="color:var(--blu);">🔗 Web</a>' if u[9] else ''}
      {'<span>📅 Desde '+u[10].strftime("%b %Y")+'</span>' if u[10] else ''}
    </div>
    <div class="pstats">
      <div class="stat"><span>{posts_n}</span><small>Posts</small></div>
      <div class="stat"><span>{followers}</span><small>Seguidores</small></div>
      <div class="stat"><span>{following}</span><small>Siguiendo</small></div>
      <div class="stat"><span>{tlikes}</span><small>⛽</small></div>
      <div class="stat"><span>{rb} {u[6]}</span><small>Racha</small></div>
    </div>
  </div>
</div>
<div class="tabs">
  <a href="/perfil/{target}?tab=posts" class="tab {'on' if tab=='posts' else ''}">Posts</a>
  {'<a href="/perfil/'+target+'?tab=guardados" class="tab '+('on' if tab=='guardados' else '')+'">🔖 Guardados</a>' if is_own else ''}
</div>'''

    items = bmarks if tab == 'guardados' else posts
    if not items:
        body += f'<div class="card empty"><span class="ic">{"🔖" if tab=="guardados" else "🏍️"}</span>Sin contenido aquí.</div>'
    for p in items:
        body += f'''<div class="card">
  <span class="cbadge">{CAT.get(p[5],"🏍️")} {p[5]}</span>
  <div class="pb">{procesar(p[2])}</div>
  {'<img src="'+p[4]+'" class="pimg">' if p[4] else ''}
  <div style="display:flex;align-items:center;gap:12px;margin-top:10px;font-size:13px;color:var(--mut);">
    <span>⛽ {p[5]}</span><span>{ago(p[3])}</span>
    <a href="/post/{p[0]}" style="margin-left:auto;color:var(--mut);">Ver →</a>
  </div>
</div>'''
    return render_template_string(layout(body, active='perfil', nc=nc, mc=mc))

# ─── CONFIG ───────────────────────────────────────────────────────────────────
@app.route('/config', methods=['GET','POST'])
@login_required
def config():
    uid = session['user_id']
    if request.method == 'POST':
        bio = request.form.get('bio','')[:300]
        moto= request.form.get('moto','')[:80]
        ubi = request.form.get('ubicacion','')[:60]
        web = request.form.get('web','')[:120]
        av_url = session.get('avatar_url','')
        bn_url = session.get('banner_url','')
        av_f = request.files.get('avatar')
        bn_f = request.files.get('banner')
        if av_f and av_f.filename:
            u = upload_imgbb(av_f)
            if u: av_url=u; session['avatar_url']=u
        if bn_f and bn_f.filename:
            u = upload_imgbb(bn_f)
            if u: bn_url=u; session['banner_url']=u
        conn=get_db()
        conn.run("UPDATE usuarios SET bio=$1,moto=$2,ubicacion=$3,web=$4,avatar_url=$5,banner_url=$6 WHERE id=$7", bio,moto,ubi,web,av_url,bn_url,uid)
        conn.close()
        flash("Perfil actualizado ✓","success")
        return redirect(f'/perfil/{session["user_name"]}')

    conn=get_db()
    rows=conn.run("SELECT bio,moto,ubicacion,web FROM usuarios WHERE id=$1",uid)
    conn.close()
    u=rows[0] if rows else ('','','','')
    nc=nc_for(uid); mc=mc_for(uid)
    body=f'''<h2 class="disp stitle">✏️ Editar Perfil</h2>
<div class="card">
  <form method="POST" enctype="multipart/form-data">
    <label>Biografía (máx. 300)</label><textarea name="bio" data-max="300">{html.escape(u[0] or '')}</textarea>
    <label>Tu moto</label><input type="text" name="moto" placeholder="Honda CB650R" value="{html.escape(u[1] or '')}">
    <label>Ubicación</label><input type="text" name="ubicacion" placeholder="Madrid, España" value="{html.escape(u[2] or '')}">
    <label>Web / Instagram</label><input type="url" name="web" placeholder="https://" value="{html.escape(u[3] or '')}">
    <hr class="div"><label>📷 Foto de perfil</label><input type="file" name="avatar" accept="image/*" style="padding:10px;">
    <label>🖼️ Portada</label><input type="file" name="banner" accept="image/*" style="padding:10px;">
    <button class="btn bp" type="submit">GUARDAR</button>
  </form>
</div>
<div class="card" style="margin-top:14px;">
  <h3 class="disp" style="font-size:18px;margin-bottom:12px;">🔐 Cambiar contraseña</h3>
  <form method="POST" action="/cambiar-password">
    <label>Contraseña actual</label><input type="password" name="actual" required>
    <label>Nueva contraseña (mín. 6)</label><input type="password" name="nueva" required minlength="6">
    <button class="btn bs" type="submit" style="width:100%;">ACTUALIZAR</button>
  </form>
</div>'''
    return render_template_string(layout(body,nc=nc,mc=mc))

@app.route('/cambiar-password', methods=['POST'])
@login_required
def cambiar_pw():
    uid=session['user_id']
    actual=request.form.get('actual',''); nueva=request.form.get('nueva','')
    conn=get_db()
    rows=conn.run("SELECT password FROM usuarios WHERE id=$1",uid)
    if rows and check_password_hash(rows[0][0],actual):
        if len(nueva)>=6:
            conn.run("UPDATE usuarios SET password=$1 WHERE id=$2",generate_password_hash(nueva),uid)
            flash("Contraseña actualizada ✓","success")
        else: flash("Mínimo 6 caracteres.","error")
    else: flash("Contraseña actual incorrecta.","error")
    conn.close(); return redirect('/config')

# ─── BUSCAR ───────────────────────────────────────────────────────────────────
@app.route('/buscar')
@login_required
def buscar():
    q=request.args.get('q','').strip(); tag=request.args.get('tag','').strip()
    modo=request.args.get('modo','posts')
    uid=session['user_id']
    conn=get_db(); nc=nc_for(uid); mc=mc_for(uid)

    body=f'''<h2 class="disp stitle">🔍 Explorar</h2>
<form action="/buscar" method="GET" class="sbar">
  <input type="text" name="q" placeholder="Posts, usuarios, hashtags…" value="{html.escape(q)}" style="margin:0;">
  <button class="btn bp" type="submit" style="width:auto;margin:0;padding:12px 18px;">Buscar</button>
</form>
<div class="tabs" style="margin-bottom:16px;">
  <a href="/buscar?q={q}&modo=posts" class="tab {'on' if modo=='posts' else ''}">Posts</a>
  <a href="/buscar?q={q}&modo=usuarios" class="tab {'on' if modo=='usuarios' else ''}">Moteros</a>
</div>'''

    def mini(r):
        av=f'<img src="{r[4]}">' if r[4] and r[4].startswith('http') else r[1][0].upper()
        return f'<div class="card"><div class="ph" style="margin-bottom:8px;"><a href="/perfil/{r[1]}"><div class="av avs" style="background:{color(r[1])}">{av}</div></a><div class="pm"><a href="/perfil/{r[1]}" style="text-decoration:none;color:var(--txt);font-weight:600;">{r[1]}</a><br><small>{ago(r[3])}</small></div></div><div class="pb">{procesar(r[2])}</div>{"<img src="+chr(34)+r[5]+chr(34)+" class=pimg>" if r[5] else ""}</div>'

    if tag:
        res=conn.run("SELECT p.id,u.nombre,p.contenido,p.fecha,u.avatar_url,p.imagen_url,p.categoria FROM posts p JOIN usuarios u ON p.usuario_id=u.id WHERE p.contenido ILIKE $1 AND p.reportes<5 ORDER BY p.fecha DESC LIMIT 30", f'%#{tag}%')
        body+=f'<p class="mut" style="margin-bottom:12px;">Posts con <strong class="htag">#{tag}</strong></p>'
        for r in res: body+=mini(r)
    elif modo=='usuarios' and q:
        res=conn.run("SELECT nombre,avatar_url,bio,moto,(SELECT COUNT(*) FROM seguidores WHERE seguido_id=u.id) FROM usuarios u WHERE nombre ILIKE $1 ORDER BY 5 DESC LIMIT 20", f'%{q}%')
        for r in res:
            av=f'<img src="{r[1]}">' if r[1] and r[1].startswith('http') else r[0][0].upper()
            body+=f'<div class="card" style="display:flex;align-items:center;gap:12px;"><a href="/perfil/{r[0]}"><div class="av avm" style="background:{color(r[0])}">{av}</div></a><div style="flex:1;"><a href="/perfil/{r[0]}" style="color:var(--txt);text-decoration:none;font-weight:700;">{r[0]}</a><div style="font-size:12px;color:var(--mut);">{r[3] or "Motero"} · {r[4]} seguidores</div>{"<p style=font-size:13px;margin-top:4px;>"+html.escape(r[2][:80])+"</p>" if r[2] else ""}</div><form action="/seguir/{r[0]}" method="POST"><button class="btn bf bsm">Seguir</button></form></div>'
    elif q:
        res=conn.run("SELECT p.id,u.nombre,p.contenido,p.fecha,u.avatar_url,p.imagen_url,p.categoria FROM posts p JOIN usuarios u ON p.usuario_id=u.id WHERE (p.contenido ILIKE $1 OR u.nombre ILIKE $2) AND p.reportes<5 ORDER BY p.fecha DESC LIMIT 30", f'%{q}%',f'%{q}%')
        if not res: body+='<div class="card empty"><span class="ic">🔍</span>Sin resultados.</div>'
        for r in res: body+=mini(r)
    else:
        res=conn.run("SELECT p.id,u.nombre,p.contenido,p.fecha,u.avatar_url,p.imagen_url,p.categoria,(SELECT COUNT(*) FROM likes WHERE post_id=p.id) as lk FROM posts p JOIN usuarios u ON p.usuario_id=u.id WHERE p.reportes<5 ORDER BY lk DESC,p.fecha DESC LIMIT 20")
        body+='<p class="mut" style="margin-bottom:12px;">🔥 Posts más populares</p>'
        for r in res: body+=mini(r)

    conn.close()
    return render_template_string(layout(body,nc=nc,mc=mc))

# ─── NOTIFICACIONES ───────────────────────────────────────────────────────────
@app.route('/notificaciones')
@login_required
def notifs():
    uid=session['user_id']; conn=get_db()
    conn.run("UPDATE notificaciones SET leido=TRUE WHERE usuario_id=$1",uid)
    rows=conn.run("SELECT tipo,mensaje,url,fecha,leido FROM notificaciones WHERE usuario_id=$1 ORDER BY fecha DESC LIMIT 30",uid)
    mc=mc_for(uid); conn.close()
    icons={'like':'⛽','comentario':'💬','seguir':'👥','mencion':'@','sistema':'📢'}
    body='<h2 class="disp stitle">🔔 Notificaciones</h2>'
    if not rows:
        body+='<div class="card empty"><span class="ic">🔔</span>Sin notificaciones nuevas.</div>'
    else:
        body+='<div class="card" style="padding:0;overflow:hidden;">'
        for n in rows:
            body+=f'<a href="{n[2] or "#"}" class="ni-item {"unr" if not n[4] else ""}"><span style="font-size:20px;">{icons.get(n[0],"📢")}</span><div style="flex:1;"><div style="font-size:14px;">{html.escape(n[1])}</div><div style="font-size:11px;color:var(--mut);">{ago(n[3])}</div></div>{"<div class=ndot></div>" if not n[4] else ""}</a>'
        body+='</div>'
    return render_template_string(layout(body,nc=0,mc=mc))

# ─── MENSAJES ─────────────────────────────────────────────────────────────────
@app.route('/mensajes')
@login_required
def mensajes():
    uid=session['user_id']; conn=get_db()
    convs=conn.run("""SELECT DISTINCT ON (CASE WHEN remitente_id=$1 THEN destinatario_id ELSE remitente_id END)
        CASE WHEN remitente_id=$1 THEN destinatario_id ELSE remitente_id END as oid,
        u.nombre,u.avatar_url,m.contenido,m.fecha,m.leido,m.remitente_id
        FROM mensajes m JOIN usuarios u ON u.id=CASE WHEN m.remitente_id=$1 THEN m.destinatario_id ELSE m.remitente_id END
        WHERE m.remitente_id=$1 OR m.destinatario_id=$1 ORDER BY oid,m.fecha DESC""",uid,uid,uid,uid,uid)
    nc=nc_for(uid); mc=mc_for(uid); conn.close()
    body='<h2 class="disp stitle">✉️ Mensajes</h2>'
    if not convs: body+='<div class="card empty"><span class="ic">✉️</span>Sin conversaciones.</div>'
    for c in convs:
        av=f'<img src="{c[2]}">' if c[2] and c[2].startswith('http') else c[1][0].upper()
        dot='<span style="width:8px;height:8px;border-radius:50%;background:var(--blu);display:inline-block;margin-left:4px;"></span>' if not c[5] and c[6]!=uid else ''
        body+=f'<a href="/mensajes/{c[1]}" style="text-decoration:none;color:var(--txt);"><div class="card" style="display:flex;gap:12px;align-items:center;"><div class="av avm" style="background:{color(c[1])}">{av}</div><div style="flex:1;min-width:0;"><strong>{c[1]}</strong>{dot}<div style="font-size:13px;color:var(--mut);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{html.escape(c[3][:60])}</div></div><small class="mut">{ago(c[4])}</small></div></a>'
    return render_template_string(layout(body,nc=nc,mc=mc))

@app.route('/mensajes/<username>', methods=['GET','POST'])
@login_required
def chat(username):
    uid=session['user_id']; conn=get_db()
    rows=conn.run("SELECT id,nombre,avatar_url FROM usuarios WHERE nombre=$1",username)
    if not rows:
        conn.close(); flash("Usuario no encontrado.","error"); return redirect('/mensajes')
    otro=rows[0]
    if request.method=='POST':
        txt=request.form.get('contenido','').strip()
        if txt: conn.run("INSERT INTO mensajes(remitente_id,destinatario_id,contenido) VALUES($1,$2,$3)",uid,otro[0],txt[:1000])
        conn.close(); return redirect(f'/mensajes/{username}')
    conn.run("UPDATE mensajes SET leido=TRUE WHERE destinatario_id=$1 AND remitente_id=$2",uid,otro[0])
    msgs=conn.run("SELECT remitente_id,contenido,fecha FROM mensajes WHERE (remitente_id=$1 AND destinatario_id=$2) OR (remitente_id=$2 AND destinatario_id=$1) ORDER BY fecha",uid,otro[0],otro[0],uid)
    nc=nc_for(uid); mc=mc_for(uid); conn.close()
    av=f'<img src="{otro[2]}">' if otro[2] and otro[2].startswith('http') else otro[1][0].upper()
    mh='<div class="mlist" style="min-height:200px;margin-bottom:16px;">'
    for m in msgs:
        me=m[0]==uid
        mh+=f'<div style="display:flex;flex-direction:column;{"align-items:flex-end;" if me else ""}"><div class="mbub {"me" if me else "them"}">{html.escape(m[1])}</div><div class="mmt">{ago(m[2])}</div></div>'
    mh+='</div>'
    body=f'<div class="chdr"><a href="/mensajes" style="color:var(--mut);text-decoration:none;font-size:20px;">←</a><a href="/perfil/{otro[1]}"><div class="av avm" style="background:{color(otro[1])}">{av}</div></a><a href="/perfil/{otro[1]}" style="text-decoration:none;color:var(--txt);"><strong>{otro[1]}</strong></a></div><div class="card">{mh}<form method="POST" style="display:flex;gap:8px;"><input type="text" name="contenido" placeholder="Escribe un mensaje…" required style="margin:0;flex:1;" autocomplete="off"><button class="btn bp" type="submit" style="width:auto;padding:12px 16px;margin:0;">↩</button></form></div>'
    return render_template_string(layout(body,nc=nc,mc=mc))

# ─── RUTAS ────────────────────────────────────────────────────────────────────
@app.route('/rutas')
@login_required
def rutas():
    uid=session['user_id']; conn=get_db()
    rows=conn.run("SELECT r.id,u.nombre,r.titulo,r.descripcion,r.distancia,r.duracion,r.dificultad,r.imagen_url,r.fecha,r.likes FROM rutas r JOIN usuarios u ON r.usuario_id=u.id ORDER BY r.fecha DESC LIMIT 30")
    nc=nc_for(uid); mc=mc_for(uid); conn.close()
    body='<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;"><h2 class="disp stitle" style="margin:0;">🗺️ Rutas</h2><a href="/rutas/nueva" class="btn bp" style="width:auto;padding:10px 18px;">+ Nueva</a></div>'
    if not rows: body+='<div class="card empty"><span class="ic">🗺️</span>Sin rutas. ¡Añade la primera!</div>'
    dif_map={'Facil':'dif-Facil','Media':'dif-Media','Dificil':'dif-Dificil','Extrema':'dif-Extrema'}
    for r in rows:
        dc=dif_map.get(r[6].replace('á','a').replace('í','i'),'dif-Media')
        body+=f'<div class="rcard">{"<img src="+chr(34)+r[7]+chr(34)+" class=rimg loading=lazy>" if r[7] else "<div style=height:120px;background:linear-gradient(135deg,#1a1a2e,#0f3460);display:flex;align-items:center;justify-content:center;font-size:48px;>🛣️</div>"}<div class="rbody"><div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px;"><h3 class="disp" style="font-size:22px;">{html.escape(r[2])}</h3><span class="dif {dc}">{r[6]}</span></div><p style="color:var(--mut);font-size:13px;margin-bottom:10px;">{html.escape((r[3] or "")[:120])}</p><div class="rstats"><div class="rstat"><span>📏 {r[4]:.0f}km</span><small>Dist.</small></div><div class="rstat"><span>⏱ {r[5] or "—"}</span><small>Duración</small></div><div class="rstat"><span>⛽ {r[9]}</span><small>Likes</small></div></div><div style="display:flex;justify-content:space-between;align-items:center;margin-top:10px;"><a href="/perfil/{r[1]}" style="color:var(--mut);font-size:13px;">por <strong>{r[1]}</strong> · {ago(r[8])}</a><a href="/rutas/{r[0]}" class="btn bs bsm">Ver →</a></div></div></div>'
    return render_template_string(layout(body,nc=nc,mc=mc))

@app.route('/rutas/nueva', methods=['GET','POST'])
@login_required
def nueva_ruta():
    uid=session['user_id']
    if request.method=='POST':
        titulo=request.form.get('titulo','').strip()[:100]
        desc  =request.form.get('descripcion','').strip()[:500]
        dist  =float(request.form.get('distancia',0) or 0)
        dur   =request.form.get('duracion','')[:30]
        dif   =request.form.get('dificultad','Media')
        foto  =request.files.get('foto')
        img   =upload_imgbb(foto) if foto and foto.filename else ''
        if titulo:
            conn=get_db()
            conn.run("INSERT INTO rutas(usuario_id,titulo,descripcion,distancia,duracion,dificultad,imagen_url) VALUES($1,$2,$3,$4,$5,$6,$7)",uid,titulo,desc,dist,dur,dif,img)
            conn.close(); flash("¡Ruta publicada!","success"); return redirect('/rutas')
        else: flash("El título es obligatorio.","error")
    nc=nc_for(uid); mc=mc_for(uid)
    body='''<h2 class="disp stitle">🗺️ Nueva Ruta</h2><div class="card"><form method="POST" enctype="multipart/form-data">
  <label>Título *</label><input type="text" name="titulo" placeholder="Puerto de Navacerrada" required>
  <label>Descripción</label><textarea name="descripcion" placeholder="Cuéntanos la ruta…" data-max="500"></textarea>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
    <div><label>Distancia (km)</label><input type="number" name="distancia" placeholder="150" min="0" step="0.1"></div>
    <div><label>Duración</label><input type="text" name="duracion" placeholder="3h 30min"></div>
  </div>
  <label>Dificultad</label>
  <select name="dificultad"><option value="Facil">🟢 Fácil</option><option value="Media" selected>🟡 Media</option><option value="Dificil">🟠 Difícil</option><option value="Extrema">🔴 Extrema</option></select>
  <label>📷 Foto</label><input type="file" name="foto" accept="image/*" style="padding:10px;">
  <button class="btn bp" type="submit">PUBLICAR RUTA</button>
</form></div>'''
    return render_template_string(layout(body,nc=nc,mc=mc))

@app.route('/rutas/<int:rid>')
@login_required
def ver_ruta(rid):
    uid=session['user_id']; conn=get_db()
    rows=conn.run("SELECT r.id,u.nombre,r.titulo,r.descripcion,r.distancia,r.duracion,r.dificultad,r.imagen_url,r.fecha,r.likes,r.usuario_id FROM rutas r JOIN usuarios u ON r.usuario_id=u.id WHERE r.id=$1",rid)
    if not rows:
        conn.close(); flash("Ruta no encontrada.","error"); return redirect('/rutas')
    r=rows[0]; nc=nc_for(uid); mc=mc_for(uid); conn.close()
    dif_map={'Facil':'dif-Facil','Media':'dif-Media','Dificil':'dif-Dificil','Extrema':'dif-Extrema'}
    dc=dif_map.get(r[6].replace('á','a').replace('í','i'),'dif-Media')
    body=f'<div class="rcard">{"<img src="+chr(34)+r[7]+chr(34)+" class=rimg>" if r[7] else ""}<div class="rbody"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;"><h1 class="disp" style="font-size:28px;">{html.escape(r[2])}</h1><span class="dif {dc}">{r[6]}</span></div><p style="color:var(--mut);font-size:14px;margin-bottom:16px;">por <a href="/perfil/{r[1]}" style="color:var(--acc);">{r[1]}</a> · {ago(r[8])}</p><p style="font-size:15px;line-height:1.7;margin-bottom:16px;">{html.escape(r[3] or "")}</p><div class="rstats"><div class="rstat"><span>📏 {r[4]:.0f}km</span><small>Distancia</small></div><div class="rstat"><span>⏱ {r[5] or "—"}</span><small>Duración</small></div><div class="rstat"><span>⛽ {r[9]}</span><small>Likes</small></div></div><div style="margin-top:14px;display:flex;gap:8px;"><form action="/rutas/{rid}/like" method="POST"><button class="btn bp" style="width:auto;padding:10px 18px;">⛽ Me gusta</button></form>{"<form action=/rutas/"+str(rid)+"/delete method=POST onsubmit=return confirm(chr(39)+Eliminar?+chr(39))><button class=btn bs>🗑️</button></form>" if r[10]==uid else ""}</div></div></div>'
    return render_template_string(layout(body,nc=nc,mc=mc))

@app.route('/rutas/<int:rid>/like', methods=['POST'])
@login_required
def like_ruta(rid):
    conn=get_db(); conn.run("UPDATE rutas SET likes=likes+1 WHERE id=$1",rid); conn.close()
    return redirect(f'/rutas/{rid}')

@app.route('/rutas/<int:rid>/delete', methods=['POST'])
@login_required
def del_ruta(rid):
    conn=get_db(); conn.run("DELETE FROM rutas WHERE id=$1 AND usuario_id=$2",rid,session['user_id']); conn.close()
    flash("Ruta eliminada.","success"); return redirect('/rutas')

# ─── ACCIONES ─────────────────────────────────────────────────────────────────
@app.route('/post', methods=['POST'])
@login_required
def new_post():
    uid=session['user_id']
    cont=request.form.get('contenido','').strip()[:500]
    cat =request.form.get('categoria','General')
    foto=request.files.get('foto')
    img =upload_imgbb(foto) if foto and foto.filename else ''
    if cont or img:
        conn=get_db()
        conn.run("INSERT INTO posts(usuario_id,contenido,categoria,imagen_url) VALUES($1,$2,$3,$4)",uid,cont,cat,img)
        rows=conn.run("SELECT ultima_actividad FROM usuarios WHERE id=$1",uid)
        last=rows[0][0] if rows else None
        today=datetime.now().date()
        if last==today-timedelta(days=1): conn.run("UPDATE usuarios SET racha=racha+1,ultima_actividad=$1 WHERE id=$2",today,uid)
        elif last!=today: conn.run("UPDATE usuarios SET racha=1,ultima_actividad=$1 WHERE id=$2",today,uid)
        conn.close()
        for m in re.findall(r'@(\w+)',cont):
            c2=get_db(); rows2=c2.run("SELECT id FROM usuarios WHERE nombre=$1",m)
            if rows2 and rows2[0][0]!=uid: notif(rows2[0][0],'mencion',f"{session['user_name']} te mencionó",'/foro')
            c2.close()
        flash("¡Publicado! 🏍️","success")
    return redirect('/foro')

@app.route('/like/<int:pid>', methods=['POST'])
@login_required
def like(pid):
    uid=session['user_id']; conn=get_db()
    ex=conn.run("SELECT 1 FROM likes WHERE usuario_id=$1 AND post_id=$2",uid,pid)
    if ex:
        conn.run("DELETE FROM likes WHERE usuario_id=$1 AND post_id=$2",uid,pid)
    else:
        conn.run("INSERT INTO likes(usuario_id,post_id) VALUES($1,$2)",uid,pid)
        rows=conn.run("SELECT usuario_id FROM posts WHERE id=$1",pid)
        if rows and rows[0][0]!=uid: notif(rows[0][0],'like',f"A {session['user_name']} le gustó tu post ⛽",f"/post/{pid}")
    conn.close(); return redirect(request.referrer or '/foro')

@app.route('/bookmark/<int:pid>', methods=['POST'])
@login_required
def bookmark(pid):
    uid=session['user_id']; conn=get_db()
    ex=conn.run("SELECT 1 FROM bookmarks WHERE usuario_id=$1 AND post_id=$2",uid,pid)
    if ex: conn.run("DELETE FROM bookmarks WHERE usuario_id=$1 AND post_id=$2",uid,pid)
    else: conn.run("INSERT INTO bookmarks(usuario_id,post_id) VALUES($1,$2)",uid,pid)
    conn.close(); return redirect(request.referrer or '/foro')

@app.route('/seguir/<seguido>', methods=['POST'])
@login_required
def seguir(seguido):
    uid=session['user_id']; conn=get_db()
    if seguido.isdigit(): rows=conn.run("SELECT id,nombre FROM usuarios WHERE id=$1",int(seguido))
    else: rows=conn.run("SELECT id,nombre FROM usuarios WHERE nombre=$1",seguido)
    if not rows: conn.close(); return redirect(request.referrer or '/foro')
    tuid,tname=rows[0]
    ex=conn.run("SELECT 1 FROM seguidores WHERE seguidor_id=$1 AND seguido_id=$2",uid,tuid)
    if ex: conn.run("DELETE FROM seguidores WHERE seguidor_id=$1 AND seguido_id=$2",uid,tuid)
    else:
        conn.run("INSERT INTO seguidores(seguidor_id,seguido_id) VALUES($1,$2)",uid,tuid)
        notif(tuid,'seguir',f"{session['user_name']} empezó a seguirte",f"/perfil/{session['user_name']}")
    conn.close(); return redirect(request.referrer or '/foro')

@app.route('/comment/<int:pid>', methods=['POST'])
@login_required
def comment(pid):
    uid=session['user_id']; txt=request.form.get('contenido','').strip()[:500]
    if txt:
        conn=get_db()
        conn.run("INSERT INTO comentarios(post_id,usuario_id,contenido) VALUES($1,$2,$3)",pid,uid,txt)
        rows=conn.run("SELECT usuario_id FROM posts WHERE id=$1",pid)
        if rows and rows[0][0]!=uid: notif(rows[0][0],'comentario',f"{session['user_name']} comentó tu post",f"/post/{pid}")
        conn.close()
    return redirect(request.referrer or f'/post/{pid}')

@app.route('/delete/<int:pid>', methods=['POST'])
@login_required
def delete(pid):
    conn=get_db(); conn.run("DELETE FROM posts WHERE id=$1 AND usuario_id=$2",pid,session['user_id']); conn.close()
    flash("Post eliminado.","success"); return redirect(request.referrer or '/foro')

@app.route('/report/<int:pid>', methods=['POST'])
@login_required
def report(pid):
    conn=get_db(); conn.run("UPDATE posts SET reportes=reportes+1 WHERE id=$1",pid); conn.close()
    flash("Reportado. Gracias.","success"); return redirect(request.referrer or '/foro')

# ─── ADMIN ────────────────────────────────────────────────────────────────────
@app.route('/admin')
@login_required
@admin_required
def admin():
    uid=session['user_id']; conn=get_db()
    tu=conn.run("SELECT COUNT(*) FROM usuarios")[0][0]
    tp=conn.run("SELECT COUNT(*) FROM posts")[0][0]
    tf=conn.run("SELECT COUNT(*) FROM posts WHERE reportes>=5")[0][0]
    rep=conn.run("SELECT id,nombre,contenido,reportes FROM posts WHERE reportes>=3 ORDER BY reportes DESC LIMIT 20")
    users=conn.run("SELECT id,nombre,rol,fecha_registro FROM usuarios ORDER BY fecha_registro DESC LIMIT 20")
    nc=nc_for(uid); conn.close()
    body=f'<h2 class="disp stitle">🔧 Admin</h2><div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:20px;"><div class="card ct" style="text-align:center;"><div style="font-size:32px;font-weight:700;">{tu}</div><div class="mut">Usuarios</div></div><div class="card ct" style="text-align:center;"><div style="font-size:32px;font-weight:700;">{tp}</div><div class="mut">Posts</div></div><div class="card ct" style="text-align:center;"><div style="font-size:32px;font-weight:700;color:var(--acc);">{tf}</div><div class="mut">Reportados</div></div></div><h3 class="disp" style="font-size:18px;margin-bottom:10px;">⚠️ Posts reportados</h3>'
    for r in rep:
        body+=f'<div class="card" style="border-color:rgba(255,69,0,.3);"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;"><span class="mut">#{r[0]} · {r[3]} reportes</span><form action="/admin/del/{r[0]}" method="POST" onsubmit="return confirm(\'¿Eliminar?\')"><button class="btn bs bsm" style="color:var(--acc);">🗑️</button></form></div><p style="font-size:13px;">{html.escape(r[2][:150])}</p></div>'
    body+='<h3 class="disp" style="font-size:18px;margin:20px 0 10px;">👥 Usuarios</h3>'
    for u in users:
        body+=f'<div class="card ct" style="display:flex;align-items:center;gap:10px;"><a href="/perfil/{u[1]}" style="flex:1;text-decoration:none;color:var(--txt);"><strong>{u[1]}</strong><span class="pill" style="margin-left:6px;">{u[2]}</span></a><form action="/admin/ver/{u[0]}" method="POST"><button class="btn bs bsm">✓</button></form></div>'
    return render_template_string(layout(body,nc=nc))

@app.route('/admin/del/<int:pid>', methods=['POST'])
@login_required
@admin_required
def admin_del(pid):
    conn=get_db(); conn.run("DELETE FROM posts WHERE id=$1",pid); conn.close()
    flash("Post eliminado.","success"); return redirect('/admin')

@app.route('/admin/ver/<int:uid>', methods=['POST'])
@login_required
@admin_required
def admin_ver(uid):
    conn=get_db(); conn.run("UPDATE usuarios SET verificado=NOT verificado WHERE id=$1",uid); conn.close()
    return redirect('/admin')

@app.route('/health')
def health():
    return jsonify({'status':'ok','version':'2.0'})

# ─── ENTRY ────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    if DATABASE_URL:
        try: init_db()
        except Exception as e: print(f"init_db: {e}")
    port=int(os.environ.get('PORT',5000))
    app.run(host='0.0.0.0', port=port, debug=False)

# Para gunicorn (Render.com lo llama así):
if DATABASE_URL and __name__ != '__main__':
    try: init_db()
    except Exception as e: print(f"init_db: {e}")
