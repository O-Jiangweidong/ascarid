## 使用手册
### 前置条件
#### 1. 需要在服务器上安装Python3.11环境
#### 2. pip3 install fastapi uvicorn
#### 3. 检查服务器是否安装lsof命令，若没有则需安装

### 执行
#### 借助 crontab 定时探活程序，执行步骤如下
#### 0. 解压 ascarid.zip 到 /opt 目录下(不要修改目录)，修改 run.sh 配置项
#### 1. 使用命令 crontab -e 编辑定时任务
#### 2. 将如下命令加入到文本栏中，并保存
#### `* * * * * /bin/bash /path/to/your/exploratory.sh >/dev/null 2>&1`


