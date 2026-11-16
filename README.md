# Agent Ekip Kiti

Claude Code ile **kalıcı çalışanlardan (worker) oluşan bir ekip** kurmanı ve onları **tek ekrandan izlemeni** sağlayan küçük bir kit. Sadece yerel dosyalardan oluşur: sunucu, hesap, internet bağlantısı ya da veri gönderimi yok.

| Parça | Ne işe yarar |
|---|---|
| **Ekip klasörü** | Her çalışan burada kendi klasöründe yaşar: `CLAUDE.md` (iş tanımı), `STANDART.md` (her işte sabit kalan kurallar), `.claude/skills/<komut>/` (başlangıç komutu). Çalışanın klasöründe Claude Code'u açtığında o rolde işe başlar. |
| **Departmanlar** | Çalışanlar departmanlara ayrılır (ör. `Pazarlama/`, `Destek/`). Her departmanın ortak kuralları `DEPARTMAN.md`'dedir. İsteğe bağlı bir **şef** de olabilir: ona bir konu verirsin, işi parçalara ayırıp çalışanlara dağıtır ve tek bir teslim yapar. |
| **`ORTAK.md`** | Bütün çalışanların ortak kuralları: dil, hitap, sınırlar, tercihler. Her çalışan bunu `@../ORTAK.md` ile kendi iş tanımına ekler. Tek bir yerden bütün ekip güncellenir. |
| **`EKIP.md`** | Ekip listesi: kim, ne yapar, nasıl başlatılır. |
| **Worker Kurucu** | Çalışan kuran çalışan. `/yeni-calisan` yazarsın, seninle kısa bir görüşme yapar, tasarımı onaylatır, yeni çalışanın klasörünü, iş tanımını, standardını ve komutunu kurar, ekip listesine ekler. Departman ve şef de kurar, mevcut çalışanları günceller. |
| **Agent Ofisi** | Tarayıcıda açılan bir pano (`http://localhost:4747`). Her Claude Code oturumu tepeden görünen bir ofiste masasında oturan bir karakter olarak çizilir. Masada o an ne yaptığı (dosya düzenliyor, komut çalıştırıyor, düşünüyor), seni ya da onayını bekleyip beklemediği, ne kadar token harcadığı ve alt agent'ları ("yardımcılar") görünür. Masaya tıklayınca son yaptıkları, en çok kullandığı araçlar ve token dökümü açılır. Terminalde tmux içinde açılan oturumlara **panodan mesaj gönderebilir** ya da onları **durdurabilirsin**. Bir çalışan seni beklemeye geçince isteğe bağlı olarak **sesli uyarı** verir ("… incelemeni bekliyor"). |

---

## Gereksinimler
- **Claude Code** (terminal sürümü `claude` ya da Claude masaüstü uygulamasının Code sekmesi). İkisi de aynı dosyaları okur.
- **Python 3.9+** (sadece standart kütüphane kullanılır, `pip install` gerekmez).
- Windows, macOS ya da Linux.
- İsteğe bağlı: **tmux** (panodan oturuma mesaj göndermek için; Linux ve macOS). Ubuntu: `sudo apt install tmux`, macOS: `brew install tmux`.

## Hızlı kurulum (elle)
Bu klasörde:
```bash
python install.py --name "Adın"
```
macOS ve Linux'ta `python` yerine `python3` yaz. Varsayılan yerler:
- ekip klasörü: `~/AgentTeam`
- Agent Ofisi: `~/AgentTeam/Agent Ofisi`

Başka bir yer istersen:
```bash
python install.py --name "Adın" --team "D:/Ekibim" --prefs "kısa cevap ver;OneDrive kullanma"
```
| Seçenek | Anlamı |
|---|---|
| `--name` | çalışanların sana hitap edeceği ad |
| `--team` | ekip klasörü |
| `--office` | Agent Ofisi klasörü (varsayılan `<ekip>/Agent Ofisi`) |
| `--lang` | çalışanların konuşacağı dil (varsayılan Türkçe) |
| `--address` | hitap ya da ton notu (ör. "Samimi konuş, bana abi de") |
| `--prefs` | bütün ekibin uyacağı tercihler, `;` ile ayrılmış |
| `--port` | Agent Ofisi portu (varsayılan 4747) |
| `--no-hooks` | Claude Code ayarlarına dokunma (bkz. "Hook'lar") |
| `--no-launcher` | `~/.local/bin/ekip` başlatıcısını kurma (Linux ve macOS) |
| `--force` | var olan dosyaları yedekleyip yeniden yaz |
| `--check` | sadece kurulumu kontrol et |
| `--uninstall` | hook'ları ayarlardan kaldır (dosyalar kalır) |

