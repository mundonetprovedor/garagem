# Garage Logbook - rastreador de manutenção veicular auto-hospedado
# Copyright (C) 2026 Hyprlab
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import os, uuid, sqlite3, hashlib, secrets, csv, io, json, re, calendar
from datetime import date
try:
    import fcntl
except ImportError:  # não-POSIX; somente processo único
    fcntl = None
from functools import wraps
from flask import (Flask, render_template, request, jsonify,
                   redirect, url_for, session, g, Response, send_from_directory,
                   has_request_context)

APP_VERSION = '0.3.2'

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'change-this-to-a-random-secret-key-in-production')
app.config['UPLOAD_FOLDER'] = os.environ.get('UPLOAD_FOLDER', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads'))
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024

ALLOWED_EXTENSIONS = {'png','jpg','jpeg','gif','webp','pdf'}
ROLES = {'admin','editor'}
DATABASE = os.environ.get('DATABASE_PATH', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'garage_logbook.db'))

# Permissões padrão do editor
DEFAULT_PERMS = {'can_add_cars':True,'can_edit_cars':True,'can_delete_cars':True,
                 'can_add_records':True,'can_edit_records':True,'can_delete_records':True,
                 'can_import':False,'can_export':True}

# Rótulos em português dos tipos de registro (o banco guarda os valores em inglês)
MAINT_TYPE_PT = {'Maintenance':'Manutenção','Repair':'Reparo','Upgrade':'Melhoria','Inspection':'Vistoria'}

def allowed_file(fn):
    return '.' in fn and fn.rsplit('.',1)[1].lower() in ALLOWED_EXTENSIONS

def hash_password(pw, salt=None):
    if not salt: salt = secrets.token_hex(16)
    return f"{salt}${hashlib.pbkdf2_hmac('sha256', pw.encode(), salt.encode(), 260000).hex()}"

def verify_password(pw, stored):
    return hash_password(pw, stored.split('$',1)[0]) == stored

def get_db():
    conn = sqlite3.connect(DATABASE, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    # Rastreia a conexão para que teardown_request possa desfazer e fechar mesmo se
    # a view lançar exceção antes do seu próprio conn.close(). Sem isso, uma
    # escrita com falha deixa uma transação aberta presa ao traceback registrado,
    # e toda escrita posterior falha com "database is locked" até o worker reciclar.
    if has_request_context():
        if '_db_conns' not in g: g._db_conns = []
        g._db_conns.append(conn)
    return conn

def init_db():
    """Serializado entre processos workers: o gunicorn importa este módulo uma vez por
    worker, então sem o lock todos executam as migrações concorrentemente e podem
    intercalar as etapas de reconstrução de tabelas."""
    lock_path = DATABASE + '.init.lock'
    try:
        os.makedirs(os.path.dirname(os.path.abspath(lock_path)), exist_ok=True)
    except Exception:
        pass
    if fcntl is None:
        return _init_db()
    with open(lock_path, 'w') as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            return _init_db()
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)

