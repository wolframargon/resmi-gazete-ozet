#!/usr/bin/env python3
"""Gunluk Resmi Gazete sayisini indirir ve ozetlenmeye hazir hale getirir.

Kullanim: python3 gorev/indir.py [yyyyMMdd]   (tarih verilmezse Turkiye saatine gore bugun)
          python3 gorev/indir.py --sonra yyyyMMdd   (telafiye o gunden sonraki gunlerden devam et)
Ciktinin ilk satiri: ZATEN_VAR | YAYINLANMADI | AG_HATASI | HAZIR <klasor>

HAZIR'dan sonraki satirlar:
  TARIH <yyyyMMdd>
  FIHRIST_ADRESI <adres>
  MUKERRER M1 fihrist-M1.txt <adres>      ayni gun cikan mukerrer sayi (varsa)
  DOSYA <ad> <boyut> KB                   klasordeki her dosya
  EK <ek dosyasi> <- <madde dosyasi> <adres>   bir maddenin sayfasindan bulunan ek
  INDIRILEMEDI <dosyalar>                 indirilemeyenler (varsa)
  GUNCELLE ozetler/<tarih>.html M<n>      ozet zaten var ama sonradan mukerrer sayi cikti:
                                          yeni ozet yazilmaz, mevcut ozet guncellenir
  KACIRILAN <tarih>                       son 3 gunden birinin ozeti hic yazilmamis; once o gun
                                          (eksik olan en eski gun) ozetlenir
  YENIDEN_CALISTIR python3 gorev/indir.py --sonra <tarih>   o gun yayinlandiktan sonra calistirilir;
                                          siradaki eksik gune ya da bugune gecer

Her PDF'in metni, cikarilabiliyorsa, yanina <ad>.pdf.txt olarak yazilir (buyuk PDF'ler icin).
Metni cikmayan (taranmis) ve 10 MB'tan buyuk PDF'lerin ilk 8 sayfasi <ad>-ilk8.pdf olarak
ayrica kaydedilir (pypdf, qpdf ya da mutool varsa).
"""
import datetime
import html
import os
import re
import shutil
import subprocess
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
    argumanlar = sys.argv[1:]
    sonra = None
    if len(argumanlar) == 2 and argumanlar[0] == "--sonra":
        sonra = argumanlar[1]
        argumanlar = []
        if not re.fullmatch(r"\d{8}", sonra):
            sys.exit("--sonra tarihi yyyyMMdd biciminde olmali")
    if argumanlar:
        tarih = argumanlar[0]
    else:
        turkiye = datetime.timezone(datetime.timedelta(hours=3))
        tarih = datetime.datetime.now(turkiye).strftime("%Y%m%d")
    if not re.fullmatch(r"\d{8}", tarih):
        sys.exit("Tarih yyyyMMdd biciminde olmali")

    # Tarih verilmeden calistirildiysa (gunluk rutin) once son 3 gune, en eskisinden baslayarak bakilir:
    # - bir gunun ozeti hic yazilmamissa (sayi rutinden sonra yayimlandi, rutin calismadi ya da
    #   kullanim siniri yuzunden basarisiz oldu...) ve sayi sitede yayindaysa once o gun ozetlenir;
    # - ozeti olan bir gunde ozet yayinlandiktan sonra mukerrer sayi ciktiysa once o gun guncellenir.
    # Ikisinde de ciktinin sonundaki YENIDEN_CALISTIR satiri, o gun yayinlandiktan sonra calistirilacak
    # komutu verir (--sonra <o gun>): sira bir sonraki eksik gune, eksik kalmadiysa bugune gecer.
    bugun = None
    kacirilan = False
    if not argumanlar:
        bulunan = telafi(tarih, sonra)
        if bulunan:
            bugun = tarih
            tarih, kacirilan = bulunan

    guncelle = 0
    if os.path.exists(os.path.join(KOK, "ozetler", tarih + ".html")):
        guncelle = yeni_mukerrer(tarih)
        if not guncelle:
            print("ZATEN_VAR", tarih)
            return

    taban = taban_adresi(tarih)
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
    if kacirilan:
        print("KACIRILAN", tarih)
    for n, adres in mukerrerler:
        print("MUKERRER", "M%d" % n, "fihrist-M%d.txt" % n, adres)
    for ad in sorted(os.listdir(cikti)):
        print("DOSYA", ad, round(os.path.getsize(os.path.join(cikti, ad)) / 1024), "KB")
    for madde, ek in ekler:
        print("EK", ek, "<-", madde, taban + ek)
    if hatalar:
        print("INDIRILEMEDI", ", ".join(hatalar))
    if guncelle:
        print("GUNCELLE", "ozetler/%s.html" % tarih, "M%d" % guncelle)
    if bugun:
        print("YENIDEN_CALISTIR", "python3 gorev/indir.py --sonra", tarih)


