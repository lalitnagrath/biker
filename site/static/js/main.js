// ===== Mobile Menu Toggle =====
const mobileMenuToggle = document.getElementById('mobileMenuToggle');
const mainNav = document.getElementById('mainNav');

if (mobileMenuToggle && mainNav) {
    mobileMenuToggle.addEventListener('click', () => {
        mainNav.classList.toggle('active');
        mobileMenuToggle.classList.toggle('active');
    });
    // Close menu when clicking a nav link (leaf links only, not parent toggles)
    mainNav.querySelectorAll('.dropdown a, .mega-model-link, .mega-view-all').forEach(link => {
        link.addEventListener('click', () => {
            mainNav.classList.remove('active');
            mobileMenuToggle.classList.remove('active');
        });
    });
}

// ===== Mobile Menu Accordion =====
document.querySelectorAll('.main-nav .has-dropdown > a').forEach(trigger => {
    trigger.addEventListener('click', (e) => {
        if (window.innerWidth > 768) return;
        e.preventDefault();
        const parent = trigger.parentElement;
        const wasExpanded = parent.classList.contains('expanded');
        // Close all sibling accordions
        parent.parentElement.querySelectorAll(':scope > .has-dropdown').forEach(item => {
            item.classList.remove('expanded');
        });
        if (!wasExpanded) parent.classList.add('expanded');
    });
});

// ===== Mega Menu Desktop Hover =====
const megaMenu = document.querySelector('.mega-menu');
const megaBrandLinks = document.querySelectorAll('.mega-brand-link');
const megaModels = document.getElementById('megaModels');

if (megaBrandLinks.length && megaModels) {
    // Build a map of brand -> models from the DOM data attributes
    const navData = {};
    megaBrandLinks.forEach(link => {
        const brand = link.dataset.brand;
        const brandName = link.textContent.trim().replace(/\u203A$/, '').trim();
        navData[brand] = brandName;
    });

    // Fetch models from inline JSON embedded by the template
    const modelsMap = window.__navModels || {};

    megaBrandLinks.forEach(link => {
        link.addEventListener('mouseenter', () => {
            megaBrandLinks.forEach(l => l.classList.remove('active'));
            link.classList.add('active');
            const brand = link.dataset.brand;
            const bikes = modelsMap[brand] || [];
            if (bikes.length) {
                megaModels.innerHTML =
                    '<div class="mega-models-title">' + link.textContent.trim().replace(/\u203A$/, '').trim() + '</div>' +
                    '<div class="mega-models-grid">' +
                    bikes.map(function(b) { return '<a href="' + b.url + '" class="mega-model-link">' + b.name + '</a>'; }).join('') +
                    '</div>';
            } else {
                megaModels.innerHTML = '<div class="mega-models-placeholder">No models found</div>';
            }
        });
    });
}

// ===== Bike Garage Widget =====
(function() {
    if (typeof BikeGarage === 'undefined') return;

    BikeGarage.init();

    var btn = document.getElementById('garageBtn');
    var dropdown = document.getElementById('garageDropdown');
    var label = document.getElementById('garageBtnLabel');
    var searchInput = document.getElementById('garageSearch');
    var list = document.getElementById('garageDropdownList');
    var clearBtn = document.getElementById('garageClearBtn');
    var items = list ? list.querySelectorAll('.garage-dropdown-item') : [];

    if (!btn || !dropdown) return;

    function updateLabel() {
        var slug = BikeGarage.get();
        if (slug) {
            var bike = BikeGarage.find(slug);
            label.textContent = bike ? (bike.brand + ' ' + bike.model) : 'My Garage';
            if (clearBtn) clearBtn.style.display = '';
        } else {
            label.textContent = 'My Garage';
            if (clearBtn) clearBtn.style.display = 'none';
        }
    }

    function highlightActive() {
        var slug = BikeGarage.get();
        for (var i = 0; i < items.length; i++) {
            items[i].classList.toggle('active', items[i].getAttribute('data-slug') === slug);
        }
    }

    btn.addEventListener('click', function(e) {
        e.stopPropagation();
        var open = dropdown.classList.toggle('open');
        btn.setAttribute('aria-expanded', open ? 'true' : 'false');
        if (open) {
            highlightActive();
            if (searchInput) { searchInput.value = ''; searchInput.focus(); filterItems(''); }
        }
    });

    document.addEventListener('click', function(e) {
        if (!dropdown.contains(e.target) && !btn.contains(e.target)) {
            dropdown.classList.remove('open');
            btn.setAttribute('aria-expanded', 'false');
        }
    });

    if (searchInput) {
        var debounce;
        searchInput.addEventListener('input', function() {
            clearTimeout(debounce);
            debounce = setTimeout(function() { filterItems(searchInput.value.toLowerCase().trim()); }, 100);
        });
    }

    function filterItems(q) {
        for (var i = 0; i < items.length; i++) {
            var brand = (items[i].getAttribute('data-brand') || '').toLowerCase();
            var model = (items[i].getAttribute('data-model') || '').toLowerCase();
            items[i].style.display = (!q || brand.indexOf(q) !== -1 || model.indexOf(q) !== -1) ? '' : 'none';
        }
    }

    for (var i = 0; i < items.length; i++) {
        items[i].addEventListener('click', function() {
            var slug = this.getAttribute('data-slug');
            BikeGarage.save(slug);
            dropdown.classList.remove('open');
            btn.setAttribute('aria-expanded', 'false');
            updateLabel();
            highlightActive();
        });
    }

    if (clearBtn) {
        clearBtn.addEventListener('click', function() {
            BikeGarage.clear();
            dropdown.classList.remove('open');
            btn.setAttribute('aria-expanded', 'false');
            updateLabel();
            highlightActive();
        });
    }

    updateLabel();
    highlightActive();
    BikeGarage.onChange(function() { updateLabel(); highlightActive(); });
})();

// ===== Search =====
const searchToggle = document.getElementById('searchToggle');
const searchOverlay = document.getElementById('searchOverlay');
const searchInput = document.getElementById('searchInput');
const searchClose = document.getElementById('searchClose');
const searchResults = document.getElementById('searchResults');
const heroSearch = document.getElementById('heroSearch');

function openSearch() {
    if (searchOverlay) {
        searchOverlay.classList.add('active');
        if (searchInput) searchInput.focus();
    }
}

