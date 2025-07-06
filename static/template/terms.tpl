<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Terms of Use - youtube-dl-nas</title>
    <link href="https://maxcdn.bootstrapcdn.com/bootstrap/3.3.5/css/bootstrap.min.css" rel="stylesheet">
    <link href="youtube-dl/static/css/style.css" rel="stylesheet">
    
    
</head>
<body>
        <div class="site-wrapper">
        <div class="site-wrapper-inner">
            <div class="terms-container">
                <div class="terms-header">
                    <h2>Terms of Use</h2>
                    <p>Please read and accept the following terms before using this application</p>
                </div>
                
                <div class="terms-content">
                    <div class="copyright-disclaimer">
                        <h4>Important Notice</h4>
                        <p>
                            This application is based on yt-dlp and is provided solely for <strong>personal and legitimate use</strong> in accordance with applicable laws.
                        </p>
                        <p>
                            Users are responsible for complying with copyright laws regarding downloaded content. Downloading or distributing
                            copyrighted material without explicit permission from the rightsholder may violate applicable laws, and this tool does not encourage or 
                            support such unauthorized use.
                        </p>
                        <p>
                            In some jurisdictions, limited use of copyrighted material may be permitted under doctrines such as "fair use" or "fair dealing." 
                            Users are responsible for understanding and adhering to these limitations in their respective jurisdictions.
                        </p>
                        <p>
                            The developer of this application bears no legal responsibility for any unauthorized or illegal use by users.
                        </p>
                        <p>
                            <small>yt-dlp is an open source software distributed under the 
                            <a href="https://github.com/yt-dlp/yt-dlp/blob/master/LICENSE" target="_blank">Public Domain</a>.</small>
                        </p>
                    </div>
                    
                    <p>By using this application, you acknowledge and agree to the following:</p>
                    
                    <ol>
                        <li>You will use this application only for personal and non-commercial purposes in compliance with all applicable laws.</li>
                        <li>You will only download content that you have legal permission to access and download.</li>
                        <li>You understand that downloading copyrighted material without proper authorization is prohibited.</li>
                        <li>You will not use this application to infringe upon any copyright laws or third-party rights.</li>
                        <li>You will not redistribute, share, or publicly perform content downloaded using this application unless you have the legal right to do so.</li>
                        <li>You understand that the developer of this application is not responsible for any misuse of the application by users.</li>
                        <li>You acknowledge that this tool is intended for downloading content legally available for personal use, such as content you own, have permission to download, or falls under legitimate exceptions to copyright.</li>
                    </ol>
                    
                    <p><strong>Last updated: 2025-07-06 </strong></p>
                    
                    <div class="terms-agreement">
                        <div class="checkbox-container">
                            <input type="checkbox" id="termsCheckbox">
                            <label for="termsCheckbox">I have read, understood, and agree to the terms of use</label>
                        </div>
                        
                        <div class="terms-actions">
                            <button id="agreeBtn" class="btn btn-success" disabled>Continue to Application</button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <script src="https://ajax.googleapis.com/ajax/libs/jquery/2.1.4/jquery.min.js"></script>
    <script src="https://maxcdn.bootstrapcdn.com/bootstrap/3.3.5/js/bootstrap.min.js"></script>
    <script>
        $(document).ready(function() {
            // 체크박스 상태에 따라 버튼 활성화/비활성화
            $('#termsCheckbox').change(function() {
                $('#agreeBtn').prop('disabled', !this.checked);
            });
            
            // 동의 버튼 클릭 이벤트
            $('#agreeBtn').click(function() {
                if ($('#termsCheckbox').is(':checked')) {
                    // 서버에 동의 정보 전송
                    $.ajax({
                        url: '/accept-terms',
                        type: 'POST',
                        success: function(response) {
                            if (response.success) {
                                // 로그인 페이지로 리다이렉트
                                window.location.href = '/';
                            } else {
                                alert('Error: ' + (response.msg || 'Failed to accept terms'));
                            }
                        },
                        error: function() {
                            alert('Network error occurred. Please try again.');
                        }
                    });
                }
            });
        });
    </script>
</body>
</html>