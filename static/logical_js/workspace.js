(function(root, factory) {
    const api = factory();
    if (typeof module === 'object' && module.exports) {
        module.exports = api;
    }
    if (root && root.document) {
        if (root.document.readyState === 'loading') {
            root.document.addEventListener('DOMContentLoaded', function() { api.start(root); });
        } else {
            api.start(root);
        }
    }
})(typeof window !== 'undefined' ? window : globalThis, function() {
    const selectableStatuses = ['new', 'already_downloaded', 'already_queued', 'date_unknown'];
    const progressStatuses = ['queued', 'running', 'completed', 'skipped', 'failed', 'missing'];
    const pageSize = 20;

    function canSelect(status) {
        return selectableStatuses.includes(status);
    }

    function selectionForPlan(items, selectedIds) {
        const selected = new Set(selectedIds);
        const allowed = items.filter(function(item) { return selected.has(item.id) && canSelect(item.status); });
        return {
            selected_item_ids: allowed.map(function(item) { return item.id; }),
            include_unknown_dates: allowed.filter(function(item) {
                return item.status === 'date_unknown';
            }).map(function(item) { return item.id; })
        };
    }

    function searchItems(items, query) {
        const normalized = String(query || '').normalize('NFKC').toLocaleLowerCase().trim();
        if (!normalized) {
            return items;
        }
        return items.filter(function(item) {
            return [item.name, item.description, item.title, item.channel, item.filename, item.relative_path]
                .filter(Boolean).join(' ').normalize('NFKC').toLocaleLowerCase().includes(normalized);
        });
    }

    function memberStatus(item) {
        if (item.status === 'missing') {
            return 'missing';
        }
        if (item.file_exists && ['completed', 'file_only', 'skipped'].includes(item.status) &&
            (item.status === 'file_only' || item.source === 'mounted_folder' || item.metadata_status === 'missing')) {
            return 'file_only';
        }
        return item.status;
    }

    function progressSummary(progress) {
        const counts = {};
        progressStatuses.forEach(function(status) {
            const value = Number((progress || {})[status]);
            counts[status] = Number.isFinite(value) ? Math.max(0, Math.floor(value)) : 0;
        });
        const total = progressStatuses.reduce(function(sum, status) { return sum + counts[status]; }, 0);
        const settled = counts.completed + counts.skipped + counts.failed + counts.missing;
        return { counts, total, percent: total ? Math.round(settled / total * 100) : 0 };
    }

    function start(win) {
        const doc = win.document;
        const page = doc.body.dataset.page;
        if (!['collections', 'ai-connect'].includes(page)) {
            return;
        }
        const media = win.YDLNAS_MEDIA_UI;
        const escape = media.escapeHtml;
        const locale = win.YDLNAS_LOCALE || 'en';
        const catalog = win.YDLNAS_I18N || {};
        const collectionId = doc.body.dataset.collectionId || '';
        const renderedContent = new WeakMap();
        const state = {
            collections: [], collection: null, items: [], batches: [], connections: [],
            plan: null, batchLimit: 25, view: 'list', page: 1, query: '',
            previewTimeout: 900000, commitTimeout: 120000,
            loading: false, mutating: 0, initialized: false
        };
        const byId = function(id) { return doc.getElementById(id); };
        const text = function(id, value) {
            const element = byId(id);
            if (element) { element.textContent = value; }
        };
        const hidden = function(id, value) {
            const element = byId(id);
            if (element) { element.hidden = value; }
        };
        function t(key, values) {
            let result = catalog[key] || key;
            Object.keys(values || {}).forEach(function(name) {
                result = result.split('{' + name + '}').join(String(values[name]));
            });
            return result;
        }
        function showMessage(message, tone) {
            const target = byId('workspace-message');
            target.textContent = message;
            target.dataset.tone = tone || 'success';
            target.setAttribute('role', tone === 'error' ? 'alert' : 'status');
            target.hidden = false;
        }
        function report(error) {
            showMessage(error.message || t('workspace.request_failed'), 'error');
        }
        function formatDate(value, dateOnly) {
            if (!value) { return t('common.unknown'); }
            let date;
            if (typeof value === 'number') {
                date = new Date(value < 1000000000000 ? value * 1000 : value);
            } else if (dateOnly && /^\d{4}-?\d{2}-?\d{2}$/.test(value)) {
                const digits = value.replaceAll('-', '');
                date = new Date(Number(digits.slice(0, 4)), Number(digits.slice(4, 6)) - 1, Number(digits.slice(6, 8)));
            } else {
                date = new Date(value);
            }
            if (Number.isNaN(date.getTime())) { return t('common.unknown'); }
            const options = { year: 'numeric', month: 'short', day: 'numeric' };
            if (!dateOnly) { options.hour = '2-digit'; options.minute = '2-digit'; }
            return new Intl.DateTimeFormat(locale, options).format(date);
        }
        function criteriaText(criteria) {
            const from = (criteria || {}).date_from;
            const to = (criteria || {}).date_to;
            if (from && to) { return t('batch.date_range', { from: formatDate(from, true), to: formatDate(to, true) }); }
            if (from) { return t('batch.date_after', { date: formatDate(from, true) }); }
            if (to) { return t('batch.date_before', { date: formatDate(to, true) }); }
            return t('collections.any_date');
        }
        async function request(path, options) {
            const settings = options || {};
            const controller = new AbortController();
            const timer = win.setTimeout(function() { controller.abort(); }, settings.timeout || 20000);
            try {
                const response = await win.fetch('/youtube-dl/api/v1' + path, {
                    method: settings.method || 'GET',
                    headers: settings.body ? { 'Content-Type': 'application/json' } : {},
                    body: settings.body ? JSON.stringify(settings.body) : undefined,
                    credentials: 'same-origin',
                    cache: 'no-store',
                    signal: controller.signal
                });
                if (response.status === 401) {
                    throw new Error(t('workspace.session_expired'));
                }
                if (!response.headers.get('content-type')?.includes('application/json')) {
                    throw new Error(t('workspace.request_failed'));
                }
                const body = await response.json();
                if (!response.ok || body.success === false) {
                    const key = 'server.' + body.code;
                    const message = catalog[key] ? t(key, body.params) :
                        response.status === 403 ? t('workspace.session_expired') :
                        response.status === 404 ? t('workspace.not_found') :
                        response.status === 409 ? t('workspace.conflict') :
                        response.status === 410 ? t('batch.expired') :
                        response.status >= 500 ? t('workspace.server_unavailable') : t('workspace.invalid_request');
                    throw new Error(message);
                }
                return body;
            } catch (error) {
                if (error.name === 'AbortError') { throw new Error(t('workspace.request_timeout')); }
                if (error instanceof TypeError) { throw new Error(t('workspace.network_error')); }
                throw error;
            } finally {
                win.clearTimeout(timer);
            }
        }
        async function runAction(container, action, pendingKey) {
            const controls = container.matches('button') ? [container] :
                Array.from(container.querySelectorAll('button, input, select, textarea'));
            const disabled = controls.map(function(control) { return control.disabled; });
            const pendingButton = pendingKey ? (container.matches('button') ? container : container.querySelector('[type="submit"], .workspace-primary')) : null;
            const originalLabel = pendingButton?.textContent;
            state.mutating++;
            container.setAttribute('aria-busy', 'true');
            controls.forEach(function(control) { control.disabled = true; });
            if (pendingButton) { pendingButton.textContent = t(pendingKey); }
            try {
                await action();
            } catch (error) {
                const dialogError = container.querySelector('[data-dialog-error]');
                if (dialogError) {
                    dialogError.textContent = error.message || t('workspace.request_failed');
                    dialogError.hidden = false;
                } else {
                    report(error);
                }
            } finally {
                state.mutating--;
                container.removeAttribute('aria-busy');
                controls.forEach(function(control, index) { control.disabled = disabled[index]; });
                if (pendingButton) { pendingButton.textContent = originalLabel; }
            }
        }
        function on(id, event, handler) {
            const target = byId(id);
            if (target) { target.addEventListener(event, handler); }
        }
        function replaceContent(id, markup) {
            const target = byId(id);
            if (target && renderedContent.get(target) !== markup) {
                target.innerHTML = markup;
                renderedContent.set(target, markup);
            }
        }
        function statusText(status) {
            const keys = {
                queued: 'activity.queued', running: 'history.status_downloading', completed: 'history.completed',
                file_only: 'history.mounted',
                skipped: 'collections.skipped', failed: 'history.failed', missing: 'history.missing',
                new: 'batch.status_new', already_downloaded: 'batch.status_downloaded',
                already_queued: 'batch.status_queued', invalid: 'batch.status_invalid',
                outside_date_range: 'batch.status_outside', date_unknown: 'batch.status_unknown'
            };
            return t(keys[status] || 'history.unknown');
        }
        function progressMarkup(progress) {
            const summary = progressSummary(progress);
            return '<div class="collection-progress">' + progressStatuses.filter(function(status) {
                return summary.counts[status] > 0;
            }).map(function(status) {
                return `<span data-status="${status}">${escape(statusText(status))} ${summary.counts[status]}</span>`;
            }).join('') + '</div>';
        }
        function emptyMarkup(title, description, action) {
            return `<div class="workspace-empty"><h4>${escape(title)}</h4><p>${escape(description)}</p>${action || ''}</div>`;
        }
        function renderPager(count) {
            const totalPages = Math.max(1, Math.ceil(count / pageSize));
            state.page = Math.min(Math.max(state.page, 1), totalPages);
            if (count <= pageSize) { replaceContent('collection-pager', ''); return; }
            replaceContent('collection-pager', `
                <button class="workspace-button" data-page-number="${state.page - 1}" ${state.page === 1 ? 'disabled' : ''}>${escape(t('history.previous'))}</button>
                <span>${escape(t('history.page_summary', { current: state.page, total: totalPages }))}</span>
                <button class="workspace-button" data-page-number="${state.page + 1}" ${state.page === totalPages ? 'disabled' : ''}>${escape(t('history.next'))}</button>`);
        }
        function renderCollections() {
            const filtered = searchItems(state.collections, state.query);
            renderPager(filtered.length);
            text('collection-result-count', t('collections.count', { count: filtered.length }));
            if (!filtered.length) {
                replaceContent('collection-list', state.query ?
                    emptyMarkup(t('history.no_matches'), t('history.no_matches_hint')) :
                    emptyMarkup(t('collections.empty'), t('collections.empty_hint'),
                        `<a class="workspace-button" href="/youtube-dl/ai-connect">${escape(t('connect.open_setup'))}</a>`));
                return;
            }
            replaceContent('collection-list', filtered.slice((state.page - 1) * pageSize, state.page * pageSize).map(function(collection) {
                const href = '/youtube-dl/collections/' + encodeURIComponent(collection.id);
                return `<article class="collection-row">
                    <div>
                        <h4><a href="${href}">${escape(collection.name)}</a></h4>
                        <p>${escape(collection.description || t('collections.no_description'))}</p>
                        <div class="collection-row-meta">
                            <span>${escape(t('collections.item_count', { count: collection.item_count || 0 }))}</span>
                            <span>${escape(media.formatBytes(collection.total_size_bytes, locale))}</span>
                            <span>${escape(criteriaText(collection.criteria))}</span>
                        </div>
                        ${progressMarkup(collection.progress)}
                    </div>
                    <div class="collection-row-aside">
                        <time class="workspace-help">${escape(formatDate(collection.updated_at))}</time>
                        <a class="workspace-button" href="${href}" aria-label="${escape(t('collections.open_named', { name: collection.name }))}">${escape(t('collections.open'))} <span aria-hidden="true">&rarr;</span></a>
                    </div>
                </article>`;
            }).join(''));
        }
        function itemKey(item) {
            return item.membership_id || item.uuid || item.id;
        }
        function itemActions(item) {
            const key = escape(itemKey(item));
            const preview = item.file_exists && ['video', 'audio'].includes(item.download_type) ?
                `<button type="button" class="workspace-button" data-preview-item="${key}">${escape(t('action.preview'))}</button>` : '';
            const download = item.file_exists && item.uuid ?
                `<a class="workspace-button" href="${media.fileHref(item, false)}" download>${escape(t('action.download'))}</a>` : '';
            return `${preview}${download}<button type="button" class="workspace-button" data-detail-item="${key}">${escape(t('collections.details'))}</button>`;
        }
        function renderMembers() {
            const filtered = searchItems(state.items, state.query);
            renderPager(filtered.length);
            text('collection-result-count', t('collections.item_count', { count: filtered.length }));
            const target = byId('collection-items');
            target.className = state.view === 'grid' ? 'collection-media-grid' : 'collection-media-list';
            if (!filtered.length) {
                replaceContent('collection-items', state.query ?
                    emptyMarkup(t('history.no_matches'), t('history.no_matches_hint')) :
                    emptyMarkup(t('collections.empty_items'), t('collections.empty_items_hint')));
                return;
            }
            replaceContent('collection-items', filtered.slice((state.page - 1) * pageSize, state.page * pageSize).map(function(item) {
                const status = memberStatus(item);
                const title = escape(item.title || item.filename || t('common.untitled'));
                const mounted = item.source === 'mounted_folder' || item.metadata_status === 'missing';
                const channel = mounted ? t('detail.mounted_folder') : (item.channel || t('common.unknown_channel'));
                const profile = item.resolution === 'mounted' ? t('history.mounted') :
                    item.resolution === 'best' ? t('composer.share_best') :
                    item.resolution === 'compatible-mp4' ? t('composer.compatible_mp4_short') : (item.resolution || '');
                const statusClass = status === 'file_only' ? 'status-file' :
                    status === 'completed' || status === 'skipped' ? 'status-completed' :
                    ['failed', 'missing'].includes(status) ? 'status-failed' : 'status-pending';
                const tags = `<span class="status-tag ${statusClass}">${escape(statusText(status))}</span>
                    ${item.file_exists ? `<span class="workspace-help">${escape(media.formatBytes(item.file_size_bytes, locale))}</span>` : ''}`;
                const path = `<span class="collection-media-path">${escape(item.relative_path || item.filename || '')}</span>`;
                if (state.view === 'grid') {
                    const thumbnail = media.safeThumbnailUrl(item.thumbnail_local_url || item.thumbnail);
                    const icons = { audio: 'glyphicon-music', video: 'glyphicon-film', subtitle: 'glyphicon-subtitles' };
                    return `<article class="history-grid-card">
                        <div class="history-grid-media">
                            <span class="history-grid-fallback" aria-hidden="true"><span class="glyphicon ${icons[item.download_type] || 'glyphicon-file'}"></span></span>
                            ${thumbnail ? `<img src="${escape(thumbnail)}" alt="" loading="lazy" referrerpolicy="no-referrer">` : ''}
                        </div>
                        <div class="history-grid-body"><h4>${title}</h4><p>${escape(channel)}</p>
                            ${path}<div class="history-grid-footer"><div class="collection-row-meta">${tags}</div>
                            <div class="workspace-actions">${itemActions(item)}</div></div>
                        </div></article>`;
                }
                return `<article class="history-card">
                    <div class="history-card-main"><div class="history-card-topline">
                        ${item.timestamp ? `<span class="download-date">${escape(formatDate(item.timestamp))}</span>` : ''}${tags}</div>
                        <h4>${title}</h4><p>${escape(channel)}</p>${path}
                    </div>
                    <div class="history-card-footer"><span class="workspace-help">${escape(profile)}</span>
                        <div class="workspace-actions">${itemActions(item)}</div></div>
                </article>`;
            }).join(''));
        }
        function renderBatches() {
            hidden('collection-batches', !state.batches.length);
            replaceContent('collection-batch-list', state.batches.map(function(batch) {
                const summary = progressSummary(batch.progress);
                return `<article class="collection-batch">
                    <div class="workspace-section-heading">
                        <strong>${escape(t('collections.batch_label', { id: String(batch.id).slice(0, 8) }))}</strong>
                        <time class="workspace-help">${escape(formatDate(batch.created_at))}</time>
                    </div>
                    ${batch.criteria ? `<p class="workspace-help">${escape(criteriaText(batch.criteria))}</p>` : ''}
                    ${progressMarkup(batch.progress)}
                    <div class="batch-progress-track" role="progressbar" aria-label="${escape(t('collections.batch_progress'))}"
                        aria-valuenow="${summary.percent}" aria-valuemin="0" aria-valuemax="100">
                        <span style="width:${summary.percent}%"></span>
                    </div>
                </article>`;
            }).join(''));
        }
        function renderCollection() {
            const collection = state.collection;
            text('collections-heading', collection.name);
            text('collections-description', collection.description || t('collections.no_description'));
            text('collection-item-count', collection.item_count || 0);
            text('collection-stored-size', media.formatBytes(collection.total_size_bytes, locale));
            text('collection-updated', formatDate(collection.updated_at));
            text('collection-date-policy', criteriaText(collection.criteria));
            text('collection-folder', '/downfolder/' + (collection.relative_directory || ''));
            text('collection-library-heading', t('collections.media'));
            hidden('collection-summary', false);
            hidden('collection-view-switch', false);
            doc.title = collection.name + ' - youtube-dl NAS';
            if (!state.initialized) {
                byId('collection-edit-name').value = collection.name;
                byId('collection-edit-description').value = collection.description || '';
                byId('batch-name').value = collection.name;
                byId('batch-description').value = collection.description || '';
                byId('batch-date-from').value = collection.criteria?.date_from || '';
                byId('batch-date-to').value = collection.criteria?.date_to || '';
            }
            renderMembers();
            renderBatches();
        }
        function renderConnections() {
            replaceContent('connection-list', state.connections.length ? state.connections.map(function(connection) {
                return `<article class="connection-row" data-revoked="${!!connection.revoked_at}">
                    <div><strong>${escape(connection.name)}</strong>
                        <code>${escape(connection.prefix || '')}</code>
                        <p>${escape(t('connect.created_at', { date: formatDate(connection.created_at) }))}</p>
                        <p>${escape(connection.revoked_at ? t('connect.revoked_at', { date: formatDate(connection.revoked_at) }) :
                            connection.last_used_at ? t('connect.last_used', { date: formatDate(connection.last_used_at) }) : t('connect.never_used'))}</p>
                    </div>
                    ${connection.revoked_at ? `<span class="status-tag status-canceled">${escape(t('connect.revoked'))}</span>` :
                        `<button type="button" class="workspace-button workspace-danger" data-revoke="${escape(connection.id)}" aria-label="${escape(t('connect.revoke_named', { name: connection.name }))}">${escape(t('connect.revoke'))}</button>`}
                </article>`;
            }).join('') : emptyMarkup(t('connect.no_connections'), t('connect.no_connections_hint')));
        }
        async function refresh() {
            if (state.loading) { return; }
            state.loading = true;
            try {
                if (page === 'collections') {
                    const result = await request('/collections' + (collectionId ? '/' + encodeURIComponent(collectionId) : ''));
                    if (collectionId) {
                        state.collection = result.collection;
                        state.items = result.items;
                        state.batches = result.batches;
                        renderCollection();
                    } else {
                        state.collections = result.collections;
                        renderCollections();
                    }
                    hidden('collection-loading', true);
                } else {
                    const result = await request('/connections');
                    state.connections = result.connections;
                    renderConnections();
                    hidden('connections-loading', true);
                }
                state.initialized = true;
                text('connection-status', t('connection.online'));
                byId('connection-status').className = 'connection-chip status-completed';
            } catch (error) {
                text('connection-status', t('connection.offline'));
                byId('connection-status').className = 'connection-chip status-failed';
                hidden('collection-loading', true);
                hidden('connections-loading', true);
                throw error;
            } finally {
                state.loading = false;
            }
        }
        function openDialog(title, markup) {
            const previousFocus = doc.activeElement;
            const dialog = doc.createElement('dialog');
            dialog.className = 'workspace-dialog';
            dialog.setAttribute('aria-labelledby', 'workspace-dialog-title');
            dialog.innerHTML = `<h3 id="workspace-dialog-title">${escape(title)}</h3>${markup}`;
            dialog.addEventListener('keydown', function(event) { media.trapFocus(event, dialog); });
            dialog.addEventListener('close', function() {
                dialog.remove();
                if (previousFocus && doc.contains(previousFocus)) { previousFocus.focus(); }
            }, { once: true });
            doc.body.appendChild(dialog);
            dialog.showModal();
            return dialog;
        }
        function confirmAction(title, message, label, action) {
            const dialog = openDialog(title, `<p id="workspace-dialog-description">${escape(message)}</p>
                <p class="workspace-message" data-tone="error" data-dialog-error role="alert" hidden></p><div class="workspace-actions">
                <button class="workspace-button" type="button" data-cancel>${escape(t('common.cancel'))}</button>
                <button class="workspace-button workspace-danger" type="button" data-confirm>${escape(label)}</button></div>`);
            dialog.setAttribute('aria-describedby', 'workspace-dialog-description');
            dialog.querySelector('[data-cancel]').addEventListener('click', function() { dialog.close(); });
            dialog.querySelector('[data-confirm]').addEventListener('click', function() {
                runAction(dialog, async function() {
                    await action();
                    dialog.close();
                });
            });
            dialog.querySelector('[data-cancel]').focus();
        }
        function showDetails(item) {
            const fields = [
                [t('detail.filename'), item.filename],
                [t('collections.relative_path'), item.relative_path],
                [t('detail.resolution'), item.resolution],
                [t('detail.size'), item.file_exists ? media.formatBytes(item.file_size_bytes, locale) : t('history.missing')],
                [t('detail.source_url'), item.url]
            ];
            const dialog = openDialog(item.title || item.filename || t('common.untitled'),
                `<dl class="detail-list">${fields.map(function(field) {
                    return `<div class="detail-field"><dt>${escape(field[0])}</dt><dd>${escape(field[1] || t('common.unknown'))}</dd></div>`;
                }).join('')}</dl><div class="workspace-actions">
                ${item.uuid ? `<a class="workspace-button" href="/youtube-dl?item=${encodeURIComponent(item.uuid)}">${escape(t('collections.manage_download'))}</a>` : ''}
                <button type="button" class="workspace-button" data-close>${escape(t('common.close'))}</button></div>`);
            dialog.querySelector('[data-close]').addEventListener('click', function() { dialog.close(); });
        }
        async function copy(value) {
            if (win.isSecureContext && win.navigator.clipboard) {
                try {
                    await win.navigator.clipboard.writeText(value);
                } catch (error) {
                    if (error.name === 'NotAllowedError' || error.name === 'SecurityError') {
                        throw new Error(t('workspace.copy_failed'));
                    }
                    throw error;
                }
            } else {
                // Private-LAN HTTP does not expose the Clipboard API.
                const previousFocus = doc.activeElement;
                const input = doc.createElement('textarea');
                input.value = value;
                input.className = 'sr-only';
                doc.body.appendChild(input);
                input.select();
                const copied = doc.execCommand('copy');
                input.remove();
                if (previousFocus) { previousFocus.focus(); }
                if (!copied) { throw new Error(t('workspace.copy_failed')); }
            }
            showMessage(t('workspace.copied'));
        }
        function clearSecret() {
            byId('connection-token').value = '';
            byId('connection-token').type = 'password';
            byId('toggle-token').setAttribute('aria-pressed', 'false');
            text('toggle-token', t('connect.reveal'));
            hidden('connection-secret', true);
        }
        function showBatch(open) {
            hidden('batch-composer', !open);
            byId('open-batch-composer').setAttribute('aria-expanded', String(open));
            if (open) {
                byId(state.plan ? 'batch-commit' : 'batch-name').focus();
            } else {
                byId('open-batch-composer').focus();
            }
        }
        function readPlanSelection() {
            const ids = Array.from(byId('batch-plan-items').querySelectorAll('input:checked')).map(function(input) { return input.value; });
            return selectionForPlan(state.plan.items, ids);
        }
        function updatePlanSelection() {
            const selection = readPlanSelection();
            text('batch-selection-count', t('batch.selected_count', { count: selection.selected_item_ids.length }));
            byId('batch-commit').disabled = !selection.selected_item_ids.length;
        }
        function updateDestinationCaption() {
            const option = byId('batch-destination').selectedOptions[0];
            text('batch-destination-caption', option ? t('batch.selected_destination', { name: option.textContent }) : '');
        }
        function renderPlan() {
            const plan = state.plan;
            text('batch-heading', t('batch.review'));
            text('batch-description-copy', criteriaText(plan.criteria) + ' \u00b7 ' + t('batch.preview_safe'));
            text('batch-plan-expiry', t('batch.expires_at', { date: formatDate(plan.expires_at) }));
            replaceContent('batch-plan-items', plan.items.map(function(item) {
                const selectable = canSelect(item.status);
                const checked = selectable && item.status !== 'date_unknown';
                return `<label class="plan-item" data-status="${escape(item.status)}">
                    <input type="checkbox" value="${escape(item.id)}" ${checked ? 'checked' : ''} ${selectable ? '' : 'disabled'}>
                    <span><strong>${escape(item.title || item.url)}</strong>
                        <small>${escape(item.url)}</small>${item.upload_date ? `<small>${escape(formatDate(item.upload_date, true))}</small>` : ''}
                    </span><span class="plan-item-status">${escape(statusText(item.status))}</span>
                </label>`;
            }).join(''));
            const destination = byId('batch-destination');
            if (collectionId) {
                destination.innerHTML = `<option value="${escape(collectionId)}">${escape(state.collection.name)}</option>`;
            } else {
                const matching = plan.matching_collections || [];
                const matches = new Set(matching.map(function(collection) { return collection.id; }));
                const existing = matching.concat(state.collections.filter(function(collection) { return !matches.has(collection.id); }));
                destination.innerHTML = `<option value="">${escape(t('batch.create_collection', { name: plan.name }))}</option>` +
                    existing.map(function(collection) {
                        const label = matches.has(collection.id) ? t('batch.suggested_collection', { name: collection.name }) : collection.name;
                        return `<option value="${escape(collection.id)}">${escape(label)}</option>`;
                    }).join('');
                if (matching.length) { destination.value = matching[0].id; }
            }
            updateDestinationCaption();
            hidden('batch-form', true);
            hidden('batch-plan', false);
            updatePlanSelection();
            byId('batch-destination').focus();
        }
        on('workspace-refresh', 'click', function(event) {
            runAction(event.currentTarget, refresh);
        });
        if (page === 'collections') {
            on('open-batch-composer', 'click', function() { showBatch(byId('batch-composer').hidden); });
            on('close-batch-composer', 'click', function() { showBatch(false); });
            on('collection-search', 'input', function(event) {
                state.query = event.target.value;
                state.page = 1;
                if (collectionId) { renderMembers(); } else { renderCollections(); }
            });
            on('collection-pager', 'click', function(event) {
                const control = event.target.closest('[data-page-number]');
                if (control && !control.disabled) {
                    state.page = Number(control.dataset.pageNumber);
                    if (collectionId) { renderMembers(); } else { renderCollections(); }
                    byId('collection-library-heading').scrollIntoView({ block: 'start' });
                }
            });
            on('collection-view-switch', 'click', function(event) {
                const control = event.target.closest('[data-collection-view]');
                if (!control) { return; }
                state.view = control.dataset.collectionView;
                byId('collection-view-switch').querySelectorAll('button').forEach(function(button) {
                    const active = button === control;
                    button.classList.toggle('is-active', active);
                    button.setAttribute('aria-pressed', String(active));
                });
                renderMembers();
            });
            on('collection-items', 'click', function(event) {
                const control = event.target.closest('[data-preview-item], [data-detail-item]');
                if (!control) { return; }
                const key = control.dataset.previewItem || control.dataset.detailItem;
                const item = state.items.find(function(member) { return String(itemKey(member)) === key; });
                if (!item) { showMessage(t('workspace.not_found'), 'error'); return; }
                if (control.dataset.previewItem) {
                    if (!media.openPreview(item, t)) { showMessage(t('preview.unavailable'), 'error'); }
                } else { showDetails(item); }
            });
            byId('collection-items').addEventListener('error', function(event) {
                if (event.target.tagName === 'IMG') { event.target.hidden = true; }
            }, true);
            on('collection-edit-form', 'submit', function(event) {
                event.preventDefault();
                const body = { name: byId('collection-edit-name').value.trim(), description: byId('collection-edit-description').value.trim() };
                runAction(event.currentTarget, async function() {
                    await request('/collections/' + encodeURIComponent(collectionId), { method: 'PATCH', body });
                    await refresh();
                    byId('collection-edit').open = false;
                    showMessage(t('collections.saved'));
                }, 'workspace.saving');
            });
            on('remove-collection', 'click', function() {
                confirmAction(t('collections.remove'), t('collections.remove_confirm', { name: state.collection.name }), t('collections.remove'), async function() {
                    await request('/collections/' + encodeURIComponent(collectionId), { method: 'DELETE' });
                    win.location.assign('/youtube-dl/collections');
                });
            });
            on('batch-form', 'submit', function(event) {
                event.preventDefault();
                const candidates = byId('batch-urls').value.split(/\r?\n/).map(function(url) { return url.trim(); }).filter(Boolean);
                if (candidates.length > state.batchLimit) {
                    showMessage(t('batch.too_many', { count: state.batchLimit }), 'error');
                    return;
                }
                const from = byId('batch-date-from').value;
                const to = byId('batch-date-to').value;
                if (from && to && from > to) {
                    showMessage(t('batch.invalid_dates'), 'error');
                    byId('batch-date-to').focus();
                    return;
                }
                const body = {
                    name: byId('batch-name').value.trim(),
                    description: byId('batch-description').value.trim(),
                    criteria: { date_from: from || null, date_to: to || null },
                    resolution: byId('batch-resolution').value,
                    candidates: candidates.map(function(url) { return { url }; })
                };
                runAction(event.currentTarget, async function() {
                    const result = await request('/plans', { method: 'POST', body, timeout: state.previewTimeout });
                    state.plan = result.plan;
                    hidden('workspace-message', true);
                    renderPlan();
                }, 'batch.checking');
            });
            on('batch-start-over', 'click', function() {
                state.plan = null;
                text('batch-heading', t('batch.heading'));
                text('batch-description-copy', t('batch.description'));
                hidden('batch-plan', true);
                hidden('batch-form', false);
                byId('batch-urls').focus();
            });
            on('batch-plan-items', 'change', updatePlanSelection);
            on('batch-destination', 'change', updateDestinationCaption);
            on('batch-commit', 'click', function(event) {
                const selection = readPlanSelection();
                if (!selection.selected_item_ids.length) { return; }
                const destination = byId('batch-destination').value;
                const body = Object.assign({}, selection, destination ? { collection_id: destination } : { create_collection: true });
                runAction(byId('batch-plan'), async function() {
                    const result = await request('/plans/' + encodeURIComponent(state.plan.id) + '/commit', { method: 'POST', body, timeout: state.commitTimeout });
                    const targetId = result.collection?.id || result.batch?.collection_id;
                    if (!targetId) { throw new Error(t('workspace.request_failed')); }
                    win.location.assign('/youtube-dl/collections/' + encodeURIComponent(targetId));
                }, 'batch.committing');
            });
            request('/capabilities').then(function(result) {
                state.batchLimit = result.batch_limit;
                text('batch-limit-hint', t('batch.urls_hint', { count: state.batchLimit }));
                [['preview_timeout_seconds', 'previewTimeout'], ['commit_timeout_seconds', 'commitTimeout']].forEach(function(entry) {
                    const seconds = result[entry[0]];
                    if (seconds === undefined) { return; }
                    if (!Number.isInteger(seconds) || seconds <= 0 || seconds > 3600) {
                        throw new Error(t('workspace.request_failed'));
                    }
                    state[entry[1]] = seconds * 1000;
                });
            }).catch(report);
        } else {
            doc.title = t('connect.heading') + ' - youtube-dl NAS';
            const endpoint = win.location.origin + '/youtube-dl/mcp';
            byId('mcp-endpoint').value = endpoint;
            hidden('connect-http-warning', win.location.protocol === 'https:');
            function renderClient() {
                const setup = win.YDLNAS_MCP_CLIENTS.setup(byId('mcp-client').value, endpoint, t('connect.token'));
                text('client-config', setup.config);
                text('client-config-location', setup.location);
                text('client-config-hint', t(setup.hintKey));
                byId('client-docs').href = setup.docs;
            }
            renderClient();
            on('mcp-client', 'change', renderClient);
            on('connection-form', 'submit', function(event) {
                event.preventDefault();
                const name = byId('connection-name').value.trim();
                runAction(event.currentTarget, async function() {
                    const result = await request('/connections', { method: 'POST', body: { name } });
                    clearSecret();
                    byId('connection-token').value = result.token;
                    hidden('connection-secret', false);
                    byId('connection-name').value = '';
                    byId('copy-token').focus();
                    await refresh();
                    showMessage(t('connect.created'));
                }, 'workspace.saving');
            });
            on('toggle-token', 'click', function(event) {
                const input = byId('connection-token');
                const visible = input.type === 'password';
                input.type = visible ? 'text' : 'password';
                event.currentTarget.setAttribute('aria-pressed', String(visible));
                event.currentTarget.textContent = t(visible ? 'connect.hide' : 'connect.reveal');
            });
            on('dismiss-token', 'click', function() { clearSecret(); byId('mcp-client').focus(); });
            on('copy-token', 'click', function(event) {
                runAction(event.currentTarget, function() { return copy(byId('connection-token').value); });
            });
            on('copy-endpoint', 'click', function(event) {
                runAction(event.currentTarget, function() { return copy(endpoint); });
            });
            on('copy-client-config', 'click', function(event) {
                runAction(event.currentTarget, function() { return copy(byId('client-config').textContent); });
            });
            on('copy-prompt', 'click', function(event) {
                runAction(event.currentTarget, function() { return copy(byId('research-prompt').textContent); });
            });
            on('connection-list', 'click', function(event) {
                const control = event.target.closest('[data-revoke]');
                if (!control) { return; }
                const connection = state.connections.find(function(item) { return item.id === control.dataset.revoke; });
                confirmAction(t('connect.revoke'), t('connect.revoke_confirm', { name: connection.name }), t('connect.revoke'), async function() {
                    await request('/connections/' + encodeURIComponent(connection.id), { method: 'DELETE' });
                    clearSecret();
                    await refresh();
                    showMessage(t('connect.revoked'));
                });
            });
            win.addEventListener('pagehide', clearSecret);
            const healthController = new AbortController();
            const healthTimer = win.setTimeout(function() { healthController.abort(); }, 10000);
            win.fetch('/youtube-dl/mcp/health', { credentials: 'omit', cache: 'no-store', signal: healthController.signal }).then(function(response) {
                if (!response.ok) { throw new Error('mcp_unavailable'); }
                return response.json();
            }).then(function(body) {
                if (body.status !== 'ok') { throw new Error('mcp_unavailable'); }
                text('mcp-service-status', t('connect.ready'));
                byId('mcp-service-status').className = 'connection-chip status-completed';
            }).catch(function() {
                text('mcp-service-status', t('connect.unavailable'));
                byId('mcp-service-status').className = 'connection-chip status-failed';
            }).finally(function() {
                win.clearTimeout(healthTimer);
            });
        }
        refresh().catch(report);
        let poll;
        function startPolling() {
            win.clearInterval(poll);
            poll = win.setInterval(function() {
                if (doc.visibilityState === 'visible' && !state.mutating) { refresh().catch(report); }
            }, page === 'collections' ? 5000 : 15000);
        }
        startPolling();
        doc.addEventListener('visibilitychange', function() {
            if (doc.visibilityState === 'visible' && !state.mutating) { refresh().catch(report); }
        });
        win.addEventListener('pagehide', function() { win.clearInterval(poll); });
        win.addEventListener('pageshow', function(event) {
            if (event.persisted) {
                startPolling();
                refresh().catch(report);
            }
        });
    }

    return { canSelect, selectionForPlan, searchItems, memberStatus, progressSummary, start };
});
