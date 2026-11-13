#!/usr/bin/env python3
"""Yazilan ozeti depoya isler: index.json'u yeniler, commit eder ve gonderir.

Kullanim: python3 gorev/yayinla.py yyyyMMdd [dal]

Hedef dal verilmezse: calisma dali "claude/" ile basliyorsa o dala, degilse main'e gonderilir.
Bulut oturumlari yalnizca "claude/..." dallarina gonderebilir; bu dallara gelen ozetleri
.github/workflows/yayinla.yml is akisi main dalina birlestirir.

Basarili olursa son satir: YAYINLANDI <tarih> <dal>
Gonderim reddedilirse son satir: GONDERILEMEDI <dal>
"""
import html
import json
import os
import re
import subprocess
import sys

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def git(*args, check=True, capture=False):
    return subprocess.run(["git", "-C", KOK] + list(args), check=check, capture_output=capture, text=True)


def boyut(yol):
    """Dosyanin depodaki (satir sonlari LF olan) halinin bayt sayisi."""
    with open(yol, "rb") as f:
        return len(f.read().replace(b"\r\n", b"\n"))


def kucuk_harf(metin):
    """Turkce kurallarla kucuk harfe cevirir (I -> ı, İ -> i); uygulamanin aramasiyla ayni olmali."""
    return metin.replace("I", "ı").replace("İ", "i").lower()


def duz_metin(parca):
    """HTML parcasini aranabilir duz metne cevirir."""
    t = re.sub(r"(?i)</(p|li|h\d|td|tr)>|<br\s*/?>", " ", parca)
    t = re.sub(r"(?s)<[^>]+>", "", t)
    return re.sub(r"\s+", " ", html.unescape(t)).strip()


def bolum(ozet, baslik):
    """Ozetteki bir <h2> bolumunun icerigi (bir sonraki <h2>'ye kadar)."""
    m = re.search(r"(?is)<h2>\s*" + baslik + r".*?</h2>(.*?)(?=<h2>|\Z)", ozet)
    return m.group(1) if m else ""


def arama_kaydi(ozet):
    """arama.json icin bir gunun kaydi: sayi, duzenleme sayisi, personel, onizleme ve duz metin."""
    sayi = re.search(r"(\d{3,6})\s+Sayılı", ozet)
    maddeler = bolum(ozet, "Maddeler")
    duzenleme = len(re.findall(r'(?is)<p>\s*<a\s[^>]*href="[^"]+"[^>]*>[^<]+</a>\s*</p>', maddeler))
    one = bolum(ozet, "Öne çıkanlar")
    basliklar = [duz_metin(b).rstrip(".:").strip() for b in re.findall(r"(?is)<li>\s*<b>(.*?)</b>", one)]
    return {
        "sayi": sayi.group(1) if sayi else "",
        "duzenleme": duzenleme,
        "personel": bool(re.search(r"(?i)<b>\s*Personel mevzuatı\s*</b>", ozet)),
        "onizleme": " · ".join(b for b in basliklar if b),
        "metin": kucuk_harf(duz_metin(ozet)),
    }


def index_yaz():
    """index.json ve arama.json dosyalarini yeniden yazar.

    index.json: uygulamanin okudugu tarih listesi (en yeni basta), her ozetin boyutu ve
    arama.json'un boyutu. Uygulama, telefondaki ozetin boyutu buradakinden farkliysa o gunu
    yeniden indirir; boylece sonradan duzeltilen ozetler telefonda da guncellenir.

    arama.json: butun gunlerin aranabilir bilgileri. Uygulamanin gecmis paneli, telefona
    inmemis gunlerde de bu dosya sayesinde indirmeden arama yapar.
    """
    klasor = os.path.join(KOK, "ozetler")
    tarihler = sorted(
        (ad[:-5] for ad in os.listdir(klasor) if re.fullmatch(r"\d{8}\.html", ad)),
        reverse=True,
    )
    gunler = {}
    for t in tarihler:
        with open(os.path.join(klasor, t + ".html"), encoding="utf-8") as f:
            gunler[t] = arama_kaydi(f.read())
    arama = os.path.join(KOK, "arama.json")
    with open(arama, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"surum": 1, "gunler": gunler}, f, ensure_ascii=False, separators=(",", ":"))
    boyutlar = {t: boyut(os.path.join(klasor, t + ".html")) for t in tarihler}
    with open(os.path.join(KOK, "index.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(
            {"guncel": tarihler[0], "tarihler": tarihler, "boyutlar": boyutlar, "arama_boyut": boyut(arama)},
            f, separators=(",", ":"),
        )


def main():
    if len(sys.argv) not in (2, 3) or not re.fullmatch(r"\d{8}", sys.argv[1]):
        sys.exit("Kullanim: yayinla.py yyyyMMdd [dal]")
    tarih = sys.argv[1]

    ozet = os.path.join(KOK, "ozetler", tarih + ".html")
    if not os.path.exists(ozet):
        sys.exit("Ozet dosyasi yok: " + ozet)
    if os.path.getsize(ozet) < 200:
        sys.exit("Ozet dosyasi cok kisa; yayinlanmadi")

    index_yaz()

    git("add", "index.json", "arama.json", "ozetler/" + tarih + ".html")
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
