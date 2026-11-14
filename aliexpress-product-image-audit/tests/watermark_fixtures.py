"""Synthetic v3 fixtures only; never a converter for historical real results."""
from copy import deepcopy


def exhaustive(row,size=(800,800)):
    row=deepcopy(row);refs=row.get('evidence_ids',[])
    marks=row.get('marks')
    if marks is None:marks=[{k:row[k] for k in ('classification','owner','location','confidence','abstain')}]
    output=[]
    for index,mark in enumerate(marks):
        mark=deepcopy(mark);mark.setdefault('mark_id','M'+str(index+1))
        mark.setdefault('bbox_xyxy',[10,10+index*100,100,60+index*100])
        mark.setdefault('abstain',row['abstain']);mark.setdefault('evidence_ids',deepcopy(refs));output.append(mark)
    row.update(schema_version='watermark/v3',image_size=list(size),coverage_complete=True,
               no_marks_detected=not bool(output),marks=output,unresolved_items=[])
    return row


def identity(row):
    row=deepcopy(row);refs=row['evidence_ids']
    values={'product_subject':'transforming toy','image_type':row['image_type'],'model_identity':row['model'],
            'color':row['color'],'packaging':{'BOX':'BOXED','FIGURE':'UNBOXED','MIXED':'MIXED'}[row['image_type']]}
    row.update(schema_version='product-identity/v3',observations={k:{'value':v,'decision':row['decision'],
        'confidence':row['confidence'],'abstain':row['abstain'],'evidence_ids':deepcopy(refs),
        **({'visibility':'VISIBLE'} if k=='model_identity' else {})} for k,v in values.items()})
    return row
