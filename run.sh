#!/bin/bash

# 这里需要把堡垒机的VOLUME_DIR配置写在这里
export VOLUME_DIR=/data/jumpserver
# 这里配置一下这个机器的操作系统, 只能是 UOS 和 CentOS
export TASK_OS=CentOS
# 这里配置一下这个任务执行的超时时间，默认30秒，
# 健康检查接口检测机制: 如果当前和上次任务执行时间差值超过此值3倍，服务将标记为不健康
export TASK_INTERVAL=10
#export VOLUME_DIR=/Users/jiangweidong/resources/dazhong_v2.19/jumpserver
# DEV
#uvicorn main:app --reload
python -m uvicorn main:app --host 0.0.0.0 --port 8888
