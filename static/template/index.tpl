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
                <h1 class="cover-heading">Let's Download </h1>
                <p class="lead">Url can be download from YouTube or <a href="https://rg3.github.io/youtube-dl/supportedsites.html">any other supported site</a>. The downloading state is passed to the server side event web socket.</p>

                <p class="lead">Welcome {{userNm}}</p>

                <div class="row">
                    <form id="form1" action="/youtube-dl/q" method="POST">
                        <div class="input-group">
                            {*<input name="url" id="url" type="url" class="form-control" placeholder="URL" value="https://www.youtube.com/watch?v=uMdgjd4x6wo">*}
                            <input name="url" id="url" type="url" class="form-control" placeholder="URL" >
                            <span class="input-group-btn">
                                <a href="#" id ="send" class="btn btn-primary" >
                                  <span class="glyphicon glyphicon-share-alt"  aria-hidden="true"></span> Submit
                                </a>
                            </span>
                        </div>

                    </form>
                </div>
            </div>
            <p class"lead"><div id="messages"></div></p>
            <div class="mastfoot">
                <div class="inner">
                    <p>Web frontend for <a href="https://github.com/hyeonsangjeon/youtube-dl-nas">youtube-dl-nas</a>, by @Hyeon Sang</a>.</p>
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
