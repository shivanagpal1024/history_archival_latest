FROM docker.repo1.uhc.com/ecap/python:latest

RUN mkdir /history-archival-process
COPY Archival_Multithreading.py /history-archival-process
COPY DB2.properties /history-archival-process

RUN chmod -R 775 /history-archival-process/*

RUN pip3 install pyftpdlib
RUN pip3 install ftputil
RUN pip3 install pymysql
RUN pip3 install ibm_db
RUN pip3 install tqdm 
run pip3 install pytz

WORKDIR /history-archival-process
RUN chown -R 1001 /history-archival-process

USER 1001

CMD [ "sleep", "86400" ]
