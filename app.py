from flask import Flask, request, jsonify, Response
import csv, re, io, os
from datetime import datetime

app = Flask(__name__)
shared_data = {'rows':[],'uploaded_by':'','uploaded_at':'','track_file':'','order_file':''}

TIS620_MAP=[8364,65533,65533,65533,65533,8230,65533,65533,65533,65533,65533,65533,65533,65533,65533,65533,65533,8216,8217,8220,8221,8226,8211,8212,65533,65533,65533,65533,65533,65533,65533,65533,160,3585,3586,3587,3588,3589,3590,3591,3592,3593,3594,3595,3596,3597,3598,3599,3600,3601,3602,3603,3604,3605,3606,3607,3608,3609,3610,3611,3612,3613,3614,3615,3616,3617,3618,3619,3620,3621,3622,3623,3624,3625,3626,3627,3628,3629,3630,3631,3632,3633,3634,3635,3636,3637,3638,3639,3640,3641,3642,65533,65533,65533,65533,3647,3648,3649,3650,3651,3652,3653,3654,3655,3656,3657,3658,3659,3660,3661,3662,3663,3664,3665,3666,3667,3668,3669,3670,3671,3672,3673,3674,3675,65533,65533,65533,65533]

def decode_tis620(b):
    return ''.join(chr(x) if x<0x80 else chr(TIS620_MAP[x-0x80]) for x in b)

def read_csv_bytes(b):
    for enc in ['utf-8-sig', None, 'tis-620', 'latin-1']:
        try:
            t = decode_tis620(b) if enc is None else b.decode(enc)
            r = list(csv.DictReader(io.StringIO(t)))
            if r: return r
        except: pass
    return list(csv.DictReader(io.StringIO(b.decode('latin-1'))))

def fc(cols, pats):
    for p in pats:
        f=next((c for c in cols if c.replace(' ','').lower()==p.replace(' ','').lower()),None)
        if f: return f
    for p in pats:
        f=next((c for c in cols if p.lower() in c.lower()),None)
        if f: return f
    return None

def detect_carrier(t):
    t=str(t).strip().upper()
    if not t or t in('','NAN','-','NONE'): return {'name':'','short':'','url':''}
    if re.match(r'^668\d{11}$',t): return {'name':'Best Express','short':'BEST','url':f'https://track.best-express.com/tracking?trackingNumber={t}&language=TH'}
    if re.match(r'^TH\d{16}$',t) or re.match(r'^\d{18}$',t): return {'name':'Flash Express','short':'FLASH','url':f'https://www.flashexpress.co.th/tracking/?se={t}'}
    if re.match(r'^800\d{9}$',t): return {'name':'J&T Express','short':'J&T','url':f'https://www.jtexpress.co.th/index/query/gzquery.html?bills={t}'}
    if re.match(r'^NIM',t): return {'name':'Nim Express','short':'NIM','url':f'https://nimexpress.com/web/tracking?trackNo={t}'}
    if re.match(r'^(EH|RH|RE|EO|RP|RR)\d+TH$',t): return {'name':'ไปรษณีย์ไทย','short':'THPOST','url':f'https://track.thailandpost.co.th/?trackNumber={t}'}
    if re.match(r'^KY',t): return {'name':'Kerry','short':'KERRY','url':f'https://th.kerryexpress.com/th/track/?track={t}'}
    return {'name':'อื่นๆ','short':'OTHER','url':''}

