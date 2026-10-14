"""Attempt-local captured values; references never become literal UI text."""
import re
from .collections import descendants

REFERENCE = re.compile(r'^\$([a-z][a-z0-9_]*)$', re.I)


def resolve_value(value, captured):
    match = REFERENCE.fullmatch(value)
    if not match:
        return value
    if match[1] not in captured:
        raise ValueError('Runtime value has not been captured: '+value)
    return captured[match[1]]['text']


def validate_bindings(steps):
    captured = set()
    for step in steps:
        value = step.get('value', '')
        if step['capability'] == 'capture_text':
            if not re.fullmatch(r'[a-z][a-z0-9_]*', value, re.I) or value in captured:
                raise ValueError('Capture variable must be a unique identifier.')
            captured.add(value)
        elif REFERENCE.fullmatch(value) and value[1:] not in captured:
            raise ValueError('Runtime value requires a preceding capture: '+value)


def captured_destination_result(step, obs, capture, destination_confirmed=False):
    """Compare a captured title outside its source collection, without AI."""
    nodes=obs.get('nodes', [])
    source_id=capture['scope'].get('collection_resource_id')
    if step.get('capability')=='assert_not_contains':
        return {'status':'blocked','reason':'Captured-title comparisons require assert_contains.',
                'evidence':'No absence verdict inferred from a missing captured title.'}
    excluded=set()
    for root in nodes:
        if source_id and root.get('resource_id')==source_id:
            excluded.update(n['node'] for n in [root,*descendants(root,nodes)])
    if re.search(r'(?i)\bscreen$',step['target'].strip()):
        if not destination_confirmed or not nodes or not source_id or excluded:
            return {'status':'blocked','reason':'Destination screen is not independently confirmed or source collection is still present.',
                    'evidence':'Captured title alone cannot prove navigation.'}
        def clean(text):return ' '.join(text.split()).casefold()
        expected=clean(capture['text'])
        def visible(item):
            b=item.get('bounds',[])
            return len(b)==4 and b[2]>b[0]>=0 and b[3]>b[1]>=0
        for source,entries in [('hierarchy',nodes),('ocr',obs.get('ocr',[]))]:
            matches=[n for n in entries if visible(n) and clean(n.get('text',''))==expected
                     and (source!='ocr' or n.get('confidence',0)>=.8)]
            if matches:
                return {'status':'passed','reason':step['target']+' contains captured title '+repr(capture['text'])+'.',
                        'evidence':'Confirmed destination '+step['target']+'; source collection absent; exact '+source+' text '+repr(capture['text'])+' at '+str(matches[0]['bounds'])}
        return {'status':'blocked','reason':'Captured title was not found in destination hierarchy/OCR evidence.',
                'evidence':'Destination confirmed, but missing text detection alone is not a product failure.'}
    queries={q.split(':id/')[-1].casefold() for q in (step['target'],*step.get('hints',()))}
    fields=[n for n in nodes if n['node'] not in excluded
            and n.get('resource_id','').split(':id/')[-1].casefold() in queries
            and n.get('text','').strip()]
    if len(fields)!=1:
        return {'status':'blocked','reason':'Captured-value comparison requires one destination text field outside the source collection.',
                'evidence':'Grounded destination candidates: '+str(len(fields))}
    actual=fields[0]['text'].strip()
    # Titles compare exactly; a substring is insufficient for vendor identity.
    equal=actual==capture['text']
    return {'status':'passed' if equal else 'failed',
            'reason':'Destination title '+('matches' if equal else 'does not match')+' captured title.',
            'evidence':step['target']+': '+repr(actual)+' compared exactly with '+repr(capture['text'])+'; destination node '+str(fields[0]['node'])}
