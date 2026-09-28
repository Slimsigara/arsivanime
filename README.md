# Arşivanime — TürkAnime TV 2018 / 2021 Arşiv Portalı

## Proje Hakkında

Türkanime'nin eski websitesinin Wayback Machine kayıtları ile kullanılabilir hale getirilmiş halidir.
2018 ve 2021 temaları arasında geçiş yapabilir ve kullanabilirsiniz.

### **⚠️Kişisel olarak kullanım için yapılmıştır ve yayınlanmıştır. Projeyi alıp başka bir amaç için kullanmak için TASARLANMAMIŞTIR. Arşiv amacıyla kullanılmalıdır.⚠️**

---

## Özellikler
- Website tamamen orijinal halindedir. Neredeyse hiçbir değişiklik **kasıtlı olarak** yapılmamıştır.
- Proje localde çalışmaya uygun haldedir ve bunun için tasarlanmıştır. 

### Anime & Bölüm Arşivi
- **6.107 Anime:** TV dizileri, OVA'lar, Filmler ve Özel bölümler.
- **71.694 Bölüm:** Eksiksiz bölüm indeksleri ve adlandırmaları.
- **1.164.775 Video Oynatıcı Linki:**
- **Fansub Grupları & Çevirmenler:** Hangi bölümü hangi fansub grubunun ve çevirmenin hazırladığına dair detaylı künye bilgileri.

---

## Teknik Kısım

| Alan | Kullanılan Teknoloji / Kütüphane | Açıklama |
| :--- | :--- | :--- |
| **Backend** | Python 3 (Saf Standart Kütüphane) | Harici hiçbir `pip` paketine ihtiyaç duymaz (`http.server`, `threading`, `sqlite3`, `json`). |
| **Veritabanı** | SQLite 3 (`.db`) | İndeksli ve tam metin arama (FTS) destekli ilişkisel veritabanı. |
| **Platform** | Platform Bağımsız (Cross-Platform) | Windows, Linux ve macOS üzerinde sıfır yapılandırmayla çalışır. |

---

## Kurulum ve Çalıştırma

Bu projenin en büyük avantajı, **harici hiçbir bağımlılık (pip install) gerektirmemesidir**. Bilgisayarınızda **Python 3.8 veya üzeri** bir sürümün kurulu olması yeterlidir.

### Windows
1. Depoyu indirin veya klonlayın:
   ```bash
   https://github.com/Slimsigara/arsivanime.git
   ```
2. Klasör içindeki **`baslat.bat`** dosyasına çift tıklayın.
3. Sunucu otomatik olarak başlayacak ve varsayılan internet tarayıcınızda `http://localhost:8000` adresi açılacaktır.

### Linux / macOS
1. Terminali açın ve proje dizinine gidin:
   ```bash
   https://github.com/Slimsigara/arsivanime.git
   cd arsivanime
   ```
2. Başlatma betiğine çalıştırma yetkisi verin ve çalıştırın:
   ```bash
   chmod +x baslat.sh
   ./baslat.sh
   ```
3. Tarayıcınızda otomatik olarak açılacaktır. Açılmazsa adres çubuğuna yazabilirsiniz:
   ```
   http://localhost:8000
   ```

### Manuel Çalıştırma (Tüm Platformlar)
Dilerseniz doğrudan Python ile de başlatabilirsiniz:
```bash
python server.py
# veya
python3 server.py
```

---

### 4. Port Numarasını Değiştirme
Varsayılan olarak `8000` portu kullanılmaktadır. Farklı bir portta çalıştırmak isterseniz:
`server.py` dosyasının en altındaki fonksiyon çağrısını güncelleyin:
```python
if __name__ == "__main__":
    run_server(port=8080) # 8000 yerine istediğiniz port
```

### Bilinen Sorunlar
- Günlük anime önerisi kısmı şu anlık çalışmıyor.
---


## 🔒 Lisans ve Feragatname

- Bu proje **kâr amacı gütmeyen**, Türk anime kültürünün nostaljisini ve geçmiş arayüz tasarımlarını hatırlatmak amacıyla geliştirilmiş bir arşiv ve araştırma projesidir.
- Sitede yer alan video player linkleri üçüncü taraf sunucularda barınmaktadır; proje yerel olarak herhangi bir video dosyası barındırmaz.
- TürkAnime TV markası, logoları ve orijinal tasarımları hak sahiplerine aittir.
- Proje üzerinde hakkım olan şeyler arşivleri birleştirip çalışır hale getirebilmektir. Bunun dışında hiçbir şey üzerinde hak iddia etmiyorum. Türkanimenin kendisi, veritabanı, video playerlar, çevirmenler, tasarımlar vb. hiçbir şey bana ait değildir. 
- Yaptığım bu projeyi alıp kapalı, kar amacı güten bir websitesine çevirmek arşivciliğe saygısızlıktır. Lütfen bu projeyi sadece arşivleme amaçlı kullanınız.

Bu depoda yer alan içeriklerin tüm hakları kendi sahiplerine aittir. Herhangi bir hak sahibi içeriğin kaldırılmasını talep ederse, depo üzerinden bizimle iletişime geçmesi yeterlidir; ilgili içerik en kısa sürede kaldırılacaktır.

---

## Arşiv Kaynakları

- Projenin veritabanı kısmı [Nutaliaxd/TurkAnimeTV_Arsiv](https://github.com/Nutaliaxd/TurkAnimeTV_Arsiv) projesinden alınmıştır. Ona da emekleri için çok teşekkürler :)

⭐ **Bu projeyi beğendiyseniz GitHub üzerinden yıldız vererek destek olmayı unutmayın!**
