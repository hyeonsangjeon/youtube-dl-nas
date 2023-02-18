# youtube-dl-nas Server Dockerfile
# https://github.com/hyeonsangjeon/youtube-dl-nas.git

# update container python 3.8
FROM python:3.8
LABEL maintainer="wingnut0310 <wingnut0310@gmail.com>"


RUN apt-get update -y 
RUN apt-get install -y v4l-utils
# Install ffmpeg.
RUN apt-get install ffmpeg -y
#RUN apt-get install -y libav-tools 
RUN apt-get install -y vim dos2unix && \
     rm -rf /var/lib/apt/lists/*


COPY /subber /usr/bin/subber 
COPY /run.sh /
COPY / /usr/src/app/ 
RUN chmod +x /usr/bin/subber && \
     dos2unix /usr/bin/subber && \
     ln -s /usr/src/app/downfolder / && \
     chmod +x /run.sh && \
     dos2unix /run.sh

WORKDIR /usr/src/app/
RUN pip install -r requirements.txt
RUN pip install -U youtube-dl

EXPOSE 8080

VOLUME ["/downfolder"]

CMD [ "/bin/bash", "/run.sh" ]
#CMD [ "python", "-u", "./youtube-dl-server.py" ]
