#! /usr/bin/env python
# -*- coding: utf-8 -*-
"""
Author: liuyouyuan
Version: v2.0
Date: 2017/8/17
互金项目日志监控脚本。
"""

import os
import re
import time
import json
import sys
import requests
# 配置文件

# app用户和秘钥，发邮件需要携带
api_user = "*"
api_key = "*"
# 发件人
sender = "*"
# 收件人 {app}alarm@maillist.sendcloud.org
recipient = "{}*"
# 发邮件的api
mail_api = "http://~~"
# 短信接受者
sms_recipient = ['189**', '***']

# 监控的日志路径/cloud/data/log/{app}/...log或者{app}/.../..log
log_path = "/cloud/data/log"
# 日志告警级别
level = ["\[~~\]", "\[~~\]", " ~~ ", " ~~ "]
# 告警日志显示的行数前10行后20行：
row = 5
# ip存放文件
ip_path = "/etc/sysconfig/network-scripts/ifcfg-eth0"
# 主机名存放文件
host_path = "/proc/sys/kernel/hostname"

# 本脚本相关的配置
# 本脚本日志路径
my_log = "~~/logAlarm/"
# 将上面的日志路径软连接到本路径 ln -s my_log link
link = "/root/logs"
# 日志格式
log_format = "{} [~~日志监控脚本] [Type={}, Status={}, Content={}]\n"

# 短信告警配置：False 不发短信
is_sms = False

# 邮件格式
mail_body = """
=============== ERROR ABSTRACT ===============<br/>
    timeStamp:      {time_stamp}<br/>
    ServerName:     {hostname}<br/>
    ServerIP:       {ip}<br/>
    FailureLevel:   {level}<br/>
    App:            {app}<br/>
    LogFile:        {log_path}<br/>
=============================================<br/>
    Error Details:
<br/>
{error_detail}
<br/>
"""

