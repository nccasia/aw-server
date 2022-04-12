#!/bin/bash

for i in `ps -aux | grep '__main__.py' | awk '{print $2}'`;
    do kill -9 $i
done

cd /home/nccsoft/komutracker/aw-server
nohup /home/nccsoft/komutracker/venv/bin/python __main__.py > aw-server-log.txt 2>&1 &