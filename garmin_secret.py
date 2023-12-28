import argparse

import garth
import sys


class GarminLogin:
    username = ""
    password = ""
    domain = ""

    def __init__(self, user, pwd, is_cn):
        self.username = user
        self.password = pwd
        if is_cn:
            self.domain = 'garmin.cn'

    def gen_secret(self) -> str:
        if self.domain:
            garth.configure(domain=self.domain)
        try:
            garth.login(self.username, self.password)
            return garth.client.dumps()
        except Exception as e:
            print(e)
            return ""


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("-u", "--user", action="store", required=True, help="email")
    parser.add_argument("-p", "--pwd", action="store", required=True, help="pwd")
    parser.add_argument("--cn", action="store_true", help="if garmin accout is cn",
                        )
    options = parser.parse_args()
    print(options)
    login = GarminLogin(options.user, options.pwd, options.cn)
    r = login.gen_secret()
    if r != "":
        print('success')
