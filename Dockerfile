# youtube-dl-nas Server Dockerfile
# https://github.com/hyeonsangjeon/youtube-dl-nas.git

FROM python:3-onbuild
LABEL maintainer="wingnut0310 <wingnut0310@gmail.com>"

# Install ffmpeg.
RUN apt-get -y update && \
     apt-get install -y libav-tools vim dos2unix && \
     rm -rf /var/lib/apt/lists/*

COPY /subber /usr/bin/subber 
RUN chmod +x /usr/bin/subber && \
     dos2unix /usr/bin/subber && \
     ln -s /usr/src/app/downfolder /

EXPOSE 8080

VOLUME ["/downfolder"]

CMD [ "/bin/bash", "./run.sh" ]
#CMD [ "python", "-u", "./youtube-dl-server.py" ]
