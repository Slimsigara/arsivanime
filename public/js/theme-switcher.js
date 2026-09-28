/* TürkAnime Theme Switcher (2018 / 2021) */
(function() {
  function getStoredTheme() {
    try {
      var saved = localStorage.getItem('turkanime_theme');
      if (saved) return saved;
      var match = document.cookie.match(/(^|; )theme=([^;]+)/);
      if (match) return match[2];
    } catch(e) {}
    return '2018';
  }

  function syncHaberlerCards() {
    var isDark = document.body && document.body.classList.contains('dark');
    var cards = document.querySelectorAll('#haberler .thumbnail');
    for (var i = 0; i < cards.length; i++) {
      if (isDark) {
        cards[i].style.setProperty('background', '#1e2026', 'important');
        cards[i].style.setProperty('border-color', '#23252c', 'important');
      } else {
        cards[i].style.removeProperty('background');
        cards[i].style.removeProperty('border-color');
      }
    }
  }

  function applyTheme(theme) {
    var isDark = (theme === 'dark' || theme === '2021');
    if (isDark) {
      document.documentElement.classList.add('dark');
      if (document.body) document.body.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
      if (document.body) document.body.classList.remove('dark');
    }

    var btn = document.getElementById('theme-toggle-btn');
    var btnText = document.getElementById('theme-btn-text');
    if (btnText) {
      btnText.textContent = isDark ? '2018' : '2021';
    }
    if (btn) {
      btn.title = isDark ? '2018 Temasına Dön' : '2021 Karanlık Temaya Geç';
    }

    syncHaberlerCards();
  }

  window.toggleTheme = function() {
    var current = getStoredTheme();
    var isDark = (current === 'dark' || current === '2021');
    var nextTheme = isDark ? '2018' : '2021';
    try {
      localStorage.setItem('turkanime_theme', nextTheme);
      document.cookie = 'theme=' + nextTheme + '; path=/; max-age=31536000';
    } catch(e) {}
    applyTheme(nextTheme);
  };

  // Immediate execution on DOM load
  var initialTheme = getStoredTheme();
  if (initialTheme === 'dark' || initialTheme === '2021') {
    document.documentElement.classList.add('dark');
    if (document.body) document.body.classList.add('dark');
  }

  function initUI() {
    applyTheme(getStoredTheme());

    // Observe #haberler changes (when user changes month selector)
    var haberlerElem = document.getElementById('haberler');
    if (haberlerElem && window.MutationObserver) {
      var observer = new MutationObserver(function() {
        syncHaberlerCards();
      });
      observer.observe(haberlerElem, { childList: true });
    }

    // Live update Discord widget counts if possible
    try {
      if (window.fetch) {
        fetch('https://discord.com/api/v9/invites/64EdNRS?with_counts=true')
          .then(function(r) { return r.json(); })
          .then(function(data) {
            if (data && data.approximate_member_count) {
              var total = data.approximate_member_count.toLocaleString('tr-TR') + ' Üye';
              var online = data.approximate_presence_count.toLocaleString('tr-TR') + ' Çevrimiçi';
              var numTotal = document.getElementById('numTotal');
              var numOnline = document.getElementById('numOnline');
              if (numTotal) numTotal.textContent = total;
              if (numOnline) numOnline.textContent = online;
              if (data.guild && data.guild.icon) {
                var iconUrl = 'https://cdn.discordapp.com/icons/' + data.guild.id + '/' + data.guild.icon + '.jpg';
                var img = document.getElementById('serverImg');
                if (img) img.style.backgroundImage = 'url(' + iconUrl + ')';
              }
            }
          }).catch(function(){});
      }
    } catch(e) {}
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initUI);
  } else {
    initUI();
  }
})();