def _init_db():
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password TEXT NOT NULL, display_name TEXT,
            role TEXT NOT NULL DEFAULT 'editor' CHECK(role IN ('admin','editor')),
            permissions TEXT NOT NULL DEFAULT '{}',
            must_change_password INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS cars (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            year INTEGER NOT NULL, make TEXT NOT NULL, model TEXT NOT NULL,
            vin TEXT, image TEXT, purchase_date TEXT,
            placa TEXT, renavam TEXT, condutor TEXT, chassi TEXT,
            licenciamento TEXT, ipva TEXT, combustivel TEXT, crv TEXT,
            crlv TEXT, seguro TEXT, vistoria_data TEXT, vistoria_validade TEXT,
            km_atual INTEGER,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS maintenance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            car_id INTEGER NOT NULL, title TEXT NOT NULL,
            maintenance_type TEXT NOT NULL CHECK(maintenance_type IN ('Repair','Maintenance','Upgrade','Inspection')),
            service_date TEXT NOT NULL, odometer INTEGER,
            parts_vendor TEXT, cost REAL, notes TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (car_id) REFERENCES cars(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS fuelups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            car_id INTEGER NOT NULL, fuel_date TEXT NOT NULL,
            liters REAL, price REAL, odometer INTEGER,
            parts_vendor TEXT, driver TEXT, notes TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (car_id) REFERENCES cars(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS infractions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            car_id INTEGER NOT NULL, infraction_date TEXT NOT NULL,
            description TEXT, value REAL, points INTEGER,
            status TEXT NOT NULL DEFAULT 'Pendente', notes TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (car_id) REFERENCES cars(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS maintenance_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            maintenance_id INTEGER NOT NULL, filename TEXT NOT NULL,
            original_name TEXT, file_type TEXT NOT NULL DEFAULT 'image',
            caption TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (maintenance_id) REFERENCES maintenance(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS vistorias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            car_id INTEGER NOT NULL,
            vistoria_data TEXT NOT NULL,
            validade TEXT,
            observacao TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (car_id) REFERENCES cars(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS vistoria_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vistoria_id INTEGER NOT NULL, filename TEXT NOT NULL,
            original_name TEXT, file_type TEXT NOT NULL DEFAULT 'image',
            caption TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (vistoria_id) REFERENCES vistorias(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS service_reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            car_id INTEGER NOT NULL, title TEXT NOT NULL,
            interval_type TEXT NOT NULL DEFAULT 'miles',
            interval_miles INTEGER NOT NULL DEFAULT 0,
            interval_months INTEGER,
            last_done_odometer INTEGER, last_done_date TEXT, notes TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (car_id) REFERENCES cars(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            settings TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
    ''')
    if conn.execute('SELECT COUNT(*) as c FROM users').fetchone()['c'] == 0:
        # OR IGNORE: o gunicorn executa vários workers, cada um importando este módulo.
        # Sem isso, os perdedores da corrida falham no username UNIQUE.
        cur = conn.execute('INSERT OR IGNORE INTO users (username,password,display_name,role,permissions,must_change_password) VALUES (?,?,?,?,?,?)',
                     ('admin', hash_password('admin'), 'Administrador', 'admin', '{}', 1))
        if cur.rowcount:
            print("\n  Admin padrão: admin / admin — altere imediatamente!\n")
    conn.commit()
    # Migrações
    try:
        cols = [r['name'] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
        if 'must_change_password' not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 0")
        if 'permissions' not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN permissions TEXT NOT NULL DEFAULT '{}'")
        conn.commit()
    except Exception as e:
        print(f"Migração de colunas de users: {e}")
    # Migração: adiciona user_id a cars se estiver faltando
    try:
        cols = [r['name'] for r in conn.execute("PRAGMA table_info(cars)").fetchall()]
        if 'user_id' not in cols:
            admin = conn.execute("SELECT id FROM users WHERE role='admin' ORDER BY id LIMIT 1").fetchone()
            admin_id = int(admin['id']) if admin else 1
            conn.execute(f"ALTER TABLE cars ADD COLUMN user_id INTEGER NOT NULL DEFAULT {admin_id}")
            conn.commit()
    except Exception as e:
        print(f"Migração de user_id: {e}")
    # Migração: atualiza o papel viewer para editor
    try:
        conn.execute("UPDATE users SET role='editor' WHERE role='viewer'")
        conn.commit()
    except Exception as e:
        print(f"Migração de viewer->editor: {e}")
    # Migração: adiciona file_type a maintenance_images
    try:
        cols = [r['name'] for r in conn.execute("PRAGMA table_info(maintenance_images)").fetchall()]
        if 'file_type' not in cols:
            conn.execute("ALTER TABLE maintenance_images ADD COLUMN file_type TEXT NOT NULL DEFAULT 'image'")
            conn.commit()
    except Exception as e:
        print(f"Migração de file_type: {e}")
    # Migração: repara a FK de maintenance_images deixada inválida pela migração
    # CHECK de Inspection anterior a 0.2.x. Aquela versão renomeou `maintenance` para
    # uma tabela temporária sem desabilitar as foreign keys primeiro; SQLite >=3.25
    # reescreve as cláusulas REFERENCES de outras tabelas para seguir o rename, então
    # esta tabela acabou apontando para a tabela temporária, que foi então descartada.
    # Resultado: todo insert aqui falha com "no such table: main._maint_old".
    try:
        row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='maintenance_images'").fetchone()
        if row and ('_maint_old' in (row['sql'] or '') or '_m_old' in (row['sql'] or '')):
            conn.executescript("""PRAGMA foreign_keys=OFF;
                BEGIN;
                CREATE TABLE maintenance_images_new (id INTEGER PRIMARY KEY AUTOINCREMENT,
                maintenance_id INTEGER NOT NULL,filename TEXT NOT NULL,original_name TEXT,
                file_type TEXT NOT NULL DEFAULT 'image',created_at TEXT DEFAULT (datetime('now')),
                caption TEXT,
                FOREIGN KEY (maintenance_id) REFERENCES maintenance(id) ON DELETE CASCADE);
                INSERT INTO maintenance_images_new (id,maintenance_id,filename,original_name,file_type,created_at,caption)
                SELECT id,maintenance_id,filename,original_name,file_type,created_at,caption FROM maintenance_images;
                DROP TABLE maintenance_images;
                ALTER TABLE maintenance_images_new RENAME TO maintenance_images;
                COMMIT;""")
            conn.commit()
            print("Migração: chave estrangeira de maintenance_images reparada")
    except Exception as e:
        print(f"Migração FK de maintenance_images: {e}")
    # Migração: legenda opcional nos anexos
    try:
        for tbl in ('maintenance_images','vistoria_images'):
            cols=[r['name'] for r in conn.execute(f"PRAGMA table_info({tbl})").fetchall()]
            if 'caption' not in cols:
                conn.execute(f"ALTER TABLE {tbl} ADD COLUMN caption TEXT")
        conn.commit()
    except Exception as e:
        print(f"Migração de caption dos anexos: {e}")
    # Migração: adiciona CHECK de Inspection
    try:
        tbl = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='maintenance'").fetchone()
        if tbl and 'Inspection' not in (tbl['sql'] or ''):
            conn.executescript("""PRAGMA foreign_keys=OFF;ALTER TABLE maintenance RENAME TO _m_old;
                CREATE TABLE maintenance (id INTEGER PRIMARY KEY AUTOINCREMENT,car_id INTEGER NOT NULL,title TEXT NOT NULL,
                maintenance_type TEXT NOT NULL CHECK(maintenance_type IN ('Repair','Maintenance','Upgrade','Inspection')),
                service_date TEXT NOT NULL,odometer INTEGER,parts_vendor TEXT,cost REAL,notes TEXT,
                created_at TEXT DEFAULT (datetime('now')),FOREIGN KEY (car_id) REFERENCES cars(id) ON DELETE CASCADE);
                INSERT INTO maintenance SELECT * FROM _m_old;DROP TABLE _m_old;PRAGMA foreign_keys=ON;""")
            conn.commit()
    except Exception as e:
        print(f"Migração de CHECK de Inspection: {e}")
    # Migração: documentos e identificação do veículo (placa, renavam, etc.)
    try:
        cols = [r['name'] for r in conn.execute("PRAGMA table_info(cars)").fetchall()]
        for col in ('placa', 'renavam', 'condutor', 'chassi', 'licenciamento', 'ipva', 'combustivel', 'crv', 'crlv', 'seguro', 'vistoria_data', 'vistoria_validade', 'km_atual'):
            if col not in cols:
                conn.execute(f"ALTER TABLE cars ADD COLUMN {col} {'INTEGER' if col=='km_atual' else 'TEXT'}")
        conn.commit()
    except Exception as e:
        print(f"Migração de documentos do veículo: {e}")
    # Migração: a vistoria deixou de ser um par de colunas em cars e passou a ser
    # histórico (1:N), para registrar data e imagens a cada nova vistoria.
    # O par legado é copiado para a tabela vistorias e então zerado em cars.
    try:
        pend = conn.execute("SELECT id, vistoria_data, vistoria_validade FROM cars "
                            "WHERE (vistoria_data IS NOT NULL AND vistoria_data != '') "
                            "OR (vistoria_validade IS NOT NULL AND vistoria_validade != '')").fetchall()
        moved = []
        for r in pend:
            if conn.execute('SELECT COUNT(*) as c FROM vistorias WHERE car_id=?', (r['id'],)).fetchone()['c']:
                continue
            conn.execute('INSERT INTO vistorias (car_id, vistoria_data, validade) VALUES (?,?,?)',
                         (r['id'], r['vistoria_data'] or r['vistoria_validade'], r['vistoria_validade']))
            moved.append(r['id'])
        if moved:
            conn.execute('UPDATE cars SET vistoria_data=NULL, vistoria_validade=NULL WHERE id IN (%s)' % ','.join('?'*len(moved)), moved)
            print(f"Migração: {len(moved)} vistoria(s) movida(s) para o histórico")
        conn.commit()
    except Exception as e:
        print(f"Migração de vistorias: {e}")
    try:
        mcols = [r['name'] for r in conn.execute("PRAGMA table_info(maintenance)").fetchall()]
        if 'driver' not in mcols:
            conn.execute("ALTER TABLE maintenance ADD COLUMN driver TEXT")
        conn.commit()
    except Exception as e:
        print(f"Migração de driver: {e}")
    # Migração: lembretes ganharam um modo baseado em tempo, então interval_miles
    # não é mais o único intervalo. Linhas anteriores a 0.3.2 são todas por quilometragem.
    try:
        cols = [r['name'] for r in conn.execute("PRAGMA table_info(service_reminders)").fetchall()]
        if 'interval_type' not in cols:
            conn.execute("ALTER TABLE service_reminders ADD COLUMN interval_type TEXT NOT NULL DEFAULT 'miles'")
        if 'interval_months' not in cols:
            conn.execute("ALTER TABLE service_reminders ADD COLUMN interval_months INTEGER")
        if 'last_done_date' not in cols:
            conn.execute("ALTER TABLE service_reminders ADD COLUMN last_done_date TEXT")
        conn.commit()
    except Exception as e:
        print(f"Migração de colunas de intervalo dos lembretes: {e}")
    conn.close()

def save_upload(file, subfolder):
    if file and allowed_file(file.filename):
        ext = file.filename.rsplit('.',1)[1].lower()
        fn = f"{uuid.uuid4().hex}.{ext}"
        folder = os.path.join(app.config['UPLOAD_FOLDER'], subfolder)
        os.makedirs(folder, exist_ok=True)
        file.save(os.path.join(folder, fn))
        return fn
    return None

def get_file_type(filename):
    if filename and filename.rsplit('.',1)[1].lower() == 'pdf': return 'document'
    return 'image'

def latest_vistoria(conn, car_id, legacy_data=None, legacy_validade=None):
    """(data, validade) da vistoria mais recente do veículo.

    A validade vem da vistoria mais recente que tiver uma; se o veículo ainda não
    tem vistorias no histórico, cai para o par legado gravado em cars.
    """
    row = conn.execute('SELECT vistoria_data, validade FROM vistorias WHERE car_id=? ORDER BY vistoria_data DESC, id DESC LIMIT 1',
                       (car_id,)).fetchone()
    if not row: return legacy_data, legacy_validade
    validade = row['validade']
    if not validade:
        alt = conn.execute("SELECT validade FROM vistorias WHERE car_id=? AND validade IS NOT NULL AND validade!='' "
                           "ORDER BY vistoria_data DESC, id DESC LIMIT 1", (car_id,)).fetchone()
        validade = alt['validade'] if alt else None
    return row['vistoria_data'], validade

def get_user_perms(user):
    """Obtém as permissões efetivas de um usuário."""
    if user['role'] == 'admin':
        return {k: True for k in DEFAULT_PERMS}
    try:
        perms = json.loads(user.get('permissions','{}') or '{}')
        return {k: perms.get(k, v) for k, v in DEFAULT_PERMS.items()}
    except:
        return dict(DEFAULT_PERMS)

MONTH_DAYS = 30.44  # mês médio do calendário, para comparações meses-para-dias

def _rem_date(v):
    """Analisa uma data armazenada YYYY-MM-DD; None para qualquer coisa inutilizável."""
    if not v: return None
    try:
        return date.fromisoformat(str(v).strip()[:10])
    except (ValueError, TypeError):
        return None

def _add_months(d, months):
    """`d` mais N meses corridos, limitado ao último dia do mês de destino."""
    m = d.month - 1 + int(months)
    y, m = d.year + m // 12, m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))

def reminder_status(conn, rem, current_odo=None, today=None):
    """Expande uma linha de service_reminders com seu estado calculado de vencimento.

    Um lembrete conta regressivamente por quilometragem ou por tempo corrido,
    conforme `interval_type`. De qualquer forma, a âncora é o registro de serviço
    mais recente cujo título corresponda ao do lembrete, então registrar o serviço
    novamente avança automaticamente a próxima data de vencimento. `last_done_odometer`
    / `last_done_date` guardam a marcação manual — definida à mão, ou ao marcar o
    contador ao registrar um serviço — e a âncora é a que estiver mais à frente,
    de modo que marcar a reinicialização de um contador sempre prevalece.

    `remaining_fraction` é quanto do intervalo resta, e é o único campo
    comparável entre os dois modos — use-o para ordenar listas mistas.
    """
    d = dict(rem)
    cid = d['car_id']
    d['interval_type'] = itype = 'time' if (d.get('interval_type') or 'miles') == 'time' else 'miles'
    d.setdefault('interval_months', None)
    d.setdefault('last_done_date', None)
    d.update(current_odometer=None, last_service_odometer=None, next_due_odometer=None,
             miles_remaining=None, last_service_date=None, next_due_date=None,
             days_remaining=None, remaining_fraction=None)

    if itype == 'time':
        match = conn.execute(
            "SELECT MAX(service_date) AS s FROM maintenance WHERE car_id=?"
            " AND lower(trim(title))=lower(trim(?))", (cid, d['title'])).fetchone()
        anchor = max([x for x in (_rem_date(match['s'] if match else None),
                                   _rem_date(d.get('last_done_date'))) if x], default=None)
        interval = int(d.get('interval_months') or 0)
        d['last_service_date'] = anchor.isoformat() if anchor else None
        if anchor is None or interval <= 0:
            d['status'] = 'no_baseline'
            return d
        due = _add_months(anchor, interval)
        d['next_due_date'] = due.isoformat()
        remaining = (due - (today or date.today())).days
        d['days_remaining'] = remaining
        d['remaining_fraction'] = remaining / (interval * MONTH_DAYS)
        soon = max(14, int(interval * MONTH_DAYS * 0.05))
        d['status'] = 'overdue' if remaining <= 0 else ('due_soon' if remaining <= soon else 'ok')
        return d

    if current_odo is None:
        row = conn.execute('SELECT MAX(odometer) AS o FROM maintenance WHERE car_id=?', (cid,)).fetchone()
        current_odo = row['o'] if row and row['o'] is not None else None
    match = conn.execute(
        "SELECT MAX(odometer) AS o FROM maintenance WHERE car_id=? AND odometer IS NOT NULL"
        " AND lower(trim(title))=lower(trim(?))", (cid, d['title'])).fetchone()
    anchor = max([int(x) for x in (match['o'] if match else None, d.get('last_done_odometer'))
                   if x is not None], default=None)
    interval = int(d.get('interval_miles') or 0)
    d['current_odometer'] = current_odo
    d['last_service_odometer'] = anchor
    if anchor is None or interval <= 0:
        d['status'] = 'no_baseline'
        return d
    next_due = int(anchor) + interval
    d['next_due_odometer'] = next_due
    if current_odo is None:
        d['status'] = 'no_baseline'
        return d
    remaining = next_due - int(current_odo)
    d['miles_remaining'] = remaining
    d['remaining_fraction'] = remaining / interval
    soon = max(250, int(interval * 0.05))
    d['status'] = 'overdue' if remaining <= 0 else ('due_soon' if remaining <= soon else 'ok')
    return d

def reset_reminder_baselines(conn, cid, ids, odo, service_date):
    """Reinicia os contadores indicados a partir deste registro de serviço:
    contadores de quilometragem a partir do odômetro dele, contadores de tempo
    a partir da data dele. IDs que não pertencem a este carro são ignorados,
    assim como um contador de quilometragem em um registro sem odômetro."""
    done = []
    for raw in ids:
        try: rid = int(str(raw).strip())
        except (TypeError, ValueError): continue
        rem = conn.execute('SELECT * FROM service_reminders WHERE id=? AND car_id=?', (rid, cid)).fetchone()
        if not rem: continue
        if (rem['interval_type'] or 'miles') == 'time':
            if not _rem_date(service_date): continue
            conn.execute('UPDATE service_reminders SET last_done_date=? WHERE id=?', (service_date, rid))
        else:
            if odo is None: continue
            conn.execute('UPDATE service_reminders SET last_done_odometer=? WHERE id=?', (int(odo), rid))
        done.append(rid)
    return done

def reminder_sort_key(r):
    """Vencimento mais próximo primeiro entre os dois modos de intervalo;
    linhas sem baseline por último."""
    f = r.get('remaining_fraction')
    return (f is None, f if f is not None else 0.0)

def parse_reminder_input(d, base=None):
    """Valida a entrada JSON/form do lembrete, usando `base` (a linha
    existente) como fallback para o que o chamador omitiu. Retorna (fields, error)."""
    def pick(key, default=None):
        v = d.get(key)
        if v is not None: return v
        if base is not None and key in base.keys(): return base[key]
        return default

    def interval(key):
        # vazio significa "inalterado" para um intervalo, nunca "limpo"
        v = d.get(key)
        if v is None or not str(v).strip():
            v = base[key] if base is not None and key in base.keys() else None
        return int(str(v).strip()) if v is not None and str(v).strip() else None

    def odometer(key):
        # vazio *limpa* a baseline manual
        v = pick(key)
        return int(str(v).strip()) if v is not None and str(v).strip() else None

    t = str(pick('title', '') or '').strip()
    itype = 'time' if str(pick('interval_type', 'miles') or '').strip().lower() == 'time' else 'miles'
    n = str(pick('notes', '') or '').strip()
    ld_date = str(pick('last_done_date', '') or '').strip() or None
    try:
        iv_mi, iv_mo, ld_odo = interval('interval_miles'), interval('interval_months'), odometer('last_done_odometer')
    except ValueError:
        return None, 'Valores de quilometragem e intervalo devem ser números inteiros'

    if itype == 'time':
        if ld_date and _rem_date(ld_date) is None: return None, 'A data da última execução deve ser uma data válida'
    else:
        if ld_odo is not None and ld_odo < 0: return None, 'A quilometragem da última execução não pode ser negativa'
    return {'title': t, 'interval_type': itype, 'interval_miles': iv_mi or 0, 'interval_months': iv_mo,
            'last_done_odometer': ld_odo, 'last_done_date': ld_date, 'notes': n or None}, None

def can_access_car(conn, cid, user):
    """Verifica se o usuário pode acessar este carro (é dono ou admin)."""
    car = conn.execute('SELECT * FROM cars WHERE id=?',(cid,)).fetchone()
    if not car: return None
    if user['role'] == 'admin' or car['user_id'] == user['id']:
        return car
    return None

# ── Tratamento de Erros ────────────────────────────────
@app.errorhandler(413)
def too_large(e):
    if request.path.startswith('/api/'): return jsonify({'error':'Arquivo muito grande (máx 32MB)'}), 413
    return 'Arquivo muito grande', 413

@app.errorhandler(500)
def server_error(e):
    if request.path.startswith('/api/'): return jsonify({'error':'Erro interno do servidor'}), 500
    return 'Erro interno do servidor', 500

@app.teardown_request
def close_db_conns(exc):
    """Libera qualquer conexão que uma view abriu, desfazendo se falhou."""
    for conn in g.pop('_db_conns', []):
        try:
            if exc is not None: conn.rollback()
            conn.close()
        except Exception:
            pass

# ── Middleware de Autenticação ─────────────────────────
@app.before_request
def load_user():
    g.user = None
    uid = session.get('user_id')
    if uid:
        conn = get_db()
        u = conn.execute('SELECT id,username,display_name,role,permissions,must_change_password FROM users WHERE id=?',(uid,)).fetchone()
        conn.close()
        if u: g.user = dict(u)

def login_required(f):
    @wraps(f)
    def dec(*a,**kw):
        if not g.user:
            if request.path.startswith('/api/'): return jsonify({'error':'Autenticação obrigatória'}), 401
            return redirect(url_for('login_page'))
        return f(*a,**kw)
    return dec

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        @login_required
        def dec(*a,**kw):
            if g.user['role'] not in roles: return jsonify({'error':'Permissões insuficientes'}), 403
            return f(*a,**kw)
        return dec
    return decorator

def perm_required(perm):
    """Verifica uma permissão granular específica."""
    def decorator(f):
        @wraps(f)
        @login_required
        def dec(*a,**kw):
            perms = get_user_perms(g.user)
            if not perms.get(perm, False): return jsonify({'error':'Permissão negada'}), 403
            return f(*a,**kw)
        return dec
    return decorator

# ── Páginas ───────────────────────────────────────────
@app.route('/uploads/<path:filename>')
@login_required
def serve_upload(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/login')
def login_page():
    if g.user: return redirect(url_for('index'))
    return render_template('login.html', version=APP_VERSION)

@app.route('/')
@login_required
def index():
    perms = get_user_perms(g.user)
    return render_template('index.html', user=g.user, version=APP_VERSION, perms=perms)

@app.route('/api/version')
def api_version():
    return jsonify({'version': APP_VERSION})

# ── API de Autenticação ────────────────────────────────
@app.route('/api/auth/login', methods=['POST'])
def api_login():
    data = request.get_json() or {}
    u, p = data.get('username','').strip(), data.get('password','')
    if not u or not p: return jsonify({'error':'Usuário e senha obrigatórios'}), 400
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE username=?',(u,)).fetchone()
    conn.close()
    if not user or not verify_password(p, user['password']): return jsonify({'error':'Credenciais inválidas'}), 401
    session.clear(); session['user_id']=user['id']; session.permanent=True
    mcp = 0
    try: mcp = user['must_change_password']
    except: pass
    return jsonify({'id':user['id'],'username':user['username'],'display_name':user['display_name'],
                    'role':user['role'],'must_change_password':bool(mcp)})

@app.route('/api/auth/logout', methods=['POST'])
def api_logout():
    session.clear(); return jsonify({'success':True})

@app.route('/api/auth/me')
@login_required
def api_me():
    perms = get_user_perms(g.user)
    return jsonify({**g.user, 'effective_permissions': perms})

@app.route('/api/auth/change-password', methods=['POST'])
@login_required
def api_change_password():
    data = request.get_json() or {}
    cur, new = data.get('current_password',''), data.get('new_password','')
    if not cur or not new: return jsonify({'error':'Ambas as senhas são obrigatórias'}), 400
    if len(new)<4: return jsonify({'error':'Mínimo de 4 caracteres'}), 400
    conn = get_db()
    u = conn.execute('SELECT password FROM users WHERE id=?',(g.user['id'],)).fetchone()
    if not verify_password(cur, u['password']): conn.close(); return jsonify({'error':'Senha atual incorreta'}), 401
    conn.execute('UPDATE users SET password=?, must_change_password=0 WHERE id=?',(hash_password(new),g.user['id']))
    conn.commit(); conn.close()
    return jsonify({'success':True})

# ── API de Configurações ───────────────────────────────
@app.route('/api/settings', methods=['GET'])
@login_required
def get_settings():
    conn = get_db()
    row = conn.execute('SELECT settings FROM user_settings WHERE user_id=?',(g.user['id'],)).fetchone()
    conn.close()
    defaults = {'dashboard_range':'all','show_vehicles':True,'show_records':True,'show_cost':True,'show_due':True,'theme':'dark'}
    if row:
        saved = json.loads(row['settings'])
        defaults.update(saved)
    return jsonify(defaults)

@app.route('/api/settings', methods=['PUT'])
@login_required
def save_settings():
    data = request.get_json() or {}
    conn = get_db()
    s = json.dumps(data)
    existing = conn.execute('SELECT user_id FROM user_settings WHERE user_id=?',(g.user['id'],)).fetchone()
    if existing: conn.execute('UPDATE user_settings SET settings=? WHERE user_id=?',(s,g.user['id']))
    else: conn.execute('INSERT INTO user_settings (user_id,settings) VALUES (?,?)',(g.user['id'],s))
    conn.commit(); conn.close()
    return jsonify({'success':True})

# ── Gerenciamento de Usuários (admin) ─────────────────
@app.route('/api/users', methods=['GET'])
@role_required('admin')
def get_users():
    conn = get_db()
    users = conn.execute('SELECT id,username,display_name,role,permissions,created_at FROM users ORDER BY created_at').fetchall()
    conn.close()
    result = []
    for u in users:
        d = dict(u)
        d['effective_permissions'] = get_user_perms(d)
        result.append(d)
    return jsonify(result)

@app.route('/api/users', methods=['POST'])
@role_required('admin')
def create_user():
    data = request.get_json() or {}
    un=data.get('username','').strip().lower(); pw=data.get('password','')
    dn=data.get('display_name','').strip(); role=data.get('role','editor').strip()
    perms=data.get('permissions',{})
    if not un or not pw: return jsonify({'error':'Usuário e senha obrigatórios'}), 400
    if role not in ROLES: return jsonify({'error':'Papel inválido'}), 400
    if len(pw)<4: return jsonify({'error':'Mínimo de 4 caracteres'}), 400
    conn = get_db()
    if conn.execute('SELECT id FROM users WHERE username=?',(un,)).fetchone():
        conn.close(); return jsonify({'error':'Nome de usuário já existe'}), 409
    conn.execute('INSERT INTO users (username,password,display_name,role,permissions) VALUES (?,?,?,?,?)',
                 (un, hash_password(pw), dn or un, role, json.dumps(perms)))
    conn.commit()
    u = conn.execute('SELECT id,username,display_name,role,permissions,created_at FROM users WHERE username=?',(un,)).fetchone()
    conn.close()
    d = dict(u); d['effective_permissions'] = get_user_perms(d)
    return jsonify(d), 201

@app.route('/api/users/<int:uid>', methods=['PUT'])
@role_required('admin')
def update_user(uid):
    data = request.get_json() or {}
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
    if not user: conn.close(); return jsonify({'error':'Não encontrado'}), 404
    dn = data.get('display_name',user['display_name']).strip()
    role = data.get('role',user['role']).strip()
    perms = data.get('permissions')
    npw = data.get('password','').strip()
    if role not in ROLES: conn.close(); return jsonify({'error':'Papel inválido'}), 400
    if user['role']=='admin' and role!='admin':
        if conn.execute("SELECT COUNT(*) as c FROM users WHERE role='admin'").fetchone()['c']<=1:
            conn.close(); return jsonify({'error':'Não é possível remover o último admin'}), 400
    perm_str = json.dumps(perms) if perms is not None else user['permissions']
    if npw:
        if len(npw)<4: conn.close(); return jsonify({'error':'Mínimo de 4 caracteres'}), 400
        conn.execute('UPDATE users SET display_name=?,role=?,permissions=?,password=? WHERE id=?',(dn,role,perm_str,hash_password(npw),uid))
    else:
        conn.execute('UPDATE users SET display_name=?,role=?,permissions=? WHERE id=?',(dn,role,perm_str,uid))
    conn.commit()
    u = conn.execute('SELECT id,username,display_name,role,permissions,created_at FROM users WHERE id=?',(uid,)).fetchone()
    conn.close()
    d = dict(u); d['effective_permissions'] = get_user_perms(d)
    return jsonify(d)

@app.route('/api/users/<int:uid>', methods=['DELETE'])
@role_required('admin')
def delete_user(uid):
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
    if not user: conn.close(); return jsonify({'error':'Não encontrado'}), 404
    if uid==g.user['id']: conn.close(); return jsonify({'error':'Não é possível excluir a si mesmo'}), 400
    if user['role']=='admin':
        if conn.execute("SELECT COUNT(*) as c FROM users WHERE role='admin'").fetchone()['c']<=1:
            conn.close(); return jsonify({'error':'Não é possível excluir o último admin'}), 400
    conn.execute('DELETE FROM users WHERE id=?',(uid,))
    conn.commit(); conn.close()
    return jsonify({'success':True})

# ── API de Carros (multiusuário) ───────────────────────
@app.route('/api/cars', methods=['GET'])
@login_required
def get_cars():
    q = request.args.get('q','').strip()
    conn = get_db()
    if g.user['role'] == 'admin':
        if q:
            cars = conn.execute("SELECT c.*, u.display_name as owner_name FROM cars c JOIN users u ON c.user_id=u.id WHERE c.year LIKE ? OR c.make LIKE ? OR c.model LIKE ? OR c.vin LIKE ? OR c.placa LIKE ? OR c.chassi LIKE ? ORDER BY c.created_at DESC",
                (f'%{q}%',f'%{q}%',f'%{q}%',f'%{q}%',f'%{q}%',f'%{q}%')).fetchall()
        else:
            cars = conn.execute('SELECT c.*, u.display_name as owner_name FROM cars c JOIN users u ON c.user_id=u.id ORDER BY c.created_at DESC').fetchall()
    else:
        if q:
            cars = conn.execute("SELECT * FROM cars WHERE user_id=? AND (year LIKE ? OR make LIKE ? OR model LIKE ? OR vin LIKE ? OR placa LIKE ? OR chassi LIKE ?) ORDER BY created_at DESC",
                (g.user['id'],f'%{q}%',f'%{q}%',f'%{q}%',f'%{q}%',f'%{q}%',f'%{q}%')).fetchall()
        else:
            cars = conn.execute('SELECT * FROM cars WHERE user_id=? ORDER BY created_at DESC',(g.user['id'],)).fetchall()
    result = []
    for car in cars:
        c = dict(car)
        s = conn.execute("SELECT COUNT(*) as count, COALESCE(SUM(cost),0) as total_cost, MAX(odometer) as max_odo FROM maintenance WHERE car_id=?",(c['id'],)).fetchone()
        c['maintenance_count']=s['count']; c['total_cost']=s['total_cost']; c['latest_odometer']=s['max_odo']
        # Próximos lembretes de serviço para o card: os mais próximos primeiro,
        # ignorando os que não têm baseline para contar.
        rems = [reminder_status(conn, r, s['max_odo'])
                for r in conn.execute('SELECT * FROM service_reminders WHERE car_id=?', (c['id'],)).fetchall()]
        rems = [r for r in rems if r['status'] != 'no_baseline']
        rems.sort(key=reminder_sort_key)
        c['reminders'] = rems[:3]
        c['reminders_total'] = len(rems)
        c['reminders_due'] = sum(1 for r in rems if r['status'] in ('overdue','due_soon'))
        # Vistoria vem do histórico (a mais recente), não mais de colunas fixas em cars
        c['vistoria_data'], c['vistoria_validade'] = latest_vistoria(conn, c['id'], c.get('vistoria_data'), c.get('vistoria_validade'))
        # Saúde do veículo: críticos primeiro, depois alertas, senão OK
        from datetime import date as _date
        today = _date.today()
        dates = [c.get(k) for k in ('licenciamento','ipva','crlv','seguro','vistoria_validade')]
        dates = [d for d in dates if d]
        overdue_doc = any(d < today.isoformat() for d in dates)
        due_doc = any(0 <= (_date.fromisoformat(d) - today).days <= 30 for d in dates)
        overdue_rem = any(r['status'] == 'overdue' for r in rems)
        due_soon_rem = any(r['status'] == 'due_soon' for r in rems)
        if overdue_doc or overdue_rem: c['health'] = 'Crítico'
        elif due_doc or due_soon_rem or c['reminders_due']: c['health'] = 'Atenção'
        else: c['health'] = 'OK'
        c['infractions_open'] = conn.execute("SELECT COUNT(*) as c FROM infractions WHERE car_id=? AND status='Pendente'",(c['id'],)).fetchone()['c']
        result.append(c)
    conn.close()
    return jsonify(result)

@app.route('/api/cars', methods=['POST'])
@perm_required('can_add_cars')
def add_car():
    year=request.form.get('year'); make=request.form.get('make','').strip()
    model=request.form.get('model','').strip(); vin=request.form.get('vin','').strip()
    pd=request.form.get('purchase_date','').strip()
    placa=request.form.get('placa','').strip(); renavam=request.form.get('renavam','').strip()
    condutor=request.form.get('condutor','').strip(); chassi=request.form.get('chassi','').strip()
    lic=request.form.get('licenciamento','').strip(); ipva=request.form.get('ipva','').strip()
    combustivel=request.form.get('combustivel','').strip(); crv=request.form.get('crv','').strip()
    crlv=request.form.get('crlv','').strip(); seguro=request.form.get('seguro','').strip()
    vis_data=request.form.get('vistoria_data','').strip(); vis_val=request.form.get('vistoria_validade','').strip()
    km=request.form.get('km_atual','').strip()
    image = save_upload(request.files.get('image'), 'cars') if 'image' in request.files else None
    conn = get_db()
    cur = conn.execute('INSERT INTO cars (user_id,year,make,model,vin,image,purchase_date,placa,renavam,condutor,chassi,licenciamento,ipva,combustivel,crv,crlv,seguro,vistoria_data,vistoria_validade,km_atual) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (g.user['id'], int(year), make, model, vin or None, image, pd or None,
                        placa or None, renavam or None, condutor or None, chassi or None, lic or None, ipva or None,
                        combustivel or None, crv or None, crlv or None, seguro or None, None, None, int(km) if km.isdigit() else None))
    # Vistoria enviada junto do cadastro vira a primeira linha do histórico
    if vis_data or vis_val:
        conn.execute('INSERT INTO vistorias (car_id,vistoria_data,validade) VALUES (?,?,?)',
                     (cur.lastrowid, vis_data or vis_val, vis_val or None))
    conn.commit()
    car = dict(conn.execute('SELECT * FROM cars WHERE id=?',(cur.lastrowid,)).fetchone())
    car['vistoria_data'], car['vistoria_validade'] = latest_vistoria(conn, car['id'], None, None)
    conn.close()
    return jsonify(car), 201

@app.route('/api/cars/import', methods=['POST'])
@perm_required('can_add_cars')
def import_cars():
    if 'file' not in request.files: return jsonify({'error':'Nenhum arquivo enviado'}), 400
    file = request.files['file']
    if not file.filename.lower().endswith('.csv'): return jsonify({'error':'Deve ser .csv'}), 400
    try:
        raw = file.read()
        try: text = raw.decode('utf-8-sig')
        except: text = raw.decode('latin-1')
    except Exception as e: return jsonify({'error':f'Erro ao ler: {e}'}), 400
    try:
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
    except Exception as e: return jsonify({'error':f'CSV inválido: {e}'}), 400
    if not rows: return jsonify({'error':'Planilha vazia'}), 400
    import unicodedata
    def norm(h):
        h = unicodedata.normalize('NFKD', h.strip().lower()).encode('ascii','ignore').decode()
        return h.replace(' ','_')
    aliases = {'ano':'year','ano_fabricacao':'year','ano_modelo':'year','marca':'make','modelo':'model','versao':'model2','chassi':'chassi','condutor':'condutor','condutor_principal':'condutor','km':'km_atual','km_atual':'km_atual','licenciamento':'licenciamento','ipva':'ipva','combustivel':'combustivel','crv':'crv','crlv':'crlv','seguro':'seguro','placa':'placa','renavam':'renavam','vistoria_data':'vistoria_data','vistoria_validade':'vistoria_validade'}
    keymap = {}
    for h in (reader.fieldnames or []):
        n = norm(h)
        keymap[h] = aliases.get(n, n)
    ok=0; skipped=0; errors=[]
    conn = get_db()
    for i,row in enumerate(rows, start=2):
        r = {keymap[k]:(v.strip() if isinstance(v,str) else v) for k,v in row.items()}
        def gv(k):
            v = r.get(k)
            if v is None: return None
            v = str(v).strip()
            if v in ('','-','--',' - ') or v.lower()=='none': return None
            return v
        make = gv('make'); model = gv('model')
        if r.get('model2'): model = (model or '') + (' ' + r['model2'].strip() if model else r['model2'].strip())
        year_raw = gv('year')
        year = None
        if year_raw:
            m = re.search(r'\d{4}', year_raw)
            year = int(m.group()) if m else None
        if not make or not model:
            skipped += 1; errors.append(f'Linha {i}: marca/modelo ausentes'); continue
        placa = gv('placa'); renavam = gv('renavam'); chassi = gv('chassi')
        try:
            cur = conn.execute('INSERT INTO cars (user_id,year,make,model,vin,image,purchase_date,placa,renavam,condutor,chassi,licenciamento,ipva,combustivel,crv,crlv,seguro,vistoria_data,vistoria_validade,km_atual) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (g.user['id'], year if year is not None else '', make, model, None, None, None,
                 placa, renavam, gv('condutor'), chassi, gv('licenciamento'), gv('ipva'), gv('combustivel'), gv('crv'), gv('crlv'), gv('seguro'), None, None, int(float(re.sub(r'[^\d.]','',gv('km_atual')))) if gv('km_atual') and re.sub(r'[^\d.]','',gv('km_atual')) else None))
            vd = gv('vistoria_data'); vv = gv('vistoria_validade')
            if vd or vv:
                conn.execute('INSERT INTO vistorias (car_id,vistoria_data,validade) VALUES (?,?,?)', (cur.lastrowid, vd or vv, vv or None))
            ok += 1
        except Exception as e:
            skipped += 1; errors.append(f'Linha {i}: {e}')
    conn.commit(); conn.close()
    return jsonify({'imported':ok,'skipped':skipped,'errors':errors[:20]})

@app.route('/api/cars/<int:cid>', methods=['GET'])
@login_required
def get_car(cid):
    conn = get_db()
    car = can_access_car(conn, cid, g.user)
    if not car:
        conn.close(); return jsonify({'error':'Não encontrado'}), 404
    car = dict(car)
    car['vistoria_data'], car['vistoria_validade'] = latest_vistoria(conn, cid, car.get('vistoria_data'), car.get('vistoria_validade'))
    conn.close()
    return jsonify(car)

@app.route('/api/cars/<int:cid>', methods=['PUT'])
@perm_required('can_edit_cars')
def update_car(cid):
    conn = get_db()
    car = can_access_car(conn, cid, g.user)
    if not car: conn.close(); return jsonify({'error':'Não encontrado'}), 404
    year=str(request.form.get('year',car['year']) or '').strip(); make=request.form.get('make',car['make']).strip()
    model=request.form.get('model',car['model']).strip(); vin=request.form.get('vin',car['vin'] or '').strip()
    pd=request.form.get('purchase_date',car['purchase_date'] or '').strip()
    placa=request.form.get('placa',car['placa'] or '').strip(); renavam=request.form.get('renavam',car['renavam'] or '').strip()
    condutor=request.form.get('condutor',car['condutor'] or '').strip(); chassi=request.form.get('chassi',car['chassi'] or '').strip()
    lic=request.form.get('licenciamento',car['licenciamento'] or '').strip(); ipva=request.form.get('ipva',car['ipva'] or '').strip()
    combustivel=request.form.get('combustivel',car['combustivel'] or '').strip(); crv=request.form.get('crv',car['crv'] or '').strip()
    crlv=request.form.get('crlv',car['crlv'] or '').strip(); seguro=request.form.get('seguro',car['seguro'] or '').strip()
    # Vistoria não faz mais parte do cadastro: fica no histórico (tabela vistorias)
    km=str(request.form.get('km_atual',car['km_atual'] if car['km_atual'] is not None else '')).strip()
    image = car['image']
    if 'image' in request.files and request.files['image'].filename:
        if car['image']:
            p = os.path.join(app.config['UPLOAD_FOLDER'],'cars',car['image'])
            if os.path.exists(p): os.remove(p)
        image = save_upload(request.files['image'],'cars')
    conn.execute('UPDATE cars SET year=?,make=?,model=?,vin=?,image=?,purchase_date=?,placa=?,renavam=?,condutor=?,chassi=?,licenciamento=?,ipva=?,combustivel=?,crv=?,crlv=?,seguro=?,vistoria_data=?,vistoria_validade=?,km_atual=? WHERE id=?',
                 (int(year) if year.isdigit() else None,make,model,vin or None,image,pd or None,placa or None,renavam or None,condutor or None,chassi or None,lic or None,ipva or None,combustivel or None,crv or None,crlv or None,seguro or None,car['vistoria_data'],car['vistoria_validade'],int(km) if km.isdigit() else None,cid))
    conn.commit()
    updated = dict(conn.execute('SELECT * FROM cars WHERE id=?',(cid,)).fetchone())
    updated['vistoria_data'], updated['vistoria_validade'] = latest_vistoria(conn, cid, updated.get('vistoria_data'), updated.get('vistoria_validade'))
    conn.close()
    return jsonify(updated)

@app.route('/api/cars/<int:cid>', methods=['DELETE'])
@perm_required('can_delete_cars')
def delete_car(cid):
    conn = get_db()
    car = can_access_car(conn, cid, g.user)
    if not car: conn.close(); return jsonify({'error':'Não encontrado'}), 404
    if car['image']:
        p = os.path.join(app.config['UPLOAD_FOLDER'],'cars',car['image'])
        if os.path.exists(p): os.remove(p)
    for img in conn.execute("SELECT mi.filename FROM maintenance_images mi JOIN maintenance m ON mi.maintenance_id=m.id WHERE m.car_id=?",(cid,)).fetchall():
        p = os.path.join(app.config['UPLOAD_FOLDER'],'maintenance',img['filename'])
        if os.path.exists(p): os.remove(p)
    for img in conn.execute("SELECT vi.filename FROM vistoria_images vi JOIN vistorias v ON vi.vistoria_id=v.id WHERE v.car_id=?",(cid,)).fetchall():
        p = os.path.join(app.config['UPLOAD_FOLDER'],'vistorias',img['filename'])
        if os.path.exists(p): os.remove(p)
    conn.execute('DELETE FROM cars WHERE id=?',(cid,)); conn.commit(); conn.close()
    return jsonify({'success':True})

# ── API de Manutenção ──────────────────────────────────
@app.route('/api/cars/<int:cid>/maintenance', methods=['GET'])
@login_required
def get_maintenance(cid):
    conn = get_db()
    car = can_access_car(conn, cid, g.user)
    if not car: conn.close(); return jsonify({'error':'Não encontrado'}), 404
    q=request.args.get('q','').strip(); sort=request.args.get('sort','date_desc')
    order = {'date_asc':'service_date ASC','cost_desc':'cost DESC','cost_asc':'cost ASC','odo_desc':'odometer DESC'}.get(sort,'service_date DESC')
    if q:
        entries = conn.execute(f"SELECT * FROM maintenance WHERE car_id=? AND (title LIKE ? OR maintenance_type LIKE ? OR parts_vendor LIKE ? OR notes LIKE ?) ORDER BY {order}",
            (cid,f'%{q}%',f'%{q}%',f'%{q}%',f'%{q}%')).fetchall()
    else:
        entries = conn.execute(f'SELECT * FROM maintenance WHERE car_id=? ORDER BY {order}',(cid,)).fetchall()
    result = []
    for e in entries:
        d = dict(e)
        d['images'] = [dict(i) for i in conn.execute('SELECT * FROM maintenance_images WHERE maintenance_id=? ORDER BY created_at',(d['id'],)).fetchall()]
        result.append(d)
    conn.close()
    return jsonify(result)

@app.route('/api/cars/<int:cid>/maintenance', methods=['POST'])
@perm_required('can_add_records')
def add_maintenance(cid):
    conn = get_db()
    car = can_access_car(conn, cid, g.user)
    if not car: conn.close(); return jsonify({'error':'Não encontrado'}), 404
    t=request.form.get('title','').strip(); mt=request.form.get('maintenance_type','').strip()
    sd=request.form.get('service_date','').strip(); odo=request.form.get('odometer','').strip()
    v=request.form.get('parts_vendor','').strip(); c=request.form.get('cost','').strip()
    n=request.form.get('notes','').strip(); drv=request.form.get('driver','').strip()
    if mt not in ('Repair','Maintenance','Upgrade','Inspection'): conn.close(); return jsonify({'error':'Tipo inválido'}), 400
    cur = conn.execute('INSERT INTO maintenance (car_id,title,maintenance_type,service_date,odometer,parts_vendor,cost,notes,driver) VALUES (?,?,?,?,?,?,?,?,?)',
        (cid,t,mt,sd,int(odo) if odo else None,v or None,float(c) if c else None,n or None,drv or None))
    mid = cur.lastrowid
    for f in request.files.getlist('gallery'):
        fn = save_upload(f,'maintenance')
        if fn: conn.execute('INSERT INTO maintenance_images (maintenance_id,filename,original_name,file_type) VALUES (?,?,?,?)',(mid,fn,f.filename,get_file_type(fn)))
    for f in request.files.getlist('documents'):
        fn = save_upload(f,'maintenance')
        if fn: conn.execute('INSERT INTO maintenance_images (maintenance_id,filename,original_name,file_type) VALUES (?,?,?,?)',(mid,fn,f.filename,'document'))
    reset_ids = reset_reminder_baselines(conn, cid, request.form.getlist('reset_reminders'),
                                         int(odo) if odo else None, sd)
    conn.commit()
    entry = dict(conn.execute('SELECT * FROM maintenance WHERE id=?',(mid,)).fetchone())
    entry['images'] = [dict(i) for i in conn.execute('SELECT * FROM maintenance_images WHERE maintenance_id=?',(mid,)).fetchall()]
    entry['reminders_reset'] = reset_ids
    conn.close()
    return jsonify(entry), 201

@app.route('/api/maintenance/<int:mid>', methods=['PUT'])
@perm_required('can_edit_records')
def update_maintenance(mid):
    conn = get_db()
    entry = conn.execute('SELECT * FROM maintenance WHERE id=?',(mid,)).fetchone()
    if not entry: conn.close(); return jsonify({'error':'Não encontrado'}), 404
    car = can_access_car(conn, entry['car_id'], g.user)
    if not car: conn.close(); return jsonify({'error':'Não encontrado'}), 404
    t=request.form.get('title',entry['title']).strip(); mt=request.form.get('maintenance_type',entry['maintenance_type']).strip()
    sd=request.form.get('service_date',entry['service_date']).strip(); odo=request.form.get('odometer','').strip()
    v=request.form.get('parts_vendor',entry['parts_vendor'] or '').strip(); c=request.form.get('cost','').strip()
    n=request.form.get('notes',entry['notes'] or '').strip(); drv=request.form.get('driver',entry['driver'] or '').strip()
    if mt not in ('Repair','Maintenance','Upgrade','Inspection'): conn.close(); return jsonify({'error':'Tipo inválido'}), 400
    conn.execute('UPDATE maintenance SET title=?,maintenance_type=?,service_date=?,odometer=?,parts_vendor=?,cost=?,notes=?,driver=? WHERE id=?',
        (t,mt,sd,int(odo) if odo else entry['odometer'],v or None,float(c) if c else entry['cost'],n or None,drv or None,mid))
    for f in request.files.getlist('gallery'):
        fn = save_upload(f,'maintenance')
        if fn: conn.execute('INSERT INTO maintenance_images (maintenance_id,filename,original_name,file_type) VALUES (?,?,?,?)',(mid,fn,f.filename,get_file_type(fn)))
    for f in request.files.getlist('documents'):
        fn = save_upload(f,'maintenance')
        if fn: conn.execute('INSERT INTO maintenance_images (maintenance_id,filename,original_name,file_type) VALUES (?,?,?,?)',(mid,fn,f.filename,'document'))
    conn.commit()
    updated = dict(conn.execute('SELECT * FROM maintenance WHERE id=?',(mid,)).fetchone())
    updated['images'] = [dict(i) for i in conn.execute('SELECT * FROM maintenance_images WHERE maintenance_id=?',(mid,)).fetchall()]
    conn.close()
    return jsonify(updated)

@app.route('/api/maintenance/<int:mid>', methods=['DELETE'])
@perm_required('can_delete_records')
def delete_maintenance(mid):
    conn = get_db()
    entry = conn.execute('SELECT * FROM maintenance WHERE id=?',(mid,)).fetchone()
    if not entry: conn.close(); return jsonify({'error':'Não encontrado'}), 404
    car = can_access_car(conn, entry['car_id'], g.user)
    if not car: conn.close(); return jsonify({'error':'Não encontrado'}), 404
    for img in conn.execute('SELECT filename FROM maintenance_images WHERE maintenance_id=?',(mid,)).fetchall():
        p = os.path.join(app.config['UPLOAD_FOLDER'],'maintenance',img['filename'])
        if os.path.exists(p): os.remove(p)
    conn.execute('DELETE FROM maintenance WHERE id=?',(mid,)); conn.commit(); conn.close()
    return jsonify({'success':True})

@app.route('/api/maintenance/<int:mid>/duplicate', methods=['POST'])
@perm_required('can_add_records')
def duplicate_maintenance(mid):
    conn = get_db()
    entry = conn.execute('SELECT * FROM maintenance WHERE id=?',(mid,)).fetchone()
    if not entry: conn.close(); return jsonify({'error':'Não encontrado'}), 404
    car = can_access_car(conn, entry['car_id'], g.user)
    if not car: conn.close(); return jsonify({'error':'Não encontrado'}), 404
    cur = conn.execute('INSERT INTO maintenance (car_id,title,maintenance_type,service_date,odometer,parts_vendor,cost,notes) VALUES (?,?,?,?,?,?,?,?)',
        (entry['car_id'],entry['title']+' (cópia)',entry['maintenance_type'],entry['service_date'],entry['odometer'],entry['parts_vendor'],entry['cost'],entry['notes']))
    conn.commit()
    new_entry = dict(conn.execute('SELECT * FROM maintenance WHERE id=?',(cur.lastrowid,)).fetchone())
    new_entry['images'] = []
    conn.close()
    return jsonify(new_entry), 201

@app.route('/api/maintenance/<int:mid>/images', methods=['POST'])
@perm_required('can_edit_records')
def add_maintenance_images(mid):
    conn = get_db()
    entry = conn.execute('SELECT car_id FROM maintenance WHERE id=?',(mid,)).fetchone()
    if not entry: conn.close(); return jsonify({'error':'Não encontrado'}), 404
    car = can_access_car(conn, entry['car_id'], g.user)
    if not car: conn.close(); return jsonify({'error':'Não encontrado'}), 404
    added = []
    for f in request.files.getlist('gallery'):
        fn = save_upload(f,'maintenance')
        if fn: conn.execute('INSERT INTO maintenance_images (maintenance_id,filename,original_name,file_type) VALUES (?,?,?,?)',(mid,fn,f.filename,get_file_type(fn))); added.append({'filename':fn,'original_name':f.filename,'file_type':'image'})
    for f in request.files.getlist('documents'):
        fn = save_upload(f,'maintenance')
        if fn: conn.execute('INSERT INTO maintenance_images (maintenance_id,filename,original_name,file_type) VALUES (?,?,?,?)',(mid,fn,f.filename,'document')); added.append({'filename':fn,'original_name':f.filename,'file_type':'document'})
    conn.commit(); conn.close()
    return jsonify(added), 201

@app.route('/api/maintenance/images/<int:iid>', methods=['DELETE'])
@perm_required('can_edit_records')
def delete_maintenance_image(iid):
    conn = get_db()
    img = conn.execute('SELECT * FROM maintenance_images WHERE id=?',(iid,)).fetchone()
    if not img: conn.close(); return jsonify({'error':'Não encontrado'}), 404
    p = os.path.join(app.config['UPLOAD_FOLDER'],'maintenance',img['filename'])
    if os.path.exists(p): os.remove(p)
    conn.execute('DELETE FROM maintenance_images WHERE id=?',(iid,)); conn.commit(); conn.close()
    return jsonify({'success':True})

@app.route('/api/maintenance/images/<int:iid>', methods=['PUT'])
@perm_required('can_edit_records')
def update_maintenance_image(iid):
    conn = get_db()
    img = conn.execute('SELECT mi.*, m.car_id FROM maintenance_images mi JOIN maintenance m ON mi.maintenance_id=m.id WHERE mi.id=?',(iid,)).fetchone()
    if not img: conn.close(); return jsonify({'error':'Não encontrado'}), 404
    if not can_access_car(conn, img['car_id'], g.user): conn.close(); return jsonify({'error':'Sem permissão'}), 403
    caption = (request.get_json(silent=True) or {}).get('caption')
    if caption is None: caption = request.form.get('caption','')
    caption = (caption or '').strip()[:500] or None
    conn.execute('UPDATE maintenance_images SET caption=? WHERE id=?',(caption,iid))
    conn.commit(); conn.close()
    return jsonify({'success':True,'caption':caption})

# ── API de Vistorias (histórico 1:N por veículo) ────────
@app.route('/api/cars/<int:cid>/vistorias', methods=['GET'])
@login_required
def get_vistorias(cid):
    conn = get_db()
    car = can_access_car(conn, cid, g.user)
    if not car: conn.close(); return jsonify({'error':'Não encontrado'}), 404
    rows = conn.execute('SELECT * FROM vistorias WHERE car_id=? ORDER BY vistoria_data DESC, id DESC',(cid,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d['images'] = [dict(i) for i in conn.execute('SELECT * FROM vistoria_images WHERE vistoria_id=? ORDER BY created_at',(d['id'],)).fetchall()]
        out.append(d)
    conn.close()
    return jsonify(out)

@app.route('/api/cars/<int:cid>/vistorias', methods=['POST'])
@perm_required('can_add_records')
def add_vistoria(cid):
    conn = get_db()
    car = can_access_car(conn, cid, g.user)
    if not car: conn.close(); return jsonify({'error':'Não encontrado'}), 404
    vd = request.form.get('vistoria_data','').strip()
    val = request.form.get('validade','').strip()
    obs = request.form.get('observacao','').strip()
    cur = conn.execute('INSERT INTO vistorias (car_id,vistoria_data,validade,observacao) VALUES (?,?,?,?)',
                       (cid, vd, val or None, obs or None))
    vid = cur.lastrowid
    for f in request.files.getlist('gallery'):
        fn = save_upload(f,'vistorias')
        if fn: conn.execute('INSERT INTO vistoria_images (vistoria_id,filename,original_name,file_type) VALUES (?,?,?,?)',
                            (vid,fn,f.filename,get_file_type(fn)))
    conn.commit()
    row = dict(conn.execute('SELECT * FROM vistorias WHERE id=?',(vid,)).fetchone())
    row['images'] = [dict(i) for i in conn.execute('SELECT * FROM vistoria_images WHERE vistoria_id=? ORDER BY created_at',(vid,)).fetchall()]
    conn.close()
    return jsonify(row), 201

@app.route('/api/vistorias/<int:vid>', methods=['DELETE'])
@perm_required('can_delete_records')
def delete_vistoria(vid):
    conn = get_db()
    v = conn.execute('SELECT * FROM vistorias WHERE id=?',(vid,)).fetchone()
    if not v: conn.close(); return jsonify({'error':'Não encontrado'}), 404
    if not can_access_car(conn, v['car_id'], g.user): conn.close(); return jsonify({'error':'Sem permissão'}), 403
    for img in conn.execute('SELECT filename FROM vistoria_images WHERE vistoria_id=?',(vid,)).fetchall():
        p = os.path.join(app.config['UPLOAD_FOLDER'],'vistorias',img['filename'])
        if os.path.exists(p): os.remove(p)
    conn.execute('DELETE FROM vistorias WHERE id=?',(vid,)); conn.commit(); conn.close()
    return jsonify({'success':True})

@app.route('/api/vistoria/images/<int:iid>', methods=['DELETE'])
@perm_required('can_delete_records')
def delete_vistoria_image(iid):
    conn = get_db()
    img = conn.execute('SELECT vi.*, v.car_id FROM vistoria_images vi JOIN vistorias v ON vi.vistoria_id=v.id WHERE vi.id=?',(iid,)).fetchone()
    if not img: conn.close(); return jsonify({'error':'Não encontrado'}), 404
    if not can_access_car(conn, img['car_id'], g.user): conn.close(); return jsonify({'error':'Sem permissão'}), 403
    p = os.path.join(app.config['UPLOAD_FOLDER'],'vistorias',img['filename'])
    if os.path.exists(p): os.remove(p)
    conn.execute('DELETE FROM vistoria_images WHERE id=?',(iid,)); conn.commit(); conn.close()
    return jsonify({'success':True})

@app.route('/api/vistoria/images/<int:iid>', methods=['PUT'])
@perm_required('can_edit_records')
def update_vistoria_image(iid):
    conn = get_db()
    img = conn.execute('SELECT vi.*, v.car_id FROM vistoria_images vi JOIN vistorias v ON vi.vistoria_id=v.id WHERE vi.id=?',(iid,)).fetchone()
    if not img: conn.close(); return jsonify({'error':'Não encontrado'}), 404
    if not can_access_car(conn, img['car_id'], g.user): conn.close(); return jsonify({'error':'Sem permissão'}), 403
    caption = (request.get_json(silent=True) or {}).get('caption')
    if caption is None: caption = request.form.get('caption','')
    caption = (caption or '').strip()[:500] or None
    conn.execute('UPDATE vistoria_images SET caption=? WHERE id=?',(caption,iid))
    conn.commit(); conn.close()
    return jsonify({'success':True,'caption':caption})

# ── Lembretes de Serviço ───────────────────────────────
@app.route('/api/cars/<int:cid>/reminders', methods=['GET'])
@login_required
def get_reminders(cid):
    conn = get_db()
    car = can_access_car(conn, cid, g.user)
    if not car: conn.close(); return jsonify({'error':'Não encontrado'}), 404
    rows = conn.execute('SELECT * FROM service_reminders WHERE car_id=? ORDER BY title', (cid,)).fetchall()
    out = [reminder_status(conn, r) for r in rows]
    conn.close()
    # mais próximos primeiro, com qualquer um sem baseline por último
    out.sort(key=reminder_sort_key)
    return jsonify(out)

@app.route('/api/cars/<int:cid>/reminders', methods=['POST'])
@perm_required('can_add_records')
def add_reminder(cid):
    conn = get_db()
    car = can_access_car(conn, cid, g.user)
    if not car: conn.close(); return jsonify({'error':'Não encontrado'}), 404
    f, err = parse_reminder_input(request.get_json(silent=True) or request.form)
    if err: conn.close(); return jsonify({'error': err}), 400
    cur = conn.execute('INSERT INTO service_reminders (car_id,title,interval_type,interval_miles,interval_months,last_done_odometer,last_done_date,notes)'
                       ' VALUES (?,?,?,?,?,?,?,?)',
                       (cid, f['title'], f['interval_type'], f['interval_miles'], f['interval_months'],
                        f['last_done_odometer'], f['last_done_date'], f['notes']))
    conn.commit()
    row = conn.execute('SELECT * FROM service_reminders WHERE id=?', (cur.lastrowid,)).fetchone()
    out = reminder_status(conn, row)
    conn.close()
    return jsonify(out), 201

@app.route('/api/reminders/<int:rid>', methods=['PUT'])
@perm_required('can_edit_records')
def update_reminder(rid):
    conn = get_db()
    rem = conn.execute('SELECT * FROM service_reminders WHERE id=?', (rid,)).fetchone()
    if not rem: conn.close(); return jsonify({'error':'Não encontrado'}), 404
    if not can_access_car(conn, rem['car_id'], g.user): conn.close(); return jsonify({'error':'Não encontrado'}), 404
    f, err = parse_reminder_input(request.get_json(silent=True) or request.form, rem)
    if err: conn.close(); return jsonify({'error': err}), 400
    conn.execute('UPDATE service_reminders SET title=?,interval_type=?,interval_miles=?,interval_months=?,'
                 'last_done_odometer=?,last_done_date=?,notes=? WHERE id=?',
                 (f['title'], f['interval_type'], f['interval_miles'], f['interval_months'],
                  f['last_done_odometer'], f['last_done_date'], f['notes'], rid))
    conn.commit()
    row = conn.execute('SELECT * FROM service_reminders WHERE id=?', (rid,)).fetchone()
    out = reminder_status(conn, row)
    conn.close()
    return jsonify(out)

@app.route('/api/reminders/<int:rid>', methods=['DELETE'])
@perm_required('can_delete_records')
def delete_reminder(rid):
    conn = get_db()
    rem = conn.execute('SELECT * FROM service_reminders WHERE id=?', (rid,)).fetchone()
    if not rem: conn.close(); return jsonify({'error':'Não encontrado'}), 404
    if not can_access_car(conn, rem['car_id'], g.user): conn.close(); return jsonify({'error':'Não encontrado'}), 404
    conn.execute('DELETE FROM service_reminders WHERE id=?', (rid,))
    conn.commit(); conn.close()
    return jsonify({'success': True})

@app.route('/api/reminders/upcoming')
@login_required
def upcoming_reminders():
    """Todos os lembretes dos veículos que este usuário pode ver, do mais próximo ao mais distante."""
    conn = get_db()
    if g.user['role'] == 'admin':
        cars = conn.execute('SELECT * FROM cars').fetchall()
    else:
        cars = conn.execute('SELECT * FROM cars WHERE user_id=?', (g.user['id'],)).fetchall()
    out = []
    for car in cars:
        odo = conn.execute('SELECT MAX(odometer) AS o FROM maintenance WHERE car_id=?', (car['id'],)).fetchone()
        current = odo['o'] if odo and odo['o'] is not None else None
        for r in conn.execute('SELECT * FROM service_reminders WHERE car_id=?', (car['id'],)).fetchall():
            d = reminder_status(conn, r, current)
            d['car_name'] = f"{car['year']} {car['make']} {car['model']}"
            out.append(d)
    conn.close()
    out.sort(key=reminder_sort_key)
    return jsonify({
        'reminders': out,
        'overdue': sum(1 for r in out if r['status'] == 'overdue'),
        'due_soon': sum(1 for r in out if r['status'] == 'due_soon'),
    })

# ── Exportação CSV ─────────────────────────────────────
@app.route('/api/cars/<int:cid>/export')
@perm_required('can_export')
def export_csv(cid):
    conn = get_db()
    car = can_access_car(conn, cid, g.user)
    if not car: conn.close(); return jsonify({'error':'Não encontrado'}), 404
    entries = conn.execute('SELECT * FROM maintenance WHERE car_id=? ORDER BY service_date DESC',(cid,)).fetchall()
    conn.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Título','Tipo','Data do serviço','Odômetro','Fornecedor','Custo','Observações'])
    for e in entries:
        writer.writerow([e['title'],MAINT_TYPE_PT.get(e['maintenance_type'],e['maintenance_type']),e['service_date'],e['odometer'] or '',e['parts_vendor'] or '',e['cost'] or '',e['notes'] or ''])
    fname = f"{car['year']}_{car['make']}_{car['model']}_maintenance.csv".replace(' ','_')
    return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition':f'attachment; filename="{fname}"'})

# ── Importação CSV (admin + editors com permissão) ─────
@app.route('/api/import/preview', methods=['POST'])
@perm_required('can_import')
def csv_preview():
    if 'file' not in request.files: return jsonify({'error':'Nenhum CSV enviado'}), 400
    file = request.files['file']
    if not file.filename.lower().endswith('.csv'): return jsonify({'error':'Deve ser .csv'}), 400
    mapping_raw = request.form.get('mapping','{}')
    car_id = request.form.get('car_id','')
    try: mapping = json.loads(mapping_raw)
    except: return jsonify({'error':'Mapeamento inválido'}), 400
    conn = get_db()
    car = can_access_car(conn, car_id, g.user)
    conn.close()
    if not car: return jsonify({'error':'Veículo não encontrado'}), 404
    try:
        raw = file.read()
        try: text = raw.decode('utf-8-sig')
        except: text = raw.decode('latin-1')
        reader = csv.DictReader(io.StringIO(text))
        csv_headers = reader.fieldnames or []
    except Exception as e: return jsonify({'error':f'Erro ao analisar: {e}'}), 400
    if not csv_headers: return jsonify({'error':'Sem cabeçalhos'}), 400
    if not mapping or all(v=='' for v in mapping.values()):
        return jsonify({'csv_headers':csv_headers,'row_count':sum(1 for _ in reader),'target_car':dict(car),'preview_rows':[],'errors':[],'valid_count':0})
    db_fields = ['title','maintenance_type','service_date','odometer','parts_vendor','cost','notes']
    field_map = {db_f:csv_c for csv_c,db_f in mapping.items() if db_f in db_fields}
    missing=[]
    if 'title' not in field_map: missing.append('Título')
    if 'service_date' not in field_map: missing.append('Data do serviço')
    if missing: return jsonify({'error':f'Obrigatórios: {", ".join(missing)}'}), 400
    valid_types = {'Repair','Maintenance','Upgrade','Inspection'}
    type_map = {'repair':'Repair','maintenance':'Maintenance','upgrade':'Upgrade','service':'Maintenance','mod':'Upgrade','modification':'Upgrade','fix':'Repair','maint':'Maintenance','inspection':'Inspection','inspect':'Inspection',
                'manutencao':'Maintenance','manutenção':'Maintenance','serviço':'Maintenance','servico':'Maintenance','reparo':'Repair','reparação':'Repair','reparacao':'Repair','melhoria':'Upgrade','melhorias':'Upgrade','inspecao':'Inspection','inspeção':'Inspection','vistoria':'Inspection','vistorias':'Inspection'}
    preview_rows=[]; errors=[]; valid_count=0
    file.seek(0)
    try:
        raw=file.read()
        try: text=raw.decode('utf-8-sig')
        except: text=raw.decode('latin-1')
        reader=csv.DictReader(io.StringIO(text))
    except: return jsonify({'error':'Falha ao reler o arquivo'}), 400
    for rn,row in enumerate(reader,start=2):
        rec={}; errs=[]
        tv = row.get(field_map.get('title',''),'').strip()
        if not tv: errs.append('Título vazio')
        rec['title']=tv
        if 'maintenance_type' in field_map:
            rt = row.get(field_map['maintenance_type'],'').strip()
            n = type_map.get(rt.lower(),rt)
            if n not in valid_types:
                if rt: errs.append(f'Tipo desconhecido "{rt}"')
                n='Maintenance'
            rec['maintenance_type']=n
        else: rec['maintenance_type']='Maintenance'
        if 'service_date' in field_map:
            rd = row.get(field_map['service_date'],'').strip()
            pd = _parse_date(rd)
            if not pd: errs.append(f'Data inválida "{rd}"')
            rec['service_date']=pd or rd
        else: rec['service_date']=''; errs.append('Data vazia')
        if 'odometer' in field_map:
            ro = re.sub(r'[^\d.]','',row.get(field_map['odometer'],'').strip())
            if ro:
                try: rec['odometer']=int(float(ro))
                except: errs.append('Odômetro inválido'); rec['odometer']=None
            else: rec['odometer']=None
        else: rec['odometer']=None
        rec['parts_vendor']=row.get(field_map.get('parts_vendor',''),'').strip() or None
        if 'cost' in field_map:
            rc = re.sub(r'[^\d.]','',row.get(field_map['cost'],'').strip())
            if rc:
                try: rec['cost']=round(float(rc),2)
                except: errs.append('Custo inválido'); rec['cost']=None
            else: rec['cost']=None
        else: rec['cost']=None
        rec['notes']=row.get(field_map.get('notes',''),'').strip() or None
        crit = any('vazi' in e.lower() or 'data inválida' in e.lower() for e in errs)
        rec['_row_num']=rn; rec['_errors']=errs; rec['_valid']=not crit
        if rec['_valid']: valid_count+=1
        preview_rows.append(rec)
        for e in errs: errors.append(f'Linha {rn}: {e}')
    return jsonify({'csv_headers':csv_headers,'row_count':len(preview_rows),'target_car':dict(car),'preview_rows':preview_rows,'errors':errors,'valid_count':valid_count})

@app.route('/api/import/commit', methods=['POST'])
@perm_required('can_import')
def csv_commit():
    data = request.get_json() or {}
    car_id=data.get('car_id'); rows=data.get('rows',[])
    conn = get_db()
    car = can_access_car(conn, car_id, g.user)
    if not car: conn.close(); return jsonify({'error':'Não encontrado'}), 404
    imported=0; skipped=0
    for r in rows:
        if not r.get('_valid'): skipped+=1; continue
        t=r.get('title','').strip(); mt=r.get('maintenance_type','Maintenance'); sd=r.get('service_date','').strip()
        if not t or not sd: skipped+=1; continue
        if mt not in ('Repair','Maintenance','Upgrade','Inspection'): mt='Maintenance'
        conn.execute('INSERT INTO maintenance (car_id,title,maintenance_type,service_date,odometer,parts_vendor,cost,notes) VALUES (?,?,?,?,?,?,?,?)',
            (car_id,t,mt,sd,r.get('odometer'),r.get('parts_vendor'),r.get('cost'),r.get('notes')))
        imported+=1
    conn.commit(); conn.close()
    return jsonify({'imported':imported,'skipped':skipped})

def _parse_date(raw):
    if not raw: return None
    raw=raw.strip()
    if re.match(r'^\d{4}-\d{2}-\d{2}$',raw): return raw
    m=re.match(r'^(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})$',raw)
    if m: return f'{m.group(3)}-{m.group(1).zfill(2)}-{m.group(2).zfill(2)}'
    m=re.match(r'^(\d{4})[/](\d{1,2})[/](\d{1,2})$',raw)
    if m: return f'{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}'
    try:
        from datetime import datetime as dt
        for fmt in ('%b %d, %Y','%B %d, %Y','%b %d %Y','%B %d %Y','%d %b %Y','%d %B %Y'):
            try: return dt.strptime(raw,fmt).strftime('%Y-%m-%d')
            except ValueError: continue
    except: pass
    return None

# ── Estatísticas do Painel (por usuário) ───────────────

@app.route('/api/cars/<int:cid>/fuelups', methods=['GET'])
def get_fuelups(cid):
    conn = get_db()
    car = can_access_car(conn, cid, g.user)
    if not car: conn.close(); return jsonify({'error':'Não encontrado'}), 404
    rows = conn.execute('SELECT * FROM fuelups WHERE car_id=? ORDER BY fuel_date DESC', (cid,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/cars/<int:cid>/fuelups', methods=['POST'])
@perm_required('can_add_records')
def add_fuelup(cid):
    conn = get_db()
    car = can_access_car(conn, cid, g.user)
    if not car: conn.close(); return jsonify({'error':'Não encontrado'}), 404
    d = request.form.get('fuel_date','').strip(); lit = request.form.get('liters','').strip()
    pr = request.form.get('price','').strip(); odo = request.form.get('odometer','').strip()
    v = request.form.get('parts_vendor','').strip(); drv = request.form.get('driver','').strip()
    n = request.form.get('notes','').strip()
    cur = conn.execute('INSERT INTO fuelups (car_id,fuel_date,liters,price,odometer,parts_vendor,driver,notes) VALUES (?,?,?,?,?,?,?,?)',
        (cid,d,float(lit) if lit else None,float(pr) if pr else None,int(odo) if odo else None,v or None,drv or None,n or None))
    conn.commit()
    row = dict(conn.execute('SELECT * FROM fuelups WHERE id=?',(cur.lastrowid,)).fetchone())
    conn.close()
    return jsonify(row), 201

@app.route('/api/fuelups/<int:fid>', methods=['DELETE'])
def delete_fuelup(fid):
    conn = get_db()
    row = conn.execute('SELECT * FROM fuelups WHERE id=?',(fid,)).fetchone()
    if not row: conn.close(); return jsonify({'error':'Não encontrado'}), 404
    if not can_access_car(conn, row['car_id'], g.user): conn.close(); return jsonify({'error':'Sem permissão'}), 403
    conn.execute('DELETE FROM fuelups WHERE id=?',(fid,)); conn.commit(); conn.close()
    return jsonify({'ok':True})

@app.route('/api/cars/<int:cid>/infractions', methods=['GET'])
def get_infractions(cid):
    conn = get_db()
    car = can_access_car(conn, cid, g.user)
    if not car: conn.close(); return jsonify({'error':'Não encontrado'}), 404
    rows = conn.execute('SELECT * FROM infractions WHERE car_id=? ORDER BY infraction_date DESC', (cid,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/cars/<int:cid>/infractions', methods=['POST'])
@perm_required('can_add_records')
def add_infraction(cid):
    conn = get_db()
    car = can_access_car(conn, cid, g.user)
    if not car: conn.close(); return jsonify({'error':'Não encontrado'}), 404
    d = request.form.get('infraction_date','').strip(); desc = request.form.get('description','').strip()
    val = request.form.get('value','').strip(); pts = request.form.get('points','').strip()
    st = request.form.get('status','Pendente').strip(); n = request.form.get('notes','').strip()
    if st not in ('Pendente','Paga','Recorrida','Cancelada'): st = 'Pendente'
    cur = conn.execute('INSERT INTO infractions (car_id,infraction_date,description,value,points,status,notes) VALUES (?,?,?,?,?,?,?)',
        (cid,d,desc or None,float(val) if val else None,int(pts) if pts else None,st,n or None))
    conn.commit()
    row = dict(conn.execute('SELECT * FROM infractions WHERE id=?',(cur.lastrowid,)).fetchone())
    conn.close()
    return jsonify(row), 201

@app.route('/api/infractions/<int:iid>', methods=['DELETE'])
def delete_infraction(iid):
    conn = get_db()
    row = conn.execute('SELECT * FROM infractions WHERE id=?',(iid,)).fetchone()
    if not row: conn.close(); return jsonify({'error':'Não encontrado'}), 404
    if not can_access_car(conn, row['car_id'], g.user): conn.close(); return jsonify({'error':'Sem permissão'}), 403
    conn.execute('DELETE FROM infractions WHERE id=?',(iid,)); conn.commit(); conn.close()
    return jsonify({'ok':True})

@app.route('/api/alerts')
def get_alerts():
    from datetime import date as _date
    conn = get_db()
    if g.user['role'] == 'admin':
        cars = conn.execute('SELECT * FROM cars').fetchall()
    else:
        cars = conn.execute('SELECT * FROM cars WHERE user_id=?', (g.user['id'],)).fetchall()
    labels = [('licenciamento','Licenciamento'),('ipva','IPVA'),('crlv','CRLV'),('seguro','Seguro'),('vistoria_validade','Vistoria')]
    today = _date.today()
    alerts = []
    for c in cars:
        vist_validade = latest_vistoria(conn, c['id'], c['vistoria_data'], c['vistoria_validade'])[1]
        for key, label in labels:
            v = vist_validade if key == 'vistoria_validade' else c[key]
            if not v: continue
            try: delta = (_date.fromisoformat(v) - today).days
            except ValueError: continue
            if delta < 0:
                alerts.append({'car': f"{c['year']} {c['make']} {c['model']}", 'car_id': c['id'], 'item': label, 'date': v, 'level': 'vencido', 'days': delta})
            elif delta <= 30:
                alerts.append({'car': f"{c['year']} {c['make']} {c['model']}", 'car_id': c['id'], 'item': label, 'date': v, 'level': 'vence_em_breve', 'days': delta})
    alerts.sort(key=lambda a: a['days'])
    conn.close()
    return jsonify(alerts)

@app.route('/api/fleet/report')
def fleet_report():
    conn = get_db()
    if g.user['role'] == 'admin':
        cars = conn.execute('SELECT * FROM cars').fetchall()
    else:
        cars = conn.execute('SELECT * FROM cars WHERE user_id=?', (g.user['id'],)).fetchall()
    rows = []
    for c in cars:
        m = conn.execute('SELECT COUNT(*) as n, COALESCE(SUM(cost),0) as t FROM maintenance WHERE car_id=?', (c['id'],)).fetchone()
        f = conn.execute('SELECT COUNT(*) as n, COALESCE(SUM(price),0) as t FROM fuelups WHERE car_id=?', (c['id'],)).fetchone()
        i = conn.execute("SELECT COUNT(*) as n, COALESCE(SUM(value),0) as t FROM infractions WHERE car_id=? AND status='Pendente'", (c['id'],)).fetchone()
        rows.append({'car_id': c['id'], 'car': f"{c['year']} {c['make']} {c['model']}", 'placa': c['placa'],
                     'maintenance_count': m['n'], 'maintenance_cost': m['t'],
                     'fuelups': f['n'], 'fuel_cost': f['t'],
                     'infractions_open': i['n'], 'infractions_value': i['t'],
                     'total_cost': m['t'] + f['t']})
    conn.close()
    return jsonify(rows)

@app.route('/api/export/fleet')
def export_fleet():
    import csv, io as _io
    conn = get_db()
    if g.user['role'] == 'admin':
        cars = conn.execute('SELECT * FROM cars ORDER BY created_at DESC').fetchall()
    else:
        cars = conn.execute('SELECT * FROM cars WHERE user_id=? ORDER BY created_at DESC', (g.user['id'],)).fetchall()
    out = _io.StringIO()
    w = csv.writer(out)
    w.writerow(['Ano','Marca','Modelo','Placa','Combustível','KM Atual','Licenciamento','IPVA','CRLV','Seguro','Vistoria','Gasto Manutenção','Gasto Combustível','Infrações Abertas'])
    for c in cars:
        m = conn.execute('SELECT COALESCE(SUM(cost),0) as t FROM maintenance WHERE car_id=?', (c['id'],)).fetchone()['t']
        f = conn.execute('SELECT COALESCE(SUM(price),0) as t FROM fuelups WHERE car_id=?', (c['id'],)).fetchone()['t']
        inf = conn.execute("SELECT COUNT(*) as n FROM infractions WHERE car_id=? AND status='Pendente'", (c['id'],)).fetchone()['n']
        w.writerow([c['year'],c['make'],c['model'],c['placa'] or '',c['combustivel'] or '',c['km_atual'] if c['km_atual'] is not None else '',c['licenciamento'] or '',c['ipva'] or '',c['crlv'] or '',c['seguro'] or '',latest_vistoria(conn, c['id'], c['vistoria_data'], c['vistoria_validade'])[1] or '',m,f,inf])
    conn.close()
    return Response(out.getvalue(), mimetype='text/csv', headers={'Content-Disposition':'attachment; filename=frota.csv'})

@app.route('/api/stats')
@login_required
def get_stats():
    range_filter = request.args.get('range','all')
    conn = get_db()
    date_clause = ''
    if range_filter=='month': date_clause="AND m.service_date >= date('now','start of month')"
    elif range_filter=='year': date_clause="AND m.service_date >= date('now','start of year')"
    if g.user['role'] == 'admin':
        tc = conn.execute('SELECT COUNT(*) as c FROM cars').fetchone()['c']
        tm = conn.execute(f'SELECT COUNT(*) as c FROM maintenance m {date_clause.replace("AND","WHERE",1) if date_clause else ""}').fetchone()['c']
        cost = conn.execute(f'SELECT COALESCE(SUM(m.cost),0) as c FROM maintenance m {date_clause.replace("AND","WHERE",1) if date_clause else ""}').fetchone()['c']
        recent = conn.execute("SELECT m.*, c.year, c.make, c.model FROM maintenance m JOIN cars c ON m.car_id=c.id ORDER BY m.created_at DESC LIMIT 5").fetchall()
    else:
        tc = conn.execute('SELECT COUNT(*) as c FROM cars WHERE user_id=?',(g.user['id'],)).fetchone()['c']
        tm = conn.execute(f'SELECT COUNT(*) as c FROM maintenance m JOIN cars c ON m.car_id=c.id WHERE c.user_id=? {date_clause}',(g.user['id'],)).fetchone()['c']
        cost = conn.execute(f'SELECT COALESCE(SUM(m.cost),0) as c FROM maintenance m JOIN cars c ON m.car_id=c.id WHERE c.user_id=? {date_clause}',(g.user['id'],)).fetchone()['c']
        recent = conn.execute("SELECT m.*, c.year, c.make, c.model FROM maintenance m JOIN cars c ON m.car_id=c.id WHERE c.user_id=? ORDER BY m.created_at DESC LIMIT 5",(g.user['id'],)).fetchall()
    conn.close()
    return jsonify({'total_cars':tc,'total_maintenance':tm,'total_cost':round(cost,2),'recent_entries':[dict(r) for r in recent]})

init_db()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