def process_data(track_rows, order_rows=None):
    if not track_rows: return []
    tc=list(track_rows[0].keys())
    tOid=fc(tc,['Order ID','OrderID']) or tc[1]
    tBrand=fc(tc,['แบรนด์','brand']) or tc[4]
    tTrack=fc(tc,['Tracking','tracking']) or tc[-1]
    tConsign=fc(tc,['consign','เลข consign']) or tc[2]
    tQty=fc(tc,['Qty.','Qty','qty']) or tc[5]

    tm={}
    for row in track_rows:
        oid=str(row.get(tOid,'')).strip()
        brand=str(row.get(tBrand,''))
        tracking=str(row.get(tTrack,'')).strip()
        consign=str(row.get(tConsign,'')).strip()
        if not oid: continue
        skus=re.findall(r'\(([A-Z]{2,3}\d+)\)',brand.replace('\n',' '))
        if oid not in tm: tm[oid]={}
        if skus:
            for s in skus: tm[oid][s]={'tracking':tracking,'consign':consign}
        elif '__nosku' not in tm[oid]:
            tm[oid]['__nosku']={'tracking':tracking,'consign':consign}

    rows=[]
    if order_rows:
        oc=list(order_rows[0].keys())
        oOid=fc(oc,['Order ID','OrderID']) or oc[2]
        oSku=fc(oc,['SkU','SKU','sku']) or oc[3]
        oBrand=fc(oc,['แบรนด์','brand']) or oc[4]
        oSize=fc(oc,['ขนาด','size']) or oc[5]
        oQty=fc(oc,['SUM of','SUM','sum','Qty']) or oc[-1]
        for row in order_rows:
            oid=str(row.get(oOid,'')).strip()
            sku=str(row.get(oSku,'')).strip()
            brand=str(row.get(oBrand,'')).strip()
            size=str(row.get(oSize,'')) if str(row.get(oSize,'')) not in ('','nan','None') else ''
            try: qty=int(float(str(row.get(oQty,1))))
            except: qty=1
            is_gift=brand.startswith('แถม')
            t=(tm.get(oid,{}).get(sku) or tm.get(oid,{}).get('__nosku') or {'tracking':'','consign':''})
            carrier=detect_carrier(t['tracking'])
            rows.append({'oid':oid,'sku':sku,'brand':brand,'size':size,'qty':qty,'consign':t['consign'],'tracking':t['tracking'],'carrier':carrier,'is_gift':is_gift})
    else:
        for row in track_rows:
            oid=str(row.get(tOid,'')).strip()
            brand=str(row.get(tBrand,''))
            tracking=str(row.get(tTrack,'')).strip()
            consign=str(row.get(tConsign,'')).strip()
            try: qty=int(float(str(row.get(tQty,1))))
            except: qty=1
            carrier=detect_carrier(tracking)
            for line in [l.strip() for l in brand.split('\n') if l.strip()]:
                sm=re.search(r'\(([A-Z]{2,3}\d+)\)',line)
                sku=sm.group(1) if sm else ''
                name=re.sub(r'\s*\(.*?\)','',line).lstrip('แถม').strip(' -–')
                is_gift=line.strip().startswith('แถม')
                rows.append({'oid':oid,'sku':sku,'brand':name,'size':'','qty':qty,'consign':consign,'tracking':tracking,'carrier':carrier,'is_gift':is_gift})
    return rows

@app.route('/')
def index():
    has_data=len(shared_data['rows'])>0
    html=HTML_PAGE.replace('__STATUS_CLASS__','' if has_data else 'hidden')
    html=html.replace('__UPLOADED_BY__',shared_data['uploaded_by'])
    html=html.replace('__UPLOADED_AT__',shared_data['uploaded_at'])
    html=html.replace('__TRACK_FILE__',shared_data['track_file'])
    html=html.replace('__ORDER_FILE__',shared_data['order_file'])
    return Response(html,mimetype='text/html')

@app.route('/upload',methods=['POST'])
def upload():
    try:
        tf=request.files.get('track_file')
        of=request.files.get('order_file')
        uploader=request.form.get('uploader','ไม่ระบุ')
        if not tf: return jsonify({'error':'กรุณาอัพโหลด Tracking file'}),400
        track_rows=read_csv_bytes(tf.read())
        order_rows=read_csv_bytes(of.read()) if of and of.filename else None
        rows=process_data(track_rows,order_rows)
        shared_data.update({'rows':rows,'uploaded_by':uploader,'uploaded_at':datetime.now().strftime('%d/%m/%Y %H:%M'),'track_file':tf.filename,'order_file':of.filename if of and of.filename else ''})
        return jsonify({'success':True,'total':len(rows),'product':sum(1 for r in rows if not r['is_gift']),'gift':sum(1 for r in rows if r['is_gift']),'uploaded_at':shared_data['uploaded_at'],'uploaded_by':uploader})
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/data')
def get_data():
    return jsonify(shared_data)


