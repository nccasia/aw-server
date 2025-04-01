from datetime import datetime, time, timedelta
import aw_client
from aw_client import queries
import pymongo
import requests

myclient = pymongo.MongoClient("mongodb://localhost:27017/")
mydb = myclient["komubot"]
mycol = mydb["komu_tracker_spent_time"]

def get_call_time_simple(aw, email, daystart, dayend):
    events = aw.get_events(f"aw-watcher-window_{email}", start=daystart, end=dayend)
    events = [e for e in events if "title" in e.data and e.data["title"] == "KomuTracker - Google Chrome"]
    komutracker_duration = sum((e.duration for e in events), timedelta())
    
    return komutracker_duration.total_seconds()

def get_call_time(aw, email, timeperiods):
    query = f"""
    events = flood(query_bucket(find_bucket("aw-watcher-window_{email}")));
    events = filter_keyvals(events, "title", ["KomuTracker - Google Chrome"]);
    afk = flood(query_bucket(find_bucket("aw-watcher-afk_{email}")));
    afk = filter_keyvals(afk, "status", ["afk"]);
    events = filter_period_intersect(events, afk);
    duration = sum_durations(events);
    RETURN = {{"events": events, "duration": duration}};
    """
    events = aw.query(query=query, timeperiods=timeperiods)
    total_duration = events[0]["duration"]

    return total_duration

def get_spent_time(aw, email, timeperiods):
    canonicalQuery = queries.canonicalEvents(
        queries.DesktopQueryParams(
            bid_window=f"aw-watcher-window_{email}",
            bid_afk=f"aw-watcher-afk_{email}",
        )
    )
    query = f"""
    {canonicalQuery}
    duration = sum_durations(events);
    RETURN = {{"events": events, "duration": duration}};
    """

    events = aw.query(query=query, timeperiods=timeperiods)
    total_duration = events[0]["duration"]
    return total_duration
    

def main():
    reportdata = []
    users = []

    try:
        api_url = "http://timesheetapi.nccsoft.vn/api/services/app/Public/GetUserWorkFromHome"
        api_key_secret = "sksCCsksCC"
        r = requests.get(api_url, headers={"securitycode": api_key_secret})
        
        for user in r.json()["result"]:
            email = user["emailAddress"].split("@")[0]
            users.append(email)
    except Exception as e:
        print(e)
        pass

    # You need to set testing=False if you're going to run this on your normal instance
    aw = aw_client.ActivityWatchClient("report-spent-time", testing=False)
    daystart = datetime.combine(datetime.now().date(), time())
    dayend = daystart + timedelta(days=1)

    timeperiods = [(daystart.astimezone(), dayend.astimezone())]
    
    for email in users:
        try:            
            try:
                total_duration = get_spent_time(aw, email, timeperiods)
            except:
                total_duration = get_spent_time(aw, f"{email}.ncc", timeperiods)                

            # add time for afk but 
            komutracker_duration = get_call_time_simple(aw, email, daystart, dayend)
            
            rec = { 
                    "email": email, 
                    "spent_time": total_duration,
                    "call_time" : komutracker_duration,
                    "date" : datetime.now().strftime("%m/%d/%Y"), 
                    "wfh": True
                }
            reportdata.append(rec)

        except Exception as e:
            rec = { 
                    "email": email, 
                    "spent_time": 0,
                    "call_time" : 0,
                    "date" : datetime.now().strftime("%m/%d/%Y"), 
                    "wfh": True
                }
            reportdata.append(rec)
            print(f"Error: {e}")

    mycol.insert_many(reportdata)
    #print(reportdata)

if __name__ == "__main__":
    main()    