function closeSearch() {
    if (searchOverlay) {
        searchOverlay.classList.remove('active');
        if (searchInput) searchInput.value = '';
        if (searchResults) searchResults.innerHTML = '';
    }
}

if (searchToggle) searchToggle.addEventListener('click', openSearch);
if (searchClose) searchClose.addEventListener('click', closeSearch);
if (heroSearch) {
    heroSearch.addEventListener('focus', openSearch);
}

if (searchOverlay) {
    searchOverlay.addEventListener('click', (e) => {
        if (e.target === searchOverlay) closeSearch();
    });
}

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeSearch();
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        openSearch();
    }
});

// ===== Search Data =====
const searchData = [];
if (typeof siteData !== 'undefined') {
    if (siteData.motorcycles) {
        siteData.motorcycles.forEach(bike => {
            searchData.push({
                type: 'Motorcycle',
                title: bike.brand + ' ' + bike.model,
                url: 'motorcycles/' + bike.slug + '/index.html',
                excerpt: bike.engine + ' | ' + bike.type + ' | ' + bike.price
            });
        });
    }
    if (siteData.products) {
        siteData.products.forEach(product => {
            searchData.push({
                type: 'Product',
                title: product.title,
                url: 'products/' + product.slug + '/index.html',
                excerpt: product.category + ' | ₹' + product.price + ' | ' + product.rating + '★'
            });
        });
    }
    if (siteData.brands) {
        siteData.brands.forEach(brand => {
            searchData.push({
                type: 'Brand',
                title: brand.name,
                url: 'brands/' + brand.slug + '/index.html',
                excerpt: brand.country + ' | ' + brand.popular_models.length + ' models'
            });
        });
    }
    if (siteData.articles) {
        siteData.articles.forEach(article => {
            searchData.push({
                type: 'Guide',
                title: article.title,
                url: 'articles/' + article.slug + '/index.html',
                excerpt: article.reading_time + ' | ' + (article.tags ? article.tags.join(', ') : '')
            });
        });
    }
}

// ===== Search Functionality =====
if (searchInput) {
    let debounceTimer;
    searchInput.addEventListener('input', (e) => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
            const query = e.target.value.toLowerCase().trim();
            if (query.length < 2) { searchResults.innerHTML = ''; return; }

            const results = searchData.filter(item =>
                item.title.toLowerCase().includes(query) ||
                item.excerpt.toLowerCase().includes(query) ||
                item.type.toLowerCase().includes(query)
            ).slice(0, 10);

            if (results.length === 0) {
                searchResults.innerHTML = '<div class="search-result-item"><div class="search-result-title">No results found</div></div>';
                return;
            }

            searchResults.innerHTML = results.map(result => `
                <a href="${result.url}" class="search-result-item">
                    <div class="search-result-type">${result.type}</div>
                    <div class="search-result-title">${result.title}</div>
                    <div class="search-result-excerpt">${result.excerpt}</div>
                </a>
            `).join('');
        }, 200);
    });
}

// ===== Hero Search Suggestions =====
const heroSuggestions = document.getElementById('heroSuggestions');
if (heroSuggestions) {
    heroSuggestions.querySelectorAll('.suggestion').forEach(suggestion => {
        suggestion.addEventListener('click', () => {
            const url = suggestion.dataset.url;
            if (url) window.location.href = url;
        });
    });
}

// ===== Smart Search (Homepage) =====
const smartSearchInput = document.getElementById('smartSearchInput');
const smartSearchResults = document.getElementById('smartSearchResults');
const popularSearchChips = document.querySelectorAll('.popular-search-chip');

if (smartSearchInput && smartSearchResults) {
    let smartDebounce;

    function buildSearchIndex() {
        if (typeof siteData === 'undefined') return [];
        var items = [];
        if (siteData.motorcycles) {
            siteData.motorcycles.forEach(function(bike) {
                items.push({
                    type: 'bike',
                    icon: '\uD83D\uDE97',
                    title: bike.brand + ' ' + bike.model,
                    meta: bike.engine + ' \u00B7 ' + bike.type + ' \u00B7 \u20B9' + bike.price,
                    url: 'motorcycles/' + bike.slug + '/index.html'
                });
            });
        }
        if (siteData.products) {
            siteData.products.forEach(function(product) {
                items.push({
                    type: 'product',
                    icon: '\uD83D\uDECD\uFE0F',
                    title: product.title,
                    meta: product.category + ' \u00B7 \u20B9' + product.price + ' \u00B7 ' + product.rating + '\u2605',
                    url: 'products/' + product.slug + '/index.html'
                });
            });
        }
        if (siteData.articles) {
            siteData.articles.forEach(function(article) {
                items.push({
                    type: 'guide',
                    icon: '\uD83D\uDCD6',
                    title: article.title,
                    meta: article.reading_time,
                    url: 'articles/' + article.slug + '/index.html'
                });
            });
        }
        return items;
    }

    var smartIndex = buildSearchIndex();

    smartSearchInput.addEventListener('input', function(e) {
        clearTimeout(smartDebounce);
        smartDebounce = setTimeout(function() {
            var query = e.target.value.toLowerCase().trim();
            if (query.length < 2) {
                smartSearchResults.classList.remove('active');
                smartSearchResults.innerHTML = '';
                return;
            }

            var results = smartIndex.filter(function(item) {
                return item.title.toLowerCase().indexOf(query) !== -1 ||
                       item.meta.toLowerCase().indexOf(query) !== -1;
            }).slice(0, 8);

            if (results.length === 0) {
                smartSearchResults.innerHTML = '<div class="smart-search-result"><div class="smart-search-result-info"><div class="smart-search-result-title">No results found</div></div></div>';
                smartSearchResults.classList.add('active');
                return;
            }

            smartSearchResults.innerHTML = results.map(function(r) {
                return '<a href="' + r.url + '" class="smart-search-result">' +
                    '<div class="smart-search-result-icon">' + r.icon + '</div>' +
                    '<div class="smart-search-result-info">' +
                    '<div class="smart-search-result-title">' + r.title + '</div>' +
                    '<div class="smart-search-result-meta">' + r.meta + '</div>' +
                    '</div></a>';
            }).join('');
            smartSearchResults.classList.add('active');
        }, 200);
    });

    smartSearchInput.addEventListener('focus', function() {
        if (smartSearchInput.value.trim().length >= 2) {
            smartSearchResults.classList.add('active');
        }
    });

    document.addEventListener('click', function(e) {
        if (!e.target.closest('.smart-search-wrapper')) {
            smartSearchResults.classList.remove('active');
        }
    });

    // Popular search chips
    popularSearchChips.forEach(function(chip) {
        chip.addEventListener('click', function(e) {
            e.preventDefault();
            var query = chip.dataset.query || chip.textContent;
            smartSearchInput.value = query;
            smartSearchInput.dispatchEvent(new Event('input'));
            smartSearchInput.focus();
        });
    });
}

