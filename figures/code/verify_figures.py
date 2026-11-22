#!/usr/bin/env python3
"""Verify preserved figure values, native ODG structure and isolated object edits.

The edit probes modify disposable copies, then actually reopen/save/export each
copy with Linux LibreOffice. Original delivery files are never modified.
This is not a Windows GUI certification or a scientific rerun.
"""
from __future__ import annotations
import argparse
import copy
import csv
from collections import Counter
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
from zipfile import ZipFile, ZIP_DEFLATED
from lxml import etree as E
import fitz

ROOT=Path(__file__).resolve().parents[1]
NS={
 'office':'urn:oasis:names:tc:opendocument:xmlns:office:1.0',
 'style':'urn:oasis:names:tc:opendocument:xmlns:style:1.0',
 'draw':'urn:oasis:names:tc:opendocument:xmlns:drawing:1.0',
 'text':'urn:oasis:names:tc:opendocument:xmlns:text:1.0',
 'svg':'urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0',
 'fo':'urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0',
 'xlink':'http://www.w3.org/1999/xlink',
}
def q(s):
 a,b=s.split(':',1); return '{'+NS[a]+'}'+b
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write_json(p,d): Path(p).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def length(s):
 m=re.fullmatch(r'([-+0-9.]+)(cm|mm|in|pt)',s)
 if not m: raise ValueError(s)
 return float(m.group(1))*{'cm':10,'mm':1,'in':25.4,'pt':25.4/72}[m.group(2)]

class Native:
 def __init__(self,path):
  self.path=Path(path)
  with ZipFile(path) as z:
   assert z.testzip() is None
   self.members={n:z.read(n) for n in z.namelist()}
  self.content=E.fromstring(self.members['content.xml'])
  self.styles=E.fromstring(self.members['styles.xml'])
  self.objects=self.content.xpath('//draw:page//*[@draw:name and not(self::draw:g)]',namespaces=NS)
  self.by_id={o.get(q('draw:name')):o for o in self.objects}
  assert len(self.objects)==len(self.by_id)
  self.refresh_styles()

 def refresh_styles(self):
  self.stylemap={s.get(q('style:name')):s for r in [self.styles,self.content]
                 for s in r.xpath('//style:style',namespaces=NS)}

 def props(self,name,kind):
  result={}; seen=set()
  def walk(n):
   if not n or n in seen: return
   seen.add(n); s=self.stylemap[n]
   walk(s.get(q('style:parent-style-name')))
   for c in s.findall(q('style:'+kind+'-properties')): result.update(c.attrib)
  walk(name)
  return result

 def text(self,o):
  return ' '.join(''.join(o.itertext()).split())

 def geometry(self,o):
  return {E.QName(k).localname:length(v) for k,v in o.attrib.items()
          if k in [q('svg:'+x) for x in ('x','y','width','height','x1','y1','x2','y2')]}

 def effective(self,o):
  name=o.get(q('draw:style-name'))
  result={'attributes':dict(o.attrib),'text':self.text(o),'graphic':self.props(name,'graphic'),
          'paragraph':self.props(name,'paragraph'),'text_properties':self.props(name,'text')}
  for p in o.xpath('.//text:p',namespaces=NS):
   if p.get(q('text:style-name')):
    result['paragraph'].update(self.props(p.get(q('text:style-name')),'paragraph'))
    result['text_properties'].update(self.props(p.get(q('text:style-name')),'text'))
   for sp in p.xpath('.//text:span',namespaces=NS):
    if sp.get(q('text:style-name')):
     result['text_properties'].update(self.props(sp.get(q('text:style-name')),'text'))
  return result

 def fingerprints(self):
  return {key:hashlib.sha256(json.dumps(self.effective(o),sort_keys=True).encode()).hexdigest()
          for key,o in self.by_id.items()}

 def write(self,path):
  self.members['content.xml']=E.tostring(self.content,encoding='utf-8',xml_declaration=True)
  self.members['styles.xml']=E.tostring(self.styles,encoding='utf-8',xml_declaration=True)
  with ZipFile(path,'w',ZIP_DEFLATED) as z:
   for name,data in self.members.items():
    z.writestr(name,data,compress_type=0 if name=='mimetype' else ZIP_DEFLATED)

def resolve_source(row):
 src=row['source']; p=ROOT/'SOURCE_DATA'/src['source_file']
 if 'json_path' in src:
  current=json.loads(p.read_text())
  for token in src['json_path'].strip('/').split('/'):
   current=current[int(token)] if isinstance(current,list) else current[token]
  return str(current)
 with p.open(encoding='utf-8',newline='') as f:
  return list(csv.DictReader(f))[src['row_index_zero_based']][src['field']]

