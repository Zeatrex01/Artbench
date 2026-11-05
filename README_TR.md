# Artbench

### ⬇ [Artbench'i Windows için indir](https://github.com/Zeatrex01/Artbench/releases/latest/download/Artbench-windows-x64.zip)

Zip'i istediğin yere aç ve `Artbench.bat`'a çift tıkla: Python içinde, kurulacak bir şey yok. ·
[artbench.malik3d.page](https://artbench.malik3d.page/) · [tüm sürümler](../../releases)

> Yeşil **Code → Download ZIP** düğmesi kaynak kodu indirir, o da Python 3.11+ ister. Kullanmak için yukarıdaki indirmeyi al.

Git'ten klonlanmış oyun projesi ile ayrı art klasörü arasında yerel bir art köprüsü:

```
Oyun projesi (git clone)  <->  Artbench  <->  Art klasörü (FBX / Blend / Textures)
```

Hangi modeller var, hangileri oyunda, nerede kullanılıyor, hangisi stokta, iki taraftaki kopya aynı mı. Tek kural:
**iki taraf arasında hiçbir dosya sessizce ezilmez.** Her model için iki tarafın son mutabık olduğu hâl tutulur;
yalnızca bir taraf değiştiyse o taraf "yeni"dir, ikisi de değiştiyse **çakışma**dır ve ne gönderim ne alma onay
almadan yapılmaz; ezilen kopya arşive gider. Git oyun projesinin aracı olarak kalır; Artbench git'e dokunmaz, onu
taklit etmez. Her taşıma ve not geçmişe yazılır, eski dosyalar arşive gider, araç hiçbir dosyayı silmez.

Masaüstünde durur, repolara girmez. Sadece Python 3 ister; Unity'ye, eklentiye veya başka araca bağımlı değildir
(motor tarafını Unity'nin metin dosyalarından okur). Mimari ve API: `ARCHITECTURE.md`.

## Çalıştırmak
Sayfa İngilizce açılır; sol alttaki **TR / EN** düğmesi dili değiştirir ve tarayıcı bunu hatırlar.

**Hazır sürüm (önerilen):** yukarıdaki indirme; zip'i aç, `Artbench.bat`'a çift tıkla, Artbench kendi penceresinde
açılır. **Kaynak koddan:** kökteki `Artbench.bat` bilgisayarda Python 3.11+ varsa onunla açar; yoksa bunu söyler ve hazır
sürümü indirmeye başlar. Açılışta kısa bir animasyon oynar (kalem tezgâhı çizer); pencere başına bir kez, herhangi bir
tuş ya da tıklama geçer, sistemde "hareketi azalt" açıksa hiç oynamaz.
`server.py` değişince sunucu yeniden başlatılmalı (kodu sıcak yüklemez).

## Favoriler, revize notları, etiketler, seçip aktarmak
Bir varlığın kartında **Favori** (yıldız) ve **Revize gelecek** (isteğe bağlı notuyla) var; satırlarda yıldız ve
Revize rozeti görünür, hepsi sol menüdeki **İşaretli** sekmesinde toplanır (Revize bekleyenler / Favoriler). Satırların
solundaki kutuyla birkaç varlığı seç (Shift: aralık); alttaki çubuktan hepsini favorile, revize işaretle ya da
**klasöre aktar**: Unity'deki modeller kullandıkları dokularla, her biri kendi klasöründe, seçtiğin klasöre kopyalanır;
önce plan gösterilir, orada olan dosyanın üstüne yazılmaz. Unity'deki bir modeli art klasörüne alırken de dokularını
getirmek için kutu işaretli gelir.

**Etiketler** senin kelimelerin (kahraman, bölüm 2, dış kaynak): kartta alana yazıp Enter'a bas, çarpıyla kaldır; seçili
varlıkların hepsine alttaki çubuktaki **Etiketle…** ile ekle. Etiketler küçük harfe çevrilir. Sol menüdeki Etiketler
kataloğu, İşaretli sekmesindeki etiketler o listeyi süzer; AI da `mark` (tags_add, tags_remove) ve `marks` (tag) ile
kullanır.

## Denetim: kopyalar ve standartlar
Sol menüdeki **Denetim** yalnızca öneri verir, hiçbir şeyi değiştirmez. **Standartlar**: çok büyük içe aktarılan
dokular (varsayılan sınır 4096), kenarı ikinin kuvveti olmayanlar, Read/Write'ı açık olanlar, sıkıştırılmamışlar; isteğe
bağlı olarak ad önekleri (T_, M_, PF_, SM_) ve model başına üçgen bütçesi (Blender'ın sayımıyla). Her kuralın sayısına
tıklayınca liste o kurala daralır; **Kurallar** düğmesinden sınırları ve önekleri ayarla. Unity ayarları `.meta`
dosyalarından yalnızca okunur. **Kopyalar**: aynı içerikli dosyalar ve her kopyayı neyin kullandığı, kopyaların kapladığı
yerle birlikte. AI aynı bilgiyi `checks` ve `checks_settings` araçlarıyla alır.

## Makine kontrolü
Sol alttaki **Projeler** → **Bu makineyi kontrol et**: açık proje için motor klasörünü, motor dökümünü, art
klasörüne yazmayı, süreçler arası proje kilidini, dosya özetini, uzun yolları (Windows), OneDrive'ı, Blender'ı ve sayfa
sunucusunu dener; her satır tamam / uyarı / başarısız / atlandı. Oyun projesine hiçbir şey yazılmaz. Aynı kontrol
komut satırından: `python -m artbench call doctor --project <id>` (MCP'de `artbench_doctor`).

## Proje modu: oyun projesinin art envanteri (art klasörü olmadan)
Ekipteki herkes için: Unity projesini kendi bilgisayarında klonlamış olman yeterli. Artbench o klonu okur; projedeki
art'ı (modeller, dokular, materyaller, prefab'lar, sahneler, animasyonlar, sesler…), onları neyin kullandığını,
neyin hiçbir yerde kullanılmadığını ve son baktığından beri neyin değiştiğini gösterir. Projeye **hiçbir şey yazmaz**;
kendi dosyalarını Artbench klasöründeki `projects/<id>/` altında tutar. Her kişi kendi klonunu, hangi daldaysa onu görür.

Kurulum (bir kez):
```
python -m artbench setup "D:/Projeler/MyGame"            (ya da ArtbenchSetup.bat "D:/Projeler/MyGame")
python -m artbench setup "D:/Projeler/MyGame" --mcp claude   (Claude Code'a da kaydeder)
python -m artbench setup "D:/Projeler/MyGame" --github hesap-adin   (bu projenin push yaptığı GitHub hesabı)
```
Komut projeyi bulur, ilk taramayı yapar ve Claude Code, Gemini CLI ve Codex için MCP kayıt satırlarını yazar.
Sayfadan da olur: sol üstteki **Proje bağla** → Unity proje klasörünü seç → **Sadece oyun projesi** → **Bağla**.
Bağlanırken her adım ilerlemesiyle görünür (dosyalar, .meta dosyaları, neyin neyi kullandığı, proje ayarları); bitince
katalog açılır.

Kullanım kelimeleri:
- **Kullanılıyor**: projede bir şey ona referans veriyor (build ayarlarındaki sahneler de sayılır).
- **Referans yok**: projenin dosyalarında hiçbir şey ona referans vermiyor. Büyük ihtimalle kullanılmıyor, ama kod
  yine de yükleyebilir; silmeden önce kontrol et.
- **Adından yükleniyor**: `Resources` ya da `StreamingAssets` içinde; kod adından yükler, referanslar bunu gösteremez.
- **Bilinmiyor**: proje Force Text değil (Project Settings › Editor › Asset Serialization), referanslar okunamıyor.

Katalog **Türe göre** ya da **Klasöre göre** gruplanır; klasör kutusundan tek bir klasörü (altındakilerle birlikte)
seçebilirsin. Project Settings'in kullandıkları (oyun ikonu, her zaman dahil edilen shader'lar) da **kullanılıyor**
sayılır; kartta "Proje ayarları" satırı olarak görünür.

Her varlık ne olduğunu gösterir:
- **Önizleme:** modeller Blender render'ı, dokular resmin kendisi (PNG/JPG doğrudan; TGA, PSD, EXR ve büyük resimleri
  Blender küçültür). Blender yoksa ikon kalır.
- **Model istatistikleri:** satırda üçgen sayısı, kartta üçgen, vertex, mesh obje, materyal, doku, kemik ve animasyon
  sayıları. Arka planda Blender ölçer, dosya değişmedikçe bir kez; ölçülürken "ölçülüyor…" yazar.
- **Doku bilgisi:** satırda çözünürlük (2048 × 2048), kartta format; dosyanın başlığından okunur, Blender gerekmez.
- **Sıralama:** ad, önce en büyük, en çok üçgen, son değişen; seçim hatırlanır.
- **Klasör gizleme:** Klasöre göre görünümde grup başlığındaki **Gizle**; gizlenenler rakamların altında listelenir,
  **Göster** ile geri gelir. Yalnızca o yol gizlenir (`Assets/Art/Old`), gizli klasörün kullandıkları yine sayılır.
- **Blender'da aç:** model kartındaki düğme; `.blend` doğrudan açılır, FBX/OBJ/glTF boş sahneye aktarılır.

**Yerleşim** (her asset türü projede durması gereken yerde mi) sen açana kadar kapalıdır. **Bu kurallarla aç**
dediğinde kuralları asset'lerin şu an durduğu yerlerden çıkarır ve gösterir; dışarıda kalanları listeler, **Bu klasör
doğru** ile bir klasörü o tür için kabul edersin. Sadece raporlar, hiçbir şeyi taşımaz.

**Değişiklikler**: pull, dal değişikliği ya da bir ekip arkadaşının işiyle gelenler; taşınan dosya tek satırdır.
**Görüldü** düğmesi işareti ilerletir; yapay zekân da aynı işareti görür (`artbench_changes` ile `since_seen`).
**Görevler**: senin önceliklerin (Yüksek / Normal / Düşük). Kendin yazarsın ya da yapay zekâna söylersin; o da MCP
ile ekler ve taşır (`artbench_task_add`, `artbench_task_update`), pano birkaç saniye içinde güncellenir. Bir varlığa
bağlı görev o varlığın kartında da görünür.

Yapay zekâna sorabileceklerin: "Oyunumda hangi dokular hiçbir yerde kullanılmıyor?", "M_Crate'i neler
kullanıyor?", "Bu daldan beri neler değişti?", "Crate dokusunu yeniden boyamayı yüksek öncelikli görev olarak ekle",
"Blender açık mı?", "Drone'u Blender'da aç".

## GitHub hesabı (projeye göre)
Projeler ekranında her projenin yanına bu projenin push yaptığı GitHub hesabını yazarsın (ya da `setup --github`).
Artbench git'i ya da gh'yi çalıştırmaz: GitHub CLI'ın hangi hesapta olduğunu kendi `hosts.yml` dosyasından okur.
Başka hesaptaysa sol menüde proje seçicinin altında uyarı çıkar ve **Geçiş komutunu kopyala** `gh auth switch`
komutunu kopyalar. Yapay zekân aynı bilgiyi proje özetinde (`artbench_overview` → `github`), makine kontrolü
`github_account` satırında görür.

## Unity'deki bir modeli art klasörüne almak
**Sadece motorda** görünümünde bir modeli aç ve **Art klasörüne al**'a bas. Kategoriyi sorar (Unity'deki klasöründen
tahmin eder, yeni bir ad da yazabilirsin) ve yalnızca modeli `FBX/<Kategori>/<Model>/` altına kopyalar. Dokuları
Unity'deki yerinde kalır, ikinci kopya olmaz. Model tek kart olur ve "Aynı" görünür; kartında ve kütüphanede
**Unity'den** etiketi, kartında da ne zaman ve hangi yoldan alındığı yazar. Geçmiş'e bir satır düşer. Değiştirip
gönderdiğinde yalnızca model gider.