// Keyboard shortcut: Cmd/Ctrl + K to focus smart search
document.addEventListener('keydown', function(e) {
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        var smartInput = document.getElementById('smartSearchInput');
        if (smartInput) {
            e.preventDefault();
            smartInput.focus();
            smartInput.select();
        }
    }
});

// ===== Bike Filters (Homepage) =====
const bikeShowcase = document.getElementById('bikeShowcase');
const filterBtns = document.querySelectorAll('.filter-btn');
const bikeSearch = document.getElementById('bikeSearch');
const bikeBrandFilter = document.getElementById('bikeBrandFilter');
const bikeTypeFilter = document.getElementById('bikeTypeFilter');
const loadMoreBtn = document.getElementById('loadMoreBtn');
const bikeShowingCount = document.getElementById('bikeShowingCount');

if (bikeShowcase) {
    const INITIAL_SHOW = 12;
    let showingCount = 0;
    let activeBrand = 'all';
    let activeType = 'all';
    let searchQuery = '';

    function getVisibleCards() {
        const cards = Array.from(bikeShowcase.querySelectorAll('.bike-showcase-card'));
        return cards.filter(card => {
            const brand = card.dataset.brand;
            const type = card.dataset.type || '';
            const text = card.textContent.toLowerCase();
            const matchBrand = activeBrand === 'all' || brand === activeBrand;
            const matchType = activeType === 'all' || type === activeType;
            const matchSearch = !searchQuery || text.includes(searchQuery);
            return matchBrand && matchType && matchSearch;
        });
    }

    function applyFilters() {
        const allCards = Array.from(bikeShowcase.querySelectorAll('.bike-showcase-card'));
        const visible = getVisibleCards();

        allCards.forEach(card => card.classList.add('hidden-card'));
        visible.slice(0, showingCount).forEach(card => card.classList.remove('hidden-card'));

        if (loadMoreBtn) {
            loadMoreBtn.style.display = showingCount >= visible.length ? 'none' : '';
        }
        if (bikeShowingCount) {
            bikeShowingCount.textContent = 'Showing ' + Math.min(showingCount, visible.length) + ' of ' + visible.length + ' motorcycles';
        }
    }

    function resetAndShow() {
        showingCount = INITIAL_SHOW;
        applyFilters();
    }

    // Quick filter buttons
    filterBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            filterBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            activeBrand = btn.dataset.filter;
            if (bikeBrandFilter) bikeBrandFilter.value = activeBrand;
            resetAndShow();
        });
    });

    // Brand select
    if (bikeBrandFilter) {
        bikeBrandFilter.addEventListener('change', () => {
            activeBrand = bikeBrandFilter.value;
            filterBtns.forEach(b => {
                b.classList.toggle('active', b.dataset.filter === activeBrand);
            });
            resetAndShow();
        });
    }

    // Type select
    if (bikeTypeFilter) {
        bikeTypeFilter.addEventListener('change', () => {
            activeType = bikeTypeFilter.value;
            resetAndShow();
        });
    }

    // Search
    if (bikeSearch) {
        let searchTimer;
        bikeSearch.addEventListener('input', (e) => {
            clearTimeout(searchTimer);
            searchTimer = setTimeout(() => {
                searchQuery = e.target.value.toLowerCase().trim();
                resetAndShow();
            }, 200);
        });
    }

    // Load More
    if (loadMoreBtn) {
        loadMoreBtn.addEventListener('click', () => {
            showingCount += INITIAL_SHOW;
            applyFilters();
        });
    }

    // Initial state
    showingCount = INITIAL_SHOW;
    applyFilters();
}

// ===== FAQ Accordions =====
document.querySelectorAll('.faq-accordion-header').forEach(header => {
    header.addEventListener('click', () => {
        const item = header.closest('.faq-accordion-item');
        const wasActive = item.classList.contains('active');

        // Close all siblings
        item.closest('.faq-accordion').querySelectorAll('.faq-accordion-item').forEach(i => i.classList.remove('active'));

        if (!wasActive) item.classList.add('active');
    });
});

// ===== Editorial Nav Scroll Spy =====
const editorialNavLinks = document.querySelectorAll('.editorial-nav-link');
if (editorialNavLinks.length > 0) {
    editorialNavLinks.forEach(link => {
        link.addEventListener('click', (e) => {
            const href = link.getAttribute('href');
            if (href && href.startsWith('#')) {
                e.preventDefault();
                const target = document.querySelector(href);
                if (target) {
                    editorialNavLinks.forEach(l => l.classList.remove('active'));
                    link.classList.add('active');
                    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }
            }
        });
    });

    // Scroll spy
    const sections = document.querySelectorAll('.editorial-section, [id]');
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const id = entry.target.id;
                if (id) {
                    editorialNavLinks.forEach(link => {
                        link.classList.toggle('active', link.getAttribute('href') === '#' + id);
                    });
                }
            }
        });
    }, { rootMargin: '-80px 0px -60% 0px' });

    sections.forEach(section => {
        if (section.id) observer.observe(section);
    });
}

// ===== Sticky CTA =====
const stickyCta = document.getElementById('stickyCta');
const stickyCtaBtn = document.getElementById('stickyCtaBtn');

if (stickyCta && stickyCtaBtn) {
    // Find affiliate link on page
    const affiliateLink = document.querySelector('[data-amazon-url]');
    if (affiliateLink) {
        stickyCtaBtn.href = affiliateLink.dataset.amazonUrl;

        let lastScrollY = 0;
        window.addEventListener('scroll', () => {
            const scrollY = window.scrollY;
            const showCta = scrollY > 400 && scrollY > lastScrollY;
            stickyCta.classList.toggle('visible', showCta);
            lastScrollY = scrollY;
        }, { passive: true });
    }
}

