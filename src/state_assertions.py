"""Generic hierarchy-backed modal identity and selection assertions."""
import re
from .recovery import strong_modal_candidate

MODAL = re.compile(r'bottom[_ -]?sheet|dialog|modal|popup', re.I)
TYPE_WORDS = re.compile(r'\b(?:bottom\s*sheet|sheet|dialog|modal|popup)\b', re.I)


def normalized(text):
    return ' '.join(str(text).casefold().split())


def within(node, root, by_id):
    seen = set()
    while node in by_id and node not in seen:
        if node == root:
            return True
        seen.add(node)
        node = by_id[node].get('parent')
    return False


def verdict(status, target, evidence):
    return {'status': status, 'reason': target + ': ' + evidence, 'evidence': evidence}


def modal_assertion(step, obs, identities):
    """Remember a titled modal, then distinguish its removal from its launcher."""
    target = step.get('target', '')
    if step.get('capability') not in ('assert_visible', 'assert_hidden') or not TYPE_WORDS.search(target):
        return None
    title = normalized(TYPE_WORDS.sub('', target))
    if not title:
        return None
    nodes = obs.get('nodes', [])
    if not nodes:
        return None  # Screenshot assessment must handle unavailable hierarchy.
    by_id = {n['node']: n for n in nodes}
    roots = [n for n in nodes if strong_modal_candidate(n)]
    labels = [n for n in nodes if title in (normalized(n.get('text', '')), normalized(n.get('description', '')))]
    matches = [(root, label) for root in roots for label in labels
               if within(label['node'], root['node'], by_id)]
    key = normalized(target)
    if matches:
        root, label = matches[0]
        identities[key] = {'container_id': root.get('resource_id', ''),
                           'heading_id': label.get('resource_id', ''), 'title': title}
        status = 'passed' if step['capability'] == 'assert_visible' else 'failed'
        return verdict(status, target, 'The titled modal container is visible; its heading is inside the container.')
    known = identities.get(key)
    if step['capability'] == 'assert_hidden' and known:
        # A different modal or reused container is ambiguous, not proof of closure.
        if roots:
            return None
        retained = any(n.get('resource_id') in (known['container_id'], known['heading_id'])
                       for n in nodes if n.get('resource_id'))
        if not retained and len(nodes) >= 5:
            return verdict('passed', target, 'The previously grounded modal container and heading are absent; the modal is closed. A same-name launcher is not the modal.')
    return None


def selected_assertion(step, obs):
    if step.get('capability') != 'assert_selected':
        return None
    target = normalized(step.get('target', ''))
    nodes = obs.get('nodes', [])
    matches = [n for n in nodes if target in (normalized(n.get('text', '')), normalized(n.get('description', '')))]
    if len(matches) != 1:
        return None
    label = matches[0]
    if label.get('selected') or label.get('checked'):
        return verdict('passed', step['target'], 'The grounded option is selected/checked in accessibility state.')
    # Radio/checkbox indicators often sit beside the label in its immediate row.
    siblings = [n for n in nodes if label.get('parent') is not None
                and n.get('parent') == label.get('parent')
                and re.search(r'radiobutton|checkbox|switch', n.get('class_name', ''), re.I)]
    if len(siblings) == 1 and 'checked' in siblings[0]:
        selected = siblings[0]['checked'] is True
        return verdict('passed' if selected else 'failed', step['target'],
                       'The option row indicator is checked (selected).' if selected else
                       'The option row indicator is unchecked (not selected).')
    return None
