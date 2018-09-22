[![GitHub license](https://img.shields.io/badge/license-MIT-blue.svg?style=flat-square)](https://raw.githubusercontent.com/manbearwiz/youtube-dl-server/master/LICENSE)

# youtube-dl-nas

simple youtube download micro web queue server. 
To prevent a queue attack when using NAS as a server, a making account was created when creating a docker container, and a new UI was added.
This Queue server based on python3 and debian Linux.
https://hub.docker.com/r/modenaf360/youtube-dl-nas/

- web server : [`bottle`](https://github.com/bottlepy/bottle) 
- youtube-dl : [`youtube-dl`](https://github.com/rg3/youtube-dl).
- base : [`python queue server`](https://github.com/manbearwiz/youtube-dl-server).
- websocket : [`bottle-websocket`](https://github.com/zeekay/bottle-websocket).

![screenshot1](https://github.com/hyeonsangjeon/youtube-dl-nas/blob/master/pic/youtube-dl-server-login.png?raw=true)



#### You can check the status of download queue processing in real time using websocket from the message below the text box.
![screenshot](https://github.com/hyeonsangjeon/youtube-dl-nas/blob/master/pic/youtube-dl-server.png?raw=true)


### How to use this image

#### To run docker, excute this command in a ternimal:
The docker volume parameter `-v` is used by the queue operation to process the downloaded mount path to the host server

- downloaded docker volume path :  '/downfloder'  
- MY_ID, MY_PW : Required variables when you login validation
- TZ :  optional variable.

## docker options are as follows,

|Variables      |Description                                                   |
|---------------|--------------------------------------------------------------|
|-v  host:guest         |/downfolder (do not change guest location. expose volume mount to host server)                            |  
|-d           |background run                                                | 
|-p   host:guest        |expose port conainer core-os port to your os (port fowarding) |
|-e MY_ID          |using it login id, linux environment variables                                   |
|-e MY_PW           |using it login password, linux environment variables                                   |
|-e TZ           |take it to user country, linux environment variables                                   |

##### To run docker, excute this command in a ternimal:
```shell
docker run -d --name youtube-dl -e MY_ID=modenaf360 -e MY_PW=1234  -v /volume2/youtube-dl:/downfolder -p 8080:8080 modenaf360/youtube-dl-nas
```

##### If want set TimeZone, example using in South-Korea web content 
```shell
docker run -d --name youtube-dl -e TZ=Asia/Seoul -e MY_ID=modenaf360 -e MY_PW=1234 -v /volume2/youtube-dl:/downfolder -p 8080:8080 modenaf360/youtube-dl-nas
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