// ===== Product Filters (Category Page) =====
const filterForm = document.getElementById('filterForm');
const productList = document.getElementById('productList');

if (filterForm && productList) {
    const sortFilter = document.getElementById('sortFilter');
    const brandFilter = document.getElementById('brandFilter');
    const priceFilter = document.getElementById('priceFilter');
    const ratingFilter = document.getElementById('ratingFilter');

    function applyFilters() {
        const products = Array.from(productList.querySelectorAll('.product-card-editorial'));
        const sort = sortFilter ? sortFilter.value : 'rating';
        const brand = brandFilter ? brandFilter.value : '';
        const priceRange = priceFilter ? priceFilter.value : '';
        const minRating = ratingFilter ? parseFloat(ratingFilter.value) || 0 : 0;

        products.forEach(product => {
            const pRating = parseFloat(product.dataset.rating) || 0;
            const pPrice = parseInt(product.dataset.price) || 0;
            const pBrand = product.dataset.brand || '';
            let show = true;
            if (brand && pBrand !== brand) show = false;
            if (minRating && pRating < minRating) show = false;
            if (priceRange) {
                const [min, max] = priceRange.split('-').map(Number);
                if (pPrice < min || pPrice > max) show = false;
            }
            product.style.display = show ? '' : 'none';
        });

        const visibleProducts = products.filter(p => p.style.display !== 'none');
        visibleProducts.sort((a, b) => {
            switch (sort) {
                case 'rating': return parseFloat(b.dataset.rating) - parseFloat(a.dataset.rating);
                case 'price-low': return parseInt(a.dataset.price) - parseInt(b.dataset.price);
                case 'price-high': return parseInt(b.dataset.price) - parseInt(a.dataset.price);
                case 'reviews': return parseInt(b.dataset.reviews) - parseInt(a.dataset.reviews);
                default: return 0;
            }
        });
        visibleProducts.forEach(product => productList.appendChild(product));
    }

    [sortFilter, brandFilter, priceFilter, ratingFilter].forEach(filter => {
        if (filter) filter.addEventListener('change', applyFilters);
    });
}

// ===== Moto FAQ Accordions =====
document.querySelectorAll('.moto-faq-header').forEach(header => {
    header.addEventListener('click', () => {
        const item = header.closest('.moto-faq-item');
        const wasActive = item.classList.contains('active');
        item.closest('.moto-faq-accordion').querySelectorAll('.moto-faq-item').forEach(i => i.classList.remove('active'));
        if (!wasActive) item.classList.add('active');
    });
});

// ===== Moto TOC Scroll Spy =====
const motoTocLinks = document.querySelectorAll('.moto-toc-link');
if (motoTocLinks.length > 0) {
    motoTocLinks.forEach(link => {
        link.addEventListener('click', (e) => {
            const href = link.getAttribute('href');
            if (href && href.startsWith('#')) {
                e.preventDefault();
                const target = document.querySelector(href);
                if (target) {
                    motoTocLinks.forEach(l => l.classList.remove('active'));
                    link.classList.add('active');
                    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }
            }
        });
    });

    const motoSections = document.querySelectorAll('.moto-section[id]');
    const motoObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const id = entry.target.id;
                if (id) {
                    motoTocLinks.forEach(link => {
                        link.classList.toggle('active', link.getAttribute('href') === '#' + id);
                    });
                }
            }
        });
    }, { rootMargin: '-80px 0px -60% 0px' });
    motoSections.forEach(section => motoObserver.observe(section));
}

// ===== Motorcycle Page Garage Button =====
(function() {
    if (typeof BikeGarage === 'undefined') return;
    var btn = document.getElementById('motoGarageBtn');
    if (!btn) return;
    var slug = btn.getAttribute('data-slug');
    var text = btn.querySelector('.moto-garage-btn-text');

    function update() {
        var current = BikeGarage.get();
        if (current === slug) {
            btn.classList.add('in-garage');
            if (text) text.textContent = 'In My Garage';
        } else {
            btn.classList.remove('in-garage');
            if (text) text.textContent = 'Add to My Garage';
        }
    }

    btn.addEventListener('click', function() {
        if (BikeGarage.get() === slug) {
            BikeGarage.clear();
        } else {
            BikeGarage.save(slug);
        }
        update();
    });

    BikeGarage.onChange(function() { update(); });
    update();
})();

// ===== Smooth Scroll =====
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function(e) {
        const target = document.querySelector(this.getAttribute('href'));
        if (target) {
            e.preventDefault();
            target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    });
});

// ===== Sidebar Collapsible Sections =====
document.querySelectorAll('.moto-sb-collapsible').forEach(header => {
    header.addEventListener('click', () => {
        const targetId = header.dataset.target;
        const target = document.getElementById(targetId);
        if (target) {
            target.classList.toggle('expanded');
            const toggle = header.querySelector('.moto-sb-toggle');
            if (toggle) {
                toggle.style.transform = target.classList.contains('expanded') ? 'rotate(180deg)' : '';
            }
        }
    });
});

