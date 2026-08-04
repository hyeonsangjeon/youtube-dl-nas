<!DOCTYPE html>
<html lang="{{locale}}">
<head>
    <meta charset="utf-8">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <!-- The above 3 meta tags *must* come first in the head; any other head content must come *after* these tags -->
    <meta name="description" content="{{t('login.meta_description')}}">
    <meta name="theme-color" content="#168a92">
    <meta name="author" content="">
    <link rel="manifest" href="/manifest.webmanifest">
    <link rel="icon" href="/youtube-dl/static/pwa/icon-192.png">
    <link rel="apple-touch-icon" href="/youtube-dl/static/pwa/icon-192.png">
    <title>{{t('login.title')}}</title>
    <!-- Bootstrap core CSS -->
    <link href="youtube-dl/static/css/bootstrap.min.css" rel="stylesheet">
    <!-- Custom styles for this template -->
    <link href="youtube-dl/static/css/signin.css?v={{app_version}}" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css?family=Roboto:400,500&display=swap" rel="stylesheet">
    <script src="https://ajax.googleapis.com/ajax/libs/jquery/2.1.4/jquery.min.js"></script>
    <script src="youtube-dl/static/logical_js/logic.js?v={{app_version}}"></script>
</head>
<body>
<div class="container">
    <form class="locale-form locale-form-login" action="/locale" method="POST">
        <input type="hidden" name="next" value="{{locale_next}}">
        <label for="locale-selector" class="sr-only">{{t('common.language')}}</label>
        <span class="locale-icon" aria-hidden="true">&#127760;</span>
        <select id="locale-selector" name="locale" aria-label="{{t('common.language')}}" onchange="this.form.submit()">
        % for locale_code, locale_name in locale_options:
            <option value="{{locale_code}}"{{!' selected' if locale_code == locale else ''}}>{{locale_name}}</option>
        % end
        </select>
    </form>
    <form action="/login" class="form-signin" method="POST">
        <input type="hidden" name="next" value="{{next_path}}">
        <h2 class="form-signin-heading">{{t('login.heading')}}</h2>
        <label for="id" class="sr-only">{{t('login.id')}}</label>
        <input type="text" id="id" name="id" class="form-control" placeholder="{{t('login.id_placeholder')}}" required autofocus>
        <label for="myPw" class="sr-only">{{t('login.password')}}</label>
        <input type="password" id="myPw" name="myPw" class="form-control" placeholder="{{t('login.password_placeholder')}}" required>
        % if msg_key != '':
            <label>
                <p>{{t(msg_key)}}</p>
            </label>
        %end
        <button type="submit" class="btn btn-lg btn-primary btn-block" id="loginBtn">{{t('login.submit')}}</button>
    </form>
    <p class="text-center">{{t('common.version', version=app_version)}}</p>
</div> <!-- /container -->
<!-- IE10 viewport hack for Surface/desktop Windows 8 bug -->
<script src="youtube-dl/static/js/ie10-viewport-bug-workaround.js"></script>
</body>
</html>
