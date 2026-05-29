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
    if re.match(r'^668\d{11}$',t): return {'name':'Best Express','short':'BEST','url':'https://track.best-express.com/tracking?trackingNumber='+t+'&language=TH'}
    if re.match(r'^TH\d{16}$',t): return {'name':'Flash Express','short':'FLASH','url':'https://www.flashexpress.co.th/tracking/?se='+t}
    if re.match(r'^800\d{9}$',t): return {'name':'J&T Express','short':'J&T','url':'https://www.jtexpress.co.th/index/query/gzquery.html?bills='+t}
    if re.match(r'^NIM',t): return {'name':'Nim Express','short':'NIM','url':'https://nimexpress.com/web/tracking?trackNo='+t}
    if re.match(r'^(EH|RH|RE|EO|RP|RR)\d+TH$',t): return {'name':'ไปรษณีย์ไทย','short':'THPOST','url':'https://track.thailandpost.co.th/?trackNumber='+t}
    if re.match(r'^KY',t): return {'name':'Kerry','short':'KERRY','url':'https://th.kerryexpress.com/th/track/?track='+t}
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
                name=re.sub(r'\s*\(.*?\)','',line).lstrip('แถม').strip(' -')
                is_gift=line.strip().startswith('แถม')
                rows.append({'oid':oid,'sku':sku,'brand':name,'size':'','qty':qty,'consign':consign,'tracking':tracking,'carrier':carrier,'is_gift':is_gift})
    return rows

@app.route('/')
def index():
    has_data=len(shared_data['rows'])>0
    sc='' if has_data else 'hidden'
    ub=shared_data['uploaded_by']
    ua=shared_data['uploaded_at']
    tf=shared_data['track_file']
    of=shared_data['order_file']
    of2=(' + '+of) if of else ''
    return Response(HTML_PAGE.replace('__SC__',sc).replace('__UB__',ub).replace('__UA__',ua).replace('__TF__',tf).replace('__OF__',of2),mimetype='text/html')

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
        return jsonify({'success':True,'total':len(rows),'product':sum(1 for r in rows if not r['is_gift']),'gift':sum(1 for r in rows if r['is_gift'])})
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/data')
def get_data():
    return jsonify(shared_data)


