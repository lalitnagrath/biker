// ===== Mobile Menu Toggle =====
const mobileMenuToggle = document.getElementById('mobileMenuToggle');
const mainNav = document.getElementById('mainNav');

if (mobileMenuToggle && mainNav) {
    mobileMenuToggle.addEventListener('click', () => {
        mainNav.classList.toggle('active');
        mobileMenuToggle.classList.toggle('active');
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
        searchInput.focus();
    }
}

function closeSearch() {
    if (searchOverlay) {
        searchOverlay.classList.remove('active');
        searchInput.value = '';
        searchResults.innerHTML = '';
    }
}

if (searchToggle) searchToggle.addEventListener('click', openSearch);
if (searchClose) searchClose.addEventListener('click', closeSearch);
if (heroSearch) {
    heroSearch.addEventListener('focus', () => {
        openSearch();
    });
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

// Populate search data from JSON
if (typeof siteData !== 'undefined') {
    // Motorcycles
    if (siteData.motorcycles) {
        siteData.motorcycles.forEach(bike => {
            searchData.push({
                type: 'Motorcycle',
                title: bike.brand + ' ' + bike.model,
                url: 'motorcycles/' + bike.slug + '/index.html',
                excerpt: bike.engine + ' | ' + bike.type + ' | MRP ' + bike.price
            });
        });
    }

    // Products
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

    // Brands
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

    // Articles
    if (siteData.articles) {
        siteData.articles.forEach(article => {
            searchData.push({
                type: 'Article',
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

            if (query.length < 2) {
                searchResults.innerHTML = '';
                return;
            }

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

// ===== Tab Navigation =====
const tabBtns = document.querySelectorAll('.tab-btn');
const tabContents = document.querySelectorAll('.tab-content');

tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        const tab = btn.dataset.tab;

        tabBtns.forEach(b => b.classList.remove('active'));
        tabContents.forEach(c => c.classList.remove('active'));

        btn.classList.add('active');
        const content = document.getElementById(tab);
        if (content) content.classList.add('active');
    });
});

// ===== Filter Functionality =====
const filterForm = document.getElementById('filterForm');
const productList = document.getElementById('productList');

if (filterForm && productList) {
    const sortFilter = document.getElementById('sortFilter');
    const brandFilter = document.getElementById('brandFilter');
    const priceFilter = document.getElementById('priceFilter');
    const ratingFilter = document.getElementById('ratingFilter');

    function applyFilters() {
        const products = Array.from(productList.querySelectorAll('.product-card-horizontal'));
        const sort = sortFilter ? sortFilter.value : 'rating';
        const brand = brandFilter ? brandFilter.value : '';
        const priceRange = priceFilter ? priceFilter.value : '';
        const minRating = ratingFilter ? parseFloat(ratingFilter.value) || 0 : 0;

        // Filter
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

        // Sort
        const visibleProducts = products.filter(p => p.style.display !== 'none');

        visibleProducts.sort((a, b) => {
            switch (sort) {
                case 'rating':
                    return parseFloat(b.dataset.rating) - parseFloat(a.dataset.rating);
                case 'price-low':
                    return parseInt(a.dataset.price) - parseInt(b.dataset.price);
                case 'price-high':
                    return parseInt(b.dataset.price) - parseInt(a.dataset.price);
                case 'reviews':
                    return parseInt(b.dataset.reviews) - parseInt(a.dataset.reviews);
                default:
                    return 0;
            }
        });

        visibleProducts.forEach(product => productList.appendChild(product));
    }

    [sortFilter, brandFilter, priceFilter, ratingFilter].forEach(filter => {
        if (filter) filter.addEventListener('change', applyFilters);
    });
}

// ===== Lazy Loading =====
if ('IntersectionObserver' in window) {
    const lazyImages = document.querySelectorAll('img[data-src]');
    const imageObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const img = entry.target;
                img.src = img.dataset.src;
                img.removeAttribute('data-src');
                imageObserver.unobserve(img);
            }
        });
    });

    lazyImages.forEach(img => imageObserver.observe(img));
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

// ===== Bike Filters (Homepage) =====
const bikeGrid = document.getElementById('bikeGrid');
const brandFilterBtns = document.querySelectorAll('.brand-filter-btn');
const typeFilterBtns = document.querySelectorAll('.type-filter-btn');

if (bikeGrid) {
    let selectedBrand = 'all';
    let selectedType = 'all';

    function filterBikes() {
        const cards = bikeGrid.querySelectorAll('.bike-card');
        cards.forEach(card => {
            const brand = card.dataset.brand;
            const type = card.dataset.type;
            const showBrand = selectedBrand === 'all' || brand === selectedBrand;
            const showType = selectedType === 'all' || type === selectedType;
            card.style.display = (showBrand && showType) ? '' : 'none';
        });
    }

    brandFilterBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            brandFilterBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            selectedBrand = btn.dataset.brand;
            filterBikes();
        });
    });

    typeFilterBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            typeFilterBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            selectedType = btn.dataset.type;
            filterBikes();
        });
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