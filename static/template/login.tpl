<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <!-- The above 3 meta tags *must* come first in the head; any other head content must come *after* these tags -->
    <meta name="description" content="Sign in to the youtube-dl-nas download queue">
    <meta name="theme-color" content="#168a92">
    <meta name="author" content="">
    <link rel="manifest" href="/manifest.webmanifest">
    <link rel="icon" href="/youtube-dl/static/pwa/icon-192.png">
    <link rel="apple-touch-icon" href="/youtube-dl/static/pwa/icon-192.png">
    <title>Sign in - youtube-dl-nas</title>
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
    <form action="/login" class="form-signin" method="POST">
        <input type="hidden" name="next" value="{{next_path}}">
        <h2 class="form-signin-heading">Welcome Back</h2>
        <label for="id" class="sr-only">ID</label>
        <input type="text" id="id" name="id" class="form-control" placeholder="Enter your ID" required autofocus>
        <label for="myPw" class="sr-only">Password</label>
        <input type="password" id="myPw" name="myPw" class="form-control" placeholder="Enter your Password" required>
        % if msg != '':
            <label>
                <p>{{msg}}</p>
            </label>
        %end
        <button class="btn btn-lg btn-primary btn-block" id="loginBtn">Sign in</button>
    </form>
    <p class="text-center">Version {{app_version}}</p>
</div> <!-- /container -->
<!-- IE10 viewport hack for Surface/desktop Windows 8 bug -->
<script src="youtube-dl/static/js/ie10-viewport-bug-workaround.js"></script>
</body>
</html>
