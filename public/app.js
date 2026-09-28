// Application State
const state = {
  featured: [],
  currentAnime: null,
  currentEpisode: null,
  activeFansub: null,
  activeLink: null,
  episodesList: [],
  searchTimeout: null,
};

// DOM Elements
const views = {
  home: document.getElementById('view-home'),
  anime: document.getElementById('view-anime'),
  watch: document.getElementById('view-watch'),
};

const searchInput = document.getElementById('search-input');
const searchDropdown = document.getElementById('search-dropdown');
const searchClear = document.getElementById('search-clear');
const featuredGrid = document.getElementById('featured-grid');

// View Switching Helper
function switchView(viewName) {
  Object.keys(views).forEach((v) => {
    if (v === viewName) {
      views[v].classList.remove('hidden');
      views[v].classList.add('active');
    } else {
      views[v].classList.remove('active');
      views[v].classList.add('hidden');
    }
  });
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// Formatters & Utilities
function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// 1. Featured Animes
async function loadFeatured() {
  try {
    const res = await fetch('/api/featured');
    const data = await res.json();
    state.featured = data.featured || [];
    renderFeatured();
  } catch (err) {
    console.error('Featured yükleme hatası:', err);
    featuredGrid.innerHTML = '<div class="loading-spinner">Veriler yüklenemedi.</div>';
  }
}

function renderFeatured() {
  if (!state.featured.length) {
    featuredGrid.innerHTML = '<div class="loading-spinner">Öne çıkan anime bulunamadı.</div>';
    return;
  }

  featuredGrid.innerHTML = state.featured
    .map(
      (a) => `
      <div class="anime-card" onclick="openAnime('${a.slug}')">
        <div class="anime-card-top">
          <h3 class="anime-card-title">${escapeHtml(a.baslik)}</h3>
          ${a.puan ? `<span class="badge-score">★ ${a.puan}</span>` : ''}
        </div>
        <p class="anime-card-synopsis">${escapeHtml(a.ozet || 'Özet bulunmuyor.')}</p>
        <div class="anime-card-footer">
          <span class="tag-cat">${escapeHtml(a.kategori || 'TV')}</span>
          <span>${a.bolum_sayisi ? a.bolum_sayisi + ' Bölüm' : ''}</span>
        </div>
      </div>
    `
    )
    .join('');
}

// 2. Search Functionality
searchInput.addEventListener('input', (e) => {
  const q = e.target.value.trim();
  if (q.length > 0) {
    searchClear.classList.remove('hidden');
  } else {
    searchClear.classList.add('hidden');
    searchDropdown.classList.add('hidden');
    return;
  }

  clearTimeout(state.searchTimeout);
  state.searchTimeout = setTimeout(() => performSearch(q), 250);
});

searchClear.addEventListener('click', () => {
  searchInput.value = '';
  searchClear.classList.add('hidden');
  searchDropdown.classList.add('hidden');
  searchInput.focus();
});

document.addEventListener('click', (e) => {
  if (!e.target.closest('.search-wrapper')) {
    searchDropdown.classList.add('hidden');
  }
});

async function performSearch(query) {
  try {
    const res = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
    const data = await res.json();
    renderSearchResults(data.results || []);
  } catch (err) {
    console.error('Arama hatası:', err);
  }
}

function renderSearchResults(results) {
  if (!results.length) {
    searchDropdown.innerHTML = '<div class="search-no-results">Sonuç bulunamadı.</div>';
    searchDropdown.classList.remove('hidden');
    return;
  }

  searchDropdown.innerHTML = results
    .map(
      (item) => `
      <div class="search-item" onclick="selectSearchResult('${item.slug}')">
        <div class="search-item-info">
          <div class="search-item-title">${escapeHtml(item.baslik)}</div>
          <div class="search-item-meta">
            ${item.kategori ? item.kategori + ' • ' : ''}
            ${item.turler && item.turler.length ? item.turler.slice(0, 2).join(', ') + ' • ' : ''}
            ${item.bolum_sayisi ? item.bolum_sayisi + ' Bölüm' : ''}
          </div>
        </div>
        ${item.puan ? `<span class="search-item-badge">★ ${item.puan}</span>` : ''}
      </div>
    `
    )
    .join('');

  searchDropdown.classList.remove('hidden');
}

function selectSearchResult(slug) {
  searchDropdown.classList.add('hidden');
  searchInput.value = '';
  searchClear.classList.add('hidden');
  openAnime(slug);
}

// 3. Anime Detail View
async function openAnime(slug) {
  try {
    const res = await fetch(`/api/anime?slug=${encodeURIComponent(slug)}`);
    const anime = await res.json();
    if (anime.error) {
      alert(anime.error);
      return;
    }

    state.currentAnime = anime;
    state.episodesList = anime.bolumler || [];

    // Render Hero Card
    document.getElementById('bc-anime-title').textContent = anime.baslik;
    document.getElementById('anime-title').textContent = anime.baslik;
    
    const info = anime.info || {};
    document.getElementById('anime-jp-title').textContent = info['Japonca'] || '';
    document.getElementById('anime-synopsis').textContent = info['Özet'] || 'Bu anime için henüz Türkçe özet eklenmemiş.';

    // Badges
    const badgesContainer = document.getElementById('anime-badges');
    badgesContainer.innerHTML = '';
    if (info['Kategori']) {
      badgesContainer.innerHTML += `<span class="badge-chip primary">${escapeHtml(info['Kategori'])}</span>`;
    }
    if (info['Puanı']) {
      badgesContainer.innerHTML += `<span class="badge-chip score">★ ${info['Puanı']}</span>`;
    }
    if (info['Anime Türü'] && Array.isArray(info['Anime Türü'])) {
      info['Anime Türü'].forEach((genre) => {
        badgesContainer.innerHTML += `<span class="badge-chip">${escapeHtml(genre)}</span>`;
      });
    }

    // Meta Grid
    const metaGrid = document.getElementById('anime-meta-grid');
    metaGrid.innerHTML = `
      <div>
        <div class="meta-item-label">Bölüm Sayısı</div>
        <div class="meta-item-val">${info['Bölüm Sayısı'] || anime.bolum_sayisi || (anime.bolumler ? anime.bolumler.length : 'Bilinmiyor')}</div>
      </div>
      <div>
        <div class="meta-item-label">Stüdyo</div>
        <div class="meta-item-val">${escapeHtml(info['Stüdyo'] || 'Belirtilmemiş')}</div>
      </div>
      <div>
        <div class="meta-item-label">Yayın Tarihi</div>
        <div class="meta-item-val">${escapeHtml(info['Başlama Tarihi'] || 'Bilinmiyor')}</div>
      </div>
      <div>
        <div class="meta-item-label">Bitiş Tarihi</div>
        <div class="meta-item-val">${escapeHtml(info['Bitiş Tarihi'] || 'Bilinmiyor')}</div>
      </div>
    `;

    // Episodes count & list
    document.getElementById('episodes-count').textContent = state.episodesList.length;
    renderEpisodes(state.episodesList);

    // Episode filter input
    const filterInput = document.getElementById('episode-filter');
    filterInput.value = '';
    filterInput.oninput = (e) => {
      const term = e.target.value.toLowerCase().trim();
      const filtered = state.episodesList.filter(
        (ep) => ep.ad.toLowerCase().includes(term) || ep.slug.toLowerCase().includes(term)
      );
      renderEpisodes(filtered);
    };

    switchView('anime');
  } catch (err) {
    console.error('Anime bilgisi çekilemedi:', err);
  }
}

function renderEpisodes(list) {
  const container = document.getElementById('episodes-grid');
  if (!list.length) {
    container.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: var(--text-dim); padding: 2rem;">Bölüm bulunamadı.</div>';
    return;
  }

  container.innerHTML = list
    .map(
      (ep) => `
      <button class="ep-button" title="${escapeHtml(ep.ad)}" onclick="openEpisode(${ep.id})">
        ${escapeHtml(ep.ad.replace(state.currentAnime.baslik, '').trim() || ep.ad)}
      </button>
    `
    )
    .join('');
}

// 4. Watch Episode View
async function openEpisode(epId) {
  try {
    const res = await fetch(`/api/episode?id=${epId}`);
    const epData = await res.json();
    if (epData.error) {
      alert(epData.error);
      return;
    }

    state.currentEpisode = epData;

    // Breadcrumb & Titles
    document.getElementById('bc-watch-anime').textContent = epData.anime ? epData.anime.baslik : 'Anime';
    document.getElementById('bc-watch-episode').textContent = epData.ad;
    document.getElementById('watch-ep-title').textContent = epData.ad;
    document.getElementById('watch-anime-name').textContent = epData.anime ? epData.anime.baslik : '';

    // Prev / Next Navigation Buttons
    const prevBtn = document.getElementById('btn-prev-ep');
    const nextBtn = document.getElementById('btn-next-ep');

    if (epData.prev_episode) {
      prevBtn.disabled = false;
      prevBtn.onclick = () => openEpisode(epData.prev_episode.id);
    } else {
      prevBtn.disabled = true;
    }

    if (epData.next_episode) {
      nextBtn.disabled = false;
      nextBtn.onclick = () => openEpisode(epData.next_episode.id);
    } else {
      nextBtn.disabled = true;
    }

    // Fansub Tabs
    renderFansubsAndPlayers(epData.grouped_links || {});

    switchView('watch');
  } catch (err) {
    console.error('Bölüm açılamadı:', err);
  }
}

function renderFansubsAndPlayers(grouped) {
  const fansubTabs = document.getElementById('fansub-tabs');
  fansubTabs.innerHTML = '';

  const fansubs = Object.keys(grouped);
  if (!fansubs.length) {
    showOverlayMessage('Bu bölüme ait kayıtlı video kaynağı bulunamadı.');
    return;
  }

  // Select first fansub or keep previous if exists
  state.activeFansub = fansubs.includes(state.activeFansub) ? state.activeFansub : fansubs[0];

  fansubs.forEach((fs) => {
    const btn = document.createElement('button');
    btn.className = `tab-btn ${fs === state.activeFansub ? 'active' : ''}`;
    btn.textContent = fs;
    btn.onclick = () => {
      state.activeFansub = fs;
      renderFansubsAndPlayers(grouped);
    };
    fansubTabs.appendChild(btn);
  });

  // Render players for active fansub
  const links = grouped[state.activeFansub] || [];
  renderPlayerButtons(links);
}

function renderPlayerButtons(links) {
  const playerButtons = document.getElementById('player-buttons');
  playerButtons.innerHTML = '';

  if (!links.length) {
    showOverlayMessage('Seçilen çeviri için video kaynağı bulunamadı.');
    return;
  }

  // Prioritize working direct embed players
  const preferredPlayers = ['ODNOKLASSNIKI', 'OK.RU', 'SIBNET', 'MAIL', 'MP4UPLOAD', 'VOE', 'GDRIVE', 'UQLOAD', 'SENDVID'];
  
  // Sort links so URL types come first, preferred players first
  const sortedLinks = [...links].sort((a, b) => {
    if (a.tip === 'url' && b.tip !== 'url') return -1;
    if (a.tip !== 'url' && b.tip === 'url') return 1;
    const aPref = preferredPlayers.indexOf(a.player.toUpperCase());
    const bPref = preferredPlayers.indexOf(b.player.toUpperCase());
    if (aPref !== -1 && bPref === -1) return -1;
    if (aPref === -1 && bPref !== -1) return 1;
    return (aPref !== -1 && bPref !== -1) ? aPref - bPref : a.player.localeCompare(b.player);
  });

  // Select first playable source by default
  let selected = sortedLinks.find((l) => l.tip === 'url') || sortedLinks[0];

  sortedLinks.forEach((link) => {
    const btn = document.createElement('button');
    const isMask = link.tip === 'mask';
    btn.className = `src-btn ${link.id === selected.id ? 'active' : ''} ${isMask ? 'mask-type' : ''}`;
    btn.textContent = link.player + (isMask ? ' (Maskeli)' : '');
    btn.title = isMask ? 'Türkanime iç proxy oynatıcısı (harici URL değil)' : 'Doğrudan oynatıcı bağlantısı';

    btn.onclick = () => {
      document.querySelectorAll('.src-btn').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      playSource(link);
    };

    playerButtons.appendChild(btn);
  });

  if (selected) {
    playSource(selected);
  }
}

function playSource(link) {
  state.activeLink = link;
  const frame = document.getElementById('video-frame');
  const overlay = document.getElementById('video-overlay');
  const infoText = document.getElementById('current-source-info');
  const extBtn = document.getElementById('btn-open-external');

  if (link.tip === 'url') {
    overlay.classList.add('hidden');
    frame.src = link.deger;
    infoText.textContent = `Oynatıcı: ${link.player} | Tip: Doğrudan Harici Kaynak`;
    extBtn.href = link.deger;
    extBtn.classList.remove('hidden');
  } else if (link.tip === 'mask') {
    frame.src = 'about:blank';
    showOverlayMessage(
      `"${link.player}" kaynağı Türkanime dahili proxy oynatıcısıdır (/player/...). Doğrudan oynatıcılar (OK.RU, SIBNET, MAIL vb.) için lütfen yukarıdaki diğer butonları seçiniz.`
    );
    infoText.textContent = `Oynatıcı: ${link.player} | Dahili Maske`;
    extBtn.classList.add('hidden');
  } else {
    showOverlayMessage('Bu kaynak desteklenmeyen bir biçimdedir.');
  }
}

function showOverlayMessage(msg) {
  const frame = document.getElementById('video-frame');
  const overlay = document.getElementById('video-overlay');
  const text = document.getElementById('overlay-text');
  frame.src = 'about:blank';
  text.textContent = msg;
  overlay.classList.remove('hidden');
}

// Navigation & Breadcrumbs
document.getElementById('brand-logo').addEventListener('click', (e) => {
  e.preventDefault();
  switchView('home');
});
document.getElementById('bc-home').addEventListener('click', (e) => {
  e.preventDefault();
  switchView('home');
});
document.getElementById('bc-watch-home').addEventListener('click', (e) => {
  e.preventDefault();
  switchView('home');
});
document.getElementById('bc-watch-anime').addEventListener('click', (e) => {
  e.preventDefault();
  if (state.currentAnime) {
    switchView('anime');
  }
});
document.getElementById('btn-back-to-list').addEventListener('click', () => {
  if (state.currentAnime) {
    switchView('anime');
  }
});

// Initialization
document.addEventListener('DOMContentLoaded', () => {
  loadFeatured();
});
