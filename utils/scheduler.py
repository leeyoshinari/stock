#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import datetime
# from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.schedulers.background import BackgroundScheduler


scheduler = BackgroundScheduler()


def get_schedule_time(hour: int = 5, minute: int = 20, second: int = 20):
    now = datetime.datetime.now()
    scheduled_time = now.replace(hour=hour, minute=minute, second=second, microsecond=0)
    if now < scheduled_time:
        return scheduled_time
    else:
        tomorrow = now + datetime.timedelta(days=1)
        return tomorrow.replace(hour=hour, minute=minute, second=second, microsecond=0)


# scheduler.add_job(remove_tmp_folder, 'cron', hour=5, minute=20, second=21)
