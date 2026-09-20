import base64,io
import numpy as np
from PIL import Image
def data_url_to_mask(data_url:str)->np.ndarray:
    if ',' not in data_url: raise ValueError('Invalid mask data URL')
    raw=base64.b64decode(data_url.split(',',1)[1])
    with Image.open(io.BytesIO(raw)) as im: rgba=np.asarray(im.convert('RGBA'))
    return rgba[:,:,3]>16
def mask_to_png(mask):
    out=io.BytesIO();Image.fromarray(np.asarray(mask,dtype=np.uint8)*255,'L').save(out,'PNG');return out.getvalue()
def overlay_png(mask,color=(255,72,72),alpha=255):
    h,w=mask.shape;rgba=np.zeros((h,w,4),dtype=np.uint8);rgba[mask]=[*color,alpha];out=io.BytesIO();Image.fromarray(rgba,'RGBA').save(out,'PNG');return out.getvalue()
def load_mask(path):
    with Image.open(path) as im:return np.asarray(im.convert('L'))>127
def save_mask(path,mask):Image.fromarray(mask.astype(np.uint8)*255,'L').save(path,'PNG')
def fit_mask(mask,height,width):
    arr=np.asarray(mask,dtype=bool)
    if arr.shape==(height,width):return arr
    im=Image.fromarray(arr.astype(np.uint8)*255,'L').resize((width,height),Image.NEAREST)
    return np.asarray(im)>127
