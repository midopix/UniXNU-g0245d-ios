#!/usr/bin/env python3
"""Read G0245D iOS color checkpoints with camera scale/tilt calibration.

analyze-bands.py PHOTO [--version v211|v212] [--manifest JSON] [--json]
[--after ISO_TIMESTAMP_OR_UNIX_EPOCH]

The immutable bootstrap stripes calibrate independent image strips. Execution
order comes from the manifest, not framebuffer row order. A fresh photograph
may still show a previous boot's framebuffer; no automatic code fix is chosen.
"""
import argparse
import colorsys
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import numpy as np
from PIL import Image, ImageOps

BASE = [
    (1300, [255,0,255], 'start_first_cpu 入口，MMU 关'),
    (1320, [255,255,0], 'common_start，引导页表已建'),
    (1340, [0,255,255], 'TCR 编程完'),
    (1360, [0,255,0], 'TTBR0/1 编程完'),
    (1380, [0,0,255], '开 MMU 前最后一笔'),
    (1400, [255,255,255], 'MMU + 缓存已开'),
    (1420, [255,0,0], 'start.s ret 即将执行'),
    (1440, [255,0,128], '进入 arm_init 函数体'),
    (1460, [0,128,255], 'PE_init_platform 返回'),
    (1500, [255,128,0], 'boot_progress_init 返回'),
    (1520, [128,0,255], 'Apple timer/wfe/misc 初始化返回'),
    (1540, [255,192,0], 'CPU 拓扑就绪，thread_bootstrap 前'),
    (1560, [0,192,255], 'thread_bootstrap 返回'),
    (1580, [0,255,128], 'cpu_bootstrap 返回'),
    (1600, [0,128,128], 'timer_call_init 返回'),
    (1640, [128,128,255], 'processor_bootstrap 返回'),
    (1480, [128,255,0], '早期 init 全过，arm_vm_init 前'),
]
BANDS = {row: (tuple(rgb), note) for row, rgb, note in BASE}
ANCHORS = BASE[:9]


def manifest_for(args):
    path = args.manifest
    if path is None and args.version != 'v211':
        path = Path(__file__).parent / 'band-manifests' / (args.version + '.json')
    obj = json.loads(Path(path).read_text()) if path else {
        'version': 'v211', 'checkpoints': [
            dict(row=r, rgb=c, note=n, order=i) for i, (r,c,n) in enumerate(BASE)]}
    points = obj.get('checkpoints', [])
    if not points:
        raise ValueError('manifest has no checkpoints')
    for i, p in enumerate(points):
        if not isinstance(p.get('row'), int) or not 0 <= p['row'] < 1920:
            raise ValueError('invalid framebuffer row in manifest')
        rgb = p.get('rgb')
        if not isinstance(rgb, list) or len(rgb) != 3 or any(
                not isinstance(v, int) or not 0 <= v <= 255 for v in rgb):
            raise ValueError('manifest rgb must contain three integers 0..255')
        p.setdefault('order', i)
        p.setdefault('note', '')
    if len({p['row'] for p in points}) != len(points):
        raise ValueError('duplicate framebuffer rows in manifest')
    if len({p['order'] for p in points}) != len(points):
        raise ValueError('duplicate execution order in manifest')
    obj['checkpoints'] = sorted(points, key=lambda p: p['order'])
    return obj


def color_mask(pixels, rgb):
    p = pixels.astype(float) / 255
    mx, mn = p.max(axis=-1), p.min(axis=-1)
    d = mx - mn
    sat = d / np.maximum(mx, 1e-6)
    if min(rgb) > 200:
        return (sat < .25) & (mn > .60)
    r, g, b = p[...,0], p[...,1], p[...,2]
    delta = np.maximum(d, 1e-6)
    idx = p.argmax(axis=-1)
    hue = np.where(idx == 0, ((g-b)/delta) % 6,
                   np.where(idx == 1, (b-r)/delta+2, (r-g)/delta+4)) * 60
    target = colorsys.rgb_to_hsv(*(v/255 for v in rgb))[0] * 360
    distance = np.abs((hue-target+180) % 360-180)
    return (distance <= 23) & (sat > .40) & (mx > .36)


def runs(mask):
    edges = np.diff(np.r_[False, mask, False].astype(int))
    return [(int(a),int(b)) for a,b in zip(
        np.flatnonzero(edges == 1), np.flatnonzero(edges == -1))]