// ===== Guide Motorcycle Selector =====
// Compact "My Motorcycle" card beside hero, BikeGarage persistence, compatibility filter
(function() {
    var config = window.__guideConfig;
    if (!config) return;
    if (typeof BikeGarage === 'undefined') return;

    var select = document.getElementById('bikeSelect');
    var statusText = document.getElementById('bikeStatusText');
    var compatHeader = document.querySelector('.guide-compat-header');
    var compatCells = document.querySelectorAll('.guide-compat-cell');
    var compatBadges = document.querySelectorAll('.guide-compat-badge');
    var compatBanners = document.querySelectorAll('.guide-compat-banner');
    var recBadges = document.querySelectorAll('.guide-rec-badge');
    var productCards = document.querySelectorAll('.guide-product-card');
    var productRows = document.querySelectorAll('.guide-product-row');
    var resultsHeading = document.getElementById('guideResultsHeading');
    var resultsDesc = document.getElementById('guideResultsDesc');
    var guideToolbar = document.getElementById('guideToolbar');
    var compatFilter = document.getElementById('compatOnlyFilter');
    var filterCount = document.getElementById('filterCount');
    var emptyState = document.getElementById('emptyCompatibleState');
    var continueSubtitle = document.getElementById('continueSubtitle');
    var continueLinks = document.querySelectorAll('.guide-continue-card');

    if (!select) return;

    // ===== URL param helpers =====
    function getBikeParam() {
        var params = new URLSearchParams(window.location.search);
        return params.get('bike') || '';
    }
    function setBikeParam(slug) {
        var url = new URL(window.location);
        if (slug) {
            url.searchParams.set('bike', slug);
        } else {
            url.searchParams.delete('bike');
        }
        window.history.replaceState({}, '', url);
    }

    function findBike(slug) {
        for (var i = 0; i < config.motorcycles.length; i++) {
            if (config.motorcycles[i].slug === slug) return config.motorcycles[i];
        }
        return null;
    }

    // ===== Recommendation badge assignment =====
    // Only assigns badges to compatible products. Never recommends incompatible products.
    // When no bike is selected, restores server-rendered badges from badgeData.
    var quickPickCards = document.querySelectorAll('.guide-quick-card');
    var recReasons = document.querySelectorAll('.guide-rec-reason');

    // Client-side recommendation score (lightweight version of product_engine.recommendation_score)
    function clientRecScore(slug, compatStatus) {
        var card = null;
        productCards.forEach(function(c) {
            if (c.getAttribute('data-product-slug') === slug) card = c;
        });
        if (!card) return -1;

        var scoreEl = card.querySelector('.score-number');
        var editorRating = scoreEl ? parseFloat(scoreEl.textContent) || 0 : 0;
        var ratingEl = card.querySelector('.rating-value');
        var userRating = ratingEl ? parseFloat(ratingEl.textContent) || 0 : 0;
        var reviewEl = card.querySelector('.review-count');
        var reviews = reviewEl ? parseInt(reviewEl.textContent.replace(/[^\d]/g, '')) || 0 : 0;
        var priceEl = card.querySelector('.bestof-product-price');
        var price = priceEl ? parseInt(priceEl.textContent.replace(/[^\d]/g, '')) || 0 : 0;

        // Value for money: quality / price
        var vfm = 0;
        if (price > 0) {
            var quality = (userRating + editorRating / 2) / 2;
            vfm = Math.min(1.0, quality / Math.max(price / 1000, 0.1) / 10);
        }

        // Compatibility boost
        var compatBoost = 0;
        if (compatStatus === 'compatible') compatBoost = 1.0;
        else if (compatStatus === 'universal') compatBoost = 0.8;

        var score = 0;
        score += 25.0 * (editorRating / 10);      // editor
        score += 20.0 * vfm;                        // value
        score += 15.0 * (userRating / 5);           // rating
        score += 15.0 * Math.min(1, Math.log10(reviews + 1) / 5); // reviews
        score += 15.0 * compatBoost;                // compatibility
        score += 5.0 * (reviews > 100 ? 1 : 0.5);  // brand proxy
        score += 5.0;                               // availability (assume available)
        return score;
    }

    function generateReason(slug, badgeType) {
        var card = null;
        productCards.forEach(function(c) {
            if (c.getAttribute('data-product-slug') === slug) card = c;
        });
        if (!card) return '';
        var title = card.querySelector('h3') ? card.querySelector('h3').textContent.trim() : '';
        var ratingEl = card.querySelector('.rating-value');
        var rating = ratingEl ? parseFloat(ratingEl.textContent) || 0 : 0;
        var priceEl = card.querySelector('.bestof-product-price');
        var price = priceEl ? priceEl.textContent.trim() : '';
        var scoreEl = card.querySelector('.score-number');
        var editor = scoreEl ? parseFloat(scoreEl.textContent) || 0 : 0;
        var reviewEl = card.querySelector('.review-count');
        var reviews = reviewEl ? parseInt(reviewEl.textContent.replace(/[^\d]/g, '')) || 0 : 0;

        if (badgeType === 'editors_choice') {
            return 'Highest recommendation with ' + editor + '/10 editor rating at ' + price;
        }
        if (badgeType === 'best_value') {
            return 'Best quality-to-price ratio' + (rating >= 4 ? ', ' + rating + '/5 user rating' : '') + ' at ' + price;
        }
        if (badgeType === 'premium_pick') {
            return 'Premium choice at ' + price + (editor >= 8 ? ', ' + editor + '/10 editor score' : '');
        }
        if (badgeType === 'most_popular') {
            return 'Most reviewed with ' + reviews.toLocaleString() + ' reviews' + (rating >= 4 ? ', ' + rating + '/5 rating' : '');
        }
        return '';
    }

    function assignRecBadges(bikeSlug) {
        var badgeData = config.badgeData || {};
        var compatMap = config.compatibilityMap || {};

        // When no bike selected: restore server-rendered badges
        if (!bikeSlug) {
            // Restore product card badges from server badgeData
            recBadges.forEach(function(b) {
                var slug = b.getAttribute('data-product-slug');
                var info = badgeData[slug];
                if (info && info.badge) {
                    b.style.display = '';
                    b.className = 'guide-rec-badge guide-rec-' + info.badge_type;
                    b.textContent = info.icon + ' ' + info.badge;
                } else {
                    b.style.display = 'none';
                    b.textContent = '';
                }
            });
            // Restore quick pick cards from server badgeData
            restoreQuickPicks(badgeData);
            // Restore reason text
            restoreReasons(badgeData);
            return;
        }

        // When bike selected: recompute badges among compatible products only
        var compatible = [];
        productCards.forEach(function(card) {
            var slug = card.getAttribute('data-product-slug');
            if (!slug || !compatMap[slug]) return;
            var info = compatMap[slug][bikeSlug] || {};
            var status = info.status || 'incompatible';
            if (status === 'incompatible') return;
            var score = clientRecScore(slug, status);
            if (score < 0) return;
            compatible.push({ slug: slug, score: score, status: status });
        });

        if (compatible.length === 0) {
            recBadges.forEach(function(b) { b.style.display = 'none'; b.textContent = ''; });
            clearQuickPicks();
            clearReasons();
            return;
        }

        // Sort by composite score for editor's choice
        var byScore = compatible.slice().sort(function(a, b) { return b.score - a.score; });
        // Sort by value (score/price) for best value
        var byValue = compatible.slice().sort(function(a, b) {
            var aCard = getProductCard(a.slug);
            var bCard = getProductCard(b.slug);
            var aPrice = getCardPrice(aCard);
            var bPrice = getCardPrice(bCard);
            var aRatio = aPrice > 0 ? a.score / aPrice : 0;
            var bRatio = bPrice > 0 ? b.score / bPrice : 0;
            return bRatio - aRatio;
        });
        // Sort by reviews for most popular
        var byPopularity = compatible.slice().sort(function(a, b) {
            return getCardReviews(a.slug) - getCardReviews(b.slug);
        }).reverse();
        // Sort by price for premium
        var byPrice = compatible.slice().sort(function(a, b) {
            return getCardPrice(getProductCard(a.slug)) - getCardPrice(getProductCard(b.slug));
        }).reverse();

        var newBadges = {};
        var used = {};

        function assign(badgeType, list) {
            for (var i = 0; i < list.length; i++) {
                if (!used[list[i].slug]) {
                    used[list[i].slug] = true;
                    newBadges[list[i].slug] = {
                        type: badgeType,
                        label: getBadgeLabel(badgeType),
                        icon: getBadgeIcon(badgeType),
                        reason: generateReason(list[i].slug, badgeType)
                    };
                    return;
                }
            }
        }

        assign('editors_choice', byScore);
        assign('best_value', byValue);
        assign('most_popular', byPopularity);
        assign('premium_pick', byPrice);

        // Apply badges to product cards
        recBadges.forEach(function(b) {
            var slug = b.getAttribute('data-product-slug');
            if (newBadges[slug]) {
                b.style.display = '';
                b.className = 'guide-rec-badge guide-rec-' + newBadges[slug].type;
                b.textContent = newBadges[slug].icon + ' ' + newBadges[slug].label;
            } else {
                b.style.display = 'none';
                b.textContent = '';
            }
        });

        // Update quick pick cards
        updateQuickPicks(newBadges);
        // Update reason text
        updateReasons(newBadges);
    }

    function getProductCard(slug) {
        var found = null;
        productCards.forEach(function(c) {
            if (c.getAttribute('data-product-slug') === slug) found = c;
        });
        return found;
    }
    function getCardPrice(card) {
        if (!card) return 0;
        var el = card.querySelector('.bestof-product-price');
        return el ? parseInt(el.textContent.replace(/[^\d]/g, '')) || 0 : 0;
    }
    function getCardReviews(slug) {
        var card = getProductCard(slug);
        if (!card) return 0;
        var el = card.querySelector('.review-count');
        return el ? parseInt(el.textContent.replace(/[^\d]/g, '')) || 0 : 0;
    }
    function getBadgeLabel(type) {
        var labels = {
            'editors_choice': "Editor's Choice",
            'best_value': 'Best Value',
            'premium_pick': 'Premium Pick',
            'most_popular': 'Most Popular'
        };
        return labels[type] || type;
    }
    function getBadgeIcon(type) {
        var icons = {
            'editors_choice': '\uD83C\uDFC6',
            'best_value': '\uD83D\uDCB0',
            'premium_pick': '\u2B50',
            'most_popular': '\uD83D\uDD25'
        };
        return icons[type] || '';
    }

    // Quick pick card helpers
    function restoreQuickPicks(badgeData) {
        var slots = ['editors_choice', 'best_value', 'premium_pick', 'most_popular'];
        quickPickCards.forEach(function(card, idx) {
            if (idx >= slots.length) return;
            var slotType = slots[idx];
            // Find the product that has this badge
            var slug = null;
            for (var s in badgeData) {
                if (badgeData[s].badge_type === slotType) { slug = s; break; }
            }
            if (slug) {
                card.style.display = '';
                var info = badgeData[slug];
                var badgeEl = card.querySelector('.guide-quick-badge');
                if (badgeEl) {
                    badgeEl.className = 'guide-quick-badge guide-quick-badge-' + slotType.replace('_', '-');
                    badgeEl.innerHTML = info.icon + ' ' + info.badge;
                }
            }
        });
    }
    function updateQuickPicks(newBadges) {
        var slots = ['editors_choice', 'best_value', 'premium_pick', 'most_popular'];
        quickPickCards.forEach(function(card, idx) {
            if (idx >= slots.length) return;
            var slotType = slots[idx];
            var slug = null;
            for (var s in newBadges) {
                if (newBadges[s].type === slotType) { slug = s; break; }
            }
            if (slug) {
                card.style.display = '';
                var badgeEl = card.querySelector('.guide-quick-badge');
                if (badgeEl) {
                    badgeEl.className = 'guide-quick-badge guide-quick-badge-' + slotType.replace('_', '-');
                    badgeEl.innerHTML = newBadges[slug].icon + ' ' + newBadges[slug].label;
                }
                // Update title link
                var h3 = card.querySelector('h3');
                if (h3) {
                    var link = h3.querySelector('a');
                    if (link) {
                        var prodCard = getProductCard(slug);
                        if (prodCard) {
                            var origLink = prodCard.querySelector('h3 a');
                            if (origLink) {
                                link.href = origLink.href;
                                link.textContent = origLink.textContent;
                            }
                        }
                    }
                }
                // Update reason
                var reasonEl = card.querySelector('.guide-quick-reason');
                if (reasonEl) reasonEl.textContent = newBadges[slug].reason;
                // Update price
                var priceEl = card.querySelector('.guide-quick-price');
                if (priceEl) {
                    var prodCard = getProductCard(slug);
                    if (prodCard) {
                        var origPrice = prodCard.querySelector('.bestof-product-price');
                        if (origPrice) priceEl.textContent = origPrice.textContent;
                    }
                }
            } else {
                card.style.display = 'none';
            }
        });
    }
    function clearQuickPicks() {
        quickPickCards.forEach(function(card) { card.style.display = 'none'; });
    }

    // Reason text helpers
    function restoreReasons(badgeData) {
        recReasons.forEach(function(el) {
            var card = el.closest('.guide-product-card');
            if (!card) return;
            var slug = card.getAttribute('data-product-slug');
            var info = badgeData[slug];
            if (info && info.reason) {
                el.style.display = '';
                var textEl = el.querySelector('.guide-rec-reason-text');
                if (textEl) textEl.textContent = 'Why we recommend: ' + info.reason;
            } else {
                el.style.display = 'none';
            }
        });
    }
    function updateReasons(newBadges) {
        recReasons.forEach(function(el) {
            var card = el.closest('.guide-product-card');
            if (!card) return;
            var slug = card.getAttribute('data-product-slug');
            if (newBadges[slug]) {
                el.style.display = '';
                var textEl = el.querySelector('.guide-rec-reason-text');
                if (textEl) textEl.textContent = 'Why we recommend: ' + newBadges[slug].reason;
            } else {
                el.style.display = 'none';
            }
        });
    }
    function clearReasons() {
        recReasons.forEach(function(el) { el.style.display = 'none'; });
    }

    // ===== Main filter function =====
    function applyFilter(bikeSlug) {
        var compatMap = config.compatibilityMap || {};
        var compatCount = 0;
        var totalCount = productCards.length;
        var onlyCompat = compatFilter && compatFilter.checked;
        var bike = bikeSlug ? findBike(bikeSlug) : null;
        var bikeName = bike ? bike.model : '';

        // Update compat badges in comparison table
        compatBadges.forEach(function(badge) {
            var slug = badge.getAttribute('data-product-slug');
            if (!slug || !bikeSlug || !compatMap[slug]) {
                badge.textContent = '';
                badge.className = 'guide-compat-badge';
                return;
            }
            var info = compatMap[slug][bikeSlug] || {};
            var status = info.status || 'incompatible';
            badge.className = 'guide-compat-badge ' + status;
            if (status === 'compatible') {
                badge.innerHTML = '&#10003; Fits your ' + bikeName;
                compatCount++;
            } else if (status === 'universal') {
                badge.innerHTML = '&#10003; Universal Fit';
                compatCount++;
            } else {
                badge.innerHTML = '&#10007; Doesn\u2019t fit ' + bikeName;
            }
        });

        // Update compat banners on product cards
        var hiddenByFilter = 0;
        compatBanners.forEach(function(banner) {
            var slug = banner.getAttribute('data-product-slug');
            if (!slug || !bikeSlug || !compatMap[slug]) {
                banner.style.display = 'none';
                banner.textContent = '';
                banner.className = 'guide-compat-banner';
                return;
            }
            var info = compatMap[slug][bikeSlug] || {};
            var status = info.status || 'incompatible';
            banner.className = 'guide-compat-banner ' + status;
            banner.style.display = 'block';

            var html = '';
            if (status === 'compatible') {
                html = '&#10003; Fits your ' + bikeName;
            } else if (status === 'universal') {
                html = '&#10003; Universal: Fits your ' + bikeName + ' and all motorcycles';
            } else {
                html = '&#10007; Doesn\u2019t fit ' + bikeName;
            }

            // Append fitment notes if present
            var notes = info.fitment_notes;
            var req = info.requires;
            if (notes || (req && req.length > 0)) {
                html += '<div class="guide-compat-details">';
                if (notes) html += '<span class="guide-fitment-note">\u2022 ' + notes + '</span>';
                if (req && req.length > 0) {
                    req.forEach(function(r) { html += '<span class="guide-fitment-requires">\u2022 Requires: ' + r + '</span>'; });
                }
                html += '</div>';
            }
            banner.innerHTML = html;
        });

        // Show/hide compat columns in table
        if (compatHeader) {
            compatHeader.style.display = bikeSlug ? '' : 'none';
        }
        compatCells.forEach(function(cell) {
            cell.style.display = bikeSlug ? '' : 'none';
        });

        // Dim or hide incompatible product cards and table rows
        productCards.forEach(function(card) {
            var slug = card.getAttribute('data-product-slug');
            if (!slug || !bikeSlug || !compatMap[slug]) {
                card.classList.remove('incompatible-dim');
                card.classList.remove('incompatible-hide');
                return;
            }
            var info = compatMap[slug][bikeSlug] || {};
            var status = info.status || 'incompatible';
            var isIncompatible = status === 'incompatible';
            card.classList.toggle('incompatible-dim', isIncompatible && !onlyCompat);
            card.classList.toggle('incompatible-hide', isIncompatible && onlyCompat);
            if (isIncompatible && onlyCompat) hiddenByFilter++;
        });
        productRows.forEach(function(row) {
            var slug = row.getAttribute('data-product-slug');
            if (!slug || !bikeSlug || !compatMap[slug]) {
                row.classList.remove('incompatible-dim');
                row.classList.remove('incompatible-hide');
                return;
            }
            var info = compatMap[slug][bikeSlug] || {};
            var status = info.status || 'incompatible';
            var isIncompatible = status === 'incompatible';
            row.classList.toggle('incompatible-dim', isIncompatible && !onlyCompat);
            row.classList.toggle('incompatible-hide', isIncompatible && onlyCompat);
        });

        // Show toolbar only when a bike is selected
        if (guideToolbar) guideToolbar.style.display = bikeSlug ? '' : 'none';

        // Update filter count
        if (filterCount && bikeSlug) {
            if (onlyCompat) {
                filterCount.textContent = compatCount + ' of ' + totalCount;
            } else {
                filterCount.textContent = compatCount + ' compatible';
            }
        }

        // Update status text beside bike selector
        updateStatus(bikeSlug, compatCount, totalCount);

        // Show/hide empty state
        if (emptyState) {
            emptyState.style.display = (bikeSlug && compatCount === 0) ? 'block' : 'none';
        }

        // Update results heading
        if (resultsHeading && bikeSlug) {
            if (compatCount > 0) {
                resultsHeading.textContent = compatCount + ' of ' + totalCount + ' products fit your ' + bikeName;
                if (resultsDesc) {
                    resultsDesc.textContent = 'Showing compatibility results for the ' + bike.brand + ' ' + bikeName + '. Compatible products are highlighted, incompatible products are dimmed.';
                }
            } else {
                resultsHeading.textContent = 'No verified products for your ' + bikeName;
                if (resultsDesc) {
                    resultsDesc.textContent = 'We don\'t have verified compatibility data for ' + config.category.toLowerCase() + ' products with the ' + bike.brand + ' ' + bikeName + ' yet.';
                }
            }
        } else if (resultsHeading) {
            resultsHeading.textContent = 'Our Top Picks at a Glance';
            if (resultsDesc) {
                resultsDesc.textContent = 'We\'ve tested and reviewed ' + totalCount + ' ' + config.category.toLowerCase() + ' to help you find the perfect one. Our recommendations are based on quality, value, user reviews, and expert testing.';
            }
        }

        // Update "Continue Shopping" subtitle
        if (continueSubtitle && bikeSlug) {
            continueSubtitle.textContent = 'More accessories for your ' + bikeName;
        } else if (continueSubtitle) {
            continueSubtitle.textContent = 'Explore more accessory guides';
        }

        // Update "Continue Shopping" links to preserve bike selection
        continueLinks.forEach(function(link) {
            var guideSlug = link.getAttribute('data-guide-slug');
            if (guideSlug && config.baseUrl) {
                var url = config.baseUrl + 'guides/' + guideSlug + '/index.html';
                if (bikeSlug) url += '?bike=' + bikeSlug;
                link.href = url;
            }
        });

        // Assign recommendation badges
        assignRecBadges(bikeSlug);
    }

    function updateStatus(bikeSlug, compatCount, totalCount) {
        if (!statusText) return;
        if (!bikeSlug) {
            statusText.textContent = 'Showing all products';
            return;
        }
        var cat = config.category.toLowerCase();
        if (compatFilter && compatFilter.checked) {
            statusText.textContent = 'Showing ' + compatCount + ' compatible ' + cat + 's';
        } else {
            statusText.textContent = 'Showing ' + compatCount + ' compatible ' + cat + 's of ' + totalCount;
        }
    }

    // ===== Initialize =====
    // Priority: ?bike= param > BikeGarage > no selection
    var urlBike = getBikeParam();
    var initialBike = urlBike || BikeGarage.get();

    if (initialBike && findBike(initialBike)) {
        if (urlBike) BikeGarage.save(urlBike);

        select.value = initialBike;
        applyFilter(initialBike);
    }

    // Listen for select changes
    select.addEventListener('change', function() {
        var slug = this.value;
        if (slug) {
            BikeGarage.save(slug);
        } else {
            BikeGarage.clear();
        }
        setBikeParam(slug);
        applyFilter(slug);
    });

    // Compatibility filter toggle
    if (compatFilter) {
        compatFilter.addEventListener('change', function() {
            var urlBike = getBikeParam() || BikeGarage.get();
            if (urlBike) applyFilter(urlBike);
        });
    }

    // Empty state buttons
    var showUniversalBtn = document.getElementById('showUniversalBtn');
    var showAllBtn = document.getElementById('showAllBtn');
    if (showUniversalBtn) {
        showUniversalBtn.addEventListener('click', function() {
            if (compatFilter) { compatFilter.checked = false; }
            var urlBike = getBikeParam() || BikeGarage.get();
            if (urlBike) applyFilter(urlBike);
        });
    }
    if (showAllBtn) {
        showAllBtn.addEventListener('click', function() {
            select.value = '';
            BikeGarage.clear();
            setBikeParam('');
            applyFilter('');
            showSelectedInfo('');
        });
    }

    // Sync with external garage changes (e.g. from header widget)
    BikeGarage.onChange(function(slug) {
        if (slug && findBike(slug)) {
            select.value = slug;
            setBikeParam(slug);
            applyFilter(slug);
            showSelectedInfo(slug);
        }
    });

    // ===== Motorcycle Card Sync =====
    var motorcycleName = document.getElementById('motorcycleName');
    var motorcycleCompat = document.getElementById('motorcycleCompat');
    var changeMotorcycleBtn = document.getElementById('changeMotorcycleBtn');

    function updateMotorcycleCard(bikeSlug) {
        if (!motorcycleName) return;
        var bike = bikeSlug ? findBike(bikeSlug) : null;
        if (bike) {
            motorcycleName.textContent = bike.brand + ' ' + bike.model;
        } else {
            motorcycleName.textContent = 'Select your bike';
        }
        if (motorcycleCompat) {
            var totalCount = productCards.length;
            var compatCount = 0;
            if (bikeSlug) {
                var compatMap = config.compatibilityMap || {};
                productCards.forEach(function(card) {
                    var slug = card.getAttribute('data-product-slug');
                    if (slug && compatMap[slug]) {
                        var info = compatMap[slug][bikeSlug] || {};
                        var status = info.status || 'incompatible';
                        if (status === 'compatible' || status === 'universal') compatCount++;
                    }
                });
                motorcycleCompat.textContent = compatCount + ' of ' + totalCount + ' compatible';
            } else {
                motorcycleCompat.textContent = totalCount + ' products available';
            }
        }
    }

    // Define showSelectedInfo and override applyFilter to update card
    showSelectedInfo = function(slug) {
        updateMotorcycleCard(slug);
    };

    var origApplyFilter = applyFilter;
    applyFilter = function(slug) {
        origApplyFilter(slug);
        updateMotorcycleCard(slug);
    };

    // Handle Change Motorcycle button
    if (changeMotorcycleBtn) {
        changeMotorcycleBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            // Try to open the garage dropdown from the header
            var garageBtn = document.getElementById('garageBtn');
            if (garageBtn) {
                garageBtn.click();
            }
        });
    }

    // Initial card update
    var initialBikeUrl = getBikeParam() || BikeGarage.get();
    updateMotorcycleCard(initialBikeUrl && findBike(initialBikeUrl) ? initialBikeUrl : '');
})();

