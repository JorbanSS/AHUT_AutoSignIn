import time


def get_time() -> dict:
    now = time.localtime()
    date = time.strftime("%Y-%m-%d", now)
    current_time = time.strftime("%H:%M:%S", now)
    full_datetime = time.strftime("%Y-%m-%d %H:%M:%S", now)
    week_list = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    weekday = week_list[now.tm_wday]
    return {"date": date, "time": current_time, "weekday": weekday, "full": full_datetime}