def check_one(number):
 scene=json.loads((ROOT/'CONTROL'/f'Fig{number}_OBJECTS_AND_VALUES.json').read_text())
 path=ROOT/'ODG_NATIVE'/f'Fig{number}.odg'; n=Native(path)
 expected={o['id']:o for o in scene['objects']}
 assert set(n.by_id)==set(expected)
 style_refs=[o.get(q('draw:style-name')) for o in n.objects]
 assert len(set(style_refs))==len(style_refs),'Direct object styles must be independent.'
 counts=Counter(E.QName(o).localname for o in n.objects)
 assert set(counts)<= {'rect','line','ellipse','circle','polygon','frame'}
 assert not n.content.xpath('//draw:image|//draw:object|//draw:object-ole',namespaces=NS)
 external=[]
 for member in ['content.xml','styles.xml','meta.xml','settings.xml']:
  if member not in n.members: continue
  root=E.fromstring(n.members[member])
  for href in root.xpath('//@xlink:href',namespaces=NS):
   if re.match(r'(?i)(https?://|file:|ftp:|/|[a-z]:[\\/])',href): external.append(href)
 assert not external,external
 geometry_errors=[]; font_sizes=[]
 for oid,o in expected.items():
  actual=n.by_id[oid]; geom=n.geometry(actual)
  if o['type']=='text':
   assert n.text(actual)==o['text'],(oid,n.text(actual),o['text'])
   tp=n.effective(actual)['text_properties']
   fontsize=length(tp[q('fo:font-size')])*72/25.4
   assert abs(fontsize-o['font_size_pt'])<.011,(oid,fontsize)
   assert abs(fontsize-round(fontsize,2))<.0001
   font_sizes.append(fontsize)
  if o['type']=='line':
   for k in ('x1','y1','x2','y2'): geometry_errors.append(abs(geom[k]-o[k]))
  elif o['type']!='polygon':
   for k in ('x','y','width','height'): geometry_errors.append(abs(geom[k]-o[k]))
  else:
   xs,ys=zip(*o['points'])
   for k,v in {'x':min(xs),'y':min(ys),'width':max(xs)-min(xs),'height':max(ys)-min(ys)}.items():
    geometry_errors.append(abs(geom[k]-v))
 assert max(geometry_errors,default=0)<=.011,max(geometry_errors)
 value_checks=[]
 for row in scene['value_trace']:
  source=resolve_source(row)
  assert Fraction(source)==Fraction(row['source_exact'])
  obj=expected[row['object_id']]; geom=n.geometry(n.by_id[row['object_id']])
  transform=row['geometry_transform']; prop=transform['property']; residual=None
  if prop in ('width','height'):
   wanted=float(Fraction(source))*transform['axis_span_mm']/float(transform['axis_maximum'])
   residual=abs(geom[prop]-wanted); assert residual<=.011
  elif prop=='centre_x':
   wanted=transform['axis_origin_mm']+float(Fraction(source))*transform['axis_span_mm']/float(transform['axis_maximum'])
   residual=abs(geom['x']+geom['width']/2-wanted); assert residual<=.016
  elif prop=='text':
   assert row['display']==n.text(n.by_id[row['object_id']])
  value_checks.append({'object_id':row['object_id'],'source_exact_equal':True,'geometry_residual_mm':residual})
 sv=E.parse(str(ROOT/'SVG_EDITABLE'/f'Fig{number}.svg'))
 svg_text=sv.xpath('//*[local-name()="text"]')
 assert len(svg_text)==counts.get('frame',0)
 assert not sv.xpath('//*[local-name()="image"]')
 assert [e.text for e in svg_text]==[o['text'] for o in scene['objects'] if o['type']=='text']
 pdf=ROOT/'PDF_VECTOR'/f'Fig{number}.pdf'
 with fitz.open(pdf) as d:
  assert len(d)==1 and not d[0].get_images()
  font_info=[]
  for entry in d[0].get_fonts(full=True):
   xref=entry[0]; name,extension,ftype,content=d.extract_font(xref)
   assert len(content)>0,(number,entry)
   font_info.append({'name':name,'type':ftype,'embedded':True})
  assert font_info
  pdfsize=[d[0].rect.width*25.4/72,d[0].rect.height*25.4/72]
  assert abs(pdfsize[0]-scene['width_mm'])<.1 and abs(pdfsize[1]-scene['height_mm'])<.1
 return {'figure':number,'status':'PASS','odg_sha256':sha(path),'pdf_sha256':sha(pdf),'svg_sha256':sha(ROOT/'SVG_EDITABLE'/f'Fig{number}.svg'),
         'native_objects':len(n.objects),'native_primitive_counts':dict(counts),'native_editable_bar_groups':len(n.content.xpath('//draw:g',namespaces=NS)),'independent_direct_graphic_styles':len(set(style_refs)),
         'native_text_frames':counts.get('frame',0),'draw_images':0,'external_asset_links':0,
         'minimum_font_pt':min(font_sizes),'maximum_font_pt':max(font_sizes),'maximum_object_geometry_residual_mm':max(geometry_errors,default=0),
         'value_checks':value_checks,'svg_editable_text_elements':len(svg_text),'pdf_font_records':font_info,'pdf_embedded_images':0,'pdf_dimensions_mm':pdfsize},n,scene

