"""Build English titles from original fields; uncertain identity stays deferred."""
import json
import re
from mye_c_automation.title_rules import PREFIX, SUFFIX, mappings, extract_models, normalize_model, source_match

def rewrite_title(product,shop):
    def defer(reason): return {'ok':False,'decision':'DEFERRED','reason_codes':[reason]}
    if shop not in PREFIX: return defer('UNKNOWN_SHOP')
    original=product.get('title')
    if not isinstance(original,str) or not original.strip(): return defer('ORIGINAL_TITLE_MISSING')
    try:
        identity=product.get('identityJson') or {}
        if isinstance(identity,str): identity=json.loads(identity)
        if not isinstance(identity,dict): return defer('INVALID_IDENTITY')
    except ValueError: return defer('INVALID_IDENTITY')
    models=extract_models(original)
    known=identity.get('modelCode')
    if known:
        known=normalize_model(known)
        if models and known not in models: return defer('MODEL_CONFLICT')
        if not models: models=[known]
    for sku in product.get('skus') or []:
        codes=extract_models(str(sku.get('skuName',sku.get('name',''))))
        if codes and models and any(c not in models for c in codes): return defer('SKU_MODEL_CONFLICT')
    groups=mappings()
    # Preserve explicit English identities using the SOP targets and known official names.
    english_roles=[(target,target) for _,target in groups['角色'] if target]
    english_roles += [('Jazz','Jazz'),('Optimus Prime','OP Commander'),('Megatron','Megatank'),('Bumblebee','Bee')]
    groups['角色'] += english_roles
    selected={key:[] for key in groups}
    for group,pairs in groups.items():
        matches=[]
        for source,target in sorted(pairs,key=lambda p:-len(p[0])):
            match=source_match(source,original)
            if match and target and not any(match.start()>=a and match.end()<=b for a,b,_ in matches):
                matches.append((match.start(),match.end(),target))
        selected[group]=list(dict.fromkeys(t for _,_,t in sorted(matches)))
    transforming=bool(re.search(r'变形|擎天柱|威震天|大黄蜂|红蜘蛛|魔方|银河|梦星|吴医生|威双|招财猫|大匠社',original)) or any(source_match(name,original) for name in ('NewAge','MFT','MMC','X-TRANSBOTS','BINGOTOYS','ToysMage','Collection Space'))
    english_role_targets={target for source,target in english_roles if source_match(source,original)}
    if len(english_role_targets)>1:
        return defer('SOURCE_ROLE_CONFLICT')
    transforming = transforming or bool(source_match('Transformers',original)) or bool(english_role_targets) or any(
        source_match(name,original) for name in ('RT','MFT'))
    brand=selected['品牌'][:1]; series=selected['系列'];roles=selected['角色'];modifiers=selected['修饰'][:2]
    properties=selected['属性']
    if re.search(r'配件包|升级件|改造件|Upgrade Kit',original,re.I):
        properties=[p for p in properties if p!='Upgrade Kit']+['Upgrade Kit']
    if 'Figure Set' in properties: properties=[p for p in properties if p not in {'Figure','Ornament','Merchandise'}]
    # English product names are source text, not model-generated additions.
    if not (roles or models or brand):
        if re.search(r'[\u4e00-\u9fff]',original): return defer('UNTRANSLATED_PRODUCT_IDENTITY')
        words=re.sub(r'\b(?:In Stock|Hot Sale|Action Figures Collection Gifts|Hasbro)\b','',original,flags=re.I).strip()
        if not words: return defer('PRODUCT_IDENTITY_MISSING')
        roles=[words]
    duplicates=[m.replace('-','') for m in models if '-' in m]
    def assemble():
        return ' '.join([PREFIX[shop]]+(['Transformation'] if transforming else [])+brand+series+models+duplicates+roles+modifiers+properties+[SUFFIX])
    title=assemble()
    for trim in ('modifiers','series','brand','roles','duplicates'):
        if len(title)<=120: break
        if trim=='modifiers': modifiers=[]
        elif trim=='series': series=[]
        elif trim=='brand': brand=['TF'] if brand else []
        elif trim=='roles':
            while len(roles)>1 and len(assemble())>120: roles.pop()
        else: duplicates=[]
        title=assemble()
    if len(title)>120: return defer('TITLE_CANNOT_FIT_WITH_IDENTITY')
    return {'ok':True,'decision':'AUTO_SAFE','titleEn':title,'modelCode':models[0] if models else None,
            'brandCode':200017853 if transforming else 200014695,
            'provenance':{'titleEn':['title'],'modelCode':['title','identityJson.modelCode'],'brandCode':['title']},
            'changed':product.get('titleEn')!=title,'reason_codes':['SOP_2026_11_07_DETERMINISTIC']}
