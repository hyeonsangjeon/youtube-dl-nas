(function(root, factory) {
    const api = factory();
    if (typeof module === 'object' && module.exports) {
        module.exports = api;
    }
    if (root) {
        root.YDLNAS_BOOKMARKLET = api;
    }
})(typeof window !== 'undefined' ? window : globalThis, function() {
    const entryPath = '/youtube-dl/bookmarklet?url=';
    const windowName = 'ydlnas';
    const windowFeatures = 'width=640,height=820';

    function normalizeOrigin(origin) {
        let parsed;
        try {
            parsed = new URL(String(origin || ''));
        } catch (error) {
            return '';
        }
        if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
            return '';
        }
        return parsed.origin;
    }

    // The bookmarklet only opens the NAS dashboard with the current page URL.
    // It carries no credentials: the browser's own session cookie signs the
    // request in, and the server shows the URL for review instead of queueing it.
    // The #fragment is dropped: browsers never send it to servers, and it can hold
    // secrets such as OAuth access tokens or share-link keys. Building the address
    // from its parts also keeps "#" and "%" out of the javascript: URL itself.
    function source(origin) {
        const base = normalizeOrigin(origin);
        if (!base) {
            return '';
        }
        const target = JSON.stringify(base + entryPath);
        return 'javascript:(function(){'
            + 'var u=' + target + '+encodeURIComponent(location.origin+location.pathname+location.search);'
            + 'var w=window.open(u,' + JSON.stringify(windowName) + ',' + JSON.stringify(windowFeatures) + ');'
            + 'if(!w){location.href=u;}'
            + '})();';
    }

    return {
        entryPath: entryPath,
        normalizeOrigin: normalizeOrigin,
        source: source
    };
});
