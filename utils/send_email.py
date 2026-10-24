#!/usr/bin/env python
# -*- coding:utf-8 -*-
# Author: leeyoshinari

import smtplib
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr
from settings import SENDER_EMAIL, RECEIVER_EMAIL, EMAIL_PASSWORD


def sendEmail(subject: str, msg: str, flag: str = None):
    """Send email \n
    :param subject: email title
    :param msg: email content
    :param flag: default send email to myself, other send to all
    :return:
    """
    if flag:
        receiver = RECEIVER_EMAIL
    else:
        receiver = SENDER_EMAIL
    sender_name = 'Recommend Stocks'
    sender_email = SENDER_EMAIL
    receiver_name = 'BuyBuy'
    receiver_email = receiver.split(',')
    host = 'smtp.qq.com'

    if len(msg) > 999:
        message = MIMEText(msg, 'html', 'utf-8')
    else:
        message = MIMEText(msg, 'plain', 'utf-8')  # Chinese required 'utf-8'
    message['Subject'] = Header(subject, 'utf-8')
    message['From'] = formataddr((sender_name, sender_email))
    message['To'] = ", ".join([formataddr((receiver_name, addr)) for addr in receiver_email])

    smtp = smtplib.SMTP_SSL(host, 465)
    smtp.login(sender_email, EMAIL_PASSWORD)
    smtp.sendmail(sender_email, receiver_email, message.as_string())
    smtp.quit()


if __name__ == '__main__':
    sendEmail("测试一下")
