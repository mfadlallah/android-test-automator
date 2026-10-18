"""Bounded, identity-based ordinal search across overlapping collection windows."""
from .collections import CollectionError, resolve_collection, items, descendants, axis

OPPOSITE={'left':'right','right':'left','up':'down','down':'up'}


def window(target, obs, hints, direction, known_target=None, ignored=None):
    container=resolve_collection(target,obs,hints,direction)
    dim=0 if direction in {'left','right'} else 1
    if axis(container,obs)!=('horizontal' if dim==0 else 'vertical'):
        raise CollectionError('Tracked collection axis is not grounded.')
    ids={h.split(':id/')[-1].casefold() for h in hints}
    rows=[]
    children=sorted(items(container,obs),key=lambda n:n['bounds'][dim])
    for index,item in enumerate(children):
        fields=[n for n in [item,*descendants(item,obs.get('nodes',[]))]
                if n.get('text','').strip() and n.get('resource_id','').split(':id/')[-1].casefold() in ids
                and len(n.get('bounds',[]))==4 and n['bounds'][2]>n['bounds'][0] and n['bounds'][3]>n['bounds'][1]]
        if len(fields)!=1:
            box=item['bounds'];cb=container['bounds']
            target_seen=known_target is not None and any(r['identity']==tuple(known_target) for r in rows)
            trailing_edge=(index==len(children)-1 and box[dim+2]>=cb[dim+2])
            # Never skip an unknown ordinal. Only an unreadable final edge
            # fragment AFTER an already identified target may be excluded.
            if not fields and target_seen and trailing_edge:
                if ignored is not None:
                    ignored.append({'node':item['node'],'bounds':box,'reason':'Unreadable trailing edge after known target; not counted.'})
                continue
            raise CollectionError('Tracking requires one identity field per visible item; node='+str(item['node'])+' bounds='+str(item['bounds'])+' matches='+str(len(fields)))
        field=fields[0]
        rows.append({'identity':(field['resource_id'],field['text'].strip()),'item':item,'field':field})
    keys=[r['identity'] for r in rows]
    if not rows or len(set(keys))!=len(keys):
        raise CollectionError('Missing or duplicate item identities; ordinal tracking is ambiguous.')
    return container,rows


class ItemTracker:
    def __init__(self,target,number,hints,direction,max_swipes=12):
        if number<1 or direction not in OPPOSITE:
            raise CollectionError('Invalid tracked ordinal or direction.')
        self.target=target;self.number=number;self.hints=hints;self.direction=direction
        self.max_swipes=max_swipes;self.swipes=0;self.phase='anchor';self.previous=None
        self.stalls=0;self.sequence=[];self.extent=0;self.trace=[];self.selected=None

    def observe(self,obs):
        known=self.sequence[self.number-1] if len(self.sequence)>=self.number else None
        ignored=[]
        try:
            container,rows=window(self.target,obs,self.hints,self.direction,known,ignored)
        except CollectionError as exc:
            self.trace.append({'phase':self.phase,'swipes':self.swipes,'error':str(exc)})
            raise
        dim=0 if self.direction in {'left','right'} else 1
        signature=[(r['identity'],r['item']['bounds'][dim],r['item']['bounds'][dim+2]) for r in rows]
        self.extent=max(self.extent,max(r['item']['bounds'][dim+2]-r['item']['bounds'][dim] for r in rows))
        self.trace.append({'phase':self.phase,'window':[list(r['identity']) for r in rows],
                           'bounds':[r['item']['bounds'] for r in rows],'swipes':self.swipes,'ignored_edges':ignored})
        if self.phase=='anchor':
            self.stalls=self.stalls+1 if signature==self.previous else 0
            if self.stalls<2:
                self.previous=signature
                return self.swipe(container,OPPOSITE[self.direction],'Establish observed collection start')
            self.phase='seek';self.previous=None;self.stalls=0
            self.sequence=[r['identity'] for r in rows]
        else:
            current=[r['identity'] for r in rows]
            overlap=next((k for k in range(min(len(self.sequence),len(current)),0,-1)
                          if self.sequence[-k:]==current[:k]),0)
            if not overlap:
                raise CollectionError('Collection windows lost identity overlap or changed order; refusing ordinal inference.')
            extra=current[overlap:]
            if any(key in self.sequence for key in extra):
                raise CollectionError('Repeated item identity or collection reorder detected.')
            self.sequence.extend(extra)
            self.stalls=self.stalls+1 if signature==self.previous else 0
        self.previous=signature
        if len(self.sequence)>=self.number:
            wanted=self.sequence[self.number-1]
            matches=[r for r in rows if r['identity']==wanted]
            if len(matches)==1:
                item=matches[0]['item'];box=item['bounds'];cb=container['bounds']
                full=all([cb[0]<=box[0],cb[1]<=box[1],box[2]<=cb[2],box[3]<=cb[3]]) and box[dim+2]-box[dim]>=.9*self.extent
                if full:
                    self.selected={'identity':list(wanted),'ordinal':self.number,'collection_resource_id':container['resource_id'],
                                   'target':self.target,'hints':list(self.hints),'direction':self.direction,'bounds':box}
                    self.selected['minimum_extent']=.9*self.extent
                    return None
                if box[dim]<=cb[dim] and box[dim+2]-box[dim]<.9*self.extent:
                    raise CollectionError('Tracked item was overscrolled and clipped; refusing a different item.')
            elif self.number<len(self.sequence):
                raise CollectionError('Tracked item moved out of view before it could be selected.')
        if self.stalls>=2:
            raise CollectionError('Collection stopped moving before the requested item was safely exposed.')
        return self.swipe(container,self.direction,'Reveal tracked item '+str(self.number))

    def swipe(self,container,direction,reason):
        if self.swipes>=self.max_swipes:
            raise CollectionError('Tracked item search exhausted its bounded swipe budget.')
        self.swipes+=1
        return {'action':'scroll','node':container['node'],'direction':direction,'scroll_fraction':.25,
                'reason':reason+' ('+str(self.swipes)+'/'+str(self.max_swipes)+')',
                'evidence':'Identity-tracked collection '+str(container.get('resource_id'))}


def resolve_tracked(selected,obs):
    container,rows=window(selected['target'],obs,selected['hints'],selected['direction'],selected['identity'])
    matches=[r for r in rows if list(r['identity'])==selected['identity']]
    if len(matches)!=1:
        raise CollectionError('Previously tracked item identity is missing or ambiguous in the current observation.')
    row=matches[0]
    box=row['item']['bounds'];cb=container['bounds']
    if not(cb[0]<=box[0]<box[2]<=cb[2] and cb[1]<=box[1]<box[3]<=cb[3]):
        raise CollectionError('Tracked item is clipped in the current observation.')
    dim=0 if selected['direction'] in {'left','right'} else 1
    if box[dim+2]-box[dim]<selected['minimum_extent']:
        raise CollectionError('Tracked item became clipped before capture/tap.')
    return container,row['item']
