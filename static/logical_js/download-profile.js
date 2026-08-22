(function(root, factory) {
    const api = factory();
    if (typeof module === 'object' && module.exports) {
        module.exports = api;
    }
    if (root) {
        root.YDLNAS_DOWNLOAD_PROFILE = api;
    }
})(typeof window !== 'undefined' ? window : globalThis, function() {
    const storageKey = 'ydlnasDownloadProfile:v1';
    const videoProfiles = new Set([
        'best', 'compatible-mp4', '2160p', '1440p', '1080p', '720p', '480p', '360p', '240p', '144p'
    ]);
    const audioProfiles = new Set(['audio', 'audio-m4a', 'audio-mp3', 'audio-opus']);
    const subtitleProfiles = new Set(['srt', 'vtt']);
    const subtitleLanguagePattern = /^[A-Za-z0-9_-]+(?:-[A-Za-z0-9_-]+)*$/;

    function normalize(profile) {
        if (!profile || typeof profile !== 'object') {
            return null;
        }

        const resolution = String(profile.resolution || '').trim();
        const mode = String(profile.mode || '').trim();
        const subtitleLanguage = String(profile.subtitleLanguage || '').trim();
        let expectedMode = '';

        if (videoProfiles.has(resolution)) {
            expectedMode = 'video';
        } else if (audioProfiles.has(resolution)) {
            expectedMode = 'audio';
        } else if (subtitleProfiles.has(resolution)) {
            expectedMode = 'subtitle';
        } else {
            return null;
        }

        if (mode !== expectedMode) {
            return null;
        }
        if (expectedMode === 'subtitle' && subtitleLanguage && !subtitleLanguagePattern.test(subtitleLanguage)) {
            return null;
        }

        return {
            version: 1,
            mode: expectedMode,
            resolution: resolution,
            subtitleLanguage: expectedMode === 'subtitle' ? subtitleLanguage : ''
        };
    }

    function fromSubmission(resolutionValue) {
        const value = String(resolutionValue || '').trim();
        const separator = value.indexOf('|');
        const resolution = separator >= 0 ? value.substring(0, separator) : value;
        const subtitleLanguage = separator >= 0 ? value.substring(separator + 1) : '';
        let mode = 'video';
        if (audioProfiles.has(resolution)) {
            mode = 'audio';
        } else if (subtitleProfiles.has(resolution)) {
            mode = 'subtitle';
        }
        return normalize({ mode: mode, resolution: resolution, subtitleLanguage: subtitleLanguage });
    }

    function load(storage) {
        if (!storage || typeof storage.getItem !== 'function') {
            return null;
        }
        try {
            const value = storage.getItem(storageKey);
            if (!value) {
                return null;
            }
            const profile = normalize(JSON.parse(value));
            if (!profile && typeof storage.removeItem === 'function') {
                storage.removeItem(storageKey);
            }
            return profile;
        } catch (error) {
            return null;
        }
    }

    function save(storage, resolutionValue) {
        const profile = fromSubmission(resolutionValue);
        if (!profile || !storage || typeof storage.setItem !== 'function') {
            return null;
        }
        try {
            storage.setItem(storageKey, JSON.stringify(profile));
            return profile;
        } catch (error) {
            return null;
        }
    }

    return {
        storageKey: storageKey,
        fromSubmission: fromSubmission,
        load: load,
        normalize: normalize,
        save: save
    };
});
