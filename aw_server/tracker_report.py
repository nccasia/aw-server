from datetime import date, datetime, timedelta, time
from aw_core.log import setup_logging
from aw_datastore import get_storage_methods
from aw_datastore.datastore import Datastore
from aw_query import query2
import requests
import logging
import pytz
import iso8601
logger = logging.getLogger('REPORT')


def _dt_is_tzaware(dt: datetime) -> bool:
    return dt.tzinfo is not None and dt.tzinfo.utcoffset(dt) is not None


def str_to_date(day: str = "") -> date:
    '''Convert string `day` (format: dd/MM/YYYY or YYYY/MM/dd) to type date
    Return today if day is not in the right format 
    '''
    try:
        if day:
            day = list(map(int, day.split("/")))
            # format: YYYY/MM/dd
            if day[0] > 1000:
                date = datetime(day[0], day[1], day[2]).date()
            # format: dd/MM/YYYY
            else:
                date = datetime(day[2], day[1], day[0]).date()
            return date
        else:
            date = datetime.combine(datetime.now().date(), time()).date()
            return date
    except Exception as e:
        logger.error(f"Error in formating {day}: {e}")
        return datetime.combine(datetime.now().date(), time()).date()

def format_timedelta(time: timedelta) -> str:
    total_seconds = time.total_seconds()
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    return f"{int(hours)}h{int(minutes)}m{int(seconds)}s"


def cal_timeperiods(day: str = ""):
    date = str_to_date(day)
    daystart = datetime.combine(date, time())
    dayend = daystart + timedelta(days=1)
    timeperiods = [(daystart.astimezone(), dayend.astimezone())]

    for start, stop in timeperiods:
        try:
            assert _dt_is_tzaware(start)
            assert _dt_is_tzaware(stop)
        except AssertionError:
            raise ValueError("start/stop needs to have a timezone set")

    _timeperiods = [
        "/".join([start.replace(tzinfo=pytz.utc).astimezone(pytz.timezone('Asia/Saigon')
                                                            ).replace(hour=6).isoformat(), end.astimezone(pytz.timezone('Asia/Saigon')).replace(hour=0).isoformat()])
        for start, end in timeperiods
    ]

    return _timeperiods


