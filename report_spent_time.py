from datetime import datetime, time, timedelta
import aw_client
import pymongo
import requests

myclient = pymongo.MongoClient("mongodb://localhost:27017/")
mydb = myclient["komubot"]
mycol = mydb["komu_tracker_spent_time"]

def main():
    trackdata = []
    reportdata = []
    users = []
    
    api_url = "http://timesheetapi.nccsoft.vn/api/services/app/Public/GetUserWorkFromHome"
    api_key_secret = "sksCCsksCC"
    r = requests.get(api_url, headers={"securitycode": api_key_secret})
    
    for user in r.json()["result"]:
        email = user["emailAddress"].split("@")[0]
        users.append(email)
    
    # You need to set testing=False if you're going to run this on your normal instance
    aw = aw_client.ActivityWatchClient("report-spent-time", testing=False)

    buckets = aw.get_buckets()
    
    for bucket_id in buckets.keys():
        try:
            daystart = datetime.combine(datetime.now().date(), time())
            dayend = daystart + timedelta(days=1)

            if bucket_id.startswith("aw-watcher-afk"):
                events = aw.get_events(bucket_id, start=daystart, end=dayend)
                events = [e for e in events if e.data["status"] == "not-afk"]
                total_duration = sum((e.duration for e in events), timedelta())
                if total_duration.total_seconds() >= 0:
                    trackerid = bucket_id.split('_')[-1]
                    trackdata.append(trackerid)
                    wfh = trackerid not in users
                    rec = { "email": trackerid, "spent_time": total_duration.total_seconds(), "date" : datetime.now().strftime("%m/%d/%Y"), "wfh": wfh }
                    reportdata.append(rec)

        except Exception as e:
            print(f"Error: {e}")

    for user in r.json()["result"]:        
        email = user["emailAddress"].split("@")[0]
        if email not in trackdata and f"{email}.ncc" not in trackdata:
            reportdata.append({ "email": email, "spent_time": 0, "date" : datetime.now().strftime("%m/%d/%Y"), "wfh": True })

    #mycol.insert_many(reportdata)
    print(reportdata)

if __name__ == "__main__":
    main()
