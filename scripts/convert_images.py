"""
고도몰 메타 피드의 상품 이미지를 흰 배경 JPG로 변환해 auto/{goodsNo}.jpg 로 저장
- 투명 배경(알파 채널) 제거, 500px 미만이면 확대
- auto/index.json 에 변환 성공한 id 목록 기록 (Apps Script가 읽음)
"""
import csv
import io
import json
import os
import sys
import time

import requests
from PIL import Image

FEED_URL = "https://manyo.co.kr/data/facebookFeed/facebookFeedExtension.tsv"
OUT_DIR = "auto"
MIN_SIDE = 500
HEADERS = {"User-Agent": "Mozilla/5.0 (toss-catalog-image-bot)"}

csv.field_size_limit(sys.maxsize)


def to_https(url):
    if not url:
        return ""
    if url.startswith("//"):
        return "https:" + url
    if url.lower().startswith("http://"):
        return "https://" + url[7:]
    return url


def convert(data):
    im = Image.open(io.BytesIO(data))
    im.load()
    has_alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
    if has_alpha:
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[3])
        im = bg
    else:
        im = im.convert("RGB")

    w, h = im.size
    if min(w, h) < MIN_SIDE:
        scale = MIN_SIDE / min(w, h)
        im = im.resize((round(w * scale), round(h * scale)), Image.LANCZOS)

    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=90, optimize=True)
    return buf.getvalue()


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    res = requests.get(FEED_URL, headers=HEADERS, timeout=60)
    res.raise_for_status()
    text = res.content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")

    ok, failed, seen = [], [], set()
    for row in reader:
        gid = (row.get("id") or "").strip()
        src = to_https((row.get("image_link") or "").strip())
        avail = (row.get("availability") or "").strip().lower()
        if not gid or not src or gid in seen:
            continue
        if avail and avail != "in stock":
            continue
        seen.add(gid)

        path = os.path.join(OUT_DIR, f"{gid}.jpg")
        try:
            r = requests.get(src, headers=HEADERS, timeout=60)
            r.raise_for_status()
            jpg = convert(r.content)
            changed = True
            if os.path.exists(path):
                with open(path, "rb") as f:
                    changed = f.read() != jpg
            if changed:
                with open(path, "wb") as f:
                    f.write(jpg)
            ok.append(gid)
        except Exception as e:  # 실패해도 기존 변환 파일이 있으면 계속 사용
            failed.append({"id": gid, "src": src, "error": str(e)[:200]})
            if os.path.exists(path):
                ok.append(gid)
        time.sleep(0.2)

    index = {"ids": sorted(set(ok)), "failed": failed}
    with open(os.path.join(OUT_DIR, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    print(f"변환 완료 {len(index['ids'])}건, 실패 {len(failed)}건")
    for item in failed:
        print(f"  실패 {item['id']}: {item['error']}")

    if not index["ids"]:
        sys.exit("변환된 이미지가 없습니다.")


if __name__ == "__main__":
    main()
