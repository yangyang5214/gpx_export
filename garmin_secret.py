import argparse
import os.path

import garth


class GarminLogin:
    username = ""
    password = ""
    domain = ""

    def __init__(self, user, pwd, is_cn):
        self.username = user
        self.password = pwd
        if is_cn:
            self.domain = 'garmin.cn'

    def gen_secret(self):
        if self.domain:
            garth.configure(domain=self.domain)
        try:
            p = '.garth_' + self.username
            if os.path.exists(p):
                return garth.client.load(p)
            garth.login(self.username, self.password)
            garth.client.dump(p)
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
