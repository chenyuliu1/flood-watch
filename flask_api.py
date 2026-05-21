# flask_api.py - flood dashboard backend
# pip install flask flask-cors

from flask import Flask, jsonify, request, Response
from flask_cors import CORS
import csv, os, json
from datetime import datetime

app = Flask(__name__)
CORS(app)

SENSOR_CSV = 'sensor_history.csv'
SENSOR_COLUMNS = ['timestamp','water_level','rate_m_min','raw_distance','arduino_state','yellow_led','red_led','buzzer']
SENSOR_HEADER = ','.join(SENSOR_COLUMNS) + '\n'
RAINFALL_CSV = 'rainfall.csv'
FLOOD_ZONES_CSV = 'flood_zones.csv'
POPULATION_CSV = 'population.csv'

WATER_WARNING = 1.5
WATER_DANGER = 3.0
RAIN_WARNING = 20.0
RAIN_DANGER = 50.0

def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as f:
        return list(csv.DictReader(f))

def latest_sensor():
    rows = read_csv(SENSOR_CSV)
    return rows[-1] if rows else None

def avg_rainfall_24h():
    rows = read_csv(RAINFALL_CSV)
    totals = {}
    now = datetime.now()
    for r in rows:
        try:
            d = datetime.strptime(r.get('date',''), '%Y-%m-%d')
            if (now - d).days <= 1:
                a = r.get('area','')
                totals[a] = totals.get(a, 0) + float(r.get('rainfall_mm', 0))
        except: pass
    return sum(totals.values()) / len(totals) if totals else 0

@app.route('/save', methods=['POST'])
def save():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'no data'}), 400
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    row = {
        'timestamp': ts,
        'water_level': data.get('water_level', ''),
        'rate_m_min': data.get('rate_m_min', ''),
        'raw_distance': data.get('raw_distance', ''),
        'arduino_state': data.get('arduino_state', ''),
        'yellow_led': data.get('yellow_led', ''),
        'red_led': data.get('red_led', ''),
        'buzzer': data.get('buzzer', ''),
    }
    if not os.path.exists(SENSOR_CSV):
        with open(SENSOR_CSV, 'w', newline='') as f:
            f.write(SENSOR_HEADER)
    with open(SENSOR_CSV, 'a', newline='') as f:
        csv.writer(f).writerow([row[c] for c in SENSOR_COLUMNS])
    return jsonify({'status': 'saved', 'timestamp': ts})

@app.route('/data')
def get_data():
    return jsonify({
        'sensor_history': read_csv(SENSOR_CSV),
        'rainfall': read_csv(RAINFALL_CSV),
        'flood_zones': read_csv(FLOOD_ZONES_CSV),
        'population': read_csv(POPULATION_CSV),
    })

