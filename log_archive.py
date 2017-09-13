#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Author: "Zing-p"
# Date: 2017/9/13
#! /usr/bin/env python2
# -*- coding: utf-8 -*-
# Author: "lyy"
# Date: 2017/9/12
"""
互金日志归档v1.0版
功能：每天凌晨两点打包上传昨天的日志
环境:python2
部署：
(1)确保pip安装，没有的话请先安装pip
(2)pip install cassdk
(3)pip install pyyaml
(4)crontab -e
    录入：
    # 互金日志归档python2脚本,定时任务每天凌晨两点
    0 2 * * * python2 /cloud/data/scripts/archive/log_archive.py >/dev/null &
    保存退出
"""

import os
import re
import time
from cas.client import CASClient
from cas.api import CasAPI
from cas.vault import Vault
import tarfile
import logging

# app日志路径
app_log_path = "/~~/log/"
# nginx日志路径
nginx_log_path = "~~/nginx/logs/"
# 打包路径
app_tar_path = "~~/log/tar/"
nginx_tar_path = "/~~nginx/logs/tar/"

# ip存放文件
ip_path = "/etc/sysconfig/network-scripts/ifcfg-eth0"

# 密钥相关信息
app_id = ""
secret_id = ""
secret_key = ""
remote_host = ""

# 日志信息配置
my_log = "~~/logArchive/"    # 日志路径
if not os.path.isdir(my_log):
    os.makedirs(my_log)
today = time.strftime("%Y-%m", time.localtime())
log = "{}{}.log".format(my_log, today)
logging.basicConfig(filename=log,
                    format='%(asctime)s %(name)s %(levelname)s : %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S ',
                    level=20)
logger = logging.getLogger("[**日志归档程序]")
log_format = "[type={},status={},[id={},file={},vault={},content={}]]"


class LogArchive(object):
    def __init__(self, remote_host_, app_id_, secret_id_, secret_key_):

        self.client = CASClient(remote_host_, app_id_, secret_id_, secret_key_)
        self.cas_api = CasAPI(self.client)
        self.ip = self.get_iP()
        self.yesterday = time.localtime(time.time() - 24*60*60)

        self.have_nginx = False
        self.have_app = False
        self.app_files = None
        self.nginx_files = None

    @staticmethod
    def tar_bz2(file_list, tar_file):
        """压缩文件"""
        tf = tarfile.open(tar_file, "w:bz2")
        for name in file_list:
            tf.add(name)
        tf.close()
        return tar_file

    @staticmethod
    def get_log_files(log_path, pattern):
        """根据模式获取指定目录下的日志，并返回日志列表"""
        app_log_files = list()
        for p, d, f in os.walk(log_path):
            path = p
            for _ in f:
                if re.search(pattern, _):
                    log = os.path.join(path, _)
                    app_log_files.append(log)
        return app_log_files

    def get_app_and_nginx_files(self):
        """获取要被打包的日志列表"""
        if self.have_app:
            app_pattern = time.strftime("%Y%m%d", self.yesterday)[2:]
            # app_pattern = "170911"
            self.app_files = self.get_log_files(app_log_path, app_pattern)
        if self.have_nginx:
            nginx_pattern = time.strftime("%Y-%m-%d", self.yesterday)
            # nginx_pattern = "2017-09-11"
            self.nginx_files = self.get_log_files(nginx_log_path, nginx_pattern)

    def detect(self, app_log, nginx_log):
        """
        检查本机的一些日志路径是否存在，并创建需要的路径
        app或nginx日志；打包路径
        """
        if os.path.isdir(app_log):
            self.have_app = os.listdir(app_log)[0]
        if os.path.isdir(nginx_log):
            self.have_nginx = True
        if self.have_app:
            if not os.path.isdir(app_tar_path):
                os.makedirs(app_tar_path)
        if self.have_nginx:
            if not os.path.isdir(nginx_tar_path):
                os.makedirs(nginx_tar_path)

    @staticmethod
    def get_iP():
        """获取ip"""
        ip = None
        with open(ip_path, "r") as f:
            for line in f:
                if line.startswith("IPADDR"):
                    ip_li = line.split("=")
                    ip = ip_li[-1].split("\n")[0]
                    return ip.strip("'")
        return ip

    @staticmethod
    def get_nginx_vault(file_li):
        """获取本机nginx日志所属"""
        prev_vault = ""
        for i in file_li:
            name = i.split("/")[-1]
            item_li = name.split(".")
            if item_li[1] == "******":
                prev_vault = item_li[0]
                break
        return prev_vault

    def get_app_tar_name(self):
        # appname_ip_日期戳.压缩扩展名命名
        tim = time.strftime("%Y-%m-%d", self.yesterday)
        app_tar_name = "{}_{}_{}.tar.bz2".format(self.have_app, self.ip, tim)
        return app_tar_name

    def get_nginx_tar_name(self):
        tim = time.strftime("%Y-%m-%d", self.yesterday)
        nginx_tar_name = "{}{}.tar.bz2".format(self.ip, tim)
        return nginx_tar_name

    def run(self):
        # 准备工作，各种路径，包括本脚本的日志
        self.detect(app_log_path, nginx_log_path)
        self.get_app_and_nginx_files()
        # 找到要打包的日志，打包，打包失败要记录日志
        if self.have_nginx:
            self.put_nginx_log()
        if self.have_app:
            self.put_app_log()

    def put_nginx_log(self):
        nginx_tar = "{}{}".format(nginx_tar_path, self.get_nginx_tar_name())
        self.tar_bz2(self.nginx_files, nginx_tar)
        nginx_vault = "{}nginx".format(self.get_nginx_vault(self.nginx_files))
        self.put_log(nginx_tar, nginx_vault)

    def put_app_log(self):
        app_tar = "{}{}".format(app_tar_path, self.get_app_tar_name())
        self.tar_bz2(self.app_files, app_tar)
        self.put_log(app_tar, self.have_app)

    def put_log(self, tar_file, vault_name):
        """上传日志"""
        size_bytes = os.path.getsize(tar_file)
        size = float(size_bytes) / 1024 / 1024
        vault = Vault.get_vault_by_name(self.cas_api, vault_name)
        if size < 100.0:
            archive_id = vault.upload_archive(tar_file)
            if archive_id:
                msg = log_format.format("upload", 0, archive_id, tar_file, vault_name, "")
                logger.info(msg)
            else:
                msg = log_format.format("upload", 1, "", tar_file, vault_name, "")
                logger.error(msg)
            # print "小于100M的ID：", archive_id
        else:
            try:
                uploader = vault.initiate_multipart_upload(tar_file)
                archive_id = uploader.start()
                if archive_id:
                    msg = log_format.format("upload", 0, archive_id, tar_file, vault_name, "")
                    logger.info(msg)
                else:
                    msg = log_format.format("upload", 1, uploader.id, tar_file, vault_name, "")
                    logger.error(msg)
                # print "大于100M的ID：", archive_id
            except Exception as e:
                msg = log_format.format("upload", 1, uploader.id, tar_file, vault_name, e)
                logger.error(msg)

                # 如果上述multipart任务上传失败，则可以使用下列方法进行断点续传，
                # 其中recover_uploader方法的参数，是待续传的uploader对象的ID
                uploader = vault.recover_uploader(uploader.id)
                uploader.resume(tar_file)
                msg = log_format.format("upload", 0, uploader.id, tar_file, vault_name, "")
                logger.info(msg)
        os.remove(tar_file)


if __name__ == '__main__':
    obj = LogArchive(remote_host, app_id, secret_id, secret_key)
    obj.run()