def graphic_props(style):
 p=style.find(q('style:graphic-properties'))
 if p is None: p=E.SubElement(style,q('style:graphic-properties'))
 return p

def probe(number,baseline,scene):
 before_sha=sha(baseline.path); expected=[]
 initial=baseline.fingerprints(); now=dict(initial)
 byscene={o['id']:o for o in scene['objects']}
 for i,(oid,obj) in enumerate(baseline.by_id.items()):
  spec=byscene[oid]; geom=baseline.geometry(obj)
  style_name=obj.get(q('draw:style-name')); st=baseline.stylemap[style_name]
  gp=graphic_props(st)
  # Every object has its own direct graphic style. New unique direct text
  # styles avoid changing any other label even if text formatting was deduplicated.
  colour=f'#{(0x304050 + i*313) % 0xffffff:06x}'
  for k in ('x','x1','x2'):
   if k in geom: obj.set(q('svg:'+k),f'{geom[k]+.2:.6f}mm')
  modified_geom={k:v+(.2 if k in ('x','x1','x2') else 0) for k,v in geom.items()}
  if 'width' in geom:
   obj.set(q('svg:width'),f'{geom["width"]+.2:.6f}mm'); modified_geom['width']+=.2
  record={'object_id':oid,'geometry':modified_geom,'colour':colour,'text':None,'font_size_pt':None}
  if spec['type']=='text':
   text=f'E{i:04d}'
   para=obj.xpath('.//text:p',namespaces=NS)[0]
   for child in list(para): para.remove(child)
   para.text=text
   pname=f'R15_probe_P_{i}'
   ps=E.SubElement(baseline.content.find(q('office:automatic-styles')),q('style:style'),
                   {q('style:name'):pname,q('style:family'):'paragraph'})
   E.SubElement(ps,q('style:paragraph-properties'),{q('fo:text-align'):'start'})
   E.SubElement(ps,q('style:text-properties'),{q('fo:font-size'):f'{spec["font_size_pt"]+.2}pt',
                 q('fo:font-family'):'Liberation Sans',q('style:font-name'):'Liberation Sans',q('fo:color'):colour})
   para.set(q('text:style-name'),pname)
   baseline.refresh_styles()
   record['text']=text; record['font_size_pt']=spec['font_size_pt']+.2
  else:
   gp.set(q('svg:stroke-color'),colour)
   if spec['type'] in ('rect','ellipse','polygon') and spec.get('fill','none')!='none':
    gp.set(q('draw:fill'),'solid'); gp.set(q('draw:fill-color'),colour)
   for descendant in list(gp):
    if E.QName(descendant).localname in ('fill-complex-color','stroke-complex-color'): gp.remove(descendant)
  after=baseline.fingerprints()
  changed=[k for k in now if after[k]!=now[k]]
  assert changed==[oid],(oid,'Edit propagated to unexpected objects',changed)
  record['isolation_verified_before_save']=True
  expected.append(record); now=after
 parent=ROOT/'EDIT_PROBES'; inputdir=parent/'input'; rt=parent/'roundtrip'; render=parent/'rendered'
 for p in (inputdir,rt,render): p.mkdir(parents=True,exist_ok=True)
 source=inputdir/f'Fig{number}_EDIT_PROBE.odg'; baseline.write(source)
 profile=(ROOT/'_runtime'/f'lo_edit_probe_{number}').resolve()
 lo=shutil.which('soffice'); commands=[]
 for fmt,outdir,src in [('odg:draw8',rt,source),('pdf:draw_pdf_Export',render,rt/source.name)]:
  cmd=[lo,'-env:UserInstallation='+profile.as_uri(),'--headless','--convert-to',fmt,'--outdir',str(outdir),str(src)]
  r=subprocess.run(cmd,capture_output=True,text=True,timeout=55)
  assert r.returncode==0,(r.stdout,r.stderr)
  commands.append({'command':cmd,'returncode':r.returncode,'stdout':r.stdout.strip(),'stderr':r.stderr.strip()})
 after=Native(rt/source.name)
 assert set(after.by_id)==set(baseline.by_id)
 residuals=[]
 for item in expected:
  obj=after.by_id[item['object_id']]; actual=after.geometry(obj)
  for k,want in item['geometry'].items():
   residual=abs(actual[k]-want); residuals.append(residual); assert residual<=.011,(item['object_id'],k,residual)
  effective=after.effective(obj)
  if item['text'] is not None:
   assert after.text(obj)==item['text'],item['object_id']
   tp=effective['text_properties']
   assert tp[q('fo:color')].lower()==item['colour'].lower()
   assert abs(length(tp[q('fo:font-size')])*72/25.4-item['font_size_pt'])<.011
  else:
   gp=effective['graphic']
   assert gp[q('svg:stroke-color')].lower()==item['colour'].lower(),(item['object_id'],gp)
   original=byscene[item['object_id']]
   if original['type'] in ('rect','ellipse','polygon') and original.get('fill','none')!='none':
    assert gp[q('draw:fill-color')].lower()==item['colour'].lower(),(item['object_id'],'fill')
  item['retained_after_native_reopen_save']=True
 assert sha(baseline.path)==before_sha,'A production file was unexpectedly changed.'
 with fitz.open(render/source.with_suffix('.pdf').name) as d:
  assert len(d)==1 and not d[0].get_images()
  pix=d[0].get_pixmap(matrix=fitz.Matrix(2,2),alpha=False)
  pix.save(render/f'Fig{number}_EDIT_PROBE.png')
  changed_hash=hashlib.sha256(pix.samples).hexdigest()
 with fitz.open(ROOT/'PDF_VECTOR'/f'Fig{number}.pdf') as d:
  original_hash=hashlib.sha256(d[0].get_pixmap(matrix=fitz.Matrix(2,2),alpha=False).samples).hexdigest()
 assert changed_hash!=original_hash
 return {'figure':number,'status':'PASS','objects_individually_isolated_and_edited':len(expected),
         'all_edits_retained_after_actual_libreoffice_reopen_save':True,'original_production_odg_unchanged':True,
         'edit_probe_odg_sha256':sha(rt/source.name),'maximum_probe_geometry_residual_mm':max(residuals,default=0),
         'changed_render_confirmed':True,'edits':expected,'commands':commands}

