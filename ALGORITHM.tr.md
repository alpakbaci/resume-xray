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

resume-xray **1. ve 2. maddeyi** ölçer. Ölçmediği şeyler:

- İşe alınıp alınmayacağınızı veya "ATS'nin vereceği puanı". Hiçbir ATS üreticisi böyle bir
  puan yayınlamaz; bunu taklit ettiğini söyleyen bir araç tahmin yürütüyordur.
- "CV'lerin %75'i ATS tarafından reddedilir" iddiası bir **mittir**. Kaynağı 2012'de kapanmış bir
  CV optimizasyon şirketinin (Preptel) satış sunumudur ve yöntemi hiç yayınlanmamıştır.

### Tek puan yok

Sonuç tek bir "%73 uyumlu" sayısı olarak verilmez. Birbiriyle ilgisiz bulguları (font hatası,
eksik yetenek, sütun düzeni) keyfi ağırlıklarla toplamak hem gerekçelendirilemez hem de kritik
hataları ortalamada gizler. Bunun yerine iki ayrı soru cevaplanır:

| Soru | Cevap biçimi | Kural |
|---|---|---|
| Belgem taranabiliyor mu? | `Uygun` / `Riskli` / `Okunamaz` | En kötü bulgu belirler |
| İlana göre aranabilir miyim? | Zorunlu ve tercih edilen terimler için ayrı kapsama oranı | Ağırlıklı kapsama (bölüm 3) |

---

## 2. Taranabilirlik

Her kontrol bir **şiddet** üretir: `kritik`, `uyarı` veya `bilgi`. Ağırlık yoktur; eşikler vardır.

- Herhangi bir `kritik` bulgu → **Okunamaz**
- `kritik` yok, en az bir `uyarı` → **Riskli**
- Diğer durumlar → **Uygun**

### 2.1 Metin katmanı (`min_chars_per_page = 50`)

Her sayfadan çıkarılan karakter sayısı `n_c` hesaplanır. `n_c < 50` ise sayfa taranmış bir
görüntüdür → **kritik**.

*Gerekçe:* Tipik bir CV sayfası 1.500–3.000 karakter içerir. 50'nin altı, yalnızca sayfa numarası
gibi kırıntıların çıkarılabildiği anlamına gelir.

### 2.2 Bozuk karakter oranı (`garbled_warn = 0.02`, `garbled_critical = 0.10`)

```
g = bozuk_karakter_sayısı / toplam_karakter_sayısı
```

Bozuk sayılanlar: `(cid:NN)` kalıpları (ToUnicode eşlemesi olmayan fontlar), `U+FFFD` (�) ve
Unicode özel kullanım alanı `U+E000–U+F8FF` (ikon fontları).

- `g > 0.02` → **uyarı**, `g > 0.10` → **kritik**

*Gerekçe:* %2'ye kadarı ikon ve madde işaretlerinden gelebilir ve okunabilirliği bozmaz. %10'un
üstünde kelimeler okunamaz hale gelir.

### 2.3 Çok sütun tespiti (`gutter_min_width_pt = 15`, `gutter_max_coverage = 0.05`, `gutter_min_height = 0.5`, `gutter_x_range = [0.2, 0.8]`)

Sayfa genişliği 1 puntoluk dilimlere bölünür. Her dilim için:

```
kapsama(x) = o dilimi bir kelime kutusuyla kesen satır sayısı / toplam satır sayısı
```

Sayfa genişliğinin %20–%80 aralığında, en az 15 punto genişliğinde, `kapsama(x) ≤ 0.05` olan
kesintisiz bir kanal varsa **ve** bu kanal metin yüksekliğinin en az %50'si boyunca sürüyorsa
sayfa **çok sütunlu** kabul edilir → **uyarı**.