HTML_PAGE = r"""<!DOCTYPE html>
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
.badges{margin-left:auto;display:flex;gap:8px;align-items:center}
.br{background:#dc2626;color:#fff;padding:5px 12px;border-radius:7px;font-size:12px;font-weight:700}
.by{background:#d97706;color:#fff;padding:5px 12px;border-radius:7px;font-size:12px;font-weight:700}
.tabs{display:flex;gap:8px;margin-bottom:12px}
.tab{padding:8px 18px;border-radius:8px;border:2px solid #e2e8f0;background:#fff;cursor:pointer;font-size:13px;font-weight:600;color:#64748b;font-family:inherit}
.tab.on{border-color:#2563eb;background:#eff6ff;color:#1d4ed8}
.panel{background:#fff;border-radius:12px;padding:16px;margin-bottom:14px;box-shadow:0 1px 4px rgba(0,0,0,.07)}
.grid{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:12px}
.box{flex:1;min-width:200px;border:2px solid #e2e8f0;border-radius:10px;padding:14px;text-align:center;background:#f8fafc}
.box-icon{font-size:22px;margin-bottom:4px}
.box-title{font-weight:700;color:#1e293b;font-size:13px;margin-bottom:6px}
.box input[type=file]{width:100%;font-size:12px;padding:6px;border:1.5px solid #94a3b8;border-radius:6px;background:#fff;cursor:pointer}
.box-done{color:#16a34a;font-size:11px;font-weight:700;margin-top:6px}
.xl-box{border:2px solid #a5b4fc;background:#faf5ff;border-radius:12px;padding:20px;margin-bottom:12px;text-align:center}
.xl-box input[type=file]{font-size:13px;padding:10px;border:2px solid #6366f1;border-radius:8px;background:#fff;cursor:pointer;width:100%;max-width:420px}
.sheet-tags{display:flex;gap:8px;justify-content:center;margin:8px 0}
.stag{background:#e0e7ff;color:#3730a3;padding:3px 10px;border-radius:5px;font-size:11px;font-weight:700}
.urow{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.urow input[type=text]{flex:1;min-width:160px;padding:9px 12px;border-radius:8px;border:1.5px solid #cbd5e1;font-size:13px;font-family:inherit;outline:none}
.ubtn{padding:10px 24px;background:#2563eb;color:#fff;border:none;border-radius:8px;font-size:13px;font-weight:700;cursor:pointer;font-family:inherit;white-space:nowrap}
.ubtn:hover{background:#1d4ed8}
.ubtn:disabled{background:#94a3b8;cursor:not-allowed}
.sbar{background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;padding:10px 14px;margin-bottom:12px;font-size:12px;color:#166534}
.sbar.hidden{display:none}
.info{background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:8px 12px;font-size:12px;color:#1e40af;margin-bottom:10px}
.ctrl{display:flex;gap:8px;margin-bottom:10px;flex-wrap:wrap;align-items:center}
.ctrl input[type=text]{flex:1;min-width:200px;padding:8px 12px;border-radius:8px;border:1.5px solid #cbd5e1;font-size:13px;outline:none;font-family:inherit}
.fbtn{padding:7px 13px;border-radius:7px;border:none;cursor:pointer;font-size:12px;font-weight:700;font-family:inherit}
.on{background:#1e293b;color:#fff}
.off{background:#e2e8f0;color:#475569}
.cnt{color:#64748b;font-size:12px}
.ebtn{padding:8px 14px;background:#16a34a;color:#fff;border:none;border-radius:7px;font-size:12px;font-weight:700;cursor:pointer;font-family:inherit}
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
.nm{color:#334155;max-width:220px;line-height:1.4}
.sku{font-family:monospace;font-size:11px;color:#475569;background:#f1f5f9;padding:2px 6px;border-radius:4px;white-space:nowrap}
.qty{text-align:center;font-weight:700;color:#1e293b}
.con{color:#64748b;font-size:11px;white-space:nowrap}
.cb{display:inline-flex;align-items:center;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700;white-space:nowrap}
.tr{padding:3px 9px;border-radius:5px;font-weight:700;font-family:monospace;font-size:12px;white-space:nowrap;display:inline-block;text-decoration:none}
.tr-r{background:#fee2e2;color:#991b1b}
.tr-r:hover{background:#fecaca}
.tr-y{background:#fef9c3;color:#854d0e}
.tr-y:hover{background:#fde68a}
.no{color:#cbd5e1}
.num{color:#94a3b8;font-size:11px}
.empty{padding:40px;text-align:center;color:#94a3b8}
.ph{background:#fff;border-radius:12px;padding:48px;text-align:center;color:#94a3b8}
.foot{margin-top:8px;color:#94a3b8;font-size:11px;text-align:right}
</style>
</head>
<body>
<div class="hdr">
  <div><h1>📦 WMS Tracking Matcher</h1><p>อัพโหลดครั้งเดียว ทุกเครื่องเห็นข้อมูลเดียวกัน</p></div>
  <div class="badges">
    <span class="br" id="cp">🔴 สินค้า: -</span>
    <span class="by" id="cg">🟡 ของแถม: -</span>
  </div>
</div>

<div class="tabs">
  <button class="tab" id="t2" onclick="setMode('two')">📂 2 ไฟล์ CSV</button>
  <button class="tab on" id="t1" onclick="setMode('one')">📗 1 ไฟล์ Excel (2 Sheet)</button>
</div>

<div class="panel">
  <div id="m2" style="display:none">
    <div class="grid">
      <div class="box">
        <div class="box-icon">📋</div>
        <div class="box-title">Tracking.csv</div>
        <input type="file" accept=".csv" id="f1" onchange="loadCSV(event,'track')">
        <div class="box-done" id="f1d"></div>
      </div>
      <div class="box">
        <div class="box-icon">📊</div>
        <div class="box-title">ข้อมูลออเดอร์.csv</div>
        <input type="file" accept=".csv" id="f2" onchange="loadCSV(event,'order')">
        <div class="box-done" id="f2d"></div>
      </div>
    </div>
  </div>
  <div id="m1">
    <div class="info">📗 ไฟล์ Excel ต้องมี 2 Sheet ชื่อ <b>"Tracking"</b> และ <b>"ข้อมูลออเดอร์"</b></div>
    <div class="xl-box">
      <div style="font-size:24px;margin-bottom:6px">📗</div>
      <div style="font-weight:700;color:#1e293b;margin-bottom:6px">เลือกไฟล์ Excel</div>
      <div class="sheet-tags">
        <span class="stag">Sheet: Tracking</span>
        <span class="stag">Sheet: ข้อมูลออเดอร์</span>
      </div>
      <div style="margin-top:10px">
        <input type="file" accept=".xlsx,.xls" id="fx" onchange="loadXL(event)">
      </div>
      <div class="box-done" id="fxd"></div>
    </div>
  </div>
  <div class="urow">
    <input type="text" id="uname" placeholder="ชื่อผู้อัพโหลด (เช่น แอดมิน)">
    <button class="ubtn" id="ubtn" onclick="doUpload()" disabled>⚡ อัพโหลดและประมวลผล</button>
  </div>
</div>

<div class="sbar __SC__" id="sbar">
  ✅ ข้อมูลพร้อมใช้งาน | อัพโหลดโดย: __UB__ | เวลา: __UA__ | ไฟล์: __TF____OF__
</div>

<div id="ra">
  <div class="ph">
    <div style="font-size:48px;margin-bottom:12px">📂</div>
    <div style="font-size:16px;color:#64748b;margin-bottom:8px;font-weight:700">ยังไม่มีข้อมูล</div>
    <div>อัพโหลด Excel (2 Sheet) หรือ 2 ไฟล์ CSV</div>
  </div>
</div>

<script>
var trackTxt=null,orderTxt=null,allRows=[],flt='all',mode='one';

function setMode(m){
  mode=m;
  document.getElementById('t2').className='tab'+(m==='two'?' on':'');
  document.getElementById('t1').className='tab'+(m==='one'?' on':'');
  document.getElementById('m2').style.display=m==='two'?'':'none';
  document.getElementById('m1').style.display=m==='one'?'':'none';
  trackTxt=null;orderTxt=null;
  document.getElementById('ubtn').disabled=true;
}

var TIS620_MAP=[8364,65533,65533,65533,65533,8230,65533,65533,65533,65533,65533,65533,65533,65533,65533,65533,65533,8216,8217,8220,8221,8226,8211,8212,65533,65533,65533,65533,65533,65533,65533,65533,160,3585,3586,3587,3588,3589,3590,3591,3592,3593,3594,3595,3596,3597,3598,3599,3600,3601,3602,3603,3604,3605,3606,3607,3608,3609,3610,3611,3612,3613,3614,3615,3616,3617,3618,3619,3620,3621,3622,3623,3624,3625,3626,3627,3628,3629,3630,3631,3632,3633,3634,3635,3636,3637,3638,3639,3640,3641,3642,65533,65533,65533,65533,3647,3648,3649,3650,3651,3652,3653,3654,3655,3656,3657,3658,3659,3660,3661,3662,3663,3664,3665,3666,3667,3668,3669,3670,3671,3672,3673,3674,3675,65533,65533,65533,65533];

function decodeTIS620(buf){
  var b=new Uint8Array(buf),s='';
  for(var i=0;i<b.length;i++) s+=b[i]<128?String.fromCharCode(b[i]):String.fromCharCode(TIS620_MAP[b[i]-128]);
  return s;
}

function loadCSV(e,type){
  var file=e.target.files[0];
  if(!file) return;
  var r=new FileReader();
  r.onload=function(ev){
    var txt=decodeTIS620(ev.target.result);
    if(type==='track'){trackTxt=txt;document.getElementById('f1d').textContent='✅ '+file.name;}
    else{orderTxt=txt;document.getElementById('f2d').textContent='✅ '+file.name;}
    document.getElementById('ubtn').disabled=!trackTxt;
  };
  r.readAsArrayBuffer(file);
}

function loadXL(e){
  var file=e.target.files[0];
  if(!file) return;
  var r=new FileReader();
  r.onload=function(ev){
    var wb=XLSX.read(ev.target.result,{type:'array'});
    var names=wb.SheetNames;
    var tS=names.find(function(s){return s.toLowerCase().indexOf('track')>=0;});
    var oS=names.find(function(s){return s.indexOf('ออเดอร์')>=0||s.toLowerCase().indexOf('order')>=0;});
    if(!tS){alert('ไม่พบ Sheet "Tracking"');return;}
    if(!oS){alert('ไม่พบ Sheet "ข้อมูลออเดอร์"');return;}
    trackTxt=XLSX.utils.sheet_to_csv(wb.Sheets[tS]);
    orderTxt=XLSX.utils.sheet_to_csv(wb.Sheets[oS]);
    var tc=trackTxt.split('\n').length-1;
    var oc=orderTxt.split('\n').length-1;
    document.getElementById('fxd').textContent='✅ '+file.name+' | Tracking: '+tc+' แถว, ออเดอร์: '+oc+' แถว';
    document.getElementById('ubtn').disabled=false;
  };
  r.readAsArrayBuffer(file);
}

function doUpload(){
  if(!trackTxt){alert('กรุณาเลือกไฟล์ก่อน');return;}
  var btn=document.getElementById('ubtn');
  btn.disabled=true;btn.textContent='⏳ กำลังประมวลผล...';
  var fd=new FormData();
  fd.append('track_file',new Blob([trackTxt],{type:'text/csv'}),'Tracking.csv');
  if(orderTxt) fd.append('order_file',new Blob([orderTxt],{type:'text/csv'}),'order.csv');
  fd.append('uploader',document.getElementById('uname').value||'ไม่ระบุ');
  fetch('/upload',{method:'POST',body:fd})
    .then(function(r){return r.json();})
    .then(function(d){
      if(d.error){alert('Error: '+d.error);btn.disabled=false;btn.textContent='⚡ อัพโหลดและประมวลผล';return;}
      loadData();btn.textContent='✅ สำเร็จ!';
      setTimeout(function(){btn.disabled=false;btn.textContent='⚡ อัพโหลดและประมวลผล';},2000);
    })
    .catch(function(e){alert('Error: '+e.message);btn.disabled=false;btn.textContent='⚡ อัพโหลดและประมวลผล';});
}

function loadData(){
  fetch('/data').then(function(r){return r.json();}).then(function(d){
    allRows=d.rows||[];
    document.getElementById('cp').textContent='🔴 สินค้า: '+allRows.filter(function(r){return !r.is_gift;}).length+' แถว';
    document.getElementById('cg').textContent='🟡 ของแถม: '+allRows.filter(function(r){return r.is_gift;}).length+' แถว';
    if(d.uploaded_at){
      var sb=document.getElementById('sbar');
      sb.className='sbar';
      sb.textContent='✅ ข้อมูลพร้อมใช้งาน | อัพโหลดโดย: '+d.uploaded_by+' | เวลา: '+d.uploaded_at+' | ไฟล์: '+d.track_file+(d.order_file?' + '+d.order_file:'');
    }
    if(allRows.length) renderUI();
  }).catch(function(e){console.error(e);});
}

function exportExcel(){
  if(!allRows.length){alert('ไม่มีข้อมูล');return;}
  var wb=XLSX.utils.book_new();
  var H=['Order ID','SKU','แบรนด์','ขนาด','SUM of','consign','บริษัทขนส่ง','Tracking'];
  function makeWs(rows){
    var data=[H];
    rows.forEach(function(r){data.push([r.oid,r.sku,r.brand,r.size,r.qty,r.consign,(r.carrier&&r.carrier.name)||'',r.tracking]);});
    var ws=XLSX.utils.aoa_to_sheet(data);
    ws['!cols']=[{wch:14},{wch:18},{wch:50},{wch:10},{wch:8},{wch:24},{wch:16},{wch:22}];
    ws['!autofilter']={ref:'A1:H1'};
    return ws;
  }
  XLSX.utils.book_append_sheet(wb,makeWs(allRows),'ทั้งหมด');
  XLSX.utils.book_append_sheet(wb,makeWs(allRows.filter(function(r){return !r.is_gift;})),'สินค้า');
  XLSX.utils.book_append_sheet(wb,makeWs(allRows.filter(function(r){return r.is_gift;})),'ของแถม');
  var d=new Date();
  XLSX.writeFile(wb,'WMS_Report_'+d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0')+'.xlsx');
}

function renderUI(){
  document.getElementById('ra').innerHTML=
    '<div class="ctrl">'+
    '<input type="text" id="srch" placeholder="ค้นหา Order ID, SKU, แบรนด์, Tracking..." oninput="renderTable()">'+
    '<button class="fbtn on" id="ba" onclick="sf(\'all\')">ทั้งหมด</button>'+
    '<button class="fbtn off" id="bp" onclick="sf(\'product\')">สินค้า</button>'+
    '<button class="fbtn off" id="bg" onclick="sf(\'gift\')">ของแถม</button>'+
    '<button class="ebtn" onclick="exportExcel()">Export Excel</button>'+
    '<span class="cnt" id="cl"></span></div>'+
    '<div class="leg"><span><span class="pr">สินค้า</span></span><span><span class="py">ของแถม</span></span><span class="note">คลิก Tracking เพื่อ Track พัสดุ</span></div>'+
    '<div class="tw"><table><thead><tr>'+
    '<th>#</th><th>Order ID</th><th>SKU</th><th>แบรนด์</th><th>ขนาด</th><th>Qty</th><th>consign</th><th>ขนส่ง</th><th>Tracking</th>'+
    '</tr></thead><tbody id="tb"></tbody></table></div>'+
    '<div class="foot" id="fdt"></div>';
  flt='all';renderTable();
}

var CC={'BEST':{bg:'#fee2e2',c:'#991b1b'},'FLASH':{bg:'#fff7ed',c:'#c2410c'},'KERRY':{bg:'#fef3c7',c:'#92400e'},'J&T':{bg:'#fee2e2',c:'#9b1c1c'},'NIM':{bg:'#ede9fe',c:'#5b21b6'},'THPOST':{bg:'#fef3c7',c:'#92400e'},'OTHER':{bg:'#f1f5f9',c:'#475569'}};

function sf(f){
  flt=f;
  ['ba','bp','bg'].forEach(function(id){
    var m=(id==='ba'&&f==='all')||(id==='bp'&&f==='product')||(id==='bg'&&f==='gift');
    document.getElementById(id).className='fbtn '+(m?'on':'off');
  });
  renderTable();
}

function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}

function renderTable(){
  var sq=((document.getElementById('srch')||{}).value||'').trim().toLowerCase();
  var data=allRows.slice();
  if(flt==='product') data=data.filter(function(r){return !r.is_gift;});
  if(flt==='gift') data=data.filter(function(r){return r.is_gift;});
  if(sq) data=data.filter(function(r){
    return r.oid.toLowerCase().indexOf(sq)>=0||r.sku.toLowerCase().indexOf(sq)>=0||
    r.brand.toLowerCase().indexOf(sq)>=0||r.tracking.indexOf(sq)>=0||
    r.consign.toLowerCase().indexOf(sq)>=0||((r.carrier&&r.carrier.name)||'').toLowerCase().indexOf(sq)>=0;
  });
  var cl=document.getElementById('cl');if(cl)cl.textContent='แสดง '+data.length+' แถว';
  var og={},gi=0;
  data.forEach(function(r){if(!(r.oid in og))og[r.oid]=gi++;});
  var tb=document.getElementById('tb');if(!tb)return;
  if(!data.length){tb.innerHTML='<tr><td colspan="9" class="empty">ไม่พบข้อมูล</td></tr>';return;}
  var html='';
  data.forEach(function(r,i){
    var alt=og[r.oid]%2===1,isG=r.is_gift;
    var cls=(isG?'rg':'rp')+(alt?' alt':'');
    var ca=r.carrier||{};
    var cc2=CC[ca.short]||{bg:'#f1f5f9',c:'#475569'};
    var cb=ca.short?'<span class="cb" style="background:'+cc2.bg+';color:'+cc2.c+'">'+esc(ca.short)+'</span>':'<span class="no">-</span>';
    var th='<span class="no">-</span>';
    if(r.tracking){
      var tc=isG?'tr tr-y':'tr tr-r';
      th=ca.url?'<a href="'+esc(ca.url)+'" target="_blank" class="'+tc+'">'+esc(r.tracking)+'</a>':'<span class="'+tc+'">'+esc(r.tracking)+'</span>';
    }
    html+='<tr class="'+cls+'"><td class="num">'+(i+1)+'</td><td class="oid">'+esc(r.oid)+'</td><td><span class="sku">'+esc(r.sku)+'</span></td><td class="nm">'+esc(r.brand)+'</td><td style="text-align:center;color:#64748b;font-size:11px">'+esc(r.size||'')+'</td><td class="qty">'+r.qty+'</td><td class="con">'+esc(r.consign)+'</td><td>'+cb+'</td><td>'+th+'</td></tr>';
  });
  tb.innerHTML=html;
  var fd=document.getElementById('fdt');if(fd)fd.textContent='อัพเดท: '+new Date().toLocaleString('th-TH');
}

setInterval(loadData,30000);
loadData();
</script>
</body>
</html>"""

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
