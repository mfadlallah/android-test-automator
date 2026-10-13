"""Ground nested collections and ordinal targets without app-specific IDs."""
import re


class CollectionError(RuntimeError):
    pass


ORDINALS = {'first': 1, 'second': 2, 'third': 3, 'fourth': 4, 'forth': 4,
            'fifth': 5, 'sixth': 6, 'seventh': 7, 'eighth': 8,
            'ninth': 9, 'tenth': 10}
ITEM = re.compile(r'\b(first|second|third|fourth|forth|fifth|sixth|seventh|eighth|ninth|tenth|\d+(?:st|nd|rd|th)?)\s+(?:visible\s+)?item\b', re.I)


def ordinal(target):
    match = ITEM.search(target)
    if not match:
        return None
    word = match.group(1).lower()
    return ORDINALS[word] if word in ORDINALS else int(re.match(r'\d+', word)[0])


def tokens(text):
    return set(re.findall(r'[a-z]+|\d+', re.sub(r'([a-z])([A-Z])', r'\1 \2', str(text)).lower()))


def descendants(node, nodes):
    lookup = {n['node']: n for n in nodes}
    result = []
    for candidate in nodes:
        parent = candidate.get('parent')
        seen = set()
        while parent in lookup and parent not in seen:
            if parent == node['node']:
                result.append(candidate)
                break
            seen.add(parent)
            parent = lookup[parent].get('parent')
    return result


def items(container, obs):
    nodes = obs.get('nodes', [])
    children = [n for n in nodes if n.get('parent') == container['node']
                and len(n.get('bounds', [])) == 4
                and n['bounds'][2] > n['bounds'][0] and n['bounds'][3] > n['bounds'][1]]
    # Unwrap a single full-size layout, never unwrap a single clickable item.
    for _ in range(4):
        if len(children) != 1 or children[0].get('clickable'):
            break
        nested = [n for n in nodes if n.get('parent') == children[0]['node']
                  and len(n.get('bounds', [])) == 4]
        if not nested or children[0].get('scrollable'):
            break
        children = nested
    return children


def axis(container, obs):
    hint = tokens(container.get('resource_id', '') + ' ' + container.get('description', ''))
    if 'horizontal' in hint:
        return 'horizontal'
    if 'vertical' in hint:
        return 'vertical'
    children = items(container, obs)
    if len(children) < 2:
        return None
    centers = [((n['bounds'][0]+n['bounds'][2])/2,
                (n['bounds'][1]+n['bounds'][3])/2) for n in children]
    dx = max(x for x, _ in centers)-min(x for x, _ in centers)
    dy = max(y for _, y in centers)-min(y for _, y in centers)
    return 'horizontal' if dx > 2*dy else 'vertical' if dy > 2*dx else None


def resolve_collection(target, obs, hints=(), direction=None):
    nodes = obs.get('nodes', [])
    requested = 'horizontal' if 'horizontal' in tokens(target) or direction in {'left', 'right'} else 'vertical' if 'vertical' in tokens(target) or direction in {'up', 'down'} else None
    containers = [n for n in nodes if n.get('scrollable') and n.get('enabled', True)
                  and len(n.get('bounds', [])) == 4 and items(n, obs)]
    if requested:
        containers = [n for n in containers if axis(n, obs) == requested]
    if not containers:
        raise CollectionError('No grounded '+(requested or '')+' collection for '+target)
    # Preserve complete ID hints before semantic stop-word removal.
    queries = {str(q).strip().split(':id/')[-1].casefold() for q in (target, *hints)}
    exact = [n for n in containers if n.get('resource_id', '').split(':id/')[-1].casefold() in queries]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise CollectionError('Resource-id identifies multiple visible collections: '+target)
    explicit_ids=[q for q in (target,*hints) if ':id/' in q or re.fullmatch(r'[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+',q)]
    if explicit_ids:
        raise CollectionError('Explicit collection resource-id is not visible: '+', '.join(explicit_ids))
    ignore = set(ORDINALS) | {'item', 'items', 'of', 'in', 'the', 'visible', 'horizontal',
                            'vertical', 'recyclerview', 'recycler', 'view', 'list', 'collection',
                            'scroll', 'left', 'right', 'up', 'down', 'swimlane', 'container'}
    query = (tokens(target) | tokens(' '.join(hints))) - ignore
    scored = []
    lookup = {n['node']: n for n in nodes}
    for container in containers:
        labels = tokens(container.get('text', '')+' '+container.get('description', ''))
        ids = tokens(container.get('resource_id', '').split(':id/')[-1])
        # A nearby heading in the same ancestor identifies a nested collection.
        parent = lookup.get(container.get('parent'))
        for _ in range(3):
            if not parent:
                break
            for sibling in nodes:
                if sibling.get('parent') == parent['node'] and sibling.get('text'):
                    labels |= tokens(sibling['text'])
            parent = lookup.get(parent.get('parent'))
        score = 10*len(query & labels)+5*len(query & ids)
        scored.append((score, container))
    best = max(score for score, _ in scored)
    matches = [n for score, n in scored if score == best]
    if len(matches) != 1 or (query and best == 0 and len(containers) > 1):
        raise CollectionError('Collection is ambiguous; provide its visible heading or resource-id hint: '+target)
    return matches[0]


def capture_item_text(target, obs, hints=()):
    """Capture one explicitly hinted field inside a grounded ordinal item."""
    container, item = resolve_item(target, obs, hints)
    children = [item, *descendants(item, obs.get('nodes', []))]
    hinted = {h.split(':id/')[-1].casefold() for h in hints}
    fields = [n for n in children if n.get('text', '').strip()
              and n.get('resource_id', '').split(':id/')[-1].casefold() in hinted]
    if not fields:
        fields = [n for n in children if n.get('text', '').strip()]
    if len(fields) != 1:
        raise CollectionError('Capture requires one text field inside the item; provide its resource-id hint.')
    field = fields[0]
    return field['text'].strip(), {'container':container['node'], 'item':item['node'],
                                 'field':field['node'], 'bounds':field['bounds'],
                                 'collection_resource_id':container.get('resource_id',''),
                                 'resource_id':field.get('resource_id', '')}


def resolve_item(target, obs, hints=()):
    number = ordinal(target)
    if number is None or number < 1:
        raise CollectionError('Invalid ordinal item target: '+target)
    if number > 1 and 'visible' not in tokens(target+' '+' '.join(hints)):
        raise CollectionError('Ordinal scope is ambiguous: specify the visible item position or an item label/resource-id. Absolute off-screen positions require index evidence.')
    container = resolve_collection(target, obs, hints)
    orientation = axis(container, obs)
    if orientation is None:
        raise CollectionError('Cannot establish collection item order: '+target)
    children = sorted(items(container, obs), key=lambda n: n['bounds'][0 if orientation == 'horizontal' else 1])
    if number > len(children):
        raise CollectionError('Requested item '+str(number)+' is not in the grounded visible window ('+str(len(children))+' items). Scroll to reveal it or use a visible item label.')
    item = children[number-1]
    x1, y1, x2, y2 = item['bounds']
    cx1, cy1, cx2, cy2 = container['bounds']
    if not (cx1 <= x1 < x2 <= cx2 and cy1 <= y1 < y2 <= cy2):
        raise CollectionError('Requested item is clipped; reveal it before asserting or tapping: '+target)
    return container, item


def swipe_points(bounds, direction):
    x1, y1, x2, y2 = bounds
    if direction in {'left', 'right'}:
        if x2-x1 < 100:
            raise CollectionError('Horizontal scroll container is too narrow')
        lo, hi = x1+round((x2-x1)*.15), x1+round((x2-x1)*.85)
        start, end = (hi, lo) if direction == 'left' else (lo, hi)
        return start, (y1+y2)//2, end, (y1+y2)//2
    if direction not in {'up', 'down'} or y2-y1 < 100:
        raise CollectionError('Invalid vertical scroll direction/container')
    lo, hi = y1+round((y2-y1)*.28), y1+round((y2-y1)*.88)
    start, end = (hi, lo) if direction == 'down' else (lo, hi)
    return (x1+x2)//2, start, (x1+x2)//2, end


def scroll_changed(before, current, target, direction, hints=()):
    old_container = resolve_collection(target, before, hints, direction)
    new_container = resolve_collection(target, current, hints, direction)
    def labels(container, obs):
        result = {}
        dim = 0 if direction in {'left', 'right'} else 1
        for n in descendants(container, obs.get('nodes', [])):
            text = ' '.join(n.get('text', '').split())
            box = n.get('bounds', [])
            if text and len(box) == 4:
                result.setdefault((n.get('resource_id', ''), text), []).append((box[dim]+box[dim+2])/2)
        return result
    old, new = labels(old_container, before), labels(new_container, current)
    moved = [key[1] for key in old.keys() & new.keys()
             if any(abs(a-b) >= 25 for a in old[key] for b in new[key])]
    appeared = [key[1] for key in new.keys()-old.keys()]
    return bool(moved or appeared), 'Scoped '+direction+' scroll evidence: moved='+repr(moved[:5])+', appeared='+repr(appeared[:5])
