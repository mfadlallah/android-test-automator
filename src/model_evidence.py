"""Compact model evidence without removing labels, node identity or screenshots."""
import copy
import json

NODE_FIELDS = {'node', 'parent', 'bounds', 'text', 'description', 'resource_id',
               'class_name', 'enabled', 'clickable', 'scrollable', 'selected',
               'checked', 'checkable', 'visible', 'visible_to_user'}


def compact_nodes(nodes):
    # Keep every node and all state booleans, including explicit False values.
    return [{k: v for k, v in node.items()
             if k in NODE_FIELDS and v is not None and v != ''}
            for node in nodes]



def node_table(nodes):
    """Columnar JSON preserves all grounding fields without repeating keys."""
    records=compact_nodes(nodes)
    columns=sorted({key for record in records for key in record})
    return {'encoding':'columns/rows; null means field unavailable',
            'columns':columns,
            'rows':[[record.get(key) for key in columns] for record in records]}



def intern_node_table(table):
    """Retry encoding: repeated strings use explicit dictionary references."""
    from collections import Counter
    if table.get('strings'):
        return table
    counts=Counter(cell for row in table.get('rows',[]) for cell in row
                   if isinstance(cell,str) and len(cell)>=12)
    strings=sorted(text for text,count in counts.items() if count>=2)
    if not strings:
        return table
    index={text:n for n,text in enumerate(strings)}
    return {**table,
            'encoding':'columns/rows; null means unavailable; {ref:N} means strings[N]',
            'strings':strings,
            'rows':[[{'ref':index[cell]} if isinstance(cell,str) and cell in index else cell
                     for cell in row] for row in table['rows']]}


def compact_history(history):
    fields = {'action', 'node', 'direction', 'reason', 'evidence', 'source',
              'step_id', 'status', 'vision_point'}
    result = []
    for record in history[-3:]:
        decision = record.get('decision', record)
        summary = {k: v for k, v in decision.items() if k in fields}
        if isinstance(record.get('plan_step'), dict):
            summary['plan_step'] = {k: v for k, v in record['plan_step'].items()
                                    if k in ('id', 'capability', 'target', 'value')}
        result.append(summary)
    return result


def compact_evidence(value):
    if isinstance(value, list):
        return [compact_evidence(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, item in value.items():
        if key == 'nodes' and isinstance(item, list) and all(isinstance(n, dict) for n in item):
            result[key] = node_table(item)
        elif key=='nodes' and isinstance(item,dict) and 'columns' in item and 'rows' in item:
            result[key]=intern_node_table(item)
        elif key in ('history', 'recent_actions') and isinstance(item, list) and all(isinstance(n, dict) for n in item):
            result[key] = compact_history(item)
        else:
            result[key] = compact_evidence(item)
    return result


def compact_chat_request(payload):
    """Only compact JSON evidence messages; never alter instructions or images."""
    result = copy.deepcopy(payload)
    changed = False
    for message in result.get('messages', []):
        if message.get('role') != 'user' or not isinstance(message.get('content'), str):
            continue
        try:
            evidence = json.loads(message['content'])
        except ValueError:
            continue
        compact = json.dumps(compact_evidence(evidence), ensure_ascii=False, separators=(',', ':'))
        if len(compact) < len(message['content']):
            message['content'] = compact
            changed = True
    return result if changed else None


def context_overflow(code, body):
    if code != 400:
        return False
    value=body
    for _ in range(6):
        if isinstance(value,str):
            try:
                value=json.loads(value)
                continue
            except ValueError:
                return 'exceeds' in value.lower() and 'context' in value.lower()
        if not isinstance(value,dict):
            return False
        if value.get('type')=='exceed_context_size_error':
            return True
        if 'error' not in value:
            return False
        value=value['error']
    return False
