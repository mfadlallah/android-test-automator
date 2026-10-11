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
            result[key] = compact_nodes(item)
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
    try:
        error = json.loads(body).get('error')
    except (ValueError, AttributeError):
        return False
    if isinstance(error, dict):
        return error.get('type') == 'exceed_context_size_error'
    return isinstance(error, str) and ('exceeds' in error.lower() and 'context' in error.lower())
