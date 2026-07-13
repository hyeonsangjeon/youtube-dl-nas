<!DOCTYPE html>
<html lang="en">

<head>
    <meta charset="utf-8">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <meta name="viewport" content="width=device-width, initial-scale=1">

    <meta name="description" content="Send video, audio, and subtitle URLs to a private NAS download queue.">
    <meta name="theme-color" content="#168a92">
    <meta name="author" content="">
    <link rel="manifest" href="/manifest.webmanifest">
    <link rel="icon" href="/youtube-dl/static/pwa/icon-192.png">
    <link rel="apple-touch-icon" href="/youtube-dl/static/pwa/icon-192.png">

    <title>youtube-dl NAS</title>

    <link href="https://maxcdn.bootstrapcdn.com/bootstrap/3.3.5/css/bootstrap.min.css" rel="stylesheet">
    <link href="youtube-dl/static/css/style.css?v={{app_version}}" rel="stylesheet">
</head>

<body class="dashboard-page">

<div class="site-wrapper">
    <div class="site-wrapper-inner">
        <div class="cover-container">

            <header class="app-header">
                <div>
                    <h1 class="app-title">youtube-dl NAS</h1>
                    <p class="app-subtitle">Download queue and history manager</p>
                </div>
                <div class="app-meta">
                    <span class="user-chip">
                        <span class="glyphicon glyphicon-user" aria-hidden="true"></span>
                        {{userNm}}
                    </span>
                    <span id="connection-status" class="connection-chip status-pending">Connecting</span>
                    <a class="logout-btn" href="/logout" title="Log out">
                        <span class="glyphicon glyphicon-log-out" aria-hidden="true"></span>
                        Logout
                    </a>
                </div>
            </header>

            <div class="dashboard-layout">
                <main class="dashboard-main">
                    <section class="panel download-composer">
                        <div class="panel-heading-row">
                            <div>
                                <h2>New Download</h2>
                                <p>Paste a URL, choose an output, and send it to the NAS queue.</p>
                            </div>
                        </div>

                        <form id="form1" class="download-form">
                            <div class="mode-tabs" role="tablist" aria-label="Download mode">
                                <button type="button" class="mode-tab active" data-download-mode="video">Video</button>
                                <button type="button" class="mode-tab" data-download-mode="audio">Audio</button>
                                <button type="button" class="mode-tab" data-download-mode="subtitle">Subtitle</button>
                            </div>
                            <div class="composer-grid">
                                <label class="form-field quality-field">
                                    <span>Quality</span>
                                    <select title="Pick a resolution" id="selResolution" class="form-control admin-control">
                                    <option>best</option>
                                    <option>2160p</option>
                                    <option>1440p</option>
                                    <option>1080p</option>
                                    <option>720p</option>
                                    <option>480p</option>
                                    <option>360p</option>
                                    <option>240p</option>
                                    <option>144p</option>
                                    <option>audio-m4a</option>
                                    <option>audio-mp3</option>
                                    <option>srt</option>
                                    <option>vtt</option>
                                    </select>
                                </label>
                                <label class="form-field url-field">
                                    <span>URL</span>
                                    <input name="url" id="url" type="url" class="form-control admin-control" placeholder="https://youtu.be/...">
                                </label>
                                <label class="form-field subtitle-field" id="subtitleLanguageContainer" style="display: none;">
                                    <span>Subtitle language</span>
                                    <select title="Pick a subtitle language" id="selSubtitleLanguage" class="form-control admin-control">
                                    <option value="en">English</option>
                                    <option value="ko">Korean</option>
                                    <option value="ja">Japanese</option>
                                    <option value="zh-Hans">Chinese (Simplified)</option>
                                    <option value="es">Spanish</option>
                                    <option value="fr">French</option>
                                    <option value="de">German</option>
                                    <option value="it">Italian</option>
                                    <option value="pt">Portuguese</option>
                                    <option value="ru">Russian</option>
                                    <option value="zh-Hant">Chinese (Traditional)</option>
                                    <option value="ar">Arabic</option>
                                    <option value="hi">Hindi</option>
                                    <option value="th">Thai</option>
                                    <option value="vi">Vietnamese</option>
                                    <option value="ab">Abkhazian</option>
                                    <option value="aa">Afar</option>
                                    <option value="af">Afrikaans</option>
                                    <option value="ak">Akan</option>
                                    <option value="sq">Albanian</option>
                                    <option value="am">Amharic</option>
                                    <option value="hy">Armenian</option>
                                    <option value="as">Assamese</option>
                                    <option value="ay">Aymara</option>
                                    <option value="az">Azerbaijani</option>
                                    <option value="bn">Bangla</option>
                                    <option value="ba">Bashkir</option>
                                    <option value="eu">Basque</option>
                                    <option value="be">Belarusian</option>
                                    <option value="bho">Bhojpuri</option>
                                    <option value="bs">Bosnian</option>
                                    <option value="br">Breton</option>
                                    <option value="bg">Bulgarian</option>
                                    <option value="my">Burmese</option>
                                    <option value="ca">Catalan</option>
                                    <option value="ceb">Cebuano</option>
                                    <option value="co">Corsican</option>
                                    <option value="hr">Croatian</option>
                                    <option value="cs">Czech</option>
                                    <option value="da">Danish</option>
                                    <option value="dv">Divehi</option>
                                    <option value="nl">Dutch</option>
                                    <option value="dz">Dzongkha</option>
                                    <option value="en-orig">English (Original)</option>
                                    <option value="eo">Esperanto</option>
                                    <option value="et">Estonian</option>
                                    <option value="ee">Ewe</option>
                                    <option value="fo">Faroese</option>
                                    <option value="fj">Fijian</option>
                                    <option value="fil">Filipino</option>
                                    <option value="fi">Finnish</option>
                                    <option value="gaa">Ga</option>
                                    <option value="gl">Galician</option>
                                    <option value="lg">Ganda</option>
                                    <option value="ka">Georgian</option>
                                    <option value="el">Greek</option>
                                    <option value="gn">Guarani</option>
                                    <option value="gu">Gujarati</option>
                                    <option value="ht">Haitian Creole</option>
                                    <option value="ha">Hausa</option>
                                    <option value="haw">Hawaiian</option>
                                    <option value="iw">Hebrew</option>
                                    <option value="hmn">Hmong</option>
                                    <option value="hu">Hungarian</option>
                                    <option value="is">Icelandic</option>
                                    <option value="ig">Igbo</option>
                                    <option value="id">Indonesian</option>
                                    <option value="iu">Inuktitut</option>
                                    <option value="ga">Irish</option>
                                    <option value="jv">Javanese</option>
                                    <option value="kl">Kalaallisut</option>
                                    <option value="kn">Kannada</option>
                                    <option value="kk">Kazakh</option>
                                    <option value="kha">Khasi</option>
                                    <option value="km">Khmer</option>
                                    <option value="rw">Kinyarwanda</option>
                                    <option value="kri">Krio</option>
                                    <option value="ku">Kurdish</option>
                                    <option value="ky">Kyrgyz</option>
                                    <option value="lo">Lao</option>
                                    <option value="la">Latin</option>
                                    <option value="lv">Latvian</option>
                                    <option value="ln">Lingala</option>
                                    <option value="lt">Lithuanian</option>
                                    <option value="lua">Luba-Lulua</option>
                                    <option value="luo">Luo</option>
                                    <option value="lb">Luxembourgish</option>
                                    <option value="mk">Macedonian</option>
                                    <option value="mg">Malagasy</option>
                                    <option value="ms">Malay</option>
                                    <option value="ml">Malayalam</option>
                                    <option value="mt">Maltese</option>
                                    <option value="gv">Manx</option>
                                    <option value="mi">Māori</option>
                                    <option value="mr">Marathi</option>
                                    <option value="mn">Mongolian</option>
                                    <option value="mfe">Morisyen</option>
                                    <option value="ne">Nepali</option>
                                    <option value="new">Newari</option>
                                    <option value="nso">Northern Sotho</option>
                                    <option value="no">Norwegian</option>
                                    <option value="ny">Nyanja</option>
                                    <option value="oc">Occitan</option>
                                    <option value="or">Odia</option>
                                    <option value="om">Oromo</option>
                                    <option value="os">Ossetic</option>
                                    <option value="pam">Pampanga</option>
                                    <option value="ps">Pashto</option>
                                    <option value="fa">Persian</option>
                                    <option value="pl">Polish</option>
                                    <option value="pt-PT">Portuguese (Portugal)</option>
                                    <option value="pa">Punjabi</option>
                                    <option value="qu">Quechua</option>
                                    <option value="ro">Romanian</option>
                                    <option value="rn">Rundi</option>
                                    <option value="sm">Samoan</option>
                                    <option value="sg">Sango</option>
                                    <option value="sa">Sanskrit</option>
                                    <option value="gd">Scottish Gaelic</option>
                                    <option value="sr">Serbian</option>
                                    <option value="crs">Seselwa Creole French</option>
                                    <option value="sn">Shona</option>
                                    <option value="sd">Sindhi</option>
                                    <option value="si">Sinhala</option>
                                    <option value="sk">Slovak</option>
                                    <option value="sl">Slovenian</option>
                                    <option value="so">Somali</option>
                                    <option value="st">Southern Sotho</option>
                                    <option value="su">Sundanese</option>
                                    <option value="sw">Swahili</option>
                                    <option value="ss">Swati</option>
                                    <option value="sv">Swedish</option>
                                    <option value="tg">Tajik</option>
                                    <option value="ta">Tamil</option>
                                    <option value="tt">Tatar</option>
                                    <option value="te">Telugu</option>
                                    <option value="bo">Tibetan</option>
                                    <option value="ti">Tigrinya</option>
                                    <option value="to">Tongan</option>
                                    <option value="ts">Tsonga</option>
                                    <option value="tn">Tswana</option>
                                    <option value="tum">Tumbuka</option>
                                    <option value="tr">Turkish</option>
                                    <option value="tk">Turkmen</option>
                                    <option value="uk">Ukrainian</option>
                                    <option value="ur">Urdu</option>
                                    <option value="ug">Uyghur</option>
                                    <option value="uz">Uzbek</option>
                                    <option value="ve">Venda</option>
                                    <option value="war">Waray</option>
                                    <option value="cy">Welsh</option>
                                    <option value="fy">Western Frisian</option>
                                    <option value="wo">Wolof</option>
                                    <option value="xh">Xhosa</option>
                                    <option value="yi">Yiddish</option>
                                    <option value="yo">Yoruba</option>
                                    <option value="zu">Zulu</option>
                                    </select>
                                </label>
                                <button id="send" type="submit" class="btn btn-primary submit-btn">
                                    <span class="glyphicon glyphicon-share-alt" aria-hidden="true"></span>
                                    Submit
                                </button>
                            </div>
                        </form>

                        <div id="thumbnail-container" class="download-preview" style="display: none;">
                            <img id="video-thumbnail" src="" alt="Video thumbnail">
                            <div>
                                <h4 id="video-title-display"></h4>
                                <p id="video-channel-display"></p>
                            </div>
                        </div>
                    </section>

                    <section class="panel activity-panel">
                        <div class="panel-heading-row">
                            <div>
                                <h2>Current Activity</h2>
                                <p id="activity-summary">No active download</p>
                            </div>
                            <span id="queue-count" class="metric-pill">Queue 0</span>
                        </div>
                        <div class="activity-content">
                            <div class="activity-thumbnail">
                                <img id="activity-thumbnail-image" src="" alt="" style="display: none;">
                                <span id="activity-thumbnail-placeholder" class="glyphicon glyphicon-facetime-video" aria-hidden="true"></span>
                            </div>
                            <div class="activity-main">
                                <div class="activity-title-row">
                                    <strong id="activity-title">Idle</strong>
                                    <span id="activity-status" class="status-tag status-pending">idle</span>
                                </div>
                                <p id="activity-channel">Waiting for the next request.</p>
                                <div id="activity-transfer" class="activity-transfer" hidden>
                                    <span id="activity-speed">--</span>
                                    <span id="activity-eta">ETA --</span>
                                </div>
                                <div id="progress-container" class="progress-shell" style="display: none;">
                                    <div class="progress">
                                        <div id="progress-bar" class="progress-bar progress-bar-striped active" role="progressbar" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100" style="width: 0%">
                                            <span id="progress-text">0%</span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div class="queue-section">
                            <div class="queue-section-heading">
                                <strong>Up next</strong>
                                <span id="queue-summary">Queue is empty</span>
                            </div>
                            <div id="queue-items" class="queue-items">
                                <div class="queue-empty">New requests will appear here in order.</div>
                            </div>
                        </div>
                    </section>

                    <div id="messages" class="message-stack"></div>
                    <div id="queue" class="sr-only"></div>

                    <section class="panel download-history">
                        <div class="history-header">
                            <div>
                                <h2 class="history-title">Files & History</h2>
                                <p id="history-result-count" class="history-subtitle">0 downloads</p>
                            </div>
                            <div class="history-actions">
                                <div class="history-view-switch" role="group" aria-label="History view">
                                    <button id="history-view-list" type="button" class="history-view-btn is-active" data-history-view="list" title="List view" aria-pressed="true">
                                        <span class="glyphicon glyphicon-list" aria-hidden="true"></span>
                                        <span>List</span>
                                    </button>
                                    <button id="history-view-grid" type="button" class="history-view-btn" data-history-view="grid" title="Grid view" aria-pressed="false">
                                        <span class="glyphicon glyphicon-th-large" aria-hidden="true"></span>
                                        <span>Grid</span>
                                    </button>
                                </div>
                                <button id="refresh-history" class="btn btn-info btn-sm">
                                    <span class="glyphicon glyphicon-refresh" aria-hidden="true"></span> Refresh
                                </button>
                                <button id="clear-history" class="btn btn-default btn-sm">
                                    <span class="glyphicon glyphicon-list-alt" aria-hidden="true"></span> Clear Rows
                                </button>
                            </div>
                        </div>
                        <div class="history-controls">
                            <div class="history-search-group">
                                <input id="history-search" class="form-control input-sm history-search" type="search" placeholder="Search title, channel, filename, or metadata">
                                <button id="history-search-button" class="btn btn-info btn-sm history-search-button" type="button">
                                    <span class="glyphicon glyphicon-search" aria-hidden="true"></span> Search
                                </button>
                            </div>
                            <select id="history-sort" class="form-control input-sm history-select" title="Sort downloads">
                                <option value="date-desc">Newest first</option>
                                <option value="date-asc">Oldest first</option>
                                <option value="title-asc">Title A-Z</option>
                                <option value="title-desc">Title Z-A</option>
                                <option value="channel-asc">Channel A-Z</option>
                                <option value="channel-desc">Channel Z-A</option>
                                <option value="quality-asc">Quality A-Z</option>
                                <option value="quality-desc">Quality Z-A</option>
                                <option value="status-asc">Status A-Z</option>
                                <option value="status-desc">Status Z-A</option>
                            </select>
                            <select id="history-status-filter" class="form-control input-sm history-select" title="Filter by status">
                                <option value="all">All statuses</option>
                                <option value="completed">Completed</option>
                                <option value="file_only">Mounted files</option>
                                <option value="failed">Failed</option>
                                <option value="error">Error</option>
                                <option value="unknown">Unknown</option>
                            </select>
                            <div class="history-type-switch" role="group" aria-label="Filter by type">
                                <button type="button" class="history-type-option is-active" data-history-type="all">All</button>
                                <button type="button" class="history-type-option" data-history-type="video">
                                    <span class="glyphicon glyphicon-facetime-video" aria-hidden="true"></span><span>Video</span>
                                </button>
                                <button type="button" class="history-type-option" data-history-type="audio">
                                    <span class="glyphicon glyphicon-music" aria-hidden="true"></span><span>Audio</span>
                                </button>
                                <button type="button" class="history-type-option" data-history-type="subtitle">
                                    <span class="glyphicon glyphicon-subtitles" aria-hidden="true"></span><span>Subs</span>
                                </button>
                                <button type="button" class="history-type-option" data-history-type="file">
                                    <span class="glyphicon glyphicon-file" aria-hidden="true"></span><span>Files</span>
                                </button>
                            </div>
                            <button id="reset-history-filters" class="btn btn-default btn-sm">Reset</button>
                        </div>
                        <div class="table-responsive">
                            <div class="table-container">
                                <table class="table table-modern">
                                    <thead>
                                        <tr>
                                            <th class="col-downloaded">Downloaded</th>
                                            <th class="col-resolution">Type / Quality</th>
                                            <th class="col-channel">Channel</th>
                                            <th class="col-title">Video Title</th>
                                            <th class="col-status">Status</th>
                                            <th class="col-size">Size</th>
                                            <th class="col-actions">Actions</th>
                                        </tr>
                                    </thead>
                                    <tbody id="completeInfo">
                                        <!-- Download history items will be dynamically added here -->
                                    </tbody>
                                </table>
                            </div>
                        </div>
                        <div id="history-grid" class="history-grid"></div>
                        <div id="history-card-list" class="history-card-list"></div>
                        <div id="history-pager" class="history-pager"></div>
                    </section>
                </main>

                <aside id="history-detail-drawer" class="detail-drawer" aria-live="polite">
                    <div class="detail-empty">
                        <span class="glyphicon glyphicon-list-alt" aria-hidden="true"></span>
                        <h2>Select a download</h2>
                        <p>Open a history item to view URL, file details, and actions.</p>
                    </div>
                </aside>
            </div>

            <div class="mastfoot">
                <div class="inner">
                  <p class="lead">                    
                    <a href="https://rg3.github.io/youtube-dl/supportedsites.html">any other supported site</a>.<br>
                  </p>
                    <p>
                        Web frontend for <a href="https://github.com/hyeonsangjeon/youtube-dl-nas">youtube-dl-nas</a>, by @Hyeonsang Jeon.
                    </p>
                    <p>latest Ver {{app_version}}</p>
                    <a href="https://www.youtube.com/watch?v=s9mO5q6GiAc">Watch Demo</a>
                </div>
            </div>

        </div>
    </div>
</div>

<script src="https://ajax.googleapis.com/ajax/libs/jquery/2.1.4/jquery.min.js"></script>
<script src="https://maxcdn.bootstrapcdn.com/bootstrap/3.3.5/js/bootstrap.min.js"></script>
<script src="youtube-dl/static/logical_js/logic.js?v={{app_version}}"></script>
<script>
    if ('serviceWorker' in navigator) {
        window.addEventListener('load', function() {
            navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(function(error) {
                console.warn('PWA service worker registration failed:', error);
            });
        });
    }
</script>
</body>

</html>