Kurulum var olan dosyaların üzerine yazmaz, tekrar çalıştırmak güvenlidir. Değiştirdiği tek ortak dosya `~/.claude/settings.json` ve önce onun yedeğini alır (`settings.json.yedek-<tarih>`).

## Ubuntu / Linux
Ubuntu 24.04'te (Python 3.12) baştan sona test edildi.
```bash
# zip'i aç (unzip kurulu olmasa da çalışır)
python3 -m zipfile -e agent-team-kit.zip ~/
cd ~/agent-team-kit
python3 install.py --name "Adın"
```
- `python` komutu Ubuntu'da yoktur, her yerde `python3` kullan. Kurulum, hook komutuna ve `baslat.sh`'ye Python'un tam yolunu (`/usr/bin/python3`) yazar.
- Agent Ofisi: `~/AgentTeam/"Agent Ofisi"/baslat.sh` sunucuyu başlatır ve tarayıcıyı `xdg-open` ile açar. Masaüstü ortamı yoksa (SSH) tarayıcı açılmaz. O zaman bilgisayarındaki tarayıcıdan `ssh -L 4747:localhost:4747 <makine>` ile bağlanıp `http://localhost:4747`'yi aç.
- Klasör adlarında boşluk var (`Worker Kurucu`, `Agent Ofisi`). Terminalde tırnakla yaz ya da Tab ile tamamla.
- **İsteğe bağlı: oturum açınca otomatik başlasın** (systemd kullanıcı servisi, yönetici yetkisi gerekmez):
  ```bash
  mkdir -p ~/.config/systemd/user
  cat > ~/.config/systemd/user/agent-ofisi.service <<'EOF'
  [Unit]
  Description=Agent Ofisi (Claude Code panosu)

  [Service]
  WorkingDirectory=%h/AgentTeam/Agent Ofisi
  Environment=OFFICE_PORT=4747
  ExecStart=/usr/bin/python3 server.py
  Restart=on-failure

  [Install]
  WantedBy=default.target
  EOF
  systemctl --user daemon-reload
  systemctl --user enable --now agent-ofisi.service
  ```
  Kapatmak için: `systemctl --user disable --now agent-ofisi.service`. Ekip klasörünü başka bir yere kurduysan `WorkingDirectory`'yi ona göre değiştir.
- **İsteğe bağlı: uygulama menüsünde kısayol:** `~/.local/share/applications/agent-ofisi.desktop` dosyası oluştur. İçine `[Desktop Entry]`, `Type=Application`, `Name=Agent Ofisi`, `Exec=sh -c '"$HOME/AgentTeam/Agent Ofisi/baslat.sh"'` ve `Terminal=false` satırlarını yaz.

## Claude ile kurulum
Bu klasörü hedef bilgisayara kopyala, klasörde Claude Code'u aç ve şunu yaz:
> README'deki "Claude için kurulum talimatı"na göre bu kiti kur.

---

## Claude için kurulum talimatı
*Bu bölüm, kurulumu yapan Claude içindir. Adımları sırayla uygula. Kullanıcıya en fazla bir kez, tek bir soru turuyla soru sor.*

