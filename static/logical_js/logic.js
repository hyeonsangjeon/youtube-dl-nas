/**
 * @fileOverview Client-side logic for a YouTube download web application.
 * This file manages the WebSocket connection and reconnection logic, state restoration and saving via localStorage,
 * dynamic UI updates for download history, progress display, and user notifications.
 *
 * @global {boolean} thdYn - Flag indicating if the history has been restored or a download has been completed.
 * @global {WebSocket|null} wsEventBus - WebSocket connection instance used for communication.
 * @global {string} currentVideoTitle - Title of the current video being processed.
 * @global {string} currentChannel - Channel name of the video currently in download.
 * @global {string|null} sessionId - Session identifier, if applicable.
 * @global {number} reconnectAttempts - Number of current WebSocket reconnection attempts.
 * @global {number} maxReconnectAttempts - Maximum allowed WebSocket reconnection attempts.
 * @global {number} reconnectDelay - Delay duration (in milliseconds) between reconnection attempts.
 *
 * @function connectWebSocket
 * @description Initializes the WebSocket connection to the server. Reuses an existing open connection if available,
 *              otherwise creates a new connection. On connection, requests download history and resets reconnection parameters.
 *
 * @function attemptReconnect
 * @description Attempts to reconnect to the WebSocket server using an exponential backoff strategy, stopping after a maximum number of attempts.
 *
 * @function saveLocalState
 * @description Saves the current download history and the timestamp of the last update into localStorage.
 *
 * @function restoreLocalState
 * @description Restores the download history from localStorage if the saved state is less than 24 hours old and updates the UI.
 *
 * @function getDownloadHistory
 * @description Extracts download history entries from the DOM and returns them as an array of history objects.
 *
 * @function restoreDownloadHistory
 * @description Populates the UI download history table with previously saved history items. Generates a unique UUID if one is not provided.
 *
 * @function generateUuid
 * @description Generates a unique identifier (UUID) using a pseudo-random number algorithm.
 * @returns {string} A generated UUID string.
 *
 * @function addHistoryItem
 * @description Creates a UUID and calls addHistoryItemWithUuid to insert a new history item into the UI.
 *
 * @function addHistoryItemWithUuid
 * @description Adds a new download history item to the UI with proper escaping and download URL generation.
 * @param {string} resolution - The resolution tag used for the download.
 * @param {string} channel - The name of the YouTube channel.
 * @param {string} title - The title of the video.
 * @param {string} uuid - Unique identifier for the history item.
 * @param {string} [filepath] - Optional file path of the downloaded file.
 * @param {string} [filename] - Optional name of the downloaded file.
 *
 * @function updateProgress
 * @description Updates the progress bar and text in the UI. Resets the UI when progress reaches 100%.
 * @param {number} percentage - The current download progress percentage.
 *
 * @function addMessage
 * @description Displays a notification message on the UI with an appropriate alert style. Supports auto-hiding after a timeout.
 * @param {string} message - The message content to be displayed.
 * @param {string} [type='info'] - The type of alert (e.g., 'info', 'warning', 'success', 'error').
 * @param {boolean} [autoHide=true] - Flag to determine if the message should disappear automatically.
 * @returns {string} The unique identifier for the created message element.
 *
 * @function clearMessages
 * @description Removes all
 *
 * @function messagesTxt
 * @description Processes incoming messages, determines the message type, and updates the UI accordingly.
 *              It handles various types such as history restoration, download progress, and UI updates for the title,
 *              channel, and thumbnail.
 * @param {string} msg - The raw message string received via the WebSocket.
 *
 * @function getResolutionClass
 * @description Determines a CSS class for the resolution tag based on the provided resolution string.
 * @param {string} resolution - The resolution string (e.g., '1080p', '720p', 'audio').
 * @returns {string} A CSS class name corresponding to the resolution.
 *
 * @function showConfirmModal
 * @description Renders a modal dialog to confirm critical actions like deletion or clearing of history.
 * @param {string} title - The title of the confirm modal.
 * @param {string} message - The message body for the confirm modal.
 * @param {Function} onConfirm - Callback function to execute if the user confirms the action.
 *
 * @function clearAllHistory
 * @description Sends an AJAX request to clear all download history from the server and updates the UI accordingly.
 *
 * @function deleteHistoryItem
 * @description Sends an AJAX request to delete a specific download history item using its UUID and refreshes the UI afterward.
 * @param {string} uuid - The unique identifier for the history item to be deleted.
 *
 * @event DOMContentLoaded
 * @description The initialization function that is executed once the document is ready. It sets up event handlers,
 *              restores local state, initializes the WebSocket connection, and binds click events for sending download
 *              requests, refreshing history, and deleting history items.
 */

var thdYn = false;
var wsEventBus = null;
var currentVideoTitle = '';
var currentChannel = '';
var sessionId = null;
var reconnectAttempts = 0;
var maxReconnectAttempts = 5;
var reconnectDelay = 1000; // 1second

function translate(key, values) {
    const catalog = window.YDLNAS_I18N || {};
    let text = catalog[key] || key;
    Object.keys(values || {}).forEach(function(name) {
        text = text.split('{' + name + '}').join(String(values[name]));
    });
    return text;
}

function appLocale() {
    return window.YDLNAS_LOCALE || 'en';
}

function localizeSubtitleLanguageOptions() {
    const select = document.getElementById('selSubtitleLanguage');
    if (!select || typeof Intl === 'undefined' || typeof Intl.DisplayNames !== 'function') {
        return;
    }

    let displayNames;
    try {
        displayNames = new Intl.DisplayNames([appLocale()], { type: 'language' });
    } catch (error) {
        return;
    }

    Array.prototype.forEach.call(select.options, function(option) {
        if (option.value === 'en-orig') {
            option.textContent = translate('composer.english_original');
            return;
        }
        try {
            option.textContent = displayNames.of(option.value) || option.textContent;
        } catch (error) {
            // Keep the bundled English label for uncommon extractor language codes.
        }
    });
}
//---------------------------------------------------------------------------------------------------//
$(document).ready(function() {
    if (!$('body').hasClass('dashboard-page')) {
        return;
    }

    // resolution/subtitle format selection event
    $('#selResolution').on('change', function() {
        const selectedValue = $(this).val();
        const subtitleContainer = $('#subtitleLanguageContainer');
        
        console.log('Resolution changed to:', selectedValue);
        
        // Display language selection box when selecting SRT or VTT
        if (selectedValue === 'srt' || selectedValue === 'vtt') {
            subtitleContainer.show();
            console.log('Showing subtitle language selector');
        } else {
            subtitleContainer.hide();
            console.log('Hiding subtitle language selector');
        }
    });
    
    // Set initial state
    const initialValue = $('#selResolution').val();
    if (initialValue === 'srt' || initialValue === 'vtt') {
        $('#subtitleLanguageContainer').show();
    }
    localizeSubtitleLanguageOptions();
});
//---------------------------------------------------------------------------------------------------//

$(function () {
    if (!$('body').hasClass('dashboard-page')) {
        return;
    }

    let historyRestoreCount = 0;
    let isHistoryRestoring = false;
    let maxMessages = 5;
    let historyItems = [];
    let historyPrefs = loadHistoryPrefs();
    let selectedHistoryUuid = null;
    let historyOverviewOpen = false;
    let activeDownload = null;
    let queueCount = 0;
    let queueItems = [];
    let statusPollTimer = null;
    let historyFetchInFlight = false;
    let pendingHistoryRefresh = false;
    let dashboardRefreshTimer = null;
    let hasOpenedWebSocket = false;
    let lastPlaylistKind = 'single';
    const historyPageSize = 20;
    const historyDrawerMedia = '(max-width: 1180px)';
    let currentHistoryPage = 1;
    const emptyColspan = 7;

    console.log("Document ready - initializing...");

    const pageParams = new URLSearchParams(window.location.search);
    const sharedStatus = pageParams.get('shared');
    if (sharedStatus === 'queued') {
        addMessage(translate('message.shared_queued'), 'success');
    } else if (sharedStatus === 'duplicate') {
        addMessage(translate('message.shared_duplicate'), 'warning');
    } else if (sharedStatus === 'review') {
        addMessage(translate('message.shared_review'), 'info');
    } else if (sharedStatus === 'missing') {
        addMessage(translate('message.shared_missing'), 'warning');
    } else if (sharedStatus === 'invalid') {
        addMessage(translate('message.shared_invalid'), 'error');
    } else if (sharedStatus === 'storage') {
        addMessage(translate('server.storage_critical'), 'error');
    }
    if (window.YDLNAS_SHARED_URL) {
        $('#url').val(window.YDLNAS_SHARED_URL);
    }
    if (sharedStatus && window.history.replaceState) {
        pageParams.delete('shared');
        const cleanQuery = pageParams.toString();
        window.history.replaceState({}, document.title, window.location.pathname + (cleanQuery ? '?' + cleanQuery : ''));
    }

    function connectWebSocket() {
        if (wsEventBus && wsEventBus.readyState === WebSocket.OPEN) {
            console.log("WebSocket already connected, skipping...");
            return;
        }

        if (wsEventBus) {
            wsEventBus.close();
            wsEventBus = null;
        }

        try {
            wsEventBus = new WebSocket(window.location.protocol.replace('http','ws')+'//'+window.location.host+'/websocket');
            console.log("WebSocket connecting to: " + window.location.host);

            wsEventBus.onopen = function(evt) {
                console.log("WebSocket opened");
                const isReconnect = hasOpenedWebSocket;
                hasOpenedWebSocket = true;
                reconnectAttempts = 0;
                reconnectDelay = 1000;
                updateConnectionStatus(translate('connection.online'), 'completed');
                messagesTxt("[MSG], WebSocket connection opened.");
                fetchStatus();

                if (isReconnect) {
                    scheduleDashboardRefresh(50);
                }

                setTimeout(() => {
                    if (!isReconnect && wsEventBus && wsEventBus.readyState === WebSocket.OPEN) {
                        console.log("Requesting history...");
                        wsEventBus.send('[REQUEST_HISTORY]');
                    }
                }, 100);
            }

            wsEventBus.onmessage = function(evt) {
                console.log("WebSocket message received: " + evt.data);
                thdYn = true;
                messagesTxt(evt.data);
            }

            wsEventBus.onclose = function(evt) {
                console.log("WebSocket closed, attempting to reconnect...");
                wsEventBus = null;
                updateConnectionStatus(translate('connection.reconnecting'), 'pending');
                messagesTxt("[MSG], Connection lost. Reconnecting...");
                attemptReconnect();
            }

            wsEventBus.onerror = function(evt) {
                console.log("WebSocket error: ", evt);
                updateConnectionStatus(translate('connection.error'), 'failed');
                messagesTxt("[MSG], Connection error occurred.");
            }
        } catch (error) {
            console.error("WebSocket connection failed:", error);
            wsEventBus = null;
            updateConnectionStatus(translate('connection.offline'), 'failed');
            attemptReconnect();
        }
    }

    function attemptReconnect() {
        if (reconnectAttempts >= maxReconnectAttempts) {
            updateConnectionStatus(translate('connection.offline'), 'failed');
            messagesTxt("[MSG], Failed to reconnect. Please refresh the page.");
            return;
        }

        reconnectAttempts++;

        setTimeout(() => {
            console.log(`Reconnection attempt ${reconnectAttempts}/${maxReconnectAttempts}`);
            connectWebSocket();
        }, reconnectDelay);

        reconnectDelay = Math.min(reconnectDelay * 1.5, 10000);
    }

    function classifyPlaylistUrl(value) {
        let parsed;
        try {
            parsed = new URL(String(value || '').trim());
        } catch (error) {
            return 'single';
        }

        const host = parsed.hostname.toLowerCase();
        const path = parsed.pathname.toLowerCase().replace(/\/$/, '');
        if (host.indexOf('youtube.com') >= 0 || host === 'youtu.be') {
            const hasVideo = Boolean(parsed.searchParams.get('v')) || host === 'youtu.be' || path.indexOf('/shorts/') === 0;
            if (parsed.searchParams.get('list')) {
                return hasVideo ? 'video_playlist' : 'playlist';
            }
            if (path === '/playlist') {
                return 'playlist';
            }
            if (/^\/(channel|c|user)\//.test(path) || path.indexOf('/@') === 0) {
                return 'channel';
            }
        }
        if (['playlist', 'album', 'set'].some((key) => parsed.searchParams.get(key))) {
            return 'playlist';
        }
        if (/(^|\/)(playlist|playlists|channel|channels)(\/|$)/.test(path)) {
            return 'playlist';
        }
        return 'single';
    }

    function updatePlaylistGuard() {
        const kind = classifyPlaylistUrl($('#url').val());
        const scopeField = $('#playlist-scope-field');
        const badge = $('#playlist-guard-badge');
        const select = $('#playlist-mode');
        const needsScope = kind !== 'single';
        const bulkOnly = kind === 'playlist' || kind === 'channel';

        scopeField.prop('hidden', !needsScope);
        badge.prop('hidden', !needsScope);
        select.find('option[value="single"]').prop('disabled', bulkOnly);
        if (!needsScope) {
            select.val('single');
        } else if (kind !== lastPlaylistKind) {
            select.val(kind === 'video_playlist' ? 'single' : '');
        }
        if (needsScope) {
            $('#download-options').prop('open', true);
        }
        lastPlaylistKind = kind;
        return kind;
    }

    function loadPreferences() {
        $.ajax({
            method: 'GET',
            url: '/youtube-dl/preferences',
            dataType: 'json',
            success: function(response) {
                if (response && response.success) {
                    $('#share-default-profile').val(response.share_profile || 'best');
                }
            }
        });
    }

    function saveShareProfile(profile) {
        $.ajax({
            method: 'POST',
            url: '/youtube-dl/preferences',
            data: JSON.stringify({ share_profile: profile }),
            dataType: 'json',
            contentType: 'application/json',
            success: function(response) {
                if (response && response.success) {
                    addMessage(translate('message.share_profile_saved'), 'success');
                } else {
                    addMessage(getResponseMessage(response, translate('message.preference_failed')), 'error');
                }
            },
            error: function(jqXHR) {
                addMessage(getAjaxErrorMessage(jqXHR, translate('message.preference_failed')), 'error');
            }
        });
    }

    function loadHistoryPrefs() {
        const defaults = {
            sort: 'date-desc',
            status: 'all',
            type: 'all',
            search: '',
            view: 'list'
        };

        try {
            const savedPrefs = localStorage.getItem('historyPrefs');
            const prefs = savedPrefs ? Object.assign(defaults, JSON.parse(savedPrefs)) : defaults;
            prefs.view = prefs.view === 'grid' ? 'grid' : 'list';
            return prefs;
        } catch (error) {
            console.error("Failed to load history prefs:", error);
            return defaults;
        }
    }

    function saveHistoryPrefs() {
        localStorage.setItem('historyPrefs', JSON.stringify(historyPrefs));
    }

    function resetHistoryPaging() {
        currentHistoryPage = 1;
    }

    function applyHistorySearch() {
        historyPrefs.search = $('#history-search').val();
        resetHistoryPaging();
        saveHistoryPrefs();
        renderHistory();
    }

    function applyHistoryPrefsToControls() {
        $('#history-search').val(historyPrefs.search);
        $('#history-sort').val(historyPrefs.sort);
        $('#history-status-filter').val(historyPrefs.status);
        $('.history-type-option').removeClass('is-active').attr('aria-pressed', 'false');
        $(`.history-type-option[data-history-type="${historyPrefs.type}"]`).addClass('is-active').attr('aria-pressed', 'true');
        $('.history-view-btn').removeClass('is-active').attr('aria-pressed', 'false');
        $(`.history-view-btn[data-history-view="${historyPrefs.view}"]`).addClass('is-active').attr('aria-pressed', 'true');
        $('.download-history').toggleClass('history-view-grid', historyPrefs.view === 'grid');
    }

    function updateConnectionStatus(label, state) {
        const chip = $('#connection-status');
        chip.text(label);
        chip.removeClass('status-completed status-failed status-pending');
        chip.addClass(state === 'completed' ? 'status-completed' : state === 'failed' ? 'status-failed' : 'status-pending');
    }

    function saveLocalState() {
        const state = {
            downloadHistory: getDownloadHistory(),
            lastUpdate: Date.now()
        };
        localStorage.setItem('downloadState', JSON.stringify(state));
    }

    function restoreLocalState() {
        try {
            const savedState = localStorage.getItem('downloadState');
            if (savedState) {
                const state = JSON.parse(savedState);

                if (Date.now() - state.lastUpdate < 24 * 60 * 60 * 1000) {
                    restoreDownloadHistory(state.downloadHistory);
                }
            }
        } catch (error) {
            console.error("Failed to restore local state:", error);
        }
    }

    function getDownloadHistory() {
        return historyItems.slice();
    }

    function restoreDownloadHistory(history) {
        historyItems = (history || []).map(normalizeHistoryItem);
        renderHistory();
        if (historyItems.length > 0) {
            $(".table-responsive").show();
            thdYn = true;
        }
    }

    function generateUuid() {
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
            var r = Math.random() * 16 | 0, v = c == 'x' ? r : (r & 0x3 | 0x8);
            return v.toString(16);
        });
    }

    function normalizeHistoryItem(item) {
        const normalized = Object.assign({
            uuid: generateUuid(),
            timestamp: '',
            url: '',
            resolution: '',
            channel: '',
            title: '',
            thumbnail: '',
            thumbnail_file: '',
            thumbnail_file_exists: false,
            thumbnail_local_url: '',
            duration_seconds: 0,
            status: 'unknown',
            failure_code: '',
            filepath: '',
            filename: '',
            file_exists: false,
            file_size_bytes: 0,
            download_type: '',
            progress: 0,
            source: 'history',
            metadata_status: ''
        }, item || {});

        if (!normalized.uuid) {
            normalized.uuid = generateUuid();
        }
        if (!normalized.download_type) {
            normalized.download_type = getHistoryType(normalized.resolution);
        }
        if (!normalized.source) {
            normalized.source = 'history';
        }
        if (!normalized.metadata_status) {
            normalized.metadata_status = normalized.source === 'mounted_folder' || normalized.status === 'file_only' ? 'missing' : 'saved';
        }
        if (!normalized.status) {
            normalized.status = 'unknown';
        }
        return normalized;
    }

    function upsertHistoryItem(item, append) {
        const normalized = normalizeHistoryItem(item);
        const index = historyItems.findIndex((historyItem) => historyItem.uuid === normalized.uuid);

        if (index >= 0) {
            historyItems[index] = normalized;
        } else if (append) {
            historyItems.push(normalized);
        } else {
            historyItems.unshift(normalized);
        }
    }

    function removeHistoryItem(uuid) {
        historyItems = historyItems.filter((item) => item.uuid !== uuid);
    }

    function renderHistory() {
        const filteredItems = getFilteredHistoryItems();
        const totalPages = getHistoryTotalPages(filteredItems.length);
        currentHistoryPage = clampHistoryPage(currentHistoryPage, totalPages);
        const startIndex = (currentHistoryPage - 1) * historyPageSize;
        const endIndex = startIndex + historyPageSize;
        const visibleItems = filteredItems.slice(startIndex, endIndex);
        const body = $("#completeInfo");
        const cards = $("#history-card-list");
        const grid = $("#history-grid");
        const pager = $("#history-pager");
        const rangeStart = filteredItems.length > 0 ? startIndex + 1 : 0;
        const rangeEnd = Math.min(endIndex, filteredItems.length);
        const resultLabel = filteredItems.length === historyItems.length ?
            translate('history.result_all', { start: rangeStart, end: rangeEnd, total: historyItems.length }) :
            translate('history.result_matching', { start: rangeStart, end: rangeEnd, total: filteredItems.length });
        $('#history-result-count').text(resultLabel);

        if (historyItems.length === 0) {
            body.html(`<tr><td colspan="${emptyColspan}" class="empty-state">${escapeHtml(translate('history.no_files'))}<br><small>${escapeHtml(translate('history.no_files_hint'))}</small></td></tr>`);
            cards.html(renderEmptyCard(translate('history.no_files'), translate('history.no_files_hint')));
            grid.html(renderEmptyCard(translate('history.no_files'), translate('history.no_files_hint')));
            pager.empty();
            renderDetailDrawer(null);
            return;
        }

        if (filteredItems.length === 0) {
            body.html(`<tr><td colspan="${emptyColspan}" class="empty-state">${escapeHtml(translate('history.no_matches'))}<br><small>${escapeHtml(translate('history.no_matches_hint'))}</small></td></tr>`);
            cards.html(renderEmptyCard(translate('history.no_matches'), translate('history.no_matches_hint')));
            grid.html(renderEmptyCard(translate('history.no_matches'), translate('history.no_matches_hint')));
            pager.empty();
            if (!historyItems.some((item) => item.uuid === selectedHistoryUuid)) {
                renderDetailDrawer(null);
            }
            $(".table-responsive").show();
            return;
        }

        body.html(visibleItems.map(renderHistoryRow).join(''));
        cards.html(visibleItems.map(renderHistoryCard).join(''));
        grid.html(visibleItems.map(renderHistoryGridCard).join(''));
        bindHistoryGridImages();
        renderHistoryPager(filteredItems.length, totalPages);
        $(".table-responsive").show();
        if (selectedHistoryUuid) {
            const selected = visibleItems.find((item) => item.uuid === selectedHistoryUuid);
            if (!selected) {
                selectedHistoryUuid = null;
            }
            renderDetailDrawer(selected || null);
        } else {
            renderDetailDrawer(null);
        }
    }

    function getHistoryTotalPages(totalCount) {
        return Math.max(1, Math.ceil(totalCount / historyPageSize));
    }

    function clampHistoryPage(page, totalPages) {
        const pageNumber = Number(page) || 1;
        return Math.min(Math.max(pageNumber, 1), totalPages);
    }

    function getHistoryPageItems(totalPages) {
        if (totalPages <= 7) {
            return Array.from({ length: totalPages }, function(_, index) {
                return index + 1;
            });
        }

        const pages = [1];
        const startPage = Math.max(2, currentHistoryPage - 1);
        const endPage = Math.min(totalPages - 1, currentHistoryPage + 1);

        if (startPage > 2) {
            pages.push('ellipsis-start');
        }

        for (let page = startPage; page <= endPage; page++) {
            pages.push(page);
        }

        if (endPage < totalPages - 1) {
            pages.push('ellipsis-end');
        }

        pages.push(totalPages);
        return pages;
    }

    function renderHistoryPager(totalCount, totalPages) {
        const pager = $("#history-pager");
        if (totalCount <= historyPageSize) {
            pager.empty();
            return;
        }

        const pageItems = getHistoryPageItems(totalPages).map(function(page) {
            if (typeof page === 'string') {
                return '<span class="history-page-ellipsis" aria-hidden="true">...</span>';
            }

            const activeClass = page === currentHistoryPage ? 'is-active' : '';
            const currentAttr = page === currentHistoryPage ? ' aria-current="page"' : '';
            return `
                <button type="button" class="history-page-btn ${activeClass}" data-page="${page}"${currentAttr}>
                    ${page}
                </button>
            `;
        }).join('');

        pager.html(`
            <button type="button" class="history-page-nav" data-page="${currentHistoryPage - 1}" ${currentHistoryPage === 1 ? 'disabled' : ''}>${escapeHtml(translate('history.previous'))}</button>
            <div class="history-page-list" aria-label="${escapeAttr(translate('history.pages_label'))}">
                ${pageItems}
            </div>
            <button type="button" class="history-page-nav" data-page="${currentHistoryPage + 1}" ${currentHistoryPage === totalPages ? 'disabled' : ''}>${escapeHtml(translate('history.next'))}</button>
            <span class="history-page-summary">${escapeHtml(translate('history.page_summary', { current: currentHistoryPage, total: totalPages }))}</span>
        `);
    }

    function getFilteredHistoryItems() {
        const searchText = (historyPrefs.search || '').toLowerCase().trim();
        const filtered = historyItems.filter((item) => {
            const failedStatuses = ['failed', 'error', 'canceled'];
            const statusMatches = historyPrefs.status === 'all'
                || item.status === historyPrefs.status
                || (historyPrefs.status === 'failed' && failedStatuses.indexOf(item.status) >= 0);
            const typeMatches = historyPrefs.type === 'all' || item.download_type === historyPrefs.type;
            const searchTarget = `${item.title || ''} ${item.channel || ''} ${item.filename || ''} ${getMetadataStatusText(item)}`.toLowerCase();
            const searchMatches = !searchText || searchTarget.indexOf(searchText) >= 0;
            return statusMatches && typeMatches && searchMatches;
        });

        return filtered.sort((a, b) => {
            if (historyPrefs.sort === 'date-asc') {
                return getTimestampValue(a.timestamp) - getTimestampValue(b.timestamp);
            }
            if (historyPrefs.sort === 'title-asc') {
                return (a.title || '').localeCompare(b.title || '');
            }
            if (historyPrefs.sort === 'title-desc') {
                return (b.title || '').localeCompare(a.title || '');
            }
            if (historyPrefs.sort === 'channel-asc') {
                return (a.channel || '').localeCompare(b.channel || '');
            }
            if (historyPrefs.sort === 'channel-desc') {
                return (b.channel || '').localeCompare(a.channel || '');
            }
            if (historyPrefs.sort === 'quality-asc') {
                return (a.resolution || '').localeCompare(b.resolution || '');
            }
            if (historyPrefs.sort === 'quality-desc') {
                return (b.resolution || '').localeCompare(a.resolution || '');
            }
            if (historyPrefs.sort === 'status-asc') {
                return (a.status || '').localeCompare(b.status || '');
            }
            if (historyPrefs.sort === 'status-desc') {
                return (b.status || '').localeCompare(a.status || '');
            }
            return getTimestampValue(b.timestamp) - getTimestampValue(a.timestamp);
        });
    }

    function renderHistoryRow(item) {
        const safeUuid = escapeAttr(item.uuid);
        const safeTitle = escapeAttr(item.title || translate('common.untitled'));
        const safeChannel = escapeAttr(item.channel || translate('common.unknown'));
        const safeTimestamp = escapeAttr(item.timestamp || '');
        const titleText = escapeHtml(item.title || translate('common.untitled'));
        const channelText = escapeHtml(item.channel || translate('common.unknown'));
        const resolutionText = escapeHtml(getResolutionText(item.resolution));
        const typeText = escapeHtml(getDownloadTypeText(item.download_type || getHistoryType(item.resolution)));
        const dateText = formatTimestamp(item.timestamp);
        const statusText = escapeHtml(getStatusText(item.status));
        const sizeText = formatFileSize(item);
        const canDownload = item.file_exists && item.uuid;
        const titleElement = canDownload ?
            `<a href="${getDownloadHref(item)}" download class="video-title" title="${safeTitle}">${titleText}</a>` :
            `<span class="video-title" title="${safeTitle}">${titleText}</span>`;
        const metadataLine = renderMetadataLine(item);
        const selectedClass = item.uuid === selectedHistoryUuid ? 'is-selected' : '';

        return `
            <tr class="history-row ${selectedClass}" data-uuid="${safeUuid}" tabindex="0">
                <td><span class="download-date" title="${safeTimestamp}">${dateText}</span></td>
                <td>
                    <span class="type-tag type-${escapeAttr(item.download_type)}">${typeText}</span>
                    <span class="resolution-tag ${getResolutionClass(item.resolution)}">${resolutionText}</span>
                </td>
                <td><span class="channel-name" title="${safeChannel}">${channelText}</span></td>
                <td><div class="title-stack">${titleElement}${metadataLine}</div></td>
                <td><span class="status-tag ${getStatusClass(item.status)}">${statusText}</span></td>
                <td><span class="file-size ${item.file_exists ? '' : 'file-missing'}">${sizeText}</span></td>
                <td class="actions-cell">${renderActionButtons(item, 'row')}</td>
            </tr>
        `;
    }

    function renderHistoryCard(item) {
        const safeUuid = escapeAttr(item.uuid);
        const titleText = escapeHtml(item.title || translate('common.untitled'));
        const channelText = escapeHtml(item.channel || translate('common.unknown'));
        const resolutionText = escapeHtml(getResolutionText(item.resolution));
        const typeText = escapeHtml(getDownloadTypeText(item.download_type || getHistoryType(item.resolution)));
        const statusText = escapeHtml(getStatusText(item.status));
        const metadataSourceLine = renderMetadataSourceLine(item);
        const resolutionBadge = item.resolution === 'mounted' ? '' :
            `<span class="resolution-tag ${getResolutionClass(item.resolution)}">${resolutionText}</span>`;
        const selectedClass = item.uuid === selectedHistoryUuid ? 'is-selected' : '';

        return `
            <article class="history-card ${selectedClass}" data-uuid="${safeUuid}" tabindex="0">
                <div class="history-card-main">
                    <div class="history-card-topline">
                        <span class="download-date">${formatTimestamp(item.timestamp)}</span>
                        <span class="status-tag ${getStatusClass(item.status)}">${statusText}</span>
                    </div>
                    <h3>${titleText}</h3>
                    <p>${channelText}</p>
                    ${metadataSourceLine}
                </div>
                <div class="history-card-footer">
                    <div class="history-card-tags">
                        <span class="type-tag type-${escapeAttr(item.download_type)}">${typeText}</span>
                        ${resolutionBadge}
                        ${renderMetadataBadge(item)}
                        <span class="file-size ${item.file_exists ? '' : 'file-missing'}">${formatFileSize(item)}</span>
                    </div>
                    <div class="history-card-actions">${renderActionButtons(item, 'card')}</div>
                </div>
            </article>
        `;
    }

    function renderHistoryGridCard(item) {
        const safeUuid = escapeAttr(item.uuid);
        const titleText = escapeHtml(item.title || item.filename || translate('common.untitled'));
        const channelText = escapeHtml(item.channel || (isMountedFile(item) ? translate('detail.mounted_folder') : translate('common.unknown')));
        const typeText = escapeHtml(getDownloadTypeText(item.download_type || getHistoryType(item.resolution)));
        const thumbnailUrl = getSafeThumbnailUrl(item.thumbnail_local_url || item.thumbnail);
        const selectedClass = item.uuid === selectedHistoryUuid ? 'is-selected' : '';
        const durationText = formatDuration(item.duration_seconds);
        const visual = `
            <span class="history-grid-fallback" aria-hidden="true">
                <span class="glyphicon ${getMediaPlaceholderIcon(item.download_type)}"></span>
            </span>
            ${thumbnailUrl ? `<img src="${escapeAttr(thumbnailUrl)}" alt="" loading="lazy" referrerpolicy="no-referrer">` : ''}
        `;
        const durationBadge = durationText ? `<span class="history-grid-duration">${durationText}</span>` : '';
        const resolutionBadge = item.resolution === 'mounted' ? '' :
            `<span class="resolution-tag ${getResolutionClass(item.resolution)}">${escapeHtml(getResolutionText(item.resolution))}</span>`;

        return `
            <article class="history-grid-card ${selectedClass}" data-uuid="${safeUuid}" tabindex="0">
                <div class="history-grid-media ${thumbnailUrl ? '' : 'history-grid-placeholder'}">
                    ${visual}
                    ${durationBadge}
                    <span class="history-grid-type type-${escapeAttr(item.download_type)}">${typeText}</span>
                </div>
                <div class="history-grid-body">
                    <h3 title="${escapeAttr(item.title || item.filename || translate('common.untitled'))}">${titleText}</h3>
                    <p title="${escapeAttr(item.channel || '')}">${channelText}</p>
                    <div class="history-grid-meta">
                        <span>${formatTimestamp(item.timestamp)}</span>
                        <span>${formatFileSize(item)}</span>
                    </div>
                    <div class="history-grid-footer">
                        <div class="history-grid-badges">
                            ${resolutionBadge}
                            ${renderMetadataBadge(item)}
                        </div>
                        <div class="history-grid-actions">${renderActionButtons(item, 'grid')}</div>
                    </div>
                </div>
            </article>
        `;
    }

    function getSafeThumbnailUrl(value) {
        const thumbnail = String(value || '').trim();
        return /^https?:\/\//i.test(thumbnail) || /^\/static\/thumbnail\//.test(thumbnail) ? thumbnail : '';
    }

    function bindHistoryGridImages() {
        $('#history-grid .history-grid-media img')
            .off('.historyGrid')
            .on('load.historyGrid', function() {
                $(this).show().closest('.history-grid-media').removeClass('history-grid-placeholder');
            })
            .on('error.historyGrid', function() {
                $(this).hide().closest('.history-grid-media').addClass('history-grid-placeholder');
            })
            .each(function() {
                if (this.complete) {
                    $(this).trigger(this.naturalWidth > 0 ? 'load.historyGrid' : 'error.historyGrid');
                }
            });
    }

    function getMediaPlaceholderIcon(type) {
        if (type === 'audio') {
            return 'glyphicon-music';
        }
        if (type === 'subtitle') {
            return 'glyphicon-subtitles';
        }
        if (type === 'video') {
            return 'glyphicon-film';
        }
        return 'glyphicon-file';
    }

    function formatDuration(value) {
        const totalSeconds = Math.max(0, Math.floor(Number(value) || 0));
        if (!totalSeconds) {
            return '';
        }
        const hours = Math.floor(totalSeconds / 3600);
        const minutes = Math.floor((totalSeconds % 3600) / 60);
        const seconds = totalSeconds % 60;
        return hours > 0 ?
            `${hours}:${pad2(minutes)}:${pad2(seconds)}` :
            `${minutes}:${pad2(seconds)}`;
    }

    function renderEmptyCard(title, message) {
        return `
            <div class="history-empty-card">
                <span class="glyphicon glyphicon-inbox" aria-hidden="true"></span>
                <strong>${escapeHtml(title)}</strong>
                <p>${escapeHtml(message)}</p>
            </div>
        `;
    }

    function getDownloadHref(item) {
        return `/static/downfolder/${encodeURIComponent(item.uuid)}`;
    }

    function getPreviewHref(item) {
        return `/static/preview/${encodeURIComponent(item.uuid)}`;
    }

    function isMountedFile(item) {
        return item.source === 'mounted_folder' || item.metadata_status === 'missing' || item.status === 'file_only';
    }

    function getMetadataStatusText(item) {
        return isMountedFile(item) ? translate('history.no_metadata') : translate('history.saved_metadata');
    }

    function renderMetadataBadge(item) {
        if (!isMountedFile(item)) {
            return '';
        }

        return `<span class="metadata-badge metadata-missing">${escapeHtml(translate('history.no_metadata'))}</span>`;
    }

    function renderMetadataLine(item) {
        if (!isMountedFile(item)) {
            return '';
        }

        return `
            <div class="history-meta-line">
                ${renderMetadataBadge(item)}
                <span>${escapeHtml(translate('history.scanned_from'))}</span>
            </div>
        `;
    }

    function renderMetadataSourceLine(item) {
        if (!isMountedFile(item)) {
            return '';
        }

        return `<div class="history-meta-line history-card-meta-line"><span>${escapeHtml(translate('history.scanned_from'))}</span></div>`;
    }

    function renderFailureGuidance(item) {
        if (!item || (item.status !== 'failed' && item.status !== 'error')) {
            return '';
        }
        const supportedCodes = [
            'storage_full', 'storage_permission', 'auth_required', 'rate_limited',
            'format_unavailable', 'unsupported_url', 'network', 'postprocessing',
            'extractor', 'source_blocked', 'unknown'
        ];
        const code = supportedCodes.indexOf(item.failure_code) >= 0 ? item.failure_code : 'unknown';
        return `
            <div class="failure-guidance">
                <span class="glyphicon glyphicon-exclamation-sign" aria-hidden="true"></span>
                <div>
                    <strong>${escapeHtml(translate(`failure.${code}.reason`))}</strong>
                    <p>${escapeHtml(translate(`failure.${code}.action`))}</p>
                </div>
            </div>
        `;
    }

    function renderActionButtons(item, context) {
        const safeUuid = escapeAttr(item.uuid);
        const isDetail = context === 'detail';
        const mountedFile = isMountedFile(item);
        const canRetry = !mountedFile && item.url && item.resolution && (item.status === 'failed' || item.status === 'error' || item.status === 'canceled');
        const canPreview = item.file_exists && (item.download_type === 'video' || item.download_type === 'audio');
        const canAnalyzeSubtitle = item.file_exists && item.download_type === 'subtitle';
        const previewButton = canPreview ? `
            <button class="action-btn action-preview" data-uuid="${safeUuid}" title="${escapeAttr(translate('action.preview_title'))}">
                <span class="glyphicon glyphicon-play"></span>${isDetail ? `<span>${escapeHtml(translate('action.preview'))}</span>` : ''}
            </button>` : '';
        const subtitleQaButton = canAnalyzeSubtitle ? `
            <button class="action-btn action-subtitle-qa" data-uuid="${safeUuid}" title="${escapeAttr(translate('action.subtitle_qa_title'))}">
                <span class="glyphicon glyphicon-check"></span>${isDetail ? `<span>${escapeHtml(translate('action.subtitle_qa'))}</span>` : ''}
            </button>` : '';
        const downloadButton = item.file_exists ? `
            <a class="action-btn action-download" href="${getDownloadHref(item)}" download title="${escapeAttr(translate('action.download_title'))}">
                <span class="glyphicon glyphicon-download-alt"></span>${isDetail ? `<span>${escapeHtml(translate('action.download'))}</span>` : ''}
            </a>` : '';
        const fileDeleteTitle = mountedFile ? translate('action.delete_mounted_title') : translate('action.delete_file_title');
        const retryButton = canRetry ? `
            <button class="action-btn action-retry" data-uuid="${safeUuid}" title="${escapeAttr(translate('action.retry_title'))}">
                <span class="glyphicon glyphicon-repeat"></span>${isDetail ? `<span>${escapeHtml(translate('action.retry'))}</span>` : ''}
            </button>` : '';
        const fileDeleteButton = item.file_exists ? `
            <button class="action-btn action-file-delete" data-uuid="${safeUuid}" title="${escapeAttr(fileDeleteTitle)}">
                <span class="glyphicon glyphicon-remove"></span>${isDetail ? `<span>${escapeHtml(translate('action.delete_file'))}</span>` : ''}
            </button>` : '';
        const historyDeleteButton = !mountedFile ? `
                <button class="action-btn action-history-delete" data-uuid="${safeUuid}" title="${escapeAttr(translate('action.delete_history_title'))}">
                    <span class="glyphicon glyphicon-trash"></span>${isDetail ? `<span>${escapeHtml(translate('action.delete_history'))}</span>` : ''}
                </button>` : '';
        const detailClass = context === 'detail' ? ' detail-action-group' : '';

        return `
            <div class="action-group${detailClass}">
                ${previewButton}
                ${subtitleQaButton}
                ${downloadButton}
                ${retryButton}
                ${historyDeleteButton}
                ${fileDeleteButton}
            </div>
        `;
    }

    function selectHistoryItem(uuid) {
        selectedHistoryUuid = uuid;
        historyOverviewOpen = true;
        renderHistory();
        if (isCompactHistoryDrawer()) {
            focusHistoryDrawerControl('#close-detail');
        }
    }

    function isCompactHistoryDrawer() {
        return !!(window.matchMedia && window.matchMedia(historyDrawerMedia).matches);
    }

    function focusHistoryDrawerControl(selector) {
        window.requestAnimationFrame(function() {
            const control = document.querySelector(selector);
            if (control) {
                control.focus();
            }
        });
    }

    function syncHistoryDrawerChrome(hasItem) {
        const compact = isCompactHistoryDrawer();
        const visible = hasItem || !compact || historyOverviewOpen;
        const drawer = $('#history-detail-drawer');
        drawer.toggleClass('detail-has-item', hasItem);
        drawer.toggleClass('detail-is-overview', !hasItem);
        drawer.toggleClass('detail-overview-open', !hasItem && compact && historyOverviewOpen);
        drawer.attr('role', compact ? 'dialog' : 'complementary');
        if (compact) {
            drawer.attr('aria-modal', 'true');
        } else {
            drawer.removeAttr('aria-modal');
        }
        $('#history-detail-backdrop').prop('hidden', !(compact && visible));
        $('#history-insights-toggle').attr('aria-expanded', compact && visible ? 'true' : 'false');
        $('body').toggleClass('history-drawer-open', compact && visible);
    }

    function formatInsightCount(value) {
        const count = Math.max(0, Number(value) || 0);
        try {
            return new Intl.NumberFormat(appLocale(), { maximumFractionDigits: 0 }).format(count);
        } catch (error) {
            return String(count);
        }
    }

    function formatInsightDay(timestamp) {
        const date = new Date(timestamp);
        try {
            return new Intl.DateTimeFormat(appLocale(), { month: 'short', day: 'numeric' }).format(date);
        } catch (error) {
            return `${date.getMonth() + 1}/${date.getDate()}`;
        }
    }

    function getHistoryInsights() {
        const helper = window.YDLNAS_HISTORY_INSIGHTS;
        if (helper && typeof helper.aggregate === 'function') {
            return helper.aggregate(historyItems, new Date());
        }
        return {
            storedFiles: 0,
            storedBytes: 0,
            recentCompleted: 0,
            failedJobs: 0,
            completed14: 0,
            activityDays: [],
            typeTotals: {},
            failureReasons: []
        };
    }

    function renderInsightActivity(insights) {
        const days = insights.activityDays || [];
        const maxCount = Math.max.apply(null, [1].concat(days.map(function(day) { return day.count; })));
        const bars = days.map(function(day) {
            const height = day.count > 0 ? Math.max(8, Math.round((day.count / maxCount) * 100)) : 0;
            const date = formatInsightDay(day.timestamp);
            const tooltip = translate('history.insights_day_tooltip', {
                date: date,
                count: formatInsightCount(day.count)
            });
            return `
                <span class="insights-day" title="${escapeAttr(tooltip)}">
                    <span class="insights-day-count">${day.count > 0 ? formatInsightCount(day.count) : ''}</span>
                    <span class="insights-bar-track">
                        <span class="insights-bar-value" style="height: ${height}%"></span>
                    </span>
                </span>
            `;
        }).join('');
        const first = days.length ? formatInsightDay(days[0].timestamp) : '';
        const middle = days.length ? formatInsightDay(days[Math.floor(days.length / 2)].timestamp) : '';
        const last = days.length ? formatInsightDay(days[days.length - 1].timestamp) : '';

        return `
            <section class="insights-section" aria-labelledby="insights-activity-heading">
                <div class="insights-section-heading">
                    <h3 id="insights-activity-heading">${escapeHtml(translate('history.insights_activity_title'))}</h3>
                    <span>${escapeHtml(translate('history.insights_activity_summary', { count: formatInsightCount(insights.completed14) }))}</span>
                </div>
                <div class="insights-chart" role="img" aria-label="${escapeAttr(translate('history.insights_activity_label', { count: formatInsightCount(insights.completed14) }))}">
                    <div class="insights-chart-bars" aria-hidden="true">${bars}</div>
                    <div class="insights-chart-axis" aria-hidden="true">
                        <span>${escapeHtml(first)}</span>
                        <span>${escapeHtml(middle)}</span>
                        <span>${escapeHtml(last)}</span>
                    </div>
                </div>
            </section>
        `;
    }

    function renderInsightTypes(insights) {
        const totals = insights.typeTotals || {};
        const types = ['video', 'audio', 'subtitle'];
        if (totals.file && totals.file.count > 0) {
            types.push('file');
        }
        const denominator = insights.storedBytes > 0 ? insights.storedBytes : Math.max(1, insights.storedFiles);
        const icons = {
            video: 'glyphicon-facetime-video',
            audio: 'glyphicon-music',
            subtitle: 'glyphicon-subtitles',
            file: 'glyphicon-file'
        };
        const rows = types.map(function(type) {
            const total = totals[type] || { count: 0, bytes: 0 };
            const shareValue = insights.storedBytes > 0 ? total.bytes : total.count;
            const width = total.count > 0 ? Math.max(3, Math.round((shareValue / denominator) * 100)) : 0;
            const label = getDownloadTypeText(type);
            const summary = translate('history.insights_type_summary', {
                count: formatInsightCount(total.count),
                size: formatBytes(total.bytes)
            });
            return `
                <button type="button" class="insights-type-row insights-filter" data-history-type="${type}"
                        title="${escapeAttr(translate('history.insights_filter_title', { label: label }))}">
                    <span class="insights-type-copy">
                        <span class="insights-type-label">
                            <span class="glyphicon ${icons[type]}" aria-hidden="true"></span>
                            <strong>${escapeHtml(label)}</strong>
                        </span>
                        <small>${escapeHtml(summary)}</small>
                    </span>
                    <span class="insights-type-track" aria-hidden="true">
                        <span class="insights-type-value insights-type-${type}" style="width: ${width}%"></span>
                    </span>
                </button>
            `;
        }).join('');

        return `
            <section class="insights-section" aria-labelledby="insights-types-heading">
                <div class="insights-section-heading">
                    <h3 id="insights-types-heading">${escapeHtml(translate('history.insights_library_title'))}</h3>
                </div>
                <div class="insights-type-list">${rows}</div>
            </section>
        `;
    }

    function renderInsightFailures(insights) {
        const reasons = insights.failureReasons || [];
        if (!reasons.length) {
            return '';
        }
        const rows = reasons.map(function(reason) {
            const label = reason.code === 'canceled' ?
                translate('history.canceled') :
                translate(`failure.${reason.code}.reason`);
            return `
                <li>
                    <span>${escapeHtml(label)}</span>
                    <strong>${formatInsightCount(reason.count)}</strong>
                </li>
            `;
        }).join('');

        return `
            <section class="insights-section insights-failures" aria-labelledby="insights-failures-heading">
                <div class="insights-section-heading">
                    <h3 id="insights-failures-heading">${escapeHtml(translate('history.insights_failures_title'))}</h3>
                    <button type="button" class="insights-section-filter insights-filter" data-history-status="failed"
                            title="${escapeAttr(translate('history.insights_filter_failures'))}" aria-label="${escapeAttr(translate('history.insights_filter_failures'))}">
                        <span class="glyphicon glyphicon-filter" aria-hidden="true"></span>
                    </button>
                </div>
                <ul>${rows}</ul>
            </section>
        `;
    }

    function renderHistoryInsights() {
        const insights = getHistoryInsights();
        return `
            <article class="insights-panel">
                <button type="button" id="close-insights" class="detail-close insights-close" title="${escapeAttr(translate('history.insights_close'))}" aria-label="${escapeAttr(translate('history.insights_close'))}">
                    <span class="glyphicon glyphicon-remove" aria-hidden="true"></span>
                </button>
                <header class="insights-heading">
                    <span class="insights-scope"><span class="glyphicon glyphicon-stats" aria-hidden="true"></span>${escapeHtml(translate('history.insights_scope'))}</span>
                    <h2>${escapeHtml(translate('history.insights_title'))}</h2>
                    <p>${escapeHtml(translate('history.insights_description'))}</p>
                </header>
                <div class="insights-metrics" role="list">
                    <div role="listitem"><span>${escapeHtml(translate('history.insights_stored_files'))}</span><strong>${formatInsightCount(insights.storedFiles)}</strong></div>
                    <div role="listitem"><span>${escapeHtml(translate('history.insights_total_size'))}</span><strong>${escapeHtml(formatBytes(insights.storedBytes))}</strong></div>
                    <div role="listitem"><span>${escapeHtml(translate('history.insights_last_7_days'))}</span><strong>${formatInsightCount(insights.recentCompleted)}</strong></div>
                    <div role="listitem"><span>${escapeHtml(translate('history.insights_failed_jobs'))}</span><strong>${formatInsightCount(insights.failedJobs)}</strong></div>
                </div>
                ${renderInsightActivity(insights)}
                ${renderInsightTypes(insights)}
                ${renderInsightFailures(insights)}
                <p class="insights-note"><span class="glyphicon glyphicon-info-sign" aria-hidden="true"></span>${escapeHtml(translate('history.insights_note'))}</p>
            </article>
        `;
    }

    function renderDetailDrawer(item) {
        const drawer = $('#history-detail-drawer');
        if (!item) {
            drawer.html(renderHistoryInsights());
            syncHistoryDrawerChrome(false);
            return;
        }

        const typeText = escapeHtml(getDownloadTypeText(item.download_type || getHistoryType(item.resolution)));
        const statusText = escapeHtml(getStatusText(item.status));
        const url = item.url || '';
        const urlHtml = url ?
            `<a href="${escapeAttr(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(url)}</a>` :
            `<span class="muted">${escapeHtml(translate('detail.no_url'))}</span>`;
        const mountedFile = isMountedFile(item);
        const sourceText = mountedFile ? translate('detail.mounted_folder') : translate('detail.download_history');
        const metadataText = getMetadataStatusText(item);
        const metadataNotice = mountedFile ? `
            <div class="metadata-notice">
                <span class="glyphicon glyphicon-info-sign" aria-hidden="true"></span>
                <div>
                    <strong>${escapeHtml(translate('detail.no_metadata_heading'))}</strong>
                    <p>${escapeHtml(translate('detail.no_metadata_description'))}</p>
                </div>
            </div>
        ` : '';
        const failureGuidance = renderFailureGuidance(item);

        drawer.html(`
            <article class="detail-panel ${mountedFile ? 'detail-panel-mounted' : ''}" data-uuid="${escapeAttr(item.uuid)}">
                <button type="button" id="close-detail" class="detail-close" title="${escapeAttr(translate('history.insights_back'))}" aria-label="${escapeAttr(translate('history.insights_back'))}">
                    <span class="glyphicon glyphicon-arrow-left" aria-hidden="true"></span>
                </button>
                <div class="detail-heading">
                    <div>
                        <span class="type-tag type-${escapeAttr(item.download_type)}">${typeText}</span>
                        <span class="status-tag ${getStatusClass(item.status)}">${statusText}</span>
                    </div>
                    <h2 title="${escapeAttr(item.title || translate('common.untitled'))}">${escapeHtml(item.title || translate('common.untitled'))}</h2>
                    <p>${escapeHtml(item.channel || translate('common.unknown_channel'))}</p>
                </div>
                ${metadataNotice}
                ${failureGuidance}
                <dl class="detail-list">
                    ${renderDetailField(translate('detail.downloaded'), formatTimestamp(item.timestamp), 'downloaded')}
                    ${renderDetailField(translate('detail.duration'), formatDuration(item.duration_seconds) || translate('common.unknown'), 'duration')}
                    ${renderDetailField(translate('detail.resolution'), getResolutionText(item.resolution), 'resolution')}
                    ${renderDetailField(translate('detail.size'), formatFileSize(item), 'size')}
                    ${renderDetailField(translate('detail.filename'), item.filename || translate('detail.no_file'), 'filename')}
                    ${item.thumbnail_file_exists ? renderDetailField(translate('detail.thumbnail_file'), item.thumbnail_file, 'thumbnail-file') : ''}
                    ${renderDetailField(translate('detail.source'), sourceText, 'source')}
                    ${renderDetailField(translate('detail.metadata'), metadataText, 'metadata')}
                    ${renderDetailField(translate('detail.uuid'), item.uuid || '', 'uuid')}
                </dl>
                <div class="detail-url ${url ? '' : 'detail-url-empty'}">
                    <span>${escapeHtml(translate('detail.source_url'))}</span>
                    ${urlHtml}
                </div>
                <div class="detail-actions">${renderActionButtons(item, 'detail')}</div>
            </article>
        `);
        syncHistoryDrawerChrome(true);
    }

    function renderDetailField(label, value, key) {
        const fieldClass = key ? ` detail-field-${escapeAttr(key)}` : '';
        return `
            <div class="detail-field${fieldClass}">
                <dt>${escapeHtml(label)}</dt>
                <dd>${escapeHtml(value)}</dd>
            </div>
        `;
    }

    function dismissHistoryDrawer(restoreFocus) {
        selectedHistoryUuid = null;
        historyOverviewOpen = false;
        renderHistory();
        if (restoreFocus && isCompactHistoryDrawer()) {
            focusHistoryDrawerControl('#history-insights-toggle');
        }
    }

    function trapHistoryDrawerFocus(event) {
        const drawer = document.getElementById('history-detail-drawer');
        if (!drawer) {
            return;
        }
        const focusable = Array.prototype.filter.call(
            drawer.querySelectorAll('a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'),
            function(element) { return element.offsetParent !== null; }
        );
        if (!focusable.length) {
            return;
        }
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        const focusOutside = !drawer.contains(document.activeElement);
        if (event.shiftKey && (document.activeElement === first || focusOutside)) {
            event.preventDefault();
            last.focus();
        } else if (!event.shiftKey && (document.activeElement === last || focusOutside)) {
            event.preventDefault();
            first.focus();
        }
    }

    function applyInsightsFilter(type, status) {
        historyPrefs.type = type || 'all';
        historyPrefs.status = status || 'all';
        historyPrefs.search = '';
        selectedHistoryUuid = null;
        historyOverviewOpen = false;
        resetHistoryPaging();
        applyHistoryPrefsToControls();
        saveHistoryPrefs();
        renderHistory();
        if (isCompactHistoryDrawer()) {
            focusHistoryDrawerControl('#history-search');
        }
    }

    function getTimestampValue(timestamp) {
        const value = Date.parse(timestamp || '');
        return isNaN(value) ? 0 : value;
    }

    function formatTimestamp(timestamp) {
        if (!timestamp) {
            return translate('common.unknown');
        }

        const date = new Date(timestamp);
        if (isNaN(date.getTime())) {
            return timestamp;
        }

        try {
            return new Intl.DateTimeFormat(appLocale(), {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit'
            }).format(date);
        } catch (error) {
            return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())} ${pad2(date.getHours())}:${pad2(date.getMinutes())}`;
        }
    }

    function pad2(value) {
        return String(value).padStart(2, '0');
    }

    function formatBytes(sizeValue) {
        const size = Number(sizeValue || 0);
        if (!Number.isFinite(size) || size <= 0) {
            return '0 B';
        }

        const units = ['B', 'KB', 'MB', 'GB', 'TB'];
        let value = size;
        let unitIndex = 0;
        while (value >= 1024 && unitIndex < units.length - 1) {
            value = value / 1024;
            unitIndex++;
        }

        const precision = value >= 10 || unitIndex === 0 ? 0 : 1;
        let formattedValue = value.toFixed(precision);
        try {
            formattedValue = new Intl.NumberFormat(appLocale(), {
                minimumFractionDigits: precision,
                maximumFractionDigits: precision
            }).format(value);
        } catch (error) {
            // Keep the stable numeric fallback above.
        }
        return `${formattedValue} ${units[unitIndex]}`;
    }

    function formatFileSize(item) {
        if (!item.file_exists) {
            return item.filename ? translate('history.missing') : '-';
        }
        return formatBytes(item.file_size_bytes);
    }

    function getHistoryType(resolution) {
        resolution = resolution || '';
        if (resolution === 'mounted') {
            return 'file';
        }
        if (resolution.indexOf('audio') === 0) {
            return 'audio';
        }
        if (/^(vtt|srt)/.test(resolution)) {
            return 'subtitle';
        }
        return 'video';
    }

    function getDownloadTypeText(type) {
        const keyByType = {
            video: 'history.video',
            audio: 'history.audio',
            subtitle: 'history.subtitle',
            file: 'history.file'
        };
        return translate(keyByType[type] || 'history.file');
    }

    function getResolutionText(resolution) {
        if (resolution === 'compatible-mp4') {
            return translate('composer.compatible_mp4_short');
        }
        return resolution || translate('common.unknown');
    }

    function getResolutionClass(resolution) {
        resolution = resolution || '';
        if (resolution.indexOf('best') >= 0 || resolution.indexOf('compatible-mp4') >= 0 || resolution.indexOf('1080') >= 0 || resolution.indexOf('1440') >= 0 || resolution.indexOf('2160') >= 0) {
            return 'resolution-high';
        } else if (resolution.indexOf('720') >= 0) {
            return 'resolution-medium';
        } else if (resolution.indexOf('audio') >= 0) {
            return 'resolution-audio';
        } else if (/^(vtt|srt)/.test(resolution)) {
            return 'resolution-subtitle';
        } else if (resolution === 'mounted') {
            return 'resolution-file';
        } else {
            return 'resolution-low';
        }
    }

    function getStatusClass(status) {
        if (status === 'file_only') {
            return 'status-file';
        }
        if (status === 'completed') {
            return 'status-completed';
        }
        if (status === 'failed' || status === 'error') {
            return 'status-failed';
        }
        if (status === 'canceled') {
            return 'status-canceled';
        }
        return 'status-pending';
    }

    function getStatusText(status) {
        const keyByStatus = {
            file_only: 'history.mounted',
            completed: 'history.completed',
            failed: 'history.failed',
            error: 'history.error',
            canceled: 'history.canceled',
            canceling: 'history.status_canceling',
            pending: 'history.status_pending',
            queued: 'activity.queued',
            working: 'history.status_working',
            extracting_info: 'history.status_extracting_info',
            downloading: 'history.status_downloading',
            downloading_file: 'history.status_downloading',
            merging: 'history.status_merging'
        };
        return translate(keyByStatus[status] || 'history.unknown');
    }

    function escapeHtml(value) {
        return String(value === null || value === undefined ? '' : value).replace(/[&<>"']/g, function(char) {
            return {
                '&': '&amp;',
                '<': '&lt;',
                '>': '&gt;',
                '"': '&quot;',
                "'": '&#39;'
            }[char];
        });
    }

    function escapeAttr(value) {
        return escapeHtml(value);
    }

    function updateProgress(percentage) {
        console.log("Updating progress to:", percentage);
        if (activeDownload) {
            activeDownload.progress = percentage;
        }
        $('#progress-bar').css('width', percentage + '%');
        $('#progress-bar').attr('aria-valuenow', percentage);

        var displayText = Math.round(percentage) + '%';
        if (currentVideoTitle) {
            displayText = currentChannel ?
                translate('activity.by_channel', { progress: Math.round(percentage), title: currentVideoTitle, channel: currentChannel }) :
                Math.round(percentage) + '% - ' + currentVideoTitle;
        }
        $('#progress-text').text(displayText);
        updateActivityPanel(activeDownload);

        if (percentage >= 100) {
            setTimeout(function() {
                $('#progress-container').hide();
                updateProgress(0);
                currentVideoTitle = '';
                currentChannel = '';
                activeDownload = null;
                updateActivityPanel(null);
                setTimeout(function() {
                    $('#thumbnail-container').hide();
                }, 2000);
            }, 3000);
        }
    }

    function applyCurrentDownload(downloadData) {
        activeDownload = downloadData ? Object.assign({}, activeDownload || {}, downloadData) : null;
        if (activeDownload) {
            currentVideoTitle = activeDownload.title || currentVideoTitle || '';
            currentChannel = activeDownload.channel || currentChannel || '';
        }
        updateActivityPanel(activeDownload);
    }

    function applyStatusResponse(response) {
        if (!response || !response.success) {
            return;
        }

        updateStorageStatus(response.storage || null);
        updateQueueCount(Number(response.queue_count || 0), response.queue || []);
        if (response.current_download) {
            applyCurrentDownload(response.current_download);
            if (response.current_download.progress !== undefined) {
                updateProgress(Number(response.current_download.progress || 0));
            }
        } else if (!response.is_downloading) {
            activeDownload = null;
            updateActivityPanel(null);
        }
    }

    function fetchStatus() {
        $.ajax({
            method: "GET",
            url: "/youtube-dl/status",
            dataType: "json",
            success: applyStatusResponse,
            error: function() {
                updateConnectionStatus(translate('connection.unavailable'), 'failed');
            }
        });
    }

    function startStatusPolling() {
        if (statusPollTimer) {
            clearInterval(statusPollTimer);
        }
        fetchStatus();
        statusPollTimer = setInterval(fetchStatus, 5000);
    }

    function updateStorageStatus(storage) {
        const chip = $('#storage-status');
        chip.removeClass('storage-ok storage-warning storage-critical storage-unavailable');
        if (!storage || !storage.available || storage.free_bytes === null || storage.free_bytes === undefined) {
            chip.text(translate('activity.storage_unavailable'))
                .addClass('storage-unavailable')
                .attr('title', translate('activity.storage_unavailable_title'))
                .prop('hidden', false);
            return;
        }

        const state = ['warning', 'critical'].indexOf(storage.state) >= 0 ? storage.state : 'ok';
        const free = formatFileSize({ file_exists: true, file_size_bytes: storage.free_bytes });
        chip.text(translate('activity.storage_free', { free: free }))
            .addClass(`storage-${state}`)
            .attr('title', translate(`activity.storage_${state}_title`))
            .prop('hidden', false);
    }

    function updateQueueCount(count, items) {
        const nextQueueCount = Math.max(0, count || 0);
        const nextQueueItems = Array.isArray(items) ? items : [];
        const currentSignature = JSON.stringify(queueItems.map(queueItemSignature));
        const nextSignature = JSON.stringify(nextQueueItems.map(queueItemSignature));
        queueCount = nextQueueCount;
        queueItems = nextQueueItems;
        $('#queue-count').text(translate('activity.queue_count', { count: queueCount }));
        if (currentSignature !== nextSignature) {
            renderQueueItems();
        }
    }

    function queueItemSignature(item) {
        return [
            item.id,
            item.position,
            item.url,
            item.resolution,
            item.source,
            Boolean(item.restored),
            item.playlist_mode,
            Boolean(item.write_thumbnail)
        ];
    }

    function renderQueueItems() {
        const container = $('#queue-items');
        const summary = $('#queue-summary');
        if (queueItems.length === 0) {
            summary.text(translate('activity.queue_empty'));
            container.html(`<div class="queue-empty">${escapeHtml(translate('activity.queue_hint'))}</div>`);
            return;
        }

        summary.text(translate('queue.waiting', { count: queueItems.length }));
        container.html(queueItems.map(function(item, index) {
            const position = Number(item.position || index + 1);
            const url = String(item.url || translate('queue.request'));
            const resolution = String(item.resolution || 'best');
            const source = String(item.source || 'web');
            const jobId = String(item.id || '');
            let sourceLabel = item.restored ?
                translate('queue.restored') :
                (source === 'api' ? translate('queue.api_request') : translate('queue.dashboard_request'));
            if (item.playlist_mode === 'first10') {
                sourceLabel += ` · ${translate('queue.first10')}`;
            } else if (item.playlist_mode === 'all') {
                sourceLabel += ` · ${translate('queue.all_items')}`;
            }
            return `
                <div class="queue-item">
                    <span class="queue-position">${position}</span>
                    <div class="queue-item-copy">
                        <strong title="${escapeAttr(url)}">${escapeHtml(formatQueueUrl(url))}</strong>
                        <span>${escapeHtml(sourceLabel)}</span>
                    </div>
                    <span class="resolution-tag ${getResolutionClass(resolution)}">${escapeHtml(getResolutionText(resolution))}</span>
                    <button type="button" class="queue-remove" data-job-id="${escapeAttr(jobId)}"
                            title="${escapeAttr(translate('queue.remove_title'))}" aria-label="${escapeAttr(translate('queue.remove_label'))}">
                        <span class="glyphicon glyphicon-remove" aria-hidden="true"></span>
                    </button>
                </div>
            `;
        }).join(''));
        container.find('.queue-remove').on('click', function() {
            removeQueuedJob(String($(this).attr('data-job-id') || ''));
        });
    }

    function formatQueueUrl(value) {
        try {
            const parsed = new URL(value);
            const compactPath = `${parsed.hostname}${parsed.pathname}`;
            return compactPath.length > 54 ? compactPath.substring(0, 51) + '...' : compactPath;
        } catch (error) {
            return value.length > 54 ? value.substring(0, 51) + '...' : value;
        }
    }

    function removeQueuedJob(jobId) {
        if (!jobId) {
            return;
        }
        $.ajax({
            method: 'POST',
            url: `/youtube-dl/q/${encodeURIComponent(jobId)}/remove`,
            dataType: 'json',
            success: function(response) {
                if (response.success) {
                    fetchStatus();
                    addMessage(translate('queue.removed'), 'info');
                } else {
                    addMessage(getResponseMessage(response, translate('queue.remove_failed')), 'error');
                }
            },
            error: function(jqXHR) {
                addMessage(getAjaxErrorMessage(jqXHR, translate('queue.remove_failed')), 'error');
                fetchStatus();
            }
        });
    }

    function requestActiveCancellation() {
        const button = $('#cancel-active');
        button.prop('disabled', true);
        $.ajax({
            method: 'POST',
            url: '/youtube-dl/q/active/cancel',
            dataType: 'json',
            success: function(response) {
                if (response.success) {
                    addMessage(translate('message.cancel_requested'), 'info');
                    fetchStatus();
                } else {
                    button.prop('disabled', false);
                    addMessage(getResponseMessage(response, translate('message.cancel_failed')), 'error');
                }
            },
            error: function(jqXHR) {
                button.prop('disabled', false);
                addMessage(getAjaxErrorMessage(jqXHR, translate('message.cancel_failed')), 'error');
                fetchStatus();
            }
        });
    }

    function updateActivityPanel(downloadData) {
        const data = downloadData || null;
        if (!data) {
            $('#activity-title').text(queueCount > 0 ? translate('activity.waiting_queue') : translate('activity.idle'));
            $('#activity-summary').text(queueCount > 0 ? translate('activity.requests_queued') : translate('activity.no_active'));
            $('#activity-channel').text(queueCount > 0 ? translate('activity.worker_hint') : translate('activity.waiting_next'));
            $('#activity-status').text(queueCount > 0 ? translate('activity.queued') : translate('activity.idle'))
                .removeClass('status-completed status-failed status-pending status-canceled')
                .addClass('status-pending');
            $('#cancel-active').prop('hidden', true).prop('disabled', false);
            $('#activity-thumbnail-image').hide().attr('src', '');
            $('#activity-thumbnail-placeholder').show();
            $('#activity-transfer').prop('hidden', true);
            $('#progress-container').hide();
            $('#progress-bar').css('width', '0%').attr('aria-valuenow', 0);
            $('#progress-text').text('0%');
            return;
        }

        const status = data.status || 'working';
        const title = data.title || currentVideoTitle || translate('activity.preparing');
        const channel = data.channel || currentChannel || translate('activity.resolving');
        $('#activity-title').text(title);
        $('#activity-summary').text(status === 'extracting_info' ? translate('activity.getting_info') : translate('activity.in_progress'));
        $('#activity-channel').text(channel);
        $('#activity-status').text(getStatusText(status))
            .removeClass('status-completed status-failed status-pending status-canceled')
            .addClass(getStatusClass(status));
        $('#cancel-active').prop('hidden', false).prop('disabled', status === 'canceling');

        if (data.thumbnail) {
            $('#activity-thumbnail-image').attr('src', data.thumbnail).show();
            $('#activity-thumbnail-placeholder').hide();
        } else {
            $('#activity-thumbnail-image').hide().attr('src', '');
            $('#activity-thumbnail-placeholder').show();
        }

        const hasTransferStats = Boolean(data.speed || data.eta);
        $('#activity-transfer').prop('hidden', !hasTransferStats);
        $('#activity-speed').text(data.speed || '--');
        $('#activity-eta').text(translate('activity.eta', { value: data.eta || '--' }));
    }

    function addMessage(message, type = 'info', autoHide = true) {
        if ($("#messages").length === 0) {
            $("body").prepend('<div id="messages" style="position: fixed; top: 20px; right: 20px; z-index: 9999; max-width: 400px;"></div>');
        }

        const messageId = 'msg-' + Date.now();
        const alertClass = type === 'error' ? 'alert-danger' :
                          type === 'warning' ? 'alert-warning' :
                          type === 'success' ? 'alert-success' : 'alert-info';

        const messageHtml = `
            <div id="${messageId}" class="alert ${alertClass} alert-dismissible" style="margin-bottom: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                <button type="button" class="close" data-dismiss="alert" aria-label="${escapeAttr(translate('common.close'))}">
                    <span aria-hidden="true">&times;</span>
                </button>
                ${escapeHtml(message)}
            </div>
        `;

        $("#messages").prepend(messageHtml);

        const messages = $("#messages .alert");
        if (messages.length > maxMessages) {
            messages.slice(maxMessages).fadeOut(300, function() {
                $(this).remove();
            });
        }

        if (autoHide) {
            setTimeout(() => {
                $(`#${messageId}`).fadeOut(300, function() {
                    $(this).remove();
                });
            }, 5000);
        }

        return messageId;
    }

    function clearMessages() {
        $("#messages .alert").fadeOut(300, function() {
            $(this).remove();
        });
    }

    function getResponseMessage(payload, fallback) {
        if (payload && payload.code) {
            const key = `server.${payload.code}`;
            const localized = translate(key, payload.params || {});
            if (localized !== key) {
                return localized;
            }
        }
        return (payload && payload.msg) || fallback;
    }

    function getAjaxErrorMessage(jqXHR, fallback) {
        if (jqXHR.responseJSON) {
            return getResponseMessage(jqXHR.responseJSON, fallback);
        }
        try {
            const response = JSON.parse(jqXHR.responseText);
            return getResponseMessage(response, fallback);
        } catch (e) {
            return fallback;
        }
    }

    function messagesTxt(msg) {
        console.log("Processing message:", msg);

        const firstCommaIndex = msg.indexOf(',');
        if (firstCommaIndex === -1) {
            console.log("Invalid message format:", msg);
            return;
        }

        const messageType = msg.substring(0, firstCommaIndex);
        const messageContent = msg.substring(firstCommaIndex + 1).trim();

        console.log("Message type:", messageType);
        console.log("Message content:", messageContent);

        if (messageType === "[RESTORE_HISTORY]") {
            try {
                if (!isHistoryRestoring) {
                    isHistoryRestoring = true;
                    historyRestoreCount = 0;
                    historyItems = [];
                    renderHistory();
                    console.log("Starting history restoration...");
                }

                const historyData = JSON.parse(messageContent);
                upsertHistoryItem(historyData, true);
                historyRestoreCount++;
            } catch (e) {
                console.error("Error parsing history data:", e, "Raw content:", messageContent);
            }

        } else if (messageType === "[HISTORY_RESTORE_COMPLETE]") {
            console.log(`History restoration completed. Restored ${historyRestoreCount} items.`);
            isHistoryRestoring = false;
            renderHistory();
            thdYn = historyItems.length > 0;
            saveLocalState();

        } else if (messageType === "[HISTORY_CLEARED]") {
            const hadHistory = historyItems.length > 0;
            historyItems = [];
            selectedHistoryUuid = null;
            renderHistory();
            saveLocalState();
            fetchHistory({ quiet: true });
            if (hadHistory) {
                addMessage(translate('message.history_reloaded'), 'warning');
            }

        } else if (messageType === "[HISTORY_DELETED]") {
            const hadItem = historyItems.some((item) => item.uuid === messageContent);
            removeHistoryItem(messageContent);
            if (selectedHistoryUuid === messageContent) {
                selectedHistoryUuid = null;
            }
            renderHistory();
            saveLocalState();
            if (hadItem) {
                addMessage(translate('message.history_deleted'), 'info');
            }

        } else if (messageType === "[COMPLETE]") {
            console.log("Complete message received");
            try {
                const completeData = JSON.parse(messageContent);
                upsertHistoryItem(completeData, false);
                renderHistory();
                thdYn = true;
                saveLocalState();
                fetchStatus();

                const displayTitle = completeData.title && completeData.title.length > 50 ? completeData.title.substring(0, 50) + '...' : completeData.title || translate('common.untitled');
                addMessage(translate('message.download_completed', { title: displayTitle }), 'success');
            } catch (e) {
                console.error("Error parsing complete message:", e, "Raw content:", messageContent);
                addMessage(translate('message.completion_error'), 'error');
            }
        } else if (messageType === "[HISTORY_UPDATED]") {
            try {
                const historyData = JSON.parse(messageContent);
                upsertHistoryItem(historyData, false);
                renderHistory();
                saveLocalState();
                activeDownload = null;
                updateActivityPanel(null);
                fetchStatus();
                if (historyData.status === 'canceled') {
                    addMessage(translate('message.download_canceled'), 'info');
                } else {
                    addMessage(translate('message.download_error'), 'error');
                }
            } catch (error) {
                console.error("Error parsing history update:", error);
                fetchHistory({ quiet: true });
            }
        } else if (messageType === "[RESTORE_ACTIVE]") {
            try {
                const activeData = JSON.parse(messageContent);
                console.log("Restoring active download:", activeData);
                applyCurrentDownload(activeData);

                if (activeData.progress !== undefined) {
                    updateProgress(activeData.progress);
                    if (activeData.progress > 0) {
                        $('#progress-container').show();
                    }
                }

                if (activeData.title) {
                    currentVideoTitle = activeData.title;
                }
                if (activeData.channel) {
                    currentChannel = activeData.channel;
                }

                if (activeData.thumbnail) {
                    $('#video-thumbnail').attr('src', activeData.thumbnail);
                    $('#video-title-display').text(activeData.title || '');
                    $('#video-channel-display').text(activeData.channel || '');
                    $('#thumbnail-container').css('display', 'grid');
                }

                if (activeData.progress > 0 && activeData.progress < 100) {
                    const displayTitle = activeData.title && activeData.title.length > 30 ?
                                       activeData.title.substring(0, 30) + '...' : activeData.title;
                    addMessage(translate('message.resuming', { title: displayTitle, progress: Math.round(activeData.progress) }), 'info');
                }
            } catch (e) {
                console.error("Error parsing active download data:", e);
            }

        } else if (messageType === "[QUEUE_UPDATED]") {
            fetchStatus();

        } else if (messageType === "[DUPLICATE]") {
            try {
                const duplicateData = JSON.parse(messageContent);
                const existing = duplicateData.existing || {};
                const title = existing.title || existing.filename || translate('common.untitled');
                addMessage(translate('message.already_on_nas', { title: title }), 'warning');
                activeDownload = null;
                updateActivityPanel(null);
                fetchStatus();
                fetchHistory({ quiet: true });
            } catch (error) {
                console.error('Error parsing duplicate download data:', error);
                fetchStatus();
            }

        } else if (messageType === "[PROGRESS]") {
            const progress = parseFloat(messageContent);
            updateProgress(progress);
            if (progress > 0) {
                $('#progress-container').show();
            }

        } else if (messageType === "[TRANSFER]") {
            try {
                const stats = JSON.parse(messageContent);
                if (activeDownload) {
                    activeDownload.speed = stats.speed || '';
                    activeDownload.eta = stats.eta || '';
                    updateActivityPanel(activeDownload);
                }
            } catch (error) {
                console.error('Error parsing transfer statistics:', error);
            }

        } else if (messageType === "[MSG]") {
            const localizedMessages = {
                "Shared URL received. Added to the NAS queue.": translate('message.shared_queued'),
                "Download error occurred": translate('message.download_error')
            };
            const message = localizedMessages[messageContent] || messageContent;

            const skipMessages = [
                "WebSocket connection opened.",
                "Connection lost. Reconnecting...",
                "We received your download. Please wait."
            ];

            const downloadPatterns = [
                /^\[Started\] downloading/,
                /^\[Finished\] downloading/,
                /Merging files/,
                /Downloading\.\.\./,
                /Getting video information/
            ];

            if (!skipMessages.includes(message.trim()) &&
                !downloadPatterns.some(pattern => pattern.test(message))) {

                let messageType = 'info';
                if (message.includes('error') || message.includes('failed')) {
                    messageType = 'error';
                } else if (message.includes('warning')) {
                    messageType = 'warning';
                } else if (message.includes('completed') || message.includes('finished')) {
                    messageType = 'success';
                }

                addMessage(message, messageType);
            }

            console.log("Message:", message);

        } else if (messageType === "[TITLE]") {
            const title = messageContent;
            currentVideoTitle = title;
            if (activeDownload) {
                activeDownload.title = title;
            }
            $('#video-title-display').text(title);
            updateActivityPanel(activeDownload);

        } else if (messageType === "[CHANNEL]") {
            const channel = messageContent;
            currentChannel = channel;
            if (activeDownload) {
                activeDownload.channel = channel;
            }
            $('#video-channel-display').text(channel);
            updateActivityPanel(activeDownload);

        } else if (messageType === "[THUMBNAIL]") {
            const thumbnail = messageContent;
            if (activeDownload) {
                activeDownload.thumbnail = thumbnail;
            }
            $('#video-thumbnail').attr('src', thumbnail);
            $('#thumbnail-container').css('display', 'grid');
            updateActivityPanel(activeDownload);
        }
    }

    function showConfirmModal(title, message, onConfirm, confirmText) {
        $('.confirm-modal').remove();
        $(document).off('keydown.confirmModal');
        const returnFocus = document.activeElement;

        const modal = $(`
            <div class="confirm-modal" role="dialog" aria-modal="true"
                 aria-labelledby="confirm-modal-title" aria-describedby="confirm-modal-message">
                <div class="confirm-content">
                    <h4 id="confirm-modal-title">${escapeHtml(title)}</h4>
                    <p id="confirm-modal-message">${escapeHtml(message)}</p>
                    <div class="confirm-buttons">
                        <button type="button" class="btn btn-default confirm-cancel">${escapeHtml(translate('common.cancel'))}</button>
                        <button type="button" class="btn btn-danger confirm-ok">${escapeHtml(confirmText || translate('common.delete'))}</button>
                    </div>
                </div>
            </div>
        `);

        $('body').append(modal);

        function closeConfirmModal(restoreFocus) {
            $(document).off('keydown.confirmModal');
            modal.remove();
            if (restoreFocus && returnFocus && document.contains(returnFocus)) {
                returnFocus.focus();
            }
        }

        modal.find('.confirm-ok').on('click', function() {
            closeConfirmModal(false);
            if (typeof onConfirm === 'function') {
                onConfirm();
            }
        });

        modal.find('.confirm-cancel').on('click', function() {
            closeConfirmModal(true);
        });

        modal.on('click', function(e) {
            if (e.target === modal[0]) {
                closeConfirmModal(true);
            }
        });

        $(document).on('keydown.confirmModal', function(event) {
            if (event.key === 'Escape') {
                closeConfirmModal(true);
            }
        });
        modal.find('.confirm-cancel').focus();
    }

    function closeMediaPreview() {
        const modal = $('.media-preview-modal');
        modal.find('video, audio').each(function() {
            this.pause();
            this.removeAttribute('src');
            this.load();
        });
        modal.remove();
    }

    function showMediaPreview(item) {
        if (!item || !item.file_exists || (item.download_type !== 'video' && item.download_type !== 'audio')) {
            addMessage(translate('preview.unavailable'), 'warning');
            return;
        }

        closeMediaPreview();
        const title = item.title || item.filename || translate('preview.media');
        const source = escapeAttr(getPreviewHref(item));
        const player = item.download_type === 'audio' ?
            `<div class="media-preview-audio-art"><span class="glyphicon glyphicon-music" aria-hidden="true"></span></div><audio controls autoplay preload="metadata" src="${source}"></audio>` :
            `<video controls autoplay playsinline preload="metadata" src="${source}"></video>`;
        const modal = $(`
            <div class="media-preview-modal" role="dialog" aria-modal="true" aria-labelledby="media-preview-title">
                <div class="media-preview-content">
                    <header class="media-preview-header">
                        <div>
                            <span>${escapeHtml(translate('preview.heading'))}</span>
                            <h2 id="media-preview-title">${escapeHtml(title)}</h2>
                        </div>
                        <button type="button" class="media-preview-close" title="${escapeAttr(translate('preview.close'))}" aria-label="${escapeAttr(translate('preview.close'))}">
                            <span class="glyphicon glyphicon-remove" aria-hidden="true"></span>
                        </button>
                    </header>
                    <div class="media-preview-player">${player}</div>
                </div>
            </div>
        `);
        $('body').append(modal);
        modal.find('.media-preview-close').focus();
    }

    function closeSubtitleQa() {
        $('.subtitle-qa-modal').remove();
    }

    function formatQaPercent(value) {
        const percentage = Number(value) * 100;
        return Number.isFinite(percentage) ? `${percentage.toFixed(1)}%` : '--';
    }

    function showSubtitleQa(item) {
        if (!item || !item.file_exists || item.download_type !== 'subtitle') {
            addMessage(translate('qa.unavailable'), 'warning');
            return;
        }

        closeSubtitleQa();
        const title = item.title || item.filename || translate('action.subtitle_qa');
        const modal = $(`
            <div class="subtitle-qa-modal" role="dialog" aria-modal="true" aria-labelledby="subtitle-qa-title">
                <div class="subtitle-qa-content">
                    <header class="subtitle-qa-header">
                        <div>
                            <span>${escapeHtml(translate('action.subtitle_qa'))}</span>
                            <h2 id="subtitle-qa-title">${escapeHtml(title)}</h2>
                            <p>${escapeHtml(item.filename || translate('qa.subtitle_file'))}</p>
                        </div>
                        <button type="button" class="subtitle-qa-close" title="${escapeAttr(translate('qa.close'))}" aria-label="${escapeAttr(translate('qa.close'))}">
                            <span class="glyphicon glyphicon-remove" aria-hidden="true"></span>
                        </button>
                    </header>
                    <form class="subtitle-qa-form">
                        <label class="subtitle-qa-field">
                            <span>${escapeHtml(translate('qa.reference'))}</span>
                            <textarea class="form-control" name="reference" rows="8" maxlength="100000" required placeholder="${escapeAttr(translate('qa.reference_placeholder'))}"></textarea>
                        </label>
                        <label class="subtitle-qa-field">
                            <span>${escapeHtml(translate('qa.keywords'))} <small>${escapeHtml(translate('qa.keywords_hint'))}</small></span>
                            <input class="form-control" name="keywords" type="text" placeholder="${escapeAttr(translate('qa.keywords_placeholder'))}">
                        </label>
                        <div class="subtitle-qa-error" role="alert" hidden></div>
                        <div class="subtitle-qa-actions">
                            <button type="button" class="btn btn-default subtitle-qa-cancel">${escapeHtml(translate('common.cancel'))}</button>
                            <button type="submit" class="btn btn-primary subtitle-qa-submit">
                                <span class="glyphicon glyphicon-stats" aria-hidden="true"></span>
                                ${escapeHtml(translate('qa.analyze'))}
                            </button>
                        </div>
                    </form>
                    <section class="subtitle-qa-results" aria-live="polite" hidden></section>
                </div>
            </div>
        `);

        $('body').append(modal);
        modal.find('textarea[name="reference"]').focus();
        modal.find('.subtitle-qa-form').on('submit', function(event) {
            event.preventDefault();
            analyzeSubtitle(item, modal);
        });
    }

    function analyzeSubtitle(item, modal) {
        const form = modal.find('.subtitle-qa-form');
        const submit = modal.find('.subtitle-qa-submit');
        const error = modal.find('.subtitle-qa-error');
        const reference = String(form.find('[name="reference"]').val() || '').trim();
        const keywords = String(form.find('[name="keywords"]').val() || '').trim();

        if (!reference) {
            error.text(translate('qa.reference_required')).prop('hidden', false);
            form.find('[name="reference"]').focus();
            return;
        }

        error.prop('hidden', true).empty();
        submit.prop('disabled', true).html(`<span class="glyphicon glyphicon-refresh qa-spin" aria-hidden="true"></span> ${escapeHtml(translate('qa.analyzing'))}`);
        $.ajax({
            method: 'POST',
            url: `/youtube-dl/subtitle-qa/${encodeURIComponent(item.uuid)}`,
            data: JSON.stringify({ reference: reference, keywords: keywords }),
            contentType: 'application/json',
            dataType: 'json',
            success: function(response) {
                if (!response.success) {
                    error.text(getResponseMessage(response, translate('qa.failed'))).prop('hidden', false);
                    return;
                }
                renderSubtitleQaResults(modal, response);
            },
            error: function(jqXHR) {
                error.text(getAjaxErrorMessage(jqXHR, translate('qa.failed'))).prop('hidden', false);
            },
            complete: function() {
                submit.prop('disabled', false).html(`<span class="glyphicon glyphicon-stats" aria-hidden="true"></span> ${escapeHtml(translate('qa.analyze'))}`);
            }
        });
    }

    function renderSubtitleQaResults(modal, response) {
        const result = response.result || {};
        const cer = result.cer || {};
        const wer = result.wer || {};
        const crr = result.crr || {};
        const keywords = Array.isArray(result.keywords) ? result.keywords : [];
        const keywordRows = keywords.length ? keywords.map(function(keyword) {
            const rate = keyword.preservation_rate === null ? translate('qa.not_in_reference') : formatQaPercent(keyword.preservation_rate);
            return `
                <tr>
                    <td>${escapeHtml(keyword.keyword)}</td>
                    <td>${Number(keyword.reference_count || 0)}</td>
                    <td>${Number(keyword.subtitle_count || 0)}</td>
                    <td>${rate}</td>
                </tr>
            `;
        }).join('') : '';
        const keywordSection = keywordRows ? `
            <div class="subtitle-qa-keywords">
                <h3>${escapeHtml(translate('qa.keyword_preservation'))}</h3>
                <div class="subtitle-qa-table-wrap">
                    <table>
                        <thead><tr><th>${escapeHtml(translate('qa.keyword'))}</th><th>${escapeHtml(translate('qa.reference_short'))}</th><th>${escapeHtml(translate('qa.subtitle_short'))}</th><th>${escapeHtml(translate('qa.preserved'))}</th></tr></thead>
                        <tbody>${keywordRows}</tbody>
                    </table>
                </div>
            </div>
        ` : '';

        modal.find('.subtitle-qa-results').html(`
            <div class="subtitle-qa-result-heading">
                <div>
                    <span>${escapeHtml(translate('qa.analysis_complete'))}</span>
                    <h3>${escapeHtml((response.file && response.file.filename) || translate('qa.subtitle_file'))}</h3>
                </div>
                <span class="subtitle-qa-engine">nlptutti ${escapeHtml(result.nlptutti_version || '')}</span>
            </div>
            <div class="subtitle-qa-metrics">
                <div><span>${escapeHtml(translate('qa.character_accuracy'))}</span><strong>${formatQaPercent(crr.crr)}</strong><small>${escapeHtml(translate('qa.higher_better'))}</small></div>
                <div><span>${escapeHtml(translate('qa.character_error'))}</span><strong>${formatQaPercent(cer.cer)}</strong><small>${escapeHtml(translate('qa.lower_better'))}</small></div>
                <div><span>${escapeHtml(translate('qa.word_error'))}</span><strong>${formatQaPercent(wer.wer)}</strong><small>${escapeHtml(translate('qa.lower_better'))}</small></div>
            </div>
            <div class="subtitle-qa-breakdown">
                <div><span>${escapeHtml(translate('qa.characters'))}</span><strong>${Number(result.subtitle_characters || 0)}</strong><small>${escapeHtml(translate('qa.reference_count', { count: Number(result.reference_characters || 0) }))}</small></div>
                <div><span>${escapeHtml(translate('qa.words'))}</span><strong>${Number(result.subtitle_words || 0)}</strong><small>${escapeHtml(translate('qa.reference_count', { count: Number(result.reference_words || 0) }))}</small></div>
                <div><span>${escapeHtml(translate('qa.substitutions'))}</span><strong>${Number(cer.substitutions || 0)}</strong><small>${escapeHtml(translate('qa.character_level'))}</small></div>
                <div><span>${escapeHtml(translate('qa.deletions'))}</span><strong>${Number(cer.deletions || 0)}</strong><small>${escapeHtml(translate('qa.character_level'))}</small></div>
                <div><span>${escapeHtml(translate('qa.insertions'))}</span><strong>${Number(cer.insertions || 0)}</strong><small>${escapeHtml(translate('qa.character_level'))}</small></div>
            </div>
            ${keywordSection}
            <div class="subtitle-qa-result-actions">
                <button type="button" class="btn btn-default subtitle-qa-edit">${escapeHtml(translate('qa.edit_reference'))}</button>
                <button type="button" class="btn btn-primary subtitle-qa-done">${escapeHtml(translate('common.done'))}</button>
            </div>
        `).prop('hidden', false);
        modal.find('.subtitle-qa-form').prop('hidden', true);
        modal.find('.subtitle-qa-results').attr('tabindex', '-1').focus();
    }

    function fetchHistory(options) {
        const settings = Object.assign({ quiet: false }, options || {});
        if (historyFetchInFlight) {
            pendingHistoryRefresh = true;
            return;
        }
        historyFetchInFlight = true;
        $.ajax({
            method: "GET",
            url: "/youtube-dl/history",
            dataType: "json",
            success: function(response) {
                if (response.success) {
                    historyItems = (response.history || []).map(normalizeHistoryItem);
                    renderHistory();
                    saveLocalState();
                    if (!settings.quiet) {
                        addMessage(translate('message.file_list_refreshed'), 'success');
                    }
                } else {
                    addMessage(getResponseMessage(response, translate('message.refresh_failed')), 'error');
                }
            },
            error: function(jqXHR) {
                addMessage(getAjaxErrorMessage(jqXHR, translate('message.refresh_failed')), 'error');
            },
            complete: function() {
                historyFetchInFlight = false;
                if (pendingHistoryRefresh) {
                    pendingHistoryRefresh = false;
                    scheduleDashboardRefresh(50);
                }
            }
        });
    }

    function scheduleDashboardRefresh(delay) {
        if (dashboardRefreshTimer) {
            clearTimeout(dashboardRefreshTimer);
        }
        dashboardRefreshTimer = setTimeout(function() {
            dashboardRefreshTimer = null;
            fetchStatus();
            fetchHistory({ quiet: true });
        }, typeof delay === 'number' ? delay : 150);
    }

    function clearAllHistory() {
        $.ajax({
            method: "POST",
            url: "/youtube-dl/history/clear",
            success: function(response) {
                if (response.success) {
                    const hadHistory = historyItems.length > 0;
                    historyItems = [];
                    selectedHistoryUuid = null;
                    renderHistory();
                    saveLocalState();
                    fetchHistory({ quiet: true });
                    if (hadHistory) {
                        addMessage(translate('message.history_cleared'), 'warning');
                    }
                } else {
                    addMessage(getResponseMessage(response, translate('message.clear_failed')), 'error');
                }
            },
            error: function(jqXHR) {
                addMessage(getAjaxErrorMessage(jqXHR, translate('message.clear_error')), 'error');
            }
        });
    }

    function deleteHistoryItem(uuid) {
        $.ajax({
            method: "POST",
            url: `/youtube-dl/history/delete/${encodeURIComponent(uuid)}`,
            success: function(response) {
                if (response.success) {
                    const hadItem = historyItems.some((item) => item.uuid === uuid);
                    removeHistoryItem(uuid);
                    if (selectedHistoryUuid === uuid) {
                        selectedHistoryUuid = null;
                    }
                    renderHistory();
                    saveLocalState();
                    if (hadItem) {
                        addMessage(translate('message.history_item_deleted'), 'info');
                    }
                } else {
                    addMessage(getResponseMessage(response, translate('message.history_delete_failed')), 'error');
                }
            },
            error: function(jqXHR) {
                addMessage(getAjaxErrorMessage(jqXHR, translate('message.history_delete_error')), 'error');
            }
        });
    }

    function deleteHistoryFile(uuid) {
        $.ajax({
            method: "POST",
            url: `/youtube-dl/history/delete-file/${encodeURIComponent(uuid)}`,
            success: function(response) {
                if (response.success) {
                    const deletedUuids = response.deleted_uuids || [uuid];
                    const deletedCount = deletedUuids.filter((deletedUuid) => historyItems.some((item) => item.uuid === deletedUuid)).length;
                    deletedUuids.forEach(removeHistoryItem);
                    if (deletedUuids.indexOf(selectedHistoryUuid) >= 0) {
                        selectedHistoryUuid = null;
                    }
                    renderHistory();
                    saveLocalState();
                    if (deletedCount > 0) {
                        addMessage(translate('message.file_deleted'), 'warning');
                    }
                } else {
                    addMessage(getResponseMessage(response, translate('message.file_delete_failed')), 'error');
                }
            },
            error: function(jqXHR) {
                addMessage(getAjaxErrorMessage(jqXHR, translate('message.file_delete_error')), 'error');
            }
        });
    }

    function retryHistoryItem(uuid) {
        $.ajax({
            method: "POST",
            url: `/youtube-dl/history/retry/${encodeURIComponent(uuid)}`,
            success: function(response) {
                if (response.success) {
                    $('#progress-container').show();
                    updateProgress(0);
                    fetchStatus();
                    addMessage(translate('message.retry_submitted'), 'success');
                } else {
                    addMessage(getResponseMessage(response, translate('message.retry_failed')), 'error');
                }
            },
            error: function(jqXHR) {
                addMessage(getAjaxErrorMessage(jqXHR, translate('message.retry_error')), 'error');
            }
        });
    }

    function downloadProfileStorage() {
        try {
            return window.localStorage;
        } catch (error) {
            return null;
        }
    }

    function restoreDownloadProfile() {
        const helper = window.YDLNAS_DOWNLOAD_PROFILE;
        if (!helper || typeof helper.load !== 'function') {
            return;
        }
        const profile = helper.load(downloadProfileStorage());
        if (!profile) {
            return;
        }

        const resolutionOption = $('#selResolution option').filter(function() {
            return this.value === profile.resolution;
        });
        if (!resolutionOption.length) {
            return;
        }

        $('#selResolution').val(profile.resolution).trigger('change');
        if (profile.mode === 'subtitle' && profile.subtitleLanguage) {
            const languageOption = $('#selSubtitleLanguage option').filter(function() {
                return this.value === profile.subtitleLanguage;
            });
            if (languageOption.length) {
                $('#selSubtitleLanguage').val(profile.subtitleLanguage);
            }
        }
    }

    function saveDownloadProfile(resolution) {
        const helper = window.YDLNAS_DOWNLOAD_PROFILE;
        if (helper && typeof helper.save === 'function') {
            helper.save(downloadProfileStorage(), resolution);
        }
    }

    function syncModeFromResolution() {
        const selectedValue = $('#selResolution').val();
        let mode = 'video';
        if (selectedValue === 'audio-m4a' || selectedValue === 'audio-mp3' || selectedValue === 'audio') {
            mode = 'audio';
        } else if (selectedValue === 'srt' || selectedValue === 'vtt') {
            mode = 'subtitle';
        }
        $('.mode-tab').removeClass('active');
        $(`.mode-tab[data-download-mode="${mode}"]`).addClass('active');
        $('#write-thumbnail').prop('disabled', mode === 'subtitle');
    }

    function setDownloadMode(mode) {
        if (mode === 'audio') {
            $('#selResolution').val('audio-mp3');
        } else if (mode === 'subtitle') {
            $('#selResolution').val('vtt');
        } else if ($('#selResolution').val() === 'audio-m4a' || $('#selResolution').val() === 'audio-mp3' || $('#selResolution').val() === 'srt' || $('#selResolution').val() === 'vtt') {
            $('#selResolution').val('best');
        }

        $('#selResolution').trigger('change');
        syncModeFromResolution();
    }

    $(document).on("submit", "#form1", function(event){
        event.preventDefault();
        console.log("Download form submitted");

        clearMessages();

        var data = {};
        data.url = $("#url").val();

        let subtitleLan = '';
        if ($("#selResolution").val() == 'vtt' || $("#selResolution").val() == 'srt') {
            subtitleLan = $("#selSubtitleLanguage").val();
            data.resolution = `${$("#selResolution").val()}|${subtitleLan}`;
        } else {
            data.resolution = $("#selResolution").val();
        }
        const playlistKind = updatePlaylistGuard();
        data.playlist_mode = $('#playlist-mode').val() || 'single';
        data.write_thumbnail = $('#write-thumbnail').is(':checked') && !/^(srt|vtt)/.test(data.resolution);
        console.log("Selected resolution:", data.resolution);

        if (!data.url) {
            addMessage(translate('message.enter_url'), 'warning');
            return false;
        }
        if (
            (playlistKind === 'playlist' || playlistKind === 'channel')
            && (!$('#playlist-mode').val() || $('#playlist-mode').val() === 'single')
        ) {
            addMessage(translate('message.playlist_scope_required'), 'warning');
            $('#playlist-mode').focus();
            return false;
        }

        $('#thumbnail-container').hide();
        $('#video-thumbnail').attr('src', '');
        $('#video-title-display').text('');
        $('#video-channel-display').text('');

        $.ajax({
            method: "POST",
            url: "/youtube-dl/q",
            data: JSON.stringify(data),
            dataType: "json",
            contentType: "application/json",
            success: function(response, status) {
                console.log("AJAX success:", response);
                if (response.duplicate) {
                    const duplicate = response.existing || response.job || {};
                    const label = duplicate.title || duplicate.filename || formatQueueUrl(data.url);
                    fetchStatus();
                    addMessage(translate('message.already_queued', { title: label }), 'warning');
                    return;
                }
                if (response.queued === true) {
                    saveDownloadProfile(data.resolution);
                }
                $('#progress-container').show();
                updateProgress(0);
                currentVideoTitle = '';
                currentChannel = '';
                fetchStatus();
                addMessage(translate('message.request_submitted'), 'success');
            },
            error: function(jqXHR, textStatus, errorThrown) {
                console.log("AJAX error - textStatus:", textStatus);
                console.log("AJAX error - errorThrown:", errorThrown);
                addMessage(getAjaxErrorMessage(jqXHR, translate('message.request_failed', { status: textStatus })), 'error');
            }
        });

        $('#url').val('').focus();
        updatePlaylistGuard();
        return false;
    });

    $(document).on("click", "#history-search-button", function() {
        applyHistorySearch();
    });

    $(document).on("keydown", "#history-search", function(event) {
        if (event.key === 'Enter') {
            event.preventDefault();
            applyHistorySearch();
        }
    });

    $(document).on("search", "#history-search", function() {
        applyHistorySearch();
    });

    $(document).on("change", "#history-sort, #history-status-filter", function() {
        historyPrefs.sort = $('#history-sort').val();
        historyPrefs.status = $('#history-status-filter').val();
        resetHistoryPaging();
        saveHistoryPrefs();
        renderHistory();
    });

    $(document).on("click", ".history-type-option", function() {
        historyPrefs.type = $(this).data('history-type') || 'all';
        resetHistoryPaging();
        applyHistoryPrefsToControls();
        saveHistoryPrefs();
        renderHistory();
    });

    $(document).on("click", ".history-view-btn", function() {
        historyPrefs.view = $(this).data('history-view') === 'grid' ? 'grid' : 'list';
        selectedHistoryUuid = null;
        applyHistoryPrefsToControls();
        saveHistoryPrefs();
        renderHistory();
    });

    $(document).on("click", "#history-insights-toggle", function() {
        selectedHistoryUuid = null;
        historyOverviewOpen = true;
        renderHistory();
        focusHistoryDrawerControl('#close-insights');
    });

    $(document).on("click", ".insights-filter", function() {
        applyInsightsFilter($(this).data('history-type'), $(this).data('history-status'));
    });

    $(document).on("click", "#reset-history-filters", function() {
        const currentView = historyPrefs.view || 'list';
        historyPrefs = {
            sort: 'date-desc',
            status: 'all',
            type: 'all',
            search: '',
            view: currentView
        };
        applyHistoryPrefsToControls();
        resetHistoryPaging();
        saveHistoryPrefs();
        renderHistory();
    });

    $(document).on("click", ".history-page-btn, .history-page-nav", function() {
        if ($(this).prop('disabled')) {
            return;
        }

        currentHistoryPage = clampHistoryPage($(this).data('page'), getHistoryTotalPages(getFilteredHistoryItems().length));
        selectedHistoryUuid = null;
        renderHistory();
    });

    $(document).on("click", ".mode-tab", function() {
        setDownloadMode($(this).data('download-mode'));
    });

    $(document).on("click", "#cancel-active", function() {
        showConfirmModal(
            translate('confirm.cancel_download_heading'),
            translate('confirm.cancel_download_message'),
            requestActiveCancellation,
            translate('activity.cancel')
        );
    });

    $(document).on("change", "#selResolution", function() {
        syncModeFromResolution();
    });

    $(document).on("input change", "#url", function() {
        updatePlaylistGuard();
    });

    $(document).on("change", "#share-default-profile", function() {
        saveShareProfile($(this).val());
    });

    $(document).on("click keydown", ".history-row, .history-card, .history-grid-card", function(event) {
        if (event.type === 'keydown' && event.key !== 'Enter' && event.key !== ' ') {
            return;
        }
        if ($(event.target).closest('.action-btn, a, button').length) {
            return;
        }
        event.preventDefault();
        selectHistoryItem($(this).data('uuid'));
    });

    $(document).on("click", "#close-detail", function() {
        selectedHistoryUuid = null;
        historyOverviewOpen = true;
        renderHistory();
        if (isCompactHistoryDrawer()) {
            focusHistoryDrawerControl('#close-insights');
        }
    });

    $(document).on("click", "#close-insights, #history-detail-backdrop", function() {
        dismissHistoryDrawer(true);
    });

    $(document).on("click", "#refresh-history", function() {
        fetchHistory();
    });

    $(document).on("click", "#clear-history", function() {
        showConfirmModal(
            translate('confirm.clear_heading'),
            translate('confirm.clear_message'),
            clearAllHistory,
            translate('history.clear_rows')
        );
    });

    $(document).on("click", ".action-history-delete", function(event) {
        event.stopPropagation();
        const uuid = $(this).data('uuid');
        const item = historyItems.find((historyItem) => historyItem.uuid === uuid);
        const title = item ? item.title : translate('common.untitled');

        showConfirmModal(
            translate('confirm.delete_history_heading'),
            translate('confirm.delete_history_message', { title: title.substring(0, 50) }),
            function() {
                deleteHistoryItem(uuid);
            },
            translate('action.delete_history')
        );
    });

    $(document).on("click", ".action-file-delete", function(event) {
        event.stopPropagation();
        const uuid = $(this).data('uuid');
        const item = historyItems.find((historyItem) => historyItem.uuid === uuid);
        const title = item ? item.title : translate('history.file');
        const mountedFile = item && isMountedFile(item);
        const message = mountedFile ?
            translate('confirm.delete_mounted_message', { title: title.substring(0, 50) }) :
            translate('confirm.delete_file_message', { title: title.substring(0, 50) });

        showConfirmModal(
            translate('confirm.delete_file_heading'),
            message,
            function() {
                deleteHistoryFile(uuid);
            },
            translate('action.delete_file')
        );
    });

    $(document).on("click", ".action-retry", function(event) {
        event.stopPropagation();
        retryHistoryItem($(this).data('uuid'));
    });

    $(document).on("click", ".action-download", function(event) {
        event.stopPropagation();
    });

    $(document).on("click", ".action-preview", function(event) {
        event.stopPropagation();
        const uuid = $(this).data('uuid');
        showMediaPreview(historyItems.find((item) => item.uuid === uuid));
    });

    $(document).on("click", ".action-subtitle-qa", function(event) {
        event.stopPropagation();
        const uuid = $(this).data('uuid');
        showSubtitleQa(historyItems.find((item) => item.uuid === uuid));
    });

    $(document).on("click", ".media-preview-close", function() {
        closeMediaPreview();
    });

    $(document).on("click", ".media-preview-modal", function(event) {
        if (event.target === this) {
            closeMediaPreview();
        }
    });

    $(document).on("click", ".subtitle-qa-close, .subtitle-qa-cancel, .subtitle-qa-done", function() {
        closeSubtitleQa();
    });

    $(document).on("click", ".subtitle-qa-edit", function() {
        const modal = $(this).closest('.subtitle-qa-modal');
        modal.find('.subtitle-qa-results').prop('hidden', true).empty();
        modal.find('.subtitle-qa-form').prop('hidden', false);
        modal.find('textarea[name="reference"]').focus();
    });

    $(document).on("click", ".subtitle-qa-modal", function(event) {
        if (event.target === this) {
            closeSubtitleQa();
        }
    });

    $(document).on("keydown", function(event) {
        if (event.key === 'Tab' && $('body').hasClass('history-drawer-open')) {
            trapHistoryDrawerFocus(event);
        } else if (event.key === 'Escape' && $('.media-preview-modal').length) {
            closeMediaPreview();
        } else if (event.key === 'Escape' && $('.subtitle-qa-modal').length) {
            closeSubtitleQa();
        } else if (event.key === 'Escape' && $('body').hasClass('history-drawer-open')) {
            dismissHistoryDrawer(true);
        }
    });

    let historyDrawerWasCompact = isCompactHistoryDrawer();
    window.addEventListener('resize', function() {
        const compact = isCompactHistoryDrawer();
        if (compact !== historyDrawerWasCompact) {
            historyDrawerWasCompact = compact;
            syncHistoryDrawerChrome(!!selectedHistoryUuid);
        }
    });

    document.addEventListener('visibilitychange', function() {
        if (document.visibilityState === 'visible') {
            scheduleDashboardRefresh(100);
        }
    });

    window.addEventListener('pageshow', function() {
        scheduleDashboardRefresh(100);
    });

    applyHistoryPrefsToControls();
    restoreDownloadProfile();
    syncModeFromResolution();
    updatePlaylistGuard();
    loadPreferences();
    restoreLocalState();
    renderHistory();
    startStatusPolling();
    connectWebSocket();
});
