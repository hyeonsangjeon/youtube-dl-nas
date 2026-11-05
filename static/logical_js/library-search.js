(function(root, factory) {
    const api = factory();
    if (typeof module === 'object' && module.exports) module.exports = api;
    if (root) root.YDLNAS_LIBRARY_SEARCH = api;
})(typeof window !== 'undefined' ? window : globalThis, function() {
    function timeLabel(value) {
        const number = Number(value);
        const seconds = Number.isFinite(number) ? Math.max(0, Math.floor(number)) : 0;
        const minutes = Math.floor(seconds / 60);
        return (minutes >= 60 ? Math.floor(minutes / 60) + ':' + String(minutes % 60).padStart(2, '0') : minutes) + ':' + String(seconds % 60).padStart(2, '0');
    }

    function mount(options) {
        const t = options.translate;
        const mediaUI = window.YDLNAS_MEDIA_UI;
        const esc = mediaUI.escapeHtml;
        const panel = document.getElementById('subtitle-search-results');
        const scope = document.getElementById('history-search-scope');
        const input = document.getElementById('history-search');
        const filePlaceholder = input.placeholder;
        let controller = null;
        let pageCursors = [null];
        let pageIndex = 0;
        let nextCursor = null;
        let results = [];
        let currentQuery = '';
        let relatedId = null;
        let relatedFiles = [];

        async function request(path, signal) {
            const response = await fetch('/youtube-dl/api/v1/library' + path, {
                credentials: 'same-origin', cache: 'no-store', signal: signal
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.code || 'search_failed');
            return result;
        }

        function message(key) {
            panel.innerHTML = `<p class="search-state" role="status">${esc(t(key))}</p>`;
        }

        function render(result) {
            results = result.items;
            nextCursor = result.next_cursor;
            const rows = results.map(function(entry, index) {
                const item = entry.media || entry.subtitle;
                const date = entry.subtitle.timestamp;
                const timestamp = date && !isNaN(Date.parse(date)) ? new Intl.DateTimeFormat(window.YDLNAS_LOCALE || 'en', { dateStyle: 'medium' }).format(new Date(date)) : t('common.unknown');
                return `<article class="subtitle-result">
                    <div class="subtitle-result-heading">
                        <span class="glyphicon glyphicon-subtitles" aria-hidden="true"></span>
                        <h3><button type="button" data-result-detail="${index}">${esc(item.title || item.filename)}</button></h3>
                        <span class="subtitle-result-date">${esc(t(entry.subtitle.timestamp_kind === 'modified' ? 'search.modified' : 'detail.downloaded'))} ${esc(timestamp)}</span>
                    </div>
                    ${entry.matches.map(function(cue, cueIndex) {
                        return `<div class="subtitle-match">
                            ${entry.media ? `<button type="button" class="subtitle-time" data-result="${index}" data-cue="${cueIndex}" title="${esc(t('search.play_at', { time: timeLabel(cue.start) }))}" aria-label="${esc(t('search.play_at', { time: timeLabel(cue.start) }))}"><span class="glyphicon glyphicon-play" aria-hidden="true"></span>${timeLabel(cue.start)}</button>` : `<span class="subtitle-time">${timeLabel(cue.start)}</span>`}
                            <p>${esc(cue.text)}</p>
                        </div>`;
                    }).join('')}
                    <div class="subtitle-result-footer"><span>${esc(entry.subtitle.filename)}</span>
                        <button type="button" class="btn btn-default btn-sm" data-transcript="${esc(entry.subtitle.uuid)}">${esc(t('search.read'))}</button>
                    </div>
                </article>`;
            }).join('');
            panel.innerHTML = `<div class="subtitle-search-summary" role="status">${esc(t('search.scanned', { count: result.scanned_through, total: result.subtitle_files }))}</div>
                ${(result.skipped || result.truncated_files) ? `<p class="search-warning" role="status">${esc(t('search.skipped', { skipped: result.skipped, truncated: result.truncated_files }))}</p>` : ''}
                ${rows || `<p class="search-state">${esc(t(result.has_more ? 'search.no_matches_page' : result.subtitle_files ? 'history.no_matches' : 'search.no_subtitles'))}</p>`}
                <nav class="subtitle-search-pager" aria-label="${esc(t('history.pages_label'))}">
                    <button type="button" class="btn btn-default" data-search-page="previous" ${pageIndex ? '' : 'disabled'}>${esc(t('history.previous'))}</button>
                    <span>${pageIndex + 1}</span>
                    <button type="button" class="btn btn-default" data-search-page="next" ${result.has_more ? '' : 'disabled'}>${esc(t('history.next'))}</button>
                </nav>`;
        }

        async function search(keepPage) {
            if (controller) controller.abort();
            const query = input.value.trim();
            if (!keepPage || query !== currentQuery) {
                pageCursors = [null];
                pageIndex = 0;
                currentQuery = query;
            }
            if (!query) { panel.removeAttribute('aria-busy'); message('search.empty'); return; }
            const current = new AbortController();
            controller = current;
            panel.setAttribute('aria-busy', 'true');
            message('search.loading');
            try {
                const params = new URLSearchParams({ q: query, limit: '20' });
                if (pageCursors[pageIndex]) params.set('cursor', pageCursors[pageIndex]);
                const result = await request('/search?' + params, current.signal);
                if (!current.signal.aborted) render(result);
            } catch (error) {
                if (error.name !== 'AbortError') message(error.message === 'search_changed' ? 'search.changed' : 'search.failed');
            } finally {
                if (controller === current) panel.removeAttribute('aria-busy');
            }
        }

        async function transcript(id) {
            const previousFocus = document.activeElement;
            const dialog = document.createElement('dialog');
            const abort = new AbortController();
            let offset = 0;
            dialog.className = 'transcript-dialog';
            dialog.setAttribute('aria-labelledby', 'transcript-title');
            dialog.innerHTML = `<header><h2 id="transcript-title">${esc(t('search.read'))}</h2><button type="button" class="action-btn transcript-close" aria-label="${esc(t('preview.close'))}"><span class="glyphicon glyphicon-remove" aria-hidden="true"></span></button></header><div class="transcript-cues"></div><p class="transcript-state" role="status"></p><button type="button" class="btn btn-default transcript-more">${esc(t('search.more'))}</button>`;
            const content = dialog.querySelector('.transcript-cues');
            const status = dialog.querySelector('.transcript-state');
            const more = dialog.querySelector('.transcript-more');
            async function load() {
                more.disabled = true;
                status.textContent = t('search.loading');
                try {
                    const result = await request('/' + encodeURIComponent(id) + '/transcript?offset=' + offset, abort.signal);
                    dialog.querySelector('h2').textContent = result.subtitle.title || result.subtitle.filename;
                    content.insertAdjacentHTML('beforeend', result.cues.map(function(cue) {
                        return `<div class="subtitle-match"><span class="subtitle-time">${timeLabel(cue.start)}</span><p>${esc(cue.text)}</p></div>`;
                    }).join(''));
                    offset = result.next_offset;
                    more.hidden = offset === null;
                    status.textContent = result.truncated ? t('search.transcript_limited') : result.cues.length ? '' : t('search.no_text');
                } catch (error) {
                    if (error.name !== 'AbortError') status.textContent = t('search.failed');
                } finally { more.disabled = false; }
            }
            dialog.querySelector('.transcript-close').addEventListener('click', function() { dialog.close(); });
            dialog.addEventListener('click', function(event) { if (event.target === dialog) dialog.close(); });
            dialog.addEventListener('close', function() {
                abort.abort();
                dialog.remove();
                if (previousFocus && document.contains(previousFocus)) previousFocus.focus();
            }, { once: true });
            more.addEventListener('click', load);
            document.body.appendChild(dialog);
            dialog.showModal();
            dialog.querySelector('.transcript-close').focus();
            load();
        }

        async function related(id) {
            relatedId = id;
            relatedFiles = [];
            const element = document.getElementById('related-files');
            if (!element) return;
            element.innerHTML = `<p role="status">${esc(t('search.loading'))}</p>`;
            try {
                const result = await request('/' + encodeURIComponent(id) + '/files');
                if (relatedId !== id || !document.contains(element)) return;
                relatedFiles = result.files;
                element.innerHTML = result.files.length > 1 ? `<h3>${esc(t('search.related'))}</h3><ul>${result.files.map(function(file, index) {
                    return `<li><span>${esc(file.filename)}</span>${file.file_exists ? `<button type="button" class="action-btn" data-related-file="${index}" title="${esc(t(file.download_type === 'subtitle' ? 'search.read' : 'action.preview'))}" aria-label="${esc(t(file.download_type === 'subtitle' ? 'search.read' : 'action.preview'))}"><span class="glyphicon ${file.download_type === 'subtitle' ? 'glyphicon-align-left' : 'glyphicon-play'}" aria-hidden="true"></span></button><a class="action-btn" href="${esc(mediaUI.fileHref(file, false))}" download title="${esc(t('action.download'))}"><span class="glyphicon glyphicon-download-alt" aria-hidden="true"></span></a>` : ''}</li>`;
                }).join('')}</ul>` : '';
            } catch (_) { if (document.contains(element)) element.innerHTML = `<p role="status">${esc(t('search.failed'))}</p>`; }
        }

        scope.addEventListener('change', function() {
            if (controller) controller.abort();
            const active = scope.value === 'subtitles';
            panel.hidden = !active;
            document.querySelector('.download-history').classList.toggle('subtitle-search-active', active);
            input.placeholder = active ? t('search.placeholder') : filePlaceholder;
            input.setAttribute('aria-label', input.placeholder);
            options.closeDetail();
            if (active) search();
            else options.searchFiles();
        });
        document.addEventListener('click', function(event) {
            const read = event.target.closest('[data-transcript], .action-transcript');
            if (read) {
                event.preventDefault(); event.stopPropagation();
                transcript(read.dataset.transcript || read.dataset.uuid); return;
            }
            const file = event.target.closest('[data-related-file]');
            if (file) {
                const item = relatedFiles[Number(file.dataset.relatedFile)];
                if (item) item.download_type === 'subtitle' ? transcript(item.uuid) : options.preview(item);
                return;
            }
            const detail = event.target.closest('[data-result-detail], [data-library-item]');
            if (detail) {
                event.preventDefault(); event.stopPropagation();
                const entry = results[Number(detail.dataset.resultDetail)];
                options.detail(detail.dataset.libraryItem || (entry.media || entry.subtitle).uuid);
                return;
            }
            const cue = event.target.closest('[data-result][data-cue]');
            if (cue) {
                const entry = results[Number(cue.dataset.result)];
                options.preview(entry.media, entry.matches[Number(cue.dataset.cue)].start); return;
            }
            const page = event.target.closest('[data-search-page]');
            if (page && !page.disabled) {
                if (page.dataset.searchPage === 'next') { pageCursors[++pageIndex] = nextCursor; }
                else pageIndex = Math.max(0, pageIndex - 1);
                search(true);
            }
        });
        return { active: function() { return scope.value === 'subtitles'; }, search: search, related: related };
    }
    return { timeLabel, mount };
});
