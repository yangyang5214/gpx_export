import argparse
import base64
import json
import os
import time
import zlib
from datetime import datetime

import eviltransform
import gpxpy
import requests
from Crypto.Cipher import AES
import xml.etree.ElementTree as ET

# need to test
LOGIN_API = "https://api.gotokeep.com/v1.1/users/login"
RUN_DATA_API = "https://api.gotokeep.com/pd/v3/stats/detail?dateUnit=all&type={activity_type}&lastDate={last_date}"
RUN_LOG_API = "https://api.gotokeep.com/pd/v3/{log_type}/{run_id}"

HR_FRAME_THRESHOLD_IN_DECISECOND = 100  # Maximum time difference to consider a data point as the nearest, the unit is decisecond(分秒)

TIMESTAMP_THRESHOLD_IN_DECISECOND = 3_600_000  # Threshold for target timestamp adjustment, the unit of timestamp is decisecond(分秒), so the 3_600_000 stands for 100 hours sports time. 100h = 100 * 60 * 60 * 10

# If your points need trans from gcj02 to wgs84 coordinate which use by Mapbox
TRANS_GCJ02_TO_WGS84 = True

user_agent = "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1"


def login(session, mobile, password):
    headers = {
        "User-Agent": user_agent,
        "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
    }
    data = {"mobile": mobile, "password": password}
    r = session.post(LOGIN_API, headers=headers, data=data)
    if r.ok:
        token = r.json()["data"]["token"]
        headers["Authorization"] = f"Bearer {token}"
        return session, headers


def get_to_download_runs_ids(session, headers):
    last_date = 0
    result = []
    for activity_type in ['hiking', 'cycling', 'running']:
        r = session.get(RUN_DATA_API.format(activity_type=activity_type, last_date=last_date), headers=headers)
        if r.ok:
            run_logs = r.json()["data"]["records"]
            for i in run_logs:
                logs = [j["stats"] for j in i["logs"]]
                result.extend(k["id"] for k in logs if not k["isDoubtful"])
            last_date = r.json()["data"]["lastTimestamp"]
            since_time = datetime.utcfromtimestamp(last_date / 1000)
            print(f"pares keep ids data since {since_time}")
            time.sleep(1)  # spider rule
            if not last_date:
                break
    return result


def get_single_run_data(session, headers, run_id):
    log_type = 'runninglog'
    if run_id.endswith("hk"):
        log_type = 'hikinglog'
    elif run_id.endswith("cy"):
        log_type = 'cyclinglog'
    r = session.get(RUN_LOG_API.format(log_type=log_type, run_id=run_id), headers=headers)
    if r.ok:
        return r.json()


def decode_runmap_data(text, is_geo=False):
    _bytes = base64.b64decode(text)
    key = "NTZmZTU5OzgyZzpkODczYw=="
    iv = "MjM0Njg5MjQzMjkyMDMwMA=="
    if is_geo:
        cipher = AES.new(base64.b64decode(key), AES.MODE_CBC, base64.b64decode(iv))
        _bytes = cipher.decrypt(_bytes)
    run_points_data = zlib.decompress(_bytes, 16 + zlib.MAX_WBITS)
    run_points_data = json.loads(run_points_data)
    return run_points_data


def parse_raw_data_to_nametuple(run_data, out_dir):
    run_data = run_data["data"]
    keep_ids = []

    # 5898009e387e28303988f3b7_9223370441312156007_rn middle
    keep_id = run_data["id"].split("_")[1]

    start_time = run_data["startTime"]
    decoded_hr_data = []
    if run_data["heartRate"]:
        avg_heart_rate = run_data["heartRate"].get("averageHeartRate", None)
        heart_rate_data = run_data["heartRate"].get("heartRates", None)
        if heart_rate_data is not None:
            decoded_hr_data = decode_runmap_data(heart_rate_data)

    if run_data["geoPoints"]:
        run_points_data = decode_runmap_data(run_data["geoPoints"], True)
        run_points_data_gpx = run_points_data
        if TRANS_GCJ02_TO_WGS84:
            run_points_data = [
                list(eviltransform.gcj2wgs(p["latitude"], p["longitude"]))
                for p in run_points_data
            ]
            for i, p in enumerate(run_points_data_gpx):
                p["latitude"] = run_points_data[i][0]
                p["longitude"] = run_points_data[i][1]

        for p in run_points_data_gpx:
            p_hr = find_nearest_hr(decoded_hr_data, int(p["timestamp"]), start_time)
            if p_hr:
                p["hr"] = p_hr

        gpx_data = parse_points_to_gpx(run_points_data_gpx, start_time)
        download_keep_gpx(gpx_data, str(keep_id), out_dir)
        keep_ids.append(keep_id)
    else:
        print(f"ID {keep_id} no gps data")


def get_all_keep_tracks(email, password, out_dir):
    if not os.path.exists(out_dir):
        os.mkdir(out_dir)
    s = requests.Session()
    print('email:' + email)
    print('password:' + password)
    s, headers = login(s, email, password)
    runs = get_to_download_runs_ids(s, headers)

    old_tracks_ids = get_old_tracks_ids(out_dir)

    runs = [run for run in runs if run.split("_")[1] not in old_tracks_ids]

    print(f"{len(runs)} ({len(runs)} - {len(old_tracks_ids)}) new keep runs to generate")
    if len(runs) == 0:
        return

    for run in runs:
        print(f"parsing keep id {run}")
        try:
            run_data = get_single_run_data(s, headers, run)
            parse_raw_data_to_nametuple(run_data, out_dir)
        except Exception as e:
            print(f"Something wrong paring keep id {run}" + str(e))


def parse_points_to_gpx(run_points_data, start_time):
    """
    Convert run points data to GPX format.

    Args:
        run_id (str): The ID of the run.
        run_points_data (list of dict): A list of run data points.
        start_time (int): The start time for adjusting timestamps. Note that the unit of the start_time is millsecond

    Returns:
        gpx_data (str): GPX data in string format.
    """
    points_dict_list = []
    # early timestamp fields in keep's data stands for delta time, but in newly data timestamp field stands for exactly time,
    # so it does'nt need to plus extra start_time
    if run_points_data[0]["timestamp"] > TIMESTAMP_THRESHOLD_IN_DECISECOND:
        start_time = 0

    for point in run_points_data:
        points_dict = {
            "latitude": point["latitude"],
            "longitude": point["longitude"],
            "time": datetime.utcfromtimestamp(
                (point["timestamp"] * 100 + start_time)
                / 1000  # note that the timestamp of a point is decisecond(分秒)
            ),
            "elevation": point.get("verticalAccuracy"),
            "hr": point.get("hr"),
        }
        points_dict_list.append(points_dict)
    gpx = gpxpy.gpx.GPX()
    gpx.nsmap["gpxtpx"] = "http://www.garmin.com/xmlschemas/TrackPointExtension/v1"
    gpx_track = gpxpy.gpx.GPXTrack()
    gpx_track.name = "gpx from keep"
    gpx.tracks.append(gpx_track)

    # Create first segment in our GPX track:
    gpx_segment = gpxpy.gpx.GPXTrackSegment()
    gpx_track.segments.append(gpx_segment)
    for p in points_dict_list:
        point = gpxpy.gpx.GPXTrackPoint(
            latitude=p["latitude"],
            longitude=p["longitude"],
            time=p["time"],
            elevation=p.get("elevation"),
        )
        if p.get("hr") is not None:
            gpx_extension_hr = ET.fromstring(
                f"""<gpxtpx:TrackPointExtension xmlns:gpxtpx="http://www.garmin.com/xmlschemas/TrackPointExtension/v1">
                    <gpxtpx:hr>{p["hr"]}</gpxtpx:hr>
                    </gpxtpx:TrackPointExtension>
                    """
            )
            point.extensions.append(gpx_extension_hr)
        gpx_segment.points.append(point)
    return gpx.to_xml()


def find_nearest_hr(
        hr_data_list, target_time, start_time, threshold=HR_FRAME_THRESHOLD_IN_DECISECOND
):
    """
    Find the nearest heart rate data point to the target time.
    if cannot found suitable HR data within the specified time frame (within 10 seconds by default), there will be no hr data return
    Args:
        heart_rate_data (list of dict): A list of heart rate data points, where each point is a dictionary
            containing at least "timestamp" and "beatsPerMinute" keys.
        target_time (float): The target timestamp for which to find the nearest heart rate data point. Please Note that the unit of target_time is decisecond(分秒),
            means 1/10 of a second ,this is very unsual!! so when we convert a target_time to second we need to divide by 10, and when we convert a target time to millsecond
            we need to times 100.
        start_time (float): The reference start time. the unit of start_time is normal millsecond timestamp
        threshold (float, optional): The maximum allowed time difference to consider a data point as the nearest.
            Default is HR_THRESHOLD, the unit is decisecond(分秒)

    Returns:
        int or None: The heart rate value of the nearest data point, or None if no suitable data point is found.
    """
    closest_element = None
    # init difference value
    min_difference = float("inf")
    if target_time > TIMESTAMP_THRESHOLD_IN_DECISECOND:
        target_time = (
                              target_time * 100 - start_time
                      ) / 100  # note that the unit of target_time is decisecond(分秒) and the unit of start_time is normal millsecond

    for item in hr_data_list:
        timestamp = item["timestamp"]
        difference = abs(timestamp - target_time)

        if difference <= threshold and difference < min_difference:
            closest_element = item
            min_difference = difference

    if closest_element:
        hr = closest_element.get("beatsPerMinute")
        if hr and hr > 0:
            return hr

    return None


def download_keep_gpx(gpx_data, keep_id, out_dir):
    try:
        print(f"downloading keep_id {str(keep_id)}.gpx")
        file_path = os.path.join(out_dir, str(keep_id) + ".gpx")
        with open(file_path, "w") as fb:
            fb.write(gpx_data)
    except:
        print(f"wrong id {keep_id}")
        pass


def get_old_tracks_ids(folder):
    return [
        i.split(".")[0]
        for i in os.listdir(folder)
        if i.endswith(".gpx") and not i.startswith(".")
    ]


def run_keep_sync(email, password, out_dir):
    get_all_keep_tracks(email, password, out_dir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phone_number", help="keep login phone number")
    parser.add_argument("password", help="keep login password")

    parser.add_argument(
        "--out",
        dest="out_dir",
        action="store",
        default="garmin_export_out",
        help="download out file dir",
    )

    options = parser.parse_args()
    run_keep_sync(options.phone_number, options.password, options.out_dir)