// ===== Category Page Motorcycle Card Sync =====
(function() {
    if (typeof BikeGarage === 'undefined') return;
    var catName = document.getElementById('catMotorcycleName');
    var catCompat = document.getElementById('catMotorcycleCompat');
    var catChangeBtn = document.getElementById('catChangeMotorcycleBtn');
    if (!catName) return;

    function updateCatCard(slug) {
        if (!slug) {
            catName.textContent = 'Select your bike';
            if (catCompat) catCompat.textContent = '';
            return;
        }
        var found = null;
        var bikes = window.__garageMotorcycles || [];
        for (var i = 0; i < bikes.length; i++) {
            if (bikes[i].slug === slug) { found = bikes[i]; break; }
        }
        if (found) {
            catName.textContent = found.brand + ' ' + found.model;
        } else {
            catName.textContent = 'Select your bike';
        }
        if (catCompat) {
            catCompat.textContent = 'Compatibility available';
        }
    }

    var currentSlug = BikeGarage.get();
    if (currentSlug) updateCatCard(currentSlug);

    BikeGarage.onChange(function(slug) {
        updateCatCard(slug || '');
    });

    if (catChangeBtn) {
        catChangeBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            var garageBtn = document.getElementById('garageBtn');
            if (garageBtn) garageBtn.click();
        });
    }
})();
