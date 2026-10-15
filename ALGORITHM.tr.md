# Algoritma

[English](ALGORITHM.md)

Bu belge, resume-xray'ın bir CV'yi nasıl analiz ettiğini, hangi hesapları neden yaptığını ve
kullandığı her eşik ile ağırlığın gerekçesini anlatır. Koddaki tüm sabitler
`resume_xray/config/weights.toml` dosyasında bu belgedeki adlarıyla tutulur.

> **Durum:** Aşağıdaki değerler gerekçeli **başlangıç değerleridir**. Test setiyle
> kalibre edildikçe güncellenecek ve her değişiklik bu belgeye işlenecektir
> (bkz. [Kalibrasyon](#5-kalibrasyon)).

---

## 1. Ne ölçüyoruz, ne ölçmüyoruz?

Ticari ATS'lerde (Workday, Greenhouse, Taleo, Lever…) bir başvurunun gözden kaçmasının üç
gerçek nedeni vardır:

1. **Ayrıştırma hatası:** Belge metne çevrilirken bölümler kaybolur veya karışır.
2. **Aramada çıkmama:** İşe alımcı yetenek veya pozisyon adıyla arama yapar; CV'de o terim
   yoksa başvuru sonuçlarda görünmez.
3. **Eleme soruları:** Çalışma izni, deneyim yılı gibi formdaki sorular (CV metniyle ilgisi yoktur).
   Örneğin Oracle Taleo'da gerekli cevabı vermeyen aday başvuru sürecinden anında çıkarılabilir [1].

resume-xray **1. ve 2. maddeyi** ölçer. Ölçmediği şeyler:

- İşe alınıp alınmayacağınızı veya "ATS'nin vereceği puanı". Hiçbir ATS üreticisi böyle bir
  puan yayınlamaz; bunu taklit ettiğini söyleyen bir araç tahmin yürütüyordur.
- "CV'lerin %75'i ATS tarafından reddedilir" iddiası bir **mittir**. Kaynağı 2012'de kapanmış bir
  CV optimizasyon şirketinin (Preptel) satış sunumudur ve yöntemi hiç yayınlanmamıştır [2].

### Tek puan yok

Sonuç tek bir "%73 uyumlu" sayısı olarak verilmez. Birbiriyle ilgisiz bulguları (font hatası,
eksik yetenek, sütun düzeni) keyfi ağırlıklarla toplamak hem gerekçelendirilemez hem de kritik
hataları ortalamada gizler. Bunun yerine iki ayrı soru cevaplanır:

| Soru | Cevap biçimi | Kural |
|---|---|---|
| Belgem taranabiliyor mu? | `Uygun` / `Riskli` / `Okunamaz` | En kötü bulgu belirler |
| İlana göre aranabilir miyim? | Zorunlu ve tercih edilen terimler için ayrı kapsama oranı | Ağırlıklı kapsama (bölüm 3) |

### Gerçekçi, güzelleştirilmemiş

resume-xray, ATS okuyucularının gerçekte elde ettiği metni raporlar, temizlenmiş bir sürümünü
değil. Bir belge yalnızca bir ATS'nin kullanmayabileceği daha akıllı bir okuyucuyla doğru
okunabiliyorsa, sorun yine de raporlanır. ATS'lerin veya metin çıkarıcıların davranışına dair her
ifade [Kaynaklar](#kaynaklar) bölümünde bir kaynağa dayanır; kendi ölçümlerimize dayanan ifadeler
bunu açıkça belirtir.

### ATS'ler bir PDF'i nasıl okur?

Bir ticari ATS'nin hangi metin çıkarıcıyı kullandığı kamuya açık değildir; resume-xray bunu
biliyormuş gibi yapmaz. Bunun yerine yaygın kullanılan çıkarıcıların üç okuma stratejisini taklit
eder:

| Strateji | Ne yapar | Belgelenmiş örnekler | Taklit eden |
|---|---|---|---|
| **İçerik akışı sırası** | Metni PDF dosyasının içinde yazıldığı sırayla verir | Apache PDFBox ve Apache Tika varsayılanı (konuma göre sıralama varsayılan olarak kapalı [3], [4]); `pdftotext -raw` [5] | `pypdf` |
| **Konum sırası** | Metni yukarıdan aşağı, soldan sağa sıralar | `sortByPosition` açık PDFBox/Tika; belgelerine göre sütunları birbirine karıştırabilir [4] | `pdfplumber` düz metni |
| **Sütun farkındalıklı okuma** | Önce sütunları bulur, sonra sırayla okur | `pdftotext` varsayılanı, sütun gibi fiziksel düzeni "geri almaya" çalışır [5]; Textkernel, sütun ayraçlarını eğitilmiş bir modelle bulur [6] | Kendi satır ve kanal tespitimiz (2.0, 2.3) |

DOCX'te soru sıra değil, hangi bölümlerin okunduğudur. Word üst bilgiyi, alt bilgiyi ve metin
kutularını gövde paragraflarından ayrı saklar; bu yüzden resume-xray iki okumayı karşılaştırır:

| Strateji | Ne okur | Dayanak |
|---|---|---|
| **Belgenin tüm bölümleri** | Üst bilgi, gövde, tablolar, metin kutuları, alt bilgi | Tam çıkarıcıların döndürdüğü; ör. mammoth metin kutularını "kutuyu içeren paragraftan sonra gelen ayrı bir paragraf" olarak okur [8] |
| **Yalnızca gövde paragrafları** | Gövde paragrafları ve tablolar | `python-docx`'in `document.paragraphs` ve `document.tables` ile döndürdüğü (kendi gözlemimiz) |

Bazı stratejileri bozan sorun **uyarı** ("bazı ATS'ler"), tüm stratejileri bozan sorun **kritik**
olarak raporlanır. Her bulgu hangi stratejileri etkilediğini belirtir.

---

## 2. Taranabilirlik

Her kontrol bir **şiddet** üretir: `kritik`, `uyarı` veya `bilgi`. Ağırlık yoktur; eşikler vardır.

- Herhangi bir `kritik` bulgu → **Okunamaz**
- `kritik` yok, en az bir `uyarı` → **Riskli**
- Diğer durumlar → **Uygun**

### 2.0 Belgenin okunması (`row_overlap_min = 0.5`, `word_gap_ratio = 0.15`)

İki format da ortak bir ara biçime çevrilir: sayfası, font boyutu, kalınlığı ve bölgesi (gövde,
üst bilgi, alt bilgi, tablo, metin kutusu) bilinen metin satırları. PDF satırları ayrıca punto
cinsinden konumlarını ve ait oldukları görsel sırayı taşır. Her sayfa, kontrollerin
karşılaştırabilmesi için her okuma stratejisinin tam metnini de saklar.

**PDF kelimeleri.** `pdfplumber` her karakteri kutusu, fontu ve boyutuyla verir. Karakterler içerik
akışı sırasıyla kelimelere birleştirilir. Kelime şu durumlarda biter: boşluk karakteri, font boyutunun
%15'inden geniş yatay boşluk, metnin sola geri dönmesi veya sıradaki karakterin kelimeyle dikeyde küçük
yüksekliğin en az yarısı kadar örtüşmemesi (aşağıdaki sıra kuralıyla aynı örtüşme). Font ve boyut
değişimi kelimeyi asla bitirmez; yuvarlak madde işareti her zaman ayrı bir kelimedir. Karakterlerinin
çoğu adında Bold, Black, Heavy, Semibold veya Demi geçen bir fonttan gelen kelime kalın sayılır.

*Gerekçe:* 3 LaTeX, 1 Canva ve 1 başka gerçek CV'de ölçüldüğünde, bir kelimenin harfleri arasındaki
boşluk font boyutunun en fazla %8'i, boşluk karakteri olmayan kelimeler arasındaki boşluk (LaTeX
kelimeleri yalnızca mesafeyle ayırır) ise en az %20'sidir; %15 ikisinin arasındadır. *Gerçek CV'lerde
bulundu:* ilk sürüm `pdfplumber`'ın varsayılanı olan sabit 3 punto kullanıyordu; bu, 9 puntoluk LaTeX
metninin kelimelerini birleştiriyordu ("CaptainoftheBlackPearl"; aralık 2.2 punto). *Gerçek ve üretilmiş CV'lerde bulundu:* başka bir
fonttan alınan harf başka bir yükseklikte durur. Bir CV'de "TÜBİTAK"ın İ harfi ayrı bir font alt
kümesinden geliyordu; Chrome ile basılmış Türkçe bir CV'de "Yılmaz"ın "ı" harfi Helvetica'ya düşmüş ve
kelimesinden 5 punto aşağıda duruyordu. Kelimeleri font değişiminde veya üst kenara göre bölmek iki
kelimeyi de bozuyordu ("TÜB İ TAK", "Y ı lmaz").

**PDF sıraları ve satırları.** Bir kelimenin dikey alanı, sıranın dikey alanıyla ikisinin küçük
yüksekliğinin en az yarısı kadar örtüşüyorsa kelime o sıraya katılır:

```
örtüşme(kelime, sıra) / min(yükseklik(kelime), yükseklik(sıra)) ≥ 0.5
```

Sıra, iki kelime arasındaki boşluğun `gutter_min_width_pt` değerinden (bkz. 2.3) geniş olduğu
yerlerden ayrı satırlara bölünür; böylece iki sütunlu bir sayfanın sol ve sağ sütunu tek satırda
birleşmez.

*Gerekçe:* Aynı satırdaki kelimeler, boyutları farklı olsa bile yüksekliklerinin çoğunu paylaşır:
madde işareti gibi küçük bir karakter tamamen satırın içinde kalır (oran 1.0). Ardışık satırlar ise
neredeyse hiç örtüşmez, çünkü satır aralığı normalde en az font boyutu kadardır (oran 0'a yakın,
çok sık aralıkta en fazla yaklaşık 0.2). 0.5 ikisinin arasında güvenli bir değerdir.

Satır içinde kelimeler soldan sağa sıralanır; aynı x konumunda başlayan kelimelerde dar olan önce
gelir.

*Gerçek bir CV'de bulundu:* Önceki sürüm, üst kenarları 3 puntodan yakın kelimeleri grupluyordu.
Bir CV'de görünen madde işaretleri çizilmiş şekillerdi; her maddenin ilk harfinin üzerinde, metnin
taban çizgisinde ve satırın üstünden 6.7 punto aşağıda görünmez 0.75 puntoluk bir metin madde
işareti duruyordu. Üst kenar gruplaması bu işareti satırın sonuna taşıyordu ("Managed •"); örtüşme
gruplaması ve "dar olan önce" kuralı onu tekrar başa aldı.

Bir PDF sayfasının üç okuması:

- **İçerik akışı sırası:** `pypdf`'in `extract_text()` çıktısı.
- **Konum sırası:** `pdfplumber`'ın `extract_text()` çıktısı, bizim kelimelerimizle aynı kelime aralığı
  kuralıyla (`x_tolerance_ratio`); böylece bu okuma bizimkinden yalnızca sırada ayrılır, temsil ettiği
  okuyucuların (PDFBox, Tika) paylaşmadığı bir `pdfplumber` boşluk tuhaflığında değil.
- **Sütun farkındalıklı sıra:** bizim satırlarımız. Kanal (2.3) yoksa sıralar yukarıdan aşağı
  okunur. Kanal varsa her satır ya soldadır (sağ sütun başlamadan biter), ya sağdadır (sol sütun
  bittikten sonra başlar) ya da iki sütuna yayılır. Yayılan satırlar sayfayı bloklara böler; bir
  blokta iki tarafta da en az iki sıra varsa önce sol, sonra sağ sütun okunur, yoksa blok sıra sıra
  okunur (böylece iki tarafta öğesi olan bir iletişim satırı bir arada kalır). Satırlar bu sırada
  saklanır; böylece bir bölüm başlığı yalnızca kendi sütunundaki satırları toplar.

**DOCX.** `python-docx` paragrafları gövdedeki sırasıyla, tabloları ve her bölümün üst/alt
bilgisini verir. Metin kutuları ham XML'den (`w:txbxContent`) okunur, çünkü `python-docx` bunları
sunmaz; Word her kutuyu iki kez saklar (DrawingML ve VML yedeği) ve yalnızca biri okunur. Font
boyutu ve kalınlık metin parçalarından (run), yoksa paragraf stilinden alınır. Her iki formatta da
bağlantı (hyperlink) hedefleri 2.7 için toplanır.

### 2.1 Metin katmanı (`min_chars_per_page = 50`, `scan_image_coverage = 0.5`, `outline_min_curves = 200`)

Bir PDF sayfası 50'den az boşluk olmayan karakter içeriyor **ve** içeriği bir resimse **metin
katmanı yoktur**: sayfanın en az yarısını kaplayan bir görsel ya da en az 200 vektör eğrisi (şekle
dönüştürülmüş metin) → **kritik** (tüm stratejileri bozar; yalnızca OCR çalıştıran bir ATS okuyabilir
[4]). Toplamda 50'den az karakter içeren bir DOCX de aynı şekilde değerlendirilir.

*Gerekçe:* Tipik bir CV sayfası 1.500–3.000 karakter içerir (kendi gözlemimiz). 50'nin altı,
yalnızca sayfa numarası gibi kırıntıların çıkarılabildiği anlamına gelir. Resim şartı testten sonra
eklendi: ikinci sayfasında yalnızca Diller bölümü (39 karakter) olan iki sayfalık bir CV taranmış
sanılıyordu. Taranmış sayfa, bütün sayfayı kaplayan tek bir görseldir (test setinde kaplama 1.0).
Şekle dönüştürülmüş metin her harf için en az bir eğri çizer, yani böyle bir sayfada binden fazla eğri
olur; test setindeki süslemeler en fazla 18 eğri çizdi. 200 ikisinin arasındadır, ancak henüz şekle
dönüştürülmüş bir CV ölçülmedi.

### 2.2 Bozuk karakterler (`garbled_warn = 0.02`, `garbled_critical = 0.10`)

```
g = bozuk_karakter_sayısı / toplam_karakter_sayısı
```

Sütun farkındalıklı okumada bozuk sayılanlar: `(cid:NN)` kalıpları (karakter eşlemesi olmayan
fontlar), `U+FFFD` (�) ve Unicode özel kullanım alanı `U+E000–F8FF` (ikon fontları).

- `g > 0.02` → **uyarı**, `g > 0.10` → **kritik**

*Gerekçe:* %2'ye kadarı ikon ve madde işaretlerinden gelebilir ve okunabilirliği bozmaz. %10'un
üstünde kelimeler okunamaz hale gelir.

### 2.3 Çok sütunlu düzen (`gutter_min_width_pt = 8`, `gutter_min_height = 0.5`, `gutter_x_range = [0.2, 0.8]`)

**Kanal**, iki sütun arasındaki boş dikey şerittir:

1. Sayfa genişliğinin %20–%80 aralığı 1 puntoluk dilimlerle taranır. Kanal, en az 8 punto genişliğinde
   ve hiçbir satırın kesmediği, sayfanın metin yüksekliğinin en az %50'si kadar ortak bir dikey
   aralığı paylaşan ardışık dilimlerdir.
2. Her iki yanda da **akan metin** varsa kanal iki sütunu ayırır: bir paragraf gibi alt alta duran,
   her biri bir öncekinin altına kendi yüksekliğinden daha yakın başlayan en az üç satır. Kanalı
   aşıp öbür sütuna uzanmayan satır o taraftadır; boş aralığın üstünde veya altında kalan satırlar da
   sayılır (kenar çubuğundaki isim, sütunun ilk başlığı).
3. Bu tür kanalların en genişi sütun aralığıdır.

Kanalı olan bir sayfada bir okuma, kelime sırası sütun farkındalıklı okumadan farklıysa (2.4'teki
gibi) ya da aynı sıradaki sol ve sağ sütunun metnini tek bir çıktı satırında yan yana birleştiriyorsa
**sütunları karıştırır**. Bulgu, sütunları karıştıran stratejileri belirten bir **uyarı**, hiçbiri
karıştırmıyorsa **bilgi** olur.

*Gerekçe:* Test setinde ölçülen sütun aralıkları 14 ile 53 punto arasındadır (en darı, düzen için
kullanılan bir Word tablosu); kelime arası boşluk ise 3–5 puntodur; 8 punto ikisini ayırır. Tüm
satırların bir payı yerine boş bir dikey aralık aramak, sütunların üstünde tam genişlikte bir başlık
bloğuna (isim, iletişim, özet) izin verir. Akan metin şartı, bir sütunu tek sütunlu sayfadaki sağa yaslı
tarihlerden ("Jan 2021 – Present") ayırır; tarihler, başlık oldukları madde işaretlerinin arasına
dağılmış tek satırlardır. Sütunlar yalnızca
onları karıştıran okuyucular için sorundur; Tika, konuma göre sıralamanın "sütunları birbirine
karıştırabileceğini" belgeler [4]. Textkernel, CV'lerin en az %15'inin sütun kullandığını tahmin eder
ve görsel boşlukları bulan eski kural tabanlı yöntemini anlatır; bu yöntem ona benzer [6].

*Test sırasında bulundu:* ilk sürüm, kanalı kesen satırların tüm satırların en fazla %5'i olmasını ve
her iki yanın metin yüksekliğinin %50'sini kaplamasını istiyordu. Word'ün iki sütun ve tablo
düzenlerini kaçırıyordu (başlık kanalı kesiyordu; sağ sütun kısaydı), gevşetildiğinde de sağa yaslı
tarihleri sütun sanıyordu. Bir sola yaslılık testi bunu düzeltti, ama gerçek bir CV'nin kenar çubuğu
sağa yaslıydı ve sütunları kaçırıldı (kör doğrulama seti); akan metin testi ikisini de karşılar.
Dar bir sağ sütunda (her satırda bir yetenek), konum sırası her yeteneği
bir deneyim satırının sonuna yapıştırdı ama kelime sırasının %85'ini korudu; yan yana birleşme testi
bu durumu yakalar.

### 2.4 Okuma sırası ve kaybolan kelimeler (`agreement_order_max = 0.85`)

Her sayfada, basit okumaların (içerik akışı, konum) kelime dizisi sütun farkındalıklı okumayla
karşılaştırılır:

```
sıra_benzerliği = 1 − Indel mesafesi(A, B) / (|A| + |B|)
```

Bu, aynı göreli sırada görünen kelimelerin payıdır (2 × en uzun ortak alt dizi / toplam uzunluk) ve
`rapidfuzz` ile hesaplanır. Kanalı olmayan bir sayfada `sıra_benzerliği < 0.85` ise → **uyarı**:
okuyucu metni sayfada göründüğünden farklı bir sırada veriyor.

Ayrıca sütun farkındalıklı okumadaki her kelimeden basit bir okumada bulunmayanlar listelenir →
**uyarı**: o kelimeyle arama yapan işe alımcı, bu tür ATS'lerde CV'yi bulamaz. Kelimeler katlama
(bkz. 2.6) sonrası karşılaştırılır; yalnızca gerçek bölünmeler sayılır.

*Gerekçe:* Şimdiye kadar ölçülen iki gerçek CV'de sayfa sırasını koruyan okumalar 0.95–1.00,
iki sütunlu sayfayı karıştıran okumalar 0.61–0.71 aldı (kendi gözlemimiz, bkz. Kalibrasyon). 0.85
ikisini her iki tarafta da pay bırakarak ayırır. *Gerçek bir CV'de bulundu:* içerik akışı okuması
"İstanbul"u "İ stanbul", "TÜBİTAK"ı "TÜB İ TAK" olarak böldü, çünkü İ harfi ayrı bir font alt
kümesinden geliyordu.

### 2.5 Gövde dışındaki içerik (DOCX)

- E-posta veya telefon **yalnızca** üst veya alt bilgide → "yalnızca gövde paragrafları" için
  **uyarı**.
- Metin kutularında herhangi bir metin → "yalnızca gövde paragrafları" için **uyarı**.

PDF'te ayrı bir üst bilgi yoktur: sayfanın üstü diğer metinler gibi çıkarılır; bu yüzden PDF için
bulgu üretilmez.

*Gerekçe:* Üst bilgi, alt bilgi ve metin kutuları DOCX dosyasının ayrı parçalarıdır ve yalnızca
gövde paragraflarını alan okuyucular bunları hiç görmez (bkz. bölüm 1'deki DOCX stratejileri).

### 2.6 Bölüm başlıkları (`heading_max_words = 4`, `heading_size_ratio = 1.15`, `heading_match_min = 85`)

Bir satır şu koşulları sağlıyorsa **başlık adayıdır**: en fazla 4 kelime, madde işaretiyle
başlamıyor ve şunlardan en az biri: font boyutu ≥ 1.15 × medyan kelime boyutu, kalın, tamamı büyük
harf veya bir Word başlık stili.

Adaylar, standart İngilizce ve Türkçe başlıklardan oluşan bir sözlükle
(`resume_xray/data/headings.toml`) **katlama** sonrası `rapidfuzz.fuzz.ratio ≥ 85` ile
karşılaştırılır. Katlama: küçük harf, `İ`/`I`/`ı` → `i`, diğer Türkçe harfler ASCII'ye (`ş` → `s`,
...), noktalama kaldırılır. Katlama sayesinde "EXPERIENCE", "Experience", "DENEYİM" ve "Deneyim",
hangi dile göre küçük harfe çevrildiklerinden bağımsız olarak eşleşir. Bir aday, bir bölümün
yazımlarından birini bütün kelimeler olarak içeriyorsa da o bölümle eşleşir ("Relevant Work Experience"
"Work Experience"ı, "Additional Skills" "Skills"i içerir); içerilen en uzun yazım kazanır.

- Temel bir bölüm (deneyim, eğitim, yetenekler) tanınmadı → **uyarı**.
- Sözlükte olmayan, en az iki harf içeren, ilk tanınan başlıktan sonra gelen ve tanınan başlıklar
  gibi biçimlendirilmiş aday → **uyarı** ve en yakın standart başlık önerisi. "Gibi biçimlendirilmiş",
  tanınan başlıkların çoğunun paylaştığı biçimle aynı kalınlık ve büyük harf, ve ona
  `heading_size_ratio` içinde bir boyut demektir. Bu, ismin ve kalın iş unvanlarının başlık
  sanılmasını önler; 12 puntoluk başlıklar arasındaki 13 puntoluk bir başlık ise yine sayılır.
- Bir okumada kendi satırında olmayan tanınmış başlık → o stratejileri belirten **uyarı**: başlık
  satırı arayan bir ayrıştırıcı onu görmez.

*Gerçek CV'lerde bulundu:* birebir aynı boyut şartı, 12 puntoluk başlıklar arasındaki 13 puntoluk
"Positions of responsibility"yi kaçırıyordu; her tanınan başlığın biçimini almak ise kenar çubuğundaki
9 puntoluk tek bir başlık yüzünden 10 puntoluk kalın üniversite adlarını başlık gibi gösteriyordu.
Sözlükte artık tekil biçimler (Skill, Yetenek, Beceri) ile Türkçe "Sertifikasyon" ve "Dersler" de var.

*Gerekçe:* Ayrıştırıcılar bölümleri başlık sözlükleriyle sınıflandırır. 85 eşiği yazım farklarını
("Experiences", "Language") yakalarken alakasız kelimeleri dışarıda bırakır. *Gerçek CV'lerde bulundu:*
fazladan kelimeli başlıklar ("Relevant Work Experience" 77, "Additional Skills" 67, "Profile Summary"
80) 85'in altında kalıyor ve bölümleri eksik bildiriliyordu; bütün kelime kuralı bunları tanır.
"Eğitimler" kurslar altındaydı, ama Türkçe CV'ler onu eğitim için kullanıyor. Eksik bölüm kritik
değil uyarıdır: CV'nin geri kalanı yine okunur.

### 2.7 İletişim bilgileri ve tarihler (`phone_min_digits = 10`, `phone_max_digits = 15`)

Düzenli ifadelerle e-posta adresi, telefon numarası (boşluk, nokta, tire, parantez veya başta `+`
içerebilen, 10 ile 15 arası rakamlı dizi) ve LinkedIn adresi aranır.

- Hiçbir okumada e-posta adresi yok → **kritik**.
- LinkedIn adresi metin olarak değil yalnızca bağlantı hedefi olarak var → **bilgi**: metin
  çıkarma görünen metni döndürür, bağlantı hedeflerini değil.
- Mevsim veya çeyrekle yazılmış tarih ("Summer 2021", "Yaz 2021", "Q3 2021") → **uyarı**: aya
  çevrilemez.

*Gerekçe:* 10 rakam, Türkiye'de ve Kuzey Amerika'da ulusal numaranın uzunluğudur; 15, ITU-T E.164'e
göre uluslararası bir numaranın en fazla uzunluğudur [9].

### 2.8 Yanlış yere düşen madde işaretleri (`bullet_size_ratio = 0.5`)

Her basit okumada, tek başına bir satırda duran veya satır başında olmayan yuvarlak madde
işaretleri (`•`, `●`, `▪`, `■`, `◦`, `►`) sayılır. Herhangi bir okumada yanlış yere düşen madde
işareti varsa → o okumaları ve her birinin kaç madde işaretini kaydırdığını belirten **uyarı**.
Sütun farkındalıklı okumada madde işaretleri satırlarının geri kalanının medyan boyutunun 0.5
katından küçükse, bulgu madde işaretlerinin metinden ayrı çizilmiş çok küçük karakterler olduğunu
açıklar.

*Gerekçe:* Bazı CV oluşturucular (genellikle HTML'den PDF'e dönüştürenler) görünen madde işaretini
şekil olarak çizer ve kopyala-yapıştır için küçük bir metin madde işareti ekler. Konum sırası
okuyucuları bu durumda madde işaretini maddenin ilk satırından sonra ayrı bir satıra koyar; bir
sonraki madde, öncekinin ortasında başlıyormuş gibi görünür. İçerik akışı okuyucuları aynı dosyayı
doğru okur; yani sonuç ATS'nin kullandığı okuyucuya bağlıdır. Normal biçimlendirilmiş madde
işaretleri metin boyutunun %50–100'ü kadardır (kendi gözlemimiz); bu kontrolü doğuran vakada oran
%7.5 idi (10 puntoluk metnin yanında 0.75 punto).

---

## 3. İlan kapsaması

İşe alımcılar ATS'de adayları CV metni üzerinde anahtar kelime ve Boolean aramalarıyla bulur.
Örneğin Greenhouse, tam metin "CV'lerde anahtar kelime arama" özelliğini [10] ve "çoğulları veya
farklı kelime biçimlerini" bulmak için açıkça `*` joker karakteri gereken Boolean sorgularını [11]
belgeler; iki sayfa da eş anlamlı genişletmeden söz etmez. Bu yüzden ilan eşleştirmesi şunu sorar:
**ilanın kendi kelimeleriyle yapılan bir arama bu CV'yi bulur mu?** Bazı ATS'ler kelimeleri kök
haline getirebilir veya eş anlamlıları genişletebilir; incelediğimiz sistemlerde bu belgelenmediği
için bu tür eşleşmeler tam puan yerine kısmi puan ve açıklama alır.

### 3.1 Normalleştirme

1. Her metnin (CV, ilan) **dili**, yaygın İngilizce ve Türkçe bağlaç/edatlar sayılarak bulunur.
2. **Kesme işaretinden sonraki ekler** atılır: "Python'da" → "Python" (Türkçe, özel isimlere ekleri
   kesme işaretiyle bağlar).
3. **Küçük harf:** `İ → i` her dilde; `I → ı` yalnızca Türkçe metinde. Python'un düz
   `str.lower()` fonksiyonu Türkçede ikisini de yanlış yapar.
4. **Kelimeler** içlerindeki `+`, `#`, `.` ve `&` karakterlerini korur; böylece `C++`, `C#`, `.NET`,
   `Node.js` ve `R&D` bütün kalır (`R&D`, R dili sanılmaz).
5. Her kelimenin, ikisi de ASCII'ye katlanmış (`ş → s`, `ı → i`, ...) iki anahtarı vardır:
   - **yüzey:** kelimenin yazıldığı hali, küçük harfle;
   - **kök:** metnin dilinde (İngilizce veya Türkçe) Snowball kökü: "managed" ve "management"
     aynı köke ("manag") sahiptir.

### 3.2 İlanın terimleri

**Bölümler.** `resume_xray/data/job_sections.toml` içindeki bilinen bir başlıkla eşleşen
(`rapidfuzz.fuzz.ratio ≥ heading_match_min`) kısa bir satır (en fazla `heading_max_words` kelime)
yeni bir bölüm başlatır:

| Bölüm türü | Örnekler | Etkisi |
|---|---|---|
| Zorunlu | Requirements, Responsibilities, Aranan Nitelikler, Sorumluluklar | Terimler zorunludur |
| Tercihli | Nice to have, Preferred, Tercih Sebepleri | Terimler tercihlidir |
| Yok sayılan | About Us, Benefits, Hakkımızda, Yan Haklar | Satırlar atlanır |
| (henüz yok) | İlk başlıktan önceki metin | Zorunlu sayılır |

Tercih ifadesi ("is a plus", "preferred", "tercih sebebidir", ...) içeren bir satırdaki terimler,
hangi bölümde olursa olsun tercihli sayılır.

**Pozisyon adı** (`title_max_words = 8`): ilanın ilk satırı, herhangi bir bölüm başlığından önce
geliyor ve en fazla 8 kelimeyse. Aksi halde ilanın bir başlık satırı yoktur (birçoğu "About the
Role" ve bir cümleyle başlar); kullanıcı pozisyon adını `--title` ile verebilir.

*Gerekçe:* Pozisyon adları kısadır ("Senior Backend Developer", "Kıdemli Proje Yöneticisi"); daha
uzun bir ilk satır başlık değil cümledir.

**Terimler.**

- **Yetenek sözlüğü** (`resume_xray/data/skills.toml`): her yetenek, aynı anlama gelen tüm
  yazımlarını listeler (`Kubernetes`, `K8s`). İlan **kök** ile, en uzun yazımlar önce ve örtüşmeden
  taranır; böylece "React Native" ayrıca "React" sayılmaz. İlanın kullandığı yazım saklanır. Bir
  veya iki karakterli yazımlar (`R`, `C`, `Go`, `UI`) büyük/küçük harf olarak da eşleşmelidir.
- **Sözlükte olmayan teknik görünümlü kelimeler:** harfle birlikte rakam, `+` veya `#` içeren,
  CamelCase yazılan (`PostgreSQL`, `ISO27001`, `iOS`) ya da en az iki büyük harften oluşan
  kısaltmalar (`ARPU`, `LTV`, `AI`).

**Kullanıcı terimleri.** Hiçbir sözlük her alanı kapsamaz; bu yüzden hangi terimlerin sayılacağına
son olarak kullanıcı karar verir:

- **Ekle** (`--add`): eklenen her terim **zorunludur**. Yetenek sözlüğündeki bir yazımsa o
  yeteneğin eş anlamlılarını da getirir; değilse yazıldığı gibi eşleştirilir. `f_t` değeri,
  ilanda geçme sayısıdır (en az 1).
- **Çıkar** (`--remove`): adı veya ilandaki yazımı çıkarılan terimle aynı olan terimler atılır.
- **Yalnızca benim terimlerim** (`--skills`): ilan yoktur; kapsama verilen terimler üzerinden
  hesaplanır.

*Gerçek bir ilanda bulundu:* bir ürün yöneticisi ilanından 9 terim çıktı; "product strategy",
"monetization", "experimentation" ve "stakeholders" sözlükte yoktu.

**Öneriler** (`suggestion_limit = 12`). Sözlükte olmayan ve teknik görünmeyen kelimeler sayılmaz,
ama bunlardan en fazla 12'si, CV'de geçip geçmedikleriyle birlikte "bunlar da anahtar kelime
olabilir" olarak gösterilir. Birine tıklamak onu kullanıcı terimi olarak ekler. Öneriler kapsamayı
asla etkilemez. Bir kelime şu koşullarda önerilir: en az üç harfli, satırını açan kelime değil (ilan
satırları fiille açılır: "Define", "Collaborate"), tireli bir birleşik kelimenin parçası değil
("cross-functional") ve bir terimin, pozisyon adının, çıkarılmış bir terimin ya da yaygın ilan
kelimeleri listesinin (`resume_xray/data/generic_words.toml`) parçası değil. İki kelimelik bir ifade,
iki kelimesi de uygunsa, aralarında bir şey yoksa ve iki kez geçiyorsa ya da iki kelimesi de büyük
harfle başlıyorsa önerilir ("Looker Studio"). Sıralama: önce zorunlu, sonra tercihli; sonra sıklık;
sonra büyük harfle başlayanlar; sonra uzun olanlar.

*Gerekçe:* İlandaki her kelimeyi anahtar kelime saymak, gerçek bir ürün yöneticisi ilanı ve bakımcının
CV'siyle ölçüldü: 100 içerik kelimesi, 63'ü eksik bildirildi ve bunların kabaca dörtte üçü dolgu
kelimeydi ("ability", "fast", "looking"); "across" ve "including" gibi eşleşmeler de kapsamayı %37'ye
şişirdi. Bunları saymak, ilanın cümlelerini CV'ye kopyalamayı ödüllendirirdi. Öneri olarak göstermek,
o yöntemin bulduklarını ("experimentation", "monetization", "Looker Studio") korurken dolgu
kelimelerin puana girmesini önler. 12 bir gösterim tercihidir.

**Tek kelimelik kökler** (`word_form_max_extra = 2`): tek kelimelik bir yazım, kelimenin başka bir
biçimiyle ancak uzunlukları en fazla 2 harf farklıysa eşleşir. Bu kural ilan ve CV için aynıdır.

*Gerekçe:* Çoğul ve kısa çekimli biçimler bir iki harf farklıdır ("roadmap" / "roadmaps",
"Liderlik" / "Liderliği"); ama kök bulma alakasız kelimeleri de birleştirir: Snowball hem "Excel"
hem "Excellent" kelimesini "excel" köküne indirir. *Gerçek bir ilanda bulundu:* "Excellent
communication skills", Excel gereksinimi sanılmıştı.

### 3.3 Terim ağırlığı (`required_weight = 1.0`, `preferred_weight = 0.5`)

```
w_t = r_t × (1 + ln(1 + f_t))
```

**`r_t` — gereklilik katsayısı:** zorunlu terimler için `1.0`, tercihli olanlar için `0.5`. Bir
yerde zorunlu, başka yerde tercihli geçen terim zorunlu sayılır.

*Gerekçe:* İlanı yazanın kendi zorunlu/tercihli ayrımına güvenilir. 0.5, "tercih edilen bir
terim, zorunlu bir terimin yarısı kadar önemlidir" varsayımının en sade halidir. Bilinen bir
bölümün dışındaki metin, eksikliği gözden kaçırmamak için zorunlu sayılır; şirket ve yan haklar
bölümleri atlanır, çünkü oradaki araçlar ("Slack kullanıyoruz") gereklilik değildir.

**`f_t` — terimin sayılan satırlarda geçme sayısı.**

*Gerekçe:* Bir terim ne kadar sık geçiyorsa o kadar önemlidir, ancak etkisi logaritmayla
**doyurulur**: 1 kez geçen terim ×1.69, 5 kez geçen ×2.79 ağırlık alır (5 kat değil). Bu, BM25'teki
terim sıklığı doygunluğuyla aynı fikirdir ve 10 kez tekrarlanan tek bir kelimenin diğer tüm
terimleri ezmesini önler.

### 3.4 Eşleşme seviyesi (`word_form_match = 0.5`, `synonym_match = 0.5`)

CV, sütun farkındalıklı (PDF) veya tüm bölümler (DOCX) okumasında aranır:

| Durum | `m_t` | Gerekçe |
|---|---|---|
| **Tam:** ilanın yazımlarından biri, aynı yüzey anahtarı | 1.0 | İlanın kelimesiyle yapılan arama bulur |
| **Kelime biçimi:** aynı kök, farklı biçim ("roadmaps" / "roadmap") | 0.5 | Yalnızca joker karakterli aramayla bulunur [11]; kullanıcıya ilanın hangi biçimi kullandığı söylenir |
| **Eş anlamlı:** aynı yeteneğin başka yazımı ("Kubernetes" / "K8s") | 0.5 | Anlam aynı, ama eş anlamlı genişletme belgelenmemiş [10, 11]; kullanıcıya ilanın yazımını eklemesi söylenir |
| Yok | 0 | — |

### 3.5 Kapsama

```
Kapsama = Σ (w_t × m_t) / Σ w_t
```

Zorunlu ve tercihli terimler için **ayrı ayrı** hesaplanır ve gösterilir. Genel bir puan oluşturulmaz.

Bulunan her terim için rapor ayrıca şunları gösterir:

- CV'nin kendi bölüm başlıklarına göre **nerede** geçtiği (deneyim maddesi mi, yalnızca yetenek
  listesi mi). Bu, kapsamayı **etkilemez**: arama iki yerde de bulur; bağlam içinde geçmesi insan
  okuyucu için önemlidir.
- Varsa **hangi okumalarda kaybolduğu**: sütun farkındalıklı okumada bulunup örneğin içerik akışı
  okumasında bulunmayan bir terim (bir harf ayrıldığı için, bkz. 2.4), o şekilde okuyan bir ATS'de
  bulunamaz.

### 3.6 Ayrı kontroller (kapsamaya karışmaz)

| Kontrol | Yöntem | Neden ayrı |
|---|---|---|
| Pozisyon adı | Bir CV satırı pozisyon adını birebir ifade olarak içeriyorsa bulunmuş sayılır (tam terimlerle aynı anahtarlar), tırnaklı bir ifade araması gibi [11]. *Test sırasında bulundu:* bulanık karşılaştırma "Project Manager"ı "Product Manager" sanmıştı (%87 benzer); işe alımcının araması bulmazdı | İşe alımcıların en çok aradığı alan |
| Deneyim yılı | İlanın sayılan satırlarındaki en büyük "N+ years" / "N yıl". CV'de deneyim bölümündeki tarih aralıkları (`MM/YYYY`, `Jan 2021`, `Oca 2021`, `2021`, "Present" / "Günümüz" = bugün), çakışan dönemler bir kez sayılacak şekilde birleştirilir. Ayı olmayan bir yıl ocakta başlar, aralıkta biter | Eleme kriteridir, kapsamayla karıştırılmamalı |
| Diploma | Lisans < Yüksek lisans < Doktora seviyeleri İngilizce ve Türkçe tanınır ("lisans", "yüksek lisans", "doktora", "BSc", "MSc"). İlanın şartı andığı **en düşük** seviyedir ("Bachelor's or Master's" → Lisans); CV'ninki eğitim bölümündeki **en yüksek** seviyedir | Eleme kriteridir |

---

## 4. Neden TF-IDF, embedding veya LLM yok?

| Yöntem | Neden kullanılmıyor |
|---|---|
| TF-IDF + cosine | IDF anlamlı olmak için çok sayıda belge ister; elimizde 2 belge var. Sonuç "neden?" sorusuna cevap vermez |
| Embedding (sentence-transformers vb.) | Kara kutu; belgelenmiş isim/cinsiyet önyargısı var [7]; ~1 GB model indirmesi gerekir. ATS araması anlamsal değil, kelime bazlıdır |
| LLM | Deterministik değil (aynı CV'ye farklı sonuç), CV'nin dışarı gönderilmesi gizlilik riski taşır |

İleride embedding, yalnızca "şu terim de yakın olabilir" önerisi üreten, **varsayılan olarak
kapalı** bir seçenek olarak eklenebilir; kapsama hesabına girmez.

---

## 5. Kalibrasyon

Eşikler `tests/fixtures/` altındaki etiketli test CV'leriyle doğrulanır. Hedef set (~30 belge):

- tek sütunlu, iki sütunlu, tablolu PDF
- Canva / tasarım aracı çıktıları, ikon fontlu belgeler
- taranmış (görüntü) PDF
- metin kutulu, üst bilgide iletişimli DOCX
- Türkçe ve İngilizce CV'ler

Her belge için beklenen bulgular elle etiketlenir. Bir eşik değiştirildiğinde test seti yeniden
çalıştırılır ve sonuç bu belgeye işlenir.

| Sürüm | Değişiklik | Test sonucu |
|---|---|---|
| 0.1 | Başlangıç değerleri | — (test seti henüz yok) |
| 0.1 | `agreement_order_max` 0.7 → 0.85; okuma sırası sütun farkındalıklı okumayla karşılaştırılıyor | İki gerçek CV (biri tek, biri iki sütunlu): sırayı koruyan okumalar 0.945–1.000, karıştıran okumalar 0.608–0.707 |
| 0.1 | 23 CV'lik sentetik test seti (`tests/fixtures/synthetic/`, Chrome ve Word ile üretildi). Kelimeler karakterlerden kuruluyor (`word_gap_pt` 3); taranmış sayfa için resim şartı (`scan_image_coverage` 0.5, `outline_min_curves` 200); kanal, sola yaslı metnin yanındaki boş şerit olarak yeniden tanımlandı, `gutter_min_width_pt` 15 → 8, `gutter_max_coverage` kaldırıldı | 23'ünün hepsi etiketleriyle uyumlu. Kanal iki sütunlu 6 PDF'in hepsinde (14–53 pt) bulundu, tek sütunluların hiçbirinde bulunmadı; sayfa sırasını koruyan okumaların sıra benzerliği 0.97–1.00 |
| 0.1 | **İlk kör doğrulama seti, hiçbir değişiklikten önce:** bakımcının resume-xray sonuçlarını görmeden etiketlediği 22 gerçek ve şablon CV (etiketlere göre: Canva 11, Overleaf 5, Google Docs 4, iş sitesi 2; 11 İngilizce, 11 Türkçe) | 204 beklentinin 164'ü uyuşuyor (%80); 22 CV'nin 4'ü tamamen uyuşuyor. Uyuşmazlıklar: 13'ü etiketleme aracından (yalnızca görüntü olan PDF'lerde bölüm ve e-posta beklemiş), 4'ü yalnızca beş standart başlık sayan bir sorudan, gerisi başlık eşleştirmesinden ("Relevant Work Experience" gibi fazladan kelimeli başlıklar), "Eğitimler"in kurslara eşlenmesinden ve LaTeX PDF'lerinde birleşen kelimelerden. Aşağıdaki düzeltmelerden sonra bu set artık kör değildir |
| 0.1 | **Aynı 22 CV, düzeltmelerden sonra (kör değil):** bütün kelimelerle başlık eşleştirme, "Eğitimler", tekil ve Türkçe başlık biçimleri, çoğunluk biçiminden başlık kademesi, font boyutunun %15'i kelime aralığı, iki yanda akan metin olarak sütunlar; etiket soruları netleştirildikten sonra 11 etiket yeniden cevaplandı | 22 CV'nin 22'si tamamen uyuşuyor (etiketleyici bir düzen cevabını düzeltti: yatay çizgiler kutu düzeni sanılmıştı). Yansız bir sayı için yeni bir kör set gerekiyor |

---

## Kaynaklar

Kaynak listesi İngilizce belgeyle aynıdır: [ALGORITHM.md#references](ALGORITHM.md#references).
