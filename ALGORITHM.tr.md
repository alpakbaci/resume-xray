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

### 2.0 Belgenin okunması (`row_overlap_min = 0.5`)

İki format da ortak bir ara biçime çevrilir: sayfası, font boyutu, kalınlığı ve bölgesi (gövde,
üst bilgi, alt bilgi, tablo, metin kutusu) bilinen metin satırları. PDF satırları ayrıca punto
cinsinden konumlarını ve ait oldukları görsel sırayı taşır. Her sayfa, kontrollerin
karşılaştırabilmesi için her okuma stratejisinin tam metnini de saklar.

**PDF.** `pdfplumber` her kelimeyi koordinatları, font adı ve boyutuyla verir. Bir kelimenin
dikey alanı, sıranın dikey alanıyla ikisinin küçük yüksekliğinin en az yarısı kadar örtüşüyorsa
kelime o sıraya katılır:

```
örtüşme(kelime, sıra) / min(yükseklik(kelime), yükseklik(sıra)) ≥ 0.5
```

Sıra, iki kelime arasındaki boşluğun `gutter_min_width_pt` değerinden (bkz. 2.3) geniş olduğu
yerlerden ayrı satırlara bölünür; böylece iki sütunlu bir sayfanın sol ve sağ sütunu tek satırda
birleşmez. Karakterlerinin çoğu adında Bold, Black, Heavy, Semibold veya Demi geçen bir fonttan
gelen kelime kalın sayılır.

*Gerekçe:* Aynı satırdaki kelimeler, boyutları farklı olsa bile yüksekliklerinin çoğunu paylaşır:
madde işareti gibi küçük bir karakter tamamen satırın içinde kalır (oran 1.0). Ardışık satırlar ise
neredeyse hiç örtüşmez, çünkü satır aralığı normalde en az font boyutu kadardır (oran 0'a yakın,
çok sık aralıkta en fazla yaklaşık 0.2). 0.5 ikisinin arasında güvenli bir değerdir.

Satır içinde kelimeler soldan sağa sıralanır; aynı x konumunda başlayan kelimelerde dar olan önce
gelir. Kelime sınırları yalnızca karakter aralıklarından belirlenir, font değişiminden asla.

*Gerçek bir CV'de bulundu:* Önceki sürüm, üst kenarları 3 puntodan yakın kelimeleri grupluyordu.
Bir CV'de görünen madde işaretleri çizilmiş şekillerdi; her maddenin ilk harfinin üzerinde, metnin
taban çizgisinde ve satırın üstünden 6.7 punto aşağıda görünmez 0.75 puntoluk bir metin madde
işareti duruyordu. Üst kenar gruplaması bu işareti satırın sonuna taşıyordu ("Managed •"); örtüşme
gruplaması ve "dar olan önce" kuralı onu tekrar başa aldı. Aynı CV, İ harfi için ayrı bir font alt
kümesi kullanıyordu ve kelimeleri font değişiminde bölmek "TÜBİTAK"ı "TÜB İ TAK" yapıyordu.

Bir PDF sayfasının üç okuması:

- **İçerik akışı sırası:** `pypdf`'in `extract_text()` çıktısı.
- **Konum sırası:** `pdfplumber`'ın `extract_text()` çıktısı.
- **Sütun farkındalıklı sıra:** bizim satırlarımız. Kanal (2.3) yoksa sıralar yukarıdan aşağı
  okunur. Kanal varsa, kanalı kesen satırlar sayfayı bloklara böler; bir blokta iki tarafta da en
  az iki sıra varsa önce sol, sonra sağ sütun okunur, yoksa blok sıra sıra okunur (böylece iki
  tarafta öğesi olan bir iletişim satırı bir arada kalır).

**DOCX.** `python-docx` paragrafları gövdedeki sırasıyla, tabloları ve her bölümün üst/alt
bilgisini verir. Metin kutuları ham XML'den (`w:txbxContent`) okunur, çünkü `python-docx` bunları
sunmaz; Word her kutuyu iki kez saklar (DrawingML ve VML yedeği) ve yalnızca biri okunur. Font
boyutu ve kalınlık metin parçalarından (run), yoksa paragraf stilinden alınır. Her iki formatta da
bağlantı (hyperlink) hedefleri 2.7 için toplanır.

