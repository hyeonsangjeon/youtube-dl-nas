<!DOCTYPE html>
<html lang="{{locale}}">
<head>
    <meta charset="utf-8">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="theme-color" content="#168a92">
    <title>{{t('terms.title')}}</title>
    <link rel="manifest" href="/manifest.webmanifest">
    <link rel="icon" href="/youtube-dl/static/pwa/icon-192.png">
    <link href="https://maxcdn.bootstrapcdn.com/bootstrap/3.3.5/css/bootstrap.min.css" rel="stylesheet">
    <link href="youtube-dl/static/css/style.css?v={{app_version}}" rel="stylesheet">
    
    
</head>
<body>
        <div class="site-wrapper">
        <div class="site-wrapper-inner">
            <div class="terms-container">
                <form class="locale-form locale-form-terms" action="/locale" method="POST">
                    <input type="hidden" name="next" value="{{locale_next}}">
                    <label for="locale-selector" class="sr-only">{{t('common.language')}}</label>
                    <span class="locale-icon" aria-hidden="true">&#127760;</span>
                    <select id="locale-selector" name="locale" aria-label="{{t('common.language')}}" onchange="this.form.submit()">
                    % for locale_code, locale_name in locale_options:
                        <option value="{{locale_code}}"{{!' selected' if locale_code == locale else ''}}>{{locale_name}}</option>
                    % end
                    </select>
                </form>
                <div class="terms-header">
                    <h2>{{t('terms.heading')}}</h2>
                    <p>{{t('terms.intro')}}</p>
                </div>
                
                <div class="terms-content">
                    <div class="copyright-disclaimer">
                        <h4>{{t('terms.notice_heading')}}</h4>
                        <p>{{t('terms.notice_personal')}}</p>
                        <p>{{t('terms.notice_copyright')}}</p>
                        <p>{{t('terms.notice_exceptions')}}</p>
                        <p>{{t('terms.notice_liability')}}</p>
                        <p>
                            <small>{{t('terms.ytdlp_license_prefix')}}
                            <a href="https://github.com/yt-dlp/yt-dlp/blob/master/LICENSE" target="_blank" rel="noopener noreferrer">{{t('terms.public_domain')}}</a>.</small>
                        </p>
                    </div>
                    
                    <p>{{t('terms.acknowledge')}}</p>
                    
                    <ol>
                        <li>{{t('terms.item_1')}}</li>
                        <li>{{t('terms.item_2')}}</li>
                        <li>{{t('terms.item_3')}}</li>
                        <li>{{t('terms.item_4')}}</li>
                        <li>{{t('terms.item_5')}}</li>
                        <li>{{t('terms.item_6')}}</li>
                        <li>{{t('terms.item_7')}}</li>
                    </ol>
                    
                    <p><strong>{{t('terms.last_updated')}}</strong></p>
                    
                    <div class="terms-agreement">
                        <div class="checkbox-container">
                            <input type="checkbox" id="termsCheckbox">
                            <label for="termsCheckbox">{{t('terms.agree')}}</label>
                        </div>
                        
                        <div class="terms-actions">
                            <button id="agreeBtn" class="btn btn-success" disabled>{{t('terms.continue')}}</button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <script src="https://ajax.googleapis.com/ajax/libs/jquery/2.1.4/jquery.min.js"></script>
    <script src="https://maxcdn.bootstrapcdn.com/bootstrap/3.3.5/js/bootstrap.min.js"></script>
    <script>
        window.YDLNAS_I18N = {{!translations_json}};

        function translate(key) {
            return window.YDLNAS_I18N[key] || key;
        }

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
                                window.location.href = '/?next=' + encodeURIComponent({{!next_path_json}});
                            } else {
                                alert(response.msg || translate('terms.accept_failed'));
                            }
                        },
                        error: function() {
                            alert(translate('terms.network_error'));
                        }
                    });
                }
            });
        });
    </script>
</body>
</html>
