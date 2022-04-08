from datetime import datetime, time, timedelta
import aw_client
import pymongo

myclient = pymongo.MongoClient("mongodb://localhost:27017/")
mydb = myclient["komubot"]
mycol = mydb["komu_tracker_spent_time"]

def main():
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
                    report_data.append({ "email": bucket_id.split('_')[-1], "spent_time": total_duration.total_seconds(), "date" : datetime.now().strftime("%m/%d/%Y") })
        except Exception as e:
            print(f"Error: {e}")

    mycol.insert_many(report_data)

if __name__ == "__main__":
    main()