MUKERRER_SINIRI = 9
TELAFI_GUN = 3  # tarih verilmeden calistirildiginda kac gun geriye bakilir


def ilk_ozet():
    """Depodaki en eski ozetin tarihi (yyyyMMdd); hic ozet yoksa None."""
    klasor = os.path.join(KOK, "ozetler")
    if not os.path.isdir(klasor):
        return None
    tarihler = [ad[:8] for ad in os.listdir(klasor) if re.fullmatch(r"\d{8}\.html", ad)]
    return min(tarihler) if tarihler else None


def telafi(tarih, sonra=None):
    """Son TELAFI_GUN gune, en eskisinden baslayarak bakar; ilk islenecek gunu dondurur.

    Donus: (gun, True) ozeti hic yazilmamis ve sayisi sitede yayinda olan gun (KACIRILAN);
    (gun, False) ozeti var ama sonradan mukerrer sayi cikmis gun (GUNCELLE); yoksa None.
    [sonra] verilirse yalnizca ondan sonraki gunlere bakilir; boylece ayni oturumda telafi
    edilen gun yeniden secilmez ve dongu olusmaz. Depodaki ilk ozetten onceki gunler telafi
    edilmez (proje oncesi gunler kendiliginden ozetlenmesin).
    """
    ilk = ilk_ozet()
    if ilk is None:
        return None
    t = datetime.datetime.strptime(tarih, "%Y%m%d")
    for fark in range(TELAFI_GUN, 0, -1):  # 3, 2, 1: eksik olan en eski gunden baslanir
        gun = (t - datetime.timedelta(days=fark)).strftime("%Y%m%d")
        if gun < ilk or (sonra and gun <= sonra):
            continue
        if os.path.exists(os.path.join(KOK, "ozetler", gun + ".html")):
            if yeni_mukerrer(gun):
                return gun, False
        elif yayinda(gun):
            return gun, True
    return None
PDF_METIN_ALT_SINIRI = 200  # bundan kisa cikan metin, taranmis goruntu sayilir ve yazilmaz


def taban_adresi(tarih):
    return "https://www.resmigazete.gov.tr/eskiler/%s/%s/" % (tarih[:4], tarih[4:6])


def yayinda(tarih):
    """O gunun sayisi sitede yayindaysa True. Ag hatasi, yayinda degil sayilir."""
    try:
        indir("%s%s.htm" % (taban_adresi(tarih), tarih), deneme=2)
        return True
    except (urllib.error.URLError, OSError):
        return False


def yeni_mukerrer(tarih):
    """Ozeti yayinlanmis bir gun icin, ozette henuz yer almayan bir mukerrer sayi ciktiysa numarasini dondurur.

    Ozetteki "N. Mükerrer Sayı" ibarelerinin en buyugu islenmis sayilir; bir sonraki
    mukerrerin fihristi sitede varsa o numara dondurulur. Ozet yoksa ya da yeni mukerrer
    yoksa 0 doner. Ag hatasi, mukerrer yok sayilir.
    """
    yol = os.path.join(KOK, "ozetler", tarih + ".html")
    if not os.path.exists(yol):
        return 0
    with open(yol, encoding="utf-8") as f:
        ozet = f.read()
    islenen = max([int(n) for n in re.findall(r"(\d+)\.\s*Mükerrer", ozet)] or [0])
    sonraki = islenen + 1
    if sonraki > MUKERRER_SINIRI:
        return 0
    try:
        indir("%s%sM%d.htm" % (taban_adresi(tarih), tarih, sonraki), deneme=1)
    except (urllib.error.URLError, OSError):
        return 0
    return sonraki


