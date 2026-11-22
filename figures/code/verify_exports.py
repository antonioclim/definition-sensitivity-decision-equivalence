#!/usr/bin/env python3
"""Replay SVG and EPS exports with independent renderers; check raster metadata.

Requires Inkscape, Ghostscript, PyMuPDF and Pillow. Performs no network request.
Visual review remains a separate recorded action; this script never invents it.
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib
import json
import subprocess
import fitz
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'CROSS_RENDERER_QA'

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def process(task):
 kind,i=task
 dest=OUT/kind/f'Fig{i}.pdf'
 source=ROOT/('SVG_EDITABLE' if kind=='SVG' else 'EPS_VECTOR')/f'Fig{i}.{kind.lower()}'
 if kind=='SVG':
  cmd=['inkscape',str(source),'--export-area-page','--export-type=pdf','--export-filename='+str(dest)]
 else:
  cmd=['gs','-q','-dSAFER','-dBATCH','-dNOPAUSE','-sDEVICE=pdfwrite','-dEPSCrop','-sOutputFile='+str(dest),str(source)]
 r=subprocess.run(cmd,capture_output=True,text=True,timeout=55)
 if r.returncode: raise RuntimeError(r.stdout+'\n'+r.stderr)
 with fitz.open(dest) as d:
  assert len(d)==1 and not d[0].get_images()
  fontinfo=[]
  for f in d[0].get_fonts(full=True):
   nm,ex,ty,content=d.extract_font(f[0]);assert content,(kind,i,nm)
   fontinfo.append({'name':nm,'embedded':True,'type':ty})
  pix=d[0].get_pixmap(matrix=fitz.Matrix(200/72,200/72),alpha=False)
  pix.save(OUT/kind/f'Fig{i}.png')
  return {'figure':i,'source_format':kind,'source_sha256':sha(source),'pdf_sha256':sha(dest),
    'pdf_dimensions_mm':[d[0].rect.width*25.4/72,d[0].rect.height*25.4/72],
    'embedded_images':0,'embedded_fonts':fontinfo,'command':cmd,'returncode':r.returncode,'stderr':r.stderr.strip()}

def main():
 for f in ['SVG','EPS']: (OUT/f).mkdir(parents=True,exist_ok=True)
 with ThreadPoolExecutor(max_workers=2) as ex:
  results=list(ex.map(process,[(k,i) for k in ['SVG','EPS'] for i in range(1,6)]))
 rasters=[]
 for i in range(1,6):
  for folder,ext,dpi in [('PNG_600','png',600),('TIFF','tif',1200 if i==1 else 600)]:
   p=ROOT/folder/f'Fig{i}.{ext}'
   with Image.open(p) as im:
    assert im.mode=='RGB'
    actual_dpi=im.info.get('dpi')
    assert actual_dpi and all(abs(v-dpi)<.1 for v in actual_dpi)
    rasters.append({'path':str(p.relative_to(ROOT)),'sha256':sha(p),'pixels':list(im.size),
                    'mode':im.mode,'dpi':[float(v) for v in actual_dpi]})
 result={'status':'STRUCTURE_PASS_VISUAL_REVIEW_RECORDED_SEPARATELY','results':results,'rasters':rasters,
         'script_sha256':sha(Path(__file__)),'limitations':['No native Windows execution','This executable does not perform or certify visual inspection']}
 (OUT/'CROSS_RENDERER_STRUCTURE.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({'status':result['status'],'vector_exports':len(results),'raster_exports':len(rasters)},indent=2))

if __name__=='__main__':main()
