#!/bin/bash

# 发送 HTTP 请求并获取响应状态码
response_code=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8888/api/health)

# 检查响应状态码是否为 200
if [[ "$response_code" -eq 200 ]]; then
    echo "Response is 200. Skipping execution."
else
    echo "Response is not 200. Executing run.sh script."
    # 执行 run.sh 脚本
    pid=$(lsof -t -i :8888)
    if [[ -n $pid ]]; then
      echo "Found process with PID $pid on port 8888. Terminating..."
      # 关闭进程
      kill $pid
    fi
    nohup /Users/jiangweidong/resources/dazhong_v2.19/ascarid/run.sh > /dev/null 2>&1 &
fi
