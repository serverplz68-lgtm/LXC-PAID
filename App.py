#!/usr/bin/env python3
"""
VantixNodes - All-in-one hosting platform
Single file: app.py | Database: VantixNodes.db
"""

import sqlite3, hashlib, json, os, secrets, base64, re
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify, session, redirect, url_for, make_response
from flask_cors import CORS

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
CORS(app)

DB_PATH = "VantixNodes.db"

# ─────────────────────────────────────────────
# DATABASE SETUP
# ─────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.executescript("""
    CREATE TABLE IF NOT EXISTS settings (
        key   TEXT PRIMARY KEY,
        value TEXT
    );

    CREATE TABLE IF NOT EXISTS admins (
        id       INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        created  TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS categories (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT NOT NULL,
        slug        TEXT UNIQUE NOT NULL,
        icon        TEXT DEFAULT '🖥️',
        description TEXT,
        sort_order  INTEGER DEFAULT 0,
        visible     INTEGER DEFAULT 1,
        created     TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS plans (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        category_id  INTEGER REFERENCES categories(id) ON DELETE CASCADE,
        name         TEXT NOT NULL,
        price        REAL NOT NULL,
        billing      TEXT DEFAULT 'monthly',
        currency     TEXT DEFAULT 'USD',
        featured     INTEGER DEFAULT 0,
        badge        TEXT,
        discord_url  TEXT,
        specs        TEXT DEFAULT '{}',
        features     TEXT DEFAULT '[]',
        visible      INTEGER DEFAULT 1,
        sort_order   INTEGER DEFAULT 0,
        created      TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS sessions (
        token      TEXT PRIMARY KEY,
        admin_id   INTEGER,
        expires    TEXT,
        created    TEXT DEFAULT (datetime('now'))
    );
    """)

    # Default settings
    defaults = {
        "site_name":    "VantixNodes",
        "site_icon":    "⚡",
        "site_logo":    "",
        "theme":        "dark",
        "accent_color": "#7c3aed",
        "discord_url":  "https://discord.gg/vantixnodes",
        "nav_links":    json.dumps([
            {"label": "Home",     "href": "#home"},
            {"label": "Services", "href": "#services"},
            {"label": "Pricing",  "href": "#pricing"},
            {"label": "Discord",  "href": "#discord"}
        ]),
        "hero_title":    "Next-Gen Game & VPS Hosting",
        "hero_subtitle": "Blazing fast servers for Minecraft, VPS, Bots & Web hosting. Zero lag, 99.9% uptime, instant setup.",
        "footer_text":   "© 2025 VantixNodes. All rights reserved.",
        "maintenance":   "0"
    }
    for k, v in defaults.items():
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

    # Default admin
    pw = hashlib.sha256("admin123".encode()).hexdigest()
    c.execute("INSERT OR IGNORE INTO admins (username, password) VALUES (?, ?)", ("admin", pw))

    # Default categories
    cats = [
        ("Minecraft Hosting", "minecraft", "⛏️", "High-performance Minecraft servers with instant setup", 1),
        ("VPS Hosting",       "vps",       "🖥️", "Powerful virtual private servers for any workload",    2),
        ("Bot Hosting",       "bots",      "🤖", "24/7 Discord and Telegram bot hosting",                3),
        ("Web Hosting",       "web",       "🌐", "Fast and reliable web hosting solutions",              4),
    ]
    for name, slug, icon, desc, order in cats:
        c.execute("INSERT OR IGNORE INTO categories (name,slug,icon,description,sort_order) VALUES (?,?,?,?,?)",
                  (name, slug, icon, desc, order))

    # Default plans
    mc_plans = [
        ("Creeper",  2.99,  '{"ram":"2GB","cpu":"2 vCores","storage":"15GB","players":"20","location":"US/EU"}',
         '["DDoS Protection","Instant Setup","Daily Backups","Multicraft Panel","Plugin Support"]', 0, None),
        ("Skeleton",  5.99, '{"ram":"4GB","cpu":"3 vCores","storage":"30GB","players":"50","location":"US/EU"}',
         '["DDoS Protection","Instant Setup","Daily Backups","Multicraft Panel","Plugin Support","Priority Support"]', 1, "Popular"),
        ("Wither",   11.99, '{"ram":"8GB","cpu":"4 vCores","storage":"60GB","players":"100","location":"US/EU/AS"}',
         '["DDoS Protection","Instant Setup","Daily Backups","Multicraft Panel","Plugin Support","Priority Support","Custom Domain"]', 0, "Best Value"),
    ]
    vps_plans = [
        ("Nano",   3.99,  '{"ram":"1GB","cpu":"1 vCore","storage":"20GB SSD","bandwidth":"1TB","os":"Linux/Windows"}',
         '["Full Root Access","KVM Virtualization","DDoS Protection","IPv4 + IPv6","99.9% Uptime"]', 0, None),
        ("Micro",  7.99,  '{"ram":"2GB","cpu":"2 vCores","storage":"40GB SSD","bandwidth":"2TB","os":"Linux/Windows"}',
         '["Full Root Access","KVM Virtualization","DDoS Protection","IPv4 + IPv6","99.9% Uptime","Snapshot Backups"]', 1, "Popular"),
        ("Power",  14.99, '{"ram":"4GB","cpu":"4 vCores","storage":"80GB SSD","bandwidth":"4TB","os":"Linux/Windows"}',
         '["Full Root Access","KVM Virtualization","DDoS Protection","IPv4 + IPv6","99.9% Uptime","Snapshot Backups","Priority Network"]', 0, "Best Value"),
    ]
    bot_plans = [
        ("Starter", 1.49, '{"ram":"512MB","cpu":"0.5 vCore","bots":"1","storage":"5GB","uptime":"99.9%"}',
         '["24/7 Online","Auto Restart","Discord.js Support","Python Support","Web Dashboard"]', 0, None),
        ("Pro",     2.99, '{"ram":"1GB","cpu":"1 vCore","bots":"3","storage":"10GB","uptime":"99.9%"}',
         '["24/7 Online","Auto Restart","Discord.js Support","Python Support","Web Dashboard","Priority Support"]', 1, "Popular"),
        ("Ultra",   5.99, '{"ram":"2GB","cpu":"2 vCores","bots":"10","storage":"20GB","uptime":"99.99%"}',
         '["24/7 Online","Auto Restart","All Languages","Web Dashboard","Priority Support","Custom Domain","Dedicated IP"]', 0, None),
    ]
    web_plans = [
        ("Basic",    1.99, '{"storage":"10GB","bandwidth":"100GB","domains":"1","emails":"5","ssl":"Free"}',
         '["Free SSL","cPanel Access","1-Click WordPress","Daily Backups","99.9% Uptime"]', 0, None),
        ("Business", 4.99, '{"storage":"50GB","bandwidth":"500GB","domains":"5","emails":"50","ssl":"Free"}',
         '["Free SSL","cPanel Access","1-Click WordPress","Daily Backups","99.9% Uptime","Priority Support","CDN"]', 1, "Popular"),
        ("Agency",   9.99, '{"storage":"200GB","bandwidth":"Unlimited","domains":"Unlimited","emails":"Unlimited","ssl":"Free"}',
         '["Free SSL","cPanel Access","1-Click WordPress","Daily Backups","99.9% Uptime","Priority Support","CDN","Dedicated IP"]', 0, "Best Value"),
    ]

    conn.commit()

    for row in c.execute("SELECT id, slug FROM categories").fetchall():
        cid, slug = row[0], row[1]
        if slug == "minecraft": plist = mc_plans
        elif slug == "vps":     plist = vps_plans
        elif slug == "bots":    plist = bot_plans
        elif slug == "web":     plist = web_plans
        else: continue
        for i, p in enumerate(plist):
            name, price, specs, feats, featured, badge = p
            c.execute("""INSERT OR IGNORE INTO plans
                (category_id,name,price,specs,features,featured,badge,sort_order)
                VALUES (?,?,?,?,?,?,?,?)
                """, (cid, name, price, specs, feats, featured, badge, i))
    conn.commit()
    conn.close()

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def get_setting(key, default=""):
    conn = get_db()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row[0] if row else default

def all_settings():
    conn = get_db()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    return {r[0]: r[1] for r in rows}

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.cookies.get("vantix_token") or request.headers.get("X-Admin-Token")
        if not token:
            return jsonify({"error": "Unauthorized"}), 401
        conn = get_db()
        row = conn.execute(
            "SELECT admin_id FROM sessions WHERE token=? AND expires > datetime('now')", (token,)
        ).fetchone()
        conn.close()
        if not row:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated

def slug_from(name):
    return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')

# ─────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────
@app.route("/api/public/settings")
def pub_settings():
    s = all_settings()
    # Only expose safe settings
    safe = ["site_name","site_icon","site_logo","theme","accent_color","discord_url",
            "nav_links","hero_title","hero_subtitle","footer_text","maintenance"]
    return jsonify({k: s.get(k,"") for k in safe})

@app.route("/api/public/categories")
def pub_categories():
    conn = get_db()
    rows = conn.execute("SELECT * FROM categories WHERE visible=1 ORDER BY sort_order").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/public/plans")
def pub_plans():
    cat = request.args.get("category", "")
    conn = get_db()
    if cat:
        rows = conn.execute("""
            SELECT p.*, c.name as category_name, c.slug as category_slug, c.icon as category_icon
            FROM plans p JOIN categories c ON p.category_id=c.id
            WHERE p.visible=1 AND c.slug=? ORDER BY p.sort_order
        """, (cat,)).fetchall()
    else:
        rows = conn.execute("""
            SELECT p.*, c.name as category_name, c.slug as category_slug, c.icon as category_icon
            FROM plans p JOIN categories c ON p.category_id=c.id
            WHERE p.visible=1 ORDER BY c.sort_order, p.sort_order
        """).fetchall()
    conn.close()
    plans = []
    for r in rows:
        d = dict(r)
        d["specs"]    = json.loads(d.get("specs","{}") or "{}")
        d["features"] = json.loads(d.get("features","[]") or "[]")
        plans.append(d)
    return jsonify(plans)

# ─────────────────────────────────────────────
# ADMIN AUTH
# ─────────────────────────────────────────────
@app.route("/api/admin/login", methods=["POST"])
def admin_login():
    data = request.get_json()
    username = data.get("username","").strip()
    password = data.get("password","")
    pw_hash  = hashlib.sha256(password.encode()).hexdigest()
    conn = get_db()
    admin = conn.execute("SELECT * FROM admins WHERE username=? AND password=?", (username, pw_hash)).fetchone()
    if not admin:
        conn.close()
        return jsonify({"error": "Invalid credentials"}), 401
    token   = secrets.token_hex(32)
    expires = (datetime.utcnow() + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("INSERT INTO sessions (token, admin_id, expires) VALUES (?,?,?)", (token, admin["id"], expires))
    conn.commit()
    conn.close()
    resp = make_response(jsonify({"success": True, "token": token}))
    resp.set_cookie("vantix_token", token, httponly=True, max_age=86400, samesite="Lax")
    return resp

@app.route("/api/admin/logout", methods=["POST"])
def admin_logout():
    token = request.cookies.get("vantix_token")
    if token:
        conn = get_db()
        conn.execute("DELETE FROM sessions WHERE token=?", (token,))
        conn.commit()
        conn.close()
    resp = make_response(jsonify({"success": True}))
    resp.delete_cookie("vantix_token")
    return resp

@app.route("/api/admin/verify")
@admin_required
def admin_verify():
    return jsonify({"authenticated": True})

# ─────────────────────────────────────────────
# ADMIN SETTINGS
# ─────────────────────────────────────────────
@app.route("/api/admin/settings", methods=["GET"])
@admin_required
def get_settings():
    return jsonify(all_settings())

@app.route("/api/admin/settings", methods=["POST"])
@admin_required
def save_settings():
    data = request.get_json()
    conn = get_db()
    for k, v in data.items():
        if isinstance(v, (dict, list)):
            v = json.dumps(v)
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (k, str(v)))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

# ─────────────────────────────────────────────
# ADMIN CATEGORIES
# ─────────────────────────────────────────────
@app.route("/api/admin/categories", methods=["GET"])
@admin_required
def admin_categories():
    conn = get_db()
    rows = conn.execute("SELECT * FROM categories ORDER BY sort_order").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/admin/categories", methods=["POST"])
@admin_required
def create_category():
    data = request.get_json()
    name = data.get("name","").strip()
    if not name:
        return jsonify({"error": "Name required"}), 400
    slug = slug_from(name)
    conn = get_db()
    try:
        conn.execute("INSERT INTO categories (name,slug,icon,description,sort_order) VALUES (?,?,?,?,?)",
                     (name, slug, data.get("icon","🖥️"), data.get("description",""),
                      int(data.get("sort_order", 99))))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "Category slug already exists"}), 400
    conn.close()
    return jsonify({"success": True})

@app.route("/api/admin/categories/<int:cid>", methods=["PUT"])
@admin_required
def update_category(cid):
    data = request.get_json()
    conn = get_db()
    conn.execute("""UPDATE categories SET name=?,icon=?,description=?,sort_order=?,visible=?
                    WHERE id=?""",
                 (data.get("name"), data.get("icon","🖥️"), data.get("description",""),
                  int(data.get("sort_order",0)), int(data.get("visible",1)), cid))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route("/api/admin/categories/<int:cid>", methods=["DELETE"])
@admin_required
def delete_category(cid):
    conn = get_db()
    conn.execute("DELETE FROM categories WHERE id=?", (cid,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

# ─────────────────────────────────────────────
# ADMIN PLANS
# ─────────────────────────────────────────────
@app.route("/api/admin/plans", methods=["GET"])
@admin_required
def admin_plans():
    conn = get_db()
    rows = conn.execute("""
        SELECT p.*, c.name as category_name FROM plans p
        LEFT JOIN categories c ON p.category_id=c.id
        ORDER BY c.sort_order, p.sort_order
    """).fetchall()
    conn.close()
    plans = []
    for r in rows:
        d = dict(r)
        d["specs"]    = json.loads(d.get("specs","{}") or "{}")
        d["features"] = json.loads(d.get("features","[]") or "[]")
        plans.append(d)
    return jsonify(plans)

@app.route("/api/admin/plans", methods=["POST"])
@admin_required
def create_plan():
    data = request.get_json()
    specs    = json.dumps(data.get("specs", {}))
    features = json.dumps(data.get("features", []))
    conn = get_db()
    conn.execute("""INSERT INTO plans
        (category_id,name,price,billing,currency,featured,badge,discord_url,specs,features,visible,sort_order)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (data.get("category_id"), data.get("name"), float(data.get("price",0)),
         data.get("billing","monthly"), data.get("currency","USD"),
         int(data.get("featured",0)), data.get("badge"),
         data.get("discord_url"), specs, features,
         int(data.get("visible",1)), int(data.get("sort_order",99))))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route("/api/admin/plans/<int:pid>", methods=["PUT"])
@admin_required
def update_plan(pid):
    data = request.get_json()
    specs    = json.dumps(data.get("specs", {}))
    features = json.dumps(data.get("features", []))
    conn = get_db()
    conn.execute("""UPDATE plans SET category_id=?,name=?,price=?,billing=?,currency=?,
                    featured=?,badge=?,discord_url=?,specs=?,features=?,visible=?,sort_order=?
                    WHERE id=?""",
        (data.get("category_id"), data.get("name"), float(data.get("price",0)),
         data.get("billing","monthly"), data.get("currency","USD"),
         int(data.get("featured",0)), data.get("badge"),
         data.get("discord_url"), specs, features,
         int(data.get("visible",1)), int(data.get("sort_order",0)), pid))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route("/api/admin/plans/<int:pid>", methods=["DELETE"])
@admin_required
def delete_plan(pid):
    conn = get_db()
    conn.execute("DELETE FROM plans WHERE id=?", (pid,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

# ─────────────────────────────────────────────
# ADMIN PASSWORD CHANGE
# ─────────────────────────────────────────────
@app.route("/api/admin/change-password", methods=["POST"])
@admin_required
def change_password():
    data   = request.get_json()
    token  = request.cookies.get("vantix_token")
    conn   = get_db()
    row    = conn.execute("SELECT admin_id FROM sessions WHERE token=?", (token,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"error":"Session error"}), 401
    admin  = conn.execute("SELECT * FROM admins WHERE id=?", (row[0],)).fetchone()
    old_pw = hashlib.sha256(data.get("old_password","").encode()).hexdigest()
    if admin["password"] != old_pw:
        conn.close()
        return jsonify({"error":"Current password is wrong"}), 400
    new_pw = hashlib.sha256(data.get("new_password","").encode()).hexdigest()
    conn.execute("UPDATE admins SET password=? WHERE id=?", (new_pw, admin["id"]))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

# ─────────────────────────────────────────────
# DISCORD REDIRECT
# ─────────────────────────────────────────────
@app.route("/discord")
def discord_redirect():
    url = get_setting("discord_url", "https://discord.gg")
    return redirect(url)

# ─────────────────────────────────────────────
# MAIN HTML (entire frontend SPA)
# ─────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>VantixNodes</title>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet"/>
<style>
:root{
  --accent:#7c3aed;
  --accent2:#a855f7;
  --accent3:#6d28d9;
  --bg:#060612;
  --bg2:#0d0d1f;
  --bg3:#12122a;
  --surface:#1a1a35;
  --surface2:#222245;
  --border:#2a2a50;
  --text:#e8e8ff;
  --text2:#9898cc;
  --text3:#6666aa;
  --green:#22c55e;
  --red:#ef4444;
  --yellow:#f59e0b;
  --radius:12px;
  --radius-lg:20px;
  --font:'Inter',sans-serif;
  --mono:'JetBrains Mono',monospace;
}
[data-theme="light"]{
  --bg:#f0f0ff;
  --bg2:#e8e8f8;
  --bg3:#ddddf0;
  --surface:#ffffff;
  --surface2:#f8f8ff;
  --border:#c8c8e8;
  --text:#1a1a3a;
  --text2:#4a4a7a;
  --text3:#8888aa;
}
*{margin:0;padding:0;box-sizing:border-box}
html{scroll-behavior:smooth}
body{font-family:var(--font);background:var(--bg);color:var(--text);line-height:1.6;overflow-x:hidden}
a{text-decoration:none;color:inherit}
button{cursor:pointer;font-family:var(--font)}
input,select,textarea{font-family:var(--font)}

/* ── SCROLLBAR ── */
::-webkit-scrollbar{width:6px}
::-webkit-scrollbar-track{background:var(--bg2)}
::-webkit-scrollbar-thumb{background:var(--accent);border-radius:3px}

/* ── NAVBAR ── */
#navbar{
  position:fixed;top:0;left:0;right:0;z-index:1000;
  background:rgba(6,6,18,.85);backdrop-filter:blur(20px);
  border-bottom:1px solid var(--border);
  padding:0 1.5rem;height:64px;
  display:flex;align-items:center;justify-content:space-between;
  transition:background .3s;
}
.nav-brand{display:flex;align-items:center;gap:.6rem;font-size:1.2rem;font-weight:800;letter-spacing:-.02em}
.nav-brand span.icon{font-size:1.4rem}
.nav-links{display:flex;align-items:center;gap:.25rem}
.nav-links a,.nav-links button{
  padding:.45rem .9rem;border-radius:8px;font-size:.9rem;font-weight:500;
  color:var(--text2);transition:all .2s;background:none;border:none;
}
.nav-links a:hover,.nav-links button:hover{color:var(--text);background:var(--surface)}
.nav-cta{
  background:var(--accent)!important;color:#fff!important;
  padding:.45rem 1.1rem!important;
}
.nav-cta:hover{background:var(--accent2)!important;transform:translateY(-1px)}
.hamburger{display:none;flex-direction:column;gap:5px;background:none;border:none;padding:.4rem}
.hamburger span{display:block;width:22px;height:2px;background:var(--text);border-radius:2px;transition:.3s}
.mobile-nav{
  display:none;position:fixed;top:64px;left:0;right:0;z-index:999;
  background:var(--bg2);border-bottom:1px solid var(--border);
  flex-direction:column;padding:1rem 1.5rem;gap:.25rem;
}
.mobile-nav.open{display:flex}
.mobile-nav a,.mobile-nav button{
  padding:.7rem 1rem;border-radius:8px;color:var(--text2);
  font-size:.95rem;font-weight:500;background:none;border:none;text-align:left;
}
.mobile-nav a:hover,.mobile-nav button:hover{background:var(--surface);color:var(--text)}

/* ── HERO ── */
#home{
  min-height:100vh;display:flex;align-items:center;justify-content:center;
  position:relative;overflow:hidden;padding:6rem 1.5rem 4rem;text-align:center;
}
.hero-bg{
  position:absolute;inset:0;pointer-events:none;
  background:radial-gradient(ellipse 80% 60% at 50% 20%, rgba(124,58,237,.18) 0%, transparent 70%);
}
.hero-grid{
  position:absolute;inset:0;pointer-events:none;opacity:.07;
  background-image:linear-gradient(var(--border) 1px,transparent 1px),
                   linear-gradient(90deg,var(--border) 1px,transparent 1px);
  background-size:40px 40px;
}
.hero-orb{
  position:absolute;border-radius:50%;filter:blur(80px);pointer-events:none;
}
.orb1{width:400px;height:400px;background:rgba(124,58,237,.2);top:-100px;left:-100px;animation:float 8s ease-in-out infinite}
.orb2{width:300px;height:300px;background:rgba(168,85,247,.15);bottom:-50px;right:-50px;animation:float 10s ease-in-out infinite reverse}
@keyframes float{0%,100%{transform:translateY(0) scale(1)}50%{transform:translateY(-30px) scale(1.05)}}

.hero-content{position:relative;max-width:780px;margin:0 auto}
.hero-badge{
  display:inline-flex;align-items:center;gap:.5rem;
  background:rgba(124,58,237,.15);border:1px solid rgba(124,58,237,.3);
  color:var(--accent2);padding:.35rem 1rem;border-radius:50px;font-size:.8rem;font-weight:600;
  margin-bottom:1.5rem;letter-spacing:.05em;text-transform:uppercase;
}
.hero-title{
  font-size:clamp(2.2rem,6vw,4.2rem);font-weight:900;line-height:1.1;
  letter-spacing:-.03em;margin-bottom:1.2rem;
}
.hero-title .gradient{
  background:linear-gradient(135deg,#a855f7,#7c3aed,#6d28d9);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;
}
.hero-sub{font-size:1.1rem;color:var(--text2);max-width:560px;margin:0 auto 2rem}
.hero-btns{display:flex;gap:1rem;justify-content:center;flex-wrap:wrap}
.btn-primary{
  background:linear-gradient(135deg,var(--accent),var(--accent3));
  color:#fff;padding:.75rem 1.8rem;border-radius:50px;font-weight:700;font-size:1rem;
  border:none;transition:all .25s;box-shadow:0 0 30px rgba(124,58,237,.3);
}
.btn-primary:hover{transform:translateY(-2px);box-shadow:0 0 50px rgba(124,58,237,.5)}
.btn-secondary{
  background:var(--surface);color:var(--text);
  padding:.75rem 1.8rem;border-radius:50px;font-weight:600;font-size:1rem;
  border:1px solid var(--border);transition:all .25s;
}
.btn-secondary:hover{background:var(--surface2);border-color:var(--accent);transform:translateY(-2px)}

.hero-stats{
  display:flex;justify-content:center;gap:3rem;margin-top:3rem;flex-wrap:wrap;
}
.stat{text-align:center}
.stat-num{font-size:1.8rem;font-weight:900;color:var(--accent2)}
.stat-label{font-size:.8rem;color:var(--text3);text-transform:uppercase;letter-spacing:.08em;margin-top:.2rem}

/* ── SECTIONS ── */
section{padding:5rem 1.5rem}
.container{max-width:1200px;margin:0 auto}
.section-header{text-align:center;margin-bottom:3.5rem}
.section-eyebrow{
  display:inline-block;font-size:.75rem;font-weight:700;letter-spacing:.15em;
  text-transform:uppercase;color:var(--accent2);margin-bottom:.75rem;
}
.section-title{font-size:clamp(1.8rem,4vw,2.8rem);font-weight:800;letter-spacing:-.02em;margin-bottom:.75rem}
.section-sub{color:var(--text2);max-width:560px;margin:0 auto}

/* ── SERVICES ── */
#services{background:var(--bg2)}
.services-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:1.5rem}
.service-card{
  background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-lg);
  padding:2rem;transition:all .3s;position:relative;overflow:hidden;cursor:pointer;
}
.service-card::before{
  content:'';position:absolute;inset:0;
  background:linear-gradient(135deg,rgba(124,58,237,.05),transparent);
  opacity:0;transition:.3s;
}
.service-card:hover{transform:translateY(-4px);border-color:var(--accent);box-shadow:0 20px 60px rgba(124,58,237,.15)}
.service-card:hover::before{opacity:1}
.service-icon{font-size:2.5rem;margin-bottom:1rem}
.service-name{font-size:1.1rem;font-weight:700;margin-bottom:.5rem}
.service-desc{color:var(--text2);font-size:.9rem;line-height:1.6}
.service-arrow{
  display:inline-flex;align-items:center;gap:.3rem;margin-top:1rem;
  color:var(--accent2);font-size:.85rem;font-weight:600;
}

/* ── PRICING ── */
#pricing{background:var(--bg)}
.cat-tabs{display:flex;gap:.5rem;justify-content:center;flex-wrap:wrap;margin-bottom:2.5rem}
.cat-tab{
  padding:.5rem 1.2rem;border-radius:50px;font-size:.9rem;font-weight:600;
  border:1px solid var(--border);background:var(--surface);color:var(--text2);
  transition:all .2s;cursor:pointer;
}
.cat-tab.active{background:var(--accent);border-color:var(--accent);color:#fff}
.cat-tab:hover:not(.active){border-color:var(--accent);color:var(--accent2)}
.plans-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:1.5rem}
.plan-card{
  background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-lg);
  padding:2rem;transition:all .3s;position:relative;
}
.plan-card.featured{
  border-color:var(--accent);
  background:linear-gradient(135deg,var(--surface),rgba(124,58,237,.08));
  box-shadow:0 0 50px rgba(124,58,237,.2);
}
.plan-badge{
  position:absolute;top:1rem;right:1rem;
  background:var(--accent);color:#fff;padding:.2rem .7rem;
  border-radius:50px;font-size:.7rem;font-weight:700;text-transform:uppercase;letter-spacing:.08em;
}
.plan-name{font-size:1.2rem;font-weight:800;margin-bottom:.25rem}
.plan-price{display:flex;align-items:baseline;gap:.3rem;margin:1rem 0}
.price-currency{font-size:1.1rem;font-weight:700;color:var(--text2)}
.price-amount{font-size:2.8rem;font-weight:900;color:var(--text);line-height:1}
.price-per{color:var(--text3);font-size:.85rem}
.plan-specs{
  background:var(--bg2);border-radius:var(--radius);padding:1rem;margin:1rem 0;
  display:grid;gap:.5rem;
}
.spec-row{display:flex;justify-content:space-between;font-size:.85rem}
.spec-key{color:var(--text2)}
.spec-val{color:var(--text);font-weight:600;font-family:var(--mono)}
.plan-features{list-style:none;margin:1rem 0;display:grid;gap:.4rem}
.plan-features li{display:flex;align-items:center;gap:.5rem;font-size:.87rem;color:var(--text2)}
.plan-features li::before{content:'✓';color:var(--green);font-weight:700;flex-shrink:0}
.plan-btn{
  width:100%;margin-top:1.2rem;padding:.7rem;border-radius:var(--radius);
  font-weight:700;font-size:.95rem;border:none;transition:all .25s;
}
.plan-btn-primary{background:var(--accent);color:#fff}
.plan-btn-primary:hover{background:var(--accent2);transform:translateY(-1px)}
.plan-btn-secondary{background:var(--surface2);color:var(--text);border:1px solid var(--border)}
.plan-btn-secondary:hover{border-color:var(--accent);color:var(--accent2)}

/* ── DISCORD ── */
#discord{
  background:linear-gradient(135deg,rgba(124,58,237,.1),rgba(91,33,182,.1));
  border-top:1px solid var(--border);border-bottom:1px solid var(--border);
}
.discord-inner{text-align:center;max-width:600px;margin:0 auto}
.discord-icon{font-size:4rem;margin-bottom:1rem}
.discord-title{font-size:2rem;font-weight:800;margin-bottom:.75rem}
.discord-sub{color:var(--text2);margin-bottom:2rem;font-size:1.05rem}
.discord-btn{
  display:inline-flex;align-items:center;gap:.5rem;
  background:#5865F2;color:#fff;padding:.85rem 2rem;border-radius:50px;
  font-weight:700;font-size:1rem;transition:all .25s;
}
.discord-btn:hover{background:#4752c4;transform:translateY(-2px);box-shadow:0 10px 40px rgba(88,101,242,.4)}

/* ── FOOTER ── */
footer{background:var(--bg2);border-top:1px solid var(--border);padding:2.5rem 1.5rem;text-align:center}
.footer-inner{max-width:1200px;margin:0 auto}
.footer-brand{font-size:1.1rem;font-weight:800;margin-bottom:.5rem}
.footer-text{color:var(--text3);font-size:.85rem}

/* ── TOAST ── */
.toast-container{position:fixed;top:80px;right:1.5rem;z-index:9999;display:flex;flex-direction:column;gap:.5rem}
.toast{
  padding:.75rem 1.25rem;border-radius:var(--radius);font-size:.9rem;font-weight:500;
  background:var(--surface2);border:1px solid var(--border);box-shadow:0 8px 30px rgba(0,0,0,.4);
  animation:slideIn .3s ease;max-width:320px;
}
.toast.success{border-color:var(--green);background:rgba(34,197,94,.1);color:var(--green)}
.toast.error{border-color:var(--red);background:rgba(239,68,68,.1);color:var(--red)}
@keyframes slideIn{from{transform:translateX(100%);opacity:0}to{transform:translateX(0);opacity:1}}

/* ── MODAL ── */
.modal-overlay{
  display:none;position:fixed;inset:0;z-index:2000;
  background:rgba(0,0,0,.7);backdrop-filter:blur(8px);
  align-items:center;justify-content:center;padding:1rem;
}
.modal-overlay.open{display:flex}
.modal{
  background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius-lg);
  padding:2rem;width:100%;max-width:560px;max-height:90vh;overflow-y:auto;
  position:relative;
}
.modal h2{font-size:1.3rem;font-weight:800;margin-bottom:1.5rem;display:flex;align-items:center;gap:.5rem}
.modal-close{
  position:absolute;top:1rem;right:1rem;background:var(--surface);
  border:1px solid var(--border);border-radius:8px;width:32px;height:32px;
  display:flex;align-items:center;justify-content:center;font-size:1.1rem;
  cursor:pointer;color:var(--text2);transition:.2s;
}
.modal-close:hover{color:var(--text);background:var(--surface2)}

