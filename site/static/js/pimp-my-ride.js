/* ==============================================
   Pimp My Ride - Upgrade Collections explorer
   UI-only behaviour: expand/collapse panels, tab
   switching and animations. All data is generated
   at build time and embedded in the page as
   window.PIMP_MY_RIDE_DATA — no fetch() calls,
   no API routes, no network requests.
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
        collectionsBySlug: {},
        expanded: {}
    };

    var grid = document.getElementById('pmrCardGrid');
    var moreGrid = document.getElementById('pmrMoreGrid');
    var panelsWrap = document.getElementById('pmrPanels');
    var viewMoreBtn = document.getElementById('pmrViewMore');

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
        var price = coll.startingPrice;
        var icon = coll.icon || '&#127930;';
        var priceLabel = price ? 'starting at &#8377;' + formatINR(price) : '';
        return '<div class="pmr-panel-wrap" data-panel-slug="' + escapeHtml(coll.slug) + '" data-open="false">' +
            '<div class="pmr-panel-inner">' +
                '<div class="pmr-panel">' +
                    '<div class="pmr-panel-head">' +
                        '<div class="pmr-panel-title-wrap">' +
                            '<span class="pmr-panel-icon">' + icon + '</span>' +
                            '<div>' +
                                (coll.badge ? '<span class="pmr-panel-badge">' + escapeHtml(coll.badge) + '</span>' : '') +
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
        var card = (grid && grid.querySelector('.pmr-card[data-slug="' + slug + '"]')) ||
            (moreGrid && moreGrid.querySelector('.pmr-card[data-slug="' + slug + '"]'));
        if (!wrap) return;
        var willOpen = typeof open === 'boolean' ? open : wrap.getAttribute('data-open') !== 'true';
        state.expanded[slug] = willOpen;

        if (willOpen) {
            wrap.setAttribute('data-open', 'true');
            wrap.classList.add('pmr-open');
            card.setAttribute('aria-expanded', 'true');
            renderProducts(slug, 'editors');
            setTimeout(function () {
                if (wrap.scrollIntoView) {
                    wrap.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }
            }, 30);
        } else {
            wrap.setAttribute('data-open', 'false');
            wrap.classList.remove('pmr-open');
            card.setAttribute('aria-expanded', 'false');
        }
    }

    function init(collections) {
        if (!grid || !panelsWrap) return;
        state.collectionsBySlug = {};
        collections.forEach(function (c) {
            state.collectionsBySlug[c.slug] = c;
        });

        // Collection cards are pre-rendered in the HTML by the generator so
        // crawlers see them; the panels (product rows + tabs) are rendered
        // here on demand.
        panelsWrap.innerHTML = collections.map(panelHTML).join('');

        if (grid) {
            grid.addEventListener('click', function (e) {
                var card = e.target.closest('.pmr-card');
                if (!card) return;
                if (e.preventDefault) e.preventDefault();
                togglePanel(card.getAttribute('data-slug'));
            });
        }

        if (moreGrid) {
            moreGrid.addEventListener('click', function (e) {
                var card = e.target.closest('.pmr-card');
                if (!card) return;
                if (e.preventDefault) e.preventDefault();
                togglePanel(card.getAttribute('data-slug'));
            });
        }

        if (viewMoreBtn) {
            viewMoreBtn.addEventListener('click', function (e) {
                var willShow = moreGrid.hidden;
                moreGrid.hidden = !willShow;
                moreGrid.classList.toggle('is-visible', willShow);
                viewMoreBtn.setAttribute('aria-expanded', willShow ? 'true' : 'false');
                var label = viewMoreBtn.querySelector('.pmr-view-more-label');
                if (label) label.textContent = willShow ? 'Show Less' : 'View More Collections';
                var chevron = viewMoreBtn.querySelector('.pmr-view-more-chevron');
                if (chevron) chevron.innerHTML = willShow ? '&#9652;' : '&#9662;';
            });
        }

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

    var buildData = window.PIMP_MY_RIDE_DATA;
    if (buildData && Array.isArray(buildData.collections) && buildData.collections.length) {
        init(buildData.collections);
    }
})();