HTML_PAGE = """<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>WMS Tracking Matcher</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.5/xlsx.full.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/PapaParse/5.4.1/papaparse.min.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Sarabun','Noto Sans Thai',Arial,sans-serif;background:#f1f5f9;min-height:100vh;padding:16px;font-size:13px}
.hdr{background:#1e293b;border-radius:12px;padding:14px 20px;margin-bottom:14px;display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.hdr h1{color:#fff;font-size:17px;font-weight:700}
.hdr p{color:#94a3b8;font-size:12px;margin-top:3px}
.badges{margin-left:auto;display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.br{background:#dc2626;color:#fff;padding:5px 12px;border-radius:7px;font-size:12px;font-weight:700}
.by{background:#d97706;color:#fff;padding:5px 12px;border-radius:7px;font-size:12px;font-weight:700}
.mode-tabs{display:flex;gap:8px;margin-bottom:12px}
.mode-tab{padding:8px 18px;border-radius:8px;border:2px solid #e2e8f0;background:#fff;cursor:pointer;font-size:13px;font-weight:600;color:#64748b;font-family:inherit}
.mode-tab.active{border-color:#2563eb;background:#eff6ff;color:#1d4ed8}
.upload-panel{background:#fff;border-radius:12px;padding:16px;margin-bottom:14px;box-shadow:0 1px 4px rgba(0,0,0,.07)}
.upload-grid{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:12px}
.drop-zone{flex:1;min-width:220px;border:2px dashed #cbd5e1;border-radius:10px;padding:16px;text-align:center;cursor:pointer;transition:.2s;background:#f8fafc;position:relative}
.drop-zone:hover,.drop-zone.drag{border-color:#3b82f6;background:#eff6ff}
.drop-zone.done{border-color:#16a34a;background:#f0fdf4}
.drop-zone input[type=file]{position:absolute;inset:0;opacity:0;cursor:pointer;width:100%;height:100%}
.drop-icon{font-size:24px;margin-bottom:5px}
.drop-title{font-weight:700;color:#1e293b;font-size:13px;margin-bottom:3px}
.drop-sub{color:#64748b;font-size:11px}
.drop-tag{display:inline-block;margin-top:4px;background:#f1f5f9;color:#475569;font-size:10px;padding:2px 7px;border-radius:4px;font-family:monospace}
.drop-done{color:#16a34a;font-weight:700;font-size:11px;margin-top:5px}
.single-upload{border:2px dashed #6366f1;border-radius:12px;padding:20px;text-align:center;cursor:pointer;background:#faf5ff;position:relative;margin-bottom:12px}
.single-upload:hover,.single-upload.drag{border-color:#4f46e5;background:#ede9fe}
.single-upload.done{border-color:#16a34a;background:#f0fdf4}
.single-upload input[type=file]{position:absolute;inset:0;opacity:0;cursor:pointer;width:100%;height:100%}
.sheet-tags{display:flex;gap:8px;justify-content:center;margin-top:8px;flex-wrap:wrap}
.sheet-tag{background:#e0e7ff;color:#3730a3;padding:3px 10px;border-radius:5px;font-size:11px;font-weight:700;font-family:monospace}
.uploader-row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.uploader-row input[type=text]{flex:1;min-width:160px;padding:9px 12px;border-radius:8px;border:1.5px solid #cbd5e1;font-size:13px;font-family:inherit;outline:none}
.uploader-row input:focus{border-color:#3b82f6}
.upload-btn{padding:10px 24px;background:#2563eb;color:#fff;border:none;border-radius:8px;font-size:13px;font-weight:700;cursor:pointer;font-family:inherit;white-space:nowrap}
.upload-btn:hover{background:#1d4ed8}
.upload-btn:disabled{background:#94a3b8;cursor:not-allowed}
.status-bar{background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;padding:10px 14px;margin-bottom:12px;font-size:12px;color:#166534;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.status-bar.hidden{display:none}
.ctrl{display:flex;gap:8px;margin-bottom:10px;flex-wrap:wrap;align-items:center}
.ctrl input{flex:1;min-width:200px;padding:8px 12px;border-radius:8px;border:1.5px solid #cbd5e1;font-size:13px;outline:none;font-family:inherit}
.ctrl input:focus{border-color:#3b82f6}
.fbtn{padding:7px 13px;border-radius:7px;border:none;cursor:pointer;font-size:12px;font-weight:700;font-family:inherit}
.on{background:#1e293b;color:#fff}.off{background:#e2e8f0;color:#475569}
.cnt{color:#64748b;font-size:12px}
.exp-btn{padding:8px 14px;background:#16a34a;color:#fff;border:none;border-radius:7px;font-size:12px;font-weight:700;cursor:pointer;font-family:inherit}
.exp-btn:hover{background:#15803d}
.leg{display:flex;gap:14px;margin-bottom:9px;font-size:12px;color:#475569;flex-wrap:wrap;align-items:center}
.pr{background:#fee2e2;color:#991b1b;padding:2px 8px;border-radius:4px;font-weight:700}
.py{background:#fef9c3;color:#854d0e;padding:2px 8px;border-radius:4px;font-weight:700}
.note{color:#94a3b8;font-size:11px}
.tw{background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.07);overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:12px}
thead tr{background:#1e293b;color:#fff}
thead th{padding:9px 10px;text-align:left;font-weight:600;white-space:nowrap}
tbody tr{border-bottom:1px solid #f1f5f9}
tbody tr.rp{background:#fff}tbody tr.rp.alt{background:#f8fafc}
tbody tr.rg{background:#fffbeb}tbody tr.rg.alt{background:#fef3c7}
tbody tr:hover{filter:brightness(.96)}
td{padding:7px 10px;vertical-align:middle}
.oid{font-weight:700;color:#1e293b;white-space:nowrap}
.name{color:#334155;max-width:220px;line-height:1.4}
.sku-c{font-family:monospace;font-size:11px;color:#475569;background:#f1f5f9;padding:2px 6px;border-radius:4px;white-space:nowrap}
.qty{text-align:center;font-weight:700;color:#1e293b}
.consign-c{color:#64748b;font-size:11px;white-space:nowrap}
.carrier-badge{display:inline-flex;align-items:center;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700;white-space:nowrap}
.track-red{background:#fee2e2;color:#991b1b;padding:3px 9px;border-radius:5px;font-weight:700;font-family:monospace;font-size:12px;white-space:nowrap;display:inline-block;text-decoration:none}
.track-red:hover{background:#fecaca}
.track-yellow{background:#fef9c3;color:#854d0e;padding:3px 9px;border-radius:5px;font-weight:700;font-family:monospace;font-size:12px;white-space:nowrap;display:inline-block;text-decoration:none}
.track-yellow:hover{background:#fde68a}
.no{color:#cbd5e1}.num{color:#94a3b8;font-size:11px}
.empty{padding:40px;text-align:center;color:#94a3b8}
.placeholder{background:#fff;border-radius:12px;padding:48px;text-align:center;color:#94a3b8}
.foot{margin-top:8px;color:#94a3b8;font-size:11px;text-align:right}
.info-box{background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:8px 12px;font-size:12px;color:#1e40af;margin-bottom:10px}
</style>
</head>
<body>
<div class="hdr">
  <div><h1>📦 WMS Tracking Matcher</h1><p>อัพโหลดครั้งเดียว ทุกเครื่องเห็นข้อมูลเดียวกัน</p></div>
  <div class="badges">
    <span class="br" id="cp">🔴 สินค้า: –</span>
    <span class="by" id="cg">🟡 ของแถม: –</span>
  </div>
</div>

<div class="mode-tabs">
  <button class="mode-tab" id="tab-two" onclick="setMode('two')">📂 2 ไฟล์ CSV</button>
  <button class="mode-tab active" id="tab-one" onclick="setMode('one')">📗 1 ไฟล์ Excel (2 Sheet)</button>
</div>

<div class="upload-panel">
  <!-- 2 CSV -->
  <div id="mode-two" style="display:none">
    <div class="upload-grid">
      <div class="drop-zone" id="dz1" ondragover="doDragOver(event,'dz1')" ondragleave="doDragLeave('dz1')" ondrop="doDrop(event,'track')">
        <div class="drop-icon">📋</div>
        <div class="drop-title">Tracking.csv</div>
        <div class="drop-sub">Order ID · Tracking · แบรนด์</div>
        <label for="csv1-input" style="display:inline-block;margin-top:8px;padding:6px 14px;background:#2563eb;color:#fff;border-radius:7px;font-size:12px;font-weight:700;cursor:pointer">เลือกไฟล์</label>
        <input type="file" accept=".csv" id="csv1-input" style="display:none" onchange="pickFile(event,'track')">
        <div class="drop-done" id="track-name"></div>
      </div>
      <div class="drop-zone" id="dz2" ondragover="doDragOver(event,'dz2')" ondragleave="doDragLeave('dz2')" ondrop="doDrop(event,'order')">
        <div class="drop-icon">📊</div>
        <div class="drop-title">ข้อมูลออเดอร์.csv <span style="color:#94a3b8;font-weight:400">(ถ้ามี)</span></div>
        <div class="drop-sub">Order ID · SKU · SUM of</div>
        <label for="csv2-input" style="display:inline-block;margin-top:8px;padding:6px 14px;background:#2563eb;color:#fff;border-radius:7px;font-size:12px;font-weight:700;cursor:pointer">เลือกไฟล์</label>
        <input type="file" accept=".csv" id="csv2-input" style="display:none" onchange="pickFile(event,'order')">
        <div class="drop-done" id="order-name"></div>
      </div>
    </div>
  </div>
  <!-- 1 Excel -->
  <div id="mode-one">
    <div class="info-box">📗 ไฟล์ Excel ต้องมี 2 Sheet ชื่อ <strong>"Tracking"</strong> และ <strong>"ข้อมูลออเดอร์"</strong></div>
    <div style="background:#faf5ff;border:2px solid #a5b4fc;border-radius:12px;padding:20px;margin-bottom:12px;text-align:center">
      <div style="font-size:24px;margin-bottom:8px">📗</div>
      <div style="font-weight:700;color:#1e293b;font-size:14px;margin-bottom:4px">อัพโหลด Excel ไฟล์เดียว</div>
      <div style="display:flex;gap:8px;justify-content:center;margin:8px 0">
        <span class="sheet-tag">Sheet: Tracking</span>
        <span class="sheet-tag">Sheet: ข้อมูลออเดอร์</span>
      </div>
      <label for="xl-input" style="display:inline-block;padding:10px 24px;background:#6366f1;color:#fff;border-radius:8px;font-size:13px;font-weight:700;cursor:pointer;margin-top:8px">📂 เลือกไฟล์ .xlsx</label>
      <input type="file" accept=".xlsx,.xls" id="xl-input" style="display:none" onchange="loadXl(event)">
      <div class="drop-done" id="xl-name" style="margin-top:8px"></div>
    </div>
  </div>
  <div class="uploader-row">
    <input type="text" id="uploader" placeholder="ชื่อผู้อัพโหลด (เช่น แอดมิน, คุณA)">
    <button class="upload-btn" id="upload-btn" onclick="doUpload()" disabled>⚡ อัพโหลดและประมวลผล</button>
  </div>
</div>

<div class="status-bar __STATUS_CLASS__" id="status-bar">
  <span>✅ ข้อมูลพร้อมใช้งาน</span>
  <span id="status-detail">อัพโหลดโดย: __UPLOADED_BY__ | เวลา: __UPLOADED_AT__ | ไฟล์: __TRACK_FILE____ORDER_FILE_DISPLAY__</span>
</div>

<div id="result-area">
  <div class="placeholder">
    <div style="font-size:48px;margin-bottom:12px">📂</div>
    <h2 style="font-size:16px;color:#64748b;margin-bottom:8px">ยังไม่มีข้อมูล</h2>
    <p>อัพโหลด Excel ไฟล์เดียว (2 Sheet) หรือ 2 ไฟล์ CSV</p>
  </div>
</div>

<script>
let trackFile=null,orderFile=null,xlFile=null,allRows=[],flt='all',mode='one';

const TIS620=(()=>{
  const m=[8364,65533,65533,65533,65533,8230,65533,65533,65533,65533,65533,65533,65533,65533,65533,65533,65533,8216,8217,8220,8221,8226,8211,8212,65533,65533,65533,65533,65533,65533,65533,65533,160,3585,3586,3587,3588,3589,3590,3591,3592,3593,3594,3595,3596,3597,3598,3599,3600,3601,3602,3603,3604,3605,3606,3607,3608,3609,3610,3611,3612,3613,3614,3615,3616,3617,3618,3619,3620,3621,3622,3623,3624,3625,3626,3627,3628,3629,3630,3631,3632,3633,3634,3635,3636,3637,3638,3639,3640,3641,3642,65533,65533,65533,65533,3647,3648,3649,3650,3651,3652,3653,3654,3655,3656,3657,3658,3659,3660,3661,3662,3663,3664,3665,3666,3667,3668,3669,3670,3671,3672,3673,3674,3675,65533,65533,65533,65533];
  return buf=>{let s='';const b=new Uint8Array(buf);for(let i=0;i<b.length;i++)s+=b[i]<0x80?String.fromCharCode(b[i]):String.fromCharCode(m[b[i]-0x80]);return s;};
})();

function setMode(m){
  mode=m;
  document.getElementById('tab-two').className='mode-tab'+(m==='two'?' active':'');
  document.getElementById('tab-one').className='mode-tab'+(m==='one'?' active':'');
  document.getElementById('mode-two').style.display=m==='two'?'':'none';
  document.getElementById('mode-one').style.display=m==='one'?'':'none';
  trackFile=orderFile=xlFile=null;
  document.getElementById('upload-btn').disabled=true;
}

function doDragOver(e,id){e.preventDefault();document.getElementById(id).classList.add('drag');}
function doDragLeave(id){document.getElementById(id).classList.remove('drag');}
function doDrop(e,type){e.preventDefault();const f=e.dataTransfer.files[0];if(f)setCSV(f,type);}
function doDropXl(e){e.preventDefault();const f=e.dataTransfer.files[0];if(f)readXl(f);}
function pickFile(e,type){const f=e.target.files[0];if(f)setCSV(f,type);}
function loadXl(e){const f=e.target.files[0];if(f)readXl(f);}

function setCSV(f,type){
  const r=new FileReader();
  r.onload=ev=>{
    const text=TIS620(ev.target.result);
    if(type==='track'){trackFile=text;document.getElementById('track-name').textContent='✅ '+f.name;document.getElementById('dz1').classList.add('done');}
    else{orderFile=text;document.getElementById('order-name').textContent='✅ '+f.name;document.getElementById('dz2').classList.add('done');}
    document.getElementById('upload-btn').disabled=!trackFile;
  };
  r.readAsArrayBuffer(f);
}

function readXl(file){
  const r=new FileReader();
  r.onload=ev=>{
    const wb=XLSX.read(ev.target.result,{type:'array'});
    const names=wb.SheetNames;
    const tSheet=names.find(s=>s.toLowerCase().includes('track'));
    const oSheet=names.find(s=>s.includes('ออเดอร์')||s.toLowerCase().includes('order'));
    if(!tSheet){alert('ไม่พบ Sheet "Tracking"');return;}
    if(!oSheet){alert('ไม่พบ Sheet "ข้อมูลออเดอร์"');return;}
    // Convert to CSV text
    trackFile=XLSX.utils.sheet_to_csv(wb.Sheets[tSheet]);
    orderFile=XLSX.utils.sheet_to_csv(wb.Sheets[oSheet]);
    const tCount=trackFile.split('\\n').length-1;
    const oCount=orderFile.split('\\n').length-1;
    document.getElementById('xl-name').textContent='✅ '+file.name+' | '+tSheet+': '+tCount+' แถว, '+oSheet+': '+oCount+' แถว';
    document.getElementById('dz-xl').classList.add('done');
    document.getElementById('upload-btn').disabled=false;
  };
  r.readAsArrayBuffer(file);
}

async function doUpload(){
  if(!trackFile){alert('กรุณาเลือกไฟล์ก่อน');return;}
  const btn=document.getElementById('upload-btn');
  btn.disabled=true;btn.textContent='⏳ กำลังประมวลผล...';
  const fd=new FormData();
  const tBlob=new Blob([trackFile],{type:'text/csv'});
  fd.append('track_file',tBlob,'Tracking.csv');
  if(orderFile){const oBlob=new Blob([orderFile],{type:'text/csv'});fd.append('order_file',oBlob,'ข้อมูลออเดอร์.csv');}
  fd.append('uploader',document.getElementById('uploader').value||'ไม่ระบุ');
  try{
    const res=await fetch('/upload',{method:'POST',body:fd});
    const data=await res.json();
    if(data.error){alert('Error: '+data.error);return;}
    await loadData();
    btn.textContent='✅ สำเร็จ!';
    setTimeout(()=>{btn.disabled=false;btn.textContent='⚡ อัพโหลดและประมวลผล';},2000);
  }catch(e){alert('เกิดข้อผิดพลาด: '+e.message);btn.disabled=false;btn.textContent='⚡ อัพโหลดและประมวลผล';}
}

async function loadData(){
  try{
    const res=await fetch('/data');
    const data=await res.json();
    allRows=data.rows||[];
    document.getElementById('cp').textContent='🔴 สินค้า: '+allRows.filter(r=>!r.is_gift).length+' แถว';
    document.getElementById('cg').textContent='🟡 ของแถม: '+allRows.filter(r=>r.is_gift).length+' แถว';
    if(data.uploaded_at){
      document.getElementById('status-bar').classList.remove('hidden');
      const of2=data.order_file?' + '+data.order_file:'';
      document.getElementById('status-detail').textContent='อัพโหลดโดย: '+data.uploaded_by+' | เวลา: '+data.uploaded_at+' | ไฟล์: '+data.track_file+of2;
    }
    if(allRows.length) renderUI();
  }catch(e){console.error(e);}
}

function exportExcel(){
  if(!allRows.length){alert('ไม่มีข้อมูล');return;}
  const wb=XLSX.utils.book_new();
  const H=['Order ID','SKU','แบรนด์','ขนาด','SUM of','consign','บริษัทขนส่ง','Tracking'];
  const toArr=rows=>[H,...rows.map(r=>[r.oid,r.sku,r.brand,r.size,r.qty,r.consign,r.carrier?.name||'',r.tracking])];
  const makeWs=rows=>{const ws=XLSX.utils.aoa_to_sheet(toArr(rows));ws['!cols']=[{wch:14},{wch:18},{wch:50},{wch:10},{wch:8},{wch:24},{wch:16},{wch:22}];ws['!autofilter']={ref:'A1:H1'};return ws;};
  XLSX.utils.book_append_sheet(wb,makeWs(allRows),'📋 ทั้งหมด');
  XLSX.utils.book_append_sheet(wb,makeWs(allRows.filter(r=>!r.is_gift)),'🔴 สินค้า');
  XLSX.utils.book_append_sheet(wb,makeWs(allRows.filter(r=>r.is_gift)),'🟡 ของแถม');
  const d=new Date();
  XLSX.writeFile(wb,'WMS_Report_'+d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0')+'.xlsx');
}

function renderUI(){
  document.getElementById('result-area').innerHTML=
    '<div class="ctrl">'+
    '<input type="text" id="search" placeholder="🔍 ค้นหา Order ID, SKU, แบรนด์, Tracking, ขนส่ง..." oninput="renderTable()">'+
    '<button class="fbtn on" id="ba" onclick="sf(\'all\')">ทั้งหมด</button>'+
    '<button class="fbtn off" id="bp" onclick="sf(\'product\')">🔴 สินค้า</button>'+
    '<button class="fbtn off" id="bg" onclick="sf(\'gift\')">🟡 ของแถม</button>'+
    '<button class="exp-btn" onclick="exportExcel()">📥 Export Excel</button>'+
    '<span class="cnt" id="cl"></span></div>'+
    '<div class="leg"><span>🔴 <span class="pr">สินค้า</span></span><span>🟡 <span class="py">ของแถม</span></span><span class="note">※ คลิก Tracking เพื่อ Track พัสดุได้เลย</span></div>'+
    '<div class="tw"><table><thead><tr>'+
    '<th>#</th><th>Order ID</th><th>SKU</th><th>แบรนด์</th><th>ขนาด</th><th style="text-align:center">Qty</th><th>consign</th><th>🚚 ขนส่ง</th><th>Tracking</th>'+
    '</tr></thead><tbody id="tb"></tbody></table></div>'+
    '<div class="foot" id="fdt"></div>';
  flt='all';renderTable();
}

const CC={'BEST':{bg:'#fee2e2',c:'#991b1b'},'FLASH':{bg:'#fff7ed',c:'#c2410c'},'KERRY':{bg:'#fef3c7',c:'#92400e'},'J&T':{bg:'#fee2e2',c:'#9b1c1c'},'NIM':{bg:'#ede9fe',c:'#5b21b6'},'THPOST':{bg:'#fef3c7',c:'#92400e'},'OTHER':{bg:'#f1f5f9',c:'#475569'}};

function sf(f){flt=f;['ba','bp','bg'].forEach(id=>{const m=(id==='ba'&&f==='all')||(id==='bp'&&f==='product')||(id==='bg'&&f==='gift');document.getElementById(id).className='fbtn '+(m?'on':'off');});renderTable();}
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}

function renderTable(){
  const sq=((document.getElementById('search')||{}).value||'').trim().toLowerCase();
  let data=allRows;
  if(flt==='product') data=data.filter(r=>!r.is_gift);
  if(flt==='gift') data=data.filter(r=>r.is_gift);
  if(sq) data=data.filter(r=>r.oid.toLowerCase().includes(sq)||r.sku.toLowerCase().includes(sq)||r.brand.toLowerCase().includes(sq)||r.tracking.includes(sq)||r.consign.toLowerCase().includes(sq)||(r.carrier?.name||'').toLowerCase().includes(sq));
  const cl=document.getElementById('cl');if(cl)cl.textContent='แสดง '+data.length+' แถว';
  const og={};let gi=0;data.forEach(r=>{if(!(r.oid in og))og[r.oid]=gi++;});
  const tb=document.getElementById('tb');if(!tb)return;
  if(!data.length){tb.innerHTML='<tr><td colspan="9" class="empty">ไม่พบข้อมูล</td></tr>';return;}
  tb.innerHTML=data.map((r,i)=>{
    const alt=og[r.oid]%2===1,isG=r.is_gift;
    const cls=(isG?'rg':'rp')+(alt?' alt':'');
    const ca=r.carrier||{};const cc2=CC[ca.short]||{bg:'#f1f5f9',c:'#475569'};
    const cb=ca.short?'<span class="carrier-badge" style="background:'+cc2.bg+';color:'+cc2.c+'">'+ca.short+'</span>':'<span class="no">–</span>';
    let th='<span class="no">–</span>';
    if(r.tracking){const tc=isG?'track-yellow':'track-red';th=ca.url?'<a href="'+esc(ca.url)+'" target="_blank" class="'+tc+'">'+esc(r.tracking)+' 🔗</a>':'<span class="'+tc+'">'+esc(r.tracking)+'</span>';}
    return '<tr class="'+cls+'"><td class="num">'+(i+1)+'</td><td class="oid">'+esc(r.oid)+'</td><td><span class="sku-c">'+esc(r.sku)+'</span></td><td class="name">'+esc(r.brand)+'</td><td style="text-align:center;color:#64748b;font-size:11px">'+esc(r.size||'')+'</td><td class="qty">'+r.qty+'</td><td class="consign-c">'+esc(r.consign)+'</td><td>'+cb+'</td><td>'+th+'</td></tr>';
  }).join('');
  const fd=document.getElementById('fdt');if(fd)fd.textContent='อัพเดท: '+new Date().toLocaleString('th-TH');
}

setInterval(loadData,30000);
loadData();
</script>
</body>
</html>"""

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
