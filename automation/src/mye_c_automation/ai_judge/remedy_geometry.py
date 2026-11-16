PROMPT = '''Observe the full original image. Return subject_box [x0,y0,x1,y1] enclosing ALL product,
packaging, official marks/social/photographer signatures and disclaimers, in original pixel coordinates.
Propose crop_box only for a third-party promotional single edge strip that removes no protected content.
If uncertain return abstain=true, decision UNCERTAIN, crop_box=null. Do not propose deleting a box image.
Optionally propose erase_box for a tiny simple-background store mark entirely outside subject_box;
never cover product texture, official/social/photographer marks, packaging text or disclaimers.
Do not invent geometry. Return task_type,item_id,decision,confidence,abstain,evidence_ids,subject_box,crop_box,erase_box.'''
