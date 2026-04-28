-- =============================================================================
-- MOTOSCLUB v2.0 — Schema completo
-- =============================================================================

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

CREATE TABLE IF NOT EXISTS seguidores (
    seguidor_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
    seguido_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (seguidor_id, seguido_id)
);

CREATE TABLE IF NOT EXISTS likes (
    usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
    post_id INTEGER REFERENCES posts(id) ON DELETE CASCADE,
    PRIMARY KEY (usuario_id, post_id)
);

CREATE TABLE IF NOT EXISTS comentarios (
    id SERIAL PRIMARY KEY,
    post_id INTEGER REFERENCES posts(id) ON DELETE CASCADE,
    usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
    contenido TEXT NOT NULL,
    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS notificaciones (
    id SERIAL PRIMARY KEY,
    usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
    tipo TEXT,
    mensaje TEXT,
    url TEXT,
    leido BOOLEAN DEFAULT FALSE,
    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bookmarks (
    usuario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
    post_id INTEGER REFERENCES posts(id) ON DELETE CASCADE,
    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (usuario_id, post_id)
);

CREATE TABLE IF NOT EXISTS mensajes (
    id SERIAL PRIMARY KEY,
    remitente_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
    destinatario_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
    contenido TEXT NOT NULL,
    leido BOOLEAN DEFAULT FALSE,
    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

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

-- Índices de rendimiento
CREATE INDEX IF NOT EXISTS idx_posts_usuario   ON posts(usuario_id);
CREATE INDEX IF NOT EXISTS idx_posts_fecha     ON posts(fecha DESC);
CREATE INDEX IF NOT EXISTS idx_likes_post      ON likes(post_id);
CREATE INDEX IF NOT EXISTS idx_coms_post       ON comentarios(post_id);
CREATE INDEX IF NOT EXISTS idx_notifs_usuario  ON notificaciones(usuario_id, leido);
CREATE INDEX IF NOT EXISTS idx_msgs_dest       ON mensajes(destinatario_id, leido);
CREATE INDEX IF NOT EXISTS idx_seguidores      ON seguidores(seguidor_id);
