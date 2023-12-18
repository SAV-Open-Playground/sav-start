#!/usr/bin/python3
# -*-coding:utf-8 -*-
"""
@File    :   sav_control_host.py
@Time    :   2023/11/30
@Version :   0.1
@Desc    :   The sav_control_host.py is responsible for the management of current host(slave).
"""
import json
import time
import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from sav_control_common import *
import argparse


class RunEmulation():
    def __init__(self, root_dir, host_signal_path=r"./active_signal.json", base_compose="./docker_compose_50.yml",
                 base_topo="./savop/topology/topo_50.sh", base_node_num=50):
        self._id = whoami()
        if not self._id:
            raise ValueError("get id error")
        self.logger = self.get_logger()
        self.root_dir = root_dir
        self.host_signal_path = host_signal_path
        self.base_compose_path = base_compose
        self.base_topo = base_topo
        self.base_node_num = base_node_num
        self.active_app = None

    def get_logger(self):
        """
        get logger function for all modules
        """
        maxsize = 1024*1024*500
        backup_num = 5
        level = logging.WARN
        level = logging.DEBUG
        logger = logging.getLogger(__name__)
        logger.setLevel(level)
        path = os.path.dirname(os.path.abspath(__file__))+f"/{self._id}_{__name__}.log"
        if not os.path.exists(path):
            os.system(f"touch {path}")
        with open(path, "w") as f:
            pass
        handler = RotatingFileHandler(path, maxBytes=maxsize, backupCount=backup_num)
        handler.setLevel(level)

        formatter = logging.Formatter("[%(asctime)s] [%(filename)s:%(lineno)s-%(funcName)s] [%(levelname)s] %(message)s")
        formatter.converter = time.gmtime
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        logging.StreamHandler(stream=None)

        # sh = logging.StreamHandler(stream=sys.stdout)
        # sh.setFormatter(formatter)
        # logger.addHandler(sh)
        return logger

    def if_base_started(self):
        """
        tell if base started
        """
        s_cmd = subprocess_cmd("docker ps")
        out = s_cmd.stdout.split("\n")
        bird_count = 0
        krill_count = 0
        routinator_count = 0
        for line in out:
            if "savop_bird_base" in line:
                bird_count += 1
            if "routinator" in line:
                routinator_count += 1
            if "krill" in line:
                krill_count += 1
        rpki = False
        if rpki:
            return bird_count == self.base_node_num and routinator_count == 1 and krill_count == 1
        else:
            return bird_count == self.base_node_num

    def send_stop_signal(self):
        """stop sav-agent and bird on all nodes"""
        data = json_r(self.host_signal_path)
        data["command"] = "stop"
        json_w(self.host_signal_path, data)
        self.logger.info("stop signal sent")

    def clear_logs(self):
        """
        clear log folders, should be called in start base function
        """
        cur_dir = os.path.dirname(os.path.abspath(__file__))
        self.logger.debug(cur_dir)
        path = r'./logs'
        if not os.path.exists(path):
            os.mkdir(path)
        folders = os.listdir(path)
        folders = [i for i in folders if os.path.isdir(os.path.join(path, i))]
        for folder in folders:
            folder_path = os.path.join(path, folder)
            files = os.listdir(folder_path)
            for file in files:
                file_path = os.path.join(folder_path, file)
                if os.path.isdir(file_path):
                    os.system("rm -rf " + file_path)
                else:
                    os.remove(file_path)

    def ready_base(self, force_restart=False):
        """
        start base ,starting containers and links
        """
        if self.if_base_started() and not force_restart:
            self.logger.info("base already started")
            return
        self.logger.info(f"init base with {self.base_compose_path}")
        t = time.time()
        cmd = f"docker compose -f {self.base_compose_path} down"
        subprocess_cmd(cmd)
        cmd = f"docker build --build-arg root_dir=./ -f {self.root_dir}/savop/dockerfiles/reference_router {self.root_dir} -t savop_bird_base"
        ret = subprocess_cmd(cmd)
        # self.clear_logs()
        self.logger.info("container stopped")
        cmd = f"docker compose -f {self.base_compose_path} up -d"
        # os.system(cmd)
        ret = subprocess_cmd(cmd)
        self.logger.info("container started")
        cmd = f"bash {self.base_topo}"
        # os.system(cmd)

        ret = run_cmd(cmd)
        self.logger.info("link started")
        t = time.time()-t
        self.logger.info(f"base start finished in {t:.4f} seconds")
        if self.if_base_started():
            self.logger.info("base ready")
            print(f"{self.base_node_num} router run successfully!")
            return
        else:
            self.logger.error("base start failed")
            sys.exit(1)

    def update_configs(self, nodes, proto):
        """
        update the bird and sav-agent configs
        """
        valid_protos = ["grpc", "quic", "dsav", "non-rpdp"]
        if not proto in valid_protos:
            raise ValueError(f"proto should be {valid_protos} ,not {proto}")
        for n in nodes:
            # update bird config
            with open(f"{self.src_cfg_path}/{n}.conf", "r") as f:
                bird_cfg = f.readlines()
            if proto != "dsav":
                bird_cfg = list(map(lambda x: x.replace(
                    "from sav_inter{", "from basic{"), bird_cfg))
            # remove unused links
            # bird config
            not_changed = True
            while not_changed:
                bird_cfg, not_changed = remove_bird_links(bird_cfg, nodes)
            # sa config
            # remove tailing spaces
            temp = []
            for l in bird_cfg:
                while l.endswith(" \n"):
                    l = l[:-2]+"\n"
                temp.append(l)
            bird_cfg = temp
            # update start delay in bird
            for i in range(len(bird_cfg)):
                count = 0
                if "connect delay time" in bird_cfg[i]:
                    bird_cfg[i] = f"\tconnect delay time {count};\n"
                    # count += 1

            with open(f"{self.dst_cfg_path}/{n}.conf", "w") as f:
                f.writelines(bird_cfg)
            for l in bird_cfg:
                if l.endswith(" \n"):
                    input(l)
            # update sav-agent config
            sa_cfg = json_r(f"{self.src_cfg_path}/{n}.json")
            if proto in ["grpc", "quic"]:
                temp = {}
                for k, v in sa_cfg["link_map"].items():
                    asns = k.split("_")[1:]
                    asns = list(map(int, asns))
                    if (asns[0] in nodes) and (asns[1] in nodes):
                        v["link_type"] = proto
                        temp[k] = v
                sa_cfg["link_map"] = temp
            else:
                sa_cfg["link_map"] = {}
            sa_cfg["enabled_sav_app"] = self.active_app
            sa_cfg["apps"] = [self.active_app]
            json_w(f"{self.dst_cfg_path}/{n}.json", sa_cfg)
            # self.logger.info(f"active_app:{self.active_app} config updated")
        # waits the configs to be updated in containers
        time.sleep(len(nodes)/30)

    def _log_to_cmd_file(self, msg, result_path, log_level='info'):
        if not log_level in ['info', 'error', 'warn']:
            raise ValueError(f"log_level should be info, error or warn: {log_level}")
        match log_level:
            case 'info':
                self.logger.info(msg)
            case 'error':
                self.logger.error(msg)
            case 'warn':
                self.logger.warning(msg)
        with open(result_path, "a+") as f:
            f.write("\n"+msg)

    def _update_scope(self, percentage, mode):
        signal_base_path = f'./signal_templates/signal_{percentage}_full.txt'
        signal = json_r(signal_base_path)
        del signal["command_timestamp"]
        signal["command"] = "start"
        signal["source"] = self.active_app
        signal["command_scope"] = list(
            map(int, signal["command_scope"].split(",")))
        signal["command_scope"].sort()
        # signal["stable_threshold"] = int((len(signal['command_scope'])/3)**2)*1.5
        if mode == "dsav":
            signal["stable_threshold"] = len(signal['command_scope'])*3
        elif mode == "grpc":
            signal["stable_threshold"] = len(signal['command_scope'])
        elif mode in ["passport"]:
            signal["stable_threshold"] = 10
        self.logger.info(
            f"active nodes: {signal['command_scope']}\n stable_threshold: {signal['stable_threshold']}")
        return signal

    def _ready_env(self, result_path, percentage, mode):
        # self.ready_base(True)
        # self.send_stop_signal()
        # time.sleep(5)
        msg = f"active_app: {self.active_app}, "
        msg += f"percentage: {percentage}, base_size:{self.base_node_num}"
        self._log_to_cmd_file(msg, result_path)
        return self._update_scope(percentage, mode)

    def get_valid_nodes(self, nodes):
        results = []
        for node in nodes:
            node_roles = {}
            bird_cfg = open(
                f"{self.dst_cfg_path}/{node}.conf", "r").readlines()
            for l in bird_cfg:
                if l.startswith("\tlocal role"):
                    node_roles[l.split()[-1][:-1]] = None
            if "provider" in node_roles:
                results.append(node)
            elif "peer" in node_roles:
                results.append(node)
        return results

    def start(self):
        self.ready_base(force_restart=True)


