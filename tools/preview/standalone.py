"""Build a self-contained ICEBOARD preview: python3 standalone.py <board.json> <out.html>"""
import json,re,base64,glob,sys,subprocess,os
import pathlib; S=str(pathlib.Path(__file__).resolve().parent)
ROOT=str(pathlib.Path(__file__).resolve().parents[2]); app=f'{ROOT}/app'; docs=f'{ROOT}/docs'
subprocess.run(['npx','vite','build','--base','./','--outDir',f'{S}/standalone','--logLevel','error'],cwd=app,check=True)
html=open(f'{S}/standalone/index.html').read()
js=open(glob.glob(f'{S}/standalone/assets/*.js')[0]).read()
css=open(glob.glob(f'{S}/standalone/assets/*.css')[0]).read()
board=json.load(open(sys.argv[1]))
if '--snapshot' in sys.argv: board['mode']='demo'; board['snapshot_label']=f"Snapshot of {board['date']} · real data, not tonight"
teams={t for g in board['games'] for t in (g['away']['abbr'],g['home']['abbr'])}
players={}
for f in glob.glob(f'{docs}/players/*.json'):
    if f.endswith('index.json'): continue
    d=json.load(open(f))
    players[str(d['id'])]=d  # all players, so search works offline
logos={os.path.basename(f)[:3]:'data:image/svg+xml;base64,'+base64.b64encode(open(f,'rb').read()).decode() for f in glob.glob(f'{docs}/assets/logos/*_dark.svg')}
badges={os.path.basename(f)[:-4]:open(f).read() for f in glob.glob(f'{docs}/badges/*.svg')}
widths=open(f'{docs}/badges/widths.json').read()
font=base64.b64encode(open(f'{docs}/fonts/NHLNewJersey.ttf','rb').read()).decode()
html=re.sub(r'<script type="module"[^>]*></script>|<link rel="stylesheet"[^>]*>|<link rel="modulepreload"[^>]*>','',html)
html=html.replace('</head>',f'<style>{css}</style><script>window.__BOARD__={json.dumps(board)};window.__LOGOS__={json.dumps(logos)};window.__PLAYERS__={json.dumps(players,separators=(',',':'))};window.__PLAYERS_INDEX__={open(f'{docs}/players/index.json').read()};window.__BADGES__={json.dumps(badges)};window.__BADGE_WIDTHS__={widths};window.__BADGE_FONT__={json.dumps(font)};</script></head>')
html=html.replace('</body>',f'<script type="module">{js.replace("</script>","<\\/script>")}</script></body>')
open(sys.argv[2],'w').write(html); print(sys.argv[2], len(html)//1024,'KB')
