
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <!-- The above 3 meta tags *must* come first in the head; any other head content must come *after* these tags -->
    <meta name="description" content="">
    <meta name="author" content="">
    <link rel="icon" href="../../favicon.ico">
    <title>Signin Template for Bootstrap</title>
    <!-- Bootstrap core CSS -->
    <link href="youtube-dl/static/css/bootstrap.min.css" rel="stylesheet">

    <!-- Custom styles for this template -->
    <link href="youtube-dl/static/css/signin.css" rel="stylesheet">
    <script src="https://ajax.googleapis.com/ajax/libs/jquery/2.1.4/jquery.min.js"></script>

    <script src="http://cdn.jsdelivr.net/sockjs/0.3/sockjs.min.js"></script>
    <script src="youtube-dl/static/logical_js/logic.js"></script>
</head>

<body>

<div class="container">

    <form action="/login" class="form-signin" method="POST">
        <input type="hidden" class="form-control" id="testVal" name="testVal" value="1234141414321">
        <h2 class="form-signin-heading">Youtube-dl sign in</h2>
        <label for="id" class="sr-only">id</label>
        <input type="username" id="id" name="id" class="form-control" placeholder="id" required autofocus>
        <label for="myPw" class="sr-only">Password</label>
        <input type="password" id="myPw" name="myPw" class="form-control" placeholder="Password" required>
        % if msg is not '':
            <label>
                <p> {{msg}} </p>
            </label>
        %end
        <!--<button class="btn btn-lg btn-primary btn-block" id="loginBtn" type="submit">Sign in</button>-->
        <button class="btn btn-lg btn-primary btn-block" id="loginBtn" >Sign in</button>
    </form>
    <p class="text-center">latest Ver 2.0219</p>

</div> <!-- /container -->



<!-- IE10 viewport hack for Surface/desktop Windows 8 bug -->
<script src="youtube-dl/static/js/ie10-viewport-bug-workaround.js"></script>
</body>
</html>
