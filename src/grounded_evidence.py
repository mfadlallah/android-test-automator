"""Save reviewable image evidence from already grounded bounds, without inference."""
import io
import json


def save_grounded_evidence(folder,stem,obs,bounds,metadata):
    record={**metadata,'source_image':f"{obs.get('observation',0):02d}.png",'grounded_bounds':bounds}
    try:
        from PIL import Image, ImageDraw
        if not bounds or len(bounds)!=4:
            raise ValueError('No grounded bounds available; no guessed crop saved.')
        source=Image.open(io.BytesIO(obs.get('png',b''))).convert('RGB')
        x1,y1,x2,y2=map(int,bounds)
        if not (0<=x1<x2<=source.width and 0<=y1<y2<=source.height):
            raise ValueError('Evidence bounds are outside the current screenshot.')
        box=(max(0,x1-12),max(0,y1-12),min(source.width,x2+12),min(source.height,y2+12))
        crop=source.crop(box)
        scale=min(3.0,1600/max(crop.size))
        if scale>1:
            crop=crop.resize((round(crop.width*scale),round(crop.height*scale)),Image.Resampling.LANCZOS)
        crop_name=stem+'-crop.png';context_name=stem+'-with-context.png'
        crop.save(folder/crop_name)
        ImageDraw.Draw(source).rectangle((x1,y1,x2-1,y2-1),outline='red',width=4)
        source.save(folder/context_name)
        record.update(crop_image=crop_name,context_image=context_name,crop_bounds=list(box),zoom_scale=max(1.0,scale))
    except Exception as exc:
        record['crop_error']=str(exc)
    (folder/(stem+'.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    return record
