"""Prepare whole-page handwriting samples for a style-conditioned model."""
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageOps

Image.MAX_IMAGE_PIXELS = 24_000_000


def process_sample(source, destination):
    destination=Path(destination); destination.mkdir(parents=True,exist_ok=True)
    with Image.open(source) as opened:
        if opened.width*opened.height>24_000_000: raise ValueError('图片过大，请缩小到 2400 万像素以内。')
        image=ImageOps.exif_transpose(opened).convert('RGB')
    if min(image.size)<160: raise ValueError('图片太小，请上传清晰的整段字迹。')
    image.thumbnail((2400,3000))
    rgb=np.array(image); gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
    background=cv2.GaussianBlur(gray,(0,0),max(9,min(gray.shape)/40))
    normal=cv2.divide(gray,background,scale=255)
    ink=(normal<155).astype('uint8')
    # Remove isolated specks; retain disconnected dots in actual writing.
    count,labels,stats,_=cv2.connectedComponentsWithStats(ink,8)
    for index in range(1,count):
        if stats[index,cv2.CC_STAT_AREA]<3: ink[labels==index]=0
    points=cv2.findNonZero(ink)
    if points is None or int(ink.sum())<150: raise ValueError('没有检测到足够笔迹，请使用深色笔和浅色纸。')
    ratio=float(ink.mean())
    if ratio>.35: raise ValueError('背景过暗或笔迹区域不清晰，请重新拍摄。')
    # Estimate modest page skew from long text baselines, ignoring isolated strokes.
    edges=cv2.Canny((ink*255),50,150)
    lines=cv2.HoughLinesP(edges,1,np.pi/180,threshold=55,minLineLength=max(70,gray.shape[1]//7),maxLineGap=25)
    angles=[]
    if lines is not None:
        for x1,y1,x2,y2 in lines[:,0]:
            angle=float(np.degrees(np.arctan2(y2-y1,x2-x1)))
            if abs(angle)<12: angles.append(angle)
    angle=float(np.median(angles)) if angles else 0
    if abs(angle)>.3:
        matrix=cv2.getRotationMatrix2D((gray.shape[1]/2,gray.shape[0]/2),angle,1)
        normal=cv2.warpAffine(normal,matrix,(gray.shape[1],gray.shape[0]),borderValue=255)
        ink=cv2.warpAffine(ink,matrix,(gray.shape[1],gray.shape[0]),flags=cv2.INTER_NEAREST,borderValue=0)
    x,y,w,h=cv2.boundingRect(cv2.findNonZero(ink))
    if h<18: raise ValueError('笔迹高度太小，请靠近拍摄。')
    projection=ink.sum(axis=1)
    rows=(projection>max(2,ink.shape[1]*.001)).astype('uint8')
    rows=cv2.morphologyEx(rows[:,None],cv2.MORPH_CLOSE,np.ones((7,1),np.uint8))[:,0]
    boundaries=np.flatnonzero(np.diff(np.r_[0,rows,0]))
    crops=[]
    for start,end in zip(boundaries[::2],boundaries[1::2]):
        if end-start<8 or int(ink[start:end].sum())<50: continue
        coords=cv2.findNonZero(ink[start:end])
        lx,ly,lw,lh=cv2.boundingRect(coords)
        if lw<25: continue
        top=max(0,start+ly-5); bottom=min(gray.shape[0],start+ly+lh+5)
        left=max(0,lx-6); right=min(gray.shape[1],lx+lw+6)
        crop=Image.fromarray(normal[top:bottom,left:right])
        name=f'line-{len(crops):03}.png'; crop.save(destination/name)
        crops.append({'file':name,'width':crop.width,'height':crop.height,'bbox':[int(left),int(top),int(right),int(bottom)]})
    if not crops: raise ValueError('未能切分出文字行，请用横向、清晰、行距适中的样本。')
    if len(crops)>24: raise ValueError('检测到过多区域，请只上传一段字迹，并裁去其他内容。')
    Image.fromarray(normal).save(destination/'normalized.png')
    blur=float(cv2.Laplacian(gray,cv2.CV_64F).var())
    warnings=[]
    if blur<40: warnings.append('图片可能偏模糊，请检查每行笔画是否清晰。')
    if len(crops)<3: warnings.append('建议提供至少三行自然书写，提高风格覆盖。')
    if any(c['height']>c['width']*.5 for c in crops): warnings.append('部分切分区域可能不是完整文字行，请检查。')
    return {'lines':crops,'warnings':warnings,'skew_deg':round(angle,2),'ink_ratio':round(ratio,4),
            'blur_score':round(blur,2),'recognition':'not-performed','pixel_size':list(image.size)}