### 2.1 Metin katmanı (`min_chars_per_page = 50`)

Her sayfadaki boşluk olmayan karakter sayısı `n_c` hesaplanır. `n_c < 50` ise sayfa taranmış bir
görüntü veya şekle dönüştürülmüş metindir → **kritik** (tüm stratejileri bozar; yalnızca OCR
çalıştıran bir ATS okuyabilir [4]).

*Gerekçe:* Tipik bir CV sayfası 1.500–3.000 karakter içerir (kendi gözlemimiz). 50'nin altı,
yalnızca sayfa numarası gibi kırıntıların çıkarılabildiği anlamına gelir.

### 2.2 Bozuk karakterler (`garbled_warn = 0.02`, `garbled_critical = 0.10`)

```
g = bozuk_karakter_sayısı / toplam_karakter_sayısı
```

Sütun farkındalıklı okumada bozuk sayılanlar: `(cid:NN)` kalıpları (karakter eşlemesi olmayan
fontlar), `U+FFFD` (�) ve Unicode özel kullanım alanı `U+E000–U+F8FF` (ikon fontları).

- `g > 0.02` → **uyarı**, `g > 0.10` → **kritik**

*Gerekçe:* %2'ye kadarı ikon ve madde işaretlerinden gelebilir ve okunabilirliği bozmaz. %10'un
üstünde kelimeler okunamaz hale gelir.

### 2.3 Çok sütunlu düzen (`gutter_min_width_pt = 15`, `gutter_max_coverage = 0.05`, `gutter_min_height = 0.5`, `gutter_x_range = [0.2, 0.8]`)

Sayfa genişliği 1 puntoluk dilimlere bölünür. Her dilim için:

```
kapsama(x) = kutusu dilimi kesen satır sayısı / toplam satır sayısı
```

**Kanal**, sayfa genişliğinin %20–%80 aralığında, en az 15 punto genişliğinde, `kapsama(x) ≤ 0.05`
olan en geniş kesintisiz şerittir; ancak solundaki ve sağındaki satırların her biri sayfanın metin
yüksekliğinin en az %50'sini kaplamalıdır.