/* ── ADMIN ── */
#admin-page{display:none;min-height:100vh;padding-top:64px;background:var(--bg)}
.admin-layout{display:flex;min-height:calc(100vh - 64px)}
.admin-sidebar{
  width:240px;flex-shrink:0;background:var(--bg2);border-right:1px solid var(--border);
  padding:1.5rem;display:flex;flex-direction:column;gap:.25rem;
}
.admin-sidebar .sidebar-section{font-size:.7rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--text3);padding:.5rem .75rem;margin-top:.5rem}
.sidebar-btn{
  display:flex;align-items:center;gap:.6rem;padding:.65rem .75rem;border-radius:var(--radius);
  font-size:.9rem;font-weight:500;color:var(--text2);background:none;border:none;
  width:100%;text-align:left;transition:.2s;cursor:pointer;
}
.sidebar-btn:hover,.sidebar-btn.active{background:var(--surface);color:var(--text)}
.sidebar-btn.active{color:var(--accent2)}
.sidebar-btn .icon{font-size:1.1rem;width:20px;text-align:center}
.admin-content{flex:1;padding:2rem;overflow-y:auto}
.admin-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:2rem}
.admin-title{font-size:1.4rem;font-weight:800}
.admin-panel{display:none}
.admin-panel.active{display:block}

