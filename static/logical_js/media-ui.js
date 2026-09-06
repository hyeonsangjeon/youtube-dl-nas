(function(root, factory) {
    const api = factory();
    if (typeof module === 'object' && module.exports) {
        module.exports = api;
    }
    if (root) {
        root.YDLNAS_MEDIA_UI = api;
    }
})(typeof window !== 'undefined' ? window : globalThis, function() {
    function escapeHtml(value) {
        return String(value === null || value === undefined ? '' : value).replace(/[&<>"']/g, function(char) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char];
        });
    }

    function formatBytes(sizeValue, locale) {
        const size = Number(sizeValue || 0);
        if (!Number.isFinite(size) || size <= 0) {
            return '0 B';
        }
        const units = ['B', 'KB', 'MB', 'GB', 'TB'];
        let value = size;
        let unit = 0;
        while (value >= 1024 && unit < units.length - 1) {
            value /= 1024;
            unit++;
        }
        const precision = value >= 10 || unit === 0 ? 0 : 1;
        return new Intl.NumberFormat(locale || 'en', {
            minimumFractionDigits: precision,
            maximumFractionDigits: precision
        }).format(value) + ' ' + units[unit];
    }

    function safeThumbnailUrl(value) {
        const thumbnail = String(value || '').trim();
        return /^https?:\/\//i.test(thumbnail) || /^\/static\/thumbnail\//.test(thumbnail) ? thumbnail : '';
    }

    function fileHref(item, preview) {
        return '/static/' + (preview ? 'preview' : 'downfolder') + '/' + encodeURIComponent(item.uuid);
    }

    function closePreview() {
        const dialog = document.querySelector('.media-preview-dialog');
        if (dialog) {
            dialog.close();
        }
    }

    function trapFocus(event, container) {
        if (event.key !== 'Tab' || !container) {
            return;
        }
        const controls = Array.from(container.querySelectorAll(
            'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
        )).filter(function(element) { return element.getClientRects().length > 0; });
        if (!controls.length) {
            return;
        }
        const first = controls[0];
        const last = controls[controls.length - 1];
        const outside = !container.contains(document.activeElement);
        if (event.shiftKey && (document.activeElement === first || outside)) {
            event.preventDefault();
            last.focus();
        } else if (!event.shiftKey && (document.activeElement === last || outside)) {
            event.preventDefault();
            first.focus();
        }
    }

    function openPreview(item, t) {
        if (!item || !item.uuid || !item.file_exists || !['video', 'audio'].includes(item.download_type)) {
            return false;
        }
        closePreview();
        const previousFocus = document.activeElement;
        const dialog = document.createElement('dialog');
        dialog.className = 'media-preview-dialog';
        dialog.setAttribute('aria-labelledby', 'media-preview-title');
        const mediaTag = item.download_type === 'audio' ? 'audio' : 'video';
        dialog.innerHTML = `
            <div class="media-preview-content">
                <header class="media-preview-header">
                    <h2 id="media-preview-title">${escapeHtml(item.title || item.filename || t('preview.media'))}</h2>
                    <button type="button" class="media-preview-close" aria-label="${escapeHtml(t('preview.close'))}">&times;</button>
                </header>
                <div class="media-preview-player">
                    <${mediaTag} controls autoplay playsinline preload="metadata" src="${escapeHtml(fileHref(item, true))}"></${mediaTag}>
                </div>
            </div>`;
        dialog.querySelector('button').addEventListener('click', function() { dialog.close(); });
        dialog.addEventListener('click', function(event) {
            if (event.target === dialog) {
                dialog.close();
            }
        });
        dialog.addEventListener('close', function() {
            const media = dialog.querySelector(mediaTag);
            media.pause();
            media.removeAttribute('src');
            media.load();
            dialog.remove();
            if (previousFocus && document.contains(previousFocus)) {
                previousFocus.focus();
            }
        }, { once: true });
        document.body.appendChild(dialog);
        dialog.showModal();
        dialog.querySelector('button').focus();
        return true;
    }

    return { escapeHtml, formatBytes, safeThumbnailUrl, fileHref, openPreview, closePreview, trapFocus };
});
