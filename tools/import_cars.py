import re, sqlite3, openpyxl

wb = openpyxl.load_workbook('ativos.xlsx', data_only=True)
ws = wb.active
rows = list(ws.iter_rows(min_row=2, values_only=True))
headers = [c[0] for c in ws.iter_rows(min_row=1, max_row=1)] if False else None

def clean(v):
    if v is None: return None
    s = str(v).strip()
    if s in ('-', '--', ' - ', '') or s.lower() in (' - ', 'nan'): return None
    return s

def num_or_none(v):
    if isinstance(v, (int, float)) and v: return int(v)
    s = clean(v)
    if s and s.replace('.','').isdigit() and s != '0': return int(float(s))
    return None

def split_make_model(mmv):
    s = str(mmv).strip()
    s = re.sub(r'\s*-\s*[Pp]laca.*$', '', s)  # remove " - Placa XYZ"
    s = re.sub(r'\s*[Pp]laca\s*[A-Z0-9]{7}\s*$', '', s)
    s = s.strip().strip('-').strip()
    if '/' in s:
        parts = [p.strip() for p in s.split('/', 1)]
        return parts[0], parts[1]
    # sem barra: primeira palavra = marca
    parts = s.split(None, 1)
    return (parts[0], parts[1] if len(parts) > 1 else parts[0])

con = sqlite3.connect('garage_logbook.db')
inserted = 0
for r in rows:
    (idv, ativo, filial, uf, mmv, renavam, mercosul, placa, condutor, ano_f, ano_m, crv, cor, chassi) = r
    if clean(placa) is None and clean(mmv) is None:
        continue
    make, model = split_make_model(mmv)
    year = num_or_none(ano_f) or num_or_none(ano_m)
    ren = str(int(renavam)) if isinstance(renavam, (int, float)) else clean(renavam)
    placa_s = clean(placa)
    cond = clean(condutor)
    chassi_s = clean(chassi)
    if chassi_s: chassi_s = chassi_s.strip()
    crv_s = str(int(crv)) if isinstance(crv, (int, float)) and crv else clean(crv)
    if crv_s in ('0',): crv_s = None
    con.execute(
        'INSERT INTO cars (user_id,year,make,model,vin,image,purchase_date,placa,renavam,condutor,chassi,licenciamento,ipva,combustivel,crv,crlv,seguro,vistoria_data,vistoria_validade,km_atual) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
        (1, year if year is not None else '', make, model, None, None, None,
         placa_s, ren, cond, chassi_s, None, None, None, crv_s, None, None, None, None, None))
    inserted += 1
con.commit()
print('inseridos:', inserted)
for c in con.execute('select year,make,model,placa,renavam,condutor,chassi,crv from cars order by id'):
    print(c)