/* ── FORMS ── */
.form-group{margin-bottom:1.2rem}
.form-label{display:block;font-size:.85rem;font-weight:600;color:var(--text2);margin-bottom:.4rem}
.form-input,.form-select,.form-textarea{
  width:100%;background:var(--surface);border:1px solid var(--border);color:var(--text);
  padding:.65rem .9rem;border-radius:var(--radius);font-size:.9rem;transition:.2s;
  outline:none;
}
.form-input:focus,.form-select:focus,.form-textarea:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(124,58,237,.15)}
.form-textarea{resize:vertical;min-height:80px}
.form-select option{background:var(--bg2);color:var(--text)}
.form-row{display:grid;grid-template-columns:1fr 1fr;gap:1rem}
.form-hint{font-size:.78rem;color:var(--text3);margin-top:.3rem}
.form-actions{display:flex;gap:.75rem;justify-content:flex-end;margin-top:1.5rem;padding-top:1rem;border-top:1px solid var(--border)}
.btn-save{background:var(--accent);color:#fff;padding:.65rem 1.4rem;border-radius:var(--radius);font-weight:700;font-size:.9rem;border:none;transition:.2s;cursor:pointer}
.btn-save:hover{background:var(--accent2)}
.btn-cancel{background:var(--surface2);color:var(--text2);padding:.65rem 1.2rem;border-radius:var(--radius);font-weight:600;font-size:.9rem;border:1px solid var(--border);transition:.2s;cursor:pointer}
.btn-cancel:hover{border-color:var(--text3);color:var(--text)}
.btn-danger{background:var(--red);color:#fff;padding:.5rem 1rem;border-radius:8px;font-weight:600;font-size:.85rem;border:none;cursor:pointer;transition:.2s}
.btn-danger:hover{background:#dc2626}
.btn-edit{background:var(--surface2);color:var(--text2);padding:.5rem 1rem;border-radius:8px;font-weight:600;font-size:.85rem;border:1px solid var(--border);cursor:pointer;transition:.2s}
.btn-edit:hover{border-color:var(--accent);color:var(--accent2)}
.btn-add{display:inline-flex;align-items:center;gap:.4rem;background:var(--accent);color:#fff;padding:.6rem 1.2rem;border-radius:var(--radius);font-weight:700;font-size:.9rem;border:none;cursor:pointer;transition:.2s}
.btn-add:hover{background:var(--accent2)}

/* ── TABLES ── */
.data-table{width:100%;border-collapse:collapse;font-size:.88rem}
.data-table th{background:var(--surface);padding:.75rem 1rem;text-align:left;font-weight:600;color:var(--text2);font-size:.78rem;text-transform:uppercase;letter-spacing:.06em;border-bottom:1px solid var(--border)}
.data-table td{padding:.75rem 1rem;border-bottom:1px solid rgba(255,255,255,.04);vertical-align:middle}
.data-table tr:hover td{background:rgba(124,58,237,.04)}
.table-wrap{overflow-x:auto;border-radius:var(--radius-lg);border:1px solid var(--border)}
.badge-featured{background:rgba(124,58,237,.2);color:var(--accent2);padding:.15rem .5rem;border-radius:4px;font-size:.75rem;font-weight:600}
.badge-hidden{background:rgba(239,68,68,.1);color:var(--red);padding:.15rem .5rem;border-radius:4px;font-size:.75rem;font-weight:600}
.badge-visible{background:rgba(34,197,94,.1);color:var(--green);padding:.15rem .5rem;border-radius:4px;font-size:.75rem;font-weight:600}
.actions-cell{display:flex;gap:.4rem;align-items:center}

/* ── SETTINGS PANEL ── */
.settings-sections{display:grid;gap:1.5rem}
.settings-card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-lg);padding:1.5rem}
.settings-card h3{font-size:1rem;font-weight:700;margin-bottom:1.2rem;padding-bottom:.75rem;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:.5rem}
.color-swatch-row{display:flex;align-items:center;gap:1rem}
.color-swatch{width:40px;height:40px;border-radius:8px;border:2px solid var(--border);cursor:pointer;flex-shrink:0}
.theme-btns{display:flex;gap:.5rem}
.theme-btn{padding:.5rem 1rem;border-radius:8px;font-size:.85rem;font-weight:600;border:1px solid var(--border);background:var(--surface2);color:var(--text2);cursor:pointer;transition:.2s}
.theme-btn.active{background:var(--accent);border-color:var(--accent);color:#fff}

/* ── LOGIN ── */
#login-page{
  display:none;min-height:100vh;align-items:center;justify-content:center;
  background:var(--bg);padding:1.5rem;
}
.login-card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-lg);padding:2.5rem;width:100%;max-width:380px;text-align:center}
.login-card .brand{font-size:1.5rem;font-weight:800;margin-bottom:.25rem}
.login-card .sub{color:var(--text2);font-size:.9rem;margin-bottom:2rem}
.login-card .form-group{text-align:left}
.login-btn{width:100%;background:var(--accent);color:#fff;padding:.8rem;border-radius:var(--radius);font-weight:700;font-size:1rem;border:none;cursor:pointer;transition:.2s;margin-top:.5rem}
.login-btn:hover{background:var(--accent2)}
.back-link{color:var(--text3);font-size:.85rem;margin-top:1.2rem;display:block}
.back-link:hover{color:var(--text2)}

/* ── MAINTENANCE ── */
#maintenance-page{display:none;min-height:100vh;align-items:center;justify-content:center;text-align:center;padding:2rem}
.maintenance-icon{font-size:5rem;margin-bottom:1rem}
.maintenance-title{font-size:2.5rem;font-weight:900;margin-bottom:.75rem}
.maintenance-sub{color:var(--text2);font-size:1.1rem}

/* ── SPECS KEY-VALUE EDITOR ── */
.kv-editor{display:grid;gap:.5rem}
.kv-row{display:flex;gap:.5rem;align-items:center}
.kv-row input{flex:1;background:var(--surface2);border:1px solid var(--border);color:var(--text);padding:.45rem .7rem;border-radius:8px;font-size:.85rem;outline:none}
.kv-row input:focus{border-color:var(--accent)}
.kv-del{background:none;border:none;color:var(--red);cursor:pointer;font-size:1.1rem;padding:.2rem .4rem;border-radius:4px;transition:.2s}
.kv-del:hover{background:rgba(239,68,68,.1)}
.kv-add{display:inline-flex;align-items:center;gap:.3rem;background:none;border:1px dashed var(--border);color:var(--text3);padding:.4rem .8rem;border-radius:8px;font-size:.82rem;cursor:pointer;transition:.2s;margin-top:.25rem}
.kv-add:hover{border-color:var(--accent);color:var(--accent2)}

/* ── FEATURES LIST EDITOR ── */
.feat-editor{display:grid;gap:.4rem}
.feat-row{display:flex;gap:.5rem;align-items:center}
.feat-row input{flex:1;background:var(--surface2);border:1px solid var(--border);color:var(--text);padding:.45rem .7rem;border-radius:8px;font-size:.85rem;outline:none}
.feat-row input:focus{border-color:var(--accent)}

/* ── EMPTY STATE ── */
.empty-state{text-align:center;padding:4rem 2rem;color:var(--text3)}
.empty-state .icon{font-size:3rem;margin-bottom:.75rem}
.empty-state p{font-size:.95rem}

/* ── RESPONSIVE ── */
@media(max-width:900px){
  .admin-sidebar{display:none}
  .admin-layout{flex-direction:column}
  .admin-content{padding:1.25rem}
  .form-row{grid-template-columns:1fr}
}
@media(max-width:768px){
  .nav-links{display:none}
  .hamburger{display:flex}
  .hero-stats{gap:1.5rem}
  .form-actions{flex-direction:column}
  .form-actions .btn-save,.form-actions .btn-cancel{width:100%}
}
@media(max-width:480px){
  .plans-grid{grid-template-columns:1fr}
  .services-grid{grid-template-columns:1fr}
  .modal{padding:1.25rem}
  .admin-content{padding:1rem}
}

/* ── LOADING ── */
.spinner{width:28px;height:28px;border:3px solid var(--border);border-top-color:var(--accent);border-radius:50%;animation:spin .7s linear infinite;margin:2rem auto}
@keyframes spin{to{transform:rotate(360deg)}}
</style>
</head>
<body>

<!-- TOAST CONTAINER -->
<div class="toast-container" id="toasts"></div>

<!-- NAVBAR -->
<nav id="navbar">
  <div class="nav-brand">
    <span class="icon" id="nb-icon">⚡</span>
    <span id="nb-name">VantixNodes</span>
  </div>
  <div class="nav-links" id="nav-links-desktop"></div>
  <button class="hamburger" id="hamburger" aria-label="Menu">
    <span></span><span></span><span></span>
  </button>
</nav>
<div class="mobile-nav" id="mobile-nav"></div>

<!-- MAINTENANCE PAGE -->
<div id="maintenance-page">
  <div>
    <div class="maintenance-icon">🔧</div>
    <h1 class="maintenance-title">Under Maintenance</h1>
    <p class="maintenance-sub">We're upgrading our systems. Back soon!<br>
      <a href="/admin" style="color:var(--accent2);margin-top:1rem;display:inline-block">Admin Login</a>
    </p>
  </div>
</div>

<!-- LOGIN PAGE -->
<div id="login-page">
  <div class="login-card">
    <div class="brand" id="login-brand">⚡ VantixNodes</div>
    <div class="sub">Admin Panel</div>
    <div class="form-group">
      <label class="form-label">Username</label>
      <input id="login-user" class="form-input" placeholder="admin" autocomplete="username"/>
    </div>
    <div class="form-group">
      <label class="form-label">Password</label>
      <input id="login-pass" class="form-input" type="password" placeholder="••••••••" autocomplete="current-password"/>
    </div>
    <button class="login-btn" onclick="doLogin()">Sign In</button>
    <a class="back-link" href="/" onclick="showPage('main')">← Back to website</a>
  </div>
</div>

<!-- MAIN WEBSITE -->
<div id="main-page">

  <!-- HERO -->
  <section id="home">
    <div class="hero-bg"></div>
    <div class="hero-grid"></div>
    <div class="hero-orb orb1"></div>
    <div class="hero-orb orb2"></div>
    <div class="hero-content">
      <div class="hero-badge">🚀 Trusted by 10,000+ Gamers & Developers</div>
      <h1 class="hero-title" id="hero-title">
        Next-Gen <span class="gradient">Game & VPS</span> Hosting
      </h1>
      <p class="hero-sub" id="hero-sub">Blazing fast servers for Minecraft, VPS, Bots & Web hosting. Zero lag, 99.9% uptime, instant setup.</p>
      <div class="hero-btns">
        <button class="btn-primary" onclick="scrollTo2('pricing')">View Plans</button>
        <button class="btn-secondary" id="hero-discord-btn" onclick="openDiscord()">Join Discord</button>
      </div>
      <div class="hero-stats">
        <div class="stat"><div class="stat-num">99.9%</div><div class="stat-label">Uptime SLA</div></div>
        <div class="stat"><div class="stat-num">10K+</div><div class="stat-label">Active Servers</div></div>
        <div class="stat"><div class="stat-num">&lt;2ms</div><div class="stat-label">Avg Latency</div></div>
        <div class="stat"><div class="stat-num">24/7</div><div class="stat-label">Support</div></div>
      </div>
    </div>
  </section>

  <!-- SERVICES -->
  <section id="services">
    <div class="container">
      <div class="section-header">
        <div class="section-eyebrow">What We Offer</div>
        <h2 class="section-title">Hosting for Every Need</h2>
        <p class="section-sub">From game servers to production VPS, we power what you build.</p>
      </div>
      <div class="services-grid" id="services-grid">
        <div class="spinner"></div>
      </div>
    </div>
  </section>

  <!-- PRICING -->
  <section id="pricing">
    <div class="container">
      <div class="section-header">
        <div class="section-eyebrow">Transparent Pricing</div>
        <h2 class="section-title">Plans for Everyone</h2>
        <p class="section-sub">No hidden fees. Cancel anytime. Get started in under 60 seconds.</p>
      </div>
      <div class="cat-tabs" id="cat-tabs"></div>
      <div class="plans-grid" id="plans-grid">
        <div class="spinner"></div>
      </div>
    </div>
  </section>

  <!-- DISCORD CTA -->
  <section id="discord">
    <div class="container">
      <div class="discord-inner">
        <div class="discord-icon">💬</div>
        <h2 class="discord-title">Join Our Community</h2>
        <p class="discord-sub" id="discord-sub">Get support, share your builds, and stay updated on the latest from VantixNodes.</p>
        <a class="discord-btn" id="discord-join-btn" href="#" onclick="openDiscord();return false">
          <svg width="22" height="16" viewBox="0 0 71 55" fill="currentColor"><path d="M60.1 4.9A58.6 58.6 0 0 0 45.6.4a.2.2 0 0 0-.2.1 40 40 0 0 0-1.8 3.6 54 54 0 0 0-16.3 0A36.8 36.8 0 0 0 25.5.5a.2.2 0 0 0-.2-.1A58.4 58.4 0 0 0 10.8 4.9a.2.2 0 0 0-.1.1C1.6 18.1-.9 31 .3 43.7a.2.2 0 0 0 .1.2 58.8 58.8 0 0 0 17.7 9 .2.2 0 0 0 .2-.1 42 42 0 0 0 3.6-5.9.2.2 0 0 0-.1-.3 38.7 38.7 0 0 1-5.5-2.6.2.2 0 0 1 0-.4l1.1-.9a.2.2 0 0 1 .2 0c11.5 5.3 24 5.3 35.4 0a.2.2 0 0 1 .2 0l1.1.9a.2.2 0 0 1 0 .4 36 36 0 0 1-5.5 2.6.2.2 0 0 0-.1.3 47 47 0 0 0 3.6 5.9.2.2 0 0 0 .2.1 58.7 58.7 0 0 0 17.7-9 .2.2 0 0 0 .1-.2c1.5-15-2.5-28-10.5-39.5a.2.2 0 0 0-.1-.2ZM23.7 36c-3.5 0-6.4-3.2-6.4-7.2s2.9-7.2 6.4-7.2c3.6 0 6.5 3.3 6.4 7.2 0 4-2.9 7.2-6.4 7.2Zm23.6 0c-3.5 0-6.4-3.2-6.4-7.2s2.9-7.2 6.4-7.2c3.6 0 6.5 3.3 6.4 7.2 0 4-2.8 7.2-6.4 7.2Z"/></svg>
          Join Our Discord
        </a>
      </div>
    </div>
  </section>

  <!-- FOOTER -->
  <footer>
    <div class="footer-inner">
      <div class="footer-brand" id="footer-brand">⚡ VantixNodes</div>
      <div class="footer-text" id="footer-text">© 2025 VantixNodes. All rights reserved.</div>
    </div>
  </footer>

</div><!-- /main-page -->

<!-- ADMIN PAGE -->
<div id="admin-page">
  <nav id="navbar" style="display:none"></nav>
  <div class="admin-layout">
    <!-- Sidebar -->
    <aside class="admin-sidebar">
      <div class="sidebar-section">Dashboard</div>
      <button class="sidebar-btn active" onclick="showPanel('dash')" id="sb-dash">
        <span class="icon">📊</span> Overview
      </button>
      <div class="sidebar-section">Catalog</div>
      <button class="sidebar-btn" onclick="showPanel('cats')" id="sb-cats">
        <span class="icon">🗂️</span> Categories
      </button>
      <button class="sidebar-btn" onclick="showPanel('plans')" id="sb-plans">
        <span class="icon">💎</span> Plans
      </button>
      <div class="sidebar-section">Appearance</div>
      <button class="sidebar-btn" onclick="showPanel('settings')" id="sb-settings">
        <span class="icon">⚙️</span> Site Settings
      </button>
      <button class="sidebar-btn" onclick="showPanel('theme')" id="sb-theme">
        <span class="icon">🎨</span> Theme & Branding
      </button>
      <div class="sidebar-section">Account</div>
      <button class="sidebar-btn" onclick="showPanel('password')" id="sb-password">
        <span class="icon">🔑</span> Change Password
      </button>
      <button class="sidebar-btn" onclick="adminLogout()" style="color:var(--red)">
        <span class="icon">🚪</span> Logout
      </button>
    </aside>

    <!-- Content -->
    <main class="admin-content">

      <!-- OVERVIEW -->
      <div class="admin-panel active" id="panel-dash">
        <div class="admin-header">
          <h1 class="admin-title">Welcome back, Admin 👋</h1>
          <a href="/" target="_blank" class="btn-edit">View Site →</a>
        </div>
        <div id="dash-stats" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:1rem;margin-bottom:2rem"></div>
        <div style="background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-lg);padding:1.5rem">
          <h3 style="margin-bottom:1rem;font-size:1rem;font-weight:700">Quick Actions</h3>
          <div style="display:flex;gap:.75rem;flex-wrap:wrap">
            <button class="btn-add" onclick="showPanel('plans');openNewPlan()">➕ New Plan</button>
            <button class="btn-add" onclick="showPanel('cats');openNewCat()" style="background:var(--surface2);color:var(--text2);border:1px solid var(--border)">➕ New Category</button>
            <button class="btn-add" onclick="showPanel('settings')" style="background:var(--surface2);color:var(--text2);border:1px solid var(--border)">⚙️ Site Settings</button>
          </div>
        </div>
      </div>

      <!-- CATEGORIES -->
      <div class="admin-panel" id="panel-cats">
        <div class="admin-header">
          <h1 class="admin-title">Categories</h1>
          <button class="btn-add" onclick="openNewCat()">➕ Add Category</button>
        </div>
        <div class="table-wrap">
          <table class="data-table">
            <thead><tr><th>Icon</th><th>Name</th><th>Slug</th><th>Order</th><th>Visible</th><th>Actions</th></tr></thead>
            <tbody id="cats-tbody"></tbody>
          </table>
        </div>
      </div>

      <!-- PLANS -->
      <div class="admin-panel" id="panel-plans">
        <div class="admin-header">
          <h1 class="admin-title">Plans</h1>
          <button class="btn-add" onclick="openNewPlan()">➕ Add Plan</button>
        </div>
        <div style="margin-bottom:1rem">
          <select class="form-select" id="plans-filter" onchange="loadPlansAdmin()" style="max-width:200px">
            <option value="">All Categories</option>
          </select>
        </div>
        <div class="table-wrap">
          <table class="data-table">
            <thead><tr><th>Name</th><th>Category</th><th>Price</th><th>Featured</th><th>Visible</th><th>Actions</th></tr></thead>
            <tbody id="plans-tbody"></tbody>
          </table>
        </div>
      </div>

      <!-- SETTINGS -->
      <div class="admin-panel" id="panel-settings">
        <div class="admin-header"><h1 class="admin-title">Site Settings</h1></div>
        <div class="settings-sections">
          <div class="settings-card">
            <h3>🌐 General</h3>
            <div class="form-row">
              <div class="form-group">
                <label class="form-label">Site Name</label>
                <input id="s-name" class="form-input" placeholder="VantixNodes"/>
              </div>
              <div class="form-group">
                <label class="form-label">Site Icon (Emoji)</label>
                <input id="s-icon" class="form-input" placeholder="⚡" maxlength="4"/>
              </div>
            </div>
            <div class="form-group">
              <label class="form-label">Discord URL</label>
              <input id="s-discord" class="form-input" placeholder="https://discord.gg/..."/>
            </div>
            <div class="form-group">
              <label class="form-label">Maintenance Mode</label>
              <select id="s-maintenance" class="form-select">
                <option value="0">Off — Site is live</option>
                <option value="1">On — Show maintenance page</option>
              </select>
            </div>
          </div>
          <div class="settings-card">
            <h3>🦸 Hero Section</h3>
            <div class="form-group">
              <label class="form-label">Hero Title</label>
              <input id="s-hero-title" class="form-input" placeholder="Next-Gen Game & VPS Hosting"/>
            </div>
            <div class="form-group">
              <label class="form-label">Hero Subtitle</label>
              <textarea id="s-hero-sub" class="form-textarea" rows="3"></textarea>
            </div>
          </div>
          <div class="settings-card">
            <h3>🔗 Navigation Links</h3>
            <div id="nav-links-editor" class="kv-editor"></div>
            <button class="kv-add" onclick="addNavLink()">＋ Add Link</button>
          </div>
          <div class="settings-card">
            <h3>🦶 Footer</h3>
            <div class="form-group">
              <label class="form-label">Footer Text</label>
              <input id="s-footer" class="form-input" placeholder="© 2025 VantixNodes..."/>
            </div>
          </div>
          <div class="form-actions" style="border:none;padding:0">
            <button class="btn-save" onclick="saveSettings()">💾 Save Settings</button>
          </div>
        </div>
      </div>

      <!-- THEME -->
      <div class="admin-panel" id="panel-theme">
        <div class="admin-header"><h1 class="admin-title">Theme & Branding</h1></div>
        <div class="settings-sections">
          <div class="settings-card">
            <h3>🎨 Color Theme</h3>
            <div class="form-group">
              <label class="form-label">Mode</label>
              <div class="theme-btns">
                <button class="theme-btn active" id="thbtn-dark" onclick="setThemeBtn('dark')">🌙 Dark</button>
                <button class="theme-btn" id="thbtn-light" onclick="setThemeBtn('light')">☀️ Light</button>
              </div>
            </div>
            <div class="form-group">
              <label class="form-label">Accent Color</label>
              <div class="color-swatch-row">
                <input type="color" id="s-accent" value="#7c3aed" class="color-swatch"/>
                <input id="s-accent-hex" class="form-input" style="max-width:130px" placeholder="#7c3aed"/>
                <span class="form-hint" style="margin:0">Affects buttons, links, highlights</span>
              </div>
            </div>
            <div style="display:flex;gap:.5rem;flex-wrap:wrap;margin-top:.75rem">
              <button class="btn-cancel" onclick="applyAccent('#7c3aed')" style="display:flex;align-items:center;gap:.4rem;font-size:.8rem">
                <span style="width:14px;height:14px;border-radius:3px;background:#7c3aed;display:inline-block"></span> Default Purple
              </button>
              <button class="btn-cancel" onclick="applyAccent('#2563eb')" style="display:flex;align-items:center;gap:.4rem;font-size:.8rem">
                <span style="width:14px;height:14px;border-radius:3px;background:#2563eb;display:inline-block"></span> Blue
              </button>
              <button class="btn-cancel" onclick="applyAccent('#059669')" style="display:flex;align-items:center;gap:.4rem;font-size:.8rem">
                <span style="width:14px;height:14px;border-radius:3px;background:#059669;display:inline-block"></span> Emerald
              </button>
              <button class="btn-cancel" onclick="applyAccent('#dc2626')" style="display:flex;align-items:center;gap:.4rem;font-size:.8rem">
                <span style="width:14px;height:14px;border-radius:3px;background:#dc2626;display:inline-block"></span> Red
              </button>
              <button class="btn-cancel" onclick="applyAccent('#d97706')" style="display:flex;align-items:center;gap:.4rem;font-size:.8rem">
                <span style="width:14px;height:14px;border-radius:3px;background:#d97706;display:inline-block"></span> Amber
              </button>
            </div>
          </div>
          <div class="form-actions" style="border:none;padding:0">
            <button class="btn-save" onclick="saveTheme()">💾 Save Theme</button>
          </div>
        </div>
      </div>

      <!-- PASSWORD -->
      <div class="admin-panel" id="panel-password">
        <div class="admin-header"><h1 class="admin-title">Change Password</h1></div>
        <div class="settings-card" style="max-width:420px">
          <div class="form-group">
            <label class="form-label">Current Password</label>
            <input id="pw-old" type="password" class="form-input" placeholder="••••••••"/>
          </div>
          <div class="form-group">
            <label class="form-label">New Password</label>
            <input id="pw-new" type="password" class="form-input" placeholder="••••••••"/>
          </div>
          <div class="form-group">
            <label class="form-label">Confirm New Password</label>
            <input id="pw-confirm" type="password" class="form-input" placeholder="••••••••"/>
          </div>
          <div class="form-actions" style="border:none;padding:0;margin-top:0">
            <button class="btn-save" onclick="changePassword()">🔑 Update Password</button>
          </div>
        </div>
      </div>

    </main>
  </div>
</div>

<!-- CATEGORY MODAL -->
<div class="modal-overlay" id="cat-modal">
  <div class="modal">
    <button class="modal-close" onclick="closeModal('cat-modal')">✕</button>
    <h2 id="cat-modal-title">🗂️ New Category</h2>
    <input type="hidden" id="cat-id"/>
    <div class="form-row">
      <div class="form-group">
        <label class="form-label">Name *</label>
        <input id="cat-name" class="form-input" placeholder="Minecraft Hosting"/>
      </div>
      <div class="form-group">
        <label class="form-label">Icon (Emoji)</label>
        <input id="cat-icon" class="form-input" placeholder="⛏️" maxlength="4"/>
      </div>
    </div>
    <div class="form-group">
      <label class="form-label">Description</label>
      <textarea id="cat-desc" class="form-textarea" placeholder="Short description…"></textarea>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label class="form-label">Sort Order</label>
        <input id="cat-order" class="form-input" type="number" value="0"/>
      </div>
      <div class="form-group">
        <label class="form-label">Visible</label>
        <select id="cat-visible" class="form-select">
          <option value="1">Yes</option>
          <option value="0">No</option>
        </select>
      </div>
    </div>
    <div class="form-actions">
      <button class="btn-cancel" onclick="closeModal('cat-modal')">Cancel</button>
      <button class="btn-save" onclick="saveCat()">💾 Save</button>
    </div>
  </div>
</div>

<!-- PLAN MODAL -->
<div class="modal-overlay" id="plan-modal">
  <div class="modal" style="max-width:680px">
    <button class="modal-close" onclick="closeModal('plan-modal')">✕</button>
    <h2 id="plan-modal-title">💎 New Plan</h2>
    <input type="hidden" id="plan-id"/>
    <div class="form-row">
      <div class="form-group">
        <label class="form-label">Plan Name *</label>
        <input id="plan-name" class="form-input" placeholder="Pro"/>
      </div>
      <div class="form-group">
        <label class="form-label">Category *</label>
        <select id="plan-cat" class="form-select"></select>
      </div>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label class="form-label">Price *</label>
        <input id="plan-price" class="form-input" type="number" step="0.01" placeholder="9.99"/>
      </div>
      <div class="form-group">
        <label class="form-label">Currency</label>
        <select id="plan-currency" class="form-select">
          <option value="USD">USD ($)</option>
          <option value="EUR">EUR (€)</option>
          <option value="GBP">GBP (£)</option>
          <option value="INR">INR (₹)</option>
        </select>
      </div>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label class="form-label">Billing Period</label>
        <select id="plan-billing" class="form-select">
          <option value="monthly">Monthly</option>
          <option value="quarterly">Quarterly</option>
          <option value="yearly">Yearly</option>
        </select>
      </div>
      <div class="form-group">
        <label class="form-label">Badge (Optional)</label>
        <input id="plan-badge" class="form-input" placeholder="Popular / Best Value"/>
      </div>
    </div>
    <div class="form-group">
      <label class="form-label">Discord / Order URL (Optional)</label>
      <input id="plan-discord" class="form-input" placeholder="https://discord.gg/…"/>
      <div class="form-hint">If set, the order button links here. Otherwise links to site Discord.</div>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label class="form-label">Featured</label>
        <select id="plan-featured" class="form-select">
          <option value="0">No</option>
          <option value="1">Yes (highlighted)</option>
        </select>
      </div>
      <div class="form-group">
        <label class="form-label">Visible</label>
        <select id="plan-visible" class="form-select">
          <option value="1">Yes</option>
          <option value="0">No</option>
        </select>
      </div>
    </div>
    <div class="form-group">
      <label class="form-label">Specs (Key → Value)</label>
      <div class="kv-editor" id="plan-specs-editor"></div>
      <button class="kv-add" onclick="addSpecRow()">＋ Add Spec</button>
    </div>
    <div class="form-group">
      <label class="form-label">Features (one per row)</label>
      <div class="feat-editor" id="plan-feats-editor"></div>
      <button class="kv-add" onclick="addFeatRow()">＋ Add Feature</button>
    </div>
    <div class="form-row">
      <div class="form-group">
        <label class="form-label">Sort Order</label>
        <input id="plan-order" class="form-input" type="number" value="0"/>
      </div>
    </div>
    <div class="form-actions">
      <button class="btn-cancel" onclick="closeModal('plan-modal')">Cancel</button>
      <button class="btn-save" onclick="savePlan()">💾 Save Plan</button>
    </div>
  </div>
</div>

<script>
// ══════════════════════════════════════════════════════════════════
// STATE
// ══════════════════════════════════════════════════════════════════
let S = {
  settings: {}, categories: [], plans: [],
  currentCat: null, isAdmin: false, theme: 'dark', accent: '#7c3aed'
};

// ══════════════════════════════════════════════════════════════════
// UTILS
// ══════════════════════════════════════════════════════════════════
const $ = id => document.getElementById(id);
const qs = sel => document.querySelector(sel);

function toast(msg, type='success'){
  const t = document.createElement('div');
  t.className = `toast ${type}`;
  t.textContent = msg;
  $('toasts').appendChild(t);
  setTimeout(()=>{t.style.opacity='0';t.style.transition='.3s';setTimeout(()=>t.remove(),400)}, 3000);
}

async function api(path, opts={}){
  const r = await fetch(path, {
    headers:{'Content-Type':'application/json',...(opts.headers||{})},
    credentials:'include',
    ...opts,
    body: opts.body ? (typeof opts.body==='string'?opts.body:JSON.stringify(opts.body)) : undefined
  });
  return r.json();
}

function scrollTo2(id){
  const el = document.getElementById(id);
  if(el) el.scrollIntoView({behavior:'smooth'});
}

function openDiscord(){
  window.open(S.settings.discord_url || 'https://discord.gg', '_blank');
}

function getCurrencySymbol(c){
  return {USD:'$',EUR:'€',GBP:'£',INR:'₹'}[c]||'$';
}

// ══════════════════════════════════════════════════════════════════
// ROUTING
// ══════════════════════════════════════════════════════════════════
function showPage(page){
  ['main','login','admin','maintenance'].forEach(p=>{
    const el = $(`${p}-page`);
    if(el){
      el.style.display = p===page ? (p==='login'||p==='maintenance'?'flex':'block') : 'none';
    }
  });
  $('navbar').style.display = (page==='main') ? 'flex' : 'none';
}

async function route(){
  const path = window.location.pathname;
  const data = await api('/api/public/settings');
  S.settings = data;
  applySettings(data);

  if(data.maintenance === '1' && !path.startsWith('/admin')){
    showPage('maintenance'); return;
  }
  if(path === '/admin/login' || path === '/admin'){
    const v = await api('/api/admin/verify');
    if(v.authenticated){ loadAdmin(); return; }
    showPage('login'); return;
  }
  showPage('main');
  loadPublic();
}

// ══════════════════════════════════════════════════════════════════
// APPLY SETTINGS (public)
// ══════════════════════════════════════════════════════════════════
function applySettings(s){
  // Name & icon
  document.title = s.site_name || 'VantixNodes';
  $('nb-name').textContent = s.site_name || 'VantixNodes';
  $('nb-icon').textContent = s.site_icon || '⚡';
  $('footer-brand').textContent = `${s.site_icon||'⚡'} ${s.site_name||'VantixNodes'}`;
  $('footer-text').textContent = s.footer_text || '';
  $('login-brand').textContent = `${s.site_icon||'⚡'} ${s.site_name||'VantixNodes'} Admin`;

  // Hero
  if(s.hero_title) $('hero-title').innerHTML = s.hero_title.replace(
    /(Game|VPS|Minecraft|Bot|Web|Hosting)/gi,
    m=>`<span class="gradient">${m}</span>`
  );
  if(s.hero_sub) $('hero-sub').textContent = s.hero_sub;

  // Theme
  if(s.theme) {
    document.documentElement.setAttribute('data-theme', s.theme);
    S.theme = s.theme;
  }
  if(s.accent_color) applyAccentLive(s.accent_color);

  // Nav links
  let navLinks = [];
  try{ navLinks = JSON.parse(s.nav_links||'[]'); }catch(e){}
  const navHTML = navLinks.map(l=>
    `<a href="${l.href||'#'}" ${l.href&&l.href.startsWith('http')?'target="_blank"':''}>${l.label}</a>`
  ).join('') +
  `<button class="nav-cta" onclick="openDiscord()">Discord</button>`;
  $('nav-links-desktop').innerHTML = navHTML;
  $('mobile-nav').innerHTML = navLinks.map(l=>
    `<a href="${l.href||'#'}">${l.label}</a>`
  ).join('') + `<button onclick="openDiscord()">Discord</button>`;
}

function applyAccentLive(color){
  const root = document.documentElement;
  root.style.setProperty('--accent', color);
  // derive lighter/darker variants
  root.style.setProperty('--accent2', color);
  root.style.setProperty('--accent3', color);
  S.accent = color;
}

// ══════════════════════════════════════════════════════════════════
// PUBLIC: LOAD SERVICES & PLANS
// ══════════════════════════════════════════════════════════════════
async function loadPublic(){
  const [cats, plans] = await Promise.all([
    api('/api/public/categories'),
    api('/api/public/plans')
  ]);
  S.categories = cats;
  S.plans = plans;
  renderServices(cats);
  renderCatTabs(cats);
  renderPlans(plans, null);
}

function renderServices(cats){
  const g = $('services-grid');
  if(!cats.length){ g.innerHTML='<div class="empty-state"><div class="icon">📦</div><p>No services yet.</p></div>'; return; }
  g.innerHTML = cats.map(c=>`
    <div class="service-card" onclick="scrollTo2('pricing');filterCat('${c.slug}')">
      <div class="service-icon">${c.icon||'🖥️'}</div>
      <div class="service-name">${c.name}</div>
      <div class="service-desc">${c.description||''}</div>
      <div class="service-arrow">View Plans →</div>
    </div>
  `).join('');
}

function renderCatTabs(cats){
  const tabs = `<button class="cat-tab active" onclick="filterCat(null)" id="tab-all">All Services</button>` +
    cats.map(c=>`<button class="cat-tab" onclick="filterCat('${c.slug}')" id="tab-${c.slug}">${c.icon||''} ${c.name}</button>`).join('');
  $('cat-tabs').innerHTML = tabs;
}

function filterCat(slug){
  S.currentCat = slug;
  document.querySelectorAll('.cat-tab').forEach(t=>t.classList.remove('active'));
  const activeTab = slug ? $(`tab-${slug}`) : $('tab-all');
  if(activeTab) activeTab.classList.add('active');
  const filtered = slug ? S.plans.filter(p=>p.category_slug===slug) : S.plans;
  renderPlans(filtered, slug);
}

function renderPlans(plans, slug){
  const g = $('plans-grid');
  if(!plans.length){
    g.innerHTML='<div class="empty-state" style="grid-column:1/-1"><div class="icon">💎</div><p>No plans available yet.</p></div>';
    return;
  }
  g.innerHTML = plans.map(p=>{
    const sym = getCurrencySymbol(p.currency||'USD');
    const specs = Object.entries(p.specs||{}).map(([k,v])=>`
      <div class="spec-row"><span class="spec-key">${k}</span><span class="spec-val">${v}</span></div>
    `).join('');
    const feats = (p.features||[]).map(f=>`<li>${f}</li>`).join('');
    const orderUrl = p.discord_url || S.settings.discord_url || '#';
    return `
    <div class="plan-card${p.featured?'  featured':''}">
      ${p.badge?`<div class="plan-badge">${p.badge}</div>`:''}
      <div style="font-size:.8rem;color:var(--text3);margin-bottom:.25rem">${p.category_icon||''} ${p.category_name||''}</div>
      <div class="plan-name">${p.name}</div>
      <div class="plan-price">
        <span class="price-currency">${sym}</span>
        <span class="price-amount">${Number(p.price).toFixed(2)}</span>
        <span class="price-per">/ ${p.billing||'mo'}</span>
      </div>
      ${specs?`<div class="plan-specs">${specs}</div>`:''}
      <ul class="plan-features">${feats}</ul>
      <button class="plan-btn ${p.featured?'plan-btn-primary':'plan-btn-secondary'}"
        onclick="window.open('${orderUrl}','_blank')">
        Order Now
      </button>
    </div>`;
  }).join('');
}

// ══════════════════════════════════════════════════════════════════
// HAMBURGER
// ══════════════════════════════════════════════════════════════════
$('hamburger').onclick = ()=>{
  $('mobile-nav').classList.toggle('open');
};

// ══════════════════════════════════════════════════════════════════
// ADMIN AUTH
// ══════════════════════════════════════════════════════════════════
async function doLogin(){
  const username = $('login-user').value.trim();
  const password = $('login-pass').value;
  if(!username||!password){ toast('Fill all fields','error'); return; }
  const r = await api('/api/admin/login', {method:'POST', body:{username,password}});
  if(r.success){ loadAdmin(); }
  else toast(r.error||'Login failed','error');
}
$('login-pass').addEventListener('keydown', e=>{ if(e.key==='Enter') doLogin(); });

async function adminLogout(){
  await api('/api/admin/logout',{method:'POST'});
  window.location.href='/';
}

// ══════════════════════════════════════════════════════════════════
// ADMIN LOAD
// ══════════════════════════════════════════════════════════════════
async function loadAdmin(){
  S.isAdmin = true;
  history.pushState({}, '', '/admin');
  showPage('admin');
  $('navbar').style.display = 'flex';
  // admin navbar
  $('nb-name').textContent = (S.settings.site_name||'VantixNodes') + ' Admin';

  await loadAdminData();
  loadDash();
  loadCatsAdmin();
  loadPlansAdmin();
  loadSettingsForm();
}

async function loadAdminData(){
  const [settings, cats] = await Promise.all([
    api('/api/admin/settings'),
    api('/api/admin/categories')
  ]);
  S.settings = settings;
  S.categories = cats;
  applySettings(settings);
}

// ── DASHBOARD
function loadDash(){
  const catCount = S.categories.length;
  const stats = [
    {icon:'🗂️', label:'Categories', val: catCount},
    {icon:'💎', label:'Total Plans', val: (S.plans||[]).length},
    {icon:'🌐', label:'Site Status', val: S.settings.maintenance==='1'?'Maintenance':'Live'},
    {icon:'🎨', label:'Theme', val: S.settings.theme==='dark'?'Dark Mode':'Light Mode'},
  ];
  $('dash-stats').innerHTML = stats.map(s=>`
    <div style="background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-lg);padding:1.25rem">
      <div style="font-size:1.5rem;margin-bottom:.5rem">${s.icon}</div>
      <div style="font-size:1.8rem;font-weight:900;margin-bottom:.2rem">${s.val}</div>
      <div style="font-size:.8rem;color:var(--text3);text-transform:uppercase;letter-spacing:.06em">${s.label}</div>
    </div>
  `).join('');
}

// ── PANELS
function showPanel(name){
  document.querySelectorAll('.admin-panel').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.sidebar-btn').forEach(b=>b.classList.remove('active'));
  $(`panel-${name}`).classList.add('active');
  const sb = $(`sb-${name}`);
  if(sb) sb.classList.add('active');
  if(name==='plans') loadPlansAdmin();
}

// ── CATEGORIES TABLE
async function loadCatsAdmin(){
  const cats = await api('/api/admin/categories');
  S.categories = cats;
  const tbody = $('cats-tbody');
  if(!cats.length){
    tbody.innerHTML=`<tr><td colspan="6"><div class="empty-state"><div class="icon">🗂️</div><p>No categories yet.</p></div></td></tr>`;
    return;
  }
  tbody.innerHTML = cats.map(c=>`
    <tr>
      <td style="font-size:1.4rem">${c.icon||'🖥️'}</td>
      <td><strong>${c.name}</strong></td>
      <td style="font-family:var(--mono);font-size:.82rem;color:var(--text3)">${c.slug}</td>
      <td>${c.sort_order}</td>
      <td><span class="badge-${c.visible?'visible':'hidden'}">${c.visible?'Visible':'Hidden'}</span></td>
      <td><div class="actions-cell">
        <button class="btn-edit" onclick='editCat(${JSON.stringify(c)})'>Edit</button>
        <button class="btn-danger" onclick="deleteCat(${c.id},'${c.name}')">Delete</button>
      </div></td>
    </tr>
  `).join('');
}

// ── PLANS TABLE
async function loadPlansAdmin(){
  const [plans, cats] = await Promise.all([
    api('/api/admin/plans'),
    api('/api/admin/categories')
  ]);
  S.plans = plans; S.categories = cats;
  // fill filter & modal selects
  const filterSel = $('plans-filter');
  const filterVal = filterSel.value;
  filterSel.innerHTML = '<option value="">All Categories</option>' +
    cats.map(c=>`<option value="${c.id}">${c.name}</option>`).join('');
  filterSel.value = filterVal;

  const filter = filterSel.value;
  const filtered = filter ? plans.filter(p=>String(p.category_id)===filter) : plans;

  const tbody = $('plans-tbody');
  if(!filtered.length){
    tbody.innerHTML=`<tr><td colspan="6"><div class="empty-state"><div class="icon">💎</div><p>No plans.</p></div></td></tr>`;
    return;
  }
  tbody.innerHTML = filtered.map(p=>`
    <tr>
      <td><strong>${p.name}</strong>${p.badge?` <span class="badge-featured">${p.badge}</span>`:''}</td>
      <td>${p.category_name||'—'}</td>
      <td style="font-weight:700">${getCurrencySymbol(p.currency||'USD')}${Number(p.price).toFixed(2)}<span style="color:var(--text3);font-size:.8rem;font-weight:400"> /${p.billing||'mo'}</span></td>
      <td>${p.featured?'<span class="badge-featured">⭐ Yes</span>':'—'}</td>
      <td><span class="badge-${p.visible?'visible':'hidden'}">${p.visible?'Yes':'No'}</span></td>
      <td><div class="actions-cell">
        <button class="btn-edit" onclick='editPlan(${JSON.stringify(p).replace(/'/g,"&#39;")})'>Edit</button>
        <button class="btn-danger" onclick="deletePlan(${p.id},'${p.name}')">Delete</button>
      </div></td>
    </tr>
  `).join('');
}

// ── CATEGORY MODAL
function openNewCat(){
  $('cat-id').value=''; $('cat-modal-title').textContent='🗂️ New Category';
  $('cat-name').value=''; $('cat-icon').value='🖥️';
  $('cat-desc').value=''; $('cat-order').value='0'; $('cat-visible').value='1';
  openModal('cat-modal');
}
function editCat(c){
  $('cat-id').value=c.id; $('cat-modal-title').textContent='✏️ Edit Category';
  $('cat-name').value=c.name; $('cat-icon').value=c.icon||'';
  $('cat-desc').value=c.description||''; $('cat-order').value=c.sort_order||0;
  $('cat-visible').value=c.visible?'1':'0';
  openModal('cat-modal');
}
async function saveCat(){
  const id = $('cat-id').value;
  const body = {
    name:$('cat-name').value.trim(), icon:$('cat-icon').value.trim(),
    description:$('cat-desc').value.trim(),
    sort_order:$('cat-order').value, visible:$('cat-visible').value
  };
  if(!body.name){ toast('Name required','error'); return; }
  const method = id?'PUT':'POST';
  const url = id?`/api/admin/categories/${id}`:'/api/admin/categories';
  const r = await api(url,{method,body});
  if(r.success){ toast('Category saved'); closeModal('cat-modal'); loadCatsAdmin(); }
  else toast(r.error||'Error','error');
}
async function deleteCat(id, name){
  if(!confirm(`Delete category "${name}" and all its plans?`)) return;
  const r = await api(`/api/admin/categories/${id}`,{method:'DELETE'});
  if(r.success){ toast('Deleted'); loadCatsAdmin(); loadPlansAdmin(); }
  else toast(r.error||'Error','error');
}

// ── PLAN MODAL
function openNewPlan(){
  $('plan-id').value=''; $('plan-modal-title').textContent='💎 New Plan';
  $('plan-name').value=''; $('plan-price').value='';
  $('plan-billing').value='monthly'; $('plan-currency').value='USD';
  $('plan-badge').value=''; $('plan-discord').value='';
  $('plan-featured').value='0'; $('plan-visible').value='1'; $('plan-order').value='0';
  // fill category select
  $('plan-cat').innerHTML = S.categories.map(c=>`<option value="${c.id}">${c.name}</option>`).join('');
  $('plan-specs-editor').innerHTML='';
  $('plan-feats-editor').innerHTML='';
  openModal('plan-modal');
}
function editPlan(p){
  $('plan-id').value=p.id; $('plan-modal-title').textContent='✏️ Edit Plan';
  $('plan-cat').innerHTML = S.categories.map(c=>`<option value="${c.id}"${c.id==p.category_id?' selected':''}>${c.name}</option>`).join('');
  $('plan-name').value=p.name; $('plan-price').value=p.price;
  $('plan-billing').value=p.billing||'monthly'; $('plan-currency').value=p.currency||'USD';
  $('plan-badge').value=p.badge||''; $('plan-discord').value=p.discord_url||'';
  $('plan-featured').value=p.featured?'1':'0'; $('plan-visible').value=p.visible?'1':'0';
  $('plan-order').value=p.sort_order||0;
  // specs
  const se = $('plan-specs-editor');
  se.innerHTML='';
  Object.entries(p.specs||{}).forEach(([k,v])=>addSpecRow(k,v));
  // features
  const fe = $('plan-feats-editor');
  fe.innerHTML='';
  (p.features||[]).forEach(f=>addFeatRow(f));
  openModal('plan-modal');
}
async function savePlan(){
  const id = $('plan-id').value;
  // collect specs
  const specs={};
  $('plan-specs-editor').querySelectorAll('.kv-row').forEach(row=>{
    const [k,v] = row.querySelectorAll('input');
    if(k.value.trim()) specs[k.value.trim()] = v.value.trim();
  });
  // collect features
  const features = [...$('plan-feats-editor').querySelectorAll('input')]
    .map(i=>i.value.trim()).filter(Boolean);
  const body = {
    category_id:$('plan-cat').value, name:$('plan-name').value.trim(),
    price:$('plan-price').value, billing:$('plan-billing').value,
    currency:$('plan-currency').value, badge:$('plan-badge').value.trim(),
    discord_url:$('plan-discord').value.trim(), featured:$('plan-featured').value,
    visible:$('plan-visible').value, sort_order:$('plan-order').value,
    specs, features
  };
  if(!body.name||!body.price){ toast('Name & price required','error'); return; }
  const method = id?'PUT':'POST';
  const url = id?`/api/admin/plans/${id}`:'/api/admin/plans';
  const r = await api(url,{method,body});
  if(r.success){ toast('Plan saved'); closeModal('plan-modal'); loadPlansAdmin(); }
  else toast(r.error||'Error','error');
}
async function deletePlan(id, name){
  if(!confirm(`Delete plan "${name}"?`)) return;
  const r = await api(`/api/admin/plans/${id}`,{method:'DELETE'});
  if(r.success){ toast('Deleted'); loadPlansAdmin(); }
  else toast(r.error||'Error','error');
}

// ── SPEC ROWS
function addSpecRow(k='',v=''){
  const row = document.createElement('div');
  row.className='kv-row';
  row.innerHTML=`<input placeholder="Key e.g. RAM" value="${k}"/><input placeholder="Value e.g. 4GB" value="${v}"/><button class="kv-del" onclick="this.parentElement.remove()">✕</button>`;
  $('plan-specs-editor').appendChild(row);
}
function addFeatRow(val=''){
  const row = document.createElement('div');
  row.className='feat-row';
  row.innerHTML=`<input placeholder="Feature description" value="${val}"/><button class="kv-del" onclick="this.parentElement.remove()">✕</button>`;
  $('plan-feats-editor').appendChild(row);
}

// ── SETTINGS FORM
function loadSettingsForm(){
  const s = S.settings;
  $('s-name').value       = s.site_name||'';
  $('s-icon').value       = s.site_icon||'';
  $('s-discord').value    = s.discord_url||'';
  $('s-maintenance').value= s.maintenance||'0';
  $('s-hero-title').value = s.hero_title||'';
  $('s-hero-sub').value   = s.hero_subtitle||'';
  $('s-footer').value     = s.footer_text||'';
  // nav links
  let navLinks=[];
  try{ navLinks=JSON.parse(s.nav_links||'[]'); }catch(e){}
  const ed = $('nav-links-editor');
  ed.innerHTML='';
  navLinks.forEach(l=>addNavLinkRow(l.label,l.href));
  // theme
  $('s-accent').value     = s.accent_color||'#7c3aed';
  $('s-accent-hex').value = s.accent_color||'#7c3aed';
  setThemeBtn(s.theme||'dark');
}
function addNavLink(){ addNavLinkRow('',''); }
function addNavLinkRow(label='',href=''){
  const row = document.createElement('div');
  row.className='kv-row';
  row.innerHTML=`<input placeholder="Label" value="${label}"/><input placeholder="URL e.g. #pricing" value="${href}"/><button class="kv-del" onclick="this.parentElement.remove()">✕</button>`;
  $('nav-links-editor').appendChild(row);
}
async function saveSettings(){
  const navLinks = [...$('nav-links-editor').querySelectorAll('.kv-row')].map(row=>{
    const [l,h]=row.querySelectorAll('input');
    return {label:l.value.trim(),href:h.value.trim()};
  }).filter(l=>l.label);
  const body = {
    site_name:$('s-name').value.trim(),
    site_icon:$('s-icon').value.trim(),
    discord_url:$('s-discord').value.trim(),
    maintenance:$('s-maintenance').value,
    hero_title:$('s-hero-title').value.trim(),
    hero_subtitle:$('s-hero-sub').value.trim(),
    footer_text:$('s-footer').value.trim(),
    nav_links:JSON.stringify(navLinks)
  };
  const r = await api('/api/admin/settings',{method:'POST',body});
  if(r.success){ toast('Settings saved'); await loadAdminData(); }
  else toast(r.error||'Error','error');
}

// ── THEME
function setThemeBtn(t){
  S.theme=t;
  document.documentElement.setAttribute('data-theme',t);
  ['dark','light'].forEach(x=>{
    const b=$(`thbtn-${x}`);
    if(b) b.classList.toggle('active', x===t);
  });
}
function applyAccent(c){
  $('s-accent').value=c;
  $('s-accent-hex').value=c;
  applyAccentLive(c);
}
$('s-accent').oninput=function(){ applyAccentLive(this.value); $('s-accent-hex').value=this.value; };
$('s-accent-hex').oninput=function(){ if(/^#[0-9a-fA-F]{6}$/.test(this.value)){ $('s-accent').value=this.value; applyAccentLive(this.value); } };
async function saveTheme(){
  const body = { theme:S.theme, accent_color:$('s-accent').value };
  const r = await api('/api/admin/settings',{method:'POST',body});
  if(r.success){ toast('Theme saved'); await loadAdminData(); }
  else toast(r.error||'Error','error');
}

// ── PASSWORD
async function changePassword(){
  const old_p=$('pw-old').value, new_p=$('pw-new').value, conf=$('pw-confirm').value;
  if(!old_p||!new_p||!conf){ toast('Fill all fields','error'); return; }
  if(new_p!==conf){ toast('Passwords do not match','error'); return; }
  if(new_p.length<6){ toast('Min 6 characters','error'); return; }
  const r = await api('/api/admin/change-password',{method:'POST',body:{old_password:old_p,new_password:new_p}});
  if(r.success){ toast('Password changed'); $('pw-old').value=$('pw-new').value=$('pw-confirm').value=''; }
  else toast(r.error||'Error','error');
}

// ── MODALS
function openModal(id){ $(id).classList.add('open'); }
function closeModal(id){ $(id).classList.remove('open'); }
document.querySelectorAll('.modal-overlay').forEach(m=>{
  m.addEventListener('click',e=>{ if(e.target===m) m.classList.remove('open'); });
});

// ── INIT
window.addEventListener('popstate', route);
route();
</script>
</body>
</html>"""

@app.route("/")
@app.route("/admin")
@app.route("/admin/login")
def serve_html():
    return HTML

if __name__ == "__main__":
    init_db()
    print("\n" + "═"*50)
    print("  ⚡  VantixNodes is running!")
    print("═"*50)
    print(f"  🌐 Website : http://localhost:5000")
    print(f"  🔐 Admin   : http://localhost:5000/admin")
    print(f"  📁 Database: VantixNodes.db")
    print(f"  👤 Login   : admin / admin123")
    print("═"*50 + "\n")
    app.run(debug=False, host="0.0.0.0", port=5000)
