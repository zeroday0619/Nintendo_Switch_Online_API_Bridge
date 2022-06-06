import base64
import time
import uuid
import requests
import keyring
import pickle

from app.flapg import FlapgAPI


class NintendoSwitchOnlineLogin:
    def __init__(self, nso_app_version: str, user_info: dict, user_lang: str, access_token, guid):
        self.headers = {
            'Host': 'api-lp1.znc.srv.nintendo.net',
            'Accept-Language': user_lang,
            'User-Agent': 'com.nintendo.znca/' + nso_app_version + ' (Android/12.1.2)',
            'Accept': 'application/json',
            'X-ProductVersion': nso_app_version,
            'Content-Type': 'application/json; charset=utf-8',
            'Connection': 'Keep-Alive',
            'Authorization': 'Bearer',
            'X-Platform': 'Android',
            'Accept-Encoding': 'gzip'
        }
        self.url = 'https://api-lp1.znc.srv.nintendo.net/v3/Account/Login'
        self.timestamp = int(time.time())
        self.guid = guid
        self.user_info = user_info
        self.access_token = access_token
        self.flapg = FlapgAPI(self.access_token, self.timestamp, self.guid).get()
        self.account = None

        self.body = {
            'parameter': {
                'f': self.flapg['f'],
                'naIdToken': self.flapg['p1'],
                'timestamp': self.flapg['p2'],
                'requestId': self.flapg['p3'],
                'naCountry': self.user_info['country'],
                'naBirthday': self.user_info['birthday'],
                'language': self.user_info['language'],
            },
        }

    def to_account(self):
        response = requests.post(
            url=self.url, headers=self.headers, json=self.body
        )
        if response.status_code != 200:
            raise Exception(
                f"Error: {response.status_code}"
            )
        self.account = response.json()
        return self.account


class NintendoSwitchOnlineAPI:
    def __init__(self, nso_app_version: str, user_info: dict, service_token: dict, user_lang: str = "en-US"):
        self.nso_app_version = nso_app_version or "2.1.1"
        self.url = 'https://api-lp1.znc.srv.nintendo.net'
        self.headers = {
            'X-ProductVersion': nso_app_version,
            'X-Platform': 'iOS',
            'User-Agent': 'Coral/2.0.0 (com.nintendo.znca; build:1489; iOS 15.3.1) Alamofire/5.4.4',
            'Accept': 'application/json',
            'Content-Type': 'application/json; charset=utf-8',
            'Host': 'api-lp1.znc.srv.nintendo.net',
            'Connection': 'Keep-Alive',
            'Accept-Encoding': 'gzip',
        }

        self.user_lang = user_lang
        self.user_info = user_info
        self.token = service_token
        self.id_token = self.token.get('id_token')
        self.access_token = self.token.get('access_token')
        self.guid = str(uuid.uuid4())

        self.login = {
            'login': None,
            'time': 0
        }
    
    def getSelf(self):
        resp = requests.post(url=self.url + "/v3/User/ShowSelf", headers=self.headers)
        if resp.status_code != 200:
            raise Exception(
                f"Error: {resp.status_code}"
            )
        return resp.json()
    
    def getFriends(self):
        resp = requests.post(url=self.url + "/v3/Friend/List", headers=self.headers)
        if resp.status_code != 200:
            raise Exception(
                f"Error: {resp.status_code}"
            )
        return resp.json()        

    def sync_login(self):
        wasc_access_token = keyring.get_password("nso-bridge", "login")
        wasc_time = keyring.get_password("nso-bridge", "wasc_time")
        
        if wasc_time is None:
            wasc_time = 0
        else:
            if wasc_access_token is not None:
                self.login = pickle.loads(base64.b64decode(wasc_access_token.encode('utf-8')))
                self.headers['Authorization'] = f"Bearer {self.login['login'].account['result']['webApiServerCredential']['accessToken']}"
                return
        
        if time.time() - int(wasc_time) < 7170:
            return
        
        login = NintendoSwitchOnlineLogin(
            self.nso_app_version,
            self.user_info,
            self.user_lang,
            self.access_token,
            self.guid
        )
        login.to_account()

        self.login = {
            'login': login,
            'time': time.time(),
        }
        self.headers['Authorization'] = f"Bearer {self.login['login'].account['result']['webApiServerCredential']['accessToken']}"
        keyring.set_password("nso-bridge", "login", base64.b64encode(pickle.dumps(self.login)).decode("utf-8"))
        keyring.set_password("nso-bridge", "wasc_access_token", self.login['login'].account['result']['webApiServerCredential']['accessToken'])
        keyring.set_password("nso-bridge", "wasc_time", str(self.login['time']))


