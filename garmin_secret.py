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

    def gen_secret(self) -> str:
        if self.domain:
            garth.configure(domain=self.domain)
        try:
            garth.login(self.username, self.password)
            return garth.client.dumps()
        except Exception as e:
            print(e)
            return ""