def pdf_metni(yol):
    """PDF'in metnini <ad>.pdf.txt dosyasina cikarir; buyuk PDF'ler bu sayede okunabilir.

    Sistemde pdftotext komutu ya da pypdf modulu varsa kullanilir; ikisi de yoksa ya da PDF
    taranmis goruntuyse (metin cikmiyorsa) dosya yazilmaz. Yazilan dosyanin yolunu dondurur.
    """
    hedef = yol + ".txt"
    metin = ""
    komut = shutil.which("pdftotext")
    if komut:
        try:
            subprocess.run([komut, "-layout", "-enc", "UTF-8", yol, hedef], check=True, timeout=180,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            with open(hedef, encoding="utf-8", errors="replace") as f:
                metin = f.read()
        except (OSError, subprocess.SubprocessError):
            metin = ""
    if not metin.strip():
        try:
            from pypdf import PdfReader  # yoksa ImportError
            metin = "\n\n".join((sayfa.extract_text() or "") for sayfa in PdfReader(yol).pages)
        except Exception:  # modul yok ya da PDF okunamadi
            metin = ""
    if len(metin.strip()) < PDF_METIN_ALT_SINIRI:
        if os.path.exists(hedef):
            os.remove(hedef)
        return None
    with open(hedef, "w", encoding="utf-8") as f:
        f.write(metin)
    return hedef


BUYUK_PDF = 10 * 1024 * 1024  # bundan buyuk taranmis PDF'ler okuma aracina sigmayabilir
ILK_SAYFA = 8


def pdf_ilk_sayfalar(yol):
    """Buyuk, taranmis bir PDF'in ilk 8 sayfasini <ad>-ilk8.pdf olarak ayri kaydeder.

    Boylece model hic degilse ilk sayfalardaki tablolari Read araciyla okuyabilir. Sirayla
    pypdf modulu, qpdf ve mutool komutlari denenir; hicbiri yoksa ya da basarisizsa None doner.
    """
    hedef = os.path.splitext(yol)[0] + "-ilk%d.pdf" % ILK_SAYFA
    try:
        from pypdf import PdfReader, PdfWriter  # yoksa ImportError
        okuyucu = PdfReader(yol)
        yazici = PdfWriter()
        for sayfa in okuyucu.pages[:ILK_SAYFA]:
            yazici.add_page(sayfa)
        with open(hedef, "wb") as f:
            yazici.write(f)
        return hedef
    except Exception:  # modul yok ya da PDF okunamadi; komut satiri araclarina gec
        pass
    komutlar = []
    if shutil.which("qpdf"):
        komutlar.append([shutil.which("qpdf"), yol, "--pages", ".", "1-%d" % ILK_SAYFA, "--", hedef])
    if shutil.which("mutool"):
        komutlar.append([shutil.which("mutool"), "merge", "-o", hedef, yol, "1-%d" % ILK_SAYFA])
    for komut in komutlar:
        try:
            subprocess.run(komut, check=True, timeout=180, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.path.exists(hedef) and os.path.getsize(hedef) > 0:
                return hedef
        except (OSError, subprocess.SubprocessError):
            continue
    return None


def kaydet(taban, cikti, ad):
    """Tek bir dosyayi indirir: PDF oldugu gibi, HTML duz metne cevrilerek. HTML'in ham halini dondurur."""
    bayt = indir(taban + ad)
    if ad.lower().endswith(".pdf"):
        yol = os.path.join(cikti, ad)
        with open(yol, "wb") as f:
            f.write(bayt)
        # Metin katmani yoksa (taranmis goruntu) ve dosya buyukse ilk sayfalar ayrica kaydedilir
        if pdf_metni(yol) is None and len(bayt) > BUYUK_PDF:
            pdf_ilk_sayfalar(yol)
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
