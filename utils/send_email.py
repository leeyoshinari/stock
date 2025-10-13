#!/usr/bin/env python
# -*- coding:utf-8 -*-
# Author: leeyoshinari

import smtplib
from email.header import Header
from email.mime.text import MIMEText


def sendEmail(msg):
    """
     Send email
    :param msg: email content
    :return:
    """
    sender_name = 'Auto'
    sender_email = 'ly@outlook.com'
    receiver_name = 'Buy'
    receiver_email = ['1583@qq.com']
    password = 'io'
    host = 'smtp.office365.com'

    subject = '股票推荐'
    s = "{0}".format(msg)

    message = MIMEText(s, 'plain', 'utf-8')  # Chinese required 'utf-8'
    message['Subject'] = Header(subject, 'utf-8')
    message['From'] = Header(sender_name, 'utf-8')
    message['To'] = Header(receiver_name, 'utf-8')

    smtp = smtplib.SMTP(host, 587)
    smtp.starttls()
    smtp.login(sender_email, password)
    smtp.sendmail(sender_email, receiver_email, message.as_string())
    smtp.quit()


if __name__ == '__main__':
    sendEmail(1)