## Uygulama penceresi ve taşınabilir klasör
`python -m artbench --app` Artbench'i kendi penceresinde açar: adres çubuğu yok, görev çubuğunda Artbench
simgesiyle durur (Edge, yoksa Chrome kullanılır). Pencereyi kapatınca Artbench da kapanır. Artbench zaten açıksa
yalnızca yeni bir pencere açılır.

**Taşınabilir klasör (Windows):** `Artbench-portable-win64.zip`'i istediğin yere aç (oyun projesinin içine değil).
İçinde kendi Python'u var, hiçbir şey kurulmaz. `Artbench.bat`'a çift tıkla; masaüstüne simgeli bir kısayol için
bir kez `CreateShortcut.bat`. Ayarların klasörün içinde durur, klasörü taşırsan seninle gelir (yapay zekâ
bağlantısını o zaman Projeler ekranından **Güncelle**). Zip'i üretmek için: `python tools/build_portable.py`.

## Yapay zekâ bağlantısı (MCP)
MCP, Claude Code, Gemini CLI ya da Codex'in Artbench'i okuyup kullanma yolu. Araç, Artbench'i gerektiğinde kendisi
başlatır; sayfanın açık olması gerekmez. Bir bilgisayarda bir kez eklenir: **Projeler** ekranındaki **Yapay zekâ
bağlantısı** kartında her aracın durumu görünür (bağlı / eski klasör / eklenmedi / kurulu değil). **Claude Code'a
ekle** tek tıkla ekler; Gemini CLI ve Codex için **Kopyala** eklenecek satırı verir. Ekledikten sonra aracı yeniden
başlat ve sor: "Artbench'te kullanılmayan modeller hangileri?"

