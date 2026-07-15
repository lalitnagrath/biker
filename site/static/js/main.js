// ===== Mobile Menu Toggle =====
const mobileMenuToggle = document.getElementById('mobileMenuToggle');
const mainNav = document.getElementById('mainNav');

if (mobileMenuToggle && mainNav) {
    mobileMenuToggle.addEventListener('click', () => {
        mainNav.classList.toggle('active');
        mobileMenuToggle.classList.toggle('active');
    });
    // Close menu when clicking a link
    mainNav.querySelectorAll('a').forEach(link => {
        link.addEventListener('click', () => {
            mainNav.classList.remove('active');
            mobileMenuToggle.classList.remove('active');
        });
    });
}

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

// ===== Bike Filters (Homepage) =====
const bikeShowcase = document.getElementById('bikeShowcase');
const filterBtns = document.querySelectorAll('.filter-btn');

if (bikeShowcase) {
    let selectedFilter = 'all';

    function filterBikes() {
        const cards = bikeShowcase.querySelectorAll('.bike-showcase-card');
        cards.forEach(card => {
            const brand = card.dataset.brand;
            const show = selectedFilter === 'all' || brand === selectedFilter;
            card.style.display = show ? '' : 'none';
        });
    }

    filterBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            filterBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            selectedFilter = btn.dataset.filter;
            filterBikes();
        });
    });
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
