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
    # Detect dense text bodies first; sparse descenders/dots must not bridge lines.
    projection=ink.sum(axis=1)
    smoothed=np.convolve(projection,np.ones(3)/3,mode='same')
    threshold=max(3,float(smoothed.max())*.08)
    rows=(smoothed>threshold).astype('uint8')
    rows=cv2.morphologyEx(rows[:,None],cv2.MORPH_CLOSE,np.ones((3,1),np.uint8))[:,0]
    boundaries=np.flatnonzero(np.diff(np.r_[0,rows,0]))
    bands=[(int(a),int(b)) for a,b in zip(boundaries[::2],boundaries[1::2])
           if b-a>=4 and int(ink[a:b].sum())>=50]
    centers=np.array([(a+b)/2 for a,b in bands])
    count,labels,stats,centroids=cv2.connectedComponentsWithStats(ink,8)
    groups=[[] for _ in bands]
    # Assign entire connected strokes, never truncate them at a horizontal cut.
    for label in range(1,count):
        if stats[label,cv2.CC_STAT_AREA]<3 or not bands: continue
        # Ignore vertical scan rules crossing several text bodies.
        if stats[label,cv2.CC_STAT_WIDTH]<=2 and stats[label,cv2.CC_STAT_HEIGHT]>3*np.median([b-a for a,b in bands]): continue
        scores=[int(np.count_nonzero(labels[a:b,stats[label,0]:stats[label,0]+stats[label,2]]==label)) for a,b in bands]
        owner=int(np.argmax(scores)) if max(scores)>0 else int(np.argmin(abs(centers-centroids[label,1])))
        groups[owner].append(label)
    crops=[]
    for group in groups:
        if not group: continue
        mask=np.isin(labels,group)
        coords=cv2.findNonZero(mask.astype('uint8'))
        left,top,lw,lh=cv2.boundingRect(coords)
        if lw<25 or lh<8: continue
        right=min(gray.shape[1],left+lw+6);bottom=min(gray.shape[0],top+lh+5)
        left=max(0,left-6);top=max(0,top-5)
        isolated=np.where(mask[top:bottom,left:right],normal[top:bottom,left:right],255).astype('uint8')
        crop=Image.fromarray(isolated)
        name=f'line-{len(crops):03}.png';crop.save(destination/name)
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