class TrackerReport:
    def __init__(self, db, query2, app=None) -> None:
        self.db = db
        self.app = app
        self.query2 = query2

    def report_user(self, email: str, day: str = None, wfh=True):
        # TODO: FIX ME
        # if day:
        #   day = list(map(int, day.split("/")))
        #   date = datetime(day[0], day[1], day[2]).date()
        #   _report = self.db.storage_strategy.get_report(email=email, day=date)
        #   if _report != None:
        #     _report['date'] = _report['date'].isoformat()
        #     return _report
        # else:
        #   date = datetime.combine(datetime.now().date(), time()).date()

        try:
            # Try getting report from database
            try:
                date = str_to_date(day)
                _report = self.db.storage_strategy.get_report(email=email,day=date)
                if _report:
                    # TODO: FIX ME Converting float to timedelta because storing in database as timedelta
                    _report["str_active_time"] = format_timedelta(timedelta(seconds=_report['active_time'])) 
                    _report["str_spent_time"] = format_timedelta(timedelta(seconds=_report['spent_time']))
                    _report["str_call_time"] = format_timedelta(timedelta(seconds=_report['call_time']))
                    _report["date"] = day
                    _report.pop('id')
                    return _report
            except Exception as e:
                logger.info(f"Error when getting Report Model: {e}") 
            # No report found, process as usual
            timeperiods = cal_timeperiods(day)
            try:
                spent_time = self.get_spent_time(email, timeperiods)
                call_time = self.get_call_time(email, timeperiods)
            except Exception as e:
                logger.info(f"Error {e}")
                spent_time = self.get_spent_time(
                    f"{email}.ncc", timeperiods)
                call_time = self.get_call_time(
                    f"{email}.ncc", timeperiods)

            rec = {
                "email": email,
                "spent_time": spent_time.total_seconds(),
                "call_time": call_time.total_seconds(),
                "active_time": sum([spent_time, call_time], timedelta()).total_seconds(),
                "str_active_time": format_timedelta(sum([spent_time, call_time], timedelta())),
                "str_spent_time": format_timedelta(spent_time),
                "str_call_time": format_timedelta(call_time),
                "date": day,
                "wfh": wfh
            }
            # ! If getting report of on going day, the report is lock on the first time called getting report. Switching to using cronjob
            # logger.info(f"rec: {rec}")
            # self.db.storage_strategy.save_report(rec)
            return rec
        except Exception as e:
            rec = {
                "email": email,
                "spent_time": 0,
                "call_time": 0,
                "active_time": 0,
                "str_active_time": '0h0m0s',
                "str_spent_time": '0h0m0s',
                "str_call_time": '0h0m0s',
                "date": day,
                "wfh": wfh
            }
            logger.error(f"Error: {e}")
            return rec
    def get_call_time(self, email, timeperiods) -> timedelta:
        query = []
        query.append(
            f"events = flood(query_bucket(find_bucket(\"aw-watcher-window_{email}\")));")
        query.append(
            "events = filter_keyvals(events, \"title\", [\"KomuTracker - Google Chrome\"]);")
        query.append(
            f"afk = query_bucket(find_bucket(\"aw-watcher-afk_{email}\"));")
        query.append("afk = filter_keyvals(afk, \"status\", [\"afk\"]);")
        query.append(f"afk = merge_events(afk);")
        query.append(f"afk = flood(afk);")
        query.append("events = filter_period_intersect(events, afk);")
        query.append("duration = sum_durations(events);")
        query.append("RETURN = {\"duration\": duration, \"events\": events};")

        result = []
        if self.query2:
            result = self.query2(
                "report-call-time", query, timeperiods, False
            )
        else:
            result = self.app.api.query2(
                "report-call-time", query, timeperiods, False
            )

        total_call_time = result[0]["duration"]
        return total_call_time

    def get_spent_time(self, email, timeperiods) -> timedelta:
        # ! Changing to only consider not_afk, ignore window_events
        query = []
        query.append(
            f"not_afk = query_bucket(\"aw-watcher-afk_{email}\");")
        query.append(
            "not_afk = filter_keyvals(not_afk, \"status\", [\"not-afk\"]);")
        query.append("not_afk_process = merge_events(not_afk);")
        query.append("not_afk_process = flood(not_afk_process);")
        query.append("duration = sum_durations(not_afk_process);")
        query.append("RETURN = {\"duration\": duration};")

        result = []
        if self.query2:
            result = self.query2(
                "report-call-time", query, timeperiods, False
            )
        else:
            result = self.app.api.query2(
                "report-call-time", query, timeperiods, False
            )
        total_duration = result[0]["duration"]
        return total_duration

    def report(self, day: str = None, save_to_db = False):
        def to_utc_midnight(day: datetime.date):
            return datetime.combine(day, time.min).replace(tzinfo=pytz.UTC)
        date = to_utc_midnight(str_to_date(day))
        # print timezone info of date
        logger.info(f"Running tracker_report on day {date}")
        # timesheetdate = date.strftime("%Y-%m-%d")
        # api_url = f"http://timesheetapi.nccsoft.vn/api/services/app/Public/GetUserWorkFromHome?date={timesheetdate}"
        # api_key_secret = "sksCCsksCC"
        # r = requests.get(api_url, headers={"securitycode": api_key_secret}, verify=False)

        users_use_tracker = self.db.storage_strategy.get_use_tracker(date)
        report_users = {}
        for user in users_use_tracker:
            user['wfh'] = False
            email = user["email"].split("@")[0]
            report_users[email] = user

        # result = r.json()["result"]
        # for user in result:
        #     email = user["emailAddress"].split("@")[0]

        #     try:
        #         report_users[email]['wfh'] = True
        #     except:
        #         user['wfh'] = True
        #         report_users[email] = user

        response = []
        for email in report_users:
            rec = self.report_user(
                email=email, wfh=report_users[email]['wfh'], day=day)
            if save_to_db:
                self.db.storage_strategy.save_report(rec)
            rec['spent_time'] = str(timedelta(seconds=rec["spent_time"]))
            rec["call_time"] = str(timedelta(seconds=rec["call_time"]))
            rec["active_time"] = str(timedelta(seconds=rec["active_time"]))
            response.append(rec)
        return response

def report_on_dates(day: datetime = datetime.today(), duration: int = 1):
    print(f"Running report from {day - timedelta(days = duration)} to {day}")
    setup_logging("Cronjob",
        testing=False,
        verbose=False,
        log_stderr=False,
        log_file=False,
        log_file_json=False,)
    storage_methods = get_storage_methods()
    storage_method = storage_methods['peewee']
    end_date = datetime.strftime(day, '%Y/%m/%d')
    db = Datastore(storage_method, testing=False)
    def self_query2(name, query, timeperiods, cache):
            result = []
            for timeperiod in timeperiods:
                period = timeperiod.split("/")[
                    :2
                ]  # iso8601 timeperiods are separated by a slash
                starttime = iso8601.parse_date(period[0])
                endtime = iso8601.parse_date(period[1])
                query = str().join(query)
                result.append(query2.query(name, query, starttime, endtime, db))
            return result
    tracker_report = TrackerReport(db=db, query2=self_query2)
    dates = [datetime.strftime(day - timedelta(days=idx + 1), '%Y/%m/%d') for idx in range(duration)]
    for date in dates:
        try:
            print(f"Start running tracker_report on {date}")
            reports = tracker_report.report(date, save_to_db=True)
            logger.info(f"Running tracker_report on day {date}")
            print(f"Finish running tracker_report on day {date}: generated {len(reports)} total reports ") 
        except Exception as e:
            print(f"Day: {date} generate error: \n{e}")
            break
    print(f"Finish reporting") 
    # print(f"Report {reports}")  

if __name__ == '__main__':
    # stop_date = datetime(2022,6,10)
    # report_on_dates(stop_date, 100)
    report_on_dates()