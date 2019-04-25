# youtube-dl-nas Server Dockerfile
# https://github.com/hyeonsangjeon/youtube-dl-nas.git

FROM python:3-onbuild
LABEL maintainer="wingnut0310 <wingnut0310@gmail.com>"

# Install ffmpeg.
#https://unix.stackexchange.com/questions/508724/failed-to-fetch-jessie-backports-repository
RUN echo "deb [check-valid-until=no] http://cdn-fastly.deb.debian.org/debian jessie main" > /etc/apt/sources.list.d/jessie.list
RUN echo "deb [check-valid-until=no] http://archive.debian.org/debian jessie-backports main" > /etc/apt/sources.list.d/jessie-backports.list
RUN sed -i '/deb http:\/\/deb.debian.org\/debian jessie-updates main/d' /etc/apt/sources.list
RUN apt-get -o Acquire::Check-Valid-Until=false update
RUN apt-get install -y libav-tools vim dos2unix && \
    rm -rf /var/lib/apt/lists/*


COPY /subber /usr/bin/subber 
COPY /run.sh /
RUN chmod +x /usr/bin/subber && \
     dos2unix /usr/bin/subber && \
     ln -s /usr/src/app/downfolder / && \
     chmod +x /run.sh && \
     dos2unix /run.sh

RUN pip install -U youtube-dl

EXPOSE 8080

VOLUME ["/downfolder"]

CMD [ "/bin/bash", "/run.sh" ]
#CMD [ "python", "-u", "./youtube-dl-server.py" ]
