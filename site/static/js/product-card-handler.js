/*!
 * Product Card Click Handler
 * Makes entire product cards clickable for Import Queue management
 * Changes: Click anywhere on card to add/remove from Import Queue
 * Visual: Selected cards have green border and checkmark
 */

(function() {
    // Check if we're in the browser
    if (typeof window === 'undefined') return;

    // ===== CONFIGURATION =====
    const CONFIG = {
        QUEUE_STORAGE_KEY: 'bikereview_import_queue',
        SELECTED_CLASS: 'product-card-selected',
        HOVER_CLASS: 'product-card-hover',
        CHECKMARK_CLASS: 'product-card-checkmark',
        GREEN_BORDER_STYLE: '3px solid #10b981',
        ANIMATION_DURATION: 200,
        DEBOUNCE_DELAY: 150
    };
    
    // Add CSS for selected cards and checkmarks
    if (typeof document !== 'undefined') {
        const style = document.createElement('style');
        style.textContent = `
        .${CONFIG.SELECTED_CLASS} {
            border: ${CONFIG.GREEN_BORDER_STYLE} !important;
            background: rgba(16, 185, 129, 0.05) !important;
            position: relative;
            transition: all ${CONFIG.ANIMATION_DURATION}ms ease;
        }
        .${CONFIG.SELECTED_CLASS}::after {
            content: '✓';
            position: absolute;
            top: 8px;
            right: 8px;
            background: #10b981;
            color: white;
            width: 20px;
            height: 20px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
            font-weight: bold;
            z-index: 10;
        }
        
        .import-queue-panel {
            position: sticky;
            top: 0;
            background: white;
            padding: 16px;
            margin: -16px -16px 24px;
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            margin-bottom: 24px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            transition: all 0.3s ease;
            z-index: 100;
        }
        
        .import-queue-panel.empty {
            opacity: 0.7;
        }
        
        .queue-panel-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 16px;
        }
        
        .queue-panel-header h3 {
            margin: 0;
            font-size: 18px;
            font-weight: 600;
        }
        
        .queue-stats {
            font-size: 14px;
            color: #6b7280;
        }
        
        .queue-items {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
            gap: 12px;
            max-height: 400px;
            overflow-y: auto;
            margin-bottom: 16px;
        }
        
        .queue-item {
            display: flex;
            align-items: center;
            padding: 12px;
            background: white;
            border: 1px solid #e5e7eb;
            border-radius: 6px;
            transition: all 0.2s ease;
            position: relative;
        }
        
        .queue-item:hover {
            border-color: #10b981;
            box-shadow: 0 2px 8px rgba(16, 185, 129, 0.1);
        }
        
        .queue-item-image {
            flex: 0 0 60px;
            height: 60px;
            margin-right: 12px;
        }
        
        .queue-item-image img {
            width: 100%;
            height: 100%;
            object-fit: cover;
            border-radius: 4px;
        }
        
        .queue-item-details {
            flex: 1;
            min-width: 0;
        }
        
        .queue-item-title {
            font-size: 14px;
            font-weight: 600;
            margin-bottom: 4px;
            line-height: 1.3;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }
        
        .queue-item-price {
            font-size: 13px;
            color: #10b981;
            font-weight: 500;
        }
        
        .queue-item-remove {
            flex: 0 0 auto;
            width: 28px;
            height: 28px;
            border-radius: 50%;
            border: 1px solid #e5e7eb;
            background: white;
            color: #6b7280;
            font-size: 18px;
            cursor: pointer;
            transition: all 0.2s ease;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .queue-item-remove:hover {
            background: #ef4444;
            border-color: #ef4444;
            color: white;
        }
        
        .queue-footer {
            border-top: 1px solid #e5e7eb;
            padding-top: 16px;
        }
        
        .queue-empty {
            text-align: center;
            padding: 24px;
            color: #9ca3af;
            font-style: italic;
        }
        `;
        document.head.appendChild(style);
    }

    // ===== STATE MANAGEMENT =====
    const state = {
        queue: [],
        isInitialized: false,
        lastUpdate: 0
    };

    // ===== INITIALIZATION =====
    function init() {
        if (state.isInitialized) return;

        // Load queue from localStorage
        loadQueue();

        // Make product cards clickable
        makeCardsClickable();

        // Add event listeners for hover effects
        addHoverEffects();

        // Attach queue panel
        attachQueuePanel();

        // Save initial state
        updateQueueState();
        state.isInitialized = true;
    }

    // ===== QUEUE MANAGEMENT =====
    function loadQueue() {
        try {
            const stored = localStorage.getItem(CONFIG.QUEUE_STORAGE_KEY);
            state.queue = stored ? JSON.parse(stored) : [];
        } catch (e) {
            state.queue = [];
        }
    }

    function saveQueue() {
        try {
            localStorage.setItem(CONFIG.QUEUE_STORAGE_KEY, JSON.stringify(state.queue));
            window.dispatchEvent(new CustomEvent('importQueueChanged', {
                detail: { queue: [...state.queue] }
            }));
            updateQueuePanel();
        } catch (e) {}
    }

    function toggleProduct(productSlug) {
        const index = state.queue.indexOf(productSlug);
        if (index === -1) {
            state.queue.push(productSlug);
            return true;
        } else {
            state.queue.splice(index, 1);
            return false;
        }
    }

    function removeFromQueue(productSlug) {
        const index = state.queue.indexOf(productSlug);
        if (index !== -1) {
            state.queue.splice(index, 1);
            saveQueue();
            updateAllCardUIs();
        }
    }

    function getQueuedProductDetails() {
        const details = [];
        const cards = document.querySelectorAll('.product-card, .hp-product-card, .bg-product-card, .guide-product-card');
        cards.forEach(card => {
            const slug = getProductSlug(card);
            if (slug && isProductQueued(slug)) {
                const title = card.querySelector('.card-title, .product-title, h2, h3, .title, .product-card-title') ? 
                    card.querySelector('.card-title, .product-title, h2, h3, .title, .product-card-title').textContent || '' : '';
                const price = card.querySelector('.price, .product-price, [data-price]') ? 
                    card.querySelector('.price, .product-price, [data-price]').textContent || '' : '';
                const image = card.querySelector('img') ? card.querySelector('img').src || '' : '';
                details.push({ slug, title, price, image });
            }
        });
        return details;
    }

    function isProductQueued(productSlug) {
        return state.queue.includes(productSlug);
    }

    function clearQueue() {
        state.queue = [];
        saveQueue();
    }

    // ===== QUEUE QUEUE PANEL UI =====
    function createQueuePanel() {
        if (typeof document === 'undefined') return;
        const panel = document.createElement('div');
        panel.id = 'importQueuePanel';
        panel.className = 'import-queue-panel';
        panel.innerHTML = `
            <div class="queue-panel-header">
                <h3>Import Queue</h3>
                <div class="queue-stats">(<span id="queueCount">0</span>)</div>
                <button id="clearQueueBtn" class="btn btn-sm btn-secondary">Clear Queue</button>
            </div>
            <div id="queueItems" class="queue-items"></div>
            <div class="queue-footer">
                <button id="importSelectedBtn" class="btn btn-accent btn-block" disabled>Import Selected</button>
            </div>
        `;
        return panel;
    }

    function updateQueuePanel() {
        const panel = document.getElementById('importQueuePanel');
        const queueCountEl = document.getElementById('queueCount');
        const queueItemsEl = document.getElementById('queueItems');
        const importBtn = document.getElementById('importSelectedBtn');
        const clearBtn = document.getElementById('clearQueueBtn');

        if (!panel) return;

        queueCountEl.textContent = state.queue.length;

        if (state.queue.length === 0) {
            panel.classList.add('empty');
            queueItemsEl.innerHTML = '<div class="queue-empty">Select products to import</div>';
            importBtn.disabled = true;
            return;
        }

        panel.classList.remove('empty');

        const itemsHtml = getQueuedProductDetails().map(item => {
            return `
                <div class="queue-item" data-slug="${item.slug}">
                    <div class="queue-item-image">
                        <img src="${item.image || '/static/images/placeholder.jpg'}" alt="${item.title}" loading="lazy" onerror="this.src='/static/images/placeholder.jpg'" />
                    </div>
                    <div class="queue-item-details">
                        <div class="queue-item-title" title="${item.title}">${item.title}</div>
                        <div class="queue-item-price">${item.price || 'Price not available'}</div>
                    </div>
                    <button class="queue-item-remove" data-slug="${item.slug}" title="Remove from queue">×</button>
                </div>
            `;
        }).join('');

        queueItemsEl.innerHTML = itemsHtml;

        importBtn.disabled = state.queue.length === 0;
        clearBtn.disabled = state.queue.length === 0;

        addQueuePanelEventListeners();
    }

    function addQueuePanelEventListeners() {
        document.querySelectorAll('#importQueuePanel .queue-item-remove').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const slug = btn.dataset.slug;
                if (slug) {
                    removeFromQueue(slug);
                }
            });
        });

        document.getElementById('clearQueueBtn')?.addEventListener('click', () => {
            clearQueue();
        });

        document.getElementById('importSelectedBtn')?.addEventListener('click', () => {
            importSelectedItems();
        });
    }

    function importSelectedItems() {
        console.log('Importing selected items:', state.queue);
        window.dispatchEvent(new CustomEvent('importRequested', {
            detail: { queue: [...state.queue] }
        }));
        clearQueue();
    }

    function attachQueuePanel() {
        const existingPanel = document.getElementById('importQueuePanel');
        if (existingPanel) {
            existingPanel.remove();
        }

        const container = document.querySelector('.container, #main, #content') || document.body;
        if (container) {
            container.insertBefore(createQueuePanel(), container.firstChild.nextSibling);
            updateQueuePanel();
        }
    }

    // ===== UI UPDATE =====
    function updateCardUI(cardElement, isQueued) {
        const wrapper = cardElement.closest('.product-card-wrapper');
        if (!wrapper) return;

        if (isQueued) {
            wrapper.classList.add(CONFIG.SELECTED_CLASS);
        } else {
            wrapper.classList.remove(CONFIG.SELECTED_CLASS);
        }
    }

    function updateAllCardUIs() {
        const cards = document.querySelectorAll('.product-card, .hp-product-card, .bg-product-card, .guide-product-card');
        cards.forEach(card => {
            const slug = getProductSlug(card);
            if (slug) {
                const isQueued = isProductQueued(slug);
                updateCardUI(card, isQueued);
            }
        });
    }

    // ===== EVENT HANDLERS =====
    function onCardClick(e) {
        const card = e.currentTarget;
        const slug = getProductSlug(card);
        if (!slug) return;

        e.preventDefault();

        // Handle different card types
        if (card.classList.contains('hp-product-card')) {
            // For homepage cards, navigate to product page
            const productUrl = card.getAttribute('href') || card.querySelector('a[href]')?.getAttribute('href');
            if (productUrl) {
                // Toggle queue before navigation
                toggleProduct(slug);
                saveQueue();
                window.location.href = productUrl;
            }
        } else if (card.classList.contains('bg-product-card')) {
            // For category cards, toggle queue and navigate
            const productUrl = card.getAttribute('href') || card.querySelector('a[href]')?.getAttribute('href');
            if (productUrl) {
                const wasQueued = isProductQueued(slug);
                toggleProduct(slug);
                updateCardUI(card, isProductQueued(slug));
                saveQueue();
                window.location.href = productUrl;
            }
        } else if (card.classList.contains('guide-product-card')) {
            // For guide cards, toggle queue and navigate
            const productUrl = card.getAttribute('href') || card.querySelector('a[href]')?.getAttribute('href');
            if (productUrl) {
                toggleProduct(slug);
                window.location.href = productUrl;
                saveQueue();
            }
        } else if (card.classList.contains('product-card')) {
            // For product cards in collections, check if clicked on non-interactive elements
            const target = e.target;
            if (target.closest('.product-card-actions, .product-badge, .product-badge, .product-card-image a, .product-card-title a')) {
                return; // Let these elements handle their own click
            }

            // Toggle queue
            const wasQueued = isProductQueued(slug);
            toggleProduct(slug);
            updateCardUI(card, isProductQueued(slug));
            saveQueue();
        }
    }

    function onCardHover(e) {
        const card = e.currentTarget;
        card.classList.add(CONFIG.HOVER_CLASS);
    }

    function onCardLeave(e) {
        const card = e.currentTarget;
        card.classList.remove(CONFIG.HOVER_CLASS);
    }

    // ===== HELPER FUNCTIONS =====
    function getProductSlug(card) {
        // Get slug from various sources
        return card.getAttribute('data-product-slug') ||
               card.getAttribute('data-slug') ||
               card.getAttribute('data-asin') ||
               card.dataset.slug ||
               card.dataset.productSlug;
    }

    function makeCardsClickable() {
        const cards = document.querySelectorAll('.product-card, .hp-product-card, .bg-product-card, .guide-product-card');
        cards.forEach(card => {
            const slug = getProductSlug(card);
            if (!slug) return;

            // Set initial queue state
            updateCardUI(card, isProductQueued(slug));

            // Skip if card has special interactive elements that shouldn't trigger card click
            const hasInteractive = card.querySelector('button, a[href], input, select, textarea');
            if (hasInteractive && !card.classList.contains('bg-product-card')) {
                // For cards with interactive elements, we need to handle the click carefully
                // The link elements will handle their own clicks, and we'll handle direct card clicks
                const cardWrapper = card.closest('.product-card-wrapper, .hp-card, .bg-card, .guide-card');
                if (cardWrapper) {
                    cardWrapper.style.cursor = 'pointer';
                    cardWrapper.addEventListener('click', function(e) {
                        // Only trigger if the click is on the wrapper itself, not its children
                        if (e.target === cardWrapper || e.target === card) {
                            onCardClick(e);
                        }
                    });
                }
            } else {
                // Simple cards - make the entire card clickable
                card.style.cursor = 'pointer';
                card.addEventListener('click', onCardClick);
            }

            // Add hover effects
            card.addEventListener('mouseenter', onCardHover);
            card.addEventListener('mouseleave', onCardLeave);
        });
    }

    function addHoverEffects() {
        const cards = document.querySelectorAll('.product-card, .hp-product-card, .bg-product-card, .guide-product-card');
        cards.forEach(card => {
            card.addEventListener('mouseenter', debounce(onCardHover, CONFIG.DEBOUNCE_DELAY));
            card.addEventListener('mouseleave', debounce(onCardLeave, CONFIG.DEBOUNCE_DELAY));
        });
    }

    // ===== UTILITY FUNCTIONS =====
    function debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }

    function updateQueueState() {
        // Dispatch event to notify other parts of the app
        window.dispatchEvent(new CustomEvent('importQueueChanged', {
            detail: { queue: [...state.queue], count: state.queue.length }
        }));
    }

    // ===== PUBLIC API =====
    window.ProductCardHandler = {
        init,
        toggleProduct,
        isProductQueued,
        getQueue: () => [...state.queue],
        clearQueue,
        loadQueue,
        saveQueue,
        updateAllCardUIs
    };

    // ===== START =====
    // Initialize on DOM ready or immediate if already loaded
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // Listen for navigation changes to update UI
    let currentPath = window.location.pathname;
    setInterval(() => {
        if (window.location.pathname !== currentPath) {
            currentPath = window.location.pathname;
            init();
        }
    }, 1000);

})();