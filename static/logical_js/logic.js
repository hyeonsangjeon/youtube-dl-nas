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
//---------------------------------------------------------------------------------------------------//
$(document).ready(function() {
    if (!$('body').hasClass('dashboard-page')) {
        return;
    }

    const pageParams = new URLSearchParams(window.location.search);
    const sharedStatus = pageParams.get('shared');
    if (sharedStatus === 'queued') {
        addMessage('Shared URL added to the NAS queue', 'success');
    } else if (sharedStatus === 'missing') {
        addMessage('No URL was found in the shared content', 'warning');
    } else if (sharedStatus === 'invalid') {
        addMessage('The shared URL could not be queued', 'error');
    }
    if (sharedStatus && window.history.replaceState) {
        pageParams.delete('shared');
        const cleanQuery = pageParams.toString();
        window.history.replaceState({}, document.title, window.location.pathname + (cleanQuery ? '?' + cleanQuery : ''));
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
    let activeDownload = null;
    let queueCount = 0;
    let queueItems = [];
    let statusPollTimer = null;
    const historyPageSize = 20;
    let currentHistoryPage = 1;
    const emptyColspan = 7;

    console.log("Document ready - initializing...");

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
                reconnectAttempts = 0;
                reconnectDelay = 1000;
                updateConnectionStatus('Online', 'completed');
                messagesTxt("[MSG], WebSocket connection opened.");
                fetchStatus();

                setTimeout(() => {
                    if (wsEventBus && wsEventBus.readyState === WebSocket.OPEN) {
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
                updateConnectionStatus('Reconnecting', 'pending');
                messagesTxt("[MSG], Connection lost. Reconnecting...");
                attemptReconnect();
            }

            wsEventBus.onerror = function(evt) {
                console.log("WebSocket error: ", evt);
                updateConnectionStatus('Error', 'failed');
                messagesTxt("[MSG], Connection error occurred.");
            }
        } catch (error) {
            console.error("WebSocket connection failed:", error);
            wsEventBus = null;
            updateConnectionStatus('Offline', 'failed');
            attemptReconnect();
        }
    }

    function attemptReconnect() {
        if (reconnectAttempts >= maxReconnectAttempts) {
            updateConnectionStatus('Offline', 'failed');
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
            duration_seconds: 0,
            status: 'unknown',
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
            `${rangeStart}-${rangeEnd} of ${historyItems.length} items` :
            `${rangeStart}-${rangeEnd} of ${filteredItems.length} matching items`;
        $('#history-result-count').text(resultLabel);

        if (historyItems.length === 0) {
            body.html(`<tr><td colspan="${emptyColspan}" class="empty-state">No files yet<br><small>Start downloading or mount files into /downfolder</small></td></tr>`);
            cards.html(renderEmptyCard("No files yet", "Start downloading or mount files into /downfolder"));
            grid.html(renderEmptyCard("No files yet", "Start downloading or mount files into /downfolder"));
            pager.empty();
            renderDetailDrawer(null);
            return;
        }

        if (filteredItems.length === 0) {
            body.html(`<tr><td colspan="${emptyColspan}" class="empty-state">No matching downloads<br><small>Try a different search or filter</small></td></tr>`);
            cards.html(renderEmptyCard("No matching downloads", "Try a different search or filter"));
            grid.html(renderEmptyCard("No matching downloads", "Try a different search or filter"));
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
            <button type="button" class="history-page-nav" data-page="${currentHistoryPage - 1}" ${currentHistoryPage === 1 ? 'disabled' : ''}>Prev</button>
            <div class="history-page-list" aria-label="History pages">
                ${pageItems}
            </div>
            <button type="button" class="history-page-nav" data-page="${currentHistoryPage + 1}" ${currentHistoryPage === totalPages ? 'disabled' : ''}>Next</button>
            <span class="history-page-summary">Page ${currentHistoryPage} of ${totalPages}</span>
        `);
    }

    function getFilteredHistoryItems() {
        const searchText = (historyPrefs.search || '').toLowerCase().trim();
        const filtered = historyItems.filter((item) => {
            const statusMatches = historyPrefs.status === 'all' || item.status === historyPrefs.status;
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
        const safeTitle = escapeAttr(item.title || 'Untitled');
        const safeChannel = escapeAttr(item.channel || 'Unknown');
        const safeTimestamp = escapeAttr(item.timestamp || '');
        const titleText = escapeHtml(item.title || 'Untitled');
        const channelText = escapeHtml(item.channel || 'Unknown');
        const resolutionText = escapeHtml(item.resolution || 'unknown');
        const typeText = escapeHtml(item.download_type || getHistoryType(item.resolution));
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
        const titleText = escapeHtml(item.title || 'Untitled');
        const channelText = escapeHtml(item.channel || 'Unknown');
        const resolutionText = escapeHtml(item.resolution || 'unknown');
        const typeText = escapeHtml(item.download_type || getHistoryType(item.resolution));
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
        const titleText = escapeHtml(item.title || item.filename || 'Untitled');
        const channelText = escapeHtml(item.channel || (isMountedFile(item) ? 'Mounted folder' : 'Unknown'));
        const typeText = escapeHtml(item.download_type || getHistoryType(item.resolution));
        const thumbnailUrl = getSafeThumbnailUrl(item.thumbnail);
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
            `<span class="resolution-tag ${getResolutionClass(item.resolution)}">${escapeHtml(item.resolution || 'unknown')}</span>`;

        return `
            <article class="history-grid-card ${selectedClass}" data-uuid="${safeUuid}" tabindex="0">
                <div class="history-grid-media ${thumbnailUrl ? '' : 'history-grid-placeholder'}">
                    ${visual}
                    ${durationBadge}
                    <span class="history-grid-type type-${escapeAttr(item.download_type)}">${typeText}</span>
                </div>
                <div class="history-grid-body">
                    <h3 title="${escapeAttr(item.title || item.filename || 'Untitled')}">${titleText}</h3>
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
        return /^https?:\/\//i.test(thumbnail) ? thumbnail : '';
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
        return isMountedFile(item) ? 'No metadata' : 'Saved metadata';
    }

    function renderMetadataBadge(item) {
        if (!isMountedFile(item)) {
            return '';
        }

        return '<span class="metadata-badge metadata-missing">No metadata</span>';
    }

    function renderMetadataLine(item) {
        if (!isMountedFile(item)) {
            return '';
        }

        return `
            <div class="history-meta-line">
                ${renderMetadataBadge(item)}
                <span>Scanned from /downfolder</span>
            </div>
        `;
    }

    function renderMetadataSourceLine(item) {
        if (!isMountedFile(item)) {
            return '';
        }

        return '<div class="history-meta-line history-card-meta-line"><span>Scanned from /downfolder</span></div>';
    }

    function renderActionButtons(item, context) {
        const safeUuid = escapeAttr(item.uuid);
        const isDetail = context === 'detail';
        const mountedFile = isMountedFile(item);
        const canRetry = !mountedFile && item.url && item.resolution && (item.status === 'failed' || item.status === 'error');
        const canPreview = item.file_exists && (item.download_type === 'video' || item.download_type === 'audio');
        const canAnalyzeSubtitle = item.file_exists && item.download_type === 'subtitle';
        const previewButton = canPreview ? `
            <button class="action-btn action-preview" data-uuid="${safeUuid}" title="Preview media">
                <span class="glyphicon glyphicon-play"></span>${isDetail ? '<span>Preview</span>' : ''}
            </button>` : '';
        const subtitleQaButton = canAnalyzeSubtitle ? `
            <button class="action-btn action-subtitle-qa" data-uuid="${safeUuid}" title="Analyze subtitle accuracy">
                <span class="glyphicon glyphicon-check"></span>${isDetail ? '<span>Subtitle QA</span>' : ''}
            </button>` : '';
        const downloadButton = item.file_exists ? `
            <a class="action-btn action-download" href="${getDownloadHref(item)}" download title="Download file">
                <span class="glyphicon glyphicon-download-alt"></span>${isDetail ? '<span>Download File</span>' : ''}
            </a>` : '';
        const fileDeleteTitle = mountedFile ? 'Delete mounted file' : 'Delete file and related history';
        const retryButton = canRetry ? `
            <button class="action-btn action-retry" data-uuid="${safeUuid}" title="Retry download">
                <span class="glyphicon glyphicon-repeat"></span>${isDetail ? '<span>Retry Download</span>' : ''}
            </button>` : '';
        const fileDeleteButton = item.file_exists ? `
            <button class="action-btn action-file-delete" data-uuid="${safeUuid}" title="${escapeAttr(fileDeleteTitle)}">
                <span class="glyphicon glyphicon-remove"></span>${isDetail ? '<span>Delete File</span>' : ''}
            </button>` : '';
        const historyDeleteButton = !mountedFile ? `
                <button class="action-btn action-history-delete" data-uuid="${safeUuid}" title="Delete history only">
                    <span class="glyphicon glyphicon-trash"></span>${isDetail ? '<span>Delete History</span>' : ''}
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
        const item = historyItems.find((historyItem) => historyItem.uuid === uuid);
        renderDetailDrawer(item || null);
        renderHistory();
        if (window.matchMedia && window.matchMedia('(max-width: 768px)').matches) {
            window.requestAnimationFrame(function() {
                const detailDrawer = document.getElementById('history-detail-drawer');
                if (detailDrawer) {
                    detailDrawer.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }
            });
        }
    }

    function renderDetailDrawer(item) {
        const drawer = $('#history-detail-drawer');
        drawer.toggleClass('detail-is-empty', !item);
        drawer.toggleClass('detail-has-item', !!item);
        if (!item) {
            drawer.html(`
                <div class="detail-empty">
                    <span class="glyphicon glyphicon-list-alt" aria-hidden="true"></span>
                    <h2>Select a download</h2>
                    <p>Open a history item to view URL, file details, and actions.</p>
                </div>
            `);
            return;
        }

        const typeText = escapeHtml(item.download_type || getHistoryType(item.resolution));
        const statusText = escapeHtml(getStatusText(item.status));
        const url = item.url || '';
        const urlHtml = url ?
            `<a href="${escapeAttr(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(url)}</a>` :
            '<span class="muted">No URL saved</span>';
        const mountedFile = isMountedFile(item);
        const sourceText = mountedFile ? 'Mounted folder' : 'Download history';
        const metadataText = getMetadataStatusText(item);
        const metadataNotice = mountedFile ? `
            <div class="metadata-notice">
                <span class="glyphicon glyphicon-info-sign" aria-hidden="true"></span>
                <div>
                    <strong>No download metadata</strong>
                    <p>This file was found in /downfolder without a saved history row, so source URL, channel, and quality details are unavailable.</p>
                </div>
            </div>
        ` : '';

        drawer.html(`
            <article class="detail-panel ${mountedFile ? 'detail-panel-mounted' : ''}" data-uuid="${escapeAttr(item.uuid)}">
                <button type="button" id="close-detail" class="detail-close" title="Close details">
                    <span class="glyphicon glyphicon-remove"></span>
                </button>
                <div class="detail-heading">
                    <div>
                        <span class="type-tag type-${escapeAttr(item.download_type)}">${typeText}</span>
                        <span class="status-tag ${getStatusClass(item.status)}">${statusText}</span>
                    </div>
                    <h2 title="${escapeAttr(item.title || 'Untitled')}">${escapeHtml(item.title || 'Untitled')}</h2>
                    <p>${escapeHtml(item.channel || 'Unknown channel')}</p>
                </div>
                ${metadataNotice}
                <dl class="detail-list">
                    ${renderDetailField('Downloaded', formatTimestamp(item.timestamp), 'downloaded')}
                    ${renderDetailField('Duration', formatDuration(item.duration_seconds) || 'Unknown', 'duration')}
                    ${renderDetailField('Resolution', item.resolution || 'unknown', 'resolution')}
                    ${renderDetailField('Size', formatFileSize(item), 'size')}
                    ${renderDetailField('Filename', item.filename || 'No file saved', 'filename')}
                    ${renderDetailField('Source', sourceText, 'source')}
                    ${renderDetailField('Metadata', metadataText, 'metadata')}
                    ${renderDetailField('UUID', item.uuid || '', 'uuid')}
                </dl>
                <div class="detail-url ${url ? '' : 'detail-url-empty'}">
                    <span>Source URL</span>
                    ${urlHtml}
                </div>
                <div class="detail-actions">${renderActionButtons(item, 'detail')}</div>
            </article>
        `);
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

    function getTimestampValue(timestamp) {
        const value = Date.parse(timestamp || '');
        return isNaN(value) ? 0 : value;
    }

    function formatTimestamp(timestamp) {
        if (!timestamp) {
            return 'Unknown';
        }

        const date = new Date(timestamp);
        if (isNaN(date.getTime())) {
            return timestamp;
        }

        return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())} ${pad2(date.getHours())}:${pad2(date.getMinutes())}`;
    }

    function pad2(value) {
        return String(value).padStart(2, '0');
    }

    function formatFileSize(item) {
        const size = Number(item.file_size_bytes || 0);
        if (!item.file_exists) {
            return item.filename ? 'Missing' : '-';
        }
        if (size <= 0) {
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
        return `${value.toFixed(precision)} ${units[unitIndex]}`;
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

    function getResolutionClass(resolution) {
        resolution = resolution || '';
        if (resolution.indexOf('best') >= 0 || resolution.indexOf('1080') >= 0 || resolution.indexOf('1440') >= 0 || resolution.indexOf('2160') >= 0) {
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
        return 'status-pending';
    }

    function getStatusText(status) {
        if (status === 'file_only') {
            return 'Mounted';
        }
        return status || 'unknown';
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
            displayText = Math.round(percentage) + '% - ' + currentVideoTitle;
            if (currentChannel) {
                displayText += ' by ' + currentChannel;
            }
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
                updateConnectionStatus('Status unavailable', 'failed');
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

    function updateQueueCount(count, items) {
        queueCount = Math.max(0, count || 0);
        queueItems = Array.isArray(items) ? items : [];
        $('#queue-count').text(`Queue ${queueCount}`);
        renderQueueItems();
    }

    function renderQueueItems() {
        const container = $('#queue-items');
        const summary = $('#queue-summary');
        if (queueItems.length === 0) {
            summary.text('Queue is empty');
            container.html('<div class="queue-empty">New requests will appear here in order.</div>');
            return;
        }

        summary.text(`${queueItems.length} waiting`);
        container.html(queueItems.map(function(item, index) {
            const position = Number(item.position || index + 1);
            const url = String(item.url || 'Queued request');
            const resolution = String(item.resolution || 'best');
            const source = String(item.source || 'web');
            return `
                <div class="queue-item">
                    <span class="queue-position">${position}</span>
                    <div class="queue-item-copy">
                        <strong title="${escapeAttr(url)}">${escapeHtml(formatQueueUrl(url))}</strong>
                        <span>${escapeHtml(source === 'api' ? 'API request' : 'Dashboard request')}</span>
                    </div>
                    <span class="resolution-tag ${getResolutionClass(resolution)}">${escapeHtml(resolution)}</span>
                </div>
            `;
        }).join(''));
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

    function updateActivityPanel(downloadData) {
        const data = downloadData || null;
        if (!data) {
            $('#activity-title').text(queueCount > 0 ? 'Waiting in queue' : 'Idle');
            $('#activity-summary').text(queueCount > 0 ? 'Requests are queued' : 'No active download');
            $('#activity-channel').text(queueCount > 0 ? 'The worker will pick up the next request.' : 'Waiting for the next request.');
            $('#activity-status').text(queueCount > 0 ? 'queued' : 'idle')
                .removeClass('status-completed status-failed status-pending')
                .addClass('status-pending');
            $('#activity-thumbnail-image').hide().attr('src', '');
            $('#activity-thumbnail-placeholder').show();
            $('#activity-transfer').prop('hidden', true);
            return;
        }

        const status = data.status || 'working';
        const title = data.title || currentVideoTitle || 'Preparing download';
        const channel = data.channel || currentChannel || 'Resolving media information';
        $('#activity-title').text(title);
        $('#activity-summary').text(status === 'extracting_info' ? 'Getting video information' : 'Download in progress');
        $('#activity-channel').text(channel);
        $('#activity-status').text(status)
            .removeClass('status-completed status-failed status-pending')
            .addClass(getStatusClass(status));

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
        $('#activity-eta').text(data.eta ? `ETA ${data.eta}` : 'ETA --');
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
                <button type="button" class="close" data-dismiss="alert" aria-label="Close">
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

    function getAjaxErrorMessage(jqXHR, fallback) {
        if (jqXHR.responseJSON && jqXHR.responseJSON.msg) {
            return jqXHR.responseJSON.msg;
        }
        try {
            const response = JSON.parse(jqXHR.responseText);
            return response.msg || fallback;
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
                addMessage("History rows cleared. Mounted files were reloaded.", 'warning');
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
                addMessage("Download history item deleted", 'info');
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

                const displayTitle = completeData.title && completeData.title.length > 50 ? completeData.title.substring(0, 50) + '...' : completeData.title || 'download';
                addMessage(`Download completed: ${displayTitle}`, 'success');
            } catch (e) {
                console.error("Error parsing complete message:", e, "Raw content:", messageContent);
                addMessage("Error processing download completion", 'error');
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
                    addMessage(`Resuming download: ${displayTitle} (${Math.round(activeData.progress)}%)`, 'info');
                }
            } catch (e) {
                console.error("Error parsing active download data:", e);
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
            const message = messageContent;

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

        const modal = $(`
            <div class="confirm-modal">
                <div class="confirm-content">
                    <h4>${escapeHtml(title)}</h4>
                    <p>${escapeHtml(message)}</p>
                    <div class="confirm-buttons">
                        <button class="btn btn-default confirm-cancel">Cancel</button>
                        <button class="btn btn-danger confirm-ok">${escapeHtml(confirmText || 'Delete')}</button>
                    </div>
                </div>
            </div>
        `);

        $('body').append(modal);

        modal.find('.confirm-ok').on('click', function() {
            modal.remove();
            if (typeof onConfirm === 'function') {
                onConfirm();
            }
        });

        modal.find('.confirm-cancel').on('click', function() {
            modal.remove();
        });

        modal.on('click', function(e) {
            if (e.target === modal[0]) {
                modal.remove();
            }
        });
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
            addMessage('This file cannot be previewed in the browser', 'warning');
            return;
        }

        closeMediaPreview();
        const title = item.title || item.filename || 'Media preview';
        const source = escapeAttr(getPreviewHref(item));
        const player = item.download_type === 'audio' ?
            `<div class="media-preview-audio-art"><span class="glyphicon glyphicon-music" aria-hidden="true"></span></div><audio controls autoplay preload="metadata" src="${source}"></audio>` :
            `<video controls autoplay playsinline preload="metadata" src="${source}"></video>`;
        const modal = $(`
            <div class="media-preview-modal" role="dialog" aria-modal="true" aria-labelledby="media-preview-title">
                <div class="media-preview-content">
                    <header class="media-preview-header">
                        <div>
                            <span>Preview</span>
                            <h2 id="media-preview-title">${escapeHtml(title)}</h2>
                        </div>
                        <button type="button" class="media-preview-close" title="Close preview" aria-label="Close preview">
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
            addMessage('Subtitle QA requires an available subtitle file', 'warning');
            return;
        }

        closeSubtitleQa();
        const title = item.title || item.filename || 'Subtitle QA';
        const modal = $(`
            <div class="subtitle-qa-modal" role="dialog" aria-modal="true" aria-labelledby="subtitle-qa-title">
                <div class="subtitle-qa-content">
                    <header class="subtitle-qa-header">
                        <div>
                            <span>Subtitle QA</span>
                            <h2 id="subtitle-qa-title">${escapeHtml(title)}</h2>
                            <p>${escapeHtml(item.filename || 'Subtitle file')}</p>
                        </div>
                        <button type="button" class="subtitle-qa-close" title="Close Subtitle QA" aria-label="Close Subtitle QA">
                            <span class="glyphicon glyphicon-remove" aria-hidden="true"></span>
                        </button>
                    </header>
                    <form class="subtitle-qa-form">
                        <label class="subtitle-qa-field">
                            <span>Reference transcript</span>
                            <textarea class="form-control" name="reference" rows="8" maxlength="100000" required placeholder="Paste the verified transcript to compare with this subtitle file."></textarea>
                        </label>
                        <label class="subtitle-qa-field">
                            <span>Keywords <small>optional, comma or line separated</small></span>
                            <input class="form-control" name="keywords" type="text" placeholder="Azure AI, yt-dlp, Synology">
                        </label>
                        <div class="subtitle-qa-error" role="alert" hidden></div>
                        <div class="subtitle-qa-actions">
                            <button type="button" class="btn btn-default subtitle-qa-cancel">Cancel</button>
                            <button type="submit" class="btn btn-primary subtitle-qa-submit">
                                <span class="glyphicon glyphicon-stats" aria-hidden="true"></span>
                                Analyze
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
            error.text('Paste a reference transcript before analyzing.').prop('hidden', false);
            form.find('[name="reference"]').focus();
            return;
        }

        error.prop('hidden', true).empty();
        submit.prop('disabled', true).html('<span class="glyphicon glyphicon-refresh qa-spin" aria-hidden="true"></span> Analyzing');
        $.ajax({
            method: 'POST',
            url: `/youtube-dl/subtitle-qa/${encodeURIComponent(item.uuid)}`,
            data: JSON.stringify({ reference: reference, keywords: keywords }),
            contentType: 'application/json',
            dataType: 'json',
            success: function(response) {
                if (!response.success) {
                    error.text(response.msg || 'Subtitle QA failed').prop('hidden', false);
                    return;
                }
                renderSubtitleQaResults(modal, response);
            },
            error: function(jqXHR) {
                error.text(getAjaxErrorMessage(jqXHR, 'Subtitle QA failed')).prop('hidden', false);
            },
            complete: function() {
                submit.prop('disabled', false).html('<span class="glyphicon glyphicon-stats" aria-hidden="true"></span> Analyze');
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
            const rate = keyword.preservation_rate === null ? 'Not in reference' : formatQaPercent(keyword.preservation_rate);
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
                <h3>Keyword preservation</h3>
                <div class="subtitle-qa-table-wrap">
                    <table>
                        <thead><tr><th>Keyword</th><th>Reference</th><th>Subtitle</th><th>Preserved</th></tr></thead>
                        <tbody>${keywordRows}</tbody>
                    </table>
                </div>
            </div>
        ` : '';

        modal.find('.subtitle-qa-results').html(`
            <div class="subtitle-qa-result-heading">
                <div>
                    <span>Analysis complete</span>
                    <h3>${escapeHtml((response.file && response.file.filename) || 'Subtitle file')}</h3>
                </div>
                <span class="subtitle-qa-engine">nlptutti ${escapeHtml(result.nlptutti_version || '')}</span>
            </div>
            <div class="subtitle-qa-metrics">
                <div><span>Character accuracy</span><strong>${formatQaPercent(crr.crr)}</strong><small>Higher is better</small></div>
                <div><span>Character error</span><strong>${formatQaPercent(cer.cer)}</strong><small>Lower is better</small></div>
                <div><span>Word error</span><strong>${formatQaPercent(wer.wer)}</strong><small>Lower is better</small></div>
            </div>
            <div class="subtitle-qa-breakdown">
                <div><span>Characters</span><strong>${Number(result.subtitle_characters || 0)}</strong><small>Reference ${Number(result.reference_characters || 0)}</small></div>
                <div><span>Words</span><strong>${Number(result.subtitle_words || 0)}</strong><small>Reference ${Number(result.reference_words || 0)}</small></div>
                <div><span>Substitutions</span><strong>${Number(cer.substitutions || 0)}</strong><small>Character level</small></div>
                <div><span>Deletions</span><strong>${Number(cer.deletions || 0)}</strong><small>Character level</small></div>
                <div><span>Insertions</span><strong>${Number(cer.insertions || 0)}</strong><small>Character level</small></div>
            </div>
            ${keywordSection}
            <div class="subtitle-qa-result-actions">
                <button type="button" class="btn btn-default subtitle-qa-edit">Edit reference</button>
                <button type="button" class="btn btn-primary subtitle-qa-done">Done</button>
            </div>
        `).prop('hidden', false);
        modal.find('.subtitle-qa-form').prop('hidden', true);
        modal.find('.subtitle-qa-results').attr('tabindex', '-1').focus();
    }

    function fetchHistory(options) {
        const settings = Object.assign({ quiet: false }, options || {});
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
                        addMessage("File list refreshed", 'success');
                    }
                } else {
                    addMessage(response.msg || "Failed to refresh history", 'error');
                }
            },
            error: function(jqXHR) {
                addMessage(getAjaxErrorMessage(jqXHR, "Failed to refresh history"), 'error');
            }
        });
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
                        addMessage("History rows cleared. Downloaded files were kept and reloaded.", 'warning');
                    }
                } else {
                    addMessage(response.msg || "Failed to clear history", 'error');
                }
            },
            error: function(jqXHR) {
                addMessage(getAjaxErrorMessage(jqXHR, "Error occurred while clearing history"), 'error');
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
                        addMessage("History item deleted. File was kept.", 'info');
                    }
                } else {
                    addMessage(response.msg || "Failed to delete history item", 'error');
                }
            },
            error: function(jqXHR) {
                addMessage(getAjaxErrorMessage(jqXHR, "Error occurred while deleting history"), 'error');
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
                        addMessage("File and related history deleted", 'warning');
                    }
                } else {
                    addMessage(response.msg || "Failed to delete file", 'error');
                }
            },
            error: function(jqXHR) {
                addMessage(getAjaxErrorMessage(jqXHR, "Error occurred while deleting file"), 'error');
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
                    addMessage("Retry request submitted successfully", 'success');
                } else {
                    addMessage(response.msg || "Failed to retry download", 'error');
                }
            },
            error: function(jqXHR) {
                addMessage(getAjaxErrorMessage(jqXHR, "Error occurred while retrying download"), 'error');
            }
        });
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
        console.log("Selected resolution:", data.resolution);

        if (!data.url) {
            addMessage("Please enter a URL", 'warning');
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
                $('#progress-container').show();
                updateProgress(0);
                currentVideoTitle = '';
                currentChannel = '';
                fetchStatus();
                addMessage("Download request submitted successfully", 'success');
            },
            error: function(jqXHR, textStatus, errorThrown) {
                console.log("AJAX error - textStatus:", textStatus);
                console.log("AJAX error - errorThrown:", errorThrown);
                addMessage(getAjaxErrorMessage(jqXHR, "Request failed: " + textStatus), 'error');
            }
        });

        $('#url').val('').focus();
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

    $(document).on("change", "#selResolution", function() {
        syncModeFromResolution();
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
        renderHistory();
        renderDetailDrawer(null);
    });

    $(document).on("click", "#refresh-history", function() {
        fetchHistory();
    });

    $(document).on("click", "#clear-history", function() {
        showConfirmModal(
            "Clear History Rows",
            "Clear saved history rows? Files in /downfolder will be kept and shown again as mounted files.",
            clearAllHistory,
            "Clear Rows"
        );
    });

    $(document).on("click", ".action-history-delete", function(event) {
        event.stopPropagation();
        const uuid = $(this).data('uuid');
        const item = historyItems.find((historyItem) => historyItem.uuid === uuid);
        const title = item ? item.title : 'this item';

        showConfirmModal(
            "Delete History Item",
            `Delete the history row for "${title.substring(0, 50)}"? The file will be kept.`,
            function() {
                deleteHistoryItem(uuid);
            },
            "Delete History"
        );
    });

    $(document).on("click", ".action-file-delete", function(event) {
        event.stopPropagation();
        const uuid = $(this).data('uuid');
        const item = historyItems.find((historyItem) => historyItem.uuid === uuid);
        const title = item ? item.title : 'this file';
        const mountedFile = item && isMountedFile(item);
        const message = mountedFile ?
            `Delete the physical file for "${title.substring(0, 50)}"? This mounted file has no saved history row.` :
            `Delete the physical file for "${title.substring(0, 50)}" and remove related history rows?`;

        showConfirmModal(
            "Delete File",
            message,
            function() {
                deleteHistoryFile(uuid);
            },
            "Delete File"
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
        if (event.key === 'Escape' && $('.media-preview-modal').length) {
            closeMediaPreview();
        }
        if (event.key === 'Escape' && $('.subtitle-qa-modal').length) {
            closeSubtitleQa();
        }
    });

    applyHistoryPrefsToControls();
    syncModeFromResolution();
    restoreLocalState();
    renderHistory();
    startStatusPolling();
    connectWebSocket();
});