@app.route('/risk')
def get_risk():
    s = latest_sensor()
    wl = float(s['water_level']) if s and s.get('water_level') else 0
    wl_rate = float(s['rate_m_min']) if s and s.get('rate_m_min') else 0
    rain_24h = {}
    now = datetime.now()
    for r in read_csv(RAINFALL_CSV):
        try:
            d = datetime.strptime(r['date'], '%Y-%m-%d')
            if (now - d).days <= 1:
                rain_24h[r['area']] = rain_24h.get(r['area'], 0) + float(r['rainfall_mm'])
        except: pass
    avg_rain = sum(rain_24h.values()) / len(rain_24h) if rain_24h else 0

    zones = read_csv(FLOOD_ZONES_CSV)
    pop = {p['area']: p for p in read_csv(POPULATION_CSV)}
    weights = {'water_proximity': 0.15, 'flood_history': 0.20, 'drainage': 0.15,
               'rainfall': 0.20, 'cald_vulnerability': 0.10, 'current_water_level': 0.20}

    # same scoring as /risk_by_area, take worst area
    worst_score = 0
    worst_area = ''
    all_scores = {}
    for z in zones:
        p = pop.get(z['area'], {})
        elev = float(z.get('elevation_m', 20))
        hist = z.get('flood_risk_historical', 'low').lower()
        drain = z.get('drainage_capacity', 'medium').lower()
        area_rain = rain_24h.get(z['area'], 0)
        low_eng = float(p.get('low_english_percentage', 0))
        need_asst = float(p.get('needs_assistance_percentage', 0))
        elderly = float(p.get('elderly_percentage', 0))
        cald = float(p.get('cald_percentage', 0))

        scores = {
            'water_proximity': max(0, min(100, int((25 - elev) * 5))),
            'flood_history': {'high': 85, 'medium': 50, 'low': 15}.get(hist, 30),
            'drainage': {'low': 80, 'medium': 45, 'high': 10}.get(drain, 45),
            'rainfall': min(100, int(area_rain * 2)),
            'cald_vulnerability': min(100, int(low_eng * 1.5 + need_asst * 1.5 + elderly * 0.8 + cald * 0.3)),
            'current_water_level': max(0, min(100, int((wl - elev * 0.1) * 20))),
        }
        overall = sum(scores[k] * weights[k] for k in weights)
        if overall > worst_score:
            worst_score = overall
            worst_area = z['area']
            all_scores = scores

    # rate boost: fast-rising water pushes score up for early warning
    if wl_rate > 0.5: worst_score *= 1.3
    elif wl_rate > 0.2: worst_score *= 1.15

    level = 'DANGER' if worst_score >= 65 else ('WARNING' if worst_score >= 40 else 'NORMAL')

    reasons = []
    if wl_rate > 0.2:
        reasons.append(f'Water level rising rapidly ({wl_rate:.2f} m/min)')
    if all_scores.get('current_water_level', 0) >= 60:
        reasons.append(f'Water level {wl:.2f}m above threshold')
    elif all_scores.get('current_water_level', 0) >= 30:
        reasons.append(f'Water level {wl:.2f}m approaching threshold')
    if all_scores.get('rainfall', 0) >= 60:
        reasons.append(f'Heavy rainfall ({avg_rain:.1f}mm/24h)')
    elif all_scores.get('rainfall', 0) >= 30:
        reasons.append(f'Elevated rainfall ({avg_rain:.1f}mm/24h)')
    if all_scores.get('flood_history', 0) >= 60:
        reasons.append('Area has high historical flood risk')
    if all_scores.get('drainage', 0) >= 60:
        reasons.append('Poor drainage capacity')
    if all_scores.get('cald_vulnerability', 0) >= 60:
        reasons.append('High community vulnerability')
    if not reasons:
        reasons.append('All factors within normal range')

    return jsonify({
        'level': level,
        'factors': {'water_level_m': round(wl, 2), 'rate_m_min': round(wl_rate, 2), 'rainfall_24h_mm': round(avg_rain, 1)},
        'scores': {k: all_scores.get(k, 0) for k in weights},
        'composite': round(worst_score, 1),
        'worst_area': worst_area,
        'weights': weights,
        'reasons': reasons
    })

@app.route('/risk_by_area')
def risk_by_area():
    zones = read_csv(FLOOD_ZONES_CSV)
    pop = {p['area']: p for p in read_csv(POPULATION_CSV)}
    rain_24h = {}
    now = datetime.now()
    for r in read_csv(RAINFALL_CSV):
        try:
            d = datetime.strptime(r['date'], '%Y-%m-%d')
            if (now - d).days <= 1:
                rain_24h[r['area']] = rain_24h.get(r['area'], 0) + float(r['rainfall_mm'])
        except: pass
    s = latest_sensor()
    wl = float(s['water_level']) if s and s.get('water_level') else 0
    wl_rate = float(s['rate_m_min']) if s and s.get('rate_m_min') else 0

    weights = {'water_proximity': 0.15, 'flood_history': 0.20, 'drainage': 0.15,
               'rainfall': 0.20, 'cald_vulnerability': 0.10, 'current_water_level': 0.20}
    areas = []
    for z in zones:
        p = pop.get(z['area'], {})
        elev = float(z.get('elevation_m', 20))
        hist = z.get('flood_risk_historical', 'low').lower()
        drain = z.get('drainage_capacity', 'medium').lower()
        area_rain = rain_24h.get(z['area'], 0)
        cald = float(p.get('cald_percentage', 0))
        elderly = float(p.get('elderly_percentage', 0))
        low_eng = float(p.get('low_english_percentage', 0))
        need_asst = float(p.get('needs_assistance_percentage', 0))

        f = {
            'flood_history': {'score': {'high':85,'medium':50,'low':15}.get(hist,30),
                'detail': f'Risk: {hist}, last flood: {z.get("last_flood_year","?")}', 'source': 'Melbourne Water'},
            'drainage': {'score': {'low':80,'medium':45,'high':10}.get(drain,45),
                'detail': f'Capacity: {drain}', 'source': 'Council'},
            'water_proximity': {'score': max(0, min(100, int((25-elev)*5))),
                'detail': f'Elevation {elev}m', 'source': 'Data Vic'},
            'rainfall': {'score': min(100, int(area_rain*2)),
                'detail': f'{area_rain:.1f}mm 24h', 'source': 'BOM'},
            'cald_vulnerability': {'score': min(100, int(low_eng*1.5 + need_asst*1.5 + elderly*0.8 + cald*0.3)),
                'detail': f'{cald}% CALD, {elderly}% elderly, {low_eng}% low English, {need_asst}% need assistance',
                'source': 'ABS Census'},
            'current_water_level': {'score': max(0, min(100, int((wl - elev*0.1)*20))),
                'detail': f'Current: {wl}m', 'source': 'Sensor'},
        }
        overall = sum(f[k]['score'] * weights[k] for k in weights)
        if wl_rate > 0.5: overall *= 1.3
        elif wl_rate > 0.2: overall *= 1.15
        top = max(f.items(), key=lambda x: x[1]['score'])
        level = 'DANGER' if overall >= 65 else ('WARNING' if overall >= 40 else 'NORMAL')
        areas.append({
            'area': z['area'], 'overall_score': round(overall,1), 'level': level,
            'lat': float(z.get('lat', 0)), 'lng': float(z.get('lng', 0)),
            'top_concern': {'factor': top[0].replace('_',' ').title(), 'score': top[1]['score'],
                'detail': top[1]['detail'], 'source': top[1]['source']},
            'all_factors': dict(sorted(f.items(), key=lambda x: -x[1]['score'])),
            'population': int(p.get('total_population', 0))
        })
    areas.sort(key=lambda x: -x['overall_score'])
    return jsonify({
        'areas': areas,
        'data_sources': ['Sensor','BOM','Melbourne Water','Council','Data Vic','ABS Census']
    })