def main():
 p=argparse.ArgumentParser(description=__doc__); p.add_argument('--edit-probes',action='store_true',help='Perform native edit/save/export checks on disposable copies');args=p.parse_args()
 results=[]; probes=[]
 for number in range(1,6):
  result,native,scene=check_one(number);results.append(result)
  if args.edit_probes: probes.append(probe(number,native,scene))
  print(f'Fig{number}: structural/value checks PASS'+('; native edit replay PASS' if args.edit_probes else ''),flush=True)
 out={'status':'PASS','scope':('Native Linux LibreOffice edit/reopen/save probes and structural/value checks.' if args.edit_probes else 'Structural and source-value checks of existing ODG, SVG and PDF files; no native edit/reopen/save probe executed.'),
      'figures':results,'edit_probe_summaries':[{k:v for k,v in p.items() if k not in ('edits','commands')} for p in probes],
      'limitations':['No native Windows or macOS execution','No claim that a submission portal accepts ODG','Editable SVG and ODG sources require the named font or an appropriate substitute; PDF and EPS are the font-embedded submission exports','Native Draw geometry has finite coordinate precision; recorded residuals are in millimetres, not changes to source values',('Programmatic object edits and native application roundtrips were tested; interactive GUI gestures are not certified' if args.edit_probes else 'No native application or GUI acceptance test was run by this invocation')]}
 write_json(ROOT/'CONTROL'/'NATIVE_STRUCTURE_AND_VALUES.json',out)
 if probes:write_json(ROOT/'CONTROL'/'NATIVE_EDIT_PROBE_DETAILS.json',{'status':'PASS','probes':probes})
 print(json.dumps({'status':'PASS','figures':len(results),'native_objects':sum(r['native_objects'] for r in results),'text_frames':sum(r['native_text_frames'] for r in results),'value_checks':sum(len(r['value_checks']) for r in results),'edit_probes':len(probes)},indent=2))

if __name__=='__main__':main()
