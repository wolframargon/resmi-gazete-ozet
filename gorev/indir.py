#!/usr/bin/env python3
"""Gunluk Resmi Gazete sayisini indirir ve ozetlenmeye hazir hale getirir.

Kullanim: python3 gorev/indir.py [yyyyMMdd]   (tarih verilmezse Turkiye saatine gore bugun)
Ciktinin ilk satiri: ZATEN_VAR | YAYINLANMADI | AG_HATASI | HAZIR <klasor>

HAZIR'dan sonraki satirlar:
  TARIH <yyyyMMdd>
  FIHRIST_ADRESI <adres>
  MUKERRER M1 fihrist-M1.txt <adres>      ayni gun cikan mukerrer sayi (varsa)
  DOSYA <ad> <boyut> KB                   klasordeki her dosya
  EK <ek dosyasi> <- <madde dosyasi> <adres>   bir maddenin sayfasindan bulunan ek
  INDIRILEMEDI <dosyalar>                 indirilemeyenler (varsa)
"""
import datetime
import html
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.request

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = "Mozilla/5.0 (X11; Linux x86_64) ResmiGazeteOzet/1.0"
MADDE = re.compile(r'href\s*=\s*"(\d{8}(?:M\d+)?-\d+(?:-\d+)?\.(?:htm|html|pdf))"', re.I)


def indir(url, deneme=3):
    """Dosyayi indirir. Gecici ag hatalarinda birkac kez yeniden dener; 404 hemen bildirilir."""
    son_hata = None
    for i in range(deneme):
        try:
            istek = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(istek, timeout=45) as yanit:
                return yanit.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise
            son_hata = e
        except (urllib.error.URLError, OSError) as e:
            son_hata = e
        if i < deneme - 1:
            time.sleep(3 * (i + 1))
    raise son_hata


def coz(bayt):
    # Sayfalar genellikle windows-1254 kodlamalidir; meta etiketi utf-8 diyorsa ona uy
    if re.search(rb'charset\s*=\s*"?utf-8', bayt[:2048], re.I):
        return bayt.decode("utf-8", "replace")
    return bayt.decode("cp1254", "replace")


def metne_cevir(sayfa, taban):
    t = re.sub(r"(?is)<(style|script)[^>]*>.*?</\1>", "", sayfa)
    t = re.sub(r"[\r\n]+", " ", t)

    def baglanti(m):
        h = m.group(1)
        if not re.match(r"https?:", h):
            h = taban + h
        return " [BAGLANTI: %s] " % h

    t = re.sub(r'(?is)<a\s[^>]*?href\s*=\s*"([^"]+)"[^>]*>', baglanti, t)
    t = re.sub(r"(?i)</p>|<br\s*/?>|</tr>|</h\d>|</div>", "\n", t)
    t = re.sub(r"(?s)<[^>]+>", "", t)
    t = html.unescape(t)
    t = re.sub(r"[ \t ]+", " ", t)
    t = re.sub(r" ?\n[ \n]*", "\n", t)
    return t.strip()


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) > 1:
        tarih = sys.argv[1]
    else:
        turkiye = datetime.timezone(datetime.timedelta(hours=3))
        tarih = datetime.datetime.now(turkiye).strftime("%Y%m%d")
    if not re.fullmatch(r"\d{8}", tarih):
        sys.exit("Tarih yyyyMMdd biciminde olmali")

    if os.path.exists(os.path.join(KOK, "ozetler", tarih + ".html")):
        print("ZATEN_VAR", tarih)
        return

    taban = "https://www.resmigazete.gov.tr/eskiler/%s/%s/" % (tarih[:4], tarih[4:6])
    try:
        fihrist = coz(indir(taban + tarih + ".htm"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print("YAYINLANMADI", tarih)
            return
        print("AG_HATASI", "HTTP", e.code)
        sys.exit(2)
    except (urllib.error.URLError, OSError) as e:
        print("AG_HATASI", e)
        sys.exit(2)

    cikti = os.path.join(KOK, "calisma", tarih)
    shutil.rmtree(cikti, ignore_errors=True)
    os.makedirs(cikti)

    hatalar, ekler = [], []
    sayi_indir(fihrist, taban, cikti, "fihrist.txt", hatalar, ekler)

    # Ayni gun cikan mukerrer sayilar: 20261231M1.htm, M2.htm ... (ilk 404'te dur)
    mukerrerler = []
    for n in range(1, MUKERRER_SINIRI + 1):
        sayi = "%sM%d" % (tarih, n)
        try:
            ek_fihrist = coz(indir(taban + sayi + ".htm"))
        except (urllib.error.URLError, OSError):
            break
        sayi_indir(ek_fihrist, taban, cikti, "fihrist-M%d.txt" % n, hatalar, ekler)
        mukerrerler.append((n, taban + sayi + ".htm"))

    print("HAZIR", cikti)
    print("TARIH", tarih)
    print("FIHRIST_ADRESI", taban + tarih + ".htm")
    for n, adres in mukerrerler:
        print("MUKERRER", "M%d" % n, "fihrist-M%d.txt" % n, adres)
    for ad in sorted(os.listdir(cikti)):
        print("DOSYA", ad, round(os.path.getsize(os.path.join(cikti, ad)) / 1024), "KB")
    for madde, ek in ekler:
        print("EK", ek, "<-", madde, taban + ek)
    if hatalar:
        print("INDIRILEMEDI", ", ".join(hatalar))


MUKERRER_SINIRI = 9


def kaydet(taban, cikti, ad):
    """Tek bir dosyayi indirir: PDF oldugu gibi, HTML duz metne cevrilerek. HTML'in ham halini dondurur."""
    bayt = indir(taban + ad)
    if ad.lower().endswith(".pdf"):
        with open(os.path.join(cikti, ad), "wb") as f:
            f.write(bayt)
        return None
    sayfa = coz(bayt)
    with open(os.path.join(cikti, os.path.splitext(ad)[0] + ".txt"), "w", encoding="utf-8") as f:
        f.write(metne_cevir(sayfa, taban))
    return sayfa


def sayi_indir(fihrist, taban, cikti, fihrist_adi, hatalar, ekler):
    """Bir sayinin fihristini ve maddelerini indirir.

    Yonetmeliklerin ekleri (ornegin 20261112-1-1.pdf) fihristte degil, maddenin kendi
    sayfasinda baglanti olarak durur; bu yuzden her HTML maddenin icindeki ekler de indirilir.
    """
    with open(os.path.join(cikti, fihrist_adi), "w", encoding="utf-8") as f:
        f.write(metne_cevir(fihrist, taban))

    maddeler = list(dict.fromkeys(MADDE.findall(fihrist)))
    gorulen = set(a.lower() for a in maddeler)
    for ad in maddeler:
        try:
            sayfa = kaydet(taban, cikti, ad)
        except (urllib.error.URLError, OSError) as e:
            hatalar.append("%s (%s)" % (ad, e))
            continue
        if sayfa is None:
            continue
        # Yalnizca bu maddeye ait ekler: adi "<madde>-" ile baslayanlar
        on_ek = os.path.splitext(ad)[0].lower() + "-"
        for ek in dict.fromkeys(MADDE.findall(sayfa)):
            if not ek.lower().startswith(on_ek) or ek.lower() in gorulen:
                continue
            gorulen.add(ek.lower())
            try:
                kaydet(taban, cikti, ek)
                ekler.append((ad, ek))
            except (urllib.error.URLError, OSError) as e:
                hatalar.append("%s (%s)" % (ek, e))


if __name__ == "__main__":
    main()
