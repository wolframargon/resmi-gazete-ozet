#!/usr/bin/env python3
"""Yazilan ozeti depoya isler: index.json'u yeniler, commit eder ve main dalina gonderir.

Kullanim: python3 gorev/yayinla.py yyyyMMdd
Basarili olursa son satir: YAYINLANDI <tarih>
"""
import json
import os
import re
import subprocess
import sys

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def git(*args):
    subprocess.run(["git", "-C", KOK] + list(args), check=True)


def main():
    if len(sys.argv) != 2 or not re.fullmatch(r"\d{8}", sys.argv[1]):
        sys.exit("Kullanim: yayinla.py yyyyMMdd")
    tarih = sys.argv[1]

    ozet = os.path.join(KOK, "ozetler", tarih + ".html")
    if not os.path.exists(ozet):
        sys.exit("Ozet dosyasi yok: " + ozet)
    if os.path.getsize(ozet) < 200:
        sys.exit("Ozet dosyasi cok kisa; yayinlanmadi")

    # index.json: uygulamanin okudugu tarih listesi, en yeni basta
    tarihler = sorted(
        (ad[:-5] for ad in os.listdir(os.path.join(KOK, "ozetler")) if re.fullmatch(r"\d{8}\.html", ad)),
        reverse=True,
    )
    with open(os.path.join(KOK, "index.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump({"guncel": tarihler[0], "tarihler": tarihler}, f, separators=(",", ":"))

    git("add", "index.json", "ozetler/" + tarih + ".html")
    git("commit", "-m", "Ozet " + tarih)
    git("push", "origin", "HEAD:main")
    print("YAYINLANDI", tarih)


if __name__ == "__main__":
    main()
