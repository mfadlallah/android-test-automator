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


def captured_destination_result(step, obs, capture):
    """Compare a captured title outside its source collection, without AI."""
    nodes=obs.get('nodes', [])
    source_id=capture['scope'].get('collection_resource_id')
    excluded=set()
    for root in nodes:
        if source_id and root.get('resource_id')==source_id:
            excluded.update(n['node'] for n in [root,*descendants(root,nodes)])
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
