[![GitHub license](https://img.shields.io/badge/license-MIT-blue.svg?style=flat-square)](https://raw.githubusercontent.com/hyeonsangjeon/youtube-dl-nas/master/LICENSE)
![Docker Pulls Shield](https://img.shields.io/docker/pulls/modenaf360/youtube-dl-nas)
![Docker Stars Shield](https://img.shields.io/docker/stars/modenaf360/youtube-dl-nas)
# youtube-dl-nas

simple youtube download micro web queue server. 
To prevent a queue attack when using NAS as a server, a making account was created when creating a docker container, and a new UI was added.
This Queue server based on python3 and debian Linux.
https://hub.docker.com/r/modenaf360/youtube-dl-nas/

- web server : [`bottle`](https://github.com/bottlepy/bottle) 
- youtube-dl : [`youtube-dl`](https://github.com/rg3/youtube-dl).
- yt-dlp : [`yt-dlp`](https://github.com/yt-dlp/yt-dlp).
- base : [`python queue server`](https://github.com/manbearwiz/youtube-dl-server).
- websocket : [`bottle-websocket`](https://github.com/zeekay/bottle-websocket).

<img src="https://github.com/hyeonsangjeon/youtube-dl-nas/blob/master/pic/Architecture-Youtube-dl-nas.png" width="90%">

![screenshot1](https://github.com/hyeonsangjeon/youtube-dl-nas/blob/master/pic/youtube-dl-server-login.png?raw=true)

### Update Info
- 2023.02.19 : [Patch] Changed the executable from youtube-dl to yt-dlp for fixed error about 'Unable to extract uploader id' and download speed..
- 2022.09.29 : [Patch] Check for updates essential packages on first startup container.
- 2022.09.28 : [Patch] Clears URL input when submitting the form.
- 2021.12.09 : [Patch] Fix proxy setting bug
- 2021.05.03 : [Patch] Fix random mkv or mp4 format when specifying resolution
- 2020.11.13 : [Patch] Added docker optinal variable to support youtube-dl proxy
- 2020.08.12 : [Patch] Added audio-mp3 option 
- 2019.04.25 : [Patch] Failed to fetch jessie backports repository patch during build Dockerfile, Add Scheduler update "pip install -U youtube-dl" once a day.You no longer need to update pip youtube-dl when inexecutable in the container.
- 2020.04.07 : [Patch] Audio only option for web-ui and REST call. Change username field type for compatiblity
- 2020.02.10 : [Patch] Modifying so this will work behind HTTPS as well.
- 2019.02.13 : [Patch] binary excution error update,  : 'caused by ExtractorError("Could not find JS function 'encodeURIComponent'; please report this issue on https://yt-dl.org/bug ..'. Binary Excution file update docker rebuild,Specify release version in html page
- 2018.11.08 : [Patch] binary excution error update,  : 'youtube_dl.utils.RegexNotFoundError: Unable to extract Initial JS player signature function name'. some url like(https://youtu.be/), Handling Variables on Application Ports for Using the docker Network Host Mode,Specify release version in html page
- 2018.10.06 : [Patch] Prevent thread death due to websocket exception in walker thread after download, add REST API 
- 2018.10.01 : [Minor Patch] Patching worker thread dead symptom when moving the browser during download, add resolution 1440p, 2160p(4k)
- 2018.09.28 : [Add functional option] Resolution selectable, Downloaded result html table representation**
 
#### You can check the status of download queue processing in real time using websocket from the message below the text box.
![screenshot](https://github.com/hyeonsangjeon/youtube-dl-nas/blob/master/pic/youtube-dl-server.png?raw=true)


### How to use this image

#### To run docker, excute this command in a ternimal:
The docker volume parameter `-v` is used by the queue operation to process the downloaded mount path to the host server

- downloaded docker volume path :  '/downfolder'  
- MY_ID, MY_PW : Required variables when you login validation, The start character  '!' '$' '&' is does not apply.
- TZ :  optional variable.

## docker options are as follows,

|Variables      |Description                                                   |
|---------------|--------------------------------------------------------------|
|-v  host:guest         |/downfolder (do not change guest location. expose volume mount to host server)                            |  
|-d           |background run                                                | 
|-p   host:guest        |expose port conainer core-os port to your os (port fowarding) |
|-e MY_ID          |using it login id, linux environment variables, do not use start character   '!' '$' '&'                                |
|-e MY_PW           |using it login password, linux environment variables ,  do not use start character   '!' '$' '&'                                  |
|-e TZ           |take it to user country, linux environment variables                                   |
|-e APP_PORT           |optinal variable. default is 8080   |
|-e PROXY           |optinal variable. set youtube-dl proxy, default is ""   |

##### To run docker, excute this command in a ternimal:
```shell
docker run -d --name youtube-dl -e MY_ID=modenaf360 -e MY_PW=1234  -v /volume2/youtube-dl:/downfolder -p 8080:8080 modenaf360/youtube-dl-nas
```

##### If want set TimeZone, example using in South-Korea web content 
```shell
docker run -d --name youtube-dl -e TZ=Asia/Seoul -e MY_ID=modenaf360 -e MY_PW=1234 -v /volume2/youtube-dl:/downfolder -p 8080:8080 modenaf360/youtube-dl-nas
```

##### example, how to using docker host network and changing the application port :
```shell
# use --net=host -e APP_PORT=custom_port
docker run -d --name youtube-dl --net=host -e APP_PORT=9999 -e MY_ID=modenaf360 -e MY_PW=1234  -v /volume2/youtube-dl:/downfolder modenaf360/youtube-dl-nas
```


#### Request restful API & Response
```shell
curl -X POST http://localhost:8080/youtube-dl/rest \
  -d '{
	"url":"https://www.youtube.com/watch?v=s9mO5q6GiAc",
	"resolution":"best", 
	"id":"iamgroot",
	"pw":"1234"
}'
```
```shell
{
    "success": true,
    "msg": "download has started",
    "Remaining downloading count": "7"
}
```

 If you want to get into docker container os, excute this command `[1]` :
```console
docker exec -i -t youtube-dl /bin/bash
```

##### Example, when using synology docker provisioning platform

- docker volume mount setting 

![screenshot1](https://github.com/hyeonsangjeon/youtube-dl-nas/blob/master/pic/volume_set_synology.png?raw=true)



- ID, Password setting to docker environment
![screenshot1](https://github.com/hyeonsangjeon/youtube-dl-nas/blob/master/pic/id_pw_set_synology.png?raw=true)

### Reference
[1]: https://github.com/hyeonsangjeon/youtube-dl-nas/blob/master/pic/youtube-dl-server-login.png
[2]: https://github.com/hyeonsangjeon/youtube-dl-nas/blob/master/pic/youtube-dl-server.png
[3]: https://github.com/hyeonsangjeon/youtube-dl-nas/blob/master/pic/volume_set_synology.png
[4]: https://github.com/hyeonsangjeon/youtube-dl-nas/blob/master/pic/id_pw_set_synology.png

`[1]`. https://docs.docker.com/engine/reference/commandline/cli/#environment-variables