def calibrate_strip(pixels):
    candidates = {row: [(a+(b-a-1)/2, b-a) for a,b in
        runs(color_mask(pixels,rgb)) if 2 <= b-a <= 35] for row,rgb,_ in ANCHORS}
    best = None
    for y0, width0 in candidates[1300]:
        for y1, width1 in candidates[1320]:
            scale = (y0-y1)/20
            if not .15 <= scale <= 3:
                continue
            if not all(.25*8*scale <= width <= 2*8*scale+1 for width in (width0,width1)):
                continue
            matches = []
            for row,_,_ in ANCHORS:
                pred = y0-(row-1300)*scale
                choices = [(abs(y-pred),y) for y,width in candidates[row]
                           if .25*8*scale <= width <= 2*8*scale+1]
                if choices:
                    error,y = min(choices)
                    if error <= max(1.6,scale*3.3):
                        matches.append((row,y,error))
            if len(matches) < 7 or 1400 not in [m[0] for m in matches]:
                continue
            quality = (len(matches),-sum(m[2] for m in matches))
            if best is None or quality > best[0]:
                fitted,intercept = np.polyfit([1300-m[0] for m in matches],
                                              [m[1] for m in matches],1)
                best = (quality,float(intercept),float(fitted))
    return best


def calibrate(a):
    h,w = a.shape[:2]
    strips = []
    half = max(2,w//450)
    for x in np.linspace(.08*w,.92*w,29).astype(int):
        pixels = np.median(a[:,x-half:x+half+1],axis=1)
        fit = calibrate_strip(pixels)
        if fit:
            strips.append(dict(x=int(x),pixels=pixels,y0=fit[1],scale=fit[2]))
    if len(strips) < 5:
        return [],'不足五个图像采样列能识别同一组 bootstrap 色带'
    best = []
    for i,first in enumerate(strips):
        for second in strips[i+1:]:
            dx = second['x']-first['x']
            if dx < .1*w:
                continue
            slope = (second['y0']-first['y0'])/dx
            inliers = [s for s in strips if abs(first['y0']+slope*(
                s['x']-first['x'])-s['y0']) <= max(2,s['scale']*3)]
            if len(inliers) > len(best):
                best = inliers
    if len(best) < 5 or best[-1]['x']-best[0]['x'] < .18*w:
        return [],'bootstrap 色带没有跨足够屏幕宽度保持一致几何关系'
    scale = float(np.median([s['scale'] for s in best]))
    best = [s for s in best if .65*scale < s['scale'] < 1.4*scale]
    return (best,None) if len(best) >= 5 else ([],'透视或遮挡过大，无法可靠校准')


def checkpoint(point,strips,height,rescale):
    matches,visible,ys = 0,0,[]
    for s in strips:
        center = s['y0']-(point['row']-1300)*s['scale']
        radius = max(2,6.5*s['scale'])
        lo,hi = round(center-radius),round(center+radius)+1
        if lo < 0 or hi > height:
            continue
        visible += 1
        stripe = [(b-a,lo+(a+b-1)/2) for a,b in
                  runs(color_mask(s['pixels'][lo:hi],point['rgb']))]
        if stripe:
            length,actual = max(stripe)
            if length >= max(2,2.5*s['scale']):
                matches += 1
                ys.append(actual*rescale)
    coverage = visible/max(1,len(strips))
    support = matches/max(1,visible)
    status = ('out_of_frame' if coverage < .65 else 'present' if support >= .60
              else 'absent' if support <= .20 else 'uncertain')
    return dict(point,status=status,column_support=round(support,3),
                visible_fraction=round(coverage,3),
                photo_y=round(float(np.median(ys)),1) if ys else None)


def image_time(im,path):
    exif = im.getexif()
    raw = exif.get(36867) or exif.get(306)
    if raw:
        try:
            capture = datetime.strptime(str(raw),'%Y:%m:%d %H:%M:%S')
            offset = exif.get(36881) or exif.get(36880)
            capture = (datetime.fromisoformat(capture.isoformat()+str(offset))
                       if offset else capture.astimezone())
            return capture,'exif'
        except (ValueError,TypeError):
            pass
    return datetime.fromtimestamp(Path(path).stat().st_mtime).astimezone(),'mtime'


def analyze(path,manifest,after=None):
    with Image.open(path) as original:
        capture,source = image_time(original,path)
        im = ImageOps.exif_transpose(original).convert('RGB')
        size = list(im.size)
        factor = min(1,1100/max(im.width,1))
        if factor < 1:
            im = im.resize((round(im.width*factor),round(im.height*factor)))
    a = np.asarray(im)
    normal = analyze_pixels(a, path, manifest, capture, source, size, factor, after, 0)
    if normal['ready_for_diagnosis'] or normal['fresh_after_flash'] is False:
        return normal
    # Some camera photos have valid EXIF but the phone in frame is upside down.
    # Keep the source timestamp and require the same version/geometry checks.
    rotated = analyze_pixels(a[::-1, ::-1], path, manifest, capture, source, size, factor, after, 180)
    if rotated['ready_for_diagnosis'] or (rotated['geometry_valid'] and not normal['geometry_valid']):
        return rotated
    return normal


def analyze_pixels(a, path, manifest, capture, source, size, factor, after, rotation):
    strips,error = calibrate(a)
    fresh = None if after is None else capture > after
    result = dict(schema=1,image=str(Path(path).resolve()),version=manifest.get('version','custom'),
        image_size=size,capture_time=capture.isoformat(),capture_time_source=source,
        rotation_after_exif_degrees=rotation,
        fresh_after_flash=fresh,framebuffer_may_contain_previous_boot=True,
        geometry_valid=not bool(error),ready_for_diagnosis=False,accepted=False,
        error=error,checkpoints=[])
    if error:
        return result
    result['geometry'] = dict(sample_columns=len(strips),pixel_scale_per_raw_row=round(
        float(np.median([s['scale'] for s in strips]))/factor,4),
        anchor_rows=[p[0] for p in ANCHORS])
    points = [checkpoint(p,strips,a.shape[0],1/factor) for p in manifest['checkpoints']]
    result['checkpoints'] = points
    states = {p['row']:p['status'] for p in points}
    required = manifest.get('version_markers',[])
    evidence = ('confirmed' if required and all(states.get(r)=='present' for r in required)
                else 'not_confirmed' if required else 'no_unique_version_marker')
    result['version_evidence'] = evidence
    missing = next((i for i,p in enumerate(points) if p['status']!='present'),len(points))
    contradictions = [p['row'] for p in points[missing+1:] if p['status']=='present']
    before = points[missing-1] if missing else None
    following = points[missing] if missing < len(points) else None
    result.update(inconsistent_sequence=contradictions,last_contiguous_checkpoint=before,
                  last_checkpoint=before,next_checkpoint=following)
    ready = bool(fresh is not False and not contradictions and missing > 0 and
                 (not required or evidence=='confirmed') and
                 (following is None or following['status']=='absent'))
    result['ready_for_diagnosis'] = ready
    # An orchestration consumer may accept only a fresh image with this version's
    # unique sentinel. A generic v211 observation remains useful for manual review.
    result['accepted'] = bool(ready and fresh is True and required and evidence=='confirmed')
    if ready:
        result['interval'] = dict(after_row=before['row'],before_row=following['row'] if following else None,
            after_note=before['note'],before_note=following['note'] if following else None)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('image',type=Path)
    p.add_argument('--version',default='v211')
    p.add_argument('--manifest',type=Path)
    p.add_argument('--json',action='store_true')
    p.add_argument('--after',help='ISO timestamp or Unix epoch of flash')
    args = p.parse_args()
    try:
        after = None
        if args.after:
            try:
                after = datetime.fromtimestamp(float(args.after),timezone.utc)
            except ValueError:
                after = datetime.fromisoformat(args.after.replace('Z','+00:00'))
                if after.tzinfo is None:
                    after = after.astimezone()
        result = analyze(args.image,manifest_for(args),after)
    except (ValueError,OSError) as exc:
        result = dict(schema=1,geometry_valid=False,ready_for_diagnosis=False,
                      accepted=False,error=str(exc))
    if args.json:
        print(json.dumps(result,ensure_ascii=False,indent=2))
    else:
        print(f"图片: {args.image}  版本: {result.get('version',args.version)}")
        if result.get('error'):
            print('无法可靠判读: '+result['error'])
        for point in result.get('checkpoints',[]):
            print(f"raw {point['row']:4}  {point['status']:12}  y={str(point['photo_y']):>7}  {point['note']}")
        interval = result.get('interval')
        if interval:
            print(f"执行顺序定位: {interval['after_row']} ({interval['after_note']}) → "
                  f"{interval['before_row']} ({interval['before_note']})")
        elif not result.get('error'):
            print('证据不足或序列冲突，保留观察结果，不能自动确定故障区间。')
        print('提示：菜单照片可能保留上一轮显存；照片时间不能证明每条色带来自本轮。')
    return 0 if result.get('ready_for_diagnosis') else 2

if __name__ == '__main__':
    sys.exit(main())