Kanalı olan bir sayfada içerik akışı ve konum okumaları sütun farkındalıklı okumayla karşılaştırılır
(2.4'teki gibi). Bulgu, sütunları karıştıran stratejileri belirten bir **uyarı**, hiçbiri
karıştırmıyorsa **bilgi** olur.

*Gerekçe:* Sütun arası boşluk genellikle 15 puntodan geniş, kelime arası boşluk 3–5 puntodur. %50
yükseklik şartı, yalnızca başlık alanında yan yana öğeler bulunan tek sütunlu sayfaların yanlış
işaretlenmesini önler. Sütunlar yalnızca onları karıştıran okuyucular için sorundur; Tika, konuma
göre sıralamanın "sütunları birbirine karıştırabileceğini" belgeler [4]. Textkernel, CV'lerin en az
%15'inin sütun kullandığını tahmin eder ve görsel boşlukları bulan eski kural tabanlı yöntemini
anlatır; bu yöntem ona benzer [6].

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
hangi dile göre küçük harfe çevrildiklerinden bağımsız olarak eşleşir.

- Temel bir bölüm (deneyim, eğitim, yetenekler) tanınmadı → **uyarı**.
- Sözlükte olmayan ama tanınan başlıklarla aynı stile (boyut, kalınlık, büyük harf) sahip ve ilk
  tanınan başlıktan sonra gelen aday → **uyarı** ve en yakın standart başlık önerisi. Aynı stil
  şartı, ismin ve kalın iş unvanlarının başlık sanılmasını önler.
- Bir okumada kendi satırında olmayan tanınmış başlık → o stratejileri belirten **uyarı**: başlık
  satırı arayan bir ayrıştırıcı onu görmez.

*Gerekçe:* Ayrıştırıcılar bölümleri başlık sözlükleriyle sınıflandırır. 85 eşiği yazım farklarını
("Experiences", "Language") yakalarken alakasız kelimeleri dışarıda bırakır. Eksik bölüm kritik
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

### 3.1 Normalleştirme (CV ve ilan için aynı)

1. Unicode NFKC dönüşümü.
2. **Türkçe uyumlu küçük harf:** `I → ı`, `İ → i`. Python'un `str.lower()` fonksiyonu Türkçede
   yanlış sonuç verir; bu, Türkçe metinlerde en sık görülen eşleşme hatasıdır.
3. `+`, `#` ve `.` korunur; aksi halde `C++`, `C#`, `.NET` kaybolur.
4. Snowball ile kök bulma (dil, stopword sayımıyla tespit edilir): "Python'da" → "python".

### 3.2 İlandan terim çıkarma

- **Yetenek sözlüğü:** 1–3 kelimelik eşleşmeler. Sözlük eş anlamlıları içerir
  (`k8s → kubernetes`, `js → javascript`). Başlangıçta elle hazırlanmış bir teknoloji listesi;
  sonraki aşamada ESCO (Türkçe dahil 28 dil) eklenecek.
- **Teknik görünümlü kelimeler:** Rakam, `+`, `#` içeren veya CamelCase yazılan kelimeler aday
  terim olarak alınır.

### 3.3 Terim ağırlığı (`required_weight = 1.0`, `preferred_weight = 0.5`)

```
w_t = r_t × (1 + ln(1 + f_t))
```

**`r_t` — gereklilik katsayısı**

| Terimin geçtiği ilan bölümü | `r_t` |
|---|---|
| "Aranan nitelikler", "Requirements", "Must have" | 1.0 |
| "Tercih sebebi", "Nice to have", "Artı" | 0.5 |
| Belirsiz | 1.0 |

*Gerekçe:* İlanı yazanın kendi zorunlu/tercihli ayrımına güvenilir. 0.5, "tercih edilen bir
terim, zorunlu bir terimin yarısı kadar önemlidir" varsayımının en sade halidir. Belirsiz
bölümler, eksikliği gözden kaçırmamak için zorunlu sayılır.

**`f_t` — terimin ilanda geçme sayısı**

*Gerekçe:* Bir terim ilanda ne kadar sık geçiyorsa o kadar önemlidir, ancak etkisi logaritmayla
**doyurulur**: 1 kez geçen terim ×1.69, 5 kez geçen ×2.79 ağırlık alır (5 kat değil). Bu, BM25'teki
terim sıklığı doygunluğuyla aynı fikirdir ve ilanda 10 kez tekrarlanan tek bir kelimenin diğer
tüm terimleri ezmesini önler.

### 3.4 Eşleşme seviyesi (`synonym_match = 0.5`)

| Durum | `m_t` | Gerekçe |
|---|---|---|
| Normalleştirme sonrası tam eşleşme | 1.0 | İşe alımcı ilandaki kelimeyle aradığında bulur |
| Yalnızca eş anlamlı var (ilan "Kubernetes", CV "k8s") | 0.5 | Anlam aynı, ama ATS araması kelime bazlıdır ve bulamayabilir. Kullanıcıya "ilandaki yazımı da ekleyin" önerilir |
| Yok | 0 | — |

### 3.5 Kapsama

```
Kapsama = Σ (w_t × m_t) / Σ w_t
```

Zorunlu ve tercih edilen terimler için **ayrı ayrı** hesaplanır ve gösterilir.

Terimin CV'de nerede geçtiği (deneyim maddesi mi, yalnızca yetenek listesi mi) de raporlanır,
ancak **kapsamayı etkilemez**. ATS araması iki yerde de bulur; deneyim içinde geçmesinin daha
değerli olması insan okuyucuya ilişkin bir tavsiyedir.

### 3.6 Ayrı kontroller (kapsamaya karışmaz)

| Kontrol | Yöntem | Neden ayrı |
|---|---|---|
| Pozisyon başlığı | İlan başlığı ile CV'deki başlıklar: `rapidfuzz.fuzz.token_set_ratio ≥ 85` | İşe alımcıların en çok aradığı alan |
| Deneyim yılı | İlandaki "5+ yıl" kalıbı; CV'deki tarih aralıkları birleştirilir (çakışan dönemler bir kez sayılır) | Eleme kriteridir, kapsamayla karıştırılmamalı |
| Diploma | İlandaki "lisans/bachelor" vb. kalıplar eğitim bölümünde aranır | Eleme kriteridir |

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

---

## Kaynaklar

Kaynak listesi İngilizce belgeyle aynıdır: [ALGORITHM.md#references](ALGORITHM.md#references).
