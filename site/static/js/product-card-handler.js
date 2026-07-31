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
            position: relative;
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

    function isProductQueued(productSlug) {
        return state.queue.includes(productSlug);
    }

    function clearQueue() {
        state.queue = [];
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