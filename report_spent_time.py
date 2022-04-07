from datetime import datetime, time, timedelta
import aw_client


def main():
    # You need to set testing=False if you're going to run this on your normal instance
    aw = aw_client.ActivityWatchClient("report-spent-time", testing=False)

    buckets = aw.get_buckets()
    #print(f"Buckets: {buckets.keys()}")

    for bucket_id in buckets.keys():
        try:
            daystart = datetime.combine(datetime.now().date(), time())
            dayend = daystart + timedelta(days=1)

            if bucket_id.startswith("aw-watcher-afk"):
                events = aw.get_events(bucket_id, start=daystart, end=dayend)
                events = [e for e in events if e.data["status"] == "not-afk"]
                total_duration = sum((e.duration for e in events), timedelta())
                print(f"Total time spent on {bucket_id} today: {total_duration}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    main()