@app.route('/clear_history', methods=['POST'])
def clear():
    with open(SENSOR_CSV, 'w', newline='') as f:
        f.write(SENSOR_HEADER)
    return jsonify({'status': 'cleared'})

@app.route('/download_csv')
def download_csv():
    if not os.path.exists(SENSOR_CSV): return 'No data', 404
    with open(SENSOR_CSV) as f: data = f.read()
    return Response(data, mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=sensor_{datetime.now().strftime("%Y%m%d")}.csv'})

@app.route('/history_dates')
def history_dates():
    dates = set()
    for r in read_csv(SENSOR_CSV):
        ts = r.get('timestamp','')
        if len(ts) >= 10: dates.add(ts[:10])
    return jsonify({'dates': sorted(dates, reverse=True)})

@app.route('/history_csv/<date>')
def history_csv(date):
    rows = [r for r in read_csv(SENSOR_CSV) if r.get('timestamp','').startswith(date)]
    lines = [','.join(SENSOR_COLUMNS)]
    for r in rows:
        lines.append(','.join(r.get(c, '') for c in SENSOR_COLUMNS))
    return Response('\n'.join(lines), mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=sensor_{date}.csv'})

@app.route('/daily_report')
def daily_report():
    date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    rows = [r for r in read_csv(SENSOR_CSV) if r.get('timestamp','').startswith(date)]
    vals = []
    for r in rows:
        try: vals.append(float(r['water_level']))
        except: pass
    hi = round(max(vals),2) if vals else 0
    lo = round(min(vals),2) if vals else 0
    avg = round(sum(vals)/len(vals),2) if vals else 0
    labels = [r.get('timestamp','').split(' ')[-1][:5] for r in rows]
    chart_vals = [float(r.get('water_level',0)) for r in rows if r.get('water_level')]

    issues = ''
    zones = read_csv(FLOOD_ZONES_CSV)
    pop = read_csv(POPULATION_CSV)
    rain = [r for r in read_csv(RAINFALL_CSV) if r.get('date','') == date]
    for z in zones:
        a = z.get('area','')
        probs = []
        if z.get('drainage_capacity','').lower() == 'low':
            probs.append(('<span class="tag tag-council">Council</span>', 'Poor drainage'))
        if z.get('flood_risk_historical','').lower() == 'high':
            probs.append(('<span class="tag tag-mw">Melbourne Water</span>', 'High flood risk'))
        for r in rain:
            if r.get('area') == a:
                try:
                    mm = float(r.get('rainfall_mm',0))
                    if mm > 15: probs.append(('<span class="tag tag-ses">SES</span>', f'{mm}mm rainfall'))
                except: pass
        for p in pop:
            if p.get('area') == a:
                try:
                    le = float(p.get('low_english_percentage',0))
                    if le > 15: probs.append(('<span class="tag tag-ses">SES</span>', f'{le}% low English'))
                except: pass
        if probs:
            issues += f'<div class="issue-block"><strong>{a}</strong><br>'
            for tag, desc in probs: issues += f'{tag} {desc}<br>'
            issues += '</div>'
    if not issues: issues = '<div class="issue-block" style="color:var(--ink-3);">No issues flagged.</div>'

    return f'''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Report — {date}</title>
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700&family=Roboto:wght@300;400;500&family=PT+Mono&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>
<style>
:root{{--ink:#111827;--ink-2:#4b5563;--ink-3:#9ca3af;--secondary:#3b4f82;--danger:#DC2626;--warning:#D97706;--success:#16A34A;--surface:#FFFFFF;--paper:#f7f6f3;--paper-deep:#edebe6;--border:#e5e7eb;--border-lt:#f3f4f6}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Roboto',sans-serif;font-size:14px;color:var(--ink);background:var(--paper);padding:32px;max-width:800px;margin:0 auto;line-height:1.55;
  background-image:url("data:image/svg+xml,%3Csvg width='200' height='200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.7' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.022'/%3E%3C/svg%3E")}}
h1{{font-family:'Montserrat',sans-serif;font-size:20px;font-weight:700;letter-spacing:-0.02em;border-bottom:2px solid var(--ink);padding-bottom:8px;margin-bottom:4px}}
.date-sub{{font-size:12px;color:var(--ink-3);margin-bottom:20px}}
.stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:16px 0 20px}}
.sb{{background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:14px 12px;text-align:center;box-shadow:0 1px 2px rgba(0,0,0,0.04)}}
.sb .v{{font-family:'PT Mono',monospace;font-size:22px;font-weight:400}}
.sb .l{{font-family:'Montserrat',sans-serif;font-size:10px;font-weight:600;color:var(--ink-3);text-transform:uppercase;letter-spacing:0.05em;margin-top:4px}}
.chart-wrap{{background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:16px;box-shadow:0 1px 2px rgba(0,0,0,0.04);margin-bottom:20px}}
.chart-wrap h2{{font-family:'Montserrat',sans-serif;font-size:14px;font-weight:600;margin-bottom:10px}}
h2.section-h{{font-family:'Montserrat',sans-serif;font-size:14px;font-weight:600;margin:20px 0 10px;padding-bottom:6px;border-bottom:1px solid var(--border)}}
.issue-block{{margin-bottom:12px;padding:10px 12px;background:var(--surface);border:1px solid var(--border);border-radius:6px}}
.issue-block strong{{font-size:14px}}
.tag{{display:inline-block;font-family:'Montserrat',sans-serif;font-size:9px;font-weight:600;padding:2px 7px;border-radius:3px;color:#fff;margin-right:3px;letter-spacing:0.03em;text-transform:uppercase}}
.tag-council{{background:var(--warning)}}.tag-mw{{background:var(--secondary)}}.tag-ses{{background:var(--danger)}}.tag-bom{{background:#0f766e}}
.footer{{margin-top:24px;padding-top:12px;border-top:1px solid var(--border-lt);font-size:11px;color:var(--ink-3)}}
</style></head><body>
<h1>Maribyrnong Flood Watch</h1>
<div class="date-sub">Daily Report — {date}</div>
<div class="stats">
<div class="sb"><div class="v" style="color:var(--danger)">{hi}m</div><div class="l">Highest</div></div>
<div class="sb"><div class="v" style="color:var(--secondary)">{lo}m</div><div class="l">Lowest</div></div>
<div class="sb"><div class="v">{avg}m</div><div class="l">Average</div></div>
<div class="sb"><div class="v">{len(rows)}</div><div class="l">Readings</div></div></div>
<div class="chart-wrap"><h2>Water Level — {date}</h2><div style="height:220px"><canvas id="c"></canvas></div></div>
<h2 class="section-h">Flagged Issues</h2>{issues}
<div class="footer">Generated by Maribyrnong Flood Watch. Data sources: Sensor, BOM, Melbourne Water, Council, ABS Census.</div>
<script>new Chart(document.getElementById("c"),{{type:"line",data:{{labels:{json.dumps(labels)},
datasets:[{{label:"Water Level",data:{json.dumps(chart_vals)},borderColor:"#3b4f82",backgroundColor:"rgba(59,79,130,0.08)",
borderWidth:2,pointRadius:1,fill:true,tension:0.2}},
{{label:"Warning",data:{json.dumps([1.5]*len(labels))},borderColor:"#D97706",borderWidth:1,borderDash:[6,6],pointRadius:0,fill:false}},
{{label:"Danger",data:{json.dumps([3.0]*len(labels))},borderColor:"#DC2626",borderWidth:1,borderDash:[6,6],pointRadius:0,fill:false}}]}},
options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{labels:{{font:{{family:"Roboto",size:11}}}}}}}},scales:{{y:{{suggestedMin:0,suggestedMax:4}}}}}}}});</script>
</body></html>'''

if __name__ == '__main__':
    if not os.path.exists(SENSOR_CSV):
        with open(SENSOR_CSV, 'w', newline='') as f:
            f.write(SENSOR_HEADER)
    app.run(host='0.0.0.0', port=5001, debug=True)