1. **Ortamı kontrol et (soru sormadan):**
   - İşletim sistemi ve Python komutu: Linux ve macOS'ta `python3 --version`, Windows'ta `python --version`. Bundan sonraki bütün komutlarda bulduğun komutu kullan. Zip hâlâ kapalıysa `python3 -m zipfile -e agent-team-kit.zip <hedef>` ile aç, `unzip` gerekmez. 3.9'dan küçükse ya da yoksa dur ve kullanıcıya Python kurmasını söyle (Windows: python.org ya da `winget install Python.Python.3.12`, macOS: `brew install python`, Linux: paket yöneticisi).
   - `claude --version` (yoksa sorun değil, kullanıcı masaüstü uygulamasını kullanıyor olabilir).
   - Linux ve macOS'ta `tmux -V`. Yoksa kurulumdan sonra kullanıcıya panodan mesaj gönderebilmek için `sudo apt install tmux` (macOS: `brew install tmux`) komutunu **kendisinin** çalıştırmasını söyle. `sudo` gerektiren komutları sen çalıştırma.
   - `~/.claude/settings.json` var mı ve geçerli JSON mu? İçinde `hooks` var mı? Varsa kurulum onlara dokunmaz, sadece kendi kayıtlarını ekler.
   - Kurumsal yönetilen ayar dosyası var mı? Windows: `C:\Program Files\ClaudeCode\managed-settings.json` ya da `C:\ProgramData\ClaudeCode\managed-settings.json`. macOS: `/Library/Application Support/ClaudeCode/managed-settings.json`. Linux: `/etc/claude-code/managed-settings.json`. İçinde hook'ları kapatan ya da sadece yöneticinin hook'larına izin veren bir ayar varsa (ör. `disableAllHooks`, `allowManagedHooksOnly`) kullanıcının hook'ları çalışmaz. Bu durumda `--no-hooks` ile kur ve kullanıcıya nedenini söyle. Emin değilsen hook'larla kur, sonra yeni bir oturumda bir mesaj gönderip `<ofis>/events.jsonl`'e satır düşüp düşmediğine bak.
