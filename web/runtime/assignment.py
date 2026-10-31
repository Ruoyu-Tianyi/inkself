"""Bounded Markdown answer-sheet layout using reviewed personal handwriting.

Formatting only: no answer generation, code execution or arithmetic rewriting.
Tables and plain-text trees retain their rows; equations wrap at source spaces.
"""
from __future__ import annotations
import hashlib,json,math,re
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageOps

VERSION='assignment-layout-2'
PAGE_W,PAGE_H,MARGIN=1240,1754,80
WIDTH=PAGE_W-2*MARGIN


def _plain(text):
    from web.markdown_document import parse_markdown
    if not text.strip():return ''
    text=re.sub(r'\*\*([^*]+)\*\*',r'\1',text)
    text=parse_markdown(text,'answer.md')['text']
    text=text.replace('¥','CNY ').replace('−','-').replace('–','-').replace('—','-').replace('⇒',' so ')
    text=re.sub(r'^\s*\(([a-z])\)\s*',r'\1. ',text)
    return text


def parse_assignment(source):
    if not isinstance(source,str) or not source.strip() or len(source)>20000:
        raise ValueError('作业答卷需包含 1 至 20,000 个字符。')
    if any(ord(c)<32 and c not in '\n\r\t' for c in source):raise ValueError('答卷含不支持的控制字符。')
    lines=source.replace('\r\n','\n').replace('\r','\n').split('\n')
    blocks=[];paragraph=[];question=None;index=0
    def add(kind,**values):
        blocks.append({'kind':kind,'question':question,**values})
        if len(blocks)>600:raise ValueError('答卷块数过多，请拆分文档。')
    def flush():
        if paragraph:
            add('paragraph',text=_plain(' '.join(paragraph)));paragraph.clear()
    def cells(line):
        return [re.sub(r'\*\*(.*?)\*\*',r'\1',v.strip()) for v in line.strip().strip('|').split('|')]
    while index<len(lines):
        line=lines[index]
        heading=re.fullmatch(r'\s*#{1,6}\s+(\d+(?:[–-]\d+)?)[.)]?\s*',line)
        if heading:
            flush();question=heading[1].replace('–','-');add('heading',text=question+'.');index+=1;continue
        if re.match(r'^\s*```',line):
            flush()
            if line.strip() not in ('```text','```'):raise ValueError('作业模式只接受 text 决策树代码块。')
            tree=[];index+=1
            while index<len(lines) and lines[index].strip()!='```':
                tree.append(lines[index]);index+=1
            if index==len(lines):raise ValueError('决策树代码块未闭合。')
            if not tree or len(tree)>60 or not any('├' in row or '└' in row for row in tree):raise ValueError('text 块必须是含分支线的文本树。')
            rows=[]
            for row in tree:
                if not row.strip():continue
                prefix=re.match(r'^[ │├└─\t]*',row)[0]
                body=row[len(prefix):].strip()
                if not body:continue
                depth=max(0,(len(prefix.expandtabs(4))+1)//4)
                if depth>12:raise ValueError('树形层级过深。')
                rows.append({'depth':depth,'text':_plain(body),'guides':[i//4 for i,c in enumerate(prefix) if c=='│']})
            add('tree',rows=rows);index+=1;continue
        if index+1<len(lines) and '|' in line and re.fullmatch(r'\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*',lines[index+1]):
            flush();headers=cells(line);rows=[];index+=2
            if not 2<=len(headers)<=8:raise ValueError('表格需为 2 至 8 列。')
            while index<len(lines) and '|' in lines[index] and lines[index].strip():
                row=cells(lines[index])
                if len(row)!=len(headers):raise ValueError('表格列数不一致。')
                rows.append(row);index+=1
            if not rows or len(rows)>100:raise ValueError('表格需为 1 至 100 行。')
            add('table',headers=[_plain(c) for c in headers],rows=[[_plain(c) for c in row] for row in rows]);continue
        choice=re.fullmatch(r'\s*(\d+)\.\s+([A-Z])\s*',line)
        if choice:
            flush()
            if blocks and blocks[-1]['kind']=='choices' and blocks[-1]['question']==question:
                blocks[-1]['choices'].append([choice[1],choice[2]])
            else:add('choices',choices=[[choice[1],choice[2]]])
            index+=1;continue
        if not line.strip():flush()
        elif re.match(r'^\s*[-+]\s+\S',line):
            flush();add('paragraph',text=_plain(line))
        else:paragraph.append(line.strip())
        index+=1
    flush()
    if not blocks:raise ValueError('答卷没有可排版内容。')
    return {'version':VERSION,'blocks':blocks,'source_sha256':hashlib.sha256(source.encode()).hexdigest(),
        'warnings':['作业模式只调整排版，不校验或改写答案；人民币符号写为 CNY。'],
        'summary':{kind:sum(b['kind']==kind for b in blocks) for kind in ('heading','paragraph','table','tree','choices')}}


def _inline(text):
    # Plain A_S / EMV_test,gross notation becomes a real subscript. Explicit
    # LaTeX regions are left untouched.
    parts=re.split(r'(\$\$.*?\$\$|\$[^$]*\$|\\\(.*?\\\)|\\\[.*?\\\])',text,flags=re.S)
    for i in range(0,len(parts),2):
        parts[i]=re.sub(r'\b([A-Za-z]+)_([A-Za-z0-9]+(?:,[A-Za-z]+)?)',
            lambda m:'$\\mathrm{'+m[1]+'}_{\\mathrm{'+m[2]+'}}$',parts[i])
    return ''.join(parts)


def preflight_assignment(source,bank,allow_supplemental=False,header=''):
    from .document_input import prepare_document
    from .math_glyphs import SUPPORTED_GLYPHS
    document=parse_assignment(source)
    allowed=set(bank['glyphs'])|set(' \n\t')
    if allow_supplemental:allowed|=set(SUPPORTED_GLYPHS)|{'*','□','○'}
    texts=[header] if header else []
    for b in document['blocks']:
        if 'text' in b:texts.append(b['text'])
        if b['kind']=='table':texts.extend(b['headers']);texts.extend(c for row in b['rows'] for c in row)
        if b['kind']=='tree':texts.extend(row['text'] for row in b['rows'])
        if b['kind']=='choices':texts.extend(n+'. '+a for n,a in b['choices'])
    for text in texts:
        # Validate explicit math separately; prose punctuation may be supplied by
        # the opted-in structural handwriting set, never a printed font.
        from .math_syntax import document_tokens,required_glyphs
        for token in document_tokens(_inline(text),True):
            required=required_glyphs(token['math']) if 'math' in token else set(token.get('text',''))
            missing=required-allowed
            if missing:raise ValueError('当前字迹不支持：'+''.join(sorted(missing))+'。可启用配套数学字形。')
    return document


class Writer:
    def __init__(self,bank,habit,spacing,seed,allow,line_spacing=1.6,spacing_options=None):
        from .spacing import normalize_spacing
        self.bank,self.habit,self.spacing,self.seed,self.allow=bank,habit,spacing,seed,allow
        self.settings=normalize_spacing(spacing_options)
        self.explicit_spacing=spacing_options is not None
        self.counter=0;self.references=set();self.supplements=set();self.baseline_lines=[]
        self.leading_factor=1.18*line_spacing/1.6

    def native(self,text):
        from .habit_model import habit_token
        from .reference_renderer import reference_token
        from .math_glyphs import supplemental_glyph
        if all(c in self.bank['glyphs'] for c in text):
            im,meta=habit_token(self.bank,self.habit,text,self.seed,self.counter,spacing=self.settings) if self.habit else reference_token(self.bank,text,spacing=self.settings,seed=self.seed,occurrence=self.counter)
            self.references.update(meta.get('references',[]));return im,meta['baseline'],meta.get('em_height',32)
        pieces=[]
        for part in re.findall(r'[A-Za-z0-9+%=.,;?:×÷-]+|.',text):
            if all(c in self.bank['glyphs'] for c in part):im,base,em=self.native(part)
            elif part in ('*','□','○') and self.allow:
                im=Image.new('L',(40,96),255);d=ImageDraw.Draw(im)
                if part=='*':
                    for a,b in [((20,32),(20,63)),((6,40),(35,57)),((6,57),(35,40))]:d.line((a,b),fill=45,width=3)
                elif part=='□':d.line([(6,40),(34,41),(33,70),(7,69),(6,40)],fill=45,width=3)
                else:d.ellipse((5,40,34,70),outline=45,width=3)
                base,em=78,96;self.supplements.add(part)
            elif self.allow:
                im,base,meta=supplemental_glyph(part,self.bank);base*=3;em=meta['em_height'];self.supplements.add(part)
            else:raise ValueError('缺少字形：'+part)
            f=96/em;im=im.resize((max(1,round(im.width*f)),max(1,round(im.height*f))),Image.Resampling.LANCZOS)
            pieces.append((im,round(base*f),0))
        im,base=self.join(pieces);return im,base,96

    @staticmethod
    def join(pieces,offsets=None):
        offsets=offsets if offsets is not None else [0]*len(pieces)
        ascent=max(p[1]-dy for p,dy in zip(pieces,offsets));descent=max(p[0].height-p[1]+dy for p,dy in zip(pieces,offsets))
        image=Image.new('L',(max(1,sum(p[0].width+p[2] for p in pieces)),max(1,ascent+descent+2)),255);x=0
        for (im,base,gap),dy in zip(pieces,offsets):x+=gap;image.paste(im,(x,ascent-base+dy));x+=im.width
        return image,ascent

    def tokens(self,text,em):
        from .math_syntax import document_tokens
        from .math_renderer import render_math
        result=[]
        for token in document_tokens(_inline(text),True):
            if token.get('newline'):result.append(None);continue
            if 'math' in token:
                im,meta=render_math(token['math'],self.bank,self.habit,self.seed,self.counter,self.allow,spacing=self.settings)
                base,original_em=meta['baseline'],meta['em_height'];self.supplements.update(meta['supplemental_math_glyphs']);self.references.update(meta['references'])
            else:im,base,original_em=self.native(token['text'])
            bounds=ImageOps.invert(im).point(lambda v:255 if v>45 else 0).getbbox()
            if not bounds:raise ValueError('空白字形。')
            im=im.crop((max(0,bounds[0]-1),0,min(im.width,bounds[2]+1),im.height))
            f=em/original_em
            im=im.resize((max(1,round(im.width*f)),max(1,round(im.height*f))),Image.Resampling.LANCZOS)
            result.append((im,round(base*f),token['space_before'],token.get('text','')));self.counter+=1
        return result

    def paragraph(self,text,em=39,width=WIDTH):
        from .word_spacing import sample_word_gaps
        from .spacing import adjust_gap
        from .baseline_rhythm import vertical_advance
        from .symbol_style import standalone_symbol,symbol_gap
        if len(text)>100:
            text=re.sub(r';\s+(?=[A-Za-z]+_[A-Za-z])',';\n',text)
        tokens=self.tokens(text,em);gaps=sample_word_gaps(self.spacing,len(tokens),self.seed,self.counter)
        lines=[];pending=[];used=0
        def finish_line():
            from .baseline_rhythm import word_offsets
            offsets=word_offsets([p[0].width for p in pending],[p[2] for p in pending],em,self.seed,len(self.baseline_lines),strength=self.settings['baseline']) if self.habit or self.explicit_spacing else [0]*len(pending)
            self.baseline_lines.append({'em':em,'offsets_px':offsets})
            lines.append(self.join(pending,offsets))
        for index,token in enumerate(tokens):
            if token is None:
                if pending:finish_line();pending=[];used=0
                continue
            im,base,space,label=token
            if im.width>width:raise ValueError('连续公式或单词过宽，请在运算符前后加空格或拆行。')
            gap=max(1,round(.08*em),round(adjust_gap(gaps[index]*em,self.spacing['mean']*em,self.settings,'word'))) if pending and space else 0
            previous_label=tokens[index-1][3] if index and tokens[index-1] else ''
            if gap and (standalone_symbol(label) or standalone_symbol(previous_label)):
                gap=max(1,round(symbol_gap(gap,self.settings,self.seed,self.counter,index)))
            if pending and used+gap+im.width>width:finish_line();pending=[];used=0;gap=0
            pending.append((im,base,gap));used+=gap+im.width
        if pending:finish_line()
        if not lines:raise ValueError('空白段落。')
        leading=[max(vertical_advance(em*self.leading_factor,self.settings,self.seed,len(self.baseline_lines)-len(lines)+i),im.height+6) for i,(im,_) in enumerate(lines)]
        image=Image.new('L',(width,sum(leading[:-1])+lines[-1][0].height),255);y=0
        for (im,_),advance in zip(lines,leading):image.paste(im,(0,y));y+=advance
        return image

    def table(self,block,em=30):
        data=[block['headers']]+block['rows'];count=len(data[0])
        def natural_width(text):
            pieces=[(t[0],t[1],round(em*.25) if t[2] else 0) for t in self.tokens(text,em) if t]
            return self.join(pieces)[0].width if pieces else 20
        natural=[max(natural_width(row[col]) for row in data)+24 for col in range(count)]
        available=WIDTH-12*count
        widths=np.asarray(natural,float)
        widths=widths/widths.sum()*available
        widths=np.maximum(widths,65);widths=widths/widths.sum()*WIDTH
        widths=[int(v) for v in widths];widths[-1]+=WIDTH-sum(widths)
        rows=[]
        for row in data:
            cells=[self.paragraph(text,em,width-18) if text else Image.new('L',(width-18,em),255) for text,width in zip(row,widths)]
            h=max(c.height for c in cells)+24;image=Image.new('L',(WIDTH,h),255);x=0
            for col,(cell,w) in enumerate(zip(cells,widths)):
                bounds=ImageOps.invert(cell).getbbox();ink_width=bounds[2] if bounds else 0
                # Crop only the unused right-hand canvas; never paste beyond a column.
                cell=cell.crop((0,0,max(1,ink_width),cell.height))
                image.paste(cell,(x+9 if col==0 else x+(w-cell.width)//2,12));x+=w
            rows.append(image)
        return rows


def render_assignment(request,bank,habit,spacing,output):
    document=preflight_assignment(request['text'],bank,request.get('allow_supplemental_math',False),request.get('answer_header',''))
    writer=Writer(bank,habit,spacing,request['seed'],request.get('allow_supplemental_math',False),request.get('answer_spacing',1.6),request.get('spacing'))
    # Match ordinary size16 to the approximately14 setting used for answer sheets.
    em=max(28,min(55,round(request.get('answer_size',16)*2.45)))
    entries=[]
    def save(im,block,**meta):
        filename=f'block-{len(entries):04}.png';im.save(output/filename)
        entries.append({'file':filename,'width':im.width,'height':im.height,'question':block.get('question'),
            'role':block['kind'],**meta})
    if request.get('answer_header'):
        save(writer.paragraph(request['answer_header'],em*.9),{'kind':'header','question':None})
    for block in document['blocks']:
        kind=block['kind']
        if kind in ('heading','paragraph'):
            image=writer.paragraph(block['text'],em)
            # Split only at paragraph line bands, never by clipping a line.
            if image.height>1400:
                mask=np.any(np.asarray(image)<210,axis=1);runs=np.flatnonzero(np.diff(np.r_[False,mask,False]))
                top=0
                for bottom in runs[1::2]:
                    if bottom-top>1250:
                        end=next((int(y) for y in runs[1::2] if top+900<y<bottom),None)
                        if end is None:raise ValueError('段落无法安全分页，请增加段落换行。')
                        save(image.crop((0,top,WIDTH,end)),block,text=block['text']);top=end
                if top<image.height:save(image.crop((0,top,WIDTH,image.height)),block,text=block['text'])
            else:save(image,block,text=block['text'])
        elif kind=='choices':
            for start in range(0,len(block['choices']),4):
                cells=[writer.paragraph(number+'. '+answer,em,WIDTH//4-12) for number,answer in block['choices'][start:start+4]]
                image=Image.new('L',(WIDTH,max(round(em*1.4),max(cell.height for cell in cells)+12)),255)
                for col,cell in enumerate(cells):image.paste(cell,(col*WIDTH//4+8,6))
                save(image,block)
        elif kind=='table':
            rows=writer.table(block,max(26,round(em*.78)))
            for index,row in enumerate(rows):save(row,block,table_row=index,table_id=len(entries)-index,table_header=index==0,table_last=index==len(rows)-1)
        elif kind=='tree':
            for index,row in enumerate(block['rows']):
                indent=min(360,row['depth']*43)
                label=writer.paragraph(row['text'],max(28,round(em*.85)),WIDTH-indent-15)
                image=Image.new('L',(WIDTH,label.height+18),255)
                if row['depth']:
                    draw=ImageDraw.Draw(image)
                    for guide in row.get('guides',[]):
                        x=guide*43+13
                        draw.line((x,0,x,image.height-1),fill=45,width=2)
                    draw.line([(indent-30,0),(indent-30,round(label.height*.5)+9),(indent-7,round(label.height*.5)+9)],fill=45,width=2)
                image.paste(label,(indent,9));save(image,block,tree_row=index,depth=row['depth'])
    footer_digits={}
    for digit in '0123456789':
        im=writer.paragraph(digit,22,100);box=ImageOps.invert(im).getbbox();im=im.crop((0,0,box[2]+1,im.height))
        filename=f'footer-{digit}.png';im.save(output/filename);footer_digits[digit]=filename
    metadata={'version':VERSION,'spacing':writer.settings,'baseline_rhythm':{'method':'bounded procedural line drift and correlated word lifts','lines':writer.baseline_lines},'entries':entries,'footer_digits':footer_digits,'document':document,'references':sorted(writer.references),
              'supplemental_math_glyphs':sorted(writer.supplements),'em':em}
    (output/'assignment.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    return metadata


def compose_assignment(folder,job,generated):
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    from .spacing import normalize_spacing
    from .baseline_rhythm import vertical_advance
    folder=Path(folder).resolve();meta=generated['assignment_layout'];entries=meta['entries'];capacity=PAGE_H-2*MARGIN-32
    settings=normalize_spacing(job['preferences'].get('spacing',meta.get('spacing')))
    seed=job['preferences'].get('seed',42)
    def after_gap(index):
        entry=entries[index]
        kind='line' if entry['role'] in ('table','tree','choices') else 'paragraph'
        return vertical_advance(12,settings,seed,index,kind)
    pages=[[]];y=MARGIN;placements=[];warnings=[]
    def next_page():
        nonlocal y
        if pages[-1]:pages.append([]);y=MARGIN
    def group_height(start,end):return sum(entries[i]['height']+after_gap(i) for i in range(start,end))
    for index,entry in enumerate(entries):
        if entry['height']>capacity:raise ValueError('答卷块高于可打印区域，请拆分。')
        if entry['role']=='heading':
            end=index+1
            while end<len(entries) and entries[end]['role']!='heading':end+=1
            total=group_height(index,end)
            if total<=capacity and y+total>PAGE_H-MARGIN-32:next_page()
            elif total>capacity and y>MARGIN:next_page()
        if entry['role']=='paragraph' and re.match(r'^[a-z]\.\s*',entry.get('text','')):
            end=index+1
            while end<len(entries) and entries[end]['role']!='heading' and not (
                    entries[end]['role']=='paragraph' and re.match(r'^[a-z]\.\s*',entries[end].get('text',''))):end+=1
            need=group_height(index,end)
            if need<=capacity and y+need>PAGE_H-MARGIN-32:next_page()
        if entry.get('table_header'):
            # Keep the header with at least the first data row.
            need=entry['height']+after_gap(index)+(entries[index+1]['height'] if index+1<len(entries) else 0)
            if y+need>PAGE_H-MARGIN-32:next_page()
        if y+entry['height']>PAGE_H-MARGIN-32:
            next_page()
            if entry['role']=='table' and not entry.get('table_header'):
                header=entries[entry['table_id']]
                header_gap=after_gap(entry['table_id'])
                if header['height']+header_gap+entry['height']>capacity:raise ValueError('表格单行连同表头过高，请缩短单元格内容。')
                pages[-1].append((header,y));placements.append({'page':len(pages),'y':y,**header,'repeated_table_header':True});y+=header['height']+header_gap
        pages[-1].append((entry,y));placements.append({'page':len(pages),'y':y,**entry,'gap_after':after_gap(index)});y+=entry['height']+after_gap(index)
    ink=job['preferences']['ink']
    pdf=canvas.Canvas(str(folder/'result.pdf'),pagesize=(595.2756,841.8898),invariant=1)
    pdf.setTitle('Inkself handwritten answer sheet')
    for n,blocks in enumerate(pages,1):
        page=Image.new('RGB',(PAGE_W,PAGE_H),'white')
        for entry,y in blocks:
            path=(folder/entry['file']).resolve()
            if path.parent!=folder or path.suffix!='.png':raise ValueError('Invalid answer image path.')
            with Image.open(path) as image:
                page.paste(ImageOps.colorize(image.convert('L'),black=ink,white='white'),(MARGIN,y))
            if entry.get('table_header') or entry.get('table_last'):
                ImageDraw.Draw(page).line((MARGIN,y+entry['height']-1,PAGE_W-MARGIN,y+entry['height']-1),fill=ink,width=1)
        digits=[]
        for digit in str(n):
            path=(folder/meta['footer_digits'][digit]).resolve()
            if path.parent!=folder:raise ValueError('Invalid footer image path.')
            with Image.open(path) as image:digits.append(image.convert('L').copy())
        footer_gap=max(1,round(2*settings['number']))
        x=(PAGE_W-sum(d.width+footer_gap for d in digits))//2
        for digit in digits:page.paste(ImageOps.colorize(digit,black=ink,white='white'),(x,PAGE_H-57));x+=digit.width+footer_gap
        page.save(folder/f'page-{n:03}.png');pdf.drawImage(ImageReader(page),0,0,width=595.2756,height=841.8898);pdf.showPage()
    pdf.save()
    layout={'schema_version':1,'version':VERSION,'spacing':settings,'pages':len(pages),'placements':placements,'warnings':warnings,
        'source_sha256':meta['document']['source_sha256'],'formatting_only':True}
    (folder/'layout.json').write_text(json.dumps(layout,ensure_ascii=False,indent=2),encoding='utf-8')
    (folder/'report.json').write_text(json.dumps({'model':generated['model'],'layout':layout,'assignment':meta,
        'validation':'Formatting and glyph provenance only; human content review required.'},ensure_ascii=False,indent=2),encoding='utf-8')
    return len(pages)
