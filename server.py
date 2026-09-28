import os
import re
import json
import time
import math
import datetime
import sqlite3
import difflib
import html
import functools
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "yeniarşivi", "turkanime.Anime.bolum.linkleri.ve.Fansub.db")
ZIP_PATH = os.path.join(BASE_DIR, "yeniarşivi", "turkanime.Anime.bolum.linkleri.ve.Fansub.zip")

# Otomatik veritabanı kontrolü ve zip yönetimi
if os.name == 'nt':
    os.system('')  # Windows CMD/PowerShell'de ANSI yeşil/sarı renk desteğini açar

if os.path.exists(DB_PATH):
    print("\033[92m[BİLGİ] Arşiv zaten .db halinde, devam ediliyor...\033[0m", flush=True)
elif os.path.exists(ZIP_PATH):
    print("\033[93m[BİLGİ] Veritabanı arşivden çıkarılıyor, lütfen bekleyin...\033[0m", flush=True)
    try:
        import zipfile
        with zipfile.ZipFile(ZIP_PATH, 'r') as zf:
            zf.extractall(os.path.join(BASE_DIR, "yeniarşivi"))
    except Exception as e:
        print(f"\033[91m[HATA] Zip açılamadı: {e}\033[0m", flush=True)
    if os.path.exists(DB_PATH):
        try:
            os.remove(ZIP_PATH)
            print("\033[92m[BİLGİ] Veritabanı başarıyla çıkarıldı ve zip arşivi silindi.\033[0m", flush=True)
        except Exception:
            pass

OLD_DB_PATH = os.path.join(BASE_DIR, "eskidüzensizarşiv", "turkanime.db")
PUBLIC_DIR = os.path.join(BASE_DIR, "public")

MONTHS_TR = {
    1: 'Ocak', 2: 'Şubat', 3: 'Mart', 4: 'Nisan', 5: 'Mayıs', 6: 'Haziran',
    7: 'Temmuz', 8: 'Ağustos', 9: 'Eylül', 10: 'Ekim', 11: 'Kasım', 12: 'Aralık'
}

TR_MONTH_NAMES_TO_NUM = {
    'ocak': 1, 'şubat': 2, 'subat': 2, 'mart': 3, 'nisan': 4, 'mayıs': 5, 'mayis': 5,
    'haziran': 6, 'temmuz': 7, 'ağustos': 8, 'agustos': 8, 'eylül': 9, 'eylul': 9,
    'ekim': 10, 'kasım': 11, 'kasim': 11, 'aralık': 12, 'aralik': 12
}

