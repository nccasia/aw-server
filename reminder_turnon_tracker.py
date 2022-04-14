from datetime import datetime, time, timedelta
import aw_client
import requests

def sendWarnToMachleo(email):
    obj = {
        "message": f"{email} please turn on komutracker",
        "channelid": "921339190090797106"
    }
    requests.post("http://172.16.100.114:3000/sendMessageToChannel", 
                    data = obj, 
                    headers = { "X-Secret-Key" : "6kkCZQja9Gn27kTiv" })

# You need to set testing=False if you're going to run this on your normal instance
aw = aw_client.ActivityWatchClient("report-spent-time", testing=False)

buckets = aw.get_buckets()
#print(f"Buckets: {buckets.keys()}")
report_data = []
for bucket_id in buckets.keys():
    try:
        daystart = datetime.combine(datetime.now().date(), time())
        dayend = daystart + timedelta(days=1)

        if bucket_id.startswith("aw-watcher-afk"):
            events = aw.get_events(bucket_id, start=daystart, end=dayend)
            events = [e for e in events if e.data["status"] == "not-afk"]
            total_duration = sum((e.duration for e in events), timedelta())
            if total_duration.total_seconds() > 0:
                report_data.append(bucket_id.split('_')[-1])
    except Exception as e:
        print(f"Error: {e}")

api_url = "http://timesheetapi.nccsoft.vn/api/services/app/Public/GetUserWorkFromHome"
api_key_secret = "sksCCsksCC"
r = requests.get(api_url, headers={"securitycode": api_key_secret})


for user in r.json()["result"]:
    email = user["emailAddress"].split("@")[0]
    if email not in report_data:
        sendWarnToMachleo(email)