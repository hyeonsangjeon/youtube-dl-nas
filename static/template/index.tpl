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
                
                <p class="lead">                    
                    <a href="https://rg3.github.io/youtube-dl/supportedsites.html">any other supported site</a>.<br>
                </p>

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
                                </select>
                            </span>
                            <input name="url" id="url" type="url" class="form-control" placeholder="URL">
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
                            <button id="clear-all-history" class="btn btn-danger btn-sm">
                                <span class="glyphicon glyphicon-trash" aria-hidden="true"></span> Clear All
                            </button>
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
                    <p>
                        Web frontend for <a href="https://github.com/hyeonsangjeon/youtube-dl-nas">youtube-dl-nas</a>, by @Hyeon Sang.
                    </p>
                    <p>latest Ver 25.0613</p>
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
