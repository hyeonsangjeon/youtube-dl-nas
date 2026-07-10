---
layout: default
title: 모바일 공유 설정
---

# 모바일 공유 설정

[English](./)

휴대폰에서 공유한 URL은 `youtube-dl-nas`가 실행 중인 사용자의 NAS로 직접 전송됩니다. 이 GitHub Pages 매뉴얼은 NAS 주소, ID, 비밀번호, API token 또는 공유 URL을 수집하거나 중계하지 않습니다.

## Android HTTPS 접속

1. Chrome에서 HTTPS로 설정된 `youtube-dl-nas`를 엽니다.
2. 로그인하고 이용약관에 동의합니다.
3. Chrome 메뉴에서 **앱 설치** 또는 **홈 화면에 추가**를 선택합니다.
4. YouTube에서 **공유**를 누르고 **youtube-dl NAS**를 선택합니다.

로그인이 만료된 경우 다시 로그인하면 공유받은 URL이 이어서 큐에 등록됩니다.

## Android 로컬 HTTP 접속

로컬 HTTP 주소는 PWA로 설치할 수 없으므로 오픈소스 [HTTP Shortcuts](https://http-shortcuts.rmy.ch/) 앱을 사용합니다.

1. HTTP Shortcuts를 설치합니다.
2. [youtube-dl NAS 템플릿 가져오기](https://http-shortcuts.rmy.ch/import?url=https%3A%2F%2Fhyeonsangjeon.github.io%2Fyoutube-dl-nas%2Fmobile%2Fassets%2Fyoutube-dl-nas-http-shortcut.zip)를 누릅니다. 문제가 있으면 [ZIP 파일](assets/youtube-dl-nas-http-shortcut.zip)을 내려받아 수동으로 가져옵니다.
3. 가져온 **youtube-dl NAS** 카테고리에서 **1. Configure NAS**를 한 번 실행합니다.
4. NAS 전체 주소, 대시보드 로그인 ID와 비밀번호를 차례로 입력합니다. 주소 예시는 `http://192.168.0.20:8080`입니다.
5. YouTube 또는 브라우저에서 URL을 공유하고 **Download to NAS**를 선택합니다. 다음부터는 저장된 설정을 묻지 않고 사용합니다.

API Bearer token은 선택 사항입니다. 기본 템플릿은 기존 ID와 비밀번호를 사용합니다.

설정이 비어 있거나 공유된 텍스트에 URL이 없으면 네트워크 요청을 보내기 전에 중단하고 필요한 조치를 화면에 표시합니다.

## iPhone과 iPad

[**Download to NAS.shortcut** 내려받기](assets/Download-to-NAS.shortcut)를 누르고 단축어 앱에서 **단축어 추가**를 선택합니다.

1. 가져온 단축어를 편집합니다.
2. `http://NAS_ADDRESS:8080/youtube-dl/rest`를 실제 NAS 주소로 바꿉니다.
3. `YOUR_ID`와 `YOUR_PASSWORD`를 대시보드 로그인 정보로 바꿉니다.
4. YouTube 또는 Safari에서 **공유**를 누르고 **Download to NAS**를 선택합니다.

이 단축어는 공유 시트의 URL을 `best` 품질과 함께 NAS REST API로 직접 전송하고 응답을 보여줍니다. Apple 단축어 도구에서 누구나 설치할 수 있도록 서명했으며 실제 NAS 주소나 로그인 정보는 포함하지 않았습니다. 원한다면 **URL의 콘텐츠 가져오기**(`POST`, JSON 본문)와 **콘텐츠 보기** 동작으로 직접 만들어도 됩니다.

## 외부 네트워크

HTTP 포트를 인터넷에 직접 노출하지 마세요. Tailscale 같은 VPN을 사용하거나 NAS에서 HTTPS 역방향 프록시를 설정하세요. 대시보드를 HTTPS로만 제공한다면 `COOKIE_SECURE=true`를 설정합니다.
