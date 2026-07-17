// ===== Bike Garage Service =====
// Persistent motorcycle selection across the site.
// Exposes: window.BikeGarage
// Reads motorcycles from window.__garageMotorcycles (injected by base.html)
(function() {
    var STORAGE_KEY = 'bikereview_my_garage';
    var _listeners = [];
    var _current = '';

    function _load() {
        try { return localStorage.getItem(STORAGE_KEY) || ''; } catch(e) { return ''; }
    }

    function _save(slug) {
        try { localStorage.setItem(STORAGE_KEY, slug); } catch(e) {}
    }

    function _remove() {
        try { localStorage.removeItem(STORAGE_KEY); } catch(e) {}
    }

    function _notify() {
        for (var i = 0; i < _listeners.length; i++) {
            try { _listeners[i](_current); } catch(e) {}
        }
    }

    var garage = {
        get: function() {
            return _current || _load();
        },

        save: function(slug) {
            if (!slug || slug === _current) return;
            _current = slug;
            _save(slug);
            _notify();
        },

        clear: function() {
            _current = '';
            _remove();
            _notify();
        },

        find: function(slug) {
            var list = garage.getAll();
            for (var i = 0; i < list.length; i++) {
                if (list[i].slug === slug) return list[i];
            }
            return null;
        },

        getAll: function() {
            return (typeof window.__garageMotorcycles !== 'undefined') ? window.__garageMotorcycles : [];
        },

        onChange: function(callback) {
            if (typeof callback === 'function') {
                _listeners.push(callback);
            }
        },

        overrideFromURL: function() {
            var params = new URLSearchParams(window.location.search);
            var bike = params.get('bike');
            if (bike) {
                _current = bike;
                _save(bike);
                _notify();
                return true;
            }
            return false;
        },

        init: function() {
            _current = _load();
            garage.overrideFromURL();
            return _current;
        }
    };

    window.BikeGarage = garage;
})();
