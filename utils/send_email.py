#!/usr/bin/env python
# -*- coding:utf-8 -*-
# Author: leeyoshinari

import smtplib
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr


def sendEmail(sender, receiver, password, msg):
    """
     Send email
    :param msg: email content
    :return:
    """
    sender_name = 'Recommend Stocks'
    sender_email = sender
    receiver_name = 'BuyBuy'
    receiver_email = receiver.split(',')
    host = 'smtp.qq.com'

    subject = '股票推荐'
    s = "{0}".format(msg)

    message = MIMEText(s, 'plain', 'utf-8')  # Chinese required 'utf-8'
    message['Subject'] = Header(subject, 'utf-8')
    message['From'] = formataddr((sender_name, sender_email))
    message['To'] = ", ".join([formataddr((receiver_name, addr)) for addr in receiver_email])

    smtp = smtplib.SMTP_SSL(host, 465)
    smtp.login(sender_email, password)
    smtp.sendmail(sender_email, receiver_email, message.as_string())
    smtp.quit()


if __name__ == '__main__':
    sendEmail("测试一下\n小米\t20.21\n没制止\t34.5")
