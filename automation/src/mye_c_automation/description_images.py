"""Narrow edits to standalone body image nodes; footer and text stay opaque."""
from copy import deepcopy
import json


def body_image_nodes(description):
    """Enumerate body images with stable source-order indices; exclude footer."""
    try:nodes=json.loads(description) if isinstance(description,str) else description
    except (TypeError,ValueError):return []
    if not isinstance(nodes,list):return []
    rows=[];marked=any(isinstance(n,dict) and n.get('shopFooter') is True for n in nodes)
    for node_index,node in enumerate(nodes):
        if isinstance(node,dict) and node.get('shopFooter') is True:break
        if isinstance(node,dict) and node.get('type')=='image' and isinstance(node.get('url'),str) and node['url']:
            rows.append(dict(index=len(rows),node_index=node_index,url=node['url']))
        elif marked and isinstance(node,dict) and node.get('type')=='text-image' and isinstance(node.get('images'),list):
            for image_index,image in enumerate(node['images']):
                if isinstance(image,dict) and isinstance(image.get('url'),str) and image['url']:
                    rows.append(dict(index=len(rows),node_index=node_index,image_index=image_index,url=image['url']))
    return rows


def delete_body_images(description, urls):
    return edit_body_images(description,urls,{})


def edit_body_images(description, urls, replacements):
    """Delete exact URLs in top-level image nodes before the marked shop footer.

    Never traverse text-image, nested content, or the footer. Callers must supply
    an independently approved deletion set; absence from images.detail alone
    does not authorize deleting a description image.
    """
    if not isinstance(urls,(list,tuple)) or any(not isinstance(u,str) or not u for u in urls):
        raise ValueError('DESCRIPTION_IMAGE_DELETIONS_INVALID')
    if not isinstance(replacements,dict) or any(not isinstance(k,str) or not k or not isinstance(v,str) or not v for k,v in replacements.items()):
        raise ValueError('DESCRIPTION_IMAGE_REPLACEMENTS_INVALID')
    if not urls and not replacements:return deepcopy(description)
    nodes=json.loads(description) if isinstance(description,str) else deepcopy(description)
    if not isinstance(nodes,list):raise ValueError('DESCRIPTION_IMAGE_NODES_UNSUPPORTED')
    targets=set(urls);kept=[];footer=False;changed=False
    marked=any(isinstance(n,dict) and n.get('shopFooter') is True for n in nodes)
    for node in nodes:
        if isinstance(node,dict) and node.get('shopFooter') is True:footer=True
        if not footer and isinstance(node,dict) and node.get('type')=='image' and node.get('url') in targets:
            changed=True
            continue
        if not footer and isinstance(node,dict) and node.get('type')=='image' and node.get('url') in replacements:
            node=deepcopy(node);node['url']=replacements[node['url']];changed=True
        if not footer and marked and isinstance(node,dict) and node.get('type')=='text-image' and isinstance(node.get('images'),list):
            updated=[]
            for image in node['images']:
                if isinstance(image,dict) and image.get('url') in targets:changed=True;continue
                if isinstance(image,dict) and image.get('url') in replacements:
                    image=deepcopy(image);image['url']=replacements[image['url']];changed=True
                updated.append(image)
            if updated!=node['images']:node=deepcopy(node);node['images']=updated
        kept.append(node)
    if not changed:return deepcopy(description)
    return json.dumps(kept,ensure_ascii=False) if isinstance(description,str) else kept
