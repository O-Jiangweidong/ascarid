"""
脚本提供的功能(方便运行，所有逻辑均在一个脚本中)
1、提供健康检测接口，Linux上crontab定时任务探活使用
2、提供JumpServer容器健康检测服务，超过检测失败次数后，执行命令jmsctl restart重启JumpServer
3、从JumpServer中获取ip、gateway、subnet mask进行本机设置，并重启docker
"""

import os
import logging
import subprocess
import shelve
import time
import threading
import ipaddress

from datetime import datetime

from fastapi import FastAPI, APIRouter, status
from fastapi.responses import JSONResponse


# ---------- 初始化区域 ----------
def get_logger():
    log = logging.getLogger('ascarid')
    handler = logging.FileHandler('app.log')
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    log.setLevel(logging.DEBUG)
    log.addHandler(handler)
    return log


logger = get_logger()

# ---------- 常量区域 ----------
UOS = 'UOS'
CENTOS = 'CentOS'
CURRENT_OS = os.environ.get('TASK_OS', CENTOS)
INTERVAL = int(os.environ.get('TASK_INTERVAL', 10))


# ---------- 常量区域 ----------


# ---------- 工具类 ----------
class Tool(object):
    def __init__(self):
        # _thread_pool = {线程名称: {'last_time': '上次执行时间', 'count': 执行次数}}
        self._thread_pool = {}
        self._init_task()

    def _period_check_net_config(self, task_name):
        self._thread_pool[task_name]['count'] += 1
        self._thread_pool[task_name]['last_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._thread_pool[task_name]['timestamp'] = int(time.time())
        logger.info('Start check')
        keys = {
            'ip': 'JUMPSERVER_IP', 'gateway': 'JUMPSERVER_GATEWAY',
            'subnet_mask': 'JUMPSERVER_SUBNET_MASK'
        }
        volume_dir = os.environ.get("VOLUME_DIR")
        db_path = os.path.join(volume_dir, 'core', 'data', 'net_config')
        while True:
            try:
                db = shelve.open(db_path)
            except Exception as err:
                logger.warning(f'DB file open failed: {err}')
                time.sleep(INTERVAL)
                continue
            result = {}
            logger.info(f'items: {",".join([f"{k}: {v}" for k, v in db.items()])}')
            try:
                for k, v in keys.items():
                    if p := db.pop(v):
                        result[k] = p
            except Exception as err:
                logger.warning(f'DB file get params error: {err}')
                time.sleep(INTERVAL)
                continue
            finally:
                try:
                    db.close()
                except Exception:
                    pass
            logger.info(f'Task {task_name} result: {result}')
            # 执行核心任务
            if len(keys) == len(result):
                t = threading.Thread(target=self.modify_network, args=(CURRENT_OS,), kwargs=result)
                t.start()
            time.sleep(INTERVAL)

    def _init_task(self):
        task_name = '周期检查JumpServer设置的网络配置'
        thread = threading.Thread(
            target=self._period_check_net_config, args=(task_name,),
            name=task_name
        )
        self._thread_pool[task_name] = {'count': 0}
        thread.setDaemon(True)
        thread.start()

    def get_tasks_info(self):
        tasks, status = self._thread_pool, 'ok'
        task_message = ''
        for name, other in tasks.items():
            task_message += f"Task [{name}]: executed {other['count']} times，last time: {other['last_time']}; "
            diff = time.time() - other.get('timestamp', 0)
            if diff > INTERVAL * 3:
                status = 'failed'
        content = f"Task total count: {len(tasks)}; {task_message}"
        return content, status

    @staticmethod
    def check_jms_core_status():
        command = "docker inspect --format='{{.State.Health.Status}}' $(docker ps -aqf 'name=jms_core')"
        try:
            result = subprocess.run(command, shell=True, check=True, stdout=subprocess.PIPE)
            health_status = result.stdout.decode().strip().lower() == 'healthy'
            logger.debug(f'Check core status result: {health_status}')
        except Exception as err:
            health_status = False
            logger.error(f'Check core status failed: {err}')
        return health_status

    @staticmethod
    def restart_jms():
        command = 'jmsctl restart'
        subprocess.run(command, shell=True, check=True)
        logger.info('The jmsctl restart command is successfully delivered')

    @staticmethod
    def restart_docker():
        command = 'systemctl restart docker'
        subprocess.run(command, shell=True, check=True)
        logger.info('The docker restart command is successfully delivered')

    @staticmethod
    def __modify_network_centos(**kwargs):
        ip = kwargs.get('ip')
        gateway = kwargs.get('gateway')
        subnet_mask = kwargs.get('subnet_mask')

        command = "ip route | grep default | awk -F '[ \t*]' '{{print $5}}'"
        logger.debug(f'Centos command: {command}')
        result = subprocess.run(command, shell=True, check=True, stdout=subprocess.PIPE)

        routers = set(result.stdout.decode().splitlines())
        if len(routers) < 1:
            logger.warning('Not find nic name')
            return False

        path = "/etc/sysconfig/network-scripts/ifcfg-" + routers.pop()
        if not os.path.exists(path):
            logger.error(f'Not find path: {path}')
            return False

        logger.info(f'Network path: {path}')
        file_handler = open(path, "r")
        network_content = file_handler.read()
        file_handler.close()
        conte = "IPADDR=%s\nGATEWAY=%s\nNETMASK=%s\n" % (ip, gateway, subnet_mask)
        num = network_content.find("IPADDR")
        if num != -1:
            network_content = network_content[:num] + conte
            file_handler = open(path, "w")
            file_handler.write(network_content)
            file_handler.close()

        os.system('service network restart')
        logger.info('The network restart command is successfully delivered')
        return True

    def modify_network(self, os_type=CENTOS, **kwargs):
        logger.info('Start run modify network.')
        if not kwargs:
            logger.info('Modify network not kwargs, the task ends.')
            return

        failed = False
        # kwargs 目前传入的参数有ip, subnet_mask, gateway
        # 自己构建一个subnet_mask_prefix
        if subnet_mask := kwargs.get('subnet_mask'):
            ip = ipaddress.IPv4Network("0.0.0.0/" + subnet_mask, strict=False)
            kwargs['subnet_mask_prefix'] = int(ip.prefixlen)
        os_actions = {
            UOS: [
                'nmcli con mod eno1  ipv4.addresses {ip}',
                'nmcli con mod eno1  ipv4.addresses {ip}/{subnet_mask_prefix}',
                'nmcli con mod eno1  ipv4.gateway {gateway}',
                'nmcli con up eno1'
            ],
            CENTOS: self.__modify_network_centos
        }
        action = os_actions.get(os_type)
        if not action:
            logger.warning(f'此操作系统({os_type})下未匹配到对应命令.')
            return

        if isinstance(action, list):
            for command in action:
                try:
                    full_command = command.format(**kwargs)
                except KeyError:
                    continue

                try:
                    subprocess.run(full_command, shell=True, check=True)
                    logger.info(f'Command [{full_command}] executed successfully')
                except Exception as err:
                    failed = True
                    logger.error(f'Command [{full_command}], executed failed: {err}')
        elif callable(action):
            failed = not action(**kwargs)
        if not failed:
            self.restart_docker()


# ---------- 工具类 ----------
tool = Tool()
app = FastAPI()
api_router = APIRouter(prefix='/api')


# ---------- 路由 ----------
@app.get('/')
async def index():
    return {'message': 'hello world'}


@api_router.get('/health')
async def health() -> JSONResponse:
    info, resp = tool.get_tasks_info()
    data = {'status': resp, 'result': info}
    if resp != 'ok':
        return JSONResponse(content=data, status_code=status.HTTP_400_BAD_REQUEST)
    return JSONResponse(content=data, status_code=status.HTTP_200_OK)


# ---------- 路由 ----------
app.include_router(api_router)
