from datetime import date, datetime, timedelta, time
import requests
import logging
import pytz

logger = logging.getLogger('REPORT')


def _dt_is_tzaware(dt: datetime) -> bool:
    return dt.tzinfo is not None and dt.tzinfo.utcoffset(dt) is not None


def str_to_date(day: str = "") -> date:
    try:
        if day:
            day = list(map(int, day.split("/")))
            date = datetime(day[2], day[1], day[0]).date()
            return date
        else:
            date = datetime.combine(datetime.now().date(), time()).date()
            return date
    except:
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
                                                            ).isoformat(), end.astimezone(pytz.timezone('Asia/Saigon')).isoformat()])
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
            timeperiods = cal_timeperiods(day)
            try:
                spent_time = self.get_spent_time(email, timeperiods)
                call_time = self.get_call_time(email, timeperiods)
            except:
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
            print(f"Error: {e}")
            return rec

    def get_call_time(self, email, timeperiods) -> timedelta:
        query = []
        query.append(
            f"events = flood(query_bucket(find_bucket(\"aw-watcher-window_{email}\")));")
        query.append(
            "events = filter_keyvals(events, \"title\", [\"KomuTracker - Google Chrome\"]);")
        query.append(
            f"afk = flood(query_bucket(find_bucket(\"aw-watcher-afk_{email}\")));")
        query.append("afk = filter_keyvals(afk, \"status\", [\"afk\"]);")
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
        
        events = result[0]['events']
        events_obj = {}
        for event in events:
           events_obj[event['id']] = event
        # logger.info(events[0]['timestamp'].isoformat())
        event_durations = []
        for event in events_obj:
            event_durations.append(events_obj[event]['duration'])
        total_call = sum(duration.total_seconds() for duration in event_durations)
        logger.info(f"total call: {total_call}")
        logger.info(len(event_durations))
        events_durations = sum(event['duration'].total_seconds() for event in events)
        logger.info(events_durations)
        # logger.info(len(events))
        return timedelta(seconds=total_call)
        # return total_call_time

    def get_spent_time(self, email, timeperiods) -> timedelta:
        query = []
        query.append(
            f"events = flood(query_bucket(\"aw-watcher-window_{email}\"));")
        query.append(
            f"not_afk = flood(query_bucket(\"aw-watcher-afk_{email}\"));")
        query.append(
            "not_afk = filter_keyvals(not_afk, \"status\", [\"not-afk\"]);")
        query.append("browser_events = [];")
        query.append(
            "audible_events = filter_keyvals(browser_events, \"audible\", [true]);")
        query.append("not_afk = period_union(not_afk, audible_events);")
        query.append("events = filter_period_intersect(events, not_afk);")
        query.append("events = categorize(events, [[[\"Work\"],{\"type\":\"regex\",\"regex\":\"Google Docs|libreoffice|ReText|xlsx|docx|json|mstsc|Remote Desktop|Terminal\"}],[[\"Work\",\"Programming\"],{\"type\":\"regex\",\"regex\":\"GitHub|Stack Overflow|BitBucket|Gitlab|vim|Spyder|kate|Ghidra|Scite|Jira|Visual Studio|Mongo|cmd\"}],[[\"Work\",\"Programming\",\"IDEs\"],{\"type\":\"regex\",\"regex\":\"deven|code|idea64\",\"ignore_case\":true}],[[\"Work\",\"Programming\",\"Others\"],{\"type\":\"regex\",\"regex\":\"Bitbucket|gitlab|github|mintty|pgadmin\",\"ignore_case\":true}],[[\"Work\",\"3D\"],{\"type\":\"regex\",\"regex\":\"Blender\"}],[[\"Media\",\"Games\"],{\"type\":\"regex\",\"regex\":\"Minecraft|RimWorld\"}],[[\"Media\",\"Video\"],{\"type\":\"regex\",\"regex\":\"YouTube|Plex|VLC\"}],[[\"Media\",\"Social Media\"],{\"type\":\"regex\",\"regex\":\"reddit|Facebook|Twitter|Instagram|devRant\",\"ignore_case\":true}],[[\"Media\",\"Music\"],{\"type\":\"regex\",\"regex\":\"Spotify|Deezer\",\"ignore_case\":true}],[[\"Comms\",\"IM\"],{\"type\":\"regex\",\"regex\":\"Messenger|Telegram|Signal|WhatsApp|Rambox|Slack|Riot|Discord|Nheko|Teams|Skype\",\"ignore_case\":true}],[[\"Comms\",\"Email\"],{\"type\":\"regex\",\"regex\":\"Gmail|Thunderbird|mutt|alpine\"}]]);")
        query.append("duration = sum_durations(events);")
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

    def report(self, day: str = None):
        date = str_to_date(day)

        timesheetdate = date.strftime("%Y-%m-%d")
        api_url = f"http://timesheetapi.nccsoft.vn/api/services/app/Public/GetUserWorkFromHome?date={timesheetdate}"
        api_key_secret = "sksCCsksCC"
        r = requests.get(api_url, headers={"securitycode": api_key_secret})

        users_use_tracker = self.db.storage_strategy.get_use_tracker()
        report_users = {}
        for user in users_use_tracker:
            user['wfh'] = False
            email = user["email"].split("@")[0]
            report_users[email] = user

        result = r.json()["result"]
        for user in result:
            email = user["emailAddress"].split("@")[0]

            try:
                report_users[email]['wfh'] = True
            except:
                user['wfh'] = True
                report_users[email] = user

        response = []
        for email in report_users:
            rec = self.report_user(
                email=email, wfh=report_users[email]['wfh'], day=day)
            rec['spent_time'] = str(timedelta(seconds=rec["spent_time"]))
            rec["call_time"] = str(timedelta(seconds=rec["call_time"]))
            rec["active_time"] = str(timedelta(seconds=rec["active_time"]))
            response.append(rec)
            # self.db.storage_strategy.save_report(rec)

        return response