*Gerekçe:* Sütun arası boşluk genellikle 15 puntodan geniş, kelime arası boşluk 3–5 puntodur.
%50 yükseklik şartı, yalnızca başlık alanında yan yana öğeler bulunan tek sütunlu sayfaların
yanlış işaretlenmesini önler. Sonuç **kritik değil**, çünkü modern ticari ayrıştırıcılar
(ör. Textkernel) sütunları çoğunlukla çözebilir; eski ve kurum içi sistemler ise çözemeyebilir.
Bu yöntem Textkernel'in ilk dönem kural tabanlı sütun tespitine benzer.

### 2.4 İki okuyucunun uyuşması (`agreement_bag_min = 0.9`, `agreement_order_max = 0.7`)

PDF hem `pdfplumber` hem `pypdf` ile okunur ve kelime dizileri karşılaştırılır:

```
kelime_benzerliği = |A ∩ B| / |A ∪ B|            (Jaccard, kelime kümeleri)
sıra_benzerliği   = SequenceMatcher(A, B).ratio() (kelime dizileri)
```

`kelime_benzerliği > 0.9` **ve** `sıra_benzerliği < 0.7` ise → **uyarı**: "okuma sırası belirsiz".

*Gerekçe:* Farklı ATS'ler farklı PDF okuyucuları kullanır. İki okuyucu aynı kelimeleri farklı
sırada çıkarıyorsa, belgenin bazı sistemlerde karışık okunma olasılığı yüksektir. Bu kontrol
2.3'ü destekleyen bağımsız bir sinyaldir.

### 2.5 Üst/alt bilgide iletişim (`header_footer_band = 0.08`)

- PDF: sayfa yüksekliğinin üst ve alt %8'lik bandı.
- DOCX: belgenin header/footer bölümleri (dosyada gövdeden ayrı saklanır).

E-posta veya telefon **yalnızca** bu alanlarda bulunuyorsa → **uyarı**.

*Gerekçe:* Bazı ayrıştırıcılar ve kütüphaneler (ör. mammoth, basit python-docx kullanımı) üst ve
alt bilgiyi atlar. Düzeltmesi kolay, riski gerçek.

### 2.6 Bölüm tespiti (`heading_max_words = 4`, `heading_size_ratio = 1.15`, `heading_match_min = 85`)

Bir satır şu koşulları sağlıyorsa **başlık adayıdır**:

- en fazla 4 kelime, **ve**
- şunlardan biri: font boyutu ≥ gövde medyanı × 1.15, kalın yazı veya tamamı büyük harf.

Aday, Türkçe/İngilizce başlık sözlüğüyle karşılaştırılır (`rapidfuzz.fuzz.ratio ≥ 85`).

- Temel bölümlerden (deneyim, eğitim, yetenekler) biri bulunamazsa → **kritik**
- Sözlükte karşılığı olmayan başlık adayı → **uyarı** ve en yakın standart başlık önerisi
  (ör. "Projelerim" → "Projeler")

*Gerekçe:* Ayrıştırıcılar bölümleri başlık sözlükleriyle sınıflandırır. 85 eşiği yazım
farklarını ("Experiences", "Is Deneyimi") yakalarken alakasız kelimeleri dışarıda bırakır.

### 2.7 Alan çıkarma

Düzenli ifadelerle (regex) şunlar aranır: e-posta, telefon (TR ve uluslararası biçimler),
LinkedIn adresi ve tarih aralıkları (`MM/YYYY`, `Oca 2021`, `Jan 2021`, `2019–2021`,
"Günümüz" / "Present").

- E-posta hiç yok → **kritik**
- Bir deneyim kaydının tarihi ayrıştırılamıyor (ör. "Yaz 2021") → **uyarı**

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
| Embedding (sentence-transformers vb.) | Kara kutu; belgelenmiş isim/cinsiyet önyargısı var (Wilson & Caliskan, AIES 2024); ~1 GB model indirmesi gerekir. ATS araması anlamsal değil, kelime bazlıdır |
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
