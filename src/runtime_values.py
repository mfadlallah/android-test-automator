"""Attempt-local captured values; references never become literal UI text."""
import re
import unicodedata
from .collections import descendants

REFERENCE = re.compile(r'^\$([a-z][a-z0-9_]*)$', re.I)


def normalized_title(text):
    return ' '.join(unicodedata.normalize('NFKC',text).split()).casefold()


def title_match(actual, expected):
    """Match full text first, or a sufficiently descriptive explicit ellipsis."""
    actual=normalized_title(actual);expected=normalized_title(expected)
    if actual==expected:
        return 'exact'
    if not actual.endswith('...'):
        return None
    prefix=actual[:-3].rstrip()
    if (expected.endswith('...') or not expected.startswith(prefix)
            or len(prefix)>=len(expected)):
        return None
    # Conservative evidence floor, not a claim of globally unique identity.
    if (sum(c.isalnum() for c in prefix)<12 or len(prefix.split())<3
            or len(prefix)/max(1,len(expected))<.6):
        return 'uncertain'
    return 'truncated_prefix'


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
        def visible(item):
            b=item.get('bounds',[])
            return len(b)==4 and b[2]>b[0]>=0 and b[3]>b[1]>=0
        candidates=[]
        for source,entries in [('hierarchy',nodes),('ocr',obs.get('ocr',[]))]:
            eligible=[n for n in entries if visible(n)
                     and (source!='ocr' or n.get('confidence',0)>=.8)]
            candidates.extend((source,n,title_match(n.get('text',''),capture['text'])) for n in eligible)
        # An exact OCR title is stronger than a truncated hierarchy label.
        for source in ('hierarchy','ocr'):
            matches=[n for s,n,mode in candidates if s==source and mode=='exact']
            if matches:
                return {'status':'passed','reason':step['target']+' contains captured title '+repr(capture['text'])+'.',
                        'evidence':'Confirmed destination '+step['target']+'; source collection absent; exact '+source+' text '+repr(capture['text'])+' at '+str(matches[0]['bounds']),
                        'match_type':'exact','source':source}
        for source in ('hierarchy','ocr'):
            matches=[n for s,n,mode in candidates if s==source and mode=='truncated_prefix']
            if not matches:
                continue
            prefix=normalized_title(matches[0]['text'])[:-3].rstrip()
            conflicts=[n for _,n,_ in candidates if not normalized_title(n.get('text','')).endswith('...')
                       and normalized_title(n.get('text','')).startswith(prefix)
                       and normalized_title(n.get('text',''))!=normalized_title(capture['text'])]
            if len(matches)!=1 or conflicts:
                return {'status':'blocked','reason':'Truncated title prefix is ambiguous on the destination screen.',
                        'evidence':step['target']+': expected '+repr(capture['text'])+'; multiple matching locations or conflicting full titles.'}
            actual=matches[0]['text']
            return {'status':'passed','reason':step['target']+': truncated title prefix matched.',
                    'evidence':step['target']+': visible '+repr(actual)+' is an explicit ellipsis prefix of captured title '+repr(capture['text'])+'; confirmed destination; source collection absent; '+source+' bounds '+str(matches[0]['bounds']),
                    'match_type':'truncated_prefix','source':source}
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
    mode=title_match(actual,capture['text'])
    if mode=='uncertain':
        return {'status':'blocked','reason':'Truncated title prefix is too short to assess reliably.',
                'evidence':step['target']+': '+repr(actual)+' versus captured '+repr(capture['text'])}
    if mode=='truncated_prefix':
        return {'status':'passed','reason':'Destination truncated title prefix matched.',
                'evidence':step['target']+': visible '+repr(actual)+' is an explicit ellipsis prefix of captured title '+repr(capture['text'])+'; destination node '+str(fields[0]['node']),
                'match_type':mode,'source':'hierarchy'}
    equal=mode=='exact'
    return {'status':'passed' if equal else 'failed',
            'reason':'Destination title '+('matches' if equal else 'does not match')+' captured title.',
            'evidence':step['target']+': '+repr(actual)+' compared exactly with '+repr(capture['text'])+'; destination node '+str(fields[0]['node'])}
