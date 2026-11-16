---
name: yeni-calisan
description: Kullanıcı için yeni bir kalıcı çalışan (worker) tasarlar ve kurar. Görüşme yapar, tasarımı onaylatır, klasörü, iş tanımını, standardı ve başlangıç komutunu oluşturur, ekip listesine ekler. Kullanıcı "/yeni-calisan", "bana şunu yapan bir çalışan aç", "yeni bir editör/asistan kur" dediğinde kullan.
---

# Yeni çalışan kurulumu

Kullanıcının tarifi (boş olabilir): $ARGUMENTS

1. Tarif boşsa tek bir soruyla iste: "Ne iş yapacak bir çalışan istiyorsun? Bir iki cümleyle anlat."
2. `CLAUDE.md`'deki iş akışını uygula: görüşme (en fazla iki tur, sadece eksikleri sor) → tasarım planı → onay → kurulum (`sablonlar/` altındaki şablonlarla) → kontrol → `../EKIP.md` kaydı → teslim.
3. Teslimde çalışanın nasıl başlatılacağını hem terminal hem masaüstü uygulaması için yaz.
