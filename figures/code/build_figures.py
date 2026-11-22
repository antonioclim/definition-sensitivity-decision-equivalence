#!/usr/bin/env python3
"""Build five native, editable scientific figures from preserved public inputs.

No simulation, acquisition or FAT microdata processing occurs in this program.
The canonical scene contains real text and individually named vector objects.
LibreOffice imports the flat OpenDocument and saves a native Draw document.
PDFs are exported from those ODG documents, rather than from a raster preview.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from fractions import Fraction
from collections import Counter
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
FONT = 'Liberation Sans'
INK = '#222222'
GRID = '#d2d2d2'
BLUE = '#477cb3'
GREEN = '#228c35'
GOLD = '#d2be3a'
CYAN = '#59c2e8'
RED = '#ef6673'
COLORS = [BLUE, GREEN, GOLD]
EXPECTED_SOURCE_SHA256 = {
 'Figure_1_architecture_register.csv':'698662f049deff77030652eec5579726518ee349251ec6ec229bfd42554d2bf5',
 'Figure_2_ablation_event_frequencies.csv':'4790a4afced7cd57c4eb6c40121ed8291cc92ed203046182bc72ccfcf2ad7327',
 'Figure_3_panel_A_reference_rates_mae.csv':'f7262ad9141f0f7503b837efe4a9ef1714431da98cbb6aab2da6257d3eec18ac',
 'Figure_3_panel_B_reference_ordering.csv':'fc74a987911aa021ea2bc3436b3b19af877d53708e338acf0d4f05b53066116a',
 'Figure_3_panel_C_unmatched_objective.csv':'ce883a4bf65b04a6cf1702d250bba12101ba36e0eeb8ba1b7736231aca9679ea',
 'Figure_4_unresolved_determinacy.csv':'185c5ad05307ccfdfae01ba955b26f9d4bc3043a876ef3687919ed5576e049bd',
 'R14_1_OA_REPORTING_TABLES.json':'b96426af1c100caea41a616fd1a962cd6bb15bd5ecd681a559ca60af000bd99b',
}
NS = {
    'office':'urn:oasis:names:tc:opendocument:xmlns:office:1.0',
    'style':'urn:oasis:names:tc:opendocument:xmlns:style:1.0',
    'draw':'urn:oasis:names:tc:opendocument:xmlns:drawing:1.0',
    'text':'urn:oasis:names:tc:opendocument:xmlns:text:1.0',
    'svg':'urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0',
    'fo':'urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0',
    'dc':'http://purl.org/dc/elements/1.1/',
    'meta':'urn:oasis:names:tc:opendocument:xmlns:meta:1.0',
    'xlink':'http://www.w3.org/1999/xlink',
}
for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)

def q(name):
    p, local = name.split(':', 1)
    return '{'+NS[p]+'}'+local

def el(parent, tag, attrs=None, text=None):
    e = ET.SubElement(parent, q(tag), {q(k):str(v) for k,v in (attrs or {}).items()})
    if text is not None:
        e.text = str(text)
    return e

def mm(v):
    return f'{float(v):.6f}mm'

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def json_write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n',encoding='utf-8')

def load_csv(name):
    with (ROOT/'SOURCE_DATA'/name).open(encoding='utf-8',newline='') as f:
        return list(csv.DictReader(f))

def ref(file, row, field):
    return {'source_file':file, 'row_index_zero_based':row, 'field':field}

class Scene:
    def __init__(self, number, width, height, description):
        self.number = number
        self.width = width
        self.height = height
        self.description = description
        self.objects = []
        self.values = []

    def add(self, kind, name, role, **kw):
        object_id = f'fig{self.number}_{name}'
        assert all(o['id'] != object_id for o in self.objects), object_id
        o = {'id':object_id, 'type':kind, 'role':role, **kw}
        self.objects.append(o)
        return object_id

    def line(self, name, x1, y1, x2, y2, color=INK, weight=.18, role='line', source=None):
        return self.add('line',name,role,x1=x1,y1=y1,x2=x2,y2=y2,stroke=color,stroke_width=weight,source=source)

    def rect(self,name,x,y,w,h,fill,stroke=INK,weight=.15,role='bar',source=None):
        return self.add('rect',name,role,x=x,y=y,width=w,height=h,fill=fill,stroke=stroke,stroke_width=weight,source=source)

    def ellipse(self,name,x,y,w,h,fill,stroke=INK,weight=.15,role='marker',source=None):
        return self.add('ellipse',name,role,x=x,y=y,width=w,height=h,fill=fill,stroke=stroke,stroke_width=weight,source=source)

    def polygon(self,name,points,fill,stroke=INK,weight=.15,role='arrowhead',source=None):
        return self.add('polygon',name,role,points=points,fill=fill,stroke=stroke,stroke_width=weight,source=source)

    def text(self,name,text,x,y,w,h=4.3,size=8.5,bold=False,align='left',role='label',source=None):
        assert '\n' not in text, 'Each text line is a separate editable frame.'
        return self.add('text',name,role,text=text,x=x,y=y,width=w,height=h,font_family=FONT,
                        font_size_pt=size,font_weight='bold' if bold else 'normal',align=align,
                        color=INK,source=source)

    def arrow(self,name,x1,y1,x2,y2):
        self.line(name+'_shaft',x1,y1,x2,y2,weight=.28,role='connector')
        dx,dy=x2-x1,y2-y1
        ln=math.hypot(dx,dy); ux,uy=dx/ln,dy/ln
        self.polygon(name+'_head',[(x2,y2),(x2-1.8*ux+0.85*uy,y2-1.8*uy-0.85*ux),
                     (x2-1.8*ux-0.85*uy,y2-1.8*uy+0.85*ux)],INK,weight=.1)

    def hatched_bar(self,name,x,y,w,h,fill,pattern,source=None):
        first=len(self.objects)
        self.rect(name,x,y,w,h,fill,source=source)
        # Hatch strokes are separate native line objects; nothing is an image fill.
        if pattern == 'none':
            return
        spacing=2.25
        if pattern in ('diagonal','cross'):
            for direction in ([1,-1] if pattern=='cross' else [1]):
                k=0; a=-h
                while a < w:
                    # Rising diagonal in local coordinates, analytically clipped.
                    lo=max(0,-a); hi=min(h,w-a)
                    if hi > lo+.05:
                        xx1,xx2=x+a+lo,x+a+hi
                        yy1,yy2=(y+h-lo,y+h-hi) if direction==1 else (y+lo,y+hi)
                        self.line(f'{name}_hatch_{direction}_{k}',xx1,yy1,xx2,yy2,
                                  color=INK,weight=.1,role='hatch',source=source)
                    k+=1; a+=spacing
        elif pattern == 'horizontal':
            v=1.6; k=0
            while v<h-.3:
                self.line(f'{name}_hatch_{k}',x,y+v,x+w,y+v,color=INK,weight=.1,role='hatch',source=source)
                v+=1.8; k+=1
        else:
            raise ValueError(pattern)
        # Outline is repeated last so every clipped hatch endpoint remains tidy.
        self.rect(name+'_outline',x,y,w,h,'none',weight=.15,role='bar_outline',source=source)
        for obj in self.objects[first:]:
            obj['native_group']=f'fig{self.number}_{name}_editable_bar_group'

    def value(self,object_id,exact,display,source,transform):
        self.values.append({'object_id':object_id,'source_exact':str(exact),'display':display,
                            'source':source,'geometry_transform':transform})

    def axis(self,name,x,y,width,maximum,ticks,label,label_y=None,tick_percent=False,grid_top=None):
        if grid_top is not None:
            for j,t in enumerate(ticks):
                if t:
                    px=x+width*t/maximum
                    self.line(f'{name}_grid_{j}',px,grid_top,px,y,color=GRID,weight=.1,role='grid')
        self.line(name+'_axis',x,y,x+width,y,weight=.2,role='axis')
        for j,t in enumerate(ticks):
            px=x+width*t/maximum
            self.line(f'{name}_tick_{j}',px,y,px,y+1.25,weight=.18,role='tick')
            txt=f'{100*t:.0f}' if tick_percent else (f'{t:.1f}' if maximum<=1 else str(t))
            self.text(f'{name}_tick_label_{j}',txt,px-5,y+1.5,10,size=8.2,align='center',role='tick_label')
        self.text(name+'_axis_label',label,2,label_y if label_y is not None else y+7,115,
                  size=8.5,align='center',role='axis_label')

    def dictionary(self):
        return {'schema':'R15_NATIVE_FIGURE_SCENE_1','figure':self.number,'width_mm':self.width,
                'height_mm':self.height,'description':self.description,'objects':self.objects,
                'value_trace':self.values,'object_count':len(self.objects),'object_types':dict(Counter(o['type'] for o in self.objects))}


def fig1():
    s=Scene(1,119,111,'Objective-conditioned measurement and decision architecture')
    panels=[('state',5,5,71,17,'#e9f0f7','State register',
             ['Mutually exclusive provider or','technology states']),
            ('classes',5,31,71,17,'#e9f3ec','Candidate positive classes',
             ['Definitions as subsets of','retained states']),
            ('indicator',5,57,71,17,'#faf6df','Indicator rates',
             ['Levels, composition and ordering']),
            ('objective',82,31,32,43,'#f1f1f1','Declared objective',
             ['Common action rule','Threshold, rank or','robust ordering']),
            ('audit',5,88,109,18,'#eaf2f5','Decision audit',
             ['Selected sets, entries, exits, loss and indeterminacy'])]
    for name,x,y,w,h,fill,title,sub in panels:
        s.rect(name+'_box',x,y,w,h,fill,weight=.24,role='architecture_node')
        s.text(name+'_title',title,x+1,y+1.4,w-2,size=9.0,bold=True,align='center',role='architecture_text')
        if name=='objective':
            ys=[y+13,y+23,y+28]
            for j,(t,yy) in enumerate(zip(sub,ys)):
                s.text(name+f'_detail_{j}',t,x+.6,yy,w-1.2,size=8.2,bold=(j==0),align='center',role='architecture_text')
        else:
            for j,t in enumerate(sub):
                s.text(name+f'_detail_{j}',t,x+1,y+6.5+j*4.3,w-2,size=8.5,align='center',role='architecture_text')
    s.arrow('state_to_classes',40.5,22,40.5,30.5)
    s.arrow('classes_to_indicator',40.5,48,40.5,56.5)
    s.arrow('indicator_to_audit',40.5,74,40.5,87.5)
    s.arrow('objective_to_audit',98,74,98,87.5)
    return s


def fig2():
    file='Figure_2_ablation_event_frequencies.csv'; rows=load_csv(file)
    s=Scene(2,119,145,'Overlapping event fractions in the preserved deterministic design register')
    color_map={'Level':BLUE,'Meaning':GREEN,'Meaning/rank':CYAN,'Action':GOLD,'Rank':RED}
    pattern_map={'Level':'diagonal','Meaning':'horizontal','Meaning/rank':'cross','Action':'diagonal','Rank':'horizontal'}
    for i,r in enumerate(rows):
        y=4+i*18
        source=ref(file,i,'fraction'); v=Fraction(r['fraction'])
        s.text(f'event_{i}_label',r['diagnostic'],4,y,111,size=8.5,source=ref(file,i,'diagnostic'))
        s.hatched_bar(f'event_{i}',4,y+6.0,78*float(v),5,color_map[r['family']],pattern_map[r['family']],source=source)
        disp=f'{float(v)*100:.1f}%'
        s.text(f'event_{i}_percent',disp,83,y+6,14,size=8.3,align='right',source=source)
        ratio=f"{r['events']}/{r['cases']}"
        s.text(f'event_{i}_count',ratio,98,y+6,18,size=8.0,align='right',source={'source_file':file,'row_index_zero_based':i,'fields':['events','cases']})
        s.value(f'fig2_event_{i}',r['fraction'],disp,source,{'property':'width','axis_origin_mm':4,'axis_span_mm':78,'axis_maximum':'1'})
    s.axis('fraction',4,131,78,1,[0,.2,.4,.6,.8,1],
           'Share of registered design cases (%)',label_y=138,tick_percent=True)
    return s


def fig3():
    s=Scene(3,119,191,'Preserved synthetic reference-cell diagnostic summaries')
    labels=['Integrated','Specialised','Digitally enabled']
    fa='Figure_3_panel_A_reference_rates_mae.csv'; a=load_csv(fa)
    assert [r['definition'] for r in a]==labels
    s.text('panel_a','a',3,1,5,size=9,bold=True,role='panel_label')
    for i,r in enumerate(a):
        y=12+13*i; v=Fraction(r['population_rate']); src=ref(fa,i,'population_rate')
        if i==2:
            s.text(f'a_label_{i}_1','Digitally',3,y-1,27,source=ref(fa,i,'definition'))
            s.text(f'a_label_{i}_2','enabled',3,y+3.3,27,source=ref(fa,i,'definition'))
        else:
            s.text(f'a_label_{i}',labels[i],3,y,27,source=ref(fa,i,'definition'))
        s.hatched_bar(f'a_rate_{i}',32,y,57*float(v)/.8,4.8,COLORS[i],['diagonal','horizontal','cross'][i],src)
        disp=f'{float(v)*100:.2f}%'
        s.text(f'a_rate_value_{i}',disp,91,y-.7,25,size=8.4,source=src)
        mae=f"MAE {float(r['observed_mae']):.3f}"
        s.text(f'a_mae_{i}',mae,91,y+3.8,25,size=8.0,source=ref(fa,i,'observed_mae'))
        s.value(f'fig3_a_rate_{i}',r['population_rate'],disp,src,{'property':'width','axis_origin_mm':32,'axis_span_mm':57,'axis_maximum':'0.8'})
        s.value(f'fig3_a_mae_{i}',r['observed_mae'],mae,ref(fa,i,'observed_mae'),{'property':'text','rounding':'three decimals'})
    s.axis('a',32,48,57,.8,[0,.2,.4,.6,.8],'Population rate (%)',label_y=56,tick_percent=True)
    fb='Figure_3_panel_B_reference_ordering.csv'; b=load_csv(fb)
    s.text('panel_b','b',3,65,5,size=9,bold=True,role='panel_label')
    s.ellipse('b_legend_circle',12,66.3,2,2,BLUE)
    s.text('b_legend_circle_text','Strict reversal',16,65.2,30,size=8.2,role='legend_text')
    s.rect('b_legend_square',54,66.3,2,2,GOLD,role='legend_marker')
    s.text('b_legend_square_text','Highest top-three churn',58,65.2,58,size=8.2,role='legend_text')
    contrasts=[('Integrated →','specialised'),('Specialised →','digitally enabled'),('Integrated →','digitally enabled')]
    for i,r in enumerate(b):
        y=80+i*13
        for j,txt in enumerate(contrasts[i]):
            s.text(f'b_label_{i}_{j}',txt,3,y-3.2+j*4.3,32,size=8.1,source=ref(fb,i,'contrast'))
        vr=Fraction(r['strict_reversal_share']); vc=Fraction(r['highest_top3_churn'])
        x1=37+74*float(vr)/.6; x2=37+74*float(vc)/.6
        s.line(f'b_connection_{i}',x1,y+1,x2,y+1,color='#999999',weight=.5,role='comparison_connector')
        id1=s.ellipse(f'b_reversal_{i}',x1-1.1,y-.1,2.2,2.2,BLUE,source=ref(fb,i,'strict_reversal_share'))
        id2=s.rect(f'b_churn_{i}',x2-1.1,y-.1,2.2,2.2,GOLD,role='marker',source=ref(fb,i,'highest_top3_churn'))
        s.value(id1,r['strict_reversal_share'],None,ref(fb,i,'strict_reversal_share'),{'property':'centre_x','axis_origin_mm':37,'axis_span_mm':74,'axis_maximum':'0.6'})
        s.value(id2,r['highest_top3_churn'],None,ref(fb,i,'highest_top3_churn'),{'property':'centre_x','axis_origin_mm':37,'axis_span_mm':74,'axis_maximum':'0.6'})
    s.axis('b',37,114,74,.6,[0,.1,.2,.3,.4,.5,.6],'Strict-reversal share / highest top-three churn',label_y=122)
    fc='Figure_3_panel_C_unmatched_objective.csv'; c=load_csv(fc)
    assert [r['definition'] for r in c]==labels
    s.text('panel_c','c',3,132,5,size=9,bold=True,role='panel_label')
    for i,r in enumerate(c):
        y=143+12*i; v=Fraction(r['semantic_mismatch_mass']); src=ref(fc,i,'semantic_mismatch_mass')
        if i==2:
            s.text(f'c_label_{i}_1','Digitally',3,y-1,27)
            s.text(f'c_label_{i}_2','enabled',3,y+3.3,27)
        else:
            s.text(f'c_label_{i}',labels[i],3,y,27)
        w=60*float(v)/.7
        s.hatched_bar(f'c_loss_{i}',32,y,w,4.8,COLORS[i],['diagonal','horizontal','cross'][i],src)
        disp=f'{float(v)*100:.1f}%'
        s.text(f'c_loss_value_{i}',disp,33+w,y,13,size=8.1,source=src)
        direction=r['mismatch_type'].split()
        for j,t in enumerate(direction):
            s.text(f'c_direction_{i}_{j}',t,96,y-1+j*4.0,20,size=8.0,source=ref(fc,i,'mismatch_type'))
        s.value(f'fig3_c_loss_{i}',r['semantic_mismatch_mass'],disp,src,{'property':'width','axis_origin_mm':32,'axis_span_mm':60,'axis_maximum':'0.7'})
    s.axis('c',32,178,60,.7,[0,.1,.2,.3,.4,.5,.6,.7],
           'Share of total synthetic state mass (%)',label_y=186,tick_percent=True)
    return s


def fig4():
    file='Figure_4_unresolved_determinacy.csv'; rows=load_csv(file)
    s=Scene(4,119,110,'Preserved synthetic strict-order determinacy by unresolved-state profile')
    x0,y0,hh=15,80,68
    s.text('y_axis_label','Share of strictly orderable pairs',15,1,100,size=8.5,role='axis_label')
    for j,v in enumerate([0,.2,.4,.6,.8,1]):
        yy=y0-hh*v
        s.line(f'y_grid_{j}',x0,yy,115,yy,color=GRID,weight=.1,role='grid')
        s.line(f'y_tick_{j}',x0-1,yy,x0,yy,role='tick')
        s.text(f'y_tick_label_{j}',f'{v:.1f}',1,yy-2,11,size=8.2,align='right',role='tick_label')
    s.line('y_axis',x0,y0-hh,x0,y0,weight=.2,role='axis')
    s.line('x_axis',x0,y0,115,y0,weight=.2,role='axis')
    definitions=['Integrated','Specialised','Digitally enabled']
    profiles=['No unresolved','Independent ≈5% unresolved','State-dependent unresolved']
    for di,definition in enumerate(definitions):
        centre=[30,64,98][di]
        for pi,profile in enumerate(profiles):
            i=next(j for j,r in enumerate(rows) if r['definition']==definition and r['profile']==profile)
            r=rows[i]; v=Fraction(r['determinate_pair_share']); src=ref(file,i,'determinate_pair_share')
            x=centre-12+pi*8; h=hh*float(v)
            s.hatched_bar(f'd{di}_p{pi}',x,y0-h,7,h,[BLUE,GOLD,GREEN][pi],['diagonal','horizontal','cross'][pi],src)
            disp=f'{float(v):.3f}'
            s.text(f'd{di}_p{pi}_value',disp,x-1.8,y0-h-5,10.6,size=8.1,align='center',source=src)
            s.value(f'fig4_d{di}_p{pi}',r['determinate_pair_share'],disp,src,{'property':'height','axis_bottom_mm':y0,'axis_span_mm':hh,'axis_maximum':'1'})
        lab=definition.split() if di==2 else [definition]
        for j,txt in enumerate(lab):
            s.text(f'x_label_{di}_{j}',txt,centre-15,83+j*4.4,30,size=8.5,align='center',role='category_label')
    legend=[(4,BLUE,'diagonal','No unresolved',24),(39,GOLD,'horizontal','Independent ≈5%',30),(81,GREEN,'cross','State-dependent',31)]
    for i,(x,col,pat,txt,w) in enumerate(legend):
        s.hatched_bar(f'legend_{i}',x,101.5,3,3,col,pat)
        s.text(f'legend_{i}_text',txt,x+4,100.8,w,size=8.0,role='legend_text')
    return s


def fig5():
    file='R14_1_OA_REPORTING_TABLES.json'
    data=json.loads((ROOT/'SOURCE_DATA'/file).read_text(encoding='utf-8'))
    s=Scene(5,119,143,'OA definition comparisons with a declared publisher-availability objective')
    specs=[('a',0,'semantic',None,'Mean semantic loss (equal country weights)',.32,[0,.1,.2,.3]),
           ('b',47,'objective_comparisons','lowest_3','Action loss per country: lowest three',.25,[0,.05,.10,.15,.20,.25]),
           ('c',94,'objective_comparisons','highest_3','Action loss per country: highest three',.25,[0,.05,.10,.15,.20,.25])]
    for panel,base,family,rule,label,maximum,ticks in specs:
        s.text(f'{panel}_panel',panel,3,base+1,5,size=9,bold=True,role='panel_label')
        for i,definition in enumerate(['D1','D2','D3']):
            row_index=next(j for j,r in enumerate(data[family]) if r['definition']==definition and r['cost']=='equal_costs' and (rule is None or r['rule']==rule))
            r=data[family][row_index]
            field='loss_exact' if family=='semantic' else 'action_loss_per_unit'
            displayfield='loss' if family=='semantic' else 'action_loss_per_unit_display'
            exact=r[field]; v=Fraction(exact); display=r[displayfield]
            source={'source_file':file,'json_path':f'/{family}/{row_index}/{field}','display_path':f'/{family}/{row_index}/{displayfield}'}
            y=base+11+9*i
            s.text(f'{panel}_{definition}_label',definition,6,y,11,size=8.7)
            s.hatched_bar(f'{panel}_{definition}',20,y,73*float(v)/maximum,4.6,COLORS[i],['diagonal','horizontal','cross'][i],source)
            s.text(f'{panel}_{definition}_value',display,96,y,21,size=8.3,source=source)
            s.value(f'fig5_{panel}_{definition}',exact,display,source,{'property':'width','axis_origin_mm':20,'axis_span_mm':73,'axis_maximum':str(maximum)})
        # Two decimal tick labels avoid ambiguities at 0.05 intervals.
        s.line(f'{panel}_axis',20,base+37,93,base+37,weight=.2,role='axis')
        for j,t in enumerate(ticks):
            x=20+73*t/maximum
            s.line(f'{panel}_tick_{j}',x,base+37,x,base+38.1,role='tick')
            s.text(f'{panel}_tick_label_{j}',f'{t:.2f}',x-5,base+38.3,10,size=8.0,align='center',role='tick_label')
        s.text(f'{panel}_axis_label',label,2,base+43,115,size=8.4,align='center',role='axis_label')
    return s


def write_fodg(scene,path):
    doc=ET.Element(q('office:document'),{q('office:version'):'1.3',q('office:mimetype'):'application/vnd.oasis.opendocument.graphics'})
    meta=el(doc,'office:meta')
    el(meta,'dc:title',text=f'Fig. {scene.number}: {scene.description}')
    el(meta,'dc:description',text='Native editable vector objects reconstructed from preserved public figure data; no new Monte Carlo run or withheld FAT output. R15.')
    faces=el(doc,'office:font-face-decls')
    el(faces,'style:font-face',{'style:name':FONT,'svg:font-family':FONT,'style:font-family-generic':'swiss','style:font-pitch':'variable'})
    styles=el(doc,'office:styles')
    default=el(styles,'style:default-style',{'style:family':'graphic'})
    el(default,'style:graphic-properties',{'draw:fill':'none','draw:stroke':'solid','svg:stroke-color':INK,'svg:stroke-width':'.18mm'})
    automatic=el(doc,'office:automatic-styles')
    # Named per-object styles survive editing independently. No shared fill style.
    for o in scene.objects:
        st=el(styles,'style:style',{'style:name':'G_'+o['id'],'style:display-name':o['id'],'style:family':'graphic'})
        gp={'draw:fill':'none' if o.get('fill','none')=='none' else 'solid',
            'draw:stroke':'none' if o['type']=='text' or o.get('stroke')=='none' else 'solid',
            'svg:stroke-color':o.get('stroke',INK),'svg:stroke-width':mm(o.get('stroke_width',.18)),
            'fo:padding':'0mm','draw:textarea-vertical-align':'middle',
            'draw:textarea-horizontal-align':o.get('align','left'),
            'draw:auto-grow-height':'false','draw:auto-grow-width':'false',
            'draw:fit-to-size':'false','style:wrap':'none'}
        if o.get('fill','none')!='none':
            gp['draw:fill-color']=o['fill']
        el(st,'style:graphic-properties',gp)
        if o['type']=='text':
            paragraph_properties={'fo:text-align':{'left':'start','right':'end','center':'center'}[o['align']],
               'fo:margin-left':'0mm','fo:margin-right':'0mm','fo:margin-top':'0mm','fo:margin-bottom':'0mm','fo:line-height':'100%'}
            text_properties={'style:font-name':FONT,'fo:font-family':FONT,'fo:font-size':f"{o['font_size_pt']}pt",
               'fo:font-weight':o['font_weight'],'fo:color':o['color']}
            el(st,'style:paragraph-properties',paragraph_properties)
            el(st,'style:text-properties',text_properties)
            ps=el(automatic,'style:style',{'style:name':'P_'+o['id'],'style:family':'paragraph'})
            el(ps,'style:paragraph-properties',paragraph_properties)
            el(ps,'style:text-properties',text_properties)
            ts=el(automatic,'style:style',{'style:name':'T_'+o['id'],'style:family':'text'})
            el(ts,'style:text-properties',text_properties)
    layout=el(automatic,'style:page-layout',{'style:name':'PM'})
    el(layout,'style:page-layout-properties',{'fo:page-width':mm(scene.width),'fo:page-height':mm(scene.height),'fo:margin':'0mm',
       'style:print-orientation':'portrait' if scene.height>scene.width else 'landscape'})
    masters=el(doc,'office:master-styles')
    el(masters,'style:master-page',{'style:name':'Default','style:page-layout-name':'PM'})
    drawing=el(el(doc,'office:body'),'office:drawing')
    page=el(drawing,'draw:page',{'draw:name':f'Fig{scene.number}','draw:master-page-name':'Default'})
    groups={}
    for o in scene.objects:
        parent=page
        if o.get('native_group'):
            if o['native_group'] not in groups:
                groups[o['native_group']]=el(page,'draw:g',{'draw:name':o['native_group']})
            parent=groups[o['native_group']]
        attrs={'draw:name':o['id'],'draw:style-name':'G_'+o['id']}
        if o['type']=='line':
            attrs.update({f'svg:{k}':mm(o[k]) for k in ('x1','y1','x2','y2')})
            el(parent,'draw:line',attrs)
        elif o['type']=='polygon':
            xs,ys=zip(*o['points']); xmin,ymin=min(xs),min(ys); w,h=max(xs)-xmin,max(ys)-ymin
            attrs.update({'svg:x':mm(xmin),'svg:y':mm(ymin),'svg:width':mm(w),'svg:height':mm(h),
                         'svg:viewBox':'0 0 10000 10000','draw:points':' '.join(f'{round((x-xmin)/w*10000)},{round((y-ymin)/h*10000)}' for x,y in o['points'])})
            el(parent,'draw:polygon',attrs)
        else:
            attrs.update({f'svg:{k}':mm(o[k]) for k in ('x','y','width','height')})
            if o['type']=='text':
                frame=el(parent,'draw:frame',attrs); box=el(frame,'draw:text-box')
                para=el(box,'text:p',{'text:style-name':'P_'+o['id']})
                el(para,'text:span',{'text:style-name':'T_'+o['id']},o['text'])
            else:
                el(parent,'draw:'+o['type'],attrs)
    ET.indent(doc,space=' ')
    ET.ElementTree(doc).write(path,encoding='utf-8',xml_declaration=True)


def write_svg(scene,path):
    # A separate editable vector source, not an image embedded in the ODG.
    ns='http://www.w3.org/2000/svg'
    doc=ET.Element('svg',{'xmlns':ns,'version':'1.1','width':mm(scene.width),'height':mm(scene.height),
                       'viewBox':f'0 0 {scene.width} {scene.height}','role':'img'})
    ET.SubElement(doc,'title').text=f'Fig. {scene.number}: {scene.description}'
    ET.SubElement(doc,'desc').text='All labels are editable SVG text; all data marks are native vector primitives. See the adjacent object and value manifests.'
    groups={}
    for o in scene.objects:
        parent=doc
        if o.get('native_group'):
            if o['native_group'] not in groups:
                groups[o['native_group']]=ET.SubElement(doc,'g',{'id':o['native_group'],'data-role':'editable_bar_group'})
            parent=groups[o['native_group']]
        attrs={'id':o['id'],'data-role':o['role']}
        if o['type']=='text':
            attrs.update({'x':str(o['x']+({'left':0,'center':.5,'right':1}[o['align']])*o['width']),
                          'y':str(o['y']+o['height']/2+o['font_size_pt']*25.4/72*.34),
                          'font-family':FONT,'font-size':str(o['font_size_pt']*25.4/72),'data-font-size-pt':str(o['font_size_pt']),'font-weight':o['font_weight'],
                          'fill':o['color'],'text-anchor':{'left':'start','right':'end','center':'middle'}[o['align']]})
            ET.SubElement(parent,'text',attrs).text=o['text']
        else:
            attrs.update({'fill':o.get('fill','none'),'stroke':o.get('stroke',INK),'stroke-width':str(o.get('stroke_width',.18))})
            if o['type']=='line':
                attrs.update({k:str(o[k]) for k in ('x1','y1','x2','y2')}); typ='line'
            elif o['type']=='rect':
                attrs.update({k:str(o[k]) for k in ('x','y','width','height')}); typ='rect'
            elif o['type']=='ellipse':
                attrs.update({'cx':str(o['x']+o['width']/2),'cy':str(o['y']+o['height']/2),
                              'rx':str(o['width']/2),'ry':str(o['height']/2)}); typ='ellipse'
            elif o['type']=='polygon':
                attrs['points']=' '.join(f'{x},{y}' for x,y in o['points']); typ='polygon'
            else:
                raise ValueError(o['type'])
            ET.SubElement(parent,typ,attrs)
    ET.indent(doc,space=' ')
    ET.ElementTree(doc).write(path,encoding='utf-8',xml_declaration=True)


def run(args,timeout=55):
    p=subprocess.run([str(a) for a in args],capture_output=True,text=True,timeout=timeout)
    if p.returncode:
        raise RuntimeError(p.stdout+'\n'+p.stderr)
    return {'command':[str(a) for a in args],'returncode':p.returncode,'stdout':p.stdout.strip(),'stderr':p.stderr.strip()}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--only',type=int,choices=range(1,6))
    p.add_argument('--scenes-only',action='store_true')
    args=p.parse_args()
    for filename,digest in EXPECTED_SOURCE_SHA256.items():
        actual=sha(ROOT/'SOURCE_DATA'/filename)
        if actual!=digest:
            raise ValueError(f'Frozen public figure source identity differs: {filename}: {actual}')
    folders=['ODG_NATIVE','SVG_EDITABLE','PDF_VECTOR','EPS_VECTOR','PNG_600','TIFF','NATIVE_SOURCE','CONTROL','QA_PREVIEWS']
    for f in folders:
        (ROOT/f).mkdir(exist_ok=True)
    scenes=[fn() for fn in (fig1,fig2,fig3,fig4,fig5)]
    if args.only:
        scenes=[s for s in scenes if s.number==args.only]
    commands=[]; summaries=[]
    for scene in scenes:
        stem=f'Fig{scene.number}'
        write_fodg(scene,ROOT/'NATIVE_SOURCE'/f'{stem}.fodg')
        write_svg(scene,ROOT/'SVG_EDITABLE'/f'{stem}.svg')
        json_write(ROOT/'CONTROL'/f'{stem}_OBJECTS_AND_VALUES.json',scene.dictionary())
        if args.scenes_only:
            continue
        lo=shutil.which('soffice')
        if not lo:
            raise RuntimeError('LibreOffice soffice is required for native ODG/PDF export.')
        profile=(ROOT/'_runtime'/f'lo_build_{scene.number}').resolve()
        cmd=[lo,'-env:UserInstallation='+profile.as_uri(),'--headless','--convert-to','odg:draw8','--outdir',ROOT/'ODG_NATIVE',ROOT/'NATIVE_SOURCE'/f'{stem}.fodg']
        commands.append(run(cmd))
        odg=ROOT/'ODG_NATIVE'/f'{stem}.odg'
        assert odg.is_file(), 'ODG import did not create its expected output.'
        commands.append(run([lo,'-env:UserInstallation='+profile.as_uri(),'--headless','--convert-to','pdf:draw_pdf_Export','--outdir',ROOT/'PDF_VECTOR',odg]))
        pdf=ROOT/'PDF_VECTOR'/f'{stem}.pdf'
        assert pdf.is_file()
        eps=ROOT/'EPS_VECTOR'/f'{stem}.eps'
        commands.append(run(['pdftops','-eps','-level3',pdf,eps]))
        import fitz
        from PIL import Image
        with fitz.open(pdf) as d:
            assert len(d)==1
            for dpi,folder,format in [(600,'PNG_600','PNG'),(200,'QA_PREVIEWS','PNG')]:
                pix=d[0].get_pixmap(matrix=fitz.Matrix(dpi/72,dpi/72),alpha=False)
                im=Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
                im.save(ROOT/folder/f'{stem}.png',format=format,dpi=(dpi,dpi))
            dpi=1200 if scene.number==1 else 600
            pix=d[0].get_pixmap(matrix=fitz.Matrix(dpi/72,dpi/72),alpha=False)
            im=Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
            im.save(ROOT/'TIFF'/f'{stem}.tif',compression='tiff_lzw',dpi=(dpi,dpi))
            summaries.append({'figure':scene.number,'page_mm':[scene.width,scene.height],
                'object_count':len(scene.objects),'value_trace_count':len(scene.values),
                'pdf_pages':len(d),'pdf_text_nonempty':bool(d[0].get_text().strip()),
                'pdf_embedded_images':len(d[0].get_images()),
                'pdf_sha256':sha(pdf),'odg_sha256':sha(odg),'svg_sha256':sha(ROOT/'SVG_EDITABLE'/f'{stem}.svg')})
    result={'status':'BUILT_VISUAL_AND_EDITABILITY_REVIEW_PENDING','figures':summaries,'commands':commands,
       'scope':'Public historical figures 1–4 reconstructed without simulations; figure 5 uses exact public R14.1 OA reporting. No new FAT numerical output.',
       'runtime':{'python':sys.version,'platform':platform.platform()},
       'inputs':[{ 'path':str(p.relative_to(ROOT)),'sha256':sha(p)} for p in sorted((ROOT/'SOURCE_DATA').iterdir()) if p.is_file()],
       'no_native_windows_execution':True,'no_scientific_simulations_run':True}
    filename=('FIGURE_SCENES_ONLY.json' if args.scenes_only else
              (f'FIGURE_BUILD_{args.only}.json' if args.only else 'FIGURE_BUILD.json'))
    json_write(ROOT/'CONTROL'/filename,result)
    print(json.dumps({'status':result['status'],'figures':summaries},indent=2))

if __name__=='__main__':
    main()
