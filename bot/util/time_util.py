from datetime import datetime, timedelta

from pytz import timezone
from bot.util.human import *


def get_time_until_minute():
    return 60 - datetime.now().second


def get_utc():
    utc = timezone('UTC')
    return utc.localize(datetime.now()).replace(tzinfo=None)


def round_time(time_object=None, round_to=30 * 60):
    """
    Round a datetime object to any time lapse in seconds
    dt : datetime.datetime object, default now.
    roundTo : Closest number of seconds to round to, default 1 minute.
    Author: Thierry Husson 2012 - Use it as you want but don't blame me.
    """
    if time_object is None:
        zone = timezone('UTC')
        utc = timezone('UTC')
        time_object = utc.localize(datetime.now())
        time_object = time_object.astimezone(zone)

    stripped_dt = time_object.replace(tzinfo=None, hour=0, minute=0, second=0)
    seconds = (time_object.replace(tzinfo=None) - stripped_dt).seconds
    rounding = (seconds + round_to / 2) // round_to * round_to
    return time_object + timedelta(0, rounding - seconds, -time_object.microsecond)


def _two_digits(digit):
    digit = str(digit)
    if len(digit) == 1:
        return '0' + digit
    return digit


def ms_to_time(ms):
    total_seconds = ms // 1000
    total_minutes = total_seconds // 60
    total_hours = total_minutes // 60
    seconds = _two_digits(total_seconds % 60)
    minutes = _two_digits(total_minutes % 60)
    hours = _two_digits(total_hours % 24)
    if hours != '00':
        return f'{hours}:{minutes}:{seconds}'
    return f'{minutes}:{seconds}'


def ms_to_human(ms):
    total_seconds = ms // 1000
    total_minutes = total_seconds // 60
    total_hours = total_minutes // 60
    days = total_hours // 24
    seconds = total_seconds % 60
    minutes = total_minutes % 60
    hours = total_hours % 24
    text = []
    if days != 0:
        text.append(f'{days} {plural(days, "day")}')
    if hours != 0:
        text.append(f'{hours} {plural(hours, "hour")}')
    if minutes != 0:
        text.append(f'{minutes} {plural(minutes, "minute")}')
    if seconds != 0:
        text.append(f'{seconds} {plural(seconds, "second")}')
    if len(text) == 0:
        return 'No duration'
    return combine_list_and(text)
