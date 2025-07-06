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
    let historyRestoreCount = 0;
    let isHistoryRestoring = false;
    let maxMessages = 5;
    let messageCleanupTimer = null;

    console.log("Document ready - initializing...");

    // Restore state from local storage
    restoreLocalState();
    
    // Add function to check if the current page is a login page
    function isLoginPage() {
        return $('.form-signin').length > 0 && $('#loginBtn').length > 0;
    }

    if(!thdYn){
        $(".table-responsive").hide();
    }

    // WebSocket connection and reconnection logic (using a single connection)
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
                
                messagesTxt("[MSG], WebSocket connection opened.");
                
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
                messagesTxt("[MSG], Connection lost. Reconnecting...");
                attemptReconnect();
            }

            wsEventBus.onerror = function(evt) {
                console.log("WebSocket error: ", evt);
                messagesTxt("[MSG], Connection error occurred.");
            }
        } catch (error) {
            console.error("WebSocket connection failed:", error);
            wsEventBus = null;
            attemptReconnect();
        }
    }

    function attemptReconnect() {
        if (reconnectAttempts >= maxReconnectAttempts) {
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

    // local storage save
    function saveLocalState() {
        const state = {
            downloadHistory: getDownloadHistory(),
            lastUpdate: Date.now()
        };
        localStorage.setItem('downloadState', JSON.stringify(state));
    }

    // local storage restore
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
        const history = [];
        $("#completeInfo tr").each(function() {
            const cells = $(this).find('td');
            if (cells.length >= 3) {
                history.push({
                    resolution: cells.eq(0).text().trim(),
                    channel: cells.eq(1).text().trim(),
                    title: cells.eq(2).text().trim(),
                    uuid: $(this).find('.action-delete').data('uuid') // uuid 추가
                });
            }
        });
        return history;
    }

    function restoreDownloadHistory(history) {
        if (history && history.length > 0) {
            $("#completeInfo").empty();
            history.forEach((item) => {
                addHistoryItemWithUuid(item.resolution, item.channel, item.title, item.uuid || generateUuid());
            });
            $(".table-responsive").show();
            thdYn = true;
        }
    }

    // UUID test
    function generateUuid() {
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
            var r = Math.random() * 16 | 0, v = c == 'x' ? r : (r & 0x3 | 0x8);
            return v.toString(16);
        });
    }

    function addHistoryItem(resolution, channel, title) {
        const uuid = generateUuid();
        addHistoryItemWithUuid(resolution, channel, title, uuid);
    }

    // initialize WebSocket connection
    connectWebSocket();

    // download request handler
    $(document).on("click","#send",function(){
        console.log("Send button clicked");
        
        clearMessages();
        
        var data = {};
        data.url = $("#url").val();
        
        
        subtitleLan = '';
        if ($("#selResolution").val() == 'vtt' || $("#selResolution").val() == 'srt') {
            subtitleLan = $("#selSubtitleLanguage").val();            
            data.resolution = `${$("#selResolution").val()}|${subtitleLan}`;
        }else{
            data.resolution = $("#selResolution").val();
        }
        console.log("Selected resolution:", data.resolution);
        

        if (!data.url) {
            addMessage("Please enter a URL", 'warning');
            return false;
        }

        console.log("Sending request with data:", data);

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
                addMessage("Download request submitted successfully", 'success');
            },
            error: function(jqXHR, textStatus, errorThrown) {
                console.log("AJAX error - textStatus:", textStatus);
                console.log("AJAX error - errorThrown:", errorThrown);
                console.log("AJAX error - response:", jqXHR.responseText);
                addMessage("Request failed: " + textStatus, 'error');
            }
        });

        $('#url').val('').focus();
        return false;
    });

    function updateProgress(percentage) {
        console.log("Updating progress to:", percentage);
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
        
        if (percentage >= 100) {
            setTimeout(function() {
                $('#progress-container').hide();
                updateProgress(0);
                currentVideoTitle = '';
                currentChannel = '';
                setTimeout(function() {
                    $('#thumbnail-container').hide();
                }, 2000);
            }, 3000);
        }
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
                ${message}
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
                    console.log("Starting history restoration...");
                    $("#completeInfo").empty();
                }
                
                const historyData = JSON.parse(messageContent);
                console.log("Restoring history item:", historyData);
                
                const resolution = historyData.resolution || "";
                const channel = historyData.channel || "";
                const title = historyData.title || "";
                const uuid = historyData.uuid; // server side uuid  
                const filepath = historyData.filepath || "";
                const filename = historyData.filename || "";
                
            
                if (uuid) {
                    console.log(`Restoring history item with UUID: ${uuid}`);
                    addHistoryItemWithUuid(resolution, channel, title, uuid, filepath, filename);
                    historyRestoreCount++;
                } else {
                    console.warn("No UUID found in history data:", historyData);
                }
                
            } catch (e) {
                console.error("Error parsing history data:", e, "Raw content:", messageContent);
            }
            
        } else if (messageType === "[HISTORY_RESTORE_COMPLETE]") {
            console.log(`History restoration completed. Restored ${historyRestoreCount} items.`);
            isHistoryRestoring = false;
            
            $('.empty-state').remove();
            
            if (historyRestoreCount === 0) {
                $("#completeInfo").html('<tr><td colspan="4" class="empty-state">No downloads yet<br><small>Start downloading to see history here</small></td></tr>');
            } else {
                console.log(`Successfully displayed ${historyRestoreCount} history items`);
                $(".table-responsive").show();
                thdYn = true;
                saveLocalState();
            }
            
        } else if (messageType === "[HISTORY_CLEARED]") {
            $("#completeInfo").html('<tr><td colspan="4" class="empty-state">No downloads yet<br><small>Start downloading to see history here</small></td></tr>');
            saveLocalState();
            addMessage("All download history cleared", 'warning');
            
        } else if (messageType === "[HISTORY_DELETED]") {
            const deletedUuid = messageContent; 
            $(`[data-uuid="${deletedUuid}"]`).closest('tr').fadeOut(300, function() {
                $(this).remove();
                saveLocalState();
                
                if ($("#completeInfo tr").length === 0) {
                    $("#completeInfo").html('<tr><td colspan="4" class="empty-state">No downloads yet<br><small>Start downloading to see history here</small></td></tr>');
                }
            });
            addMessage("Download history item deleted", 'info');
            
        } else if (messageType === "[COMPLETE]") {
            console.log("Complete message received");
            try {
                // JSON 파싱으로 변경
                const completeData = JSON.parse(messageContent);
                
                const resolution = completeData.resolution || "";
                const channel = completeData.channel || "";
                const title = completeData.title || "";
                const filepath = completeData.filepath || "";
                const filename = completeData.filename || "";
                const uuid = completeData.uuid || "";
                
                console.log("Parsed complete data:", completeData);
                
                addHistoryItemWithUuid(resolution, channel, title, uuid, filepath, filename);
                
                $(".table-responsive").show();
                thdYn = true;
                saveLocalState();
                
                const displayTitle = title.length > 50 ? title.substring(0, 50) + '...' : title;
                addMessage(`✅ Download completed: ${displayTitle}`, 'success');
                
            } catch (e) {
                console.error("Error parsing complete message:", e, "Raw content:", messageContent);
                addMessage("Error processing download completion", 'error');
            }
        } else if (messageType === "[RESTORE_ACTIVE]") {
            try {
                const activeData = JSON.parse(messageContent);
                console.log("Restoring active download:", activeData);
                
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
                    $('#thumbnail-container').show();
                }
                
                if (activeData.progress > 0 && activeData.progress < 100) {
                    const displayTitle = activeData.title && activeData.title.length > 30 ? 
                                       activeData.title.substring(0, 30) + '...' : activeData.title;
                    addMessage(`🔄 Resuming download: ${displayTitle} (${Math.round(activeData.progress)}%)`, 'info');
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
            $('#video-title-display').text(title);
            
        } else if (messageType === "[CHANNEL]") {
            const channel = messageContent;
            currentChannel = channel;
            $('#video-channel-display').text(channel);
            
        } else if (messageType === "[THUMBNAIL]") {
            const thumbnail = messageContent;
            $('#video-thumbnail').attr('src', thumbnail);
            $('#thumbnail-container').show();
        }
    }


    function addHistoryItemWithUuid(resolution, channel, title, uuid, filepath, filename) {
        console.log(`Adding history item: ${uuid} - ${title} (${filepath})`);
        
        const resolutionClass = getResolutionClass(resolution);
        const safeTitle = title ? title.replace(/"/g, '&quot;') : '';
        const safeChannel = channel ? channel.replace(/"/g, '&quot;') : '';
        
        let downloadUrl = '';

        downloadUrl = `/static/downfolder/${uuid}`;
        console.log(`Download URL set to: ${downloadUrl}`);

        const titleElement = downloadUrl ?
            `<a href="${downloadUrl}" download class="video-title" title="${safeTitle}">${safeTitle}</a>` :
            `<span class="video-title" title="${safeTitle}">${safeTitle}</span>`;
        
        const newRow = `
            <tr>
                <td><span class="resolution-tag ${resolutionClass}">${resolution}</span></td>
                <td><span class="channel-name" title="${safeChannel}">${safeChannel}</span></td>
                <td>${titleElement}</td>
                <td>
                    <button class="action-delete" data-uuid="${uuid}" title="Delete this item">
                        <span class="glyphicon glyphicon-trash"></span>
                    </button>
                </td>
            </tr>
        `;
        
        $('.empty-state').remove();
        
        if (isHistoryRestoring) {
            $("#completeInfo").append(newRow);
        } else {
            $("#completeInfo").prepend(newRow);
        }
        
        console.log(`History item added successfully: ${title}`);
    }

    function getResolutionClass(resolution) {
        if (resolution.includes('best') || resolution.includes('1080') || resolution.includes('4K')) {
            return 'resolution-high';
        } else if (resolution.includes('720')) {
            return 'resolution-medium';
        } else if (resolution.includes('audio')) {
            return 'resolution-audio';
        } else {
            return 'resolution-low';
        }
    }

    // for delete content
    function showConfirmModal(title, message, onConfirm) {
        $('.confirm-modal').remove();
        
        const modal = $(`
            <div class="confirm-modal" style="position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); display: flex; justify-content: center; align-items: center; z-index: 1000;">
                <div class="confirm-content" style="background: white; padding: 30px; border-radius: 12px; text-align: center; max-width: 400px;">
                    <h4>${title}</h4>
                    <p>${message}</p>
                    <div class="confirm-buttons" style="display: flex; gap: 15px; justify-content: center;">
                        <button class="btn btn-default confirm-cancel">Cancel</button>
                        <button class="btn btn-danger confirm-ok">Delete</button>
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

    // function clearAllHistory() {
    //     $.ajax({
    //         method: "POST",
    //         url: "/youtube-dl/history/clear",
    //         success: function(response) {
    //             if (response.success) {
    //                 $("#completeInfo").html('<tr><td colspan="4" class="empty-state">No downloads yet<br><small>Start downloading to see history here</small></td></tr>');
    //                 saveLocalState();
    //                 console.log("All history cleared successfully");
    //             } else {
    //                 console.error("Failed to clear history:", response.msg);
    //             }
    //         },
    //         error: function() {
    //             console.error("Error occurred while clearing history");
    //         }
    //     });
    // }

    function deleteHistoryItem(uuid) {

        $.ajax({
            method: "POST",
            url: `/youtube-dl/history/delete/${uuid}`, 
            success: function(response) {
                if (response.success) {
                    $(`[data-uuid="${uuid}"]`).closest('tr').fadeOut(300, function() {
                        $(this).remove();
                        saveLocalState();
                        
                        if ($("#completeInfo tr").length === 0) {
                            $("#completeInfo").html('<tr><td colspan="4" class="empty-state">No downloads yet<br><small>Start downloading to see history here</small></td></tr>');
                        }
                    });
                    console.log("History item deleted successfully");
                } else {
                    console.error("Failed to delete history item:", response.msg);
                }
            },
            error: function() {
                console.error("Error occurred while deleting history item");
            }
        });
    }

    // event handler
    // $(document).on("click", "#clear-all-history", function() {
    //     showConfirmModal(
    //         "Clear All History", 
    //         "Are you sure you want to delete all download history? This action cannot be undone.",
    //         function() {
    //             clearAllHistory();
    //         }
    //     );
    // });

    $(document).on("click", "#refresh-history", function() {
        if (wsEventBus && wsEventBus.readyState === WebSocket.OPEN) {
            console.log("Refreshing history...");
            $("#completeInfo").empty();
            historyRestoreCount = 0;
            isHistoryRestoring = false;
            wsEventBus.send('[REQUEST_HISTORY]');
        }
    });

    $(document).on("click", ".action-delete", function() {
        const uuid = $(this).data('uuid'); 
        const title = $(this).closest('tr').find('.video-title').text().trim();
        
        showConfirmModal(
            "Delete History Item", 
            `Are you sure you want to delete "${title.substring(0, 50)}..."?`,
            function() {
                deleteHistoryItem(uuid); 
            }
        );
    });

    // message payload empty
    if ($("#completeInfo").children().length === 0) {
        $("#completeInfo").html('<tr><td colspan="4" class="empty-state">No downloads yet<br><small>Start downloading to see history here</small></td></tr>');
    }
});