class LogAlarm(object):

    def __init__(self):
        self.ip = self._iP()
        self.host = self._host()
        self.level_ = self.format_level()
        self.last_time = self.prev_minute()
        self.logs = self.search_logs()
        self.app = self.get_app()
        self.last_time = self.prev_minute()
        self.mail_log = None
        self.sms_log = None
        self.ready_dir()

    @staticmethod
    def _iP():
        """获取ip"""
        ip = None
        with open(ip_path, "r") as f:
            for line in f:
                if line.startswith("IPADDR"):
                    ip_li = line.split("=")
                    ip = ip_li[-1].split("\n")[0]
                    return ip
        return ip

    @staticmethod
    def _host():
        """获取主机名"""
        f = open(host_path, "r")
        host = f.read()
        f.close()
        return host

    def ready_dir(self):
        if not os.path.isdir(log_path):
            sys.exit()
        mid_path = os.path.join(my_log, time.strftime("%Y%m", time.localtime()))
        if not os.path.isdir(mid_path):
            os.makedirs(mid_path)
        path = "logAlarm-{0}.log".format(time.strftime("%Y%m%d", time.localtime()))
        self.mail_log = "%s/%s_mail_%s" % (mid_path, self.app, path)
        self.sms_log = "%s/%s_sms_%s" % (mid_path, self.app, path)
        if not os.path.islink(link):
            os.symlink(my_log, link)

    @staticmethod
    def search_logs():
        """获取当天的日志名称"""
        logs = list()
        for p, d, f in os.walk(log_path):
            path = p
            for _ in f:
                if re.search(".log$", _):
                    log = os.path.join(path, _)
                    logs.append(log)
        return logs

    def get_app(self):
        """获取app名称"""
        return self.logs[0].split('/')[4]

    @staticmethod
    def prev_minute():
        """格式化前一分钟时间2017-07-14 08:09"""
        before_minute = time.localtime(time.time() - 60)
        return time.strftime("%Y-%m-%d %H:%M", before_minute)

    @staticmethod
    def format_level():
        """告警级别大小写"""
        level_ = list()
        for _ in level:
            level_.append("{}|{}".format(_, _.upper()))
        return level_

    @staticmethod
    def get_index(pat1, pat2, filename):
        """返回日志中符合时间和告警级别的那条日志的索引"""
        with open(filename, "r") as f:
            index_li = []
            for index, line in enumerate(f):
                if re.search(pat1, line) and re.search(pat2, line):
                    index_li.append(index)
            return index_li

    @staticmethod
    def get_details(index, filename):
        """获取详细的错误日志，报错的前5行和后10行。"""
        if not index:
            return ""
        else:
            low = index[0]
            high = index[-1]
            f = open(filename, "r")
            li = f.readlines()
            f.close()
            length = len(li)
            if (low - row) > 0 and (high + 2 * row) < length:
                lis = li[(low - row): (high + 2 * row)]
            elif (low - row) <= 0 and (high + 2 * row) < length:
                lis = li[: (high + 2 * row)]
            elif (low - row) > 0 and (high + 2 * row) >= length:
                lis = li[(low - row):]
            else:
                lis = li
            return "".join(lis)

    @staticmethod
    def sms_details(lev, strings):
        """获取短信摘要信息"""
        st = "%s.{10}|%s.{10}" % (lev, lev.upper())
        ret = re.findall(st, strings)
        return ret

    def sms_alarm(self, lev, abs):
        """短信告警"""
        import Qcloud.Sms.sms as SmsSender
        app_id = 1400034053
        app_key = "a81a7ca7c0682cde1418de70b7713747"
        templ_id = 25890

        sms_body = "{}({}),{},{},{}".format(self.ip, self.host, self.app, lev, abs)
        params = sms_body.split(",")  # 这个列表只允许4个元素
        multi_sender = SmsSender.SmsMultiSender(app_id, app_key)
        # 发短信
        result = multi_sender.send_with_param("86", sms_recipient, templ_id, params, "", "", "")
        rsp = json.loads(result)
        status = rsp["errmsg"]
        # 写日志
        t = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        cont = "{}{}".format(",".join(sms_recipient), sms_body)
        content = log_format.format(t, "sms", status, cont)
        self.write_log(self.sms_log, content)

    @staticmethod
    def write_log(f, cont):
        """写日志"""
        f = open(f, "a+")
        f.write(cont)
        f.close()

    def mail_alarm(self, lev, html):
        """发邮件"""
        params = {
            "apiUser": api_user,
            "apiKey": api_key,
            "to": recipient.format(self.app),
            "from": sender,
            "fromName": "互金监控报警",
            "subject": "日志监控报警[{0}:{1}({2}):{3}]".format(self.app, self.ip, self.host, lev),
            "useAddressList": True,
            "html": html,
        }

        res = requests.post(url=mail_api, data=params)
        status = res.status_code
        return status

    def run(self):
        for log in self.logs:
            print "log:", log
            for i in range(4):
                r = self.get_index(self.last_time, self.level_[i], log)
                if r:
                    detail = self.get_details(r, log)
                    self.mail_handle(detail, log, i)
                    if i < 2:
                        self.sms_handle(detail, i)

    def mail_handle(self, item, log, num):
        item_ = self.sub_html(item)
        body1 = mail_body.format(
            time_stamp=self.last_time,
            hostname=self.host,
            ip=self.ip,
            level=level[num],
            log_path=log,
            app=self.app,
            error_detail=re.sub('\n', '<br/>', item_),
        )
        # 发邮件并返回状态
        status = self.mail_alarm(level[num], body1)
        t = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        cont = log_format.format(t, "mail", status, item)
        # 写日志
        self.write_log(self.mail_log, cont)

    def sms_handle(self, item, num):
        if not is_sms:
            pass
        else:
            abs = self.sms_details(level[num], item)
            for j in abs:
                self.sms_alarm(level[num], j)

    @staticmethod
    def sub_html(string):
        a = ["fatal", "critical", "error", "exception"]
        for i in a:
            new = "<span style='color: red'>%s</span>" % i
            string = re.sub("{}|{}".format(i, i.upper()), new, string)
        return string


if __name__ == '__main__':
    obj = LogAlarm()
    obj.run()