class DevicePerformance():
    __cpucommand = "dstat -c --nocolor 1 2 --nocolor| sed -e '1,3d'"
    __memorycommand = "dstat -m --nocolor 1 2 --nocolor| sed -e '1,3d'"
    __diskcommand = "dstat -d --nocolor 1 2 --nocolor| sed -e '1,3d'"
    __networkcommand = "dstat -n --nocolor 1 2 --nocolor| sed -e '1,3d'"
    __dockerStatscommand = "docker stats --no-stream --format json"

    def get_cpu_performance(self):
        ret = subprocess_cmd(cmd=self.__cpucommand)
        return ret.returncode, ret.stderr, ret.stdout

    def get_memory_performace(self):
        ret = subprocess_cmd(cmd=self.__memorycommand)
        return ret.returncode, ret.stderr, ret.stdout

    def get_disk_performance(self):
        ret = subprocess_cmd(cmd=self.__diskcommand)
        return ret.returncode, ret.stderr, ret.stdout

    def get_network_performance(self):
        ret = subprocess_cmd(cmd=self.__networkcommand)
        return ret.returncode, ret.stderr, ret.stdout

    def get_docker_container_performance(self):
        ret = subprocess_cmd(cmd=self.__dockerStatscommand)
        return ret.returncode, ret.stderr, ret.stdout


class Minitor:
    performance = DevicePerformance()
    @staticmethod
    def host_performance():
        performance = DevicePerformance()
        performance_dict = {"CPU": {}, "memory": {}, "disk": {}, "network": {}}
        # CPU
        returncode, stderr, stdout = performance.get_cpu_performance()
        cpu_performance = stdout.replace("\n", "").replace("  ", " ").strip().split()
        performance_dict["CPU"] = {"usr": cpu_performance[0], "sys": cpu_performance[1], "usage": f"{100-int(cpu_performance[2])}",
                              "wai": cpu_performance[3], "stl": cpu_performance[4]}
        # memory
        returncode, stderr, stdout = performance.get_memory_performace()
        memory_performance = stdout.replace("\n", "").strip().split()
        performance_dict["memory"] = {"used": memory_performance[0], "free": memory_performance[1], "buff": memory_performance[2], "cache": memory_performance[3]}
        # disk
        returncode, stderr, stdout = performance.get_disk_performance()
        disk_performance = stdout.replace("\n", "").strip().split()
        performance_dict["disk"] = {"read": disk_performance[0], "writ": disk_performance[1]}
        # network
        returncode, stderr, stdout = performance.get_network_performance()
        network_performance = stdout.replace("\n", "").strip().split()
        performance_dict["network"] = {"recv": network_performance[0], "send": network_performance[1]}
        return performance_dict

    @staticmethod
    def container_performance():
        performance = DevicePerformance()
        performance_dict = []
        returncode, stderr, stdout = performance.get_docker_container_performance()
        for item in stdout.strip().split("\n"):
            performance_dict.append(json.loads(item))
        return performance_dict


def run(args):
    action = args.action
    performance = args.performance
    if action is not None:
        savop_root_dir = ensure_no_trailing_slash(args.dir)
        node_num = args.node_num
        host_signal_path = f"{savop_root_dir}/savop_run/this_config/active_signal.json"
        base_compose = f"{savop_root_dir}/savop_run/this_config/docker-compose.yml"
        base_topo = f"{savop_root_dir}/savop_run/this_config/topo.sh"
        base_node_num = node_num
        run_emulation = RunEmulation(root_dir=savop_root_dir, host_signal_path=host_signal_path,
                                     base_compose=base_compose, base_topo=base_topo,
                                     base_node_num=base_node_num)
        match action:
            case 'start':
                result = run_emulation.start()
            case 'stop':
                result = "SAVOP stop"
            case 'restart':
                result = "SAVOP restart"
    if performance is not None:
        match performance:
            case 'host':
                result = Minitor.host_performance()
            case 'container':
                result = Minitor.container_performance()
            case 'all':
                result = {"host_performance": "", "container_performance": ""}
                result["host_performance"] = Minitor.host_performance()
                result["container_performance"] = Minitor.container_performance()
    return json.dumps(result, indent=4)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="this scripts control SAVOP")
    operate_group = parser.add_argument_group("operate", "control the operation of SAVOP")
    operate_group.add_argument("-a", "--action", choices=["start", "stop", "restart"],
                        help="control SAVOP execution, only support three values: start, stop and restart")
    operate_group.add_argument("-d", "--dir", help="SAVOP root directory")
    operate_group.add_argument("-n", "--node_num", type=int, help="the count of the running container on the slave")

    monitor_group = parser.add_argument_group("monitor", "Monitor the operational status of SAVOP")
    monitor_group.add_argument("-p", "--performance", choices=["host", "container", "all"], help="monitor the performance "
                                                                                          "of machines or containers")
    args = parser.parse_args()
    result = run(args=args)
    if result is not None:
        print(result)
