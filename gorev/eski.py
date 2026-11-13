#!/usr/bin/env python3
"""Onceki bir Resmi Gazete sayisindaki metni getirir (eski-yeni karsilastirmasi icin).

Kullanim:
  python3 gorev/eski.py 20140219        o sayinin fihristini numarali olarak listeler
  python3 gorev/eski.py 20140219 6      listedeki 6 numarali metni indirir, yolunu yazar

Mukerrer sayilarda tarihin sonuna M1, M2 eklenir (ornek: 20201231M1).
Ciktinin ilk satiri: BULUNAMADI | AG_HATASI | FIHRIST <sayi> | HAZIR <dosya yolu>
Metnin ekleri varsa (ayri PDF olarak yayimlananlar) onlar da indirilir ve "EK <yol>" satirlariyla bildirilir.
Indirilen metinler calisma/eski/ klasorune yazilir; depoya gonderilmez.
"""
import html
import os
import re
import sys
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import indir as ortak  # noqa: E402  (ayni klasordeki indir.py: indirme ve metne cevirme)

SAYI = re.compile(r"^\d{8}(?:M\d+)?$")
DOSYA = re.compile(r"^\d{8}(?:M\d+)?-\d+(?:-\d+)?\.(?:htm|html|pdf)$", re.I)
BAGLANTI = re.compile(r'(?is)<a\s[^>]*?href\s*=\s*"([^"]+)"[^>]*>(.*?)</a>')


def maddeler(fihrist):
    """Fihristteki maddeleri (dosya adi, baslik) ciftleri olarak sirayla dondurur."""
    sonuc, gorulen = [], set()
    for m in BAGLANTI.finditer(fihrist):
        dosya = m.group(1).rsplit("/", 1)[-1]
        if not DOSYA.match(dosya) or dosya in gorulen:
            continue
        baslik = html.unescape(re.sub(r"(?s)<[^>]+>", "", m.group(2)))
        baslik = re.sub(r"\s+", " ", baslik).strip("  –—-")
        if not baslik:
            continue
        gorulen.add(dosya)
        sonuc.append((dosya, baslik))
    return sonuc


def main():
    # Basliklar Turkce karakter icerir; ortam ne olursa olsun UTF-8 yaz
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) not in (2, 3) or not SAYI.match(sys.argv[1]):
        sys.exit("Kullanim: eski.py yyyyMMdd[M1] [madde numarasi]")
    sayi = sys.argv[1]
    taban = "https://www.resmigazete.gov.tr/eskiler/%s/%s/" % (sayi[:4], sayi[4:6])

    try:
        fihrist = ortak.coz(ortak.indir(taban + sayi + ".htm"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print("BULUNAMADI", sayi)
            return
        print("AG_HATASI", "HTTP", e.code)
        sys.exit(2)
    except (urllib.error.URLError, OSError) as e:
        print("AG_HATASI", e)
        sys.exit(2)

    liste = maddeler(fihrist)
    if len(sys.argv) == 2:
        print("FIHRIST", sayi)
        for i, (dosya, baslik) in enumerate(liste, 1):
            print("%d. %s [%s]" % (i, baslik, dosya))
        if not liste:
            print("(madde baglantisi bulunamadi)")
        return

    secim = sys.argv[2]
    if not secim.isdigit() or not 1 <= int(secim) <= len(liste):
        sys.exit("Gecersiz madde numarasi: %s (1-%d arasi olmali)" % (secim, len(liste)))
    dosya, baslik = liste[int(secim) - 1]

    try:
        bayt = ortak.indir(taban + dosya)
    except (urllib.error.URLError, OSError) as e:
        print("AG_HATASI", e)
        sys.exit(2)

    klasor = os.path.join(ortak.KOK, "calisma", "eski")
    os.makedirs(klasor, exist_ok=True)
    ekler = []
    if dosya.lower().endswith(".pdf"):
        yol = os.path.join(klasor, dosya)
        with open(yol, "wb") as f:
            f.write(bayt)
        metin = ortak.pdf_metni(yol)  # buyuk PDF'ler icin duz metin kopyasi (cikarilabiliyorsa)
        if metin:
            ekler.append(metin)
        elif len(bayt) > ortak.BUYUK_PDF:
            ilk = ortak.pdf_ilk_sayfalar(yol)  # taranmis buyuk PDF: ilk sayfalar ayri dosyada
            if ilk:
                ekler.append(ilk)
    else:
        sayfa = ortak.coz(bayt)
        yol = os.path.join(klasor, os.path.splitext(dosya)[0] + ".txt")
        with open(yol, "w", encoding="utf-8") as f:
            f.write(ortak.metne_cevir(sayfa, taban))
        # Maddenin kendi sayfasinda baglantisi olan ekler (ornegin 20140219-6-1.pdf)
        on_ek = os.path.splitext(dosya)[0].lower() + "-"
        for ek in dict.fromkeys(ortak.MADDE.findall(sayfa)):
            if not ek.lower().startswith(on_ek):
                continue
            try:
                ortak.kaydet(taban, klasor, ek)
            except (urllib.error.URLError, OSError):
                continue
            ad = ek if ek.lower().endswith(".pdf") else os.path.splitext(ek)[0] + ".txt"
            ekler.append(os.path.join(klasor, ad))

    print("HAZIR", yol)
    print("BASLIK", baslik)
    print("BOYUT", round(os.path.getsize(yol) / 1024), "KB")
    for ek in ekler:
        print("EK", ek)


if __name__ == "__main__":
    main()
