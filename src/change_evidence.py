"""Retain an unobstructed baseline across modal workflows."""
from .recovery import strong_modal_candidate


class ModalBaseline:
    def __init__(self):
        self.latest = None
        self.before = None
        self.modal_open = False

    def observe(self, obs):
        modal = any(strong_modal_candidate(n) for n in obs.get('nodes', []))
        if modal and not self.modal_open:
            self.before = self.latest
        if not modal and obs.get('nodes'):
            self.latest = obs
        self.modal_open = modal

    def consume(self):
        self.before = None


def repeated_item_titles(obs, bounds):
    """Use repeated named/title fields inside a grounded collection only."""
    import re
    groups = {}
    if not bounds:
        return groups
    x1, y1, x2, y2 = bounds
    for node in obs.get('nodes', []):
        box = node.get('bounds', [])
        text = ' '.join(node.get('text', '').split())
        rid = node.get('resource_id', '')
        suffix = rid.split(':id/')[-1]
        if (len(box) != 4 or not text or not rid
                or not re.search(r'(?:^|_)(?:name|title)$', suffix)
                or not (x1 <= box[0] < box[2] <= x2 and y1 <= box[1] < box[3] <= y2)):
            continue
        groups.setdefault(rid, []).append((box[1], box[0], text))
    return {rid: [text for _, _, text in sorted(rows)]
            for rid, rows in groups.items()
            if len(rows) >= 2 or rid.split(':id/')[-1].endswith('_name')}


def collection_change(before, current, before_bounds, current_bounds):
    old = repeated_item_titles(before, before_bounds)
    new = repeated_item_titles(current, current_bounds)
    for rid in sorted(old.keys() & new.keys()):
        if old[rid] != new[rid]:
            return {'status': 'passed',
                'reason': 'Scoped collection item identities/order changed between before and current.',
                'evidence': 'Before: '+repr(old[rid])+'; current: '+repr(new[rid])+'. Item identity field: '+rid}, {'field': rid, 'before': old[rid], 'current': new[rid]}
    return None, {'before_fields': old, 'current_fields': new}


def collection_visible(step, obs, bounds):
    import re
    if step.get('capability')!='assert_visible' or not re.search(r'\b(?:items|list|collection|results)\b',step.get('target',''),re.I):
        return None
    if not bounds or any(strong_modal_candidate(n) for n in obs.get('nodes',[])):
        return None
    # The crop must correspond to an actual visible scrollable container.
    containers=[n for n in obs.get('nodes',[]) if n.get('scrollable')
                and list(n.get('bounds',[]))==list(bounds)]
    names=repeated_item_titles(obs,bounds)
    if not containers or not names:
        return None
    return {'status':'passed', 'reason':step['target']+' is visible with grounded item content.',
            'evidence':'A visible scrollable container contains named item content: '+repr(names)}


def change_reference(capability, modal_before, last_action):
    """Action changes compare against that action, not an older modal workflow."""
    if capability == 'assert_changed':
        return last_action
    if capability == 'wait_changed':
        return modal_before or last_action
    return last_action


def layout_change_requested(step):
    import re
    text=step.get('success','')
    return step.get('capability')=='assert_changed' and bool(
        re.search(r'\blayout\b|\bfrom\b.+\b(?:view|mode)\b.+\bto\b.+\b(?:view|mode)\b',text,re.I))
