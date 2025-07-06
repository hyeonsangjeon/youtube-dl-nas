<!DOCTYPE html>
<html lang="en">

<head>
    <meta charset="utf-8">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <meta name="viewport" content="width=device-width, initial-scale=1">

    <meta name="description" content="">
    <meta name="author" content="">
    <link rel="icon" href="../../favicon.ico">

    <title>youtube-dl</title>

    <link href="https://maxcdn.bootstrapcdn.com/bootstrap/3.3.5/css/bootstrap.min.css" rel="stylesheet">
    <link href="youtube-dl/static/css/style.css" rel="stylesheet">
</head>

<body>

<div class="site-wrapper">
    <div class="site-wrapper-inner">
        <div class="cover-container">

            <div class="inner cover">
                <h1 class="cover-heading">Let's Download</h1>
                
                <!-- Place the thumbnail container at the same level as the cover heading -->
                <div id="thumbnail-container" style="display: none;">
                    <div class="thumbnail-wrapper">
                        <img id="video-thumbnail" src="" alt="Video Thumbnail">
                        <div id="video-info">
                            <h4 id="video-title-display"></h4>
                            <p id="video-channel-display"></p>
                        </div>
                    </div>
                </div>
                
              

                <p class="lead">Welcome {{userNm}}</p
                
                <div class="row">
                    <form id="form1">
                        <div class="input-group">
                            <span class="input-group-btn">
                                <select title="Pick a resolution" id="selResolution" class="form-control" style="width:100px;">
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
                            </span>
                            <input name="url" id="url" type="url" class="form-control" placeholder="URL">
                            <!-- 자막 언어 선택 박스 (처음에는 숨김) -->
                            <span class="input-group-btn" id="subtitleLanguageContainer" style="display: none;">
                                <select title="Pick a subtitle language" id="selSubtitleLanguage" class="form-control" style="width:120px;">                                    
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
                            </span>
                            <span class="input-group-btn">
                                <button id="send" class="btn btn-primary">
                                    <span class="glyphicon glyphicon-share-alt" aria-hidden="true"></span> Submit
                                </button>
                            </span>
                        </div>
                    </form>
                </div>
            </div>

            <p class="lead"><div id="messages"></div></p>
            
            <!-- Add progress bar -->
            <div id="progress-container" style="display: none;">
                <div class="progress">
                    <div id="progress-bar" class="progress-bar progress-bar-striped active" role="progressbar" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100" style="width: 0%">
                        <span id="progress-text">0%</span>
                    </div>
                </div>
            </div>
            
            <p class="lead"><div id="queue"></div></p>

            <!-- Improved History Table Section -->
            <div class="table-responsive" style="overflow: visible;">
                <div class="download-history">
                    <div class="history-header">
                        <h3 class="history-title">Download History</h3>
                        <div class="history-controls">
                            <button id="refresh-history" class="btn btn-info btn-sm">
                                <span class="glyphicon glyphicon-refresh" aria-hidden="true"></span> Refresh
                            </button>
                        </div>
                    </div>
                    <div class="table-container">
                        <table class="table table-modern">
                            <thead>
                                <tr>
                                    <th class="col-resolution">Quality</th>
                                    <th class="col-channel">Channel</th>
                                    <th class="col-title">Video Title</th>
                                    <th class="col-actions">Actions</th>
                                </tr>
                            </thead>
                            <tbody id="completeInfo">
                                <!-- Download history items will be dynamically added here -->
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            <div class="mastfoot">
                <div class="inner">
                  <p class="lead">                    
                    <a href="https://rg3.github.io/youtube-dl/supportedsites.html">any other supported site</a>.<br>
                  </p>
                    <p>
                        Web frontend for <a href="https://github.com/hyeonsangjeon/youtube-dl-nas">youtube-dl-nas</a>, by @Hyeonsang Jeon.
                    </p>
                    <p>latest Ver 25.0706</p>
                    <a href="https://www.youtube.com/watch?v=s9mO5q6GiAc">Watch Demo</a>
                </div>
            </div>

        </div>
    </div>
</div>

<script src="https://ajax.googleapis.com/ajax/libs/jquery/2.1.4/jquery.min.js"></script>
<script src="https://maxcdn.bootstrapcdn.com/bootstrap/3.3.5/js/bootstrap.min.js"></script>
<script src="youtube-dl/static/logical_js/logic.js"></script>
</body>

</html>
