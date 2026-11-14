"""Deterministic mappings read from the preserved, versioned title SOP."""
from pathlib import Path
import re

SOP_PATH=Path(__file__).resolve().parents[1]/'references'/'SOP-商品标题重写.md'
PREFIX={4:'In Stock',7:'Hot Sale'}
SUFFIX='Action Figures Collection Gifts'

def mappings():
    groups={key:[] for key in ('品牌','系列','角色','修饰','属性')}
    document=SOP_PATH.read_text(encoding='utf-8')
    section=document.split('## 3. 替换表（合并版）',1)[1].split('## 4.',1)[0]
    for line in section.splitlines():
        cells=[s.strip().replace('**','') for s in line.strip('|').split('|')]
        if len(cells)!=3 or cells[2] not in groups: continue
        originals=cells[0].split(' / ');english=cells[1].split(' / ')
        if len(english)==len(originals): pairs=zip(originals,english)
        else: pairs=((o,english[0]) for o in originals)
        for original,target in pairs:
            target=target.split('（')[0].strip()
            if target in {'删除','省略'}: target=''
            # In role/modifier rows the SOP uses the middle dot to list aliases
            # (e.g. 小比例·极小比例), not a literal compound product name.
            aliases=original.split('·') if cells[2] in {'角色','修饰'} else [original]
            groups[cells[2]].extend((alias.strip(),target) for alias in aliases if alias.strip())
    # Explicit SOP branch brands that do not require translation.
    groups['品牌'] += [(b,b) for b in ('NewAge','MMC','DNA','X-TRANSBOTS','BINGOTOYS','RT','ToysMage','Action Toys','Bandai','GSC','APEX','LIMEPIE','AniMester')]
    return groups

def normalize_model(value):
    value=re.sub(r'\s+','-',value.strip().upper())
    if re.fullmatch(r'(?:NAH|MF|RT|MC)\d+[A-Z]*',value):
        if value.startswith('NAH'): return 'NA-H'+value[3:]
        return re.sub(r'^([A-Z]+)(\d)',r'\1-\2',value)
    return value

def extract_models(text):
    found=re.findall(r'(?<![A-Za-z0-9])(?:[A-Za-z]{1,5}(?:[- ][A-Za-z])?[- ]?\d{2,5}[A-Za-z]*(?:-[A-Za-z0-9]+)?)(?![A-Za-z0-9])',text)
    return list(dict.fromkeys(normalize_model(v) for v in found if v.upper() not in {'SS86','SSONE'}))


def source_match(source, text):
    """Latin aliases must be whole tokens; Chinese phrases keep substring matching."""
    pattern = re.escape(source)
    if source and source[0].isascii() and source[0].isalnum():
        pattern = r'(?<![A-Za-z0-9])' + pattern
    if source and source[-1].isascii() and source[-1].isalnum():
        pattern += r'(?![A-Za-z0-9])'
    return re.search(pattern, text, re.I)