2. **Tek soru turu** (seçenekli soru aracın varsa onu kullan, önerini ilk seçenek yap):
   - Adın ne, çalışanlar sana nasıl hitap etsin?
   - Ekip klasörü nerede olsun? (öneri: ana klasörde `AgentTeam`. Bulutla senkronize edilen klasörleri, örneğin OneDrive, iCloud ya da Dropbox içindeki Masaüstü/Belgeler'i, önerme.)
   - Bütün ekibin uyacağı tercihler var mı? (ör. dil, cevap uzunluğu, kullanılmaması gereken servisler). Yoksa boş bırak.
3. **Kur:**
   ```bash
   python install.py --name "<ad>" --team "<klasör>" [--address "<hitap notu>"] [--prefs "<a;b;c>"] [--no-hooks]
   ```
   Komutun çıktısını oku. Çıkış kodu 0 değilse `✗` satırlarını düzelt ve tekrar çalıştır.
4. **Doğrula:**
   - `python install.py --check --team "<klasör>"` → "HAZIR" görmelisin.
   - Agent Ofisi'ni arka planda başlat (`<ofis>/baslat.bat` ya da `baslat.sh`, veya `python "<ofis>/server.py"`). `http://localhost:4747/api/state` adresinden JSON geldiğini kontrol et (`curl -s` ya da Python ile), sonra sunucuyu kapat. Tarayıcı aracın varsa sayfayı açıp bir ekran görüntüsü al.
5. **Kullanıcıya rapor ver:** nereye ne kuruldu, Agent Ofisi'nin nasıl açılacağı, ilk çalışanın nasıl kurulacağı (aşağıdaki "Kullanım") ve hook'ların yeni açılan oturumlarda devreye gireceği. Ayar dosyasının yedeğini de söyle. Linux ve macOS'ta `ekip` komutunu tanıt (çalışanları tmux içinde açar, böylece panodan mesaj gönderilebilir). `~/.local/bin` PATH'te değilse yeni bir terminal açmasını söyle.
6. Linux'ta kullanıcıya "Ubuntu / Linux" bölümündeki iki isteğe bağlı adımı (oturum açınca otomatik başlatma ve menü kısayolu) öner. Sadece "evet" derse uygula.
7. Kurulumu yaptığın oturum ekip klasörünün dışında. Kullanıcı ilk çalışanını kurmak isterse `Worker Kurucu` klasöründe **yeni bir oturum** açmasını söyle (ya da masaüstü uygulamasında oturum başlatma aracın varsa onu kullan).

---

## Kullanım

### İlk çalışanını kur
Linux ve macOS:
```bash
ekip "Worker Kurucu"
```
Windows ya da `ekip` olmadan:
```bash
cd ~/AgentTeam/"Worker Kurucu"
claude
```
Sonra şunu yaz:
```
/yeni-calisan bana pull request'leri ekip standardımıza göre inceleyen bir çalışan aç
```
Worker Kurucu en fazla iki tur soru sorar, tasarımı tek bir planda gösterir. Sen onaylayınca örneğin `~/AgentTeam/PR Inceleyici/` klasörünü kurar ve `EKIP.md`'ye ekler.

### Bir çalışanı çalıştır
- **Terminal, `ekip` ile (önerilen, Linux ve macOS):** `ekip "<Çalışan Adı>"` çalışanı kendi tmux oturumunda açar. Zaten açıksa o oturuma bağlanır, tmux'un içindeysen yeni bir pencere açar. Böylece panodan mesaj gönderebilirsin. `ekip` tek başına çalışan listesini gösterir. İlk mesajı da verebilirsin: `ekip "Worker Kurucu" "/yeni-calisan bana ... aç"`.
- **Terminal, elle:** `cd ~/AgentTeam/"<Çalışan Adı>"`, sonra `claude`, sonra çalışanın başlangıç komutu (ör. `/incele`)
- **Claude masaüstü uygulaması:** Code sekmesi → yeni oturum → çalışma klasörü olarak çalışanın klasörünü seç → başlangıç komutu

İlk açılışta Claude Code, `@../ORTAK.md` içe aktarımı proje klasörünün dışında olduğu için bir kez onay isteyebilir. Onay vermen gerekiyor.

### Departmanlar ve şef
```
AgentTeam/
  ORTAK.md, EKIP.md, Worker Kurucu/
  Pazarlama/                ← departman
    DEPARTMAN.md            ← departmanın işi, ortak standardı, çalışan tablosu
    isler/                  ← şefin iş kayıtları
    Pazarlama Şefi/         ← şef (/yeni-is)
    Metin Yazarı/  Görsel Tasarımcı/  ...
```
- Departman açmak için Worker Kurucu'ya söyle: *"Pazarlama diye bir departman aç, içine metin yazarı ve görsel tasarımcı koy, bir de şef olsun."* Yeni çalışanı açarken de hangi departmana gireceğini sorar.
- Departman çalışanları hem `ORTAK.md`'yi hem `DEPARTMAN.md`'yi okur (`@../../ORTAK.md`, `@../DEPARTMAN.md`). Departmanın bütün çalışanlarının uyacağı marka, palet, font ve ton gibi kurallar `DEPARTMAN.md`'ye yazılır.
- **Şefi kullanmak:** `ekip "Pazarlama/Pazarlama Şefi" "/yeni-is yeni ürün lansmanı için içerik hazırla"`. Şef şunları yapar:
  1. İşi alt işlere böler.
  2. Kimin neyi, nasıl ve hangi sırayla yapacağını tek bir planda gösterir ve senden tek onay alır.
  3. İşleri dağıtır:
     - **Yardımcı:** kısa ve soru gerektirmeyen işler şefin kendi oturumunda alt agent olarak yapılır, hızlı biter.
     - **Ayrı oturum:** uzun ya da senin onayını isteyen işler çalışanın kendi oturumunda açılır. Masaüstü uygulamasında yeni bir oturum, terminalde `ekip` ile yeni bir tmux penceresi açılır. Bu oturumlar Agent Ofisi'nde ayrı masalarda görünür.
  4. İlerlemeyi `isler/<tarih>-<konu>.md` dosyasında takip eder ve sonunda tek bir teslim raporu verir.
- `ekip` tek başına bütün ekibi departmanlarıyla listeler.

### Agent Ofisi
`<ofis>/baslat.bat` (Windows) ya da `<ofis>/baslat.sh` (macOS/Linux) tarayıcıda `http://localhost:4747`'yi açar. Pano bütün Claude Code oturumlarını gösterir: terminal, masaüstü uygulaması, hangi klasörde olursa olsun. Masalar yan yana **odalar** (kartlar) halinde gruplanır, böylece bütün ekip tek ekranda görünür: **Yönetim** (Worker Kurucu gibi departmansız çalışanlar), her departman için bir oda (o an kimse çalışmıyorsa da görünür) ve en altta **ekip dışı oturumlar**. Masadaki 👤 çalışanın adını gösterir. **Çalışanlar her zaman görünür:** o an oturumu açık olmayan bir çalışan kendi odasında soluk, boş bir masada durur. Masada adı, başlangıç komutu ve son görülme zamanı yazar. Tıklayınca nasıl mesaiye çağrılacağı ve son oturumları açılır. Ekip klasörünü pano `<ofis>/ofis.json`'dan okur (kurulum yazar) ya da `OFFICE_TEAM` ortam değişkeninden alır.

| İşaret | Anlamı |
|---|---|
| eller klavyede, ekran akıyor | **Çalışıyor**: balonda o anki iş yazar |
| mavi ••• rozeti | **Düşünüyor** |
| turuncu ! rozeti | **Seni bekliyor**: cevabını verdi, sıra sende. Beklerken boş durmaz: ya masasında 📱 reels kaydırır ya da odanın ☕ kahve köşesine gider (birkaç dakikada bir değişir). Köşede iki kişi olunca sohbet ederler. Masa ile köşe arasında yürürler, mesaj gelince masalarına koşarlar (yol çapraz değil: önce yatay, sonra dikey). Rozet her durumda masada kalır. |
| kırmızı ? rozeti | **Onay bekliyor**: bir izin ya da sorunun cevabı bekleniyor |
| zZz | **Boşta** (1 saatten uzun süredir hareket yok) |
| masanın yanındaki küçük karakterler | alt agent'lar (yardımcılar) |

- **Etkin token:** Önbellekten okunan token ×0,1, önbelleğe yazılan ×2, çıktı ×5 ağırlıkla sayılır. Gerçek maliyete yakın bir karşılaştırma ölçüsüdür, fatura değildir.
- **Limit kartları (isteğe bağlı):** Pano `<ofis>/usage.json` dosyası varsa plan limitlerini (5 saatlik, haftalık) gösterir, aradaki süreyi de token tüketiminden tahmin eder (≈ işareti). Claude masaüstü uygulamasında herhangi bir çalışana "limitleri güncelle" demen yeterli, `ORTAK.md`'deki talimata göre dosyayı yazar. Terminalde limitler için Claude Code'un `/usage` komutunu kullan.
- Port değiştirmek için: `OFFICE_PORT=5050`. Kaç saat geriye bakılacağı için: `OFFICE_HOURS=24` (varsayılan 168 saat).

### Sesli uyarı
Üst bardaki **🔕 Sesli uyarı** düğmesiyle açılır ve kapanır. Seçim tarayıcıda hatırlanır. Açıkken bir çalışan senden cevap beklemeye geçtiğinde kısa bir zil çalar, ardından sesli bir cümle okunur:
- **Seni bekliyor** → "*Worker Kurucu* incelemeni bekliyor"
- **Onay bekliyor** → "*Worker Kurucu* onayını bekliyor"

Ad, çalışanın klasör adıdır. Aynı çalışan için 20 saniyede en fazla bir uyarı verilir. Bekleyen çalışan sayısı sekme başlığında da görünür, ör. "(2) Agent Ofisi". **▶** düğmesi sesi dener.
- Tarayıcılar sesi ancak sayfada bir tıklamadan sonra çalmaya izin verir. Sayfayı yeniden açtığında düğme "Sesi etkinleştirmek için tıkla" der. Sayfada herhangi bir yere bir kez tıklaman yeterli.
- Konuşma tarayıcının kendi sesiyle (Web Speech API) yapılır, internet ya da ek program gerekmez. Bir Türkçe ses varsa o kullanılır (Windows'ta genelde "Microsoft Tolga", Chrome'da "Google Türkçe").
- **Ubuntu:** Chrome'un Türkçe sesi genelde vardır. Firefox sesleri sistemden alır. Ses yoksa `sudo apt install speech-dispatcher espeak-ng` komutunu çalıştırıp tarayıcıyı yeniden başlat. Hiç ses bulunamazsa sadece zil çalar.
- Pano sekmesi arka planda olsa da uyarı çalışır, yeter ki sekme açık olsun.

### Mesaiyi bitirme, masayı kaldırma, işten çıkarma
**Çalışan** kalıcıdır (klasörü), **oturum** onun bir mesaisidir. Pano ikisi için ayrı işlemler sunar:
- **Mesaiyi bitir** (oturum panelinde, mesaj kutusunun yanında): oturuma önce Esc, sonra `/exit` gönderir, Claude Code kapanır. Çalışan ve dosyaları yerinde kalır. Sadece tmux içinde açılmış terminal oturumlarında çalışır. Masaüstü uygulamasındaki oturumları uygulamanın kenar çubuğundan arşivle.
- **Masadan kaldır** (oturum panelinde): kapanmış ya da boştaki bir oturumun masasını panodan gizler. Oturum silinmez. Üst bardaki 🗄️ **Arşiv** → "Hepsini geri getir" ile geri gelir. Gizlenenler `<ofis>/gizli-masalar.json`'da tutulur.
- **İşten çıkar** (boş masaya tıklayınca açılan çalışan panelinde): çalışanın klasörünü ekip klasöründeki `_Arşiv/` altına taşır, `DEPARTMAN.md` ve `EKIP.md` tablolarından satırını çıkarır, panoda artık görünmez. **Silinmez:** 🗄️ Arşiv → "Geri al" klasörü eski yerine taşır ve tablo satırlarını eski yerlerine geri koyar.
  - Mesaideki bir çalışan (son 6 saatte kapanmamış oturumu olan, seni bekleyenler dahil) çıkarılamaz. Önce mesaisini bitir.
  - Worker Kurucu çıkarılamaz.
  - Windows'ta klasörü kullanan açık bir program varsa taşıma yapılmaz ve nedeni gösterilir.
- Bütün bu işlemler mesaj gönderme ile aynı korumayı kullanır: sadece `127.0.0.1`, sayfaya gömülü anahtar ve yalnızca ekip klasörü içindeki gerçek çalışan klasörleri.

### Panodan oturuma mesaj gönderme
Bir masaya tıkla, açılan panelde **"Bu oturuma yaz"** kutusu var.
- **Gönder** (ya da Ctrl+Enter): mesaj o oturumun terminaline yazılır ve Enter'a basılır. Sen klavyeden yazmışsın gibi olur. Claude o an çalışıyorsa mesaj sıraya girer ve işi bitince okunur. Çok satırlı mesajlar tek parça gider.
- **Durdur (Esc):** oturuma Esc tuşu gönderir, yani Claude'un o anki işini durdurur.
- **Şartı:** oturum terminalde, **tmux içinde** açılmış olmalı. En kolayı `ekip "<Çalışan Adı>"` ile açmak. İstersen kendin `tmux` açıp içinde `claude` da çalıştırabilirsin, ikisi de olur. Oturum başlarken hook hangi tmux panelinde olduğunu kaydeder, pano mesajı o panele yazar (`tmux paste-buffer` ve `send-keys`).
- **Çalışmadığı durumlar:** Claude masaüstü uygulamasındaki oturumlar (mesajı uygulamadan gönder), tmux dışında açılmış terminal oturumları ve Windows'taki yerel terminal (tmux yok; WSL içinde çalışır). Bu durumlarda kutu kapalı görünür ve nedeni yazar.
- **Güvenlik:** Mesaj ucu sadece `127.0.0.1`'de dinler. Başka sitelerden ve sahte adreslerden (DNS rebinding) gelen istekleri reddeder. Her sunucu açılışında değişen ve sadece panonun kendi sayfasına gömülen bir anahtar ister. Yani tarayıcında açık başka bir site senin adına oturumlarına mesaj gönderemez. Pano, kendi sayfası dışında hiçbir dosya sunmaz.

### Hook'lar
Kurulum `~/.claude/settings.json`'a beş olay ekler: `SessionStart`, `Notification`, `Stop`, `UserPromptSubmit`, `SessionEnd`. Her olay `hook.py` ile `<ofis>/events.jsonl` dosyasına tek bir satır yazar (zaman, oturum kimliği, olay adı, bildirim metni, `SessionStart`'ta ayrıca tmux paneli). Bu sayede pano "onay bekliyor" ve "seni bekliyor" durumlarını anında görür ve mesajı hangi panele yazacağını bilir.
- Hook her zaman sıfır kodla çıkar, yani Claude'u asla durdurmaz ya da yavaşlatmaz (en fazla 5 sn zaman aşımı).
- `events.jsonl` 5 MB'ı geçince kendini kırpar.
- Hook'lar olmadan da pano çalışır, sadece "onay bekliyor" durumunu ayırt edemez ve mesaj gönderemez.
- Kaldırmak için: `python install.py --uninstall`

