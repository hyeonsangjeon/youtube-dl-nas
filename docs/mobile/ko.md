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

대시보드 **Options**에서 이 기기의 모바일 공유 기본값을 최고 화질, 호환 MP4, 1080p, 720p, MP3, M4A, Opus 또는 **항상 물어보기**로 정할 수 있습니다. 항상 물어보기는 공유 URL을 입력창에 채워 직접 확인하게 하고, 나머지 프로필은 바로 큐에 넣습니다. 로그인이 만료된 경우 다시 로그인하면 URL을 리디렉션 주소에 노출하지 않고 같은 흐름이 이어집니다.

재생목록과 채널을 공유하면 항상 입력창을 열어 Playlist Guard에서 처음 10개 또는 전체 항목 범위를 명시적으로 선택하게 합니다.

## Android 로컬 HTTP 접속

로컬 HTTP 주소는 PWA로 설치할 수 없으므로 오픈소스 [HTTP Shortcuts](https://http-shortcuts.rmy.ch/) 앱을 사용합니다.

1. HTTP Shortcuts를 설치합니다.
2. [youtube-dl NAS 템플릿 가져오기](https://http-shortcuts.rmy.ch/import?url=https%3A%2F%2Fhyeonsangjeon.github.io%2Fyoutube-dl-nas%2Fmobile%2Fassets%2Fyoutube-dl-nas-http-shortcut.zip)를 누릅니다. 문제가 있으면 [ZIP 파일](assets/youtube-dl-nas-http-shortcut.zip)을 내려받아 수동으로 가져옵니다.
3. 가져온 **youtube-dl NAS** 카테고리에서 **1. Configure NAS**를 한 번 실행합니다.
4. NAS 전체 주소, 대시보드 로그인 ID, 비밀번호, 기본 프로필을 차례로 입력합니다. 주소는 `http://192.168.0.20:8080`, 프로필은 `best`처럼 입력합니다.
5. YouTube 또는 브라우저에서 URL을 공유하고 **Download to NAS**를 선택합니다. 다음부터는 저장된 설정을 묻지 않고 사용합니다.

API Bearer token은 선택 사항입니다. 기본 템플릿은 기존 ID와 비밀번호를 사용합니다.

기본 프로필은 최고 화질, 호환 MP4, 1080p, 720p, MP3, M4A, Opus 중에서 저장할 수 있습니다. Android 공유 제목과 본문을 모두 확인하고, 기기가 공유 데이터에서 URL을 누락하면 URL 입력창을 대안으로 표시합니다. 설정이 비어 있으면 네트워크 요청을 보내기 전에 중단합니다.

## iPhone과 iPad

[**Download to NAS.shortcut** 내려받기](assets/Download-to-NAS.shortcut)를 눌러 Smart Share v2 단축어를 엽니다.

1. 가져오기 화면에서 끝에 `/`가 없는 NAS 기본 주소를 입력합니다. 예: `http://192.168.0.20:8080`
2. 대시보드 로그인 ID와 비밀번호를 입력합니다.
3. 기본 프로필로 `best`, `compatible-mp4`, `1080p`, `720p`, `audio-mp3`, `audio-m4a`, `audio-opus`, `ask` 중 하나를 입력합니다.
4. **단축어 추가**를 누릅니다. 내부 동작을 직접 편집할 필요가 없습니다.
5. YouTube 또는 Safari에서 **공유**를 누르고 **Download to NAS**를 선택합니다.

평소에는 저장한 프로필로 묻지 않고 바로 보냅니다. `ask`를 선택한 경우에만 프로필 메뉴가 열립니다. 순수 재생목록이나 채널은 처음 10개 또는 전체 항목을 고르게 하고, 타임스탬프가 있는 YouTube 링크는 전체 영상 또는 해당 시점부터 받기를 묻습니다. 공유 시트 없이 단축어를 직접 실행하면 URL 입력창이 열립니다.

서버 응답에는 큐 추가, 이미 큐에 있음, NAS에 이미 다운로드됨 여부와 가능한 경우 큐 순서가 표시됩니다. Apple 단축어 도구에서 누구나 설치할 수 있도록 서명했으며 배포 파일에는 실제 NAS 주소나 로그인 정보가 들어 있지 않습니다.

## 외부 네트워크

HTTP 포트를 인터넷에 직접 노출하지 마세요. Tailscale 같은 VPN을 사용하거나 NAS에서 HTTPS 역방향 프록시를 설정하세요. 대시보드를 HTTPS로만 제공한다면 `COOKIE_SECURE=true`를 설정합니다.