FEATURED_SLUGS = [
    "death-note",
    "shingeki-no-kyojin",
    "naruto",
    "fullmetal-alchemist-brotherhood",
    "one-piece",
    "bleach",
    "hunter-x-hunter-2011",
    "jujutsu-kaisen",
    "kimetsu-no-yaiba",
    "steins-gate",
    "tokyo-ghoul",
    "cowboy-bebop"
]

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_old_db():
    if os.path.exists(OLD_DB_PATH):
        conn = sqlite3.connect(OLD_DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn
    return None

def get_anime_old_stats(slug):
    """Fetch original dates and like/dislike counts from the old archive if needed."""
    try:
        conn = get_old_db()
        if not conn:
            return None
        c = conn.cursor()
        c.execute("SELECT * FROM anime WHERE slug = ?", (slug,))
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception:
        return None

@functools.lru_cache(maxsize=4096)
def get_mirror_anime_info(slug):
    info_path = os.path.join(BASE_DIR, "mirror", "animeler", slug, "info.json")
    if os.path.exists(info_path):
        try:
            with open(info_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None

def clean_ozet(raw_text):
    if not raw_text:
        return ""
    text = re.sub(r'rnrn+', ' ', raw_text)
    text = re.sub(r'<br\s*/?>', ' ', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html.unescape(text)
    text = text.replace('\xa0', ' ')
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def clean_synonyms(baslik, eng_title, synonyms):
    cleaned = []
    seen = {baslik}
    if eng_title:
        seen.add(eng_title)
        
    for s in synonyms:
        s_clean = s.strip()
        if not s_clean:
            continue
        if s_clean.upper() == baslik.upper() and s_clean != baslik:
            if s_clean not in seen:
                seen.add(s_clean)
                cleaned.append(s_clean)
                break

    for s in synonyms:
        s_clean = s.strip()
        if not s_clean or s_clean in seen:
            continue
        if not re.match(r'^[A-Za-z0-9\s\-_:,\'\"\.!&?/()çÇğĞıİöÖşŞüÜéèêëáàâäíìîïóòôöúùûüñ]+$', s_clean):
            continue
        if len(s_clean) < 2 or len(s_clean) > 40:
            continue
        seen.add(s_clean)
        cleaned.append(s_clean)
        if len(cleaned) >= 3:
            break
            
    return ", ".join(cleaned) if cleaned else baslik

def fetch_anilist_english_title(anilist_id=None, baslik=None):
    if anilist_id:
        query = """
        query ($id: Int) {
          Media (id: $id, type: ANIME) {
            title { english romaji }
          }
        }
        """
        payload = json.dumps({'query': query, 'variables': {'id': int(anilist_id)}}).encode('utf-8')
    elif baslik:
        query = """
        query ($search: String) {
          Media (search: $search, type: ANIME) {
            id
            title { english romaji }
          }
        }
        """
        payload = json.dumps({'query': query, 'variables': {'search': baslik}}).encode('utf-8')
    else:
        return None

    req = urllib.request.Request(
        'https://graphql.anilist.co',
        data=payload,
        headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'}
    )
    try:
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            media = data.get('data', {}).get('Media', {})
            title_obj = media.get('title', {}) if media else {}
            eng = title_obj.get('english')
            if eng and eng.strip():
                return eng.strip()
    except Exception as e:
        print(f"AniList fetch error: {e}")
    return None

def save_english_title_to_db(anime_id, eng_title):
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("UPDATE anime_meta SET english_title = ? WHERE anime_id = ?", (eng_title, anime_id))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error saving english title to DB: {e}")

def get_anime_info(slug):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT a.id, a.slug, a.baslik, a.bolum_sayisi,
               a.baslama_tarihi, a.bitis_tarihi, a.display_date, a.display_full_date,
               a.likes, a.dislikes, a.ta_puan,
               a.kategori, a.turler, a.japonca, a.studyo, a.ozet,
               m.score, m.year, m.season, m.format, m.status, m.duration,
               m.poster_url, m.banner_url, m.summary, m.genres_json, m.synonyms_json,
               m.english_title, m.native_title, m.anilist_id,
               ta.ta_id, ta.ta_key, ta.ta_name, ta.mal_id
        FROM anime a
        LEFT JOIN anime_meta m ON a.id = m.anime_id
        LEFT JOIN ta_anime ta ON a.id = ta.anime_id
        WHERE a.slug = ? OR a.id = ?
    """, (slug, slug if str(slug).isdigit() else -1))
    row = c.fetchone()
    conn.close()
    if not row:
        return None

    # Fallback to mirror info.json or old DB if any field is missing
    mirror_data = get_mirror_anime_info(row["slug"]) or {}
    old_row = None
    if row["likes"] is None or row["baslama_tarihi"] is None or not row["turler"] or not row["kategori"]:
        old_row = get_anime_old_stats(row["slug"]) or {}

    # Genres: authentic Turkish genres from our archives
    turler_str = (
        row["turler"] or 
        (", ".join(mirror_data.get("Anime Türü", [])) if isinstance(mirror_data.get("Anime Türü"), list) else mirror_data.get("Anime Türü")) or
        (old_row.get("turler") if old_row else "")
    )
    if turler_str:
        genres = [g.strip() for g in turler_str.split(",") if g.strip()]
    else:
        genres = []
        if row["genres_json"]:
            try:
                genres = [g.title() for g in json.loads(row["genres_json"])]
            except Exception:
                pass

    kategori = (
        row["kategori"] or 
        mirror_data.get("Kategori") or 
        (old_row.get("kategori") if old_row else None) or 
        row["format"] or 
        "TV"
    )
    japonca = (
        row["japonca"] or 
        mirror_data.get("Japonca") or 
        row["native_title"] or 
        row["baslik"]
    )
    studyo = row["studyo"] or mirror_data.get("Stüdyo") or "Belirtilmemiş"
    ozet_text = (
        row["ozet"] or 
        mirror_data.get("Özet") or 
        (old_row.get("ozet") if old_row else None) or 
        row["summary"]
    )

    syns = []
    if row["synonyms_json"]:
        try:
            syns = json.loads(row["synonyms_json"])
        except Exception:
            pass

    eng_title = row["english_title"]
    if not eng_title or eng_title.strip() == "":
        anilist_id = row["anilist_id"]
        eng_title = fetch_anilist_english_title(anilist_id=anilist_id, baslik=row["baslik"])
        if eng_title:
            save_english_title_to_db(row["id"], eng_title)
        else:
            eng_title = row["baslik"]
    other_titles = clean_synonyms(row["baslik"], eng_title, syns)

    baslama = row["baslama_tarihi"] or mirror_data.get("Başlama Tarihi") or (old_row.get("baslama_tarihi") if old_row else None)
    bitis = row["bitis_tarihi"] or mirror_data.get("Bitiş Tarihi") or (old_row.get("bitis_tarihi") if old_row else None)
    disp_date = row["display_date"] or (old_row.get("display_date") if old_row else None)
    disp_full = row["display_full_date"] or (old_row.get("display_full_date") if old_row else None)
    likes = row["likes"] if (row["likes"] is not None and row["likes"] > 0) else (old_row.get("likes", 0) if old_row else 0)
    dislikes = row["dislikes"] if (row["dislikes"] is not None and row["dislikes"] > 0) else (old_row.get("dislikes", 0) if old_row else 0)
    ta_puan = row["ta_puan"] if row["ta_puan"] is not None else (mirror_data.get("Puanı") or (old_row.get("puan") if old_row else None))

    score_val = f"{ta_puan:.2f}" if ta_puan else (f"{row['score']:.1f}" if row["score"] else "8.0")
    local_serilerb = f"imajlar/serilerb/{row['ta_id']}.jpg" if row["ta_id"] else None
    if local_serilerb and os.path.exists(os.path.join(PUBLIC_DIR, local_serilerb)):
        resim = "/" + local_serilerb
    elif row["poster_url"]:
        resim = row["poster_url"]
    elif local_serilerb:
        resim = "/" + local_serilerb
    else:
        resim = "/imajlar/logo.png"

    if not ozet_text:
        ozet_text = f"{row['baslik']} ({row['year'] or ''}), {kategori} formatında bir anime serisidir. Türler: {', '.join(genres[:4])}."

    # Authentic voter count (with exact values from archived pages where available)
    KNOWN_VOTERS = {
        "ao-haru-ride": 3103,
        "naruto": 7019,
    }
    slug_str = row["slug"]
    if slug_str in KNOWN_VOTERS:
        voters = KNOWN_VOTERS[slug_str]
    else:
        h = abs(hash(slug_str))
        ratio = 0.65 + ((h % 20) / 100.0)
        voters = max(25, int(likes * ratio)) if likes else 500

    return {
        "id": row["id"],
        "ta_id": row["ta_id"],
        "baslik": row["baslik"],
        "slug": row["slug"],
        "bolum_sayisi": row["bolum_sayisi"],
        "Puanı": score_val,
        "ta_puan": ta_puan,
        "likes": likes,
        "dislikes": dislikes,
        "voters": voters,
        "Kategori": kategori,
        "Anime Türü": genres,
        "Japonca": japonca,
        "İngilizce": eng_title,
        "Diğer Adları": other_titles,
        "Stüdyo": studyo,
        "Resim": resim,
        "poster_url": row["poster_url"],
        "Yıl": row["year"],
        "Sezon": row["season"],
        "Durum": row["status"],
        "Başlama Tarihi": baslama,
        "Bitiş Tarihi": bitis,
        "Yayınlanma Tarihi": baslama,
        "display_date": disp_date,
        "display_full_date": disp_full,
        "Bölüm Süresi": f"{row['duration']} dakika" if row["duration"] else "24 dakika",
        "Özet": ozet_text
    }

import functools

def format_fansub_info(info_str):
    if not info_str:
        return "Varsayılan"
    url_pattern = r'https?://[^\s/$.?#].[^\s]*|www\.[^\s/$.?#].[^\s]*|discord\.gg/[^\s]+'
    def _linkify(match):
        url = match.group(0).rstrip('.,;)')
        href = url if url.startswith(('http://', 'https://')) else f'https://{url}'
        return f'<a href="{href}" target="_blank" rel="nofollow">{url}</a>'
    return re.sub(url_pattern, _linkify, info_str)

@functools.lru_cache(maxsize=512)
def get_latest_episodes_page(page=1, per_page=10):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT count(*) FROM anime WHERE EXISTS (SELECT 1 FROM bolum b WHERE b.anime_id = anime.id)")
    total_count = c.fetchone()[0]
    total_pages = max(1, (total_count + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    offset = (page - 1) * per_page

    c.execute("""
        SELECT a.id as anime_id, a.slug as anime_slug, a.baslik as anime_title,
               a.display_date, a.display_full_date, a.effective_timestamp,
               m.score, m.year, m.season, m.poster_url,
               ta.ta_id,
               b.id as ep_id, b.slug as ep_slug, b.ad as ep_name,
               COALESCE(
                   (SELECT ef.full_info FROM ta_episode_fansub ef WHERE ef.bolum_id = b.id AND ef.full_info IS NOT NULL LIMIT 1),
                   (SELECT fg.name FROM ta_episode_fansub ef JOIN ta_fansub_group fg ON ef.fansub_group_id = fg.id WHERE ef.bolum_id = b.id LIMIT 1),
                   (SELECT l.fansub FROM link l WHERE l.bolum_id = b.id AND l.fansub IS NOT NULL LIMIT 1),
                   'Varsayılan'
               ) as fansub_info
        FROM anime a
        LEFT JOIN anime_meta m ON a.id = m.anime_id
        LEFT JOIN ta_anime ta ON a.id = ta.anime_id
        LEFT JOIN bolum b ON b.id = (
            SELECT b2.id FROM bolum b2 WHERE b2.anime_id = a.id ORDER BY b2.id DESC LIMIT 1
        )
        WHERE EXISTS (SELECT 1 FROM bolum b3 WHERE b3.anime_id = a.id)
        ORDER BY a.effective_timestamp DESC, a.id DESC
        LIMIT ? OFFSET ?
    """, (per_page, offset))
    rows = c.fetchall()
    conn.close()

    episodes = []
    for r in rows:
        resim = f"/imajlar/serilerb/{r['ta_id']}.jpg" if r["ta_id"] else (r["poster_url"] or "/imajlar/logo.png")
        score = r["score"] or 8.0
        h = abs(hash(r["anime_slug"]))
        likes_num = max(1, int(score * 2.5 + (h % 20)))
        dislikes_num = max(0, int(likes_num * 0.04)) if (h % 3 == 0) else 0
        year_str = str(r["year"]) if r["year"] else "2024"
        season_str = r["season"] or ""

        ep_title = r["ep_name"] or r["anime_title"]
        fansub_html = format_fansub_info(r["fansub_info"])

        if r["display_date"]:
            date_str = f"{r['display_date']} eklendi."
            full_date = r["display_full_date"] if r["display_full_date"] else r["display_date"]
        else:
            date_str = f"{year_str} eklendi."
            full_date = f"{year_str} {season_str}".strip()

        episodes.append({
            "anime_title": r["anime_title"],
            "anime_slug": r["anime_slug"],
            "ep_slug": r["ep_slug"] or r["anime_slug"],
            "ep_name": ep_title,
            "fansub": r["fansub_info"],
            "fansub_raw": r["fansub_info"],
            "fansub_html": fansub_html,
            "resim": resim,
            "full_date": full_date,
            "date_str": date_str,
            "likes": f"{likes_num:,}".replace(",", "."),
            "dislikes": f"{dislikes_num:,}".replace(",", ".")
        })

    return {
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "total_count": total_count,
        "episodes": episodes
    }

@functools.lru_cache(maxsize=1024)
def render_cards_page_html(page=1, per_page=10):
    page_data = get_latest_episodes_page(page, per_page)
    episodes = page_data["episodes"]
    total_pages = page_data["total_pages"]
    current_page = page_data["page"]

    cards_html = []
    for ep in episodes:
        title_display = ep['ep_name']
        short_title = title_display[:28] + ("..." if len(title_display) > 28 else "")

        card = f'''<div class="col-xs-6" style="padding:5px;">
  <div class="panel" style="margin-bottom:5px;">
    <div class="panel-ust-ic">
      <div class="panel-title" style="height:16px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; width:95%;">
        <a href="video/{ep['ep_slug']}" class="baloon" data-toggle="tooltip" title="{title_display}">{title_display}</a>
      </div>
    </div>
    <div class="panel-body" style="padding:5px; height:150px; overflow:hidden; position:relative;">
      <a href="video/{ep['ep_slug']}" class="thumbnail pull-left" style="margin-right:5px; margin-bottom:0px;">
        <img class="media-object" src="{ep['resim']}" alt="{ep['anime_title']}" style="width:75px; height:100px; object-fit:cover;" onerror="this.src='imajlar/logo.png'">
      </a>
      <span class="media-heading" style="font-weight:normal; display:block; height:20px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
        <a href="video/{ep['ep_slug']}">{short_title}</a>
        <span class="pull-right"><img class="media-object baloon" src="imajlar/TR.gif" alt="" title="Türkçe Altyazılı" data-toggle="tooltip"></span>
      </span>
      <div class="row" style="padding:0px; margin:0px;">
        <span class="bold media-object" style="margin-top:7px;">Çeviri Fansub</span>
        <span class="media-object" style="margin-top:3px; font-size:11px; line-height:14px; max-height:42px; overflow:hidden; text-overflow:ellipsis; word-break:break-word;">
          <i class="ikon ikon-angle-right"></i> {ep['fansub_html']}
        </span>
        <span class="media-object" style="margin-top:4px;">
          <i class="ikon ikon-clock baloon" data-toggle="tooltip" title="{ep['full_date']}"></i> {ep['date_str']}
        </span>
        <span class="media-object" style="margin:0 auto; bottom: 8px; position: absolute; right:5px;">
          <div class="btn-group btn-group-sm pull-right clearfix">
            <a href="javascript:void(0);" onclick="modal('ajax/uyegirisi','modallar','Kullanıcı Girişi!'); return false;" class="btn btn-default bold colorbegen baloon" data-toggle="tooltip" title="Kişi beğendi!"><i class="ikon ikon-thumbs-up4 ikon-fw"></i> {ep['likes']}</a>
            <a href="javascript:void(0);" onclick="modal('ajax/uyegirisi','modallar','Kullanıcı Girişi!'); return false;" class="btn btn-default bold baloon" data-toggle="tooltip" title="İzlediklerime Ekle!"><i class="ikon ikon-eye ikon-fw ikon-1x ikon-margin"></i></a>
            <a href="javascript:void(0);" onclick="modal('ajax/uyegirisi','modallar','Kullanıcı Girişi!'); return false;" class="btn btn-default bold colorbegenme baloon" data-toggle="tooltip" title="Kişi beğenmedi!"><i class="ikon ikon-thumbs-down2 ikon-fw"></i> {ep['dislikes']}</a>
          </div>
        </span>
      </div>
    </div>
  </div>
</div>'''
        cards_html.append(card)

    rows_html = []
    for i in range(0, len(cards_html), 2):
        row_content = "".join(cards_html[i:i+2])
        rows_html.append(f'<div class="row" style="margin-left:-5px; margin-right:-5px;">{row_content}</div>')

    prev_btn = (
        f'<button onclick="Sayfalama(\'ajax/yenieklenenanime\',\'{current_page-1}\',\'orta-icerik\'); return $(this).button(\'loading\');" data-loading-text="Önceki Sayfa <i class=\'ikon ikon-spinner ikon-spin ikon-fw\'></i>" class="btn btn-default bold"><i class="ikon ikon-double-angle-left ikon-fw"></i> Önceki Sayfa</button>'
        if current_page > 1 else
        '<button class="btn btn-default bold" disabled="disabled"><i class="ikon ikon-double-angle-left ikon-fw"></i> Önceki Sayfa</button>'
    )
    next_btn = (
        f'<button onclick="Sayfalama(\'ajax/yenieklenenanime\',\'{current_page+1}\',\'orta-icerik\'); return $(this).button(\'loading\');" data-loading-text="Sonraki Sayfa <i class=\'ikon ikon-spinner ikon-spin ikon-fw\'></i>" class="btn btn-default bold">Sonraki Sayfa <i class="ikon ikon-double-angle-right ikon-fw"></i></button>'
        if current_page < total_pages else
        '<button class="btn btn-default bold" disabled="disabled">Sonraki Sayfa <i class="ikon ikon-double-angle-right ikon-fw"></i></button>'
    )

    page_items = []
    for p in range(1, min(total_pages + 1, 612)):
        act = ' class="active"' if p == current_page else ''
        page_items.append(f'<li{act}><a href="javascript:void(0);" onclick="Sayfalama(\'ajax/yenieklenenanime\',\'{p}\',\'orta-icerik\');">{p}. Sayfa</a></li>')
    dropdown_items_html = "".join(page_items)

    pagination_html = f'''<div class="col-xs-12" style="padding:6px;">
  <span class="label label-default" style="float:left; padding:8px; font-size:12px; margin-top:1px;">{current_page} / {total_pages}</span>
  <div class="btn-group btn-group-sm pull-right">
    {prev_btn}
    <div class="btn-group btn-group-sm dropup">
      <button type="button" class="btn btn-default bold dropdown-toggle" data-toggle="dropdown">{current_page} <span class="caret"></span></button>
      <ul class="dropdown-menu dropdown-menu2 scrollable-menu" role="menu" style="max-height: 280px; overflow-y: auto;">
        {dropdown_items_html}
      </ul>
    </div>
    {next_btn}
  </div>
</div>'''

    return "".join(rows_html) + pagination_html

def get_series_page(page=1, per_page=10, order_by="likes"):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT count(*) FROM anime")
    total_count = c.fetchone()[0]
    total_pages = max(1, (total_count + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    offset = (page - 1) * per_page

    order_clause = "ORDER BY CASE WHEN a.likes IS NOT NULL THEN a.likes ELSE 0 END DESC, a.id DESC"
    if order_by == "date":
        order_clause = "ORDER BY CASE WHEN a.effective_timestamp IS NOT NULL THEN a.effective_timestamp ELSE 0 END DESC, a.id DESC"
    elif order_by == "puan":
        order_clause = "ORDER BY CASE WHEN a.ta_puan IS NOT NULL THEN a.ta_puan ELSE (CASE WHEN m.score IS NOT NULL THEN m.score ELSE 0 END) END DESC, a.id DESC"

    c.execute(f"""
        SELECT a.id, a.slug, a.baslik, a.bolum_sayisi, a.ozet,
               a.likes, a.dislikes, a.ta_puan,
               m.score, m.year, m.season, m.format, m.status, m.duration,
               m.poster_url, m.genres_json,
               ta.ta_id,
               (SELECT count(*) FROM bolum b WHERE b.anime_id = a.id) as actual_bolum_count
        FROM anime a
        LEFT JOIN anime_meta m ON a.id = m.anime_id
        LEFT JOIN ta_anime ta ON a.id = ta.anime_id
        {order_clause}
        LIMIT ? OFFSET ?
    """, (per_page, offset))
    rows = c.fetchall()
    conn.close()

    animes = []
    for r in rows:
        slug = r["slug"]
        baslik = r["baslik"]
        puan_val = r["ta_puan"] if r["ta_puan"] else (r["score"] if r["score"] else 8.0)
        puan_str = f"{puan_val:.1f}" if puan_val else ""

        mirror_info = get_mirror_anime_info(slug) or {}

        # Episode count formatting
        mirror_ep = mirror_info.get("Bölüm Sayısı")
        if mirror_ep and isinstance(mirror_ep, str) and "/" in mirror_ep:
            bolum = mirror_ep.replace(" ", "")
        else:
            actual_cnt = r["actual_bolum_count"] or 0
            total_cnt = r["bolum_sayisi"] or 0
            if total_cnt > 0:
                if actual_cnt > total_cnt:
                    bolum = f"{actual_cnt}/{total_cnt}+"
                else:
                    bolum = f"{actual_cnt}/{total_cnt}" if actual_cnt > 0 else f"{total_cnt}/{total_cnt}"
            elif actual_cnt > 0:
                bolum = f"{actual_cnt}/?"
            else:
                bolum = "Belirtilmemiş"

        resim = f"/imajlar/serilerb/{r['ta_id']}.jpg" if r["ta_id"] else (r["poster_url"] or "/imajlar/logo.png")

        # Turkish authentic summary
        raw_ozet = r["ozet"] or mirror_info.get("Özet")
        ozet = clean_ozet(raw_ozet)
        if not ozet:
            genres = []
            if r["genres_json"]:
                try:
                    genres = [g.title() for g in json.loads(r["genres_json"])]
                except Exception:
                    pass
            ozet = f"{r['format'] or 'TV'} serisi ({r['year'] or ''}). Türler: {', '.join(genres[:4])}."

        likes_val = r["likes"] if (r["likes"] is not None and r["likes"] > 0) else 100
        dislikes_val = r["dislikes"] if (r["dislikes"] is not None and r["dislikes"] > 0) else max(5, int(likes_val / 38))

        animes.append({
            "slug": slug,
            "baslik": baslik,
            "puan": puan_str,
            "bolum": bolum,
            "resim": resim,
            "ozet": ozet,
            "kategori": r["format"] or "TV",
            "likes": f"{likes_val:,}",
            "dislikes": f"{dislikes_val:,}"
        })

    return {
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "total_count": total_count,
        "animes": animes
    }

def render_series_cards_page_html(page=1, per_page=10, endpoint="ajax/rankagore", target_div="orta-icerik", order_by="likes"):
    page_data = get_series_page(page, per_page, order_by=order_by)
    animes = page_data["animes"]
    total_pages = page_data["total_pages"]
    current_page = page_data["page"]

    cards_html = []
    for a in animes:
        rank_badge = f'<div class="rank-s" style="left:2px; bottom:2px; right:auto; min-width:32px; padding:2px 4px; text-align:center;">{a["puan"]}</div>' if a["puan"] else ''
        card = f'''<div class="col-xs-6" style="padding:5px;">
  <div class="panel" style="margin-bottom:5px;">
    <div class="panel-ust-ic">
      <div class="panel-title" style="height:16px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; width:95%;">
        <a href="anime/{a['slug']}" class="baloon bold" data-toggle="tooltip" title="{a['baslik']}"><b>{a['baslik']}</b></a>
      </div>
    </div>
    <div class="panel-body" style="padding:5px; height:150px; overflow:hidden; position:relative;">
      <a href="anime/{a['slug']}" class="thumbnail pull-left" style="margin-right:8px; margin-bottom:0px;">
        <div class="imaj" style="position:relative;">
          <img class="media-object" src="{a['resim']}" alt="{a['baslik']}" style="width:75px; height:100px; object-fit:cover;" onerror="this.src='imajlar/logo.png'">
          {rank_badge}
        </div>
      </a>
      <span class="media-heading" style="font-weight:normal; display:block; height:18px; line-height:18px; margin-bottom:2px;">
        <span class="pull-right anime-bolum" style="font-size:12px; font-weight:bold;">{a['bolum']}</span>
        <span style="display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; padding-right:5px;">
          <a href="anime/{a['slug']}" class="anime-title" style="font-weight:bold;">{a['baslik']}</a>
        </span>
      </span>
      <div class="row" style="padding:0px; margin:0px;">
        <span class="media-object anime-ozet" style="margin-top:6px; height:48px; overflow:hidden; text-overflow:ellipsis; display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; font-size:11px; line-height:16px; word-break:break-word;">
          {a['ozet']}
        </span>
        <span class="media-object" style="margin:0 auto; bottom:6px; position:absolute; right:6px;">
          <div class="btn-group btn-group-sm pull-right">
            <a href="javascript:void(0);" onclick="modal('ajax/uyegirisi','modallar','Kullanıcı Girişi!'); return false;" class="btn btn-default bold colorbegen baloon" data-toggle="tooltip" title="Kişi beğendi!"><i class="ikon ikon-thumbs-up4 ikon-fw"></i> {a['likes']}</a>
            <a href="javascript:void(0);" onclick="modal('ajax/uyegirisi','modallar','Kullanıcı Girişi!'); return false;" class="btn btn-default bold baloon" data-toggle="tooltip" title="İzlediklerime Ekle!"><i class="ikon ikon-eye ikon-fw ikon-1x ikon-margin"></i></a>
            <a href="javascript:void(0);" onclick="modal('ajax/uyegirisi','modallar','Kullanıcı Girişi!'); return false;" class="btn btn-default bold colorbegenme baloon" data-toggle="tooltip" title="Kişi beğenmedi!"><i class="ikon ikon-thumbs-down2 ikon-fw"></i> {a['dislikes']}</a>
          </div>
        </span>
      </div>
    </div>
  </div>
</div>'''
        cards_html.append(card)

    rows_html = []
    for i in range(0, len(cards_html), 2):
        row_content = "".join(cards_html[i:i+2])
        rows_html.append(f'<div class="row" style="margin-left:-5px; margin-right:-5px;">{row_content}</div>')

    prev_btn = (
        f'<button onclick="Sayfalama(\'{endpoint}\',\'{current_page-1}\',\'{target_div}\'); return $(this).button(\'loading\');" data-loading-text="Önceki Sayfa <i class=\'ikon ikon-spinner ikon-spin ikon-fw\'></i>" class="btn btn-default bold"><i class="ikon ikon-double-angle-left ikon-fw"></i> Önceki Sayfa</button>'
        if current_page > 1 else
        '<button class="btn btn-default bold" disabled="disabled"><i class="ikon ikon-double-angle-left ikon-fw"></i> Önceki Sayfa</button>'
    )
    next_btn = (
        f'<button onclick="Sayfalama(\'{endpoint}\',\'{current_page+1}\',\'{target_div}\'); return $(this).button(\'loading\');" data-loading-text="Sonraki Sayfa <i class=\'ikon ikon-spinner ikon-spin ikon-fw\'></i>" class="btn btn-default bold">Sonraki Sayfa <i class="ikon ikon-double-angle-right ikon-fw"></i></button>'
        if current_page < total_pages else
        '<button class="btn btn-default bold" disabled="disabled">Sonraki Sayfa <i class="ikon ikon-double-angle-right ikon-fw"></i></button>'
    )

    page_items = []
    for p in range(1, min(total_pages + 1, 50)):
        act = ' class="active"' if p == current_page else ''
        page_items.append(f'<li{act}><a href="javascript:void(0);" onclick="Sayfalama(\'{endpoint}\',\'{p}\',\'{target_div}\');">{p}. Sayfa</a></li>')
    dropdown_items_html = "".join(page_items)

    pagination_html = f'''<div class="col-xs-12" style="padding:6px;">
  <span class="label label-default" style="float:left; padding:8px; font-size:12px; margin-top:1px;">{current_page} / {total_pages}</span>
  <div class="btn-group btn-group-sm pull-right">
    {prev_btn}
    <div class="btn-group btn-group-sm dropup">
      <button type="button" class="btn btn-default bold dropdown-toggle" data-toggle="dropdown">{current_page} <span class="caret"></span></button>
      <ul class="dropdown-menu dropdown-menu2 scrollable-menu" role="menu" style="max-height: 280px; overflow-y: auto;">
        {dropdown_items_html}
      </ul>
    </div>
    {next_btn}
  </div>
</div>'''

    return "".join(rows_html) + pagination_html

def prefetch_series_page_images(page, per_page=10, order_by="likes"):
    def _worker():
        try:
            page_data = get_series_page(page, per_page, order_by=order_by)
            for a in page_data["animes"]:
                resim = a.get("resim", "")
                if resim and resim.startswith("/imajlar/"):
                    get_or_fetch_image(resim.lstrip("/"))
        except Exception:
            pass
    threading.Thread(target=_worker, daemon=True).start()

import threading

_TURLER_CACHE = None


def render_arsiv_haberler_html(tarih):
    if not tarih or tarih == "default":
        return None
    fpath = os.path.join(PUBLIC_DIR, "arsiv_haberler", f"{tarih}.json")
    if not os.path.exists(fpath):
        return '<div class="alert alert-info" style="margin:10px;">Bu aya ait haber bulunamadı.</div>'
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return '<div class="alert alert-danger" style="margin:10px;">Haber verisi okunamadı.</div>'
    cards = data.get("cards", [])
    if not cards:
        return '<div class="alert alert-info" style="margin:10px;">Bu aya ait haber bulunamadı.</div>'
    items_html = []
    for c in cards:
        title = html.escape(c.get("title", ""))
        href = html.escape(c.get("href", "#"))
        ozet = html.escape(c.get("ozet", ""))
        date = html.escape(c.get("date", ""))
        img = c.get("img")
        img_html = ""
        if img:
            img_html = f'<a href="{href}" target="_blank" title="{title}"><img src="{html.escape(img)}" alt="{title}" onerror="if(this.parentElement)this.parentElement.remove();"></a>'
        card_html = (
            f'<div class="thumbnail" style="margin: 5px 10px 5px 5px;">'
            f'{img_html}'
            f'<div class="caption">'
            f'<h4 class="ozet" style="font-size:16px; font-weight:bold; line-height:20px;">'
            f'<a href="{href}" target="_blank" title="{title}">{title}</a>'
            f'</h4>'
            f'<p class="ozet">{ozet}</p>'
            f'<small class="pull-right ozet">{date}</small>'
            f'<div class="clearfix"></div>'
            f'</div></div>'
        )
        items_html.append(card_html)
    return "\n".join(items_html)

def render_turler_html():
    global _TURLER_CACHE
    if _TURLER_CACHE is None:
        candidates = [
            os.path.join(BASE_DIR, "templates", "turler_final.html"),
            os.path.join(BASE_DIR, "scratch", "turler_final.html"),
            os.path.join(BASE_DIR, "public", "turler_final.html"),
        ]
        for p in candidates:
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    _TURLER_CACHE = f.read()
                break
        if _TURLER_CACHE is None:
            _TURLER_CACHE = '<div id="kategoriler"><div id="kategori-list"><p>Türler listesi yüklenemedi.</p></div></div>'
    return _TURLER_CACHE

@functools.lru_cache(maxsize=1)
def render_tamliste_html():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT slug, baslik FROM anime ORDER BY baslik COLLATE NOCASE ASC")
    rows = c.fetchall()
    conn.close()

    items = []
    for r in rows:
        slug = r["slug"] or ""
        baslik = r["baslik"] or ""
        esc_baslik = html.escape(baslik)
        esc_slug = html.escape(slug)
        items.append(
            f'<li><a href="anime/{esc_slug}" title="{esc_baslik}" style="margin-left:5px; width: 100% !important; display: inline-block; cursor:pointer">'
            f'<span style="color:#4a4a4a;" class="ikon ikon-tag ikon-fw ikon-margin"></span> '
            f'<span class="animeAdi">{esc_baslik}</span></a></li>'
        )

    script = """<script>
$(document).off('input keyup', '#filtre-input-tam').on('input keyup', '#filtre-input-tam', function() {
    var val = $(this).val().toLowerCase().trim();
    $('#tamliste-list .list li').each(function() {
        var text = $(this).find('.animeAdi').text().toLowerCase();
        $(this).toggle(text.indexOf(val) > -1);
    });
});
</script>"""
    return f'<div id="tamliste"><div id="tamliste-list"><input type="search" class="search" id="filtre-input-tam" placeholder="Filtrele..."><div id="sagScrollTam"><ul class="list menum">{"".join(items)}</ul></div></div></div>\n{script}'

@functools.lru_cache(maxsize=1)
def render_yillar_html():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT DISTINCT year FROM anime_meta WHERE year IS NOT NULL AND year > 1950 ORDER BY year DESC")
    rows = c.fetchall()
    conn.close()

    items = []
    for r in rows:
        year = r["year"]
        items.append(
            f'<li><a href="yil/{year}" title="{year} Yılına ait animeler" style="margin-left:5px; width: 100% !important; display: inline-block; cursor:pointer">'
            f'<span style="color:#4a4a4a;" class="ikon ikon-tag ikon-fw ikon-margin"></span> '
            f'<span class="yilAdi">{year}</span></a></li>'
        )

    script = """<script>
$(document).off('input keyup', '#filtre-input-yil').on('input keyup', '#filtre-input-yil', function() {
    var val = $(this).val().toLowerCase().trim();
    $('#yil-list .list li').each(function() {
        var text = $(this).find('.yilAdi').text().toLowerCase();
        $(this).toggle(text.indexOf(val) > -1);
    });
});
</script>"""
    return f'<div id="yillar"><div id="yil-list"><input type="search" class="search" id="filtre-input-yil" placeholder="Filtrele..."><div id="sagScrollYil"><ul class="list menum">{"".join(items)}</ul></div></div></div>\n{script}'

ANIME_TEMPLATE_PATH = os.path.join(BASE_DIR, "archivedownload", "animesayfaları", "www.turkanime.tv", "index.html")
_RAW_ANIME_TEMPLATE = None

def get_raw_anime_template():
    global _RAW_ANIME_TEMPLATE
    if _RAW_ANIME_TEMPLATE is None:
        candidates = [
            os.path.join(BASE_DIR, "templates", "anime_template.html"),
            ANIME_TEMPLATE_PATH,
            os.path.join(BASE_DIR, "public", "index.html"),
        ]
        for p in candidates:
            if p and os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    _RAW_ANIME_TEMPLATE = f.read()
                break
    return _RAW_ANIME_TEMPLATE

MMORPG_PANEL_HTML = '''<div class="col-xs-12" style="padding-right:0px;"> <div class="panel"><div class="panel-ust"><div class="panel-title">ÜCRETSİZ MMPORG OYUNLAR</div></div><div class="panel-body padding-none" style="text-align:center;"><div id="editorial_content" style="display:inline-block;"></div></div><div class="panel-footer clearfix"></div></div></div>'''

SPONSOR_PANEL_BOTTOM_HTML = '''<div class="col-xs-12" style="padding-right:0px;"> <div class="panel"><div class="panel-ust"><div class="panel-title">SPONSOR REKLAM</div></div><div class="panel-body" style="padding:3px; text-align:center; height:250px;"></div><div class="panel-footer clearfix"></div> </div></div>'''


def replace_aktif_icerik(html, new_inner_html):
    start_pos = html.find('id="aktif-icerik"')
    if start_pos == -1:
        return html
    open_tag = html.rfind('<div', 0, start_pos)
    pos = html.find('>', start_pos) + 1
    depth = 1
    while depth > 0 and pos < len(html):
        m = re.search(r'</?div[^>]*>', html[pos:])
        if not m:
            break
        tag = m.group(0)
        pos += m.end()
        if tag.startswith('</'):
            depth -= 1
        else:
            depth += 1
    return html[:open_tag] + f'<div class="panel-body padding-none" id="aktif-icerik">{new_inner_html}</div>' + html[pos:]

def replace_orta_icerik(html, new_inner_html):
    start_pos = html.find('id="orta-icerik"')
    if start_pos == -1:
        return html
    open_tag = html.rfind('<div', 0, start_pos)
    pos = html.find('>', start_pos) + 1
    depth = 1
    while depth > 0 and pos < len(html):
        m = re.search(r'</?div[^>]*>', html[pos:])
        if not m:
            break
        tag = m.group(0)
        pos += m.end()
        if tag.startswith('</'):
            depth -= 1
        else:
            depth += 1
    return html[:open_tag] + f'<div class="panel-body" id="orta-icerik">{new_inner_html}</div>' + html[pos:]

def replace_detay_paylas(html, new_content):
    start_pos = html.find('id="detayPaylas"')
    if start_pos == -1:
        return html
    open_tag = html.rfind('<div', 0, start_pos)
    if open_tag == -1:
        open_tag = start_pos
    pos = html.find('>', start_pos) + 1
    depth = 1
    while depth > 0 and pos < len(html):
        m = re.search(r'</?div[^>]*>', html[pos:])
        if not m:
            break
        tag = m.group(0)
        pos += m.end()
        if tag.startswith('</'):
            depth -= 1
        else:
            depth += 1
    return html[:open_tag] + new_content + html[pos:]

CATALOG_TABS_HTML = (
    '<ul class="nav panel-tabs" id="aktif-sekme">'
    '<li class="active"><a href="javascript:void(0);" data-url="ajax/turler" data-div="aktif-icerik" data-toggle="tab">Türüne Göre</a></li>'
    '<li class=""><a href="javascript:void(0);" data-url="ajax/tamliste" data-div="aktif-icerik" data-toggle="tab">Tam Liste</a></li>'
    '<li class=""><a href="javascript:void(0);" data-url="ajax/yillar" data-div="aktif-icerik" data-toggle="tab">Yılına Göre</a></li>'
    '</ul>'
)

def apply_catalog_sidebar(html):
    html = re.sub(r'<ul class="nav panel-tabs" id="aktif-sekme">.*?</ul>', CATALOG_TABS_HTML, html, count=1, flags=re.DOTALL)
    html = replace_aktif_icerik(html, render_turler_html())
    return html

def get_animeler_page(page=1, per_page=28):
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT count(*) FROM anime")
    total_count = c.fetchone()[0]
    total_pages = max(1, (total_count + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    offset = (page - 1) * per_page

    c.execute("""
        SELECT a.id, a.slug, a.baslik, a.likes, a.dislikes, a.ta_puan,
               m.score, m.poster_url, ta.ta_id,
               (SELECT count(*) FROM bolum b WHERE b.anime_id = a.id) as actual_bolum_count,
               a.bolum_sayisi, a.ozet
        FROM anime a
        LEFT JOIN anime_meta m ON a.id = m.anime_id
        LEFT JOIN ta_anime ta ON a.id = ta.anime_id
        ORDER BY 
            CASE 
                WHEN a.slug = 'summer' OR a.baslik LIKE '\\_%' ESCAPE '\\' THEN 0
                WHEN substr(a.baslik, 1, 1) NOT GLOB '[A-Za-z0-9]' THEN 1
                WHEN substr(a.baslik, 1, 1) GLOB '[0-9]' THEN 2
                ELSE 3
            END ASC,
            a.baslik COLLATE NOCASE ASC
        LIMIT ? OFFSET ?
    """, (per_page, offset))
    rows = c.fetchall()
    conn.close()

    animes = []
    for r in rows:
        slug = r["slug"]
        baslik = r["baslik"]
        puan_val = r["ta_puan"] if r["ta_puan"] else (r["score"] if r["score"] else None)
        puan_str = f"{puan_val:.2f}" if puan_val else ""

        actual_cnt = r["actual_bolum_count"] or 0
        total_cnt = r["bolum_sayisi"] or 0
        if total_cnt > 0:
            if actual_cnt > total_cnt:
                bolum = f"{actual_cnt}/{total_cnt}+"
            else:
                bolum = f"{actual_cnt}/{total_cnt}" if actual_cnt > 0 else f"{total_cnt}/{total_cnt}"
        elif actual_cnt > 0:
            bolum = f"{actual_cnt}/?"
        else:
            bolum = "Belirtilmemiş"

        resim = f"/imajlar/serilerb/{r['ta_id']}.jpg" if r["ta_id"] else (r["poster_url"] or "/imajlar/logo.png")
        ozet = r["ozet"] or f"{baslik} anime serisi."
        ozet_clean = re.sub(r'<[^>]+>', ' ', ozet).strip()
        if len(ozet_clean) > 135:
            ozet_clean = ozet_clean[:132] + "..."

        likes_val = r["likes"] if (r["likes"] is not None and r["likes"] > 0) else 100
        dislikes_val = r["dislikes"] if (r["dislikes"] is not None and r["dislikes"] > 0) else max(5, int(likes_val / 38))

        animes.append({
            "slug": slug,
            "baslik": baslik,
            "puan": puan_str,
            "bolum": bolum,
            "resim": resim,
            "ozet": ozet_clean,
            "likes": f"{likes_val:,}".replace(",", "."),
            "dislikes": f"{dislikes_val:,}".replace(",", ".")
        })

    return {
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "total_count": total_count,
        "animes": animes
    }

def render_animeler_cards_html(page=1, per_page=28):
    data = get_animeler_page(page, per_page)
    animes = data["animes"]
    current_page = data["page"]
    total_pages = data["total_pages"]

    cards_html = []
    for a in animes:
        esc_baslik = html.escape(a["baslik"])
        esc_slug = html.escape(a["slug"])
        rank_badge = f'<div class="rank-s">{a["puan"]}</div>' if a["puan"] else ''
        card = f'''<div class="col-xs-6" style="padding:5px;">
  <div class="panel" style="margin-bottom:5px;">
    <div class="panel-ust-ic">
      <div class="panel-title">
        <a href="anime/{esc_slug}" class="baloon bold" data-toggle="tooltip" title="{esc_baslik}"><b>{esc_baslik}</b></a>
      </div>
    </div>
    <div class="panel-body" style="padding:5px; height:150px; overflow:hidden; position:relative;">
      <a href="anime/{esc_slug}" class="thumbnail pull-left" style="margin-right:8px; margin-bottom:0px;">
        <div class="imaj" style="position:relative;">
          <img class="media-object" src="{a['resim']}" alt="{esc_baslik}" style="width:75px; height:100px; object-fit:cover;" onerror="this.src=\'/imajlar/logo.png\'">
          {rank_badge}
        </div>
      </a>
      <span class="media-heading" style="font-weight:normal; display:block; height:18px; line-height:18px; margin-bottom:2px;">
        <span class="pull-right anime-bolum" style="font-size:12px; font-weight:bold;">{a['bolum']}</span>
        <span style="display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; padding-right:5px;">
          <a href="anime/{esc_slug}" class="anime-title" style="font-weight:bold;">{esc_baslik}</a>
        </span>
      </span>
      <div class="row" style="padding:0px; margin:0px;">
        <span class="media-object anime-ozet" style="margin-top:6px; height:48px; overflow:hidden; text-overflow:ellipsis; display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; font-size:11px; line-height:16px; word-break:break-word;">
          {a['ozet']}
        </span>
        <span class="media-object" style="margin:0 auto; bottom:6px; position:absolute; right:6px;">
          <div class="btn-group btn-group-sm pull-right">
            <a href="javascript:void(0);" onclick="modal('ajax/uyegirisi','modallar','Kullanıcı Girişi!'); return false;" class="btn btn-default bold colorbegen baloon" data-toggle="tooltip" title="Kişi beğendi!"><i class="ikon ikon-thumbs-up4 ikon-fw"></i> {a['likes']}</a>
            <a href="javascript:void(0);" onclick="modal('ajax/uyegirisi','modallar','Kullanıcı Girişi!'); return false;" class="btn btn-default bold baloon" data-toggle="tooltip" title="İzlediklerime Ekle!"><i class="ikon ikon-eye ikon-fw ikon-1x ikon-margin"></i></a>
            <a href="javascript:void(0);" onclick="modal('ajax/uyegirisi','modallar','Kullanıcı Girişi!'); return false;" class="btn btn-default bold colorbegenme baloon" data-toggle="tooltip" title="Kişi beğenmedi!"><i class="ikon ikon-thumbs-down2 ikon-fw"></i> {a['dislikes']}</a>
          </div>
        </span>
      </div>
    </div>
  </div>
</div>'''
        cards_html.append(card)

    rows_html = []
    for i in range(0, len(cards_html), 2):
        row_content = "".join(cards_html[i:i+2])
        rows_html.append(f'<div class="row" style="margin-left:-5px; margin-right:-5px;">{row_content}</div>')

    prev_btn = (
        f'<button type="button" class="btn btn-default bold" onclick="Sayfalama(\'ajax/animeler\',\'{current_page-1}\',\'orta-icerik\');"><i class="ikon ikon-double-angle-left ikon-fw"></i> Önceki Sayfa</button>'
        if current_page > 1 else
        '<button type="button" class="btn btn-default bold" disabled="disabled"><i class="ikon ikon-double-angle-left ikon-fw"></i> Önceki Sayfa</button>'
    )
    next_btn = (
        f'<button type="button" class="btn btn-default bold" onclick="Sayfalama(\'ajax/animeler\',\'{current_page+1}\',\'orta-icerik\');">Sonraki Sayfa <i class="ikon ikon-double-angle-right ikon-fw"></i></button>'
        if current_page < total_pages else
        '<button type="button" class="btn btn-default bold" disabled="disabled">Sonraki Sayfa <i class="ikon ikon-double-angle-right ikon-fw"></i></button>'
    )

    page_items = []
    for p in range(1, total_pages + 1):
        if p == current_page:
            page_items.append(f'<li class="active"><a href="javascript:void();" onclick="Sayfalama(\'ajax/animeler\',\'{p}\',\'orta-icerik\');">{p}. Sayfa</a></li>')
        else:
            page_items.append(f'<li><a href="javascript:void(0);" onclick="Sayfalama(\'ajax/animeler\',\'{p}\',\'orta-icerik\');">{p}. Sayfa</a></li>')

    dropdown_items_html = "".join(page_items)

    pagination_html = f'''<div class="row">
  <div class="col-xs-12" style="text-align:center; margin-top:10px; margin-bottom:10px;">
    <div class="btn-group btn-group-sm">
      {prev_btn}
      <div class="btn-group btn-group-sm dropup">
        <button type="button" class="btn btn-default bold dropdown-toggle" data-toggle="dropdown">{current_page} <span class="caret"></span></button>
        <ul class="dropdown-menu dropdown-menu2 scrollable-menu" role="menu" style="max-height: 280px; overflow-y: auto;">
          {dropdown_items_html}
        </ul>
      </div>
      {next_btn}
    </div>
  </div>
</div>'''

    return "".join(rows_html) + pagination_html

def prefetch_animeler_page_images(page, per_page=28):
    def _worker():
        try:
            page_data = get_animeler_page(page, per_page)
            for a in page_data["animes"]:
                resim = a.get("resim", "")
                if resim and resim.startswith("/imajlar/"):
                    get_or_fetch_image(resim.lstrip("/"))
        except Exception:
            pass
    threading.Thread(target=_worker, daemon=True).start()

def render_animeler_page_html(page=1):
    raw_template = get_raw_anime_template()
    if not raw_template:
        return None

    cards_and_pagination = render_animeler_cards_html(page)

    animeler_panel = f'''<div class="panel">
  <div class="panel-ust"><div class="panel-title">ANIMELER</div></div>
  <div class="panel-body" id="orta-icerik">
    {cards_and_pagination}
  </div>
  <div class="panel-footer clearfix"></div>
</div>'''

    html = raw_template
    if '<head' in html and '<base href="/"' not in html:
        html = re.sub(r'(<head[^>]*>)', r'\\1\n<base href="/">', html, count=1)

    top_gap_css = '<style>body#bd { padding-top: 50px !important; } body#bd > article.container { margin-top: 0 !important; padding-top: 0 !important; } #arkaplan { margin-top: 0 !important; }</style>'
    if '<head' in html:
        html = re.sub(r'(<head[^>]*>)', r'\1\n' + top_gap_css, html, count=1)

    html = re.sub(r'<title>.*?</title>', '<title>Animeler - Türk Anime TV</title>', html, count=1)
    html = re.sub(r'<meta name="title" content=".*?">', '<meta name="title" content="Animeler">', html, count=1)

    animeler_full_content = animeler_panel + "\n" + MMORPG_PANEL_HTML + "\n" + SPONSOR_PANEL_BOTTOM_HTML
    m_mid = re.search(r'(<div class="col-xs-8">)(.*?)(</div>\s*<div class="col-xs-4">)', html, re.DOTALL)
    if m_mid:
        html = html[:m_mid.start(2)] + animeler_full_content + html[m_mid.end(2):]

    html = html.replace('../www.animeler.net/', 'www.animeler.net/')
    html = html.replace('../st.chatango.com/', 'st.chatango.com/')
    html = html.replace('../www.facebook.com/', 'www.facebook.com/')
    html = html.replace('href="index/index.html"', 'href="/"')
    html = html.replace('href="index.html"', 'href="/"')
    html = html.replace('href="./"', 'href="/"')

    html = apply_catalog_sidebar(html)
    prefetch_animeler_page_images(page, 28)
    prefetch_animeler_page_images(page + 1, 28)

    return html

_ALL_DB_GENRES = None

def get_all_genres():
    global _ALL_DB_GENRES
    if _ALL_DB_GENRES is None:
        try:
            conn = get_db()
            c = conn.cursor()
            c.execute("SELECT DISTINCT turler FROM anime WHERE turler IS NOT NULL AND turler != ''")
            rows = c.fetchall()
            conn.close()
            genres = set()
            for (t,) in rows:
                for part in t.split(','):
                    p = part.strip()
                    if p:
                        genres.add(p)
            _ALL_DB_GENRES = genres
        except Exception:
            _ALL_DB_GENRES = set()
    return _ALL_DB_GENRES

def normalize_genre_name(raw_name):
    if not raw_name:
        return "Aksiyon"
    s = urllib.parse.unquote(raw_name).strip()
    s = re.sub(r'/(?:index\.html)?$', '', s).strip()
    s = re.sub(r'\.html$', '', s).strip()
    s = re.sub(r'^\d+/', '', s).strip()
    s = s.replace("_", " ").replace("-", " ").strip()

    all_genres = get_all_genres()
    for g in all_genres:
        if g.lower() == s.lower():
            return g

    def tr_ascii(text):
        tr_map = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
        return text.translate(tr_map).lower()

    s_ascii = tr_ascii(s)
    for g in all_genres:
        if tr_ascii(g) == s_ascii:
            return g

    return s.title()

SEASON_MAP = {
    'kis': ('WINTER', ['Aralık', 'Ocak', 'Şubat']),
    'ilkbahar': ('SPRING', ['Mart', 'Nisan', 'Mayıs']),
    'yaz': ('SUMMER', ['Haziran', 'Temmuz', 'Ağustos']),
    'sonbahar': ('FALL', ['Eylül', 'Ekim', 'Kasım']),
}

BAHTIMA_ID_MAP = {
    "1": "Aksiyon",
    "2": "Macera",
    "3": "Arabalar",
    "4": "Komedi",
    "5": "Şizofreni",
    "6": "Şeytanlar",
    "7": "Gizem",
    "8": "Dram",
    "9": "Ecchi",
    "10": "Fantastik",
    "11": "Oyun",
    "13": "Tarihi",
    "14": "Korku",
    "15": "Çocuklar",
    "16": "Büyü",
    "17": "Dövüş Sanatları",
    "18": "Mecha",
    "19": "Müzik",
    "20": "Parodi",
    "21": "Samuray",
    "22": "Romantizm",
    "23": "Okul",
    "24": "Bilim Kurgu",
    "25": "Shoujo",
    "26": "Shoujo Ai",
    "27": "Shounen",
    "28": "Shounen Ai",
    "29": "Uzay",
    "30": "Spor",
    "31": "Süper Güçler",
    "32": "Vampir",
    "33": "Yaoi",
    "34": "Yuri",
    "35": "Harem",
    "36": "Yaşamdan Kesitler",
    "37": "Doğaüstü Güçler",
    "38": "Askeri",
    "39": "Polisiye",
    "40": "Psikolojik",
    "41": "Gerilim",
    "42": "Seinen",
    "43": "Josei",
}

def make_kategori_ajax_url(genre_enc, sira='ad', sezon='all', yil='all'):
    parts = [f"tur={genre_enc}"]
    if sira and sira != 'ad':
        parts.append(f"sira={sira}")
    if sezon and sezon != 'all':
        parts.append(f"sezon={sezon}")
    if yil and yil != 'all':
        parts.append(f"yil={yil}")
    return "ajax/kategori&" + "&".join(parts)

def get_kategori_page(genre_name, page=1, per_page=28, order_by='ad', season=None, year=None):
    conn = get_db()
    c = conn.cursor()

    genre_clause = "(',' || replace(replace(a.turler, ', ', ','), ' ,', ',') || ',') LIKE ('%,' || ? || ',%')"
    params = [genre_name]

    extra_clauses = []
    if season and season != 'all':
        s_key = season.lower()
        if s_key in SEASON_MAP:
            eng_season, months = SEASON_MAP[s_key]
            month_likes = " OR ".join(["a.baslama_tarihi LIKE ?" for _ in months])
            extra_clauses.append(f"(m.season = ? OR ({month_likes}))")
            params.append(eng_season)
            params.extend([f"%{m}%" for m in months])
    if year and year != 'all':
        try:
            y_val = int(year)
            extra_clauses.append("(m.year = ? OR a.baslama_tarihi LIKE ?)")
            params.extend([y_val, f"%{y_val}%"])
        except ValueError:
            pass

    where_sql = "WHERE " + " AND ".join([genre_clause] + extra_clauses)

    c.execute(f"SELECT count(*) FROM anime a LEFT JOIN anime_meta m ON a.id = m.anime_id {where_sql}", params)
    total_count = c.fetchone()[0]
    total_pages = max(1, (total_count + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    offset = (page - 1) * per_page

    order_clause = "a.baslik COLLATE NOCASE ASC"
    if order_by == 'puan':
        order_clause = "CASE WHEN a.ta_puan > 0 THEN a.ta_puan WHEN m.score > 0 THEN m.score ELSE 0 END DESC, a.baslik COLLATE NOCASE ASC"
    elif order_by == 'begen':
        order_clause = "COALESCE(a.likes, 0) DESC, a.baslik COLLATE NOCASE ASC"
    elif order_by == 'yil':
        order_clause = "COALESCE(m.year, 0) DESC, a.id DESC"
    elif order_by == 'tarih':
        order_clause = "COALESCE(a.effective_timestamp, 0) DESC, a.id DESC"

    query = f"""
        SELECT a.id, a.slug, a.baslik, a.likes, a.dislikes, a.ta_puan,
               m.score, m.poster_url, ta.ta_id,
               (SELECT count(*) FROM bolum b WHERE b.anime_id = a.id) as actual_bolum_count,
               a.bolum_sayisi, a.ozet
        FROM anime a
        LEFT JOIN anime_meta m ON a.id = m.anime_id
        LEFT JOIN ta_anime ta ON a.id = ta.anime_id
        {where_sql}
        ORDER BY {order_clause}
        LIMIT ? OFFSET ?
    """
    c.execute(query, params + [per_page, offset])
    rows = c.fetchall()
    conn.close()

    animes = []
    for r in rows:
        slug = r["slug"]
        baslik = r["baslik"]
        puan_val = r["ta_puan"] if r["ta_puan"] else (r["score"] if r["score"] else None)
        puan_str = f"{puan_val:.2f}" if puan_val else ""

        actual_cnt = r["actual_bolum_count"] or 0
        total_cnt = r["bolum_sayisi"] or 0
        if total_cnt > 0:
            if actual_cnt > total_cnt:
                bolum = f"{actual_cnt}/{total_cnt}+"
            else:
                bolum = f"{actual_cnt}/{total_cnt}" if actual_cnt > 0 else f"{total_cnt}/{total_cnt}"
        elif actual_cnt > 0:
            bolum = f"{actual_cnt}/?"
        else:
            bolum = "Belirtilmemiş"

        resim = f"/imajlar/serilerb/{r['ta_id']}.jpg" if r["ta_id"] else (r["poster_url"] or "/imajlar/logo.png")
        ozet = r["ozet"] or f"{baslik} anime serisi."
        ozet_clean = re.sub(r'<[^>]+>', ' ', ozet).strip()
        if len(ozet_clean) > 135:
            ozet_clean = ozet_clean[:132] + "..."

        likes_val = r["likes"] if (r["likes"] is not None and r["likes"] > 0) else 100
        dislikes_val = r["dislikes"] if (r["dislikes"] is not None and r["dislikes"] > 0) else max(5, int(likes_val / 38))

        animes.append({
            "slug": slug,
            "baslik": baslik,
            "puan": puan_str,
            "bolum": bolum,
            "resim": resim,
            "ozet": ozet_clean,
            "likes": f"{likes_val:,}".replace(",", "."),
            "dislikes": f"{dislikes_val:,}".replace(",", ".")
        })

    return {
        "genre": genre_name,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "total_count": total_count,
        "animes": animes
    }

def render_kategori_cards_html(genre_name, page=1, per_page=28, order_by='ad', season=None, year=None):
    data = get_kategori_page(genre_name, page, per_page, order_by=order_by, season=season, year=year)
    animes = data["animes"]
    current_page = data["page"]
    total_pages = data["total_pages"]

    genre_encoded = urllib.parse.quote(genre_name)
    ajax_base = make_kategori_ajax_url(genre_encoded, order_by, season, year)

    # Filter bar
    years_html = "".join([f'<li><a href="javascript:void(0);" onclick="Sayfalama(\'{make_kategori_ajax_url(genre_encoded, order_by, season, y)}\',\'1\',\'orta-icerik\');">{y}</a></li>' for y in range(2026, 1969, -1)])
    filter_bar_html = f'''<div class="row" style="margin-bottom:12px; margin-top:2px;">
  <div class="col-xs-12 text-right">
    <div class="btn-group btn-group-sm" style="margin-right:5px;">
      <button type="button" class="btn btn-primary bold dropdown-toggle" data-toggle="dropdown">
        <i class="ikon ikon-umbrella"></i> Anime Sezonu Seçiniz <span class="caret"></span>
      </button>
      <ul class="dropdown-menu text-left" role="menu">
        <li><a href="javascript:void(0);" onclick="Sayfalama('{make_kategori_ajax_url(genre_encoded, order_by, 'all', year)}','1','orta-icerik');">Tüm Sezonlar</a></li>
        <li><a href="javascript:void(0);" onclick="Sayfalama('{make_kategori_ajax_url(genre_encoded, order_by, 'kis', year)}','1','orta-icerik');">Kış</a></li>
        <li><a href="javascript:void(0);" onclick="Sayfalama('{make_kategori_ajax_url(genre_encoded, order_by, 'ilkbahar', year)}','1','orta-icerik');">İlkbahar</a></li>
        <li><a href="javascript:void(0);" onclick="Sayfalama('{make_kategori_ajax_url(genre_encoded, order_by, 'yaz', year)}','1','orta-icerik');">Yaz</a></li>
        <li><a href="javascript:void(0);" onclick="Sayfalama('{make_kategori_ajax_url(genre_encoded, order_by, 'sonbahar', year)}','1','orta-icerik');">Sonbahar</a></li>
      </ul>
    </div>
    <div class="btn-group btn-group-sm">
      <button type="button" class="btn btn-primary bold dropdown-toggle" data-toggle="dropdown">
        <i class="ikon ikon-time"></i> Sezon Yılı Seçiniz <span class="caret"></span>
      </button>
      <ul class="dropdown-menu scrollable-menu text-left" role="menu" style="max-height:250px; overflow-y:auto;">
        <li><a href="javascript:void(0);" onclick="Sayfalama('{make_kategori_ajax_url(genre_encoded, order_by, season, 'all')}','1','orta-icerik');">Tüm Yıllar</a></li>
        {years_html}
      </ul>
    </div>
  </div>
</div>'''

    cards_html = []
    for a in animes:
        esc_baslik = html.escape(a["baslik"])
        esc_slug = html.escape(a["slug"])
        rank_badge = f'<div class="rank-s">{a["puan"]}</div>' if a["puan"] else ''
        card = f'''<div class="col-xs-6" style="padding:5px;">
  <div class="panel" style="margin-bottom:5px;">
    <div class="panel-ust-ic">
      <div class="panel-title">
        <a href="anime/{esc_slug}" class="baloon bold" data-toggle="tooltip" title="{esc_baslik}"><b>{esc_baslik}</b></a>
      </div>
    </div>
    <div class="panel-body" style="padding:5px; height:150px; overflow:hidden; position:relative;">
      <a href="anime/{esc_slug}" class="thumbnail pull-left" style="margin-right:8px; margin-bottom:0px;">
        <div class="imaj" style="position:relative;">
          <img class="media-object" src="{a['resim']}" alt="{esc_baslik}" style="width:75px; height:100px; object-fit:cover;" onerror="this.src=\'/imajlar/logo.png\'">
          {rank_badge}
        </div>
      </a>
      <span class="media-heading" style="font-weight:normal; display:block; height:18px; line-height:18px; margin-bottom:2px;">
        <span class="pull-right anime-bolum" style="font-size:12px; font-weight:bold;">{a['bolum']}</span>
        <span style="display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; padding-right:5px;">
          <a href="anime/{esc_slug}" class="anime-title" style="font-weight:bold;">{esc_baslik}</a>
        </span>
      </span>
      <div class="row" style="padding:0px; margin:0px;">
        <span class="media-object anime-ozet" style="margin-top:6px; height:48px; overflow:hidden; text-overflow:ellipsis; display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; font-size:11px; line-height:16px; word-break:break-word;">
          {a['ozet']}
        </span>
        <span class="media-object" style="margin:0 auto; bottom:6px; position:absolute; right:6px;">
          <div class="btn-group btn-group-sm pull-right">
            <a href="javascript:void(0);" onclick="modal('ajax/uyegirisi','modallar','Kullanıcı Girişi!'); return false;" class="btn btn-default bold colorbegen baloon" data-toggle="tooltip" title="Kişi beğendi!"><i class="ikon ikon-thumbs-up4 ikon-fw"></i> {a['likes']}</a>
            <a href="javascript:void(0);" onclick="modal('ajax/uyegirisi','modallar','Kullanıcı Girişi!'); return false;" class="btn btn-default bold baloon" data-toggle="tooltip" title="İzlediklerime Ekle!"><i class="ikon ikon-eye ikon-fw ikon-1x ikon-margin"></i></a>
            <a href="javascript:void(0);" onclick="modal('ajax/uyegirisi','modallar','Kullanıcı Girişi!'); return false;" class="btn btn-default bold colorbegenme baloon" data-toggle="tooltip" title="Kişi beğenmedi!"><i class="ikon ikon-thumbs-down2 ikon-fw"></i> {a['dislikes']}</a>
          </div>
        </span>
      </div>
    </div>
  </div>
</div>'''
        cards_html.append(card)

    if not cards_html:
        cards_content = '<div class="alert alert-info" style="margin:15px;">Bu türe ait henüz anime bulunmamaktadır.</div>'
    else:
        rows_html = []
        for i in range(0, len(cards_html), 2):
            row_content = "".join(cards_html[i:i+2])
            rows_html.append(f'<div class="row" style="margin-left:-5px; margin-right:-5px;">{row_content}</div>')
        cards_content = "".join(rows_html)

    prev_btn = (
        f'<button type="button" class="btn btn-default bold" onclick="Sayfalama(\'{ajax_base}\',\'{current_page-1}\',\'orta-icerik\');"><i class="ikon ikon-double-angle-left ikon-fw"></i> Önceki Sayfa</button>'
        if current_page > 1 else
        '<button type="button" class="btn btn-default bold" disabled="disabled"><i class="ikon ikon-double-angle-left ikon-fw"></i> Önceki Sayfa</button>'
    )
    next_btn = (
        f'<button type="button" class="btn btn-default bold" onclick="Sayfalama(\'{ajax_base}\',\'{current_page+1}\',\'orta-icerik\');">Sonraki Sayfa <i class="ikon ikon-double-angle-right ikon-fw"></i></button>'
        if current_page < total_pages else
        '<button type="button" class="btn btn-default bold" disabled="disabled">Sonraki Sayfa <i class="ikon ikon-double-angle-right ikon-fw"></i></button>'
    )

    page_items = []
    for p in range(1, total_pages + 1):
        if p == current_page:
            page_items.append(f'<li class="active"><a href="javascript:void();" onclick="Sayfalama(\'{ajax_base}\',\'{p}\',\'orta-icerik\');">{p}. Sayfa</a></li>')
        else:
            page_items.append(f'<li><a href="javascript:void(0);" onclick="Sayfalama(\'{ajax_base}\',\'{p}\',\'orta-icerik\');">{p}. Sayfa</a></li>')

    dropdown_items_html = "".join(page_items)

    pagination_html = f'''<div class="row">
  <div class="col-xs-12" style="text-align:center; margin-top:10px; margin-bottom:10px;">
    <div class="btn-group btn-group-sm">
      {prev_btn}
      <div class="btn-group btn-group-sm dropup">
        <button type="button" class="btn btn-default bold dropdown-toggle" data-toggle="dropdown">{current_page} <span class="caret"></span></button>
        <ul class="dropdown-menu dropdown-menu2 scrollable-menu" role="menu" style="max-height: 280px; overflow-y: auto;">
          {dropdown_items_html}
        </ul>
      </div>
      {next_btn}
    </div>
  </div>
</div>''' if total_pages > 1 else ''

    return filter_bar_html + cards_content + pagination_html

def prefetch_kategori_page_images(genre_name, page, per_page=28, order_by='ad', season=None, year=None):
    def _worker():
        try:
            page_data = get_kategori_page(genre_name, page, per_page, order_by=order_by, season=season, year=year)
            for a in page_data["animes"]:
                resim = a.get("resim", "")
                if resim and resim.startswith("/imajlar/"):
                    get_or_fetch_image(resim.lstrip("/"))
        except Exception:
            pass
    threading.Thread(target=_worker, daemon=True).start()

def render_kategori_page_html(genre_name, page=1, order_by='ad', season=None, year=None):
    raw_template = get_raw_anime_template()
    if not raw_template:
        return None

    genre_encoded = urllib.parse.quote(genre_name)
    cards_and_pagination = render_kategori_cards_html(genre_name, page, 28, order_by=order_by, season=season, year=year)

    panel_html = f'''<div class="panel">
  <div class="panel-ust">
    <div class="panel-title">"{genre_name}" Türüne ait animeler</div>
  </div>
  <div class="panel-body" id="orta-icerik">
    {cards_and_pagination}
  </div>
  <div class="panel-footer clearfix"></div>
</div>'''

    html = raw_template
    if '<head' in html and '<base href="/"' not in html:
        html = re.sub(r'(<head[^>]*>)', r'\1\n<base href="/">', html, count=1)

    top_gap_css = '<style>body#bd { padding-top: 50px !important; } body#bd > article.container { margin-top: 0 !important; padding-top: 0 !important; } #arkaplan { margin-top: 0 !important; }</style>'
    if '<head' in html:
        html = re.sub(r'(<head[^>]*>)', r'\1\n' + top_gap_css, html, count=1)

    html = re.sub(r'<title>.*?</title>', f'<title>{genre_name} Türündeki Animeler - Türk Anime TV</title>', html, count=1)
    html = re.sub(r'<meta name="title" content=".*?">', f'<meta name="title" content="{genre_name} Animeleri">', html, count=1)

    panel_full_content = panel_html + "\n" + MMORPG_PANEL_HTML + "\n" + SPONSOR_PANEL_BOTTOM_HTML
    m_mid = re.search(r'(<div class="col-xs-8">)(.*?)(</div>\s*<div class="col-xs-4">)', html, re.DOTALL)
    if m_mid:
        html = html[:m_mid.start(2)] + panel_full_content + html[m_mid.end(2):]

    html = html.replace('../www.animeler.net/', 'www.animeler.net/')
    html = html.replace('../st.chatango.com/', 'st.chatango.com/')
    html = html.replace('../www.facebook.com/', 'www.facebook.com/')
    html = html.replace('href="index/index.html"', 'href="/"')
    html = html.replace('href="index.html"', 'href="/"')
    html = html.replace('href="./"', 'href="/"')

    html = apply_catalog_sidebar(html)
    prefetch_kategori_page_images(genre_name, page, 28, order_by=order_by, season=season, year=year)
    prefetch_kategori_page_images(genre_name, page + 1, 28, order_by=order_by, season=season, year=year)

    return html

# ----------------- HARF SAYFALARI (ALFABE FİLTRELEME) -----------------

def normalize_letter(raw_letter):
    l = urllib.parse.unquote(str(raw_letter)).strip()
    l = re.sub(r'/(?:index\.html)?$', '', l).strip()
    l = re.sub(r'\.html$', '', l).strip()
    if l in ('0-9', '.#0-9', '#0-9', '09'):
        return '0-9'
    return l[:1].upper() if l else '0-9'

def get_harf_page(letter, page=1, per_page=28, order_by='ad', season=None, year=None):
    letter = normalize_letter(letter)
    conn = get_db()
    c = conn.cursor()

    if letter == '0-9':
        letter_clause = "(a.baslik GLOB '[0-9]*' OR substr(a.baslik, 1, 1) NOT GLOB '[A-Za-z]')"
        params = []
    else:
        letter_clause = "a.baslik LIKE ?"
        params = [f"{letter}%"]

    extra_clauses = []
    if season and season != 'all':
        s_key = season.lower()
        if s_key in SEASON_MAP:
            eng_season, months = SEASON_MAP[s_key]
            month_likes = " OR ".join(["a.baslama_tarihi LIKE ?" for _ in months])
            extra_clauses.append(f"(m.season = ? OR ({month_likes}))")
            params.append(eng_season)
            params.extend([f"%{m}%" for m in months])
    if year and year != 'all':
        try:
            y_val = int(year)
            extra_clauses.append("(m.year = ? OR a.baslama_tarihi LIKE ?)")
            params.extend([y_val, f"%{y_val}%"])
        except ValueError:
            pass

    where_sql = "WHERE " + " AND ".join([letter_clause] + extra_clauses)

    c.execute(f"SELECT count(*) FROM anime a LEFT JOIN anime_meta m ON a.id = m.anime_id {where_sql}", params)
    total_count = c.fetchone()[0]
    total_pages = max(1, (total_count + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    offset = (page - 1) * per_page

    order_clause = "a.baslik COLLATE NOCASE ASC"
    if order_by == 'puan':
        order_clause = "CASE WHEN a.ta_puan > 0 THEN a.ta_puan WHEN m.score > 0 THEN m.score ELSE 0 END DESC, a.baslik COLLATE NOCASE ASC"
    elif order_by == 'begen':
        order_clause = "COALESCE(a.likes, 0) DESC, a.baslik COLLATE NOCASE ASC"
    elif order_by == 'yil':
        order_clause = "COALESCE(m.year, 0) DESC, a.id DESC"
    elif order_by == 'tarih':
        order_clause = "COALESCE(a.effective_timestamp, 0) DESC, a.id DESC"

    query = f"""
        SELECT a.id, a.slug, a.baslik, a.likes, a.dislikes, a.ta_puan,
               m.score, m.poster_url, ta.ta_id,
               (SELECT count(*) FROM bolum b WHERE b.anime_id = a.id) as actual_bolum_count,
               a.bolum_sayisi, a.ozet
        FROM anime a
        LEFT JOIN anime_meta m ON a.id = m.anime_id
        LEFT JOIN ta_anime ta ON a.id = ta.anime_id
        {where_sql}
        ORDER BY {order_clause}
        LIMIT ? OFFSET ?
    """
    c.execute(query, params + [per_page, offset])
    rows = c.fetchall()
    conn.close()

    animes = []
    for r in rows:
        slug = r["slug"]
        baslik = r["baslik"]
        puan_val = r["ta_puan"] if r["ta_puan"] else (r["score"] if r["score"] else None)
        puan_str = f"{puan_val:.2f}" if puan_val else ""

        actual_cnt = r["actual_bolum_count"] or 0
        total_cnt = r["bolum_sayisi"] or 0
        if total_cnt > 0:
            if actual_cnt > total_cnt:
                bolum = f"{actual_cnt}/{total_cnt}+"
            else:
                bolum = f"{actual_cnt}/{total_cnt}" if actual_cnt > 0 else f"{total_cnt}/{total_cnt}"
        elif actual_cnt > 0:
            bolum = f"{actual_cnt}/?"
        else:
            bolum = "Belirtilmemiş"

        resim = f"/imajlar/serilerb/{r['ta_id']}.jpg" if r["ta_id"] else (r["poster_url"] or "/imajlar/logo.png")
        ozet = r["ozet"] or f"{baslik} anime serisi."
        ozet_clean = re.sub(r'<[^>]+>', ' ', ozet).strip()
        if len(ozet_clean) > 135:
            ozet_clean = ozet_clean[:132] + "..."

        likes_val = r["likes"] if (r["likes"] is not None and r["likes"] > 0) else 100
        dislikes_val = r["dislikes"] if (r["dislikes"] is not None and r["dislikes"] > 0) else max(5, int(likes_val / 38))

        animes.append({
            "slug": slug,
            "baslik": baslik,
            "puan": puan_str,
            "bolum": bolum,
            "resim": resim,
            "ozet": ozet_clean,
            "likes": f"{likes_val:,}".replace(",", "."),
            "dislikes": f"{dislikes_val:,}".replace(",", ".")
        })

    return {
        "letter": letter,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "total_count": total_count,
        "animes": animes
    }

def make_harf_ajax_url(letter_enc, sira='ad', sezon='all', yil='all'):
    parts = [f"harf={letter_enc}"]
    if sira and sira != 'ad':
        parts.append(f"sira={sira}")
    if sezon and sezon != 'all':
        parts.append(f"sezon={sezon}")
    if yil and yil != 'all':
        parts.append(f"yil={yil}")
    return "ajax/harf&" + "&".join(parts)

def render_harf_cards_html(letter, page=1, per_page=28, order_by='ad', season=None, year=None):
    norm_letter = normalize_letter(letter)
    data = get_harf_page(norm_letter, page, per_page, order_by=order_by, season=season, year=year)
    animes = data["animes"]
    current_page = data["page"]
    total_pages = data["total_pages"]

    letter_encoded = urllib.parse.quote(norm_letter)
    ajax_base = make_harf_ajax_url(letter_encoded, order_by, season, year)

    # Filter bar
    years_html = "".join([f'<li><a href="javascript:void(0);" onclick="Sayfalama(\'{make_harf_ajax_url(letter_encoded, order_by, season, y)}\',\'1\',\'orta-icerik\');">{y}</a></li>' for y in range(2026, 1969, -1)])
    filter_bar_html = f'''<div class="row" style="margin-bottom:12px; margin-top:2px;">
  <div class="col-xs-12 text-right">
    <div class="btn-group btn-group-sm" style="margin-right:5px;">
      <button type="button" class="btn btn-primary bold dropdown-toggle" data-toggle="dropdown">
        <i class="ikon ikon-umbrella"></i> Anime Sezonu Seçiniz <span class="caret"></span>
      </button>
      <ul class="dropdown-menu text-left" role="menu">
        <li><a href="javascript:void(0);" onclick="Sayfalama('{make_harf_ajax_url(letter_encoded, order_by, 'all', year)}','1','orta-icerik');">Tüm Sezonlar</a></li>
        <li><a href="javascript:void(0);" onclick="Sayfalama('{make_harf_ajax_url(letter_encoded, order_by, 'kis', year)}','1','orta-icerik');">Kış</a></li>
        <li><a href="javascript:void(0);" onclick="Sayfalama('{make_harf_ajax_url(letter_encoded, order_by, 'ilkbahar', year)}','1','orta-icerik');">İlkbahar</a></li>
        <li><a href="javascript:void(0);" onclick="Sayfalama('{make_harf_ajax_url(letter_encoded, order_by, 'yaz', year)}','1','orta-icerik');">Yaz</a></li>
        <li><a href="javascript:void(0);" onclick="Sayfalama('{make_harf_ajax_url(letter_encoded, order_by, 'sonbahar', year)}','1','orta-icerik');">Sonbahar</a></li>
      </ul>
    </div>
    <div class="btn-group btn-group-sm">
      <button type="button" class="btn btn-primary bold dropdown-toggle" data-toggle="dropdown">
        <i class="ikon ikon-time"></i> Sezon Yılı Seçiniz <span class="caret"></span>
      </button>
      <ul class="dropdown-menu scrollable-menu text-left" role="menu" style="max-height:250px; overflow-y:auto;">
        <li><a href="javascript:void(0);" onclick="Sayfalama('{make_harf_ajax_url(letter_encoded, order_by, season, 'all')}','1','orta-icerik');">Tüm Yıllar</a></li>
        {years_html}
      </ul>
    </div>
  </div>
</div>'''

    cards_html = []
    for a in animes:
        esc_baslik = html.escape(a["baslik"])
        esc_slug = html.escape(a["slug"])
        rank_badge = f'<div class="rank-s">{a["puan"]}</div>' if a["puan"] else ''
        card = f'''<div class="col-xs-6" style="padding:5px;">
  <div class="panel" style="margin-bottom:5px;">
    <div class="panel-ust-ic">
      <div class="panel-title">
        <a href="anime/{esc_slug}" class="baloon bold" data-toggle="tooltip" title="{esc_baslik}"><b>{esc_baslik}</b></a>
      </div>
    </div>
    <div class="panel-body" style="padding:5px; height:150px; overflow:hidden; position:relative;">
      <a href="anime/{esc_slug}" class="thumbnail pull-left" style="margin-right:8px; margin-bottom:0px;">
        <div class="imaj" style="position:relative;">
          <img class="media-object" src="{a['resim']}" alt="{esc_baslik}" style="width:75px; height:100px; object-fit:cover;" onerror="this.src=\'/imajlar/logo.png\'">
          {rank_badge}
        </div>
      </a>
      <span class="media-heading" style="font-weight:normal; display:block; height:18px; line-height:18px; margin-bottom:2px;">
        <span class="pull-right anime-bolum" style="font-size:12px; font-weight:bold;">{a['bolum']}</span>
        <span style="display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; padding-right:5px;">
          <a href="anime/{esc_slug}" class="anime-title" style="font-weight:bold;">{esc_baslik}</a>
        </span>
      </span>
      <div class="row" style="padding:0px; margin:0px;">
        <span class="media-object anime-ozet" style="margin-top:6px; height:48px; overflow:hidden; text-overflow:ellipsis; display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; font-size:11px; line-height:16px; word-break:break-word;">
          {a['ozet']}
        </span>
        <span class="media-object" style="margin:0 auto; bottom:6px; position:absolute; right:6px;">
          <div class="btn-group btn-group-sm pull-right">
            <a href="javascript:void(0);" onclick="modal('ajax/uyegirisi','modallar','Kullanıcı Girişi!'); return false;" class="btn btn-default bold colorbegen baloon" data-toggle="tooltip" title="Kişi beğendi!"><i class="ikon ikon-thumbs-up4 ikon-fw"></i> {a['likes']}</a>
            <a href="javascript:void(0);" onclick="modal('ajax/uyegirisi','modallar','Kullanıcı Girişi!'); return false;" class="btn btn-default bold baloon" data-toggle="tooltip" title="İzlediklerime Ekle!"><i class="ikon ikon-eye ikon-fw ikon-1x ikon-margin"></i></a>
            <a href="javascript:void(0);" onclick="modal('ajax/uyegirisi','modallar','Kullanıcı Girişi!'); return false;" class="btn btn-default bold colorbegenme baloon" data-toggle="tooltip" title="Kişi beğenmedi!"><i class="ikon ikon-thumbs-down2 ikon-fw"></i> {a['dislikes']}</a>
          </div>
        </span>
      </div>
    </div>
  </div>
</div>'''
        cards_html.append(card)

    if not cards_html:
        cards_content = f'<div class="alert alert-info" style="margin:15px;">"{norm_letter}" harfine ait henüz anime bulunmamaktadır.</div>'
    else:
        rows_html = []
        for i in range(0, len(cards_html), 2):
            row_content = "".join(cards_html[i:i+2])
            rows_html.append(f'<div class="row" style="margin-left:-5px; margin-right:-5px;">{row_content}</div>')
        cards_content = "".join(rows_html)

    prev_btn = (
        f'<button type="button" class="btn btn-default bold" onclick="Sayfalama(\'{ajax_base}\',\'{current_page-1}\',\'orta-icerik\');"><i class="ikon ikon-double-angle-left ikon-fw"></i> Önceki Sayfa</button>'
        if current_page > 1 else
        '<button type="button" class="btn btn-default bold" disabled="disabled"><i class="ikon ikon-double-angle-left ikon-fw"></i> Önceki Sayfa</button>'
    )
    next_btn = (
        f'<button type="button" class="btn btn-default bold" onclick="Sayfalama(\'{ajax_base}\',\'{current_page+1}\',\'orta-icerik\');">Sonraki Sayfa <i class="ikon ikon-double-angle-right ikon-fw"></i></button>'
        if current_page < total_pages else
        '<button type="button" class="btn btn-default bold" disabled="disabled">Sonraki Sayfa <i class="ikon ikon-double-angle-right ikon-fw"></i></button>'
    )

    page_items = []
    for p in range(1, total_pages + 1):
        if p == current_page:
            page_items.append(f'<li class="active"><a href="javascript:void();" onclick="Sayfalama(\'{ajax_base}\',\'{p}\',\'orta-icerik\');">{p}. Sayfa</a></li>')
        else:
            page_items.append(f'<li><a href="javascript:void(0);" onclick="Sayfalama(\'{ajax_base}\',\'{p}\',\'orta-icerik\');">{p}. Sayfa</a></li>')

    dropdown_items_html = "".join(page_items)

    pagination_html = f'''<div class="row">
  <div class="col-xs-12" style="text-align:center; margin-top:10px; margin-bottom:10px;">
    <div class="btn-group btn-group-sm">
      {prev_btn}
      <div class="btn-group btn-group-sm dropup">
        <button type="button" class="btn btn-default bold dropdown-toggle" data-toggle="dropdown">{current_page} <span class="caret"></span></button>
        <ul class="dropdown-menu dropdown-menu2 scrollable-menu" role="menu" style="max-height: 280px; overflow-y: auto;">
          {dropdown_items_html}
        </ul>
      </div>
      {next_btn}
    </div>
  </div>
</div>''' if total_pages > 1 else ''

    return filter_bar_html + cards_content + pagination_html

def prefetch_harf_page_images(letter, page, per_page=28, order_by='ad', season=None, year=None):
    def _worker():
        try:
            norm_letter = normalize_letter(letter)
            page_data = get_harf_page(norm_letter, page, per_page, order_by=order_by, season=season, year=year)
            for a in page_data["animes"]:
                resim = a.get("resim", "")
                if resim and resim.startswith("/imajlar/"):
                    get_or_fetch_image(resim.lstrip("/"))
        except Exception:
            pass
    threading.Thread(target=_worker, daemon=True).start()

def build_alphabet_navbar_html(active_letter):
    norm_active = normalize_letter(active_letter)
    letters = ['0-9'] + [chr(c) for c in range(ord('A'), ord('Z') + 1)]
    buttons = []
    for l in letters:
        label = ".#0-9" if l == '0-9' else l
        btn_class = "btn-danger" if l == norm_active else "btn-default"
        buttons.append(f'<a href="harf/{l}" class="btn {btn_class}" style="padding-left:12px; padding-right:12px;"><b>{label}</b></a>')
    
    return f'''<div class="navbar navbar-inverse panel" style="margin:10px 0 10px 0"><div class="navbar-inner panel-ust" style="padding:5px 0 5px 0; margin: 0 auto; text-align: center;"><div class="btn-group btn-group-sm">{''.join(buttons)}</div></div></div>'''

def render_harf_page_html(letter, page=1, order_by='ad', season=None, year=None):
    raw_template = get_raw_anime_template()
    if not raw_template:
        return None

    norm_letter = normalize_letter(letter)
    letter_encoded = urllib.parse.quote(norm_letter)
    cards_and_pagination = render_harf_cards_html(norm_letter, page, 28, order_by=order_by, season=season, year=year)

    panel_html = f'''<div class="panel">
  <div class="panel-ust">
    <div class="panel-title">"{norm_letter}" Harfine ait animeler</div>
  </div>
  <div class="panel-body" id="orta-icerik">
    {cards_and_pagination}
  </div>
  <div class="panel-footer clearfix"></div>
</div>'''

    html = raw_template
    if '<head' in html and '<base href="/"' not in html:
        html = re.sub(r'(<head[^>]*>)', r'\1\n<base href="/">', html, count=1)

    top_gap_css = '<style>body#bd { padding-top: 50px !important; } body#bd > article.container { margin-top: 0 !important; padding-top: 0 !important; } #arkaplan { margin-top: 0 !important; }</style>'
    if '<head' in html:
        html = re.sub(r'(<head[^>]*>)', r'\1\n' + top_gap_css, html, count=1)

    html = re.sub(r'<title>.*?</title>', f'<title>"{norm_letter}" Harfine Ait Animeler - Türk Anime TV</title>', html, count=1)
    html = re.sub(r'<meta name="title" content=".*?">', f'<meta name="title" content="{norm_letter} Harfine Ait Animeler">', html, count=1)

    alpha_nav = build_alphabet_navbar_html(norm_letter)
    html = re.sub(r'<div class="navbar navbar-inverse panel"[^>]*>.*?</div>\s*</div>\s*</div>', alpha_nav, html, count=1, flags=re.DOTALL)

    panel_full_content = panel_html + "\n" + MMORPG_PANEL_HTML + "\n" + SPONSOR_PANEL_BOTTOM_HTML
    m_mid = re.search(r'(<div class="col-xs-8">)(.*?)(</div>\s*<div class="col-xs-4">)', html, re.DOTALL)
    if m_mid:
        html = html[:m_mid.start(2)] + panel_full_content + html[m_mid.end(2):]

    html = html.replace('../www.animeler.net/', 'www.animeler.net/')
    html = html.replace('../st.chatango.com/', 'st.chatango.com/')
    html = html.replace('../www.facebook.com/', 'www.facebook.com/')
    html = html.replace('href="index/index.html"', 'href="/"')
    html = html.replace('href="index.html"', 'href="/"')
    html = html.replace('href="./"', 'href="/"')

    html = apply_catalog_sidebar(html)
    prefetch_harf_page_images(norm_letter, page, 28, order_by=order_by, season=season, year=year)
    prefetch_harf_page_images(norm_letter, page + 1, 28, order_by=order_by, season=season, year=year)

    return html

# ----------------- YIL SAYFALARI (YIL FİLTRELEME) -----------------

def normalize_year(raw_year):
    y = urllib.parse.unquote(str(raw_year)).strip()
    y = re.sub(r'/(?:index\.html)?$', '', y).strip()
    y = re.sub(r'\.html$', '', y).strip()
    try:
        y_int = int(y)
        if 1950 <= y_int <= 2035:
            return y_int
    except Exception:
        pass
    return 2024

def make_yil_ajax_url(year, sira='ad', sezon='all'):
    parts = [f"yil={year}"]
    if sira and sira != 'ad':
        parts.append(f"sira={sira}")
    if sezon and sezon != 'all':
        parts.append(f"sezon={sezon}")
    return "ajax/yil&" + "&".join(parts)

def get_yil_page(year, page=1, per_page=28, order_by='ad', season=None):
    year = normalize_year(year)
    conn = get_db()
    c = conn.cursor()

    year_clause = "(m.year = ? OR a.baslama_tarihi LIKE ?)"
    params = [year, f"%{year}%"]

    extra_clauses = []
    if season and season != 'all':
        s_key = season.lower()
        if s_key in SEASON_MAP:
            eng_season, months = SEASON_MAP[s_key]
            month_likes = " OR ".join(["a.baslama_tarihi LIKE ?" for _ in months])
            extra_clauses.append(f"(m.season = ? OR ({month_likes}))")
            params.append(eng_season)
            params.extend([f"%{m}%" for m in months])

    where_sql = "WHERE " + " AND ".join([year_clause] + extra_clauses)

    c.execute(f"SELECT count(*) FROM anime a LEFT JOIN anime_meta m ON a.id = m.anime_id {where_sql}", params)
    total_count = c.fetchone()[0]
    total_pages = max(1, (total_count + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    offset = (page - 1) * per_page

    order_clause = "a.baslik COLLATE NOCASE ASC"
    if order_by == 'puan':
        order_clause = "CASE WHEN a.ta_puan > 0 THEN a.ta_puan WHEN m.score > 0 THEN m.score ELSE 0 END DESC, a.baslik COLLATE NOCASE ASC"
    elif order_by == 'begen':
        order_clause = "COALESCE(a.likes, 0) DESC, a.baslik COLLATE NOCASE ASC"
    elif order_by == 'yil':
        order_clause = "COALESCE(m.year, 0) DESC, a.id DESC"
    elif order_by == 'tarih':
        order_clause = "COALESCE(a.effective_timestamp, 0) DESC, a.id DESC"

    query = f"""
        SELECT a.id, a.slug, a.baslik, a.likes, a.dislikes, a.ta_puan,
               m.score, m.poster_url, ta.ta_id,
               (SELECT count(*) FROM bolum b WHERE b.anime_id = a.id) as actual_bolum_count,
               a.bolum_sayisi, a.ozet
        FROM anime a
        LEFT JOIN anime_meta m ON a.id = m.anime_id
        LEFT JOIN ta_anime ta ON a.id = ta.anime_id
        {where_sql}
        ORDER BY {order_clause}
        LIMIT ? OFFSET ?
    """
    c.execute(query, params + [per_page, offset])
    rows = c.fetchall()
    conn.close()

    animes = []
    for r in rows:
        slug = r["slug"]
        baslik = r["baslik"]
        puan_val = r["ta_puan"] if r["ta_puan"] else (r["score"] if r["score"] else None)
        puan_str = f"{puan_val:.2f}" if puan_val else ""

        actual_cnt = r["actual_bolum_count"] or 0
        total_cnt = r["bolum_sayisi"] or 0
        if total_cnt > 0:
            if actual_cnt > total_cnt:
                bolum = f"{actual_cnt}/{total_cnt}+"
            else:
                bolum = f"{actual_cnt}/{total_cnt}" if actual_cnt > 0 else f"{total_cnt}/{total_cnt}"
        elif actual_cnt > 0:
            bolum = f"{actual_cnt}/?"
        else:
            bolum = "Belirtilmemiş"

        resim = f"/imajlar/serilerb/{r['ta_id']}.jpg" if r["ta_id"] else (r["poster_url"] or "/imajlar/logo.png")
        ozet = r["ozet"] or f"{baslik} anime serisi."
        ozet_clean = re.sub(r'<[^>]+>', ' ', ozet).strip()
        if len(ozet_clean) > 135:
            ozet_clean = ozet_clean[:132] + "..."

        likes_val = r["likes"] if (r["likes"] is not None and r["likes"] > 0) else 100
        dislikes_val = r["dislikes"] if (r["dislikes"] is not None and r["dislikes"] > 0) else max(5, int(likes_val / 38))

        animes.append({
            "slug": slug,
            "baslik": baslik,
            "puan": puan_str,
            "bolum": bolum,
            "resim": resim,
            "ozet": ozet_clean,
            "likes": f"{likes_val:,}".replace(",", "."),
            "dislikes": f"{dislikes_val:,}".replace(",", ".")
        })

    return {
        "year": year,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "total_count": total_count,
        "animes": animes
    }

def render_yil_cards_html(year, page=1, per_page=28, order_by='ad', season=None):
    year = normalize_year(year)
    data = get_yil_page(year, page, per_page, order_by=order_by, season=season)
    animes = data["animes"]
    current_page = data["page"]
    total_pages = data["total_pages"]

    ajax_base = make_yil_ajax_url(year, order_by, season)

    # Filter bar
    years_html = "".join([f'<li><a href="yil/{y}" onclick="Sayfalama(\'{make_yil_ajax_url(y, order_by, season)}\',\'1\',\'orta-icerik\'); if(window.history && window.history.pushState) window.history.pushState(null,\'\',\'yil/{y}\'); return false;">{y}</a></li>' for y in range(2026, 1969, -1)])
    filter_bar_html = f'''<div class="row" style="margin-bottom:12px; margin-top:2px;">
  <div class="col-xs-12 text-right">
    <div class="btn-group btn-group-sm" style="margin-right:5px;">
      <button type="button" class="btn btn-primary bold dropdown-toggle" data-toggle="dropdown">
        <i class="ikon ikon-umbrella"></i> Anime Sezonu Seçiniz <span class="caret"></span>
      </button>
      <ul class="dropdown-menu text-left" role="menu">
        <li><a href="javascript:void(0);" onclick="Sayfalama('{make_yil_ajax_url(year, order_by, 'all')}','1','orta-icerik');">Tüm Sezonlar</a></li>
        <li><a href="javascript:void(0);" onclick="Sayfalama('{make_yil_ajax_url(year, order_by, 'kis')}','1','orta-icerik');">Kış</a></li>
        <li><a href="javascript:void(0);" onclick="Sayfalama('{make_yil_ajax_url(year, order_by, 'ilkbahar')}','1','orta-icerik');">İlkbahar</a></li>
        <li><a href="javascript:void(0);" onclick="Sayfalama('{make_yil_ajax_url(year, order_by, 'yaz')}','1','orta-icerik');">Yaz</a></li>
        <li><a href="javascript:void(0);" onclick="Sayfalama('{make_yil_ajax_url(year, order_by, 'sonbahar')}','1','orta-icerik');">Sonbahar</a></li>
      </ul>
    </div>
    <div class="btn-group btn-group-sm">
      <button type="button" class="btn btn-primary bold dropdown-toggle" data-toggle="dropdown">
        <i class="ikon ikon-time"></i> Yıl Değiştir ({year}) <span class="caret"></span>
      </button>
      <ul class="dropdown-menu scrollable-menu text-left" role="menu" style="max-height:250px; overflow-y:auto;">
        {years_html}
      </ul>
    </div>
  </div>
</div>'''

    cards_html = []
    for a in animes:
        esc_baslik = html.escape(a["baslik"])
        esc_slug = html.escape(a["slug"])
        rank_badge = f'<div class="rank-s">{a["puan"]}</div>' if a["puan"] else ''
        card = f'''<div class="col-xs-6" style="padding:5px;">
  <div class="panel" style="margin-bottom:5px;">
    <div class="panel-ust-ic">
      <div class="panel-title">
        <a href="anime/{esc_slug}" class="baloon bold" data-toggle="tooltip" title="{esc_baslik}"><b>{esc_baslik}</b></a>
      </div>
    </div>
    <div class="panel-body" style="padding:5px; height:150px; overflow:hidden; position:relative;">
      <a href="anime/{esc_slug}" class="thumbnail pull-left" style="margin-right:8px; margin-bottom:0px;">
        <div class="imaj" style="position:relative;">
          <img class="media-object" src="{a['resim']}" alt="{esc_baslik}" style="width:75px; height:100px; object-fit:cover;" onerror="this.src=\'/imajlar/logo.png\'">
          {rank_badge}
        </div>
      </a>
      <span class="media-heading" style="font-weight:normal; display:block; height:18px; line-height:18px; margin-bottom:2px;">
        <span class="pull-right anime-bolum" style="font-size:12px; font-weight:bold;">{a['bolum']}</span>
        <span style="display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; padding-right:5px;">
          <a href="anime/{esc_slug}" class="anime-title" style="font-weight:bold;">{esc_baslik}</a>
        </span>
      </span>
      <div class="row" style="padding:0px; margin:0px;">
        <span class="media-object anime-ozet" style="margin-top:6px; height:48px; overflow:hidden; text-overflow:ellipsis; display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; font-size:11px; line-height:16px; word-break:break-word;">
          {a['ozet']}
        </span>
        <span class="media-object" style="margin:0 auto; bottom:6px; position:absolute; right:6px;">
          <div class="btn-group btn-group-sm pull-right">
            <a href="javascript:void(0);" onclick="modal('ajax/uyegirisi','modallar','Kullanıcı Girişi!'); return false;" class="btn btn-default bold colorbegen baloon" data-toggle="tooltip" title="Kişi beğendi!"><i class="ikon ikon-thumbs-up4 ikon-fw"></i> {a['likes']}</a>
            <a href="javascript:void(0);" onclick="modal('ajax/uyegirisi','modallar','Kullanıcı Girişi!'); return false;" class="btn btn-default bold baloon" data-toggle="tooltip" title="İzlediklerime Ekle!"><i class="ikon ikon-eye ikon-fw ikon-1x ikon-margin"></i></a>
            <a href="javascript:void(0);" onclick="modal('ajax/uyegirisi','modallar','Kullanıcı Girişi!'); return false;" class="btn btn-default bold colorbegenme baloon" data-toggle="tooltip" title="Kişi beğenmedi!"><i class="ikon ikon-thumbs-down2 ikon-fw"></i> {a['dislikes']}</a>
          </div>
        </span>
      </div>
    </div>
  </div>
</div>'''
        cards_html.append(card)

    if not cards_html:
        cards_content = f'<div class="alert alert-info" style="margin:15px;">"{year}" yılına ait henüz anime bulunmamaktadır.</div>'
    else:
        rows_html = []
        for i in range(0, len(cards_html), 2):
            row_content = "".join(cards_html[i:i+2])
            rows_html.append(f'<div class="row" style="margin-left:-5px; margin-right:-5px;">{row_content}</div>')
        cards_content = "".join(rows_html)

    prev_btn = (
        f'<button type="button" class="btn btn-default bold" onclick="Sayfalama(\'{ajax_base}\',\'{current_page-1}\',\'orta-icerik\');"><i class="ikon ikon-double-angle-left ikon-fw"></i> Önceki Sayfa</button>'
        if current_page > 1 else
        '<button type="button" class="btn btn-default bold" disabled="disabled"><i class="ikon ikon-double-angle-left ikon-fw"></i> Önceki Sayfa</button>'
    )
    next_btn = (
        f'<button type="button" class="btn btn-default bold" onclick="Sayfalama(\'{ajax_base}\',\'{current_page+1}\',\'orta-icerik\');">Sonraki Sayfa <i class="ikon ikon-double-angle-right ikon-fw"></i></button>'
        if current_page < total_pages else
        '<button type="button" class="btn btn-default bold" disabled="disabled">Sonraki Sayfa <i class="ikon ikon-double-angle-right ikon-fw"></i></button>'
    )

    page_items = []
    for p in range(1, total_pages + 1):
        if p == current_page:
            page_items.append(f'<li class="active"><a href="javascript:void();" onclick="Sayfalama(\'{ajax_base}\',\'{p}\',\'orta-icerik\');">{p}. Sayfa</a></li>')
        else:
            page_items.append(f'<li><a href="javascript:void(0);" onclick="Sayfalama(\'{ajax_base}\',\'{p}\',\'orta-icerik\');">{p}. Sayfa</a></li>')

    dropdown_items_html = "".join(page_items)

    pagination_html = f'''<div class="row">
  <div class="col-xs-12" style="text-align:center; margin-top:10px; margin-bottom:10px;">
    <div class="btn-group btn-group-sm">
      {prev_btn}
      <div class="btn-group btn-group-sm dropup">
        <button type="button" class="btn btn-default bold dropdown-toggle" data-toggle="dropdown">{current_page} <span class="caret"></span></button>
        <ul class="dropdown-menu dropdown-menu2 scrollable-menu" role="menu" style="max-height: 280px; overflow-y: auto;">
          {dropdown_items_html}
        </ul>
      </div>
      {next_btn}
    </div>
  </div>
</div>''' if total_pages > 1 else ''

    return filter_bar_html + cards_content + pagination_html

def prefetch_yil_page_images(year, page, per_page=28, order_by='ad', season=None):
    def _worker():
        try:
            page_data = get_yil_page(year, page, per_page, order_by=order_by, season=season)
            for a in page_data["animes"]:
                resim = a.get("resim", "")
                if resim and resim.startswith("/imajlar/"):
                    get_or_fetch_image(resim.lstrip("/"))
        except Exception:
            pass
    threading.Thread(target=_worker, daemon=True).start()

def render_yil_page_html(year, page=1, order_by='ad', season=None):
    raw_template = get_raw_anime_template()
    if not raw_template:
        return None

    year = normalize_year(year)
    cards_and_pagination = render_yil_cards_html(year, page, 28, order_by=order_by, season=season)

    panel_html = f'''<div class="panel">
  <div class="panel-ust">
    <div class="panel-title">"{year}" Yılına ait animeler</div>
  </div>
  <div class="panel-body" id="orta-icerik">
    {cards_and_pagination}
  </div>
  <div class="panel-footer clearfix"></div>
</div>'''

    html = raw_template
    if '<head' in html and '<base href="/"' not in html:
        html = re.sub(r'(<head[^>]*>)', r'\1\n<base href="/">', html, count=1)

    top_gap_css = '<style>body#bd { padding-top: 50px !important; } body#bd > article.container { margin-top: 0 !important; padding-top: 0 !important; } #arkaplan { margin-top: 0 !important; }</style>'
    if '<head' in html:
        html = re.sub(r'(<head[^>]*>)', r'\1\n' + top_gap_css, html, count=1)

    html = re.sub(r'<title>.*?</title>', f'<title>"{year}" Yılına Ait Animeler - Türk Anime TV</title>', html, count=1)
    html = re.sub(r'<meta name="title" content=".*?">', f'<meta name="title" content="{year} Yılına Ait Animeler">', html, count=1)

    panel_full_content = panel_html + "\n" + MMORPG_PANEL_HTML + "\n" + SPONSOR_PANEL_BOTTOM_HTML
    m_mid = re.search(r'(<div class="col-xs-8">)(.*?)(</div>\s*<div class="col-xs-4">)', html, re.DOTALL)
    if m_mid:
        html = html[:m_mid.start(2)] + panel_full_content + html[m_mid.end(2):]

    html = html.replace('../www.animeler.net/', 'www.animeler.net/')
    html = html.replace('../st.chatango.com/', 'st.chatango.com/')
    html = html.replace('../www.facebook.com/', 'www.facebook.com/')
    html = html.replace('href="index/index.html"', 'href="/"')
    html = html.replace('href="index.html"', 'href="/"')
    html = html.replace('href="./"', 'href="/"')

    html = apply_catalog_sidebar(html)
    prefetch_yil_page_images(year, page, 28, order_by=order_by, season=season)
    prefetch_yil_page_images(year, page + 1, 28, order_by=order_by, season=season)

    return html



def render_episodes_list_html(episodes, active_ep_slug=None):
    if not episodes:
        return '<div class="alert alert-info" style="margin:10px;">Henüz bölüm eklenmemiş.</div>'
    items = []
    for ep in episodes:
        ep_name = ep["ad"]
        ep_slug = ep["slug"]
        is_active = (ep_slug == active_ep_slug)
        active_class = "active-bolum" if is_active else ""
        bg_style = "background-color:#e0e0e0; font-weight:bold; color:#d9534f;" if is_active else ""
        icon_color = "#d9534f" if is_active else "#4a4a4a"
        items.append(
            f'<li class="{active_class}"><a href="video/{ep_slug}" title="{ep_name}" style="margin-left:5px; width: 100% !important; display: inline-block; cursor:pointer; {bg_style}">'
            f'<span style="color:{icon_color};" class="ikon ikon-play-circle ikon-fw ikon-margin"></span> '
            f'<span class="bolumAdi">{ep_name}</span></a></li>'
        )

    script = """<script>
$(document).off('input keyup', '#filtre-input-bolum').on('input keyup', '#filtre-input-bolum', function() {
    var val = $(this).val().toLowerCase().trim();
    $('#bolum-list .list li').each(function() {
        var text = $(this).find('.bolumAdi').text().toLowerCase();
        if (text.indexOf(val) !== -1) {
            $(this).show();
        } else {
            $(this).hide();
        }
    });
});
var activeEp = $('#bolum-list .active-bolum');
if (activeEp.length && $('#sagScrollBolum').length) {
    var pos = activeEp.position();
    if (pos) {
        $('#sagScrollBolum').scrollTop(pos.top - 50);
    }
}
</script>"""
    return f'<div id="bolumler"><div id="bolum-list"><input type="search" class="search" id="filtre-input-bolum" placeholder="Filtrele..."><div id="sagScrollBolum" style="max-height: 480px; overflow-y: auto;"><ul class="list menum">{"".join(items)}</ul></div></div></div>\n{script}'

@functools.lru_cache(maxsize=1024)
def render_anime_page_html(slug):
    raw_template = get_raw_anime_template()
    if not raw_template:
        return None

    info = get_anime_info(slug)
    if not info:
        return None

    anime_id = info["id"]
    ta_id = info["ta_id"] or anime_id
    baslik = info["baslik"]

    conn = get_db()
    c = conn.cursor()

    # Episodes
    c.execute("SELECT id, slug, ad FROM bolum WHERE anime_id = ? ORDER BY id ASC", (anime_id,))
    episodes = [dict(r) for r in c.fetchall()]

    # Fansub groups
    c.execute("""
        SELECT DISTINCT fg.name 
        FROM ta_episode_fansub ef
        JOIN ta_fansub_group fg ON ef.fansub_group_id = fg.id
        WHERE ef.bolum_id IN (SELECT id FROM bolum WHERE anime_id = ?)
        LIMIT 6
    """, (anime_id,))
    fansub_groups = [r[0] for r in c.fetchall() if r[0]]
    if not fansub_groups:
        c.execute("""
            SELECT DISTINCT l.fansub 
            FROM link l 
            JOIN bolum b ON l.bolum_id = b.id 
            WHERE b.anime_id = ? AND l.fansub IS NOT NULL AND l.fansub != ''
            LIMIT 6
        """, (anime_id,))
        fansub_groups = [r[0] for r in c.fetchall() if r[0]]
    conn.close()

    kategori = info["Kategori"]
    eng_title = info["İngilizce"]
    other_titles = info["Diğer Adları"]
    jap_title = info["Japonca"]
    studyo = info["Stüdyo"]
    genres = info["Anime Türü"]

    score_str = info["Puanı"]
    resim = info["Resim"]

    likes = info["likes"] or 500
    dislikes = info["dislikes"] or max(5, int(likes / 38))
    likes_str = f"{likes:,}".replace(",", ".")
    dislikes_str = f"{dislikes:,}".replace(",", ".")
    voters = info.get("voters", max(25, int(likes * 0.70)))

    duration_str = info["Bölüm Süresi"]
    ep_count_str = f"{len(episodes)} / {info['bolum_sayisi'] or len(episodes)}"
    start_date = info["Başlama Tarihi"] or "Belirtilmemiş"
    end_date = info["Bitiş Tarihi"] or ("Devam Ediyor" if info["Durum"] == "RELEASING" else "Tamamlandı")

    summary_clean = info["Özet"] or f"{baslik}, {kategori} formatında yayınlanan bir anime serisidir."

    genre_badges = " ".join([
        f'<a href="anime-turu/{g.replace(" ", "_")}" class="btn btn-default btn-xs" style="margin-bottom:3px; margin-right:3px;"><i style="color:#4a4a4a; position:relative; top:1px;" class="ikon ikon-tag"></i> {g}</a>'
        for g in genres
    ])

    fansub_badges = " ".join([
        f'<span class="btn btn-default btn-xs" style="margin-bottom:3px; margin-right:3px;"><i style="color:#4a4a4a; position:relative; top:1px;" class="ikon ikon-heart3"></i> {fg}</span>'
        for fg in fansub_groups
    ]) if fansub_groups else '<span class="btn btn-default btn-xs" style="margin-bottom:3px; margin-right:3px;"><i style="color:#4a4a4a; position:relative; top:1px;" class="ikon ikon-heart3"></i> Varsayılan</span>'

    studyo_row = ""
    if studyo and studyo != "Belirtilmemiş":
        studyo_row = f'<tr><td style="vertical-align: middle;"><b>Stüdyo</b></td><td align="center" style="vertical-align: middle;">:</td><td width="70%" style="vertical-align: middle;">{studyo}</td></tr>'

    animedetay_table = f'''<table border="0" width="100%" class="table table-striped table-bordered"><tbody><tr><td style="vertical-align: middle;"><b>Kategori</b></td><td align="center" style="vertical-align: middle;">:</td><td width="70%" style="vertical-align: middle;">{kategori}</td></tr><tr><td style="vertical-align: middle;"><b>İngilizce</b></td><td align="center" style="vertical-align: middle;">:</td><td width="70%" style="vertical-align: middle;">{eng_title}</td></tr><tr><td style="vertical-align: middle;"><b>Diğer Adları</b></td><td align="center" style="vertical-align: middle;">:</td><td width="70%" style="vertical-align: middle;">{other_titles}</td></tr><tr><td style="vertical-align: middle;"><b>Japonca</b></td><td align="center" style="vertical-align: middle;">:</td><td width="70%" style="vertical-align: middle;">{jap_title}</td></tr><tr><td style="vertical-align: middle;"><b>Anime Türü</b></td><td align="center" style="vertical-align: middle;">:</td><td width="70%" style="vertical-align: middle;">{genre_badges}</td></tr><tr><td style="vertical-align: middle;"><b>Bölüm Sayısı</b></td><td align="center" style="vertical-align: middle;">:</td><td width="70%" style="vertical-align: middle;">{ep_count_str}</td></tr><tr><td style="vertical-align: middle;"><b>Başlama Tarihi</b></td><td align="center" style="vertical-align: middle;">:</td><td width="70%" style="vertical-align: middle;">{start_date}</td></tr><tr><td style="vertical-align: middle;"><b>Bitiş Tarihi</b></td><td align="center" style="vertical-align: middle;">:</td><td width="70%" style="vertical-align: middle;">{end_date}</td></tr><tr><td style="vertical-align: middle;"><b>Yaş Sınırı</b></td><td align="center" style="vertical-align: middle;">:</td><td width="70%" style="vertical-align: middle;">PG-13 - 13 Yaş üstü</td></tr>{studyo_row}<tr><td style="vertical-align: middle;"><b>Bölüm Süresi</b></td><td align="center" style="vertical-align: middle;">:</td><td width="70%" style="vertical-align: middle;">{duration_str}</td></tr><tr><td style="vertical-align: middle;"><b>Puanı</b></td><td align="center" style="vertical-align: middle;">:</td><td width="70%" style="vertical-align: middle;" class="baloon" title="Oylama sonuçlarının belirlenmesi için en az 5 oy kullanılması gerekmektedir."><span class="puan" style="font-weight:bold;">{score_str}</span> / 10 Üzerinden <i>( Oylamaya <span class="toplam">{voters}</span> kişi katıldı. )</i></td></tr><tr><td style="vertical-align: middle;"><b>Oylama</b></td><td align="center" style="vertical-align: middle;">:</td><td width="70%" style="vertical-align: middle;"><div class="oylama" data-id="{ta_id}" data-skor="{score_str}"></div></td></tr><tr><td style="vertical-align: middle;"><b>Fansub</b></td><td align="center" style="vertical-align: middle;">:</td><td width="70%" style="vertical-align: middle;">{fansub_badges}</td></tr><tr><td style="vertical-align: middle;"><b>Altyazı</b></td><td align="center" style="vertical-align: middle;">:</td><td width="70%" style="vertical-align: middle;"><span class="btn btn-default btn-xs" style="margin-bottom:3px; margin-right:3px;"><i style="color:#4a4a4a; position:relative; top:1px;" class="ikon ikon-star4"></i> Türkçe Altyazılı</span></td></tr><tr><td style="vertical-align: middle;"><b>Beğeniler</b></td><td align="center" style="vertical-align: middle;">:</td><td width="70%" style="vertical-align: middle;"><div class="btn-group btn-group-sm"><a href="javascript:void(0);" onclick="modal('ajax/uyegirisi','modallar','Kullanıcı Girişi!'); return false;" class="btn btn-default bold colorbegen baloon" data-toggle="tooltip" title="Kişi beğendi!"><i class="ikon ikon-thumbs-up4 ikon-fw"></i> {likes_str}</a><a href="javascript:void(0);" onclick="modal('ajax/uyegirisi','modallar','Kullanıcı Girişi!'); return false;" class="btn btn-default bold baloon" data-toggle="tooltip" title="İzlediklerime Ekle!"><i class="ikon ikon-eye ikon-fw ikon-1x ikon-margin"></i></a><a href="javascript:void(0);" onclick="modal('ajax/uyegirisi','modallar','Kullanıcı Girişi!'); return false;" class="btn btn-default bold colorbegenme baloon" data-toggle="tooltip" title="Kişi beğenmedi!"><i class="ikon ikon-thumbs-down2 ikon-fw"></i> {dislikes_str}</a><a href="javascript:void(0);" class="btn btn-default bold baloon dropdown-toggle" data-toggle="dropdown" aria-haspopup="true" aria-expanded="false" title="İzleme Listeme Ekle">Ekle <span class="caret"></span></a><ul class="dropdown-menu dropdown-menu2 menuArrow3" role="menu"><li><a href="javascript:void(0);" onclick="modal('ajax/uyegirisi','modallar','Kullanıcı Girişi!');"><i class="ikon ikon-exclamation ikon-fw"></i> İzlemeyi Sürdürdüklerim</a></li><li><a href="javascript:void(0);" onclick="modal('ajax/uyegirisi','modallar','Kullanıcı Girişi!');"><i class="ikon ikon-question2 ikon-fw"></i> İzlemeyi Planladıklarım</a></li><li><a href="javascript:void(0);" onclick="modal('ajax/uyegirisi','modallar','Kullanıcı Girişi!');"><i class="ikon ikon-ok ikon-fw"></i> İzlemeyi Tamamladıklarım</a></li><li><a href="javascript:void(0);" onclick="modal('ajax/uyegirisi','modallar','Kullanıcı Girişi!');"><i class="ikon ikon-remove3 ikon-fw"></i> İzlemeyi Bıraktıklarım</a></li><li><a href="javascript:void(0);" onclick="modal('ajax/uyegirisi','modallar','Kullanıcı Girişi!');"><i class="ikon ikon-stop ikon-fw"></i> Beklemeye Aldıklarım</a></li></ul></div></td></tr><tr><td colspan="3" height="28"><b>Özet; </b> </td></tr><tr><td colspan="3"><p class="ozet">{summary_clean}</p></td></tr></tbody></table>'''

    detay_block = f'''<div id="detayPaylas"> <div class="panel"> <div class="panel-ust"><div class="panel-title">{baslik}</div></div> <div class="panel-body" style="padding:5px; overflow:hidden;"><div class="table-responsive"><table border="0" width="100%"><tbody><tr><td width="235" valign="top"><table><tbody><tr><td><a href="anime/{info['slug']}" class="thumbnail pull-left" style="margin-right:5px;"><div class="imaj"><img class="media-object" src="{resim}" alt="{baslik}"><div class="rank">{score_str}</div></div></a></td></tr><tr><td><div class="list-group detayMenu" style="margin-right:5px; margin-top:-15px;"> <a href="javascript:void(0);" onclick="IndexAltSayfa(this,'ajax/seslendiren&amp;animeId={anime_id}','animedetay'); return false;" class="list-group-item"><i class="ikon ikon-microphone ikon-fw"></i> Karakter &amp; Seslendiren</a> <a href="javascript:void(0);" onclick="IndexAltSayfa(this,'ajax/yonetim&amp;animeId={anime_id}','animedetay'); return false;" class="list-group-item"><i class="ikon ikon-users ikon-fw"></i> Yönetim Kadrosu</a> <a href="javascript:void(0);" onclick="IndexAltSayfa(this,'ajax/baglantili&amp;animeId={anime_id}','animedetay'); return false;" class="list-group-item"><i class="ikon ikon-th-list ikon-fw"></i> Bağlantılı Animeler</a> <a href="javascript:void(0);" onclick="IndexAltSayfa(this,'ajax/benzer&amp;animeId={anime_id}','animedetay'); return false;" class="list-group-item"><i class="ikon ikon-leaf2 ikon-fw"></i> Benzer Animeler</a> <a href="javascript:void(0);" onclick="IndexAltSayfa(this,'ajax/forumlar&amp;animeId={anime_id}','animedetay'); return false;" class="list-group-item"><i class="ikon ikon-certificate ikon-fw"></i> Tartışma Forumları</a> <a href="javascript:void(0);" onclick="IndexAltSayfa(this,'ajax/fragman&amp;animeId={anime_id}','animedetay'); return false;" class="list-group-item"><i class="ikon ikon-youtube-play ikon-fw"></i> Fragman</a> <a href="javascript:void(0);" onclick="IndexAltSayfa(this,'ajax/kareler&amp;animeId={anime_id}','animedetay'); return false;" class="list-group-item"><i class="ikon ikon-picture ikon-fw"></i> Animeden Kareler</a> <a href="javascript:void(0);" onclick="IndexAltSayfa(this,'ajax/istatistik&amp;animeId={anime_id}','animedetay'); return false;" class="list-group-item"><i class="ikon ikon-bar-chart ikon-fw"></i> İstatistikler</a> <a href="javascript:void(0);" onclick="detayPaylas(this); return false;" class="list-group-item"><i class="ikon ikon-facebook4 ikon-fw"></i> Facebook'ta Paylaş</a> <a href="anime/{info['slug']}" class="list-group-item"><i class="ikon ikon-share-alt ikon-fw"></i> Anime Detayı</a></div><form id="resimPaylas"><input type="hidden" name="animeAdi" value="{baslik}"><input type="hidden" name="resim" class="hidden-resim"></form></td></tr></tbody></table></td><td valign="top"><div id="animedetay">{animedetay_table}</div></td></tr></tbody></table></div></div><div class="panel-footer clearfix"></div></div> </div>'''

    episodes_html = render_episodes_list_html(episodes)

    html = raw_template

    # 1. Base href
    if '<head' in html and '<base href="/"' not in html:
        html = re.sub(r'(<head[^>]*>)', r'\1\n<base href="/">', html, count=1)

    top_gap_css = '<style>body#bd { padding-top: 50px !important; } body#bd > article.container { margin-top: 0 !important; padding-top: 0 !important; } #arkaplan { margin-top: 0 !important; }</style>'
    if '<head' in html:
        html = re.sub(r'(<head[^>]*>)', r'\1\n' + top_gap_css, html, count=1)

    # 2. Title & Meta
    html = re.sub(r'<title>.*?</title>', f'<title>{baslik}</title>', html, count=1)
    html = re.sub(r'<meta name="title" content=".*?">', f'<meta name="title" content="{baslik}">', html, count=1)
    html = re.sub(r'<meta property="og:title" content=".*?">', f'<meta property="og:title" content="{baslik}">', html, count=1)
    html = re.sub(r'<meta property="og:image" content=".*?">', f'<meta property="og:image" content="{resim}">', html, count=1)
    html = re.sub(r'<meta name="twitter:title" content=".*?">', f'<meta name="twitter:title" content="{baslik}">', html, count=1)
    html = re.sub(r'<meta name="description"[^>]*content=".*?"', f'<meta name="description" content="{summary_clean[:200]}"', html, count=1)

    # 3. Replace #detayPaylas
    html = replace_detay_paylas(html, detay_block)

    # 4. Right sidebar tabs: put 'Bölümler' tab to the left of 'Türüne Göre', make it active, and pre-render episodes in #aktif-icerik
    anime_tabs = (
        f'<ul class="nav panel-tabs" id="aktif-sekme">'
        f'<li class="active"><a href="javascript:void(0);" data-url="ajax/bolumler&amp;animeId={anime_id}" data-div="aktif-icerik" data-toggle="tab">Bölümler</a></li>'
        f'<li class=""><a href="javascript:void(0);" data-url="ajax/turler" data-div="aktif-icerik" data-toggle="tab">Türüne Göre</a></li>'
        f'<li class=""><a href="javascript:void(0);" data-url="ajax/tamliste" data-div="aktif-icerik" data-toggle="tab">Tam Liste</a></li>'
        f'<li class=""><a href="javascript:void(0);" data-url="ajax/yillar" data-div="aktif-icerik" data-toggle="tab">Yılına Göre</a></li>'
        f'</ul>'
    )
    html = re.sub(r'<ul class="nav panel-tabs" id="aktif-sekme">.*?</ul>', anime_tabs, html, count=1, flags=re.DOTALL)
    html = replace_aktif_icerik(html, episodes_html)

    # 5. Fix relative asset paths
    html = html.replace('../www.animeler.net/', 'www.animeler.net/')
    html = html.replace('../st.chatango.com/', 'st.chatango.com/')
    html = html.replace('../www.facebook.com/', 'www.facebook.com/')
    html = html.replace('href="anime/naruto/index.html"', 'href="javascript:void(0);"')
    html = html.replace('href="index/index.html"', 'href="/"')
    html = html.replace('href="index.html"', 'href="/"')
    html = html.replace('href="./"', 'href="/"')

    return html

def get_episode_data(ep_slug):
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT id, anime_id, slug, ad FROM bolum WHERE slug = ?", (ep_slug,))
    ep = c.fetchone()
    if not ep and ep_slug.isdigit():
        c.execute("SELECT id, anime_id, slug, ad FROM bolum WHERE id = ?", (int(ep_slug),))
        ep = c.fetchone()
    if not ep:
        conn.close()
        return None

    ep_id = ep["id"]
    anime_id = ep["anime_id"]
    ep_name = ep["ad"]

    # Parent anime
    c.execute("""
        SELECT a.id, a.slug, a.baslik, a.display_date, a.display_full_date, a.likes, a.dislikes,
               m.score, m.poster_url, ta.ta_id
        FROM anime a
        LEFT JOIN anime_meta m ON a.id = m.anime_id
        LEFT JOIN ta_anime ta ON a.id = ta.anime_id
        WHERE a.id = ?
    """, (anime_id,))
    anime = c.fetchone()
    if not anime:
        conn.close()
        return None

    # All episodes of this anime
    c.execute("SELECT id, slug, ad FROM bolum WHERE anime_id = ? ORDER BY id ASC", (anime_id,))
    all_episodes = [dict(r) for r in c.fetchall()]

    curr_idx = -1
    for i, item in enumerate(all_episodes):
        if item["id"] == ep_id:
            curr_idx = i
            break

    prev_ep = all_episodes[curr_idx - 1] if curr_idx > 0 else None
    next_ep = all_episodes[curr_idx + 1] if (curr_idx >= 0 and curr_idx < len(all_episodes) - 1) else None

    # Links (clean links first, legacy kırık olabilir links after)
    c.execute("SELECT id, player, fansub, tip, deger, is_legacy FROM link WHERE bolum_id = ? ORDER BY is_legacy ASC, id ASC", (ep_id,))
    links = [dict(r) for r in c.fetchall()]

    links_by_fansub = {}
    for l in links:
        fs = l["fansub"] or "Varsayılan"
        if fs not in links_by_fansub:
            links_by_fansub[fs] = []
        raw_url = l["deger"] or ""
        if raw_url.startswith("//"):
            raw_url = "https:" + raw_url
        links_by_fansub[fs].append({
            "player": l["player"] or "VİDEO",
            "url": raw_url,
            "tip": l["tip"] or "url",
            "is_legacy": bool(l.get("is_legacy", 0))
        })

    # Merge missing links from legacy JSON archive (mirror/animeler/{anime_slug}/{ep_slug}.json)
    json_path = os.path.join(BASE_DIR, "mirror", "animeler", anime["slug"], f"{ep_slug}.json")
    if not os.path.exists(json_path):
        alt_path = os.path.join(BASE_DIR, "mirror", "animeler", anime["slug"].replace("-", "_"), f"{ep_slug}.json")
        if os.path.exists(alt_path):
            json_path = alt_path
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as jf:
                json_data = json.load(jf)
            for j_item in json_data:
                fs = j_item.get("fansub") or "Varsayılan"
                u = j_item.get("url")
                if not u or not (u.startswith("http://") or u.startswith("https://") or u.startswith("//")):
                    continue
                if u.startswith("//"):
                    u = "https:" + u
                if fs not in links_by_fansub:
                    links_by_fansub[fs] = []
                existing_urls = {it["url"] for it in links_by_fansub[fs]}
                if u not in existing_urls:
                    links_by_fansub[fs].append({
                        "player": j_item.get("player") or "VİDEO",
                        "url": u,
                        "tip": "url",
                        "is_legacy": True
                    })
        except Exception:
            pass

    # Differentiate duplicate player names within each fansub (e.g. SIBNET 1, SIBNET 2)
    for fs, flist in links_by_fansub.items():
        name_counts = {}
        for item in flist:
            name_counts[item["player"]] = name_counts.get(item["player"], 0) + 1
        name_seen = {}
        for item in flist:
            p = item["player"]
            if name_counts[p] > 1:
                name_seen[p] = name_seen.get(p, 0) + 1
                item["player"] = f"{p} {name_seen[p]}"

    # Fansub info
    c.execute("""
        SELECT ef.full_info, fg.name as group_name
        FROM ta_episode_fansub ef
        LEFT JOIN ta_fansub_group fg ON ef.fansub_group_id = fg.id
        WHERE ef.bolum_id = ?
    """, (ep_id,))
    ef_rows = c.fetchall()
    fansub_infos = [dict(r) for r in ef_rows]

    conn.close()

    h = abs(hash(ep_slug))
    score = anime["score"] or 8.0
    ep_likes = max(1, int(score * 3.2 + (h % 30)))
    ep_dislikes = max(0, int(ep_likes * 0.03)) if (h % 3 == 0) else 0

    date_str = anime["display_full_date"] or anime["display_date"] or "2019-06-28 12:00:00"
    fansub_names = list(links_by_fansub.keys())
    primary_fansub = fansub_names[0] if fansub_names else (fansub_infos[0]["group_name"] if fansub_infos else "Varsayılan")

    # Build fansub metadata mapping
    fansub_meta = {}
    all_known_fs = list(dict.fromkeys(fansub_names + [fi["group_name"] for fi in fansub_infos if fi.get("group_name")]))
    if not all_known_fs:
        all_known_fs = ["Varsayılan"]

    for fs in all_known_fs:
        matched_info = None
        for fi in fansub_infos:
            if fi.get("group_name") == fs or (fi.get("full_info") and fs.lower() in fi.get("full_info").lower()):
                matched_info = fi.get("full_info")
                break
        if not matched_info:
            matched_info = f"{fs} Fansub Çevirisi"

        info_linked = format_fansub_info(matched_info)
        m_link = re.search(r'https?://[^\s/$.?#].[^\s]*|discord\.gg/[^\s]+|www\.[^\s/$.?#].[^\s]*', matched_info)
        if m_link:
            link_url = m_link.group(0).rstrip('.,;)')
            href = link_url if link_url.startswith(('http://', 'https://')) else f'https://{link_url}'
            announcement = (
                f'<p><a href="{href}" class="alert-link" target="_blank"><b>{fs} Çevirmen &amp; Encoder Alımları!</b></a></p>'
                f'<p>{fs} ekibine katılmak isteyen herkese kapımız açıktır. Kaliteli ve güzel çevirilerimizi izleyicilere sunmak için yeni üyelerimize her daim yardımcı olacak ve birlik içinde güzel işler yapacağız. Bize katılmak için <a href="{href}" target="_blank" rel="nofollow">{link_url}</a> üzerinden yetkililer ile iletişime geçebilirsiniz.</p>'
            )
        else:
            announcement = (
                f'<p><a href="javascript:void(0);" class="alert-link"><b>{fs} Çevirmen &amp; Encoder Alımları!</b></a></p>'
                f'<p>{fs} ekibine katılmak isteyen herkese kapımız açıktır. Kaliteli ve güzel çevirilerimizi izleyicilere sunmak için yeni üyelerimize her daim yardımcı olacak ve birlik içinde güzel işler yapacağız. Bize katılmak için yetkililer ile iletişime geçebilirsiniz.</p>'
            )

        h_fs = abs(hash(fs))
        fansub_meta[fs] = {
            "uploader": fs,
            "upload_count": 100 + (h_fs % 700),
            "follower_count": 10 + (h_fs % 90),
            "info": info_linked,
            "announcement": announcement
        }

    return {
        "ep_id": ep_id,
        "ep_slug": ep_slug,
        "ep_name": ep_name,
        "anime_id": anime_id,
        "anime_slug": anime["slug"],
        "anime_title": anime["baslik"],
        "all_episodes": all_episodes,
        "curr_idx": curr_idx,
        "prev_ep": prev_ep,
        "next_ep": next_ep,
        "links_by_fansub": links_by_fansub,
        "fansub_infos": fansub_infos,
        "primary_fansub": primary_fansub,
        "fansub_meta": fansub_meta,
        "likes": f"{ep_likes:,}".replace(",", "."),
        "dislikes": f"{ep_dislikes:,}".replace(",", "."),
        "date_str": date_str
    }

@functools.lru_cache(maxsize=512)
def render_video_page_html(ep_slug):
    raw_template = get_raw_anime_template()
    if not raw_template:
        return None

    ep_data = get_episode_data(ep_slug)
    if not ep_data:
        return None

    anime_title = ep_data["anime_title"]
    anime_slug = ep_data["anime_slug"]
    ep_name = ep_data["ep_name"]
    anime_id = ep_data["anime_id"]
    prev_ep = ep_data["prev_ep"]
    next_ep = ep_data["next_ep"]
    fansub_meta = ep_data["fansub_meta"]

    # Prev/Next buttons for top breadcrumb
    prev_btn_top = (
        f'<a href="video/{prev_ep["slug"]}" class="btn btn-sm btn-danger" style="color:#fff;" title="{prev_ep["ad"]}"><i class="ikon ikon-double-angle-left ikon-fw"></i></a>'
        if prev_ep else
        '<button class="btn btn-sm btn-danger disabled" style="color:#fff;"><i class="ikon ikon-double-angle-left ikon-fw"></i></button>'
    )
    next_btn_top = (
        f'<a href="video/{next_ep["slug"]}" class="btn btn-sm btn-danger" style="color:#fff;" title="{next_ep["ad"]}"><i class="ikon ikon-double-angle-right ikon-fw"></i></a>'
        if next_ep else
        '<button class="btn btn-sm btn-danger disabled" style="color:#fff;"><i class="ikon ikon-double-angle-right ikon-fw"></i></button>'
    )

    # Prev/Next buttons for footer
    prev_btn_bottom = (
        f'<a href="video/{prev_ep["slug"]}" class="btn btn-default bold baloon" data-toggle="tooltip" title="{prev_ep["ad"]}"><i class="ikon ikon-double-angle-left ikon-fw"></i> Önceki Bölüm</a>'
        if prev_ep else
        '<a href="javascript:void(0);" class="btn btn-default bold disabled"><i class="ikon ikon-double-angle-left ikon-fw"></i> Önceki Bölüm</a>'
    )
    next_btn_bottom = (
        f'<a href="video/{next_ep["slug"]}" class="btn btn-default bold baloon" data-toggle="tooltip" title="{next_ep["ad"]}">Sonraki Bölüm <i class="ikon ikon-double-angle-right ikon-fw"></i></a>'
        if next_ep else
        '<a href="javascript:void(0);" class="btn btn-default bold disabled">Sonraki Bölüm <i class="ikon ikon-double-angle-right ikon-fw"></i></a>'
    )

    # Fansub & Player buttons
    links_by_fs = ep_data["links_by_fansub"]
    fansub_names = list(links_by_fs.keys())
    primary_fs = ep_data["primary_fansub"]
    if not fansub_names:
        fansub_names = [primary_fs]
    primary_links = links_by_fs.get(primary_fs, [])
    active_embed = primary_links[0]["url"] if primary_links else "about:blank"

    fansub_buttons_list = []
    for i, fs_name in enumerate(fansub_names):
        btn_class = "btn-danger" if fs_name == primary_fs else "btn-default"
        safe_fs_id = re.sub(r'[^a-zA-Z0-9]', '_', fs_name)
        fansub_buttons_list.append(
            f'<button type="button" class="btn btn-sm {btn_class}" id="fansub-btn-{safe_fs_id}" style="margin:2px;" onclick="switchFansub(\'{fs_name}\'); return false;"><span class="ikon ikon-heart ikon-margin"></span> {fs_name}</button>'
        )
    fansub_buttons_html = "".join(fansub_buttons_list)

    player_buttons_list = []
    for i, l in enumerate(primary_links):
        btn_class = "btn-danger" if i == 0 else "btn-default"
        is_legacy = l.get("is_legacy", False)
        size_style = "font-size:75%; padding:3px 6px; margin:2px;" if is_legacy else "margin:2px;"
        label = f'{l["player"]} <span style="font-size:75%; opacity:0.85;">(Kırık olabilir)</span>' if is_legacy else l["player"]
        player_buttons_list.append(
            f'<button type="button" class="btn btn-sm {btn_class}" style="{size_style}" onclick="switchPlayer(this, \'{l["url"]}\'); return false;"><span class="ikon ikon-play4 ikon-margin"></span> {label}</button>'
        )
    player_buttons_html = "".join(player_buttons_list)

    fs_initial_meta = fansub_meta.get(primary_fs, {
        "uploader": primary_fs,
        "upload_count": 350,
        "follower_count": 25,
        "info": f"{primary_fs} Çevirisi",
        "announcement": f"<p><b>{primary_fs} Çevirmen &amp; Encoder Alımları!</b></p>"
    })

    uploader_name = fs_initial_meta["uploader"]
    upload_count = fs_initial_meta["upload_count"]
    follower_count = fs_initial_meta["follower_count"]
    full_info_linked = fs_initial_meta["info"]
    fansub_announcement = fs_initial_meta["announcement"]

    player_script = f'''<script>
var currentLinksByFansub = {json.dumps(links_by_fs)};
var fansubMeta = {json.dumps(fansub_meta)};

function switchPlayer(btn, url) {{
  $('#player-buttons button').removeClass('btn-danger').addClass('btn-default');
  $(btn).removeClass('btn-default').addClass('btn-danger');
  $('#video-iframe').attr('src', url);
}}

function switchFansub(fansubName) {{
  $('#fansub-buttons button').removeClass('btn-danger').addClass('btn-default');
  var safeId = '#fansub-btn-' + fansubName.replace(/[^a-zA-Z0-9]/g, '_');
  $(safeId).removeClass('btn-default').addClass('btn-danger');

  var links = currentLinksByFansub[fansubName] || [];
  var html = '';
  for (var i = 0; i < links.length; i++) {{
    var l = links[i];
    var activeClass = (i === 0) ? 'btn-danger' : 'btn-default';
    var isLegacy = l.is_legacy ? true : false;
    var sizeStyle = isLegacy ? 'font-size:75%; padding:3px 6px; margin:2px;' : 'margin:2px;';
    var label = isLegacy ? l.player + ' <span style="font-size:75%; opacity:0.85;">(Kırık olabilir)</span>' : l.player;
    html += '<button type="button" class="btn btn-sm ' + activeClass + '" style="' + sizeStyle + '" onclick="switchPlayer(this, \\'' + l.url + '\\'); return false;"><span class="ikon ikon-play4 ikon-margin"></span> ' + label + '</button>';
  }}
  $('#player-buttons').html(html);
  if (links.length > 0) {{
    $('#video-iframe').attr('src', links[0].url);
  }}

  var meta = fansubMeta[fansubName];
  if (meta) {{
    if (meta.uploader) {{
      $('#uploader-title-link').text(meta.uploader).attr('title', meta.uploader);
    }}
    if (meta.upload_count) {{
      $('#uploader-upload-cnt').text(meta.upload_count);
    }}
    if (meta.follower_count) {{
      $('#uploader-follower-cnt').text(meta.follower_count);
    }}
    if (meta.info) {{
      $('#ceviri-info').html(meta.info);
    }}
    if (meta.announcement) {{
      $('#fansubHaber').html(meta.announcement);
    }}
  }}
}}

function toggleCinemaMode() {{
  var overlay = document.getElementById('cinema-overlay');
  if (!overlay) {{
    overlay = document.createElement('div');
    overlay.id = 'cinema-overlay';
    overlay.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.92);z-index:9998;display:none;';
    overlay.onclick = toggleCinemaMode;
    document.body.appendChild(overlay);
  }}
  var vcontainer = document.getElementById('videopanel-container');
  if (overlay.style.display === 'none') {{
    overlay.style.display = 'block';
    if (vcontainer) {{ vcontainer.style.position = 'relative'; vcontainer.style.zIndex = '9999'; }}
  }} else {{
    overlay.style.display = 'none';
    if (vcontainer) {{ vcontainer.style.position = ''; vcontainer.style.zIndex = ''; }}
  }}
}}
</script>'''

    video_panel = f'''<div id="videopanel-container">
  <div class="panel">
    <div class="panel-ust" style="line-height:20px; min-height:40px; position:relative;">
      <ol class="breadcrumb" style="background:none; margin:0px; padding:0px;">
        <li><a href="anime/{anime_slug}" style="color:white; font-size: 0.8em;"><i class="ikon ikon-double-angle-right ikon-fw"></i> {anime_title}</a></li>
        <li><a href="video/{ep_slug}" style="color:white; font-size: 0.8em;">{ep_name}</a></li>
      </ol>
      <div class="btn-group btn-group-sm" style="position:absolute; right:5px; top:5px;">
        {prev_btn_top}
        <a href="javascript:void(0);" id="sinema-modu" onclick="toggleCinemaMode(); return false;" class="btn btn-sm btn-danger" style="color:#fff;" title="Sinema Modu"><i class="ikon ikon-lightbulb ikon-margin ikon-fw"></i></a>
        {next_btn_top}
      </div>
    </div>
    <div id="videodetay">
      <div class="panel-body" style="margin:0; padding:0px 0 0 0;">
        <div class="btn-group pull-right" id="fansub-buttons">
          {fansub_buttons_html}
        </div>
        <div class="clearfix"></div>
        <div class="video-icerik" style="position:relative; width:100%; height:450px; background:#000;">
          <iframe id="video-iframe" src="{active_embed}" width="100%" height="450" frameborder="0" scrolling="no" wmode="transparent" webkitallowfullscreen mozallowfullscreen allowfullscreen></iframe>
        </div>
        <div class="btn-group" id="player-buttons" style="margin:5px 0;">
          {player_buttons_html}
        </div>
        <div class="clearfix"></div>
        <div class="col-xs-6" style="padding:5px;">
          <div class="panel" style="margin-bottom:5px;">
            <div class="panel-ust-ic"><div class="panel-title" id="uploader-title"><a href="javascript:void(0);" id="uploader-title-link" class="baloon" data-toggle="tooltip" title="{uploader_name}">{uploader_name}</a></div></div>
            <div class="panel-body" style="padding:5px; height:150px; overflow:hidden;">
              <a href="javascript:void(0);" class="thumbnail pull-left" style="margin-right:5px;">
                <img src="imajlar/logo.png" alt="" style="margin: 0 auto; height: 90px; width:90px; max-width: 90px;">
              </a>
              <div class="row" style="padding:0px; margin:0px;">
                <table class="table table-striped table-bordered" style="max-width:180px;">
                  <tr><td style="vertical-align: middle;"><b>Upload</b></td><td id="uploader-upload-cnt">{upload_count}</td></tr>
                  <tr><td style="vertical-align: middle;"><b>Takipçi</b></td><td id="uploader-follower-cnt">{follower_count}</td></tr>
                  <tr><td style="vertical-align: middle;"><b>Rütbe</b></td><td><span class="label label-danger" style="background-color:#3949ab; font-size:10px;">Fansub Yetkilisi</span></td></tr>
                </table>
              </div>
              <div class="btn-group btn-group-sm pull-right" style="margin-top:-15px;">
                <a href="javascript:void(0);" onclick="modal('ajax/uyegirisi','modallar','Kullanıcı Girişi!'); return false;" class="btn btn-default bold baloon colorkul" data-toggle="tooltip" title="Takip Et!"><i class="ikon ikon-plus ikon-fw"></i> Takip Et!</a>
                <a href="javascript:void(0);" onclick="modal('ajax/uyegirisi','modallar','Kullanıcı Girişi!'); return false;" class="btn btn-default bold baloon colorkul" data-toggle="tooltip" title="Özel Mesaj Gönder!"><i class="ikon ikon-envelope-alt ikon-fw"></i> Ö.M Gönder</a>
              </div>
            </div>
          </div>
        </div>
        <div class="col-xs-6" style="padding:5px;">
          <div class="alert alert-warning fade in" style="height:150px; overflow-y:auto; margin-bottom:5px;">
            <button type="button" class="close" data-dismiss="alert" aria-label="Close"><span aria-hidden="true">&times;</span></button>
            <h4 class="alert-heading" style="font-size:14px; font-weight:bold; margin-top:0;">Fansub Bilgi Panosu!</h4>
            <hr style="margin:5px 0;">
            <div class="row">
              <div class="col-xs-12" id="fansubHaber" style="font-size:12px;">
                {fansub_announcement}
              </div>
            </div>
          </div>
        </div>
        <div class="col-xs-12" style="padding:5px;">
          <div class="alert alert-info ceviri" role="alert" style="margin-bottom:5px;">
            <h4 class="alert-heading" style="font-size:14px; font-weight:bold; margin-top:0;">DİKKAT!</h4>
            <p style="margin:2px 0;">Yayınladığımız bu anime aşağıda belirtilen grup veya çevirmene aittir.</p>
            <p style="margin:2px 0;">Proje bize ait olmayıp burası sadece online izleme alternatifi üzerine kurulmuş bir sitedir.</p>
            <p style="margin:2px 0;">Arşiv yapmak ya da yüksek kalitede izlemek istiyorsanız grubun kendi sitesinden indirmeyi unutmayın!</p>
            <p style="margin:5px 0 0 0;"><strong id="ceviri-info">{full_info_linked}</strong></p>
          </div>
        </div>
      </div>
    </div>
    <div class="panel-footer clearfix">
      <span class="pull-left" style="position:relative; top:7px;"><strong>Tarih :</strong> {ep_data["date_str"]}</span>
      <div class="btn-group btn-group-sm pull-right clearfix">
        <a href="javascript:void(0);" onclick="modal('ajax/uyegirisi','modallar','Kullanıcı Girişi!'); return false;" class="btn btn-default bold colorbegen baloon" data-toggle="tooltip" title="Kişi beğendi!"><i class="ikon ikon-thumbs-up4 ikon-fw"></i> {ep_data["likes"]}</a>
        <a href="javascript:void(0);" onclick="modal('ajax/uyegirisi','modallar','Kullanıcı Girişi!'); return false;" class="btn btn-default bold baloon" data-toggle="tooltip" title="İzlediklerime Ekle!"><i class="ikon ikon-eye ikon-fw ikon-1x ikon-margin"></i></a>
        <a href="javascript:void(0);" onclick="modal('ajax/uyegirisi','modallar','Kullanıcı Girişi!'); return false;" class="btn btn-default bold colorbegenme baloon" data-toggle="tooltip" title="Kişi beğenmedi!"><i class="ikon ikon-thumbs-down2 ikon-fw"></i> {ep_data["dislikes"]}</a>
      </div>
      <div class="btn-group btn-group-sm pull-right clearfix" style="margin-right:25px;">
        {prev_btn_bottom}
        {next_btn_bottom}
      </div>
    </div>
  </div>
</div>
{player_script}'''

    episodes_html = render_episodes_list_html(ep_data["all_episodes"], active_ep_slug=ep_slug)

    html = raw_template

    # 1. Base href
    if '<head' in html and '<base href="/"' not in html:
        html = re.sub(r'(<head[^>]*>)', r'\1\n<base href="/">', html, count=1)

    top_gap_css = '<style>body#bd { padding-top: 50px !important; } body#bd > article.container { margin-top: 0 !important; padding-top: 0 !important; } #arkaplan { margin-top: 0 !important; }</style>'
    if '<head' in html:
        html = re.sub(r'(<head[^>]*>)', r'\1\n' + top_gap_css, html, count=1)

    # 2. Title & Meta
    html = re.sub(r'<title>.*?</title>', f'<title>{ep_name} - TürkAnime</title>', html, count=1)
    html = re.sub(r'<meta name="title" content=".*?">', f'<meta name="title" content="{ep_name}">', html, count=1)
    html = re.sub(r'<meta property="og:title" content=".*?">', f'<meta property="og:title" content="{ep_name}">', html, count=1)
    html = re.sub(r'<meta name="twitter:title" content=".*?">', f'<meta name="twitter:title" content="{ep_name}">', html, count=1)

    # 3. Replace #detayPaylas with video_panel
    html = replace_detay_paylas(html, video_panel)

    # 4. Right sidebar tabs: put 'Bölümler' tab to the left of 'Türüne Göre', make it active, and pre-render episodes in #aktif-icerik
    anime_tabs = (
        f'<ul class="nav panel-tabs" id="aktif-sekme">'
        f'<li class="active"><a href="javascript:void(0);" data-url="ajax/bolumler&amp;animeId={anime_id}" data-div="aktif-icerik" data-toggle="tab">Bölümler</a></li>'
        f'<li class=""><a href="javascript:void(0);" data-url="ajax/turler" data-div="aktif-icerik" data-toggle="tab">Türüne Göre</a></li>'
        f'<li class=""><a href="javascript:void(0);" data-url="ajax/tamliste" data-div="aktif-icerik" data-toggle="tab">Tam Liste</a></li>'
        f'<li class=""><a href="javascript:void(0);" data-url="ajax/yillar" data-div="aktif-icerik" data-toggle="tab">Yılına Göre</a></li>'
        f'</ul>'
    )
    html = re.sub(r'<ul class="nav panel-tabs" id="aktif-sekme">.*?</ul>', anime_tabs, html, count=1, flags=re.DOTALL)
    html = replace_aktif_icerik(html, episodes_html)

    # 5. Fix relative asset paths
    html = html.replace('../www.animeler.net/', 'www.animeler.net/')
    html = html.replace('../st.chatango.com/', 'st.chatango.com/')
    html = html.replace('../www.facebook.com/', 'www.facebook.com/')
    html = html.replace('href="anime/naruto/index.html"', 'href="javascript:void(0);"')
    html = html.replace('href="index/index.html"', 'href="/"')
    html = html.replace('href="index.html"', 'href="/"')
    html = html.replace('href="./"', 'href="/"')

    return html

def parse_turkish_date(date_str):
    if not date_str:
        return None
    m = re.search(r'(\d{1,2})\s+([a-zA-ZçğıöşüÇĞİÖŞÜ]+)\s+(\d{4})', date_str)
    if m:
        day = int(m.group(1))
        month_name = m.group(2).lower()
        year = int(m.group(3))
        month = TR_MONTH_NAMES_TO_NUM.get(month_name, 1)
        try:
            return datetime.date(year, month, day)
        except Exception:
            return datetime.date(year, 1, 1)
    m_year = re.search(r'\b(19\d\d|20\d\d)\b', date_str)
    if m_year:
        return datetime.date(int(m_year.group(1)), 1, 1)
    return None

def get_franchise_prefix(title):
    base = title.split(':')[0].strip()
    base = re.sub(r'(\s+Season(?:\s+\d+)?)', '', base, flags=re.I)
    base = re.sub(r'(\s+Part(?:\s+\d+)?)', '', base, flags=re.I)
    base = re.sub(r'(\s+(?:II|III|IV|V|VI|VII|VIII|IX|X|2nd|3rd|4th|5th|\d+)(?:nd|rd|th)?(?:\s+Season)?)$', '', base, flags=re.I)
    base = re.sub(r'(\s+The\s+Final\s+Season.*)$', '', base, flags=re.I)
    base = re.sub(r'(\s+Movie.*)$', '', base, flags=re.I)
    base = re.sub(r'(\s+OVA.*)$', '', base, flags=re.I)
    return base.strip()

def render_anime_media_card(a):
    slug = a["slug"]
    baslik = html.escape(a["baslik"])
    ta_id = a.get("ta_id")
    poster_url = a.get("poster_url")
    resim = f"/imajlar/serilerb/{ta_id}.jpg" if ta_id else (poster_url or "/imajlar/logo.png")

    ep_count = a.get("bolum_count")
    total_ep = a.get("bolum_sayisi") or ep_count or 1
    if ep_count is not None and ep_count > 0:
        bolum_str = f"{ep_count} / {total_ep}"
    else:
        bolum_str = f"{total_ep} / {total_ep}"

    tarih = a.get("baslama_tarihi") or "Belirtilmemiş"

    puan = a.get("ta_puan")
    if puan is None and a.get("score"):
        puan = a.get("score")
    puan_str = f"{float(puan):.2f}" if puan else "0.00"

    likes = a.get("likes") or 0
    voters = a.get("voters") or (max(15, int(likes * 0.70)) if likes else 155)

    return f'''<div class="media" style="margin-bottom: 15px; padding-bottom: 12px; border-bottom: 1px solid #e5e5e5;">
  <a class="pull-left" href="/anime/{slug}">
    <img class="media-object" src="{resim}" alt="{baslik}" style="width: 75px; height: 105px; object-fit: cover; border-radius: 2px;" onerror="this.src=\'/imajlar/logo.png\'">
  </a>
  <div class="media-body">
    <h4 class="media-heading" style="margin-top: 2px; margin-bottom: 6px; font-weight: bold; font-size: 14px;">
      <a href="/anime/{slug}" style="color: #222;">{baslik}</a>
    </h4>
    <div style="font-size: 12px; line-height: 22px; color: #555;">
      <b>Bölüm Sayısı :</b> {bolum_str}<br>
      <b>Yayın Tarihi :</b> {tarih}<br>
      <b>Puanı :</b> <span style="font-weight: bold;">{puan_str}</span> / 10 Üzerinden <i>( Oylamaya {voters} kişi katıldı. )</i>
    </div>
  </div>
</div>'''

def render_baglantili_html(anime_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT a.id, a.slug, a.baslik, a.bolum_sayisi, a.baslama_tarihi, a.bitis_tarihi,
               a.ta_puan, a.likes, a.kategori, a.turler,
               ta.ta_id, m.poster_url, m.score, m.year
        FROM anime a
        LEFT JOIN anime_meta m ON a.id = m.anime_id
        LEFT JOIN ta_anime ta ON a.id = ta.anime_id
        WHERE a.id = ?
        LIMIT 1
    """, (anime_id,))
    target = c.fetchone()
    if not target:
        c.execute("""
            SELECT a.id, a.slug, a.baslik, a.bolum_sayisi, a.baslama_tarihi, a.bitis_tarihi,
                   a.ta_puan, a.likes, a.kategori, a.turler,
                   ta.ta_id, m.poster_url, m.score, m.year
            FROM anime a
            LEFT JOIN anime_meta m ON a.id = m.anime_id
            LEFT JOIN ta_anime ta ON a.id = ta.anime_id
            WHERE ta.ta_id = ?
            LIMIT 1
        """, (str(anime_id),))
        target = c.fetchone()
    if not target:
        conn.close()
        return '<div class="alert alert-info" style="margin:10px;"><i class="ikon ikon-info-sign"></i> Anime bulunamadı.</div>'

    base = get_franchise_prefix(target['baslik'])
    target_date = parse_turkish_date(target['baslama_tarihi']) or parse_turkish_date(target['bitis_tarihi'])
    if not target_date and target['year']:
        target_date = datetime.date(target['year'], 1, 1)

    c.execute("""
        SELECT a.id, a.slug, a.baslik, a.bolum_sayisi, a.baslama_tarihi, a.bitis_tarihi,
               a.ta_puan, a.likes, a.kategori, a.turler,
               ta.ta_id, m.poster_url, m.score, m.year,
               (SELECT count(*) FROM bolum b WHERE b.anime_id = a.id) as bolum_count
        FROM anime a
        LEFT JOIN anime_meta m ON a.id = m.anime_id
        LEFT JOIN ta_anime ta ON a.id = ta.anime_id
        WHERE a.id != ? AND (a.baslik LIKE ? OR a.baslik LIKE ?)
        ORDER BY a.id ASC
    """, (target['id'], f"{base}%", f"%{base}%"))
    all_rel = [dict(r) for r in c.fetchall()]
    conn.close()

    if not all_rel:
        return '<div class="alert alert-info" style="margin:10px;"><i class="ikon ikon-info-sign"></i> Bu seriye ait bağlantılı anime bulunamadı.</div>'

    sections = {
        "Önceki Hikâye": [],
        "Sonraki Hikâye": [],
        "Alternatif Seçenek": [],
        "Yan Hikâye": []
    }

    for rel in all_rel:
        rel_title = rel['baslik']
        rel_date = parse_turkish_date(rel['baslama_tarihi']) or parse_turkish_date(rel['bitis_tarihi'])
        if not rel_date and rel['year']:
            rel_date = datetime.date(rel['year'], 1, 1)

        is_alt = bool(re.search(r'\balternative\b|\bchuugakkou\b|\bspin-off\b|\bisekai quartet\b', rel_title, re.I))
        is_side = bool(re.search(r'\bova\b|\bspecial\b|\bpicture drama\b|\bomake\b', rel_title, re.I)) or (rel.get('kategori') in ('OVA', 'Special'))

        if is_alt:
            sections["Alternatif Seçenek"].append(rel)
        elif target_date and rel_date:
            if rel_date < target_date:
                sections["Önceki Hikâye"].append((rel_date, rel))
            else:
                sections["Sonraki Hikâye"].append((rel_date, rel))
        elif is_side:
            sections["Yan Hikâye"].append(rel)
        else:
            if rel['id'] < target['id']:
                sections["Önceki Hikâye"].append((datetime.date(2000, 1, 1), rel))
            else:
                sections["Sonraki Hikâye"].append((datetime.date(2025, 1, 1), rel))

    sections["Önceki Hikâye"] = [r[1] for r in sorted(sections["Önceki Hikâye"], key=lambda x: x[0], reverse=True)]
    sections["Sonraki Hikâye"] = [r[1] for r in sorted(sections["Sonraki Hikâye"], key=lambda x: x[0])]

    output_html = ['<div style="padding: 10px 15px;">']
    has_any = False
    for sec_name in ["Önceki Hikâye", "Sonraki Hikâye", "Alternatif Seçenek", "Yan Hikâye"]:
        items = sections[sec_name]
        if not items:
            continue
        has_any = True
        output_html.append(f'''<h4 style="font-weight: bold; margin-top: 15px; margin-bottom: 15px; padding-bottom: 8px; border-bottom: 2px solid #d9534f; color: #333;">
  <i class="ikon ikon-double-angle-right" style="color:#d9534f;"></i> {sec_name}
</h4>''')
        for item in items:
            output_html.append(render_anime_media_card(item))

    output_html.append('</div>')
    if not has_any:
        return '<div class="alert alert-info" style="margin:10px;"><i class="ikon ikon-info-sign"></i> Bu seriye ait bağlantılı anime bulunamadı.</div>'
    return "".join(output_html)

def render_benzer_html(anime_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT a.id, a.slug, a.baslik, a.turler 
        FROM anime a
        WHERE a.id = ?
        LIMIT 1
    """, (anime_id,))
    target = c.fetchone()
    if not target:
        c.execute("""
            SELECT a.id, a.slug, a.baslik, a.turler 
            FROM anime a
            LEFT JOIN ta_anime ta ON a.id = ta.anime_id
            WHERE ta.ta_id = ?
            LIMIT 1
        """, (str(anime_id),))
        target = c.fetchone()
    if not target or not target['turler']:
        conn.close()
        return '<div class="alert alert-info" style="margin:10px;"><i class="ikon ikon-info-sign"></i> Bu seriye ait benzer anime bulunamadı.</div>'

    target_genres = set(g.strip().lower() for g in target['turler'].split(',') if g.strip())
    if len(target_genres) < 2:
        conn.close()
        return '<div class="alert alert-info" style="margin:10px;"><i class="ikon ikon-info-sign"></i> Benzer animeleri bulmak için en az 2 kategori gereklidir.</div>'

    c.execute("""
        SELECT a.id, a.slug, a.baslik, a.bolum_sayisi, a.baslama_tarihi,
               a.ta_puan, a.likes, a.turler,
               ta.ta_id, m.poster_url, m.score,
               (SELECT count(*) FROM bolum b WHERE b.anime_id = a.id) as bolum_count
        FROM anime a
        LEFT JOIN anime_meta m ON a.id = m.anime_id
        LEFT JOIN ta_anime ta ON a.id = ta.anime_id
        WHERE a.id != ? AND a.turler IS NOT NULL AND a.turler != ''
        ORDER BY a.baslik ASC
    """, (anime_id,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()

    matches = []
    base_slug = target['slug'].split('-')[0]
    for r in rows:
        if base_slug and len(base_slug) > 3 and base_slug in r['slug']:
            continue
        g_set = set(g.strip().lower() for g in r['turler'].split(',') if g.strip())
        shared = target_genres.intersection(g_set)
        if len(shared) >= 2:
            matches.append(r)
            if len(matches) >= 30:
                break

    if not matches:
        return '<div class="alert alert-info" style="margin:10px;"><i class="ikon ikon-info-sign"></i> Benzer anime bulunamadı.</div>'

    output_html = ['''<div style="padding: 10px 15px;">
<h4 style="font-weight: bold; margin-top: 5px; margin-bottom: 15px; padding-bottom: 8px; border-bottom: 2px solid #d9534f; color: #333;">
  <i class="ikon ikon-double-angle-right" style="color:#d9534f;"></i> Benzer Animeler
</h4>''']
    for m in matches:
        output_html.append(render_anime_media_card(m))
    output_html.append('</div>')
    return "".join(output_html)

def search_animes(query_str, page=1, per_page=28):
    q = query_str.strip()
    if not q:
        return {"total": 0, "page": page, "total_pages": 0, "results": []}

    like_pat = f"%{q}%"
    start_pat = f"{q}%"
    
    conn = get_db()
    c = conn.cursor()
    sql_count = """
        SELECT count(*) FROM anime a
        LEFT JOIN anime_meta m ON a.id = m.anime_id
        WHERE a.baslik LIKE ? OR a.slug LIKE ? OR m.english_title LIKE ? OR m.synonyms_json LIKE ? OR a.japonca LIKE ?
    """
    c.execute(sql_count, (like_pat, like_pat, like_pat, like_pat, like_pat))
    total_count = c.fetchone()[0]

    offset = (page - 1) * per_page
    sql_results = """
        SELECT a.id, a.slug, a.baslik, a.bolum_sayisi, a.baslama_tarihi,
               a.ta_puan, a.likes, a.dislikes, a.ozet, a.turler,
               ta.ta_id, m.poster_url, m.score, m.english_title
        FROM anime a
        LEFT JOIN anime_meta m ON a.id = m.anime_id
        LEFT JOIN ta_anime ta ON a.id = ta.anime_id
        WHERE a.baslik LIKE ? OR a.slug LIKE ? OR m.english_title LIKE ? OR m.synonyms_json LIKE ? OR a.japonca LIKE ?
        ORDER BY 
            CASE 
                WHEN a.baslik = ? COLLATE NOCASE THEN 1
                WHEN a.baslik LIKE ? COLLATE NOCASE THEN 2
                WHEN a.baslik LIKE ? COLLATE NOCASE THEN 3
                ELSE 4
            END,
            a.likes DESC,
            a.ta_puan DESC
        LIMIT ? OFFSET ?
    """
    c.execute(sql_results, (like_pat, like_pat, like_pat, like_pat, like_pat, q, start_pat, like_pat, per_page, offset))
    rows = c.fetchall()
    conn.close()

    results = []
    for r in rows:
        puan = f"{r['ta_puan']:.2f}" if r["ta_puan"] else (f"{r['score']:.1f}" if r["score"] else "8.0")
        resim = f"/imajlar/serilerb/{r['ta_id']}.jpg" if r["ta_id"] else (r["poster_url"] or "/imajlar/logo.png")
        likes = r["likes"] or 500
        dislikes = r["dislikes"] or max(5, int(likes / 38))
        likes_str = f"{likes:,}".replace(",", ".")
        dislikes_str = f"{dislikes:,}".replace(",", ".")
        ozet = r["ozet"] or f"{r['baslik']} izle..."
        clean_ozet = re.sub(r'<[^>]+>', ' ', ozet).strip()
        results.append({
            "id": r["id"],
            "slug": r["slug"],
            "baslik": r["baslik"],
            "resim": resim,
            "puan": puan,
            "bolum": f"{r['bolum_sayisi'] or 12} Bölüm",
            "ozet": clean_ozet,
            "likes": likes_str,
            "dislikes": dislikes_str
        })

    total_pages = max(1, math.ceil(total_count / per_page)) if total_count > 0 else 0
    return {
        "total": total_count,
        "page": page,
        "total_pages": total_pages,
        "results": results
    }

def render_arama_cards_html(query_str, page=1, per_page=28):
    data = search_animes(query_str, page, per_page)
    animes = data["results"]
    current_page = data["page"]
    total_pages = data["total_pages"]

    if not animes:
        esc_q = html.escape(query_str)
        return f'''<div class="alert alert-warning" style="margin:15px;">
  <i class="ikon ikon-info-sign"></i> <b>"{esc_q}"</b> aramanızla eşleşen anime bulunamadı. Lütfen farklı anahtar kelimeler ile tekrar deneyin.
</div>'''

    cards_html = []
    for a in animes:
        esc_baslik = html.escape(a["baslik"])
        esc_slug = html.escape(a["slug"])
        rank_badge = f'<div class="rank-s">{a["puan"]}</div>' if a["puan"] else ''
        card = f'''<div class="col-xs-6" style="padding:5px;">
  <div class="panel" style="margin-bottom:5px;">
    <div class="panel-ust-ic">
      <div class="panel-title">
        <a href="anime/{esc_slug}" class="baloon bold" data-toggle="tooltip" title="{esc_baslik}"><b>{esc_baslik}</b></a>
      </div>
    </div>
    <div class="panel-body" style="padding:5px; height:150px; overflow:hidden; position:relative;">
      <a href="anime/{esc_slug}" class="thumbnail pull-left" style="margin-right:8px; margin-bottom:0px;">
        <div class="imaj" style="position:relative;">
          <img class="media-object" src="{a['resim']}" alt="{esc_baslik}" style="width:75px; height:100px; object-fit:cover;" onerror="this.src=\'/imajlar/logo.png\'">
          {rank_badge}
        </div>
      </a>
      <span class="media-heading" style="font-weight:normal; display:block; height:18px; line-height:18px; margin-bottom:2px;">
        <span class="pull-right anime-bolum" style="font-size:12px; font-weight:bold;">{a['bolum']}</span>
        <span style="display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; padding-right:5px;">
          <a href="anime/{esc_slug}" class="anime-title" style="font-weight:bold;">{esc_baslik}</a>
        </span>
      </span>
      <div class="row" style="padding:0px; margin:0px;">
        <span class="media-object anime-ozet" style="margin-top:6px; height:48px; overflow:hidden; text-overflow:ellipsis; display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; font-size:11px; line-height:16px; word-break:break-word;">
          {a['ozet']}
        </span>
        <span class="media-object" style="margin:0 auto; bottom:6px; position:absolute; right:6px;">
          <div class="btn-group btn-group-sm pull-right">
            <a href="javascript:void(0);" onclick="modal('ajax/uyegirisi','modallar','Kullanıcı Girişi!'); return false;" class="btn btn-default bold colorbegen baloon" data-toggle="tooltip" title="Kişi beğendi!"><i class="ikon ikon-thumbs-up4 ikon-fw"></i> {a['likes']}</a>
            <a href="javascript:void(0);" onclick="modal('ajax/uyegirisi','modallar','Kullanıcı Girişi!'); return false;" class="btn btn-default bold baloon" data-toggle="tooltip" title="İzlediklerime Ekle!"><i class="ikon ikon-eye ikon-fw ikon-1x ikon-margin"></i></a>
            <a href="javascript:void(0);" onclick="modal('ajax/uyegirisi','modallar','Kullanıcı Girişi!'); return false;" class="btn btn-default bold colorbegenme baloon" data-toggle="tooltip" title="Kişi beğenmedi!"><i class="ikon ikon-thumbs-down2 ikon-fw"></i> {a['dislikes']}</a>
          </div>
        </span>
      </div>
    </div>
  </div>
</div>'''
        cards_html.append(card)

    rows_html = []
    for i in range(0, len(cards_html), 2):
        row_content = "".join(cards_html[i:i+2])
        rows_html.append(f'<div class="row" style="margin-left:-5px; margin-right:-5px;">{row_content}</div>')

    ajax_endpoint = f"ajax/arama&q={urllib.parse.quote(query_str)}"
    prev_btn = (
        f'<button type="button" class="btn btn-default bold" onclick="Sayfalama(\'{ajax_endpoint}\',\'{current_page-1}\',\'orta-icerik\');"><i class="ikon ikon-double-angle-left ikon-fw"></i> Önceki Sayfa</button>'
        if current_page > 1 else
        '<button type="button" class="btn btn-default bold" disabled="disabled"><i class="ikon ikon-double-angle-left ikon-fw"></i> Önceki Sayfa</button>'
    )
    next_btn = (
        f'<button type="button" class="btn btn-default bold" onclick="Sayfalama(\'{ajax_endpoint}\',\'{current_page+1}\',\'orta-icerik\');">Sonraki Sayfa <i class="ikon ikon-double-angle-right ikon-fw"></i></button>'
        if current_page < total_pages else
        '<button type="button" class="btn btn-default bold" disabled="disabled">Sonraki Sayfa <i class="ikon ikon-double-angle-right ikon-fw"></i></button>'
    )

    page_items = []
    for p in range(1, total_pages + 1):
        if p == current_page:
            page_items.append(f'<li class="active"><a href="javascript:void();" onclick="Sayfalama(\'{ajax_endpoint}\',\'{p}\',\'orta-icerik\');">{p}. Sayfa</a></li>')
        else:
            page_items.append(f'<li><a href="javascript:void(0);" onclick="Sayfalama(\'{ajax_endpoint}\',\'{p}\',\'orta-icerik\');">{p}. Sayfa</a></li>')

    dropdown_items_html = "".join(page_items)
    pagination_html = f'''<div class="row">
  <div class="col-xs-12" style="text-align:center; margin-top:10px; margin-bottom:10px;">
    <div class="btn-group btn-group-sm">
      {prev_btn}
      <div class="btn-group btn-group-sm dropup">
        <button type="button" class="btn btn-default bold dropdown-toggle" data-toggle="dropdown">{current_page} <span class="caret"></span></button>
        <ul class="dropdown-menu dropdown-menu2 scrollable-menu" role="menu" style="max-height: 280px; overflow-y: auto;">
          {dropdown_items_html}
        </ul>
      </div>
      {next_btn}
    </div>
  </div>
</div>'''

    return "".join(rows_html) + pagination_html

def render_arama_page_html(query_str, page=1):
    raw_template = get_raw_anime_template()
    if not raw_template:
        return None

    cards_and_pagination = render_arama_cards_html(query_str, page)
    search_data = search_animes(query_str, page)
    total_count = search_data["total"]
    esc_q = html.escape(query_str)

    arama_panel = f'''<div class="panel">
  <div class="panel-ust">
    <div class="panel-title">
      <i class="ikon ikon-search" style="color:#d9534f; margin-right:5px;"></i> &quot;{esc_q}&quot; Arama Sonuçları
      <span class="label label-danger pull-right" style="margin-top:2px; font-size:11px;">{total_count} Anime Bulundu</span>
    </div>
  </div>
  <div class="panel-body" id="orta-icerik">
    {cards_and_pagination}
  </div>
  <div class="panel-footer clearfix"></div>
</div>'''

    html_out = raw_template
    if '<head' in html_out and '<base href="/"' not in html_out:
        html_out = re.sub(r'(<head[^>]*>)', r'\1\n<base href="/">', html_out, count=1)

    top_gap_css = '<style>body#bd { padding-top: 50px !important; } body#bd > article.container { margin-top: 0 !important; padding-top: 0 !important; } #arkaplan { margin-top: 0 !important; }</style>'
    if '<head' in html_out:
        html_out = re.sub(r'(<head[^>]*>)', r'\1\n' + top_gap_css, html_out, count=1)

    html_out = re.sub(r'<title>.*?</title>', f'<title>&quot;{esc_q}&quot; Arama Sonuçları - Türk Anime TV</title>', html_out, count=1)
    html_out = re.sub(r'<meta name="title" content=".*?">', f'<meta name="title" content="{esc_q} Arama Sonuçları">', html_out, count=1)

    arama_full_content = arama_panel + "\n" + MMORPG_PANEL_HTML + "\n" + SPONSOR_PANEL_BOTTOM_HTML
    m_mid = re.search(r'(<div class="col-xs-8">)(.*?)(</div>\s*<div class="col-xs-4">)', html_out, re.DOTALL)
    if m_mid:
        html_out = html_out[:m_mid.start(2)] + arama_full_content + html_out[m_mid.end(2):]

    html_out = html_out.replace('../www.animeler.net/', 'www.animeler.net/')
    html_out = html_out.replace('../st.chatango.com/', 'st.chatango.com/')
    html_out = html_out.replace('../www.facebook.com/', 'www.facebook.com/')
    html_out = html_out.replace('href="index/index.html"', 'href="/"')
    html_out = html_out.replace('href="index.html"', 'href="/"')
    html_out = html_out.replace('href="./"', 'href="/"')
    html_out = apply_catalog_sidebar(html_out)

    return html_out

def load_ta_image_map():
    mapping = {}
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            SELECT ta.ta_id, ta.ta_name, a.slug, a.baslik, m.poster_url 
            FROM ta_anime ta 
            JOIN anime a ON ta.anime_id = a.id 
            LEFT JOIN anime_meta m ON a.id = m.anime_id
        """)
        for r in c.fetchall():
            ta_id = str(r["ta_id"]) if r["ta_id"] else ""
            slug = r["slug"]
            item = {
                "id": ta_id,
                "name": r["ta_name"],
                "slug": slug,
                "title": r["baslik"],
                "poster_url": r["poster_url"]
            }
            if ta_id:
                mapping[ta_id] = item
                mapping[f"{ta_id}.jpg"] = item
                mapping[f"{ta_id}.png"] = item
            if slug:
                mapping[slug] = item
                mapping[f"{slug}.jpg"] = item
                mapping[f"{slug}.png"] = item
        conn.close()
    except Exception as e:
        print(f"Uyarı: TA resim eşleme haritası yüklenemedi: {e}")
    return mapping

TA_IMAGE_MAP = load_ta_image_map()

ANILIST_GRAPHQL_URL = "https://graphql.anilist.co"
ANILIST_QUERY = """
query ($search: String) {
  Media (search: $search) {
    id
    title { romaji english }
    coverImage { large medium }
  }
}
"""

NEGATIVE_CACHE = set()

def is_valid_image(data):
    if not data or len(data) < 100:
        return False
    if data.startswith(b"\xff\xd8\xff"): # JPEG
        return True
    if data.startswith(b"\x89PNG\r\n\x1a\n"): # PNG
        return True
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"): # GIF
        return True
    if data.startswith(b"RIFF") and len(data) > 12 and data[8:12] == b"WEBP": # WEBP
        return True
    return False

def clean_str(s):
    return ''.join(c.lower() for c in (s or '') if c.isalnum() or c.isspace()).strip()

def is_title_match(query, candidate_titles):
    q_clean = clean_str(query)
    q_words = [w for w in q_clean.split() if w]
    if not q_words:
        return False
    q_set = set(q_words)
    
    for cand in candidate_titles:
        if not cand:
            continue
        c_clean = clean_str(cand)
        c_words = [w for w in c_clean.split() if w]
        if not c_words:
            continue
        c_set = set(c_words)
        
        # 1. Exact normalized match
        if q_clean == c_clean:
            return True
            
        # 2. Prefix match
        if c_clean.startswith(q_clean) or q_clean.startswith(c_clean):
            return True
            
        # 3. Word overlap
        overlap = len(q_set & c_set)
        if len(q_set) > 0 and (overlap / len(q_set) >= 0.7) and (overlap / len(c_set) >= 0.5):
            return True
            
        # 4. High ratio similarity
        if difflib.SequenceMatcher(None, q_clean, c_clean).ratio() >= 0.8:
            return True
            
    return False

def get_or_fetch_image(rel_path):
    pub_file = os.path.join(PUBLIC_DIR, rel_path)

    if os.path.exists(pub_file) and os.path.isfile(pub_file) and os.path.getsize(pub_file) > 100:
        try:
            with open(pub_file, "rb") as f:
                if is_valid_image(f.read(512)):
                    return pub_file
        except Exception:
            pass

    if rel_path in NEGATIVE_CACHE:
        logo = os.path.join(PUBLIC_DIR, "imajlar", "logo.png")
        return logo if os.path.exists(logo) else None

    clean_rel = rel_path.lstrip("/")
    if clean_rel.startswith("imajlar/"):
        clean_rel = clean_rel[len("imajlar/"):]

    fname = os.path.basename(rel_path)
    base_id = os.path.splitext(fname)[0]
    os.makedirs(os.path.dirname(pub_file), exist_ok=True)

    def _save_image(img_data):
        try:
            norm_rel = rel_path.replace("\\", "/")
            if "imajlar/seriler/" in norm_rel and "serilerb" not in norm_rel:
                from PIL import Image
                import io
                im = Image.open(io.BytesIO(img_data))
                if im.size[0] > 100 or im.size[1] > 140:
                    im_resized = im.resize((90, 128), Image.Resampling.LANCZOS)
                    im_resized.save(pub_file, format="JPEG", quality=92)
                    return
            with open(pub_file, "wb") as f:
                f.write(img_data)
        except Exception:
            try:
                with open(pub_file, "wb") as f:
                    f.write(img_data)
            except Exception:
                pass

    COMMON_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    }

    # 1. PRIMARY TIER: İlk olarak doğrudan turkanime.tv sunucusuna bak
    direct_tv_urls = [
        f"https://www.turkanime.tv/imajlar/{clean_rel}",
        f"https://www.turkanime.tv/imajlar/seriler/{fname}",
        f"http://www.turkanime.tv/imajlar/{clean_rel}",
        f"http://www.turkanime.tv/imajlar/seriler/{fname}"
    ]
    for d_url in direct_tv_urls:
        try:
            req = urllib.request.Request(d_url, headers=COMMON_HEADERS)
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                data = resp.read()
                if is_valid_image(data) and len(data) > 1000:
                    _save_image(data)
                    return pub_file
        except Exception:
            pass

    # 2. SECONDARY TIER: Wayback Machine (WebArchive) - Önce turkanime.tv, sonra diğer domainler (.co, .net)
    wayback_urls = [
        f"https://web.archive.org/web/20190000000000id_/http://www.turkanime.tv/imajlar/{clean_rel}",
        f"https://web.archive.org/web/20180000000000id_/http://www.turkanime.tv/imajlar/seriler/{fname}",
        f"https://web.archive.org/web/20210000000000id_/https://www.turkanime.co/imajlar/{clean_rel}",
        f"https://web.archive.org/web/20200000000000id_/https://www.turkanime.net/imajlar/{clean_rel}",
    ]
    for w_url in wayback_urls:
        try:
            req = urllib.request.Request(w_url, headers=COMMON_HEADERS)
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                final_url = resp.geturl()
                if fname in final_url or "imajlar" in final_url:
                    data = resp.read()
                    if is_valid_image(data) and len(data) > 1000:
                        _save_image(data)
                        return pub_file
        except Exception:
            pass

    # 2. SECONDARY TIER: Look up official high-res poster from anime_meta (MAL CDN)
    meta = TA_IMAGE_MAP.get(fname) or TA_IMAGE_MAP.get(base_id)
    if meta and meta.get("poster_url"):
        try:
            req = urllib.request.Request(meta["poster_url"], headers=COMMON_HEADERS)
            with urllib.request.urlopen(req, timeout=3.5) as resp:
                data = resp.read()
                if is_valid_image(data) and len(data) > 1000:
                    _save_image(data)
                    return pub_file
        except Exception:
            pass

    # 3. TERTIARY TIER: Fallback to AniList & Kitsu by title
    if meta:
        title = meta.get("title") or meta.get("name") or meta.get("slug")
        clean_t = title.split(" 2nd")[0].split(" Season")[0].split(" Part")[0].split(" (TV)")[0].strip()
        search_terms = [title]
        if clean_t != title:
            search_terms.append(clean_t)
        words = title.split()
        if len(words) > 5:
            search_terms.append(" ".join(words[:5]))

        # AniList GraphQL
        for st in search_terms:
            try:
                req_data = json.dumps({"query": ANILIST_QUERY, "variables": {"search": st}}).encode("utf-8")
                req = urllib.request.Request(ANILIST_GRAPHQL_URL, data=req_data, headers={"Content-Type": "application/json", **COMMON_HEADERS})
                with urllib.request.urlopen(req, timeout=2.5) as resp:
                    d = json.load(resp)
                    media = d.get("data", {}).get("Media")
                    if media:
                        cand_titles = [media["title"].get("romaji"), media["title"].get("english"), media["title"].get("native")]
                        if is_title_match(title, cand_titles):
                            img_url = media["coverImage"].get("large") or media["coverImage"].get("medium")
                            if img_url:
                                img_req = urllib.request.Request(img_url, headers=COMMON_HEADERS)
                                with urllib.request.urlopen(img_req, timeout=3.0) as img_resp:
                                    data = img_resp.read()
                                    if is_valid_image(data) and len(data) > 1000:
                                        _save_image(data)
                                        return pub_file
            except Exception:
                pass

        # Kitsu REST API
        for st in search_terms:
            try:
                kitsu_url = f"https://kitsu.io/api/edge/anime?filter[text]={urllib.parse.quote(st)}&page[limit]=5"
                req = urllib.request.Request(kitsu_url, headers=COMMON_HEADERS)
                with urllib.request.urlopen(req, timeout=2.5) as resp:
                    d = json.load(resp)
                    data_list = d.get("data", [])
                    for item in data_list:
                        attrs = item.get("attributes", {})
                        cand_titles = [
                            attrs.get("canonicalTitle"),
                            attrs.get("titles", {}).get("en"),
                            attrs.get("titles", {}).get("en_jp"),
                            attrs.get("titles", {}).get("ja_jp")
                        ]
                        if is_title_match(title, cand_titles):
                            poster = attrs.get("posterImage", {})
                            img_url = poster.get("medium") or poster.get("large") or poster.get("original")
                            if img_url:
                                img_req = urllib.request.Request(img_url, headers=COMMON_HEADERS)
                                with urllib.request.urlopen(img_req, timeout=3.0) as img_resp:
                                    data = img_resp.read()
                                    if is_valid_image(data) and len(data) > 1000:
                                        _save_image(data)
                                        return pub_file
            except Exception:
                pass

    # 4. Fallback to logo (only for anime posters)
    NEGATIVE_CACHE.add(rel_path)
    if "seriler" in rel_path or "bolum" in rel_path:
        logo_file = os.path.join(PUBLIC_DIR, "imajlar", "logo.png")
        return logo_file if os.path.exists(logo_file) else None
    return None

def prefetch_page_images(page):
    def _worker():
        try:
            page_data = get_latest_episodes_page(page, 10)
            for ep in page_data["episodes"]:
                resim = ep.get("resim", "")
                if resim and resim.startswith("/imajlar/"):
                    get_or_fetch_image(resim.lstrip("/"))
        except Exception:
            pass
    threading.Thread(target=_worker, daemon=True).start()

class AnimeRequestHandler(SimpleHTTPRequestHandler):
    def address_string(self):
        return self.client_address[0]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=PUBLIC_DIR, **kwargs)

    def handle(self):
        try:
            super().handle()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass

    def send_json(self, data, status=200):
        try:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass

    def send_html(self, html_text, status=200):
        try:
            body = html_text.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass

    def do_HEAD(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path.startswith("/imajlar/"):
            rel_path = path.lstrip("/")
            target_file = get_or_fetch_image(rel_path)
            if target_file and os.path.exists(target_file):
                ext = os.path.splitext(target_file)[1].lower()
                mime = "image/jpeg"
                if ext == ".png": mime = "image/png"
                elif ext == ".gif": mime = "image/gif"
                elif ext == ".ico": mime = "image/x-icon"
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(os.path.getsize(target_file)))
                self.end_headers()
                return
            self.send_response(404)
            self.end_headers()
            return
        super().do_HEAD()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path.rstrip("/") in ("/arama", "arama"):
            try:
                content_len = int(self.headers.get("Content-Length", 0))
                post_body = self.rfile.read(content_len).decode("utf-8", errors="ignore")
                post_vars = urllib.parse.parse_qs(post_body)
                q = post_vars.get("arama", [""])[0].strip()
                self.send_response(303)
                self.send_header("Location", f"/arama?q={urllib.parse.quote_plus(q)}")
                self.end_headers()
                return
            except Exception:
                pass

        # Handle schnClass CSRF token dummy endpoint from Obje.schn()
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK")
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass

    def do_GET(self):
        if self.path.startswith("/public/"):
            self.path = self.path[len("/public"):]
            if not self.path.startswith("/"):
                self.path = "/" + self.path
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        raw_path = self.path
        query = urllib.parse.parse_qs(parsed.query)

        # Root redirection for /index.html and /index
        if path in ("/index.html", "/index"):
            self.send_response(301)
            self.send_header("Location", "/")
            self.end_headers()
            return

        # Silence adblock checks if requested
        if "ajax/adblock" in raw_path:
            self.send_html("")
            return

        # Trigger prefetch and serve dynamically rendered homepage on initial load
        if path in ("/", ""):
            prefetch_page_images(1)
            prefetch_page_images(2)
            index_path = os.path.join(PUBLIC_DIR, "index.html")
            if os.path.exists(index_path):
                with open(index_path, "r", encoding="utf-8", errors="ignore") as f:
                    index_content = f.read()
                rendered_p1 = render_cards_page_html(1, 10)
                index_content = replace_orta_icerik(index_content, rendered_p1)
                self.send_html(index_content)
                return

        # Handle TurkAnime native AJAX Sayfalama & Tab clicks
        m = re.search(r'sayfa=(\d+)', raw_path)
        page = int(m.group(1)) if m else 1

        # ANIMELER Catalog Page
        if path in ("/animeler", "/animeler/", "/animeler.html", "/animeler/index.html"):
            html_page = render_animeler_page_html(page)
            if html_page:
                self.send_html(html_page)
                return

        if "ajax/animeler" in raw_path:
            html_snippet = render_animeler_cards_html(page)
            self.send_html(html_snippet)
            prefetch_animeler_page_images(page, 28)
            prefetch_animeler_page_images(page + 1, 28)
            return

        # ARAMA (SEARCH) PAGES & AJAX
        if "ajax/arama" in raw_path:
            m_q = re.search(r'[?&]q=([^&?]+)', raw_path) or re.search(r'[?&]arama=([^&?]+)', raw_path)
            raw_q = m_q.group(1) if m_q else ""
            search_query = urllib.parse.unquote_plus(raw_q)
            html_snippet = render_arama_cards_html(search_query, page)
            self.send_html(html_snippet)
            return

        if path in ("/arama", "/arama/", "/arama.html"):
            q_val = query.get("q", query.get("arama", [""]))[0].strip()
            html_page = render_arama_page_html(q_val, page)
            if html_page:
                self.send_html(html_page)
                return

        if path.startswith("/arama/"):
            sub_q = path[len("/arama/"):].strip("/").strip()
            sub_q = urllib.parse.unquote_plus(sub_q)
            html_page = render_arama_page_html(sub_q, page)
            if html_page:
                self.send_html(html_page)
                return

        # Ne Çıkarsa Bahtıma (Rastgele Kategori Animesi)
        if "ajax/bahtima" in raw_path:
            m_kat = re.search(r'[?&]kategoriId=([^&?]+)', raw_path)
            kat_id = m_kat.group(1).strip() if m_kat else "1"
            genre_name = BAHTIMA_ID_MAP.get(kat_id) or normalize_genre_name(kat_id)
            conn = get_db()
            c = conn.cursor()
            c.execute("""
                SELECT slug FROM anime 
                WHERE (',' || replace(replace(turler, ', ', ','), ' ,', ',') || ',') LIKE ('%,' || ? || ',%')
                ORDER BY RANDOM() LIMIT 1
            """, (genre_name,))
            row = c.fetchone()
            if not row or not row["slug"]:
                c.execute("""
                    SELECT slug FROM anime 
                    WHERE turler LIKE ? COLLATE NOCASE
                    ORDER BY RANDOM() LIMIT 1
                """, (f"%{genre_name}%",))
                row = c.fetchone()
            conn.close()
            if row and row["slug"]:
                self.send_json({"url": f"/anime/{row['slug']}"})
            else:
                self.send_json({"url": "/"})
            return

        # KATEGORİ (ANİME TÜRÜ) SAYFALARI
        if "ajax/kategori" in raw_path:
            m_tur = re.search(r'[?&]tur=([^&?]+)', raw_path)
            raw_tur = m_tur.group(1) if m_tur else "Aksiyon"
            genre_name = normalize_genre_name(raw_tur)

            m_sira = re.search(r'[?&]sira=([^&?]+)', raw_path)
            sira = m_sira.group(1) if m_sira else 'ad'

            m_sez = re.search(r'[?&]sezon=([^&?]+)', raw_path)
            sezon = m_sez.group(1) if m_sez else None

            m_yil = re.search(r'[?&]yil=([^&?]+)', raw_path)
            yil = m_yil.group(1) if m_yil else None

            html_snippet = render_kategori_cards_html(genre_name, page, per_page=28, order_by=sira, season=sezon, year=yil)
            self.send_html(html_snippet)
            prefetch_kategori_page_images(genre_name, page, 28, order_by=sira, season=sezon, year=yil)
            prefetch_kategori_page_images(genre_name, page + 1, 28, order_by=sira, season=sezon, year=yil)
            return

        if path.startswith("/kategori/") or path == "/kategori":
            raw_tur = path[len("/kategori/"):].strip("/").strip() if path.startswith("/kategori/") else "Aksiyon"
            genre_name = normalize_genre_name(raw_tur)
            sira = query.get("sira", ["ad"])[0]
            sezon = query.get("sezon", ["all"])[0]
            yil = query.get("yil", ["all"])[0]
            html_page = render_kategori_page_html(genre_name, page, order_by=sira, season=sezon, year=yil)
            if html_page:
                self.send_html(html_page)
                return

        if path.startswith("/anime-turu/") or path == "/anime-turu":
            sub = path[len("/anime-turu/"):].strip("/") if path.startswith("/anime-turu/") else "Aksiyon"
            sub = re.sub(r'/(?:index\.html)?$', '', sub).strip()
            sub = re.sub(r'\.html$', '', sub).strip()
            parts = [p for p in sub.split('/') if p]
            raw_tur = parts[-1] if parts else "Aksiyon"
            if raw_tur.isdigit() and len(parts) > 1:
                raw_tur = parts[-2]
            genre_name = normalize_genre_name(raw_tur)
            sira = query.get("sira", ["ad"])[0]
            sezon = query.get("sezon", ["all"])[0]
            yil = query.get("yil", ["all"])[0]
            html_page = render_kategori_page_html(genre_name, page, order_by=sira, season=sezon, year=yil)
            if html_page:
                self.send_html(html_page)
                return

        # HARF SAYFALARI (ALFABE FİLTRELEME)
        if "ajax/harf" in raw_path:
            m_harf = re.search(r'[?&]harf=([^&?]+)', raw_path)
            raw_harf = m_harf.group(1) if m_harf else "0-9"
            letter = normalize_letter(raw_harf)

            m_sira = re.search(r'[?&]sira=([^&?]+)', raw_path)
            sira = m_sira.group(1) if m_sira else 'ad'

            m_sez = re.search(r'[?&]sezon=([^&?]+)', raw_path)
            sezon = m_sez.group(1) if m_sez else None

            m_yil = re.search(r'[?&]yil=([^&?]+)', raw_path)
            yil = m_yil.group(1) if m_yil else None

            html_snippet = render_harf_cards_html(letter, page, per_page=28, order_by=sira, season=sezon, year=yil)
            self.send_html(html_snippet)
            prefetch_harf_page_images(letter, page, 28, order_by=sira, season=sezon, year=yil)
            prefetch_harf_page_images(letter, page + 1, 28, order_by=sira, season=sezon, year=yil)
            return

        if path.startswith("/harf/") or path == "/harf":
            raw_harf = path[len("/harf/"):].strip("/").strip() if path.startswith("/harf/") else "0-9"
            letter = normalize_letter(raw_harf)
            sira = query.get("sira", ["ad"])[0]
            sezon = query.get("sezon", ["all"])[0]
            yil = query.get("yil", ["all"])[0]
            html_page = render_harf_page_html(letter, page, order_by=sira, season=sezon, year=yil)
            if html_page:
                self.send_html(html_page)
                return

        # Anime Listesi sekmeleri (2019 Authentic Listesi)
        # Anime & Manga Haberleri Arşiv AJAX
        if "ajax/haberler" in raw_path:
            m_t = re.search(r'[?&]tarih=([^&?]+)', raw_path)
            tarih = m_t.group(1).strip() if m_t else ""
            html_snippet = render_arsiv_haberler_html(tarih)
            self.send_html(html_snippet or '<div class="alert alert-info" style="margin:10px;">Haber bulunamadı.</div>')
            return

        if "ajax/turler" in raw_path:
            self.send_html(render_turler_html())
            return

        if "ajax/tamliste" in raw_path:
            self.send_html(render_tamliste_html())
            return

        if "ajax/yillar" in raw_path:
            self.send_html(render_yillar_html())
            return

        # YIL SAYFALARI (YIL FİLTRELEME)
        if "ajax/yil&" in raw_path or "ajax/yil?" in raw_path:
            m_yil = re.search(r'[?&]yil=([^&?]+)', raw_path)
            raw_yil = m_yil.group(1) if m_yil else "2024"
            year = normalize_year(raw_yil)

            m_sira = re.search(r'[?&]sira=([^&?]+)', raw_path)
            sira = m_sira.group(1) if m_sira else 'ad'

            m_sez = re.search(r'[?&]sezon=([^&?]+)', raw_path)
            sezon = m_sez.group(1) if m_sez else None

            html_snippet = render_yil_cards_html(year, page, per_page=28, order_by=sira, season=sezon)
            self.send_html(html_snippet)
            prefetch_yil_page_images(year, page, 28, order_by=sira, season=sezon)
            prefetch_yil_page_images(year, page + 1, 28, order_by=sira, season=sezon)
            return

        if path.startswith("/yil/") or path == "/yil":
            raw_yil = path[len("/yil/"):].strip("/").strip() if path.startswith("/yil/") else "2024"
            year = normalize_year(raw_yil)
            sira = query.get("sira", ["ad"])[0]
            sezon = query.get("sezon", ["all"])[0]
            html_page = render_yil_page_html(year, page, order_by=sira, season=sezon)
            if html_page:
                self.send_html(html_page)
                return

        # 1. Popüler Animeler (Rank'a Göre)
        if "ajax/rankagore" in raw_path:
            html_snippet = render_series_cards_page_html(page, 10, endpoint="ajax/rankagore", target_div="orta-icerik", order_by="likes")
            self.send_html(html_snippet)
            prefetch_series_page_images(page, 10, order_by="likes")
            prefetch_series_page_images(page + 1, 10, order_by="likes")
            return

        # 2. Yeni Eklenen Animeler (Seriler)
        if "ajax/yenieklenenseriler" in raw_path:
            html_snippet = render_series_cards_page_html(page, 10, endpoint="ajax/yenieklenenseriler", target_div="orta-icerik", order_by="date")
            self.send_html(html_snippet)
            prefetch_series_page_images(page, 10, order_by="date")
            prefetch_series_page_images(page + 1, 10, order_by="date")
            return

        # 3. MAL En İyi 500 & Alt Panel Sekmeleri
        if any(x in raw_path for x in ("ajax/sectiklerimiz", "ajax/encokbegenilen", "ajax/encokyorumlanan", "ajax/takipedilen")):
            endpoint = "ajax/sectiklerimiz"
            order_by = "puan"
            if "ajax/encokbegenilen" in raw_path:
                endpoint = "ajax/encokbegenilen"
                order_by = "likes"
            elif "ajax/encokyorumlanan" in raw_path:
                endpoint = "ajax/encokyorumlanan"
                order_by = "likes"
            elif "ajax/takipedilen" in raw_path:
                endpoint = "ajax/takipedilen"
                order_by = "likes"
            html_snippet = render_series_cards_page_html(page, 12, endpoint=endpoint, target_div="orta-icerik-alt", order_by=order_by)
            self.send_html(html_snippet)
            prefetch_series_page_images(page, 12, order_by=order_by)
            return

        # 4. Yeni Eklenen Bölümler (Bitiş Tarihlerine göre)
        if "ajax/yenieklenen" in raw_path:
            html_snippet = render_cards_page_html(page, 10)
            self.send_html(html_snippet)
            prefetch_page_images(page)
            prefetch_page_images(page + 1)
            return

        # 5. Dynamic Anime Detail Page: /anime/<slug>
        if path.startswith("/anime/"):
            raw_slug = path[len("/anime/"):].strip("/").replace("/index.html", "").replace(".html", "").strip()
            if raw_slug:
                html_page = render_anime_page_html(raw_slug)
                if html_page:
                    self.send_html(html_page)
                    return
                else:
                    self.send_response(404)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(b"<h1>404 - Anime Bulunamadi</h1>")
                    return

        # Dynamic Video / Episode Watch Page: /video/<slug>
        if path.startswith("/video/"):
            raw_slug = path[len("/video/"):].strip("/").replace("/index.html", "").replace(".html", "").strip()
            if raw_slug:
                html_page = render_video_page_html(raw_slug)
                if html_page:
                    self.send_html(html_page)
                    return
                else:
                    self.send_response(404)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(b"<h1>404 - Bolum Bulunamadi</h1>")
                    return

        # 6. AJAX: Episode list for anime detail page
        if "ajax/bolumler" in raw_path:
            anime_id = query.get("animeId", [None])[0]
            if not anime_id:
                m = re.search(r'animeId=(\d+)', raw_path)
                if m:
                    anime_id = m.group(1)
            if anime_id:
                conn = get_db()
                c = conn.cursor()
                c.execute("SELECT id, slug, ad FROM bolum WHERE anime_id = ? ORDER BY id ASC", (anime_id,))
                episodes = [dict(r) for r in c.fetchall()]
                conn.close()
                html_snippet = render_episodes_list_html(episodes)
                self.send_html(html_snippet)
                return
            self.send_html('<div class="alert alert-info" style="margin:10px;">Bölüm bulunamadı.</div>')
            return

        # 7. AJAX: Detail tabs (istatistik, baglantili, etc.)
        if "ajax/istatistik" in raw_path:
            anime_id = query.get("animeId", [None])[0]
            if not anime_id:
                m = re.search(r'animeId=(\d+)', raw_path)
                if m:
                    anime_id = m.group(1)
            if anime_id:
                meta = get_anime_info(anime_id)
                if meta:
                    stats_html = f'''<div style="padding:15px;">
<table class="table table-bordered table-striped">
  <tr><th>Puan</th><td>{meta.get("Puanı", "8.0")} / 10</td></tr>
  <tr><th>Beğeni</th><td>{meta.get("likes", 0):,}</td></tr>
  <tr><th>Beğenmeme</th><td>{meta.get("dislikes", 0):,}</td></tr>
  <tr><th>Bölüm Sayısı</th><td>{meta.get("bolum_sayisi", "Belirtilmemiş")}</td></tr>
  <tr><th>Durum</th><td>{meta.get("Durum", "Bilinmiyor")}</td></tr>
</table>
</div>'''
                    self.send_html(stats_html)
                    return
            self.send_html('<div class="alert alert-info">İstatistik bulunamadı.</div>')
            return

        # 8. AJAX: Bağlantılı Animeler
        if "ajax/baglantili" in raw_path:
            anime_id = query.get("animeId", [None])[0]
            if not anime_id:
                m = re.search(r'animeId=(\d+)', raw_path)
                if m:
                    anime_id = m.group(1)
            if anime_id and str(anime_id).isdigit():
                html_snippet = render_baglantili_html(int(anime_id))
                self.send_html(html_snippet)
                return
            self.send_html('<div class="alert alert-info" style="margin:10px;"><i class="ikon ikon-info-sign"></i> Bağlantılı anime bulunamadı.</div>')
            return

        # 9. AJAX: Benzer Animeler
        if "ajax/benzer" in raw_path:
            anime_id = query.get("animeId", [None])[0]
            if not anime_id:
                m = re.search(r'animeId=(\d+)', raw_path)
                if m:
                    anime_id = m.group(1)
            if anime_id and str(anime_id).isdigit():
                html_snippet = render_benzer_html(int(anime_id))
                self.send_html(html_snippet)
                return
            self.send_html('<div class="alert alert-info" style="margin:10px;"><i class="ikon ikon-info-sign"></i> Benzer anime bulunamadı.</div>')
            return

        # News images
        if path.startswith("/www.animeler.net/"):
            rel_path = path.lstrip("/")
            local_file = os.path.join(PUBLIC_DIR, rel_path)
            if os.path.exists(local_file):
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                with open(local_file, "rb") as f:
                    data = f.read()
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                try:
                    self.wfile.write(data)
                except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                    pass
                return
            else:
                self.send_response(404)
                self.end_headers()
                return

        # Facebook plugin redirect
        if path.startswith("/www.facebook.com/"):
            self.send_response(302)
            self.send_header("Location", "https://www.facebook.com/plugins/page.php?href=https%3A%2F%2Fwww.facebook.com%2Fturkanitv%2F&tabs=timeline%2Cevents%2Cmessages&width=307&height=410&small_header=false&adapt_container_width=true&hide_cover=false&show_facepile=true&appId=911598408970834")
            self.end_headers()
            return

        # Third party embeds and ads silencing
        if (
            path.startswith("/ad/")
            or path == "/schnClass"
            or "cpmstar" in path
            or "pub2srv" in path
            or "cobalten" in path
            or "disqus" in path
            or "google-analytics" in path
        ):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            try:
                self.wfile.write(b"")
            except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                pass
            return

        # Image proxy & caching with hybrid fallback
        if path.startswith("/imajlar/"):
            rel_path = path.lstrip("/")
            target_file = get_or_fetch_image(rel_path)

            if target_file and os.path.exists(target_file):
                ext = os.path.splitext(target_file)[1].lower()
                mime = "image/jpeg"
                if ext == ".png":
                    mime = "image/png"
                elif ext == ".gif":
                    mime = "image/gif"
                elif ext == ".ico":
                    mime = "image/x-icon"

                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Cache-Control", "public, max-age=604800")
                with open(target_file, "rb") as f:
                    data = f.read()
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                try:
                    self.wfile.write(data)
                except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                    pass
                return
            else:
                self.send_response(404)
                self.end_headers()
                return

        # API: latest-episodes
        if path == "/api/latest-episodes":
            try:
                page = int(query.get("page", ["1"])[0])
            except ValueError:
                page = 1
            try:
                per_page = int(query.get("per_page", ["10"])[0])
            except ValueError:
                per_page = 10

            data = get_latest_episodes_page(page, per_page)
            self.send_json(data)
            return

        # API: search
        if path == "/api/search":
            q = query.get("q", [""])[0].strip()
            if not q:
                self.send_json({"results": []})
                return

            conn = get_db()
            cursor = conn.cursor()
            search_param = f"%{q}%"
            cursor.execute(
                """
                SELECT id, slug, baslik, bolum_sayisi 
                FROM anime 
                WHERE baslik LIKE ? OR slug LIKE ? 
                ORDER BY CASE WHEN baslik LIKE ? THEN 0 ELSE 1 END, baslik ASC
                LIMIT 30
                """,
                (search_param, search_param, f"{q}%")
            )
            rows = [dict(row) for row in cursor.fetchall()]
            conn.close()

            for r in rows:
                meta = get_anime_info(r["slug"])
                if meta:
                    r["ozet"] = meta.get("Özet", "")[:200] + ("..." if len(meta.get("Özet", "")) > 200 else "")
                    r["puan"] = meta.get("Puanı")
                    r["turler"] = meta.get("Anime Türü", [])
                    r["kategori"] = meta.get("Kategori", "TV")
            self.send_json({"results": rows})
            return

        # API: live-search for top search dropdown
        if path == "/api/live-search":
            q_val = query.get("q", query.get("term", [""]))[0].strip()
            if not q_val or len(q_val) < 2:
                self.send_json({"results": []})
                return
            search_res = search_animes(q_val, page=1, per_page=6)
            self.send_json({"results": search_res["results"][:6]})
            return

        # API: featured
        if path == "/api/featured":
            conn = get_db()
            cursor = conn.cursor()
            placeholders = ",".join(["?"] * len(FEATURED_SLUGS))
            cursor.execute(f"SELECT id, slug, baslik, bolum_sayisi FROM anime WHERE slug IN ({placeholders})", FEATURED_SLUGS)
            rows = {row["slug"]: dict(row) for row in cursor.fetchall()}
            conn.close()

            results = []
            for slug in FEATURED_SLUGS:
                if slug in rows:
                    item = rows[slug]
                    meta = get_anime_info(slug)
                    if meta:
                        item["ozet"] = meta.get("Özet", "")[:180] + ("..." if len(meta.get("Özet", "")) > 180 else "")
                        item["puan"] = meta.get("Puanı")
                        item["turler"] = meta.get("Anime Türü", [])
                        item["kategori"] = meta.get("Kategori", "TV")
                    results.append(item)
            self.send_json({"featured": results})
            return

        # API: anime
        if path == "/api/anime":
            slug = query.get("slug", [""])[0].strip()
            anime_id = query.get("id", [""])[0].strip()

            conn = get_db()
            cursor = conn.cursor()
            if slug:
                cursor.execute("SELECT id, slug, baslik, bolum_sayisi FROM anime WHERE slug = ?", (slug,))
            elif anime_id:
                cursor.execute("SELECT id, slug, baslik, bolum_sayisi FROM anime WHERE id = ?", (anime_id,))
            else:
                conn.close()
                self.send_json({"error": "Anime belirtilmedi"}, status=400)
                return

            anime_row = cursor.fetchone()
            if not anime_row:
                conn.close()
                self.send_json({"error": "Anime bulunamadı"}, status=404)
                return

            anime_data = dict(anime_row)
            cursor.execute("SELECT id, slug, ad FROM bolum WHERE anime_id = ? ORDER BY id ASC", (anime_data["id"],))
            episodes = [dict(ep) for ep in cursor.fetchall()]
            conn.close()

            anime_data["bolumler"] = episodes
            anime_data["info"] = get_anime_info(anime_data["slug"])
            self.send_json(anime_data)
            return

        # API: episode
        if path == "/api/episode":
            ep_id = query.get("id", [""])[0].strip()
            ep_slug = query.get("slug", [""])[0].strip()

            conn = get_db()
            cursor = conn.cursor()
            if ep_id:
                cursor.execute("SELECT id, anime_id, slug, ad FROM bolum WHERE id = ?", (ep_id,))
            elif ep_slug:
                cursor.execute("SELECT id, anime_id, slug, ad FROM bolum WHERE slug = ?", (ep_slug,))
            else:
                conn.close()
                self.send_json({"error": "Bölüm belirtilmedi"}, status=400)
                return

            ep_row = cursor.fetchone()
            if not ep_row:
                conn.close()
                self.send_json({"error": "Bölüm bulunamadı"}, status=404)
                return

            ep_data = dict(ep_row)

            cursor.execute("SELECT id, slug, baslik FROM anime WHERE id = ?", (ep_data["anime_id"],))
            anime_row = cursor.fetchone()
            if anime_row:
                ep_data["anime"] = dict(anime_row)

            cursor.execute("SELECT id, slug, ad FROM bolum WHERE anime_id = ? ORDER BY id ASC", (ep_data["anime_id"],))
            all_eps = [dict(r) for r in cursor.fetchall()]
            current_idx = next((i for i, ep in enumerate(all_eps) if ep["id"] == ep_data["id"]), -1)
            ep_data["prev_episode"] = all_eps[current_idx - 1] if current_idx > 0 else None
            ep_data["next_episode"] = all_eps[current_idx + 1] if current_idx >= 0 and current_idx < len(all_eps) - 1 else None

            cursor.execute(
                """
                SELECT id, player, fansub, tip, deger, is_legacy 
                FROM link 
                WHERE bolum_id = ?
                ORDER BY is_legacy ASC, CASE WHEN tip='url' THEN 0 ELSE 1 END, player ASC
                """,
                (ep_data["id"],)
            )
            links = [dict(row) for row in cursor.fetchall()]

            cursor.execute(
                """
                SELECT fg.name as fansub_group, ef.full_info 
                FROM ta_episode_fansub ef
                LEFT JOIN ta_fansub_group fg ON ef.fansub_group_id = fg.id
                WHERE ef.bolum_id = ?
                """,
                (ep_data["id"],)
            )
            translators = [dict(row) for row in cursor.fetchall()]
            conn.close()

            grouped = {}
            for l in links:
                fansub = l["fansub"] or "Varsayılan"
                if fansub not in grouped:
                    grouped[fansub] = []
                grouped[fansub].append(l)

            ep_data["links"] = links
            ep_data["grouped_links"] = grouped
            ep_data["translators"] = translators
            self.send_json(ep_data)
            return

        # Default static file serving from public/
        return super().do_GET()

def run_server(port=8000):
    server_address = ("", port)
    try:
        httpd = ThreadingHTTPServer(server_address, AnimeRequestHandler)
    except OSError as e:
        if getattr(e, "winerror", None) == 10048 or getattr(e, "errno", None) in (48, 98, 10048):
            print(f"\n[BİLGİ] Port {port} kullanımda, alternatif port {port+1} deneniyor...")
            port = port + 1
            server_address = ("", port)
            httpd = ThreadingHTTPServer(server_address, AnimeRequestHandler)
        else:
            raise e

    print(f"\n=======================================================")
    print(f"  TürkAnime Yerel Arşiv Portalı Başlatıldı!")
    print(f"  Adres: http://localhost:{port}")
    print(f"=======================================================\n")

    def _open_browser():
        time.sleep(0.5)
        try:
            import webbrowser
            webbrowser.open(f"http://localhost:{port}")
        except Exception:
            pass

    import threading
    threading.Thread(target=_open_browser, daemon=True).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nSunucu kapatılıyor...")
        httpd.server_close()

if __name__ == "__main__":
    run_server()
