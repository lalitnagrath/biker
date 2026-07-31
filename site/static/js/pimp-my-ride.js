/* ==============================================
   Pimp My Ride - Upgrade Collections explorer
   Renders curated upgrade collections for the
   current motorcycle using the editorial API.
   ============================================== */
(function () {
    'use strict';

    var section = document.getElementById('pimp-my-ride');
    if (!section) return;

    var config = {
        motoSlug: section.getAttribute('data-moto-slug') || '',
        basePath: section.getAttribute('data-base-path') || './'
    };

    var state = {
        apiBase: null,
        products: {},
        expanded: {}
    };

    var grid = document.getElementById('pmrCardGrid');
    var panelsWrap = document.getElementById('pmrPanels');
    var stateBox = document.getElementById('pmrState');
    var stateText = document.getElementById('pmrStateText');

    function escapeHtml(str) {
        if (str == null) return '';
        return String(str).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }

    function quoteAttr(str) {
        return escapeHtml(str);
    }

    function formatINR(n) {
        var num = Number(n);
        if (!num || isNaN(num)) return '0';
        return num.toLocaleString('en-IN');
    }

    function starsHTML(rating) {
        var r = Math.round((Number(rating) || 0) * 2) / 2;
        var full = Math.floor(r);
        var half = (r - full) >= 0.5;
        var s = '';
        var i;
        for (i = 0; i < full; i++) s += '&#9733;';
        if (half) s += '&#9733;';
        for (i = full + (half ? 1 : 0); i < 5; i++) s += '&#9734;';
        return s;
    }

    function usableImage(url) {
        var s = String(url || '');
        if (s.indexOf('http://') === 0 || s.indexOf('https://') === 0 || s.indexOf('//') === 0) return s;
        if (s.indexOf('.') === -1) return '';
        var base = String(s).replace(/^.*[\\\/]/, '');
        if (!base) return '';
        return config.basePath + 'static/images/products/' + base;
    }

    function normalizeProduct(p) {
        if (!p) return null;
        var rawImg = p.image || p.amazon_image_url || '';
        return {
            slug: p.slug || p.asin || '',
            asin: p.asin || '',
            title: p.title || '',
            brand: p.brand || '',
            category: p.category || '',
            universal: !!p.universal,
            compatible_bikes: p.compatible_bikes || [],
            status: p.status || '',
            price: Number(p.price) || 0,
            mrp: Number(p.mrp) || 0,
            rating: Number(p.rating) || 0,
            review_count: Number(p.review_count) || 0,
            editor_rating: Number(p.editor_rating) || 0,
            editorial_verdict: p.editorial_verdict || '',
            editors_choice: !!p.editors_choice,
            image: usableImage(rawImg),
            affiliate_url: p.affiliate_url || ''
        };
    }

    function isCompatible(p) {
        if (!p) return false;
        if (p.universal) return true;
        var cb = p.compatible_bikes || [];
        if (typeof cb === 'string') return cb.split(',').indexOf(config.motoSlug) !== -1;
        if (Array.isArray(cb)) return cb.indexOf(config.motoSlug) !== -1;
        return false;
    }

    function scoreProduct(p) {
        if (!p) return 0;
        var s = 0;
        var ev = String(p.editorial_verdict || '').toLowerCase();
        if (p.editors_choice || ev.indexOf('editors choice') !== -1 || ev.indexOf('editor') !== -1) s += 40;
        else if (ev.indexOf('best value') !== -1) s += 30;
        else if (ev.indexOf('premium') !== -1) s += 25;
        s += (Number(p.editor_rating) || 0) * 0.3;
        s += (Number(p.rating) || 0) * 4;
        s += Math.min(20, Math.log10((Number(p.review_count) || 0) + 1) * 10);
        if (p.price > 0) s += 8;
        if (p.image) s += 4;
        if (p.affiliate_url) s += 2;
        if (p.status === 'approved') s += 6;
        else if (p.status === 'review') s += 3;
        return s;
    }

    function sortByScore(list) {
        return list.slice().sort(function (a, b) {
            return scoreProduct(b) - scoreProduct(a);
        });
    }

    function pickHero(coll) {
        var withImg = coll.compatibleProducts.filter(function (p) { return p.image; });
        var pool = withImg.length ? withImg : coll.compatibleProducts;
        return sortByScore(pool)[0] || null;
    }

    function minPrice(coll) {
        var prices = coll.compatibleProducts
            .map(function (p) { return Number(p.price) || 0; })
            .filter(function (n) { return n > 0; });
        return prices.length ? Math.min.apply(null, prices) : null;
    }

    function cardHTML(coll) {
        var hero = pickHero(coll);
        var heroImg = hero && hero.image ? hero.image : '';
        var price = minPrice(coll);
        var count = coll.compatibleProducts.length;
        var icon = coll.icon || '&#127930;';
        var countLabel = count + ' product' + (count === 1 ? '' : 's');
        var priceHTML = price
            ? '<span class="pmr-card-price">&#8377;' + formatINR(price) + '</span><span class="pmr-card-price-label">starting at</span>'
            : '<span class="pmr-card-price-label">Prices on request</span>';
        var mediaHTML = heroImg
            ? '<span class="pmr-card-media" style="background-image:url(\'' + quoteAttr(heroImg) + '\')"></span>'
            : '<span class="pmr-card-media pmr-card-media-empty"><span class="pmr-card-empty-icon">' + icon + '</span></span>';

        return '<button type="button" class="pmr-card" data-slug="' + escapeHtml(coll.slug) + '" aria-expanded="false">' +
            mediaHTML +
            '<span class="pmr-card-body">' +
                '<span class="pmr-card-icon-chip">' + icon + '</span>' +
                '<span class="pmr-card-name">' + escapeHtml(coll.name) + '</span>' +
                '<span class="pmr-card-desc">' + escapeHtml((coll.description || '').slice(0, 120)) + '</span>' +
                '<span class="pmr-card-meta">' +
                    '<span class="pmr-card-count">' + countLabel + '</span>' +
                    '<span class="pmr-card-price-wrap">' + priceHTML + '</span>' +
                '</span>' +
                '<span class="pmr-card-cta"><span>Explore</span><span class="pmr-card-chevron">&#9662;</span></span>' +
            '</span>' +
        '</button>';
    }

    function tabData(coll) {
        var list = coll.compatibleProducts;
        var ranked = sortByScore(list);
        var priced = list.filter(function (p) { return p.price > 0; });
        return {
            editors: ranked.slice(0, 3),
            trending: list.slice().sort(function (a, b) {
                if (b.review_count !== a.review_count) return (b.review_count || 0) - (a.review_count || 0);
                return (b.rating || 0) - (a.rating || 0);
            }).slice(0, 4),
            budget: priced.slice().sort(function (a, b) { return a.price - b.price; }).slice(0, 4),
            premium: priced.slice().sort(function (a, b) { return b.price - a.price; }).slice(0, 4),
            all: ranked
        };
    }

    function tabBadge(tabKey) {
        switch (tabKey) {
            case 'editors': return { cls: 'editors_choice', label: "Editor's Choice" };
            case 'trending': return { cls: 'most_reviewed', label: 'Trending' };
            case 'budget': return { cls: 'budget_pick', label: 'Budget Pick' };
            case 'premium': return { cls: 'premium_pick', label: 'Premium Pick' };
            default: return null;
        }
    }

    function productLink(p) {
        return p.affiliate_url || (config.basePath + 'products/' + encodeURIComponent(p.slug) + '/index.html');
    }

    function productCardHTML(p, badge) {
        var link = productLink(p);
        var imgHTML = p.image
            ? '<img src="' + quoteAttr(p.image) + '" alt="' + quoteAttr(p.title) + '" loading="lazy" onerror="this.style.display=\'none\';">'
            : '<div class="moto-product-no-image">&#128737;</div>';
        var badgeHTML = badge
            ? '<div class="moto-product-badge moto-badge-' + badge.cls + '">' + badge.label + '</div>'
            : '';
        var ratingHTML = '';
        if (p.rating && p.review_count) {
            ratingHTML = '<span class="moto-stars">' + starsHTML(p.rating) + '</span>' +
                '<span class="moto-rating-num">' + p.rating.toFixed(1) + '</span>' +
                '<span class="moto-reviews">(' + (p.review_count).toLocaleString('en-IN') + ')</span>';
        } else {
            ratingHTML = '<span class="verdict-label">Our Verdict</span>';
        }
        var priceHTML = '';
        if (p.price) {
            priceHTML = '<span class="moto-price">&#8377;' + formatINR(p.price) + '</span>';
            if (p.mrp > p.price) {
                var pct = Math.round(((p.mrp - p.price) / p.mrp) * 100);
                priceHTML += '<span class="moto-original-price">&#8377;' + formatINR(p.mrp) + '</span>' +
                    '<span class="moto-savings-badge">-' + pct + '%</span>';
            }
        }
        var cta = p.affiliate_url
            ? '<a href="' + quoteAttr(p.affiliate_url) + '" class="btn btn-sm btn-accent" target="_blank" rel="nofollow sponsored">Check Price on Amazon</a>'
            : '<a href="' + quoteAttr(config.basePath + 'products/' + encodeURIComponent(p.slug) + '/index.html') + '" class="btn btn-sm btn-outline">View Details</a>';

        return '<div class="moto-product-card">' +
            badgeHTML +
            '<a href="' + quoteAttr(link) + '" class="moto-product-link" target="_blank" rel="nofollow sponsored">' +
                '<div class="moto-product-image">' + imgHTML + '</div>' +
                '<div class="moto-product-info">' +
                    '<span class="moto-product-title">' + escapeHtml(p.title) + '</span>' +
                    '<div class="moto-product-rating our-verdict">' + ratingHTML + '</div>' +
                    '<div class="moto-product-pricing">' + priceHTML + '</div>' +
                    (p.brand ? '<span class="moto-product-brand">' + escapeHtml(p.brand) + '</span>' : '') +
                '</div>' +
            '</a>' +
            '<div class="moto-product-cta">' + cta + '</div>' +
        '</div>';
    }

    function renderProducts(slug, tabKey) {
        var coll = state.collectionsBySlug[slug];
        if (!coll) return;
        var data = tabData(coll)[tabKey] || [];
        var badge = tabBadge(tabKey);
        var html = data.map(function (p) {
            return productCardHTML(p, badge);
        }).join('');
        var wrap = panelsWrap.querySelector('[data-panel-slug="' + slug + '"] .pmr-products');
        if (wrap) wrap.innerHTML = html || '<div class="pmr-panel-empty">No products in this view yet.</div>';
    }

    function panelHTML(coll) {
        var count = coll.compatibleProducts.length;
        var price = minPrice(coll);
        var icon = coll.icon || '&#127930;';
        var priceLabel = price ? 'starting at &#8377;' + formatINR(price) : '';
        return '<div class="pmr-panel-wrap" data-panel-slug="' + escapeHtml(coll.slug) + '" data-open="false">' +
            '<div class="pmr-panel-inner">' +
                '<div class="pmr-panel">' +
                    '<div class="pmr-panel-head">' +
                        '<div class="pmr-panel-title-wrap">' +
                            '<span class="pmr-panel-icon">' + icon + '</span>' +
                            '<div>' +
                                '<h3 class="pmr-panel-title">' + escapeHtml(coll.name) + '</h3>' +
                                '<p class="pmr-panel-desc">' + escapeHtml(coll.description || '') + '</p>' +
                            '</div>' +
                        '</div>' +
                        '<div class="pmr-panel-meta">' +
                            '<span class="pmr-panel-count">' + count + ' compatible product' + (count === 1 ? '' : 's') + '</span>' +
                            (priceLabel ? '<span class="pmr-panel-price">' + priceLabel + '</span>' : '') +
                        '</div>' +
                        '<button type="button" class="pmr-panel-close" data-close="' + escapeHtml(coll.slug) + '" aria-label="Collapse ' + escapeHtml(coll.name) + '">&#10005;</button>' +
                    '</div>' +
                    '<div class="pmr-tabs" role="tablist" aria-label="Product views">' +
                        '<button type="button" class="pmr-tab is-active" data-tab="editors" role="tab" aria-selected="true">Editor\'s Choice</button>' +
                        '<button type="button" class="pmr-tab" data-tab="trending" role="tab" aria-selected="false">Trending</button>' +
                        '<button type="button" class="pmr-tab" data-tab="budget" role="tab" aria-selected="false">Budget Picks</button>' +
                        '<button type="button" class="pmr-tab" data-tab="premium" role="tab" aria-selected="false">Premium Picks</button>' +
                        '<button type="button" class="pmr-tab" data-tab="all" role="tab" aria-selected="false">View All</button>' +
                    '</div>' +
                    '<div class="pmr-products pmr-product-grid"></div>' +
                '</div>' +
            '</div>' +
        '</div>';
    }

    function togglePanel(slug, open) {
        var wrap = panelsWrap.querySelector('[data-panel-slug="' + slug + '"]');
        var card = grid.querySelector('.pmr-card[data-slug="' + slug + '"]');
        if (!wrap) return;
        var willOpen = typeof open === 'boolean' ? open : wrap.getAttribute('data-open') !== 'true';
        state.expanded[slug] = willOpen;

        if (willOpen) {
            wrap.setAttribute('data-open', 'true');
            wrap.classList.add('pmr-open');
            card.setAttribute('aria-expanded', 'true');
            renderProducts(slug, 'editors');
        } else {
            wrap.setAttribute('data-open', 'false');
            wrap.classList.remove('pmr-open');
            card.setAttribute('aria-expanded', 'false');
        }
    }

    function renderCards(collections) {
        state.collectionsBySlug = {};
        collections.forEach(function (c) {
            state.collectionsBySlug[c.slug] = c;
        });
        var cards = collections.map(cardHTML).join('');
        panelsWrap.innerHTML = collections.map(panelHTML).join('');
        grid.innerHTML = cards;

        grid.addEventListener('click', function (e) {
            var card = e.target.closest('.pmr-card');
            if (!card) return;
            togglePanel(card.getAttribute('data-slug'));
        });

        panelsWrap.addEventListener('click', function (e) {
            var tab = e.target.closest('.pmr-tab');
            if (tab) {
                var wrap = tab.closest('.pmr-panel-wrap');
                var slug = wrap.getAttribute('data-panel-slug');
                var tabKey = tab.getAttribute('data-tab');
                wrap.querySelectorAll('.pmr-tab').forEach(function (t) {
                    t.classList.toggle('is-active', t === tab);
                    t.setAttribute('aria-selected', t === tab ? 'true' : 'false');
                });
                renderProducts(slug, tabKey);
                return;
            }
            var close = e.target.closest('.pmr-panel-close');
            if (close) togglePanel(close.getAttribute('data-close'), false);
        });

        collections.forEach(function (c) {
            if (state.expanded[c.slug]) {
                togglePanel(c.slug, true);
            }
        });
    }

    function showState(html) {
        if (!stateBox) return;
        stateBox.innerHTML = html;
    }

    var apiBaseResolved = null;
    var apiBasePromise = null;

    function tryBase(base) {
        return fetch(base + '/api/upgrade-collections').then(function (r) {
            if (!r.ok) throw new Error('HTTP ' + r.status);
            return base;
        });
    }

    function getApiBase() {
        if (apiBaseResolved) return Promise.resolve(apiBaseResolved);
        if (apiBasePromise) return apiBasePromise;
        apiBasePromise = tryBase('')
            .catch(function () { return tryBase('http://localhost:8765'); })
            .then(function (base) {
                apiBaseResolved = base;
                return base;
            });
        return apiBasePromise;
    }

    function fetchJSON(path) {
        return getApiBase().then(function (base) {
            return fetch(base + path).then(function (r) {
                if (!r.ok) throw new Error('HTTP ' + r.status);
                return r.json();
            });
        });
    }

    function loadData() {
        showState('<span class="pmr-spinner"></span><span>Finding curated upgrades for ' + escapeHtml(config.motoSlug) + '...</span>');
        return fetchJSON('/api/upgrade-collections')
            .then(function (listData) {
                var list = (listData.collections || listData).filter(function (c) { return c.enabled !== false; });
                var detailJobs = list.map(function (col) {
                    return fetchJSON('/api/upgrade-collections/' + encodeURIComponent(col.slug)).then(function (d) {
                        return mergeCollection(col, d.products || []);
                    }).catch(function () {
                        return null;
                    });
                });
                return Promise.all(detailJobs);
            })
            .then(function (cols) {
                state.collections = cols
                    .filter(Boolean)
                    .filter(function (c) { return c.compatibleProducts.length > 0; })
                    .sort(function (a, b) {
                        return (a.sort_order || 0) - (b.sort_order || 0) || (a.name || '').localeCompare(b.name || '');
                    });
                if (!state.collections.length) {
                    showState('<span class="pmr-empty-icon">&#127937;</span><span>No curated upgrade collections match your ' + escapeHtml(config.motoSlug) + ' yet. Check back soon!</span>');
                    return;
                }
                renderCards(state.collections);
            });
    }

    function mergeCollection(col, detailProducts) {
        col.compatibleProducts = detailProducts
            .map(normalizeProduct)
            .map(function (p) { return p && state.products[p.slug] ? state.products[p.slug] : null; })
            .filter(Boolean)
            .filter(function (p) { return p.status !== 'rejected' && isCompatible(p); });
        return col;
    }

    fetchJSON('/api/products').then(function (data) {
        var all = (data.products || []).map(normalizeProduct);
        all.forEach(function (p) { if (p && p.slug) state.products[p.slug] = p; });
        return loadData();
    }).catch(function () {
        showState('<span class="pmr-empty-icon">&#9888;</span><span>Could not load upgrades. Please refresh the page.</span>');
    });
})();
