"""Resolve named native controls using semantic ID and accessibility type."""
import re


def named_control(nodes, target):
    words=re.sub(r'(?<=[a-z0-9])(?=[A-Z])',' ',target).casefold().split()
    types={'checkbox':'checkbox','switch':'switch','radio':'radiobutton','radiobutton':'radiobutton'}
    kind=next((types[w] for w in words if w in types),None)
    if kind is None:
        return None
    name=set(words)-set(types)-{'button','control','the'}
    if not name:
        return None
    matches=[]
    for node in nodes:
        if not node.get('enabled',False):continue
        if node.get('class_name','').split('.')[-1].casefold()!=kind:continue
        suffix=node.get('resource_id','').split('/')[-1]
        suffix=re.sub(r'(?<=[a-z0-9])(?=[A-Z])',' ',suffix)
        tokens=set(re.findall(r'\w+',suffix.replace('_',' ').casefold()))
        if name <= tokens:
            matches.append(node)
    return matches[0] if len(matches)==1 else None