## Blender eklentisi (Artbench Bridge)
`python -m artbench addon` eklenti zip'ini yazar (çıktı yolu verilmezse `artbench_bridge.zip`). Blender
4.2+ içinde: Edit → Preferences → Get Extensions → Install from Disk → zip.

**Notlar (Artbench kapalıyken de çalışır).** 3D görünümün yan panelinde (`N`) **Artbench** sekmesi, **Notes** bölümü:
dosyanın notları ve yapılacakları (to-do'da onay kutusu, öncelik rengi, bağlı olduğu obje). Bir objeye sağ tık →
**Add note**, ya da listenin yanındaki **+**: metin, to-do mı not mu, öncelik; not seçili objeye bağlanır. Açık
notlar 3D görünümde objenin yanında küçük bir iğne ve ilk satırıyla durur (aynı objede birden fazlaysa en acili ve
+sayı); biten to-do'lar görünmez, **Show pins in the 3D view** hepsini gizler. Listede bir nota tıklayıp objenin
yanındaki düğmeyle objeyi seçip ekrana getirirsin. Notlar `.blend`'in içinde saklanır: dosyayla gider, obje adı
değişse de bağ kopmaz, eklentisi olmayan bir Blender da veriyi korur. Her değişiklik geri alınabilir ve Blender
dosyayı kaydedilmemiş sayar.

**Artbench desteği.** Artbench açıksa ve dosya bir projedeyse Notes bölümünde **Send to Artbench** çıkar: dosyanın
notlarının bir kopyasını gönderir. Artbench'te Görevler sayfasının altında ayrı bir **Blender'dan** bölümünde,
dosya başına bir kartta görünür (gönderme zamanıyla); yeniden göndermek o dosyanın kartını yeniler, kopya oluşmaz.
Orada salt okunurdur: değiştirmek için Blender. Artbench hiçbir `.blend`'i kendisi açıp okumaz. Yapay zekân
`artbench_blender_notes` ile aynı listeyi okur.

**Bağlantı.** **Artbench link** bölümü bağlantıyı açıkça yazar: bağlıysa proje ve dosya, değilse sebebi ve nereye
baktığı; **Test connection** hemen dener. Eklenti 5 saniyede bir Artbench'e Blender'ın açık olduğunu ve hangi dosyanın
açık olduğunu söyler; kapanınca kapandığını. Eklenti ayarlarında (Preferences → Add-ons → Artbench Bridge) adres,
bağlantı durumu ve **Test connection** var. İstekler proxy'den geçmez; stüdyo ağındaki bir proxy bağlantıyı
engellemez. Yapay zekân `artbench_blender_status` ile Blender'ın açık olup olmadığını, dosyayı ve projeyi öğrenir.
Adres eklenti ayarından ya da `ARTBENCH_URL` ortam değişkeninden değişir. 0.2'deki pano görevleri bölümü kalktı; o
bölümden eklenen görevler panoda durur. Sahneyi okuma, değişiklik takibi ve export şablonları sonraki adımlar.

## Proje bağlamak (art modu: oyun projesi + art klasörü)
1. **Oyun projesi:** oyun projesinin içinden bir klasör seç (Gözat düğmesi yerel klasör penceresi açar). Araç Unity
   projesini bulur (`Assets` + `ProjectSettings`) ve art kökünü önerir.
2. **Art klasörü:** projeye ad ver, art klasörünün adını ve nereye kurulacağını seç. Klasör varsa bağlanır, yoksa
   şablondan oluşturulur: `FBX/<Kategori>/`, `Outbox/`, `Stock/`, `_Archive/`, `Blend/<Kategori>/`, `Textures/`,
   `README.md`, `art_inventory.json`. Takip dosyaları da bu klasörde durur; klasör bütün hâlinde taşınabilir.

Zaten ayar dosyası olan bir art klasörü "Mevcut art klasörünü bağla" ile eklenir. "Ayır" sadece listeden çıkarır,
dosya silmez. Projeler listesi `projects.json` içindedir; makineye özel tek dosya budur.

## Klasör kuralı (art klasörü)
| Klasör | Anlamı |
|---|---|
| `FBX/<Kategori>/<Set>/` | oyunda olan modeller, dokuları yanında (Outbox'tan gönderilen model kendi klasörüne gider: `FBX/<Kategori>/<ModelAdı>/`) |
| `Outbox/<Kategori>/` | bitti, motora gönderilmeyi bekliyor |
| `Stock/<Kategori>/` | hazır ama oyunda değil |
| `_Archive/<tarih>/` | değiştirilen dosyalar (silinmez) |
| `Blend/<Kategori>/` | Blender kaynakları |
| `Textures/<Set>/` | ortak doku setleri (model değildir, tarama atlar) |

Şablondan önce kurulmuş bir art klasöründe ayar dosyası art kökünün yanında olabilir (`Desktop/MyGame/art_inventory.json`,
art kökü `INGAME/`, arşiv bir üstte `_Archive/`). Ayar formatı ikisini de karşılar.

## Paket: model + dokuları
Bir model motora dokularıyla birlikte gider. Modelin klasöründe adı model adıyla başlayan (`Crate_BaseColor.png`,
`Crate-Normal.tga`, ...) dokular onun paketidir; klasörde birden çok model varsa en uzun eşleşen ad kazanır.
Motora yalnızca hazır formatlar gider (`package_extensions`, varsayılan `.png .tga .jpg .jpeg`); `.psd`, `.exr` gibi
kaynaklar art tarafında kalır ve kartta "kaynak" olarak listelenir. Bir `.gltf` ayrıca içinde adı geçen dosyaları
yanında taşır: `.bin` veri dosyaları (kartta veri simgesiyle) ve adı model adıyla başlamasa da kullandığı dokular.
Bunlar motorda her zaman modelin yanına gider, çünkü `.gltf` onları orada arar. Taşınamayan bir dosya adı geçiyorsa
(başka klasörde, eksik ya da bir model dosyası) kart bunu söyler ve gönderim önce onay ister; `.bin`'i olmadan giden bir
`.gltf` motorda bozuk açılır. İki modelin birlikte kullandığı bir dosya kartta belirtilir; her birinin kendi kopyası
olana kadar bu modeller klasör değiştiremez. Her dosyanın kendi eşitlik durumu vardır;
listede ve sayaçlarda modelin durumu paketteki en kötü durumdur.

Motorda yeni dosyanın nereye gideceği projeye göre seçilir (`engine_layout`):
- `per_model` (kendi projen, yeni bağlanan projelerde varsayılan): model ve dokuları tek klasörde,
  `<engine_targets[kategori]>/<ModelAdı>/`.
- `follow` (ekibin dosyaları taşıdığı projeler): motordaki dosyalar adıyla bulunur, nereye
  taşındıysa oradan güncellenir; yeni doku modelin diğer dokularının durduğu klasöre gider, hiç yoksa
  `engine_texture_targets[kategori]`, o da yoksa "hedef yok" denir ve gönderilmez. Artbench klasör uydurmaz,
  Unity projesini yeniden düzenlemez.

Gönder/Al diyaloğu paket dosyalarını onay kutularıyla listeler. **Ekibin motorda değiştirdiği bir doku varsayılan
olarak işaretsiz gelir** ("Unity'de değişti, önce al"); işaretlersen arşive alınarak ezilir ve geçmişe `FORCED`
yazılır. Önce dokular, en son model yazılır; bir dosya yazılamazsa durur, yazılanlar yazılmış kalır ve hangi
dosyanın gittiği, hangisinin gitmediği gösterilir. Her dosya geçmişe ayrı satır olarak düşer.

## Blender kaynağı (.blend bağlama)
Kart modelin `.blend` dosyasını gösterir: `Blend/` altında aynı adlı dosya otomatik bulunur ("aynı ad"), farklıysa
karttaki seçiciden bağlanır ("bağlı"). Satırın üzerine gelince Blender'da aç / klasörde göster düğmeleri çıkar.
`.blend` motora hiç gönderilmez.

## Sayfa
- **Sol:** kategori → set ağacı (sayılar, kullanılmayan sayısı turuncu), durum / kullanım / eşitlik filtreleri.
- **Orta:** set set gruplanmış model listesi; küçük önizleme (Blender arka planda çizer, önbellekli), durum,
  kullanım, motorla eşitlik (aynı / masaüstü yeni / motor yeni / **çakışma** / motorda yok), doku sayısı, not.
- **Sağ:** seçili modelin kartı. En üstte **Eşitlik** bloğu: Masaüstü ve Unity yan yana (Aynı / Değişti / Yok,
  tarih, boyut), son eşitleme zamanı, tek cümle açıklama ve yalnızca o duruma uygun düğmeler: **Unity'ye gönder**,
  **Motordan al**, çakışmada **Benimkini gönder / Motordakini al** (kırmızı). Onay diyaloğu düz cümleyle ne olacağını
  söyler: hangi taraf ne zaman değişti, ezilen kopya hangi arşiv yoluna gider, `.meta` korunur, kaç prefab/sahne
  etkilenir. Eşitlik henüz tarih karşılaştırmasına dayanıyorsa etiketler soluk ve kart bunu söyler. Altında
  **Değişiklikler**, **Konum** (Oyunda / Gidecek / Stok / Arşiv klasörleri arasında taşıma), nerede kullanılıyor,
  dokular, Blender kaynağı, görevler, not; en altta Klasörde göster / Unity'de göster / Grafta göster.
  **Değişiklikler** bölümü gönderince oyunda ne değişeceğini gösterir: vertex/poligon sayısı, eklenen/çıkan nesne,
  materyal, doku, bone ve animasyon, bounding box. Altında **Uyarılar** (Unity referanslarını kırabilecek farklar) ve
  **Etkilenen** (modeli kullanan prefab/sahne/materyaller). Çakışmada "Masaüstünde değişen" ve "Motorda değişen" ayrı
  listelenir. Bilgi arka planda Blender'la çıkarılır ve içerik başına bir kez önbelleğe alınır; Blender yoksa yalnızca
  dosya boyutu karşılaştırılır. Gönderim planındaki uyarılar da aynı kaynaktan gelir.
- **Alt sekmeler:** Sadece motorda (Unity'de var, masaüstünde yok), Model bekleyen geçiciler (kodla yapılmış mesh
  `.asset`'ler; kullanılanlar işaretli), **Görevler** (yapılacak / yapılıyor / bitti, varlığa bağlanabilir),
  **Yerleşim** (açınca, her türün durduğu yerlerden öğrenilen kuralların dışında kalan dosyalar; sadece bilgi, taşımaz),
  **Graf** (model → materyal → doku → prefab → sahne referans grafiği; bir düğüm seçilir, 2 komşuluk çizilir;
  kullanılmayanlar kesikli halka; "Sadece kullanılmayan" listesi), Blender kaynakları, Sınıflanmamış, Geçmiş.
- **Sahneler:** her sahnenin kullandıkları (prefab, model, materyal, doku, geçici mesh), eşitlik noktalarıyla; satıra
  tıklayınca o modelin kartı açılır. Salt okunur, Artbench sahneye asla dokunmaz. Unity köprüsünden taze rapor gelmişse
  "canlı" (kaydedilmemiş değişiklikler dahil), yoksa "dosyalardan". Sol altta köprünün son rapor zamanı görünür.
- Sayfa 4 saniyede bir tarar; "Yenile" motor taramasını zorlar.

## Claude ve diğer yerel ajanlar için MCP
`artbench/mcp_server.py` aynı envanteri MCP aracı olarak sunar; Claude Code içinden "hangi modeller
kullanılmıyor", "bu model nerede kullanılıyor", "şu görevi ekle", "şunu stoğa taşı" denebilir. Araçlar:
`artbench_projects`, `artbench_overview`, `artbench_search`, `artbench_asset`, `artbench_unused`, `artbench_placeholders`,
`artbench_layout_issues`, `artbench_graph_neighbors`, `artbench_tasks`, `artbench_task_add`, `artbench_task_update`,
`artbench_note`, `artbench_move`, `artbench_history`, `artbench_refresh`, `artbench_changes`, `artbench_send_plan`, `artbench_send`,
`artbench_pull_plan`, `artbench_pull` (gönder/al `files` ile paketten dosya seçebilir), `artbench_metadata_snapshot`,
`artbench_metadata_diff`. Her yazma işlemi sayfayla aynı geçmişe düşer; aynı anda yazan süreçler proje kilidini bekler.
Araç listesi sayfadakiyle aynı işlem katmanından (`artbench/ops/` paketi) üretilir; ayrıca `artbench_meta`, `artbench_preview`,
`artbench_scene_inventory` (sahne neyi kullanıyor), `artbench_engine_status` (Unity köprüsü rapor verdi mi),
`artbench_doctor` (makine kontrolü), `artbench_catalog`, `artbench_blender_status` (Blender açık mı, hangi dosya),
`artbench_blender_notes` (Blender'dan gönderilen notlar),
`artbench_open_in_blender` (modeli Blender'da aç), `artbench_layout_settings` (Yerleşimi aç/kapat, klasör kabul et),
`artbench_bring_in_plan` ve `artbench_bring_in` (Unity'deki modeli art klasörüne al) vardır: toplam 34 araç, sadece oyun
projesinde 21.
Kayıt makine başına bir kez yapılır; `<Artbench>` aracın klasörünün yolu (ör. `C:\Users\<kullanıcı>\Desktop\Artbench`):

Claude Code:
```
claude mcp add --scope user artbench -e PYTHONPATH=<Artbench> -- python -m artbench.mcp_server
```
Gemini CLI (`~/.gemini/settings.json`):
```
{"mcpServers": {"artbench": {"command": "python", "args": ["-m", "artbench.mcp_server"],
                           "env": {"PYTHONPATH": "<Artbench>"}}}}
```
Codex (`~/.codex/config.toml`):
```
[mcp_servers.artbench]
command = "python"
args = ["-m", "artbench.mcp_server"]
env = { PYTHONPATH = "<Artbench>" }
```

**Güncellemeden sonra:** Artbench'in çalışan her sürecini yeniden başlat: sayfanın sunucusu ve her yapay zekâ
CLI'ındaki MCP sunucusu (CLI'ı kapatıp açmak yeter). Eski sürümle yeni sürüm aynı projeye birlikte yazmamalı; proje
kilidi sürümler arasında değişti.

## Komut satırı ve yerel API
MCP konuşamayan araçlar ve betikler aynı işlemleri komut satırından çağırır (sonuç JSON):
```
python -m artbench ops
python -m artbench call scene_inventory --project demo
python -m artbench call send --project demo --arg id=FBX/Props/Crate/Crate.fbx --json-args "{\"files\": [\"FBX/Props/Crate/Crate_BaseColor.png\"]}"
```
Çıkış kodu 0 başarı, 1 işlem hatası (hata JSON olarak yazılır), 2 kullanım hatası. Sunucu açıkken aynı işlemler
`http://127.0.0.1:8765/api/v1/<işlem>` adresinden de çağrılır (Blender eklentisi bugün bunu kullanır, Unity köprüsü
de kullanacak); sözleşme `ARCHITECTURE.md`'de.
Köprünün göndereceği sahne raporunun şeması `docs/contracts/engine_report.v1.schema.json`. 64 MB'tan büyük
istekler okunmadan reddedilir (413).

## Veriler (art klasöründe)
`inventory.json` notlar, `tasks.json` görevler, `inventory_history.log` geçmiş, `engine_index.json` motor dökümü,
`engine_index_stale.json` Unity köprüsünün "döküm eskidi" işareti (köprü bir import bildirdiğinde yazılır).
Önbellekler (`.hash_cache.json`, `.unity_dump_cache.json`, Blender çıktıları için `.cache/<tür>/`) Artbench klasöründe
kalır. Oyun projesi modundaki projelerin ayarları ve dosyaları (görevler, geçmiş, değişiklik akışı) Artbench klasöründe
`projects/<id>/` altında durur; oyun projesine hiçbir şey yazılmaz.

## Geliştirme
Katmanlar ve şemalar `ARCHITECTURE.md`'de. Yerleşim kuralları açınca projeden öğrenilir ve `layout_rules` olarak
yazılır; elle de düzenlenebilir.

## Windows paketini üretmek
`Build.bat`'a çift tıkla (ya da `python tools/build_portable.py`): kendi Python'unu taşıyan
`dist\Artbench-<sürüm>-windows-x64.zip` oluşur ve `dist` klasörü açılır. Yayınlamak için `artbench/__init__.py`'deki
sürümü ayarla ve aynı sürümle bir etiket gönder (`git tag v0.1.1`, `git push origin v0.1.1`): GitHub paketi Windows'ta
kurar, dener ve Releases sayfasına koyar. İndirme sayfası (https://artbench.malik3d.page/, kaynağı `site/`)
her yayından sonra yeni zip'i gösterecek şekilde GitHub Pages ile kendiliğinden güncellenir.

## Lisans
Kendi işin için kullanabilir, değiştirebilir ve paylaşabilirsin; atıf yapman yeter ("Artbench by Zeatrex01"). Satılamaz.
Resmi hali: Commons Clause'lu Apache-2.0 (`LICENSE`, `NOTICE`); Blender eklentisi yalnızca Apache-2.0.
