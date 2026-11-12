#!/usr/bin/env python3
"""Yazilan ozeti depoya isler: index.json'u yeniler, commit eder ve gonderir.

Kullanim: python3 gorev/yayinla.py yyyyMMdd [dal]

Hedef dal verilmezse: calisma dali "claude/" ile basliyorsa o dala, degilse main'e gonderilir.
Bulut oturumlari yalnizca "claude/..." dallarina gonderebilir; bu dallara gelen ozetleri
.github/workflows/yayinla.yml is akisi main dalina birlestirir.

Basarili olursa son satir: YAYINLANDI <tarih> <dal>
Gonderim reddedilirse son satir: GONDERILEMEDI <dal>
"""
import json
import os
import re
import subprocess
import sys

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def git(*args, check=True, capture=False):
    return subprocess.run(["git", "-C", KOK] + list(args), check=check, capture_output=capture, text=True)


def main():
    if len(sys.argv) not in (2, 3) or not re.fullmatch(r"\d{8}", sys.argv[1]):
        sys.exit("Kullanim: yayinla.py yyyyMMdd [dal]")
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
    # Yeniden denemede (onceki calistirma commit etmis olabilir) ikinci kez commit etme
    if git("diff", "--cached", "--quiet", check=False).returncode != 0:
        kimlik = []
        if not git("config", "user.name", check=False, capture=True).stdout.strip():
            kimlik = ["-c", "user.name=Resmi Gazete Ozet", "-c", "user.email=resmi-gazete-ozet@users.noreply.github.com"]
        git(*kimlik, "commit", "-m", "Ozet " + tarih)

    if len(sys.argv) == 3:
        hedef = sys.argv[2]
    else:
        dal = git("rev-parse", "--abbrev-ref", "HEAD", capture=True).stdout.strip()
        hedef = dal if dal.startswith("claude/") else "main"
    if not re.fullmatch(r"[A-Za-z0-9._/-]+", hedef) or hedef.startswith("-"):
        sys.exit("Gecersiz dal adi: " + hedef)

    if git("push", "origin", "HEAD:refs/heads/" + hedef, check=False).returncode != 0:
        print("GONDERILEMEDI", hedef)
        sys.exit(1)
    print("YAYINLANDI", tarih, hedef)


if __name__ == "__main__":
    main()