## Gizlilik
- Her şey yerel. Pano sadece `~/.claude/projects/**/*.jsonl` (Claude Code'un kendi oturum kayıtları) ve `events.jsonl` dosyalarını okur, sadece `127.0.0.1`'de dinler, dışarıya hiçbir şey göndermez.
- Pano oturum kayıtlarından son mesaj ve araç özetleri gösterir. Ekranını paylaşırken buna dikkat et.
- İş bilgisayarında: şirket verisini ve kodunu kişisel yedeklere taşıma. Bu kit sadece kurallar ve şablonlardan oluşur.

## Kaldırma
```bash
python install.py --uninstall      # hook'ları ayarlardan çıkarır
```
Sonra ekip ve ofis klasörlerini istersen elle sil.

## Sorun giderme
| Belirti | Çözüm |
|---|---|
| Panoda "sunucuya ulaşılamıyor" | Ofis sunucusu kapalı: `baslat.bat` ya da `baslat.sh`'yi çalıştır. Port doluysa `OFFICE_PORT` ile değiştir. |
| Panoda hiç masa yok | Son 24 saatte oturum yok. Sağ üstteki seçiciden "son 7 gün"ü seç. |
| "canlı olaylar kapalı" yazıyor | Henüz hiçbir hook çalışmadı. Yeni bir Claude Code oturumu aç ve bir mesaj gönder. Hâlâ kapalıysa `python install.py --check` çalıştır, kurumsal ayarlar hook'ları kapatmış olabilir. |
| `/yeni-calisan` komutu görünmüyor | Claude Code'u `Worker Kurucu` klasörünün **içinde** açtığından emin ol. |
| Çalışan ortak kuralları bilmiyor | İlk açılışta "dış dosya içe aktarımı" onayını vermemiş olabilirsin. Oturumu yeniden aç ve onay ver. |
| Hook'lar Windows'ta çalışmıyor | `settings.json`'daki komutta Python'un tam yolu var. Python'u taşıdıysan ya da güncellediysen kurulumu tekrar çalıştır. |
| Mesaj kutusu kapalı: "tmux içinde açılmamış" | Oturumu `ekip "<Çalışan Adı>"` ile ya da tmux içinde `claude` ile yeniden aç. Kurulumdan **önce** açılmış oturumların paneli kayıtlı değildir. |
| Mesaj kutusu kapalı: "panel artık yok" | O terminal ya da tmux oturumu kapanmış. Çalışanı yeniden aç. |
| `ekip: command not found` | `~/.local/bin` PATH'te değil. Yeni bir terminal aç ya da `~/.profile`'a `export PATH="$HOME/.local/bin:$PATH"` ekle. |
| Mesaj gitti ama Claude göndermedi | Claude bir onay ekranında bekliyordu ve mesaj o ekrana yazıldı. Terminale geçip onay ekranını kapat. Durdur (Esc) da işe yarar. |

## Klasör yapısı
```
agent-team-kit/
  README.md            ← bu dosya
  install.py           ← kurulum, kontrol ve kaldırma
  office/              ← Agent Ofisi: server.py, index.html, hook.py
  team/
    ORTAK.md.sablon    ← ortak kurallar şablonu (kurulumda doldurulur)
    EKIP.md.sablon     ← ekip listesi şablonu
    Worker Kurucu/     ← çalışan kuran çalışan (CLAUDE.md, .claude/skills/yeni-calisan/,
                         sablonlar/: çalışan, standart, komut, departman ve şef şablonları)
```
