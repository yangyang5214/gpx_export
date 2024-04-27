import argparse
import sys
import garth


def main(user: str, pwd: str, is_cn: bool, gpx_file: str):
    if not user:
        exit(1)

    if is_cn:
        garth.configure(
            domain="garmin.cn",
            timeout=180
        )

    try:
        garth.login(user, pwd)
    except:
        print('login failed')
        exit(1)

    with open(gpx_file, "rb") as f:
        uploaded = garth.client.upload(f)
        print(uploaded)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-u", "--user", action="store", required=True, help="email")
    parser.add_argument("-p", "--pwd", action="store", required=True, help="pwd")
    parser.add_argument("-f", "--file", action="store", required=True, help="file")
    parser.add_argument(
        "--is-cn",
        dest="is_cn",
        action="store_true",
        help="if garmin accout is cn",
    )

    options = parser.parse_args()
    main(options.user, options.pwd, options.is_cn, options.file)
