"""Export public hardware capabilities only; no credentials, firmware or config files."""
import argparse, json, subprocess, re
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[3].parent/'pico-esp32');a=p.parse_args()
source=a.source.resolve()
def listing(flag):
    r=subprocess.run(['python3',str(source/'scripts/build.py'),flag,'--json'],cwd=source,capture_output=True,text=True,timeout=60,check=True)
    return json.loads(r.stdout)
boards=listing('--list-boards');languages=listing('--list-languages')
if not boards or not languages: raise ValueError('Empty firmware catalogue')
# Only publish fields already supplied by the upstream public hardware listing.
keys=('board','name','type','target','display_name','wake_word_supported','build_options')
boards=[{k:b[k] for k in keys} for b in boards]
revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip()
v=re.search(r'set\(PROJECT_VER\s+"([^"]+)"', (source/'CMakeLists.txt').read_text())
out=Path(__file__).resolve().parents[1]/'src/generated/firmwareCatalog.json'
out.write_text(json.dumps({'boards':boards,'languages':languages,'revision':revision,'version':v.group(1) if v else 'unknown','source':'pico-esp32'},ensure_ascii=False,indent=2)+'\n')
print(f'Exported {len(boards)} board variants to {out}')
