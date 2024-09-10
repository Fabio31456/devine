import json
import logging
import re
from abc import ABCMeta, abstractmethod
from http.cookiejar import CookieJar
from typing import Optional, Union
from urllib.parse import urlparse
import click
import requests
from requests.adapters import HTTPAdapter, Retry
from rich.padding import Padding
from rich.rule import Rule
from devine.core.service import Service
from devine.core.titles import Movies, Movie, Titles_T, Title_T, Series, Episode
from devine.core.cacher import Cacher
from devine.core.config import config
from devine.core.console import console
from devine.core.constants import AnyTrack
from devine.core.credential import Credential
from devine.core.tracks import Chapters, Tracks
from devine.core.utilities import get_ip_info
from devine.core.manifests import HLS, DASH
from devine.core.utils.collections import as_list

class DSNP(Service):
    """
    Service code for Disney+

    Written by TPD94

    Authorization: Login

    Security: HD@L3
    """

    GEOFENCE = ('')

    # Static method, this method belongs to the class
    @staticmethod

    # The command name, must much the service tag (and by extension the service folder)
    @click.command(name="DSNP", short_help="https://disneyplus.com", help=__doc__)

    # Using series ID for Disney+
    @click.argument("title", type=str)

    # Option if it is a movie
    @click.option("--movie", is_flag=True, help="Specify if it's a movie")

    # Pass the context back to the CLI with arguments
    @click.pass_context
    def cli(ctx, **kwargs):
        return DSNP(ctx, **kwargs)

    # Accept the CLI arguments by overriding the constructor (The __init__() method)
    def __init__(self, ctx, title, movie):

        # Pass the series_id argument to self so it's accessable across all methods
        self.title = title

        self.movie = movie
        
        # Initialize variable for credentials
        self.credential = None

        # Overriding the constructor
        super().__init__(ctx)

    # Define authenticate function
    def authenticate(self, cookies: Optional[CookieJar] = None, credential: Optional[Credential] = None) -> None:

        # Set API url
        api_url = 'https://disney.api.edge.bamgrid.com/graph/v1/device/graphql'
        
        # Load credential for the whole session
        if self.credential is None:
            self.credential = credential

        # Set first (public) header for device registration
        headers = {
            'authorization': 'Bearer ZGlzbmV5JmJyb3dzZXImMS4wLjA.Cu56AgSfBTDag5NiRA81oLHkDZfu5L3CKadnefEAY84',
        }

        # Set first (public) json data for device registration
        json_data = {
            'operationName': 'registerDevice',
            'query': 'mutation registerDevice($input: RegisterDeviceInput!) {\n            registerDevice(registerDevice: $input) {\n                grant {\n                  grantType\n                  assertion\n                },\n                activeSession {\n                  partnerName\n                  profile {\n                    id\n                  }\n                }\n            }\n        }',
            'variables': {
                'input': {
                    'deviceFamily': 'browser',
                    'applicationRuntime': 'firefox',
                    'deviceProfile': 'windows',
                    'deviceLanguage': 'en',
                    'attributes': {
                        'brand': 'web',
                        'operatingSystem': 'n/a',
                        'operatingSystemVersion': 'n/a',
                    },
                },
            },
        }

        # Get the device registration auth token
        tmp = requests.post(url=api_url, json=json_data, headers=headers).json()
        register_auth = tmp['extensions']['sdk']['token']['accessToken']
        #register_auth = 'eyJ6aXAiOiJERUYiLCJraWQiOiJLcTYtNW1Ia3BxOXdzLUtsSUUyaGJHYkRIZFduRjU3UjZHY1h6aFlvZi04IiwiY3R5IjoiSldUIiwiZW5jIjoiQzIwUCIsImFsZyI6ImRpciJ9..UpjnEBDleSJ-jZ3i.k7F8tdoIs-jDA9qLcydlcV0UtaNX6wr6WF6selbBRc8vwPSVCLfuNtArOJhFS_HOjmT4qme-jZwoBx0S20GfQpnwP4o2N0Iv2F02-4hd34YF7Z0xvnTl7w2sfdSXdh54D17yySS1Gup5u3N2QWsMGckE7OUrKIl6NUGzM-R1UaLdnp_Ytu8uEkb43MRCo4A7eMeE7Z0aMau4tuR6LdKZkRsDm7hX-KZ0JJm7_F3LtQe5lQGvNpkRKtUpl1h_BI_BRP38AS2vOWntLXncNT3Glo-0c_w0tRvhFMP4lxfwLGreCJjI9X8hltCY7-RgFr7IkxvC6tinyda8aTSGM4PiE3uJBAEuem249U1HI1TPE1PiQGeHpzP-o33bHu1nI_NO_OCTQZ6kH9KFvIGpjT7gySVVGc-hQ9rsRxcUU2Va4EU26rqeusyhX3DifvfjiCASp78YuQBde2C0sFHRhorCsJcfPKmGRjf-5d1zLCeqQqQsa9P9daexguAT-_tn_EB9U1uPTPbO0ao01_XrmRVoi9WvAIvYa2WAthxhRYKRsmeTbx66x0CsMzqZHrUbNmCo90abIFzTAJBx-ALcbl3r7Iounwlu5Rf7i4NqVPRTxWcL4oB56MPh15Qf8Ob3t1FOdu8g090l9CAfGZ6eU4kGk5UyaBJ02acApDWdpvJWUEle2p_D4skQBUNd19tcY9UWhwqtOEJOYgNiEB--HqEwr6ke3scIbrCzC2pSaT4JHGEOPDa6as3M3PSCU0ijB8PCku6jR2WisJXdenby-WzH82BtG43AvXesIPJVC6U-BwBfOE728wrstnTj2lJtgjh5UyWSzcpnCKw1A7dzRigzV3f9aT9Xc9GASCTUti-3R0RLDRoRB3OHHXA3KwLc7bxujoHxih1k5XaVf-qEz2SVcrn9kENx7yFcSYmzgVHNeWf_mbvpiyA9UfbGlb5Tv3xGvMW1aaVj1s503wT10zJ4rP95BMPGMhhVHlLx02vUwnsY7B-jRj7JIra-9DipYrjGrv-2c5BajAGMbI3q6DuI-0ctV_Psq2kGteLqT2JK2c95on6tdFpPEETLryTN9PNaW4K1rSnT53gGLiuYsDq_oDv9Yy3yIObWV6SS4KGvqF0QK-EtIzGPBdAVAtgzPo5kOhYcMpbHIJR9w0kZoJWj2ALwi_9zLsaOtUu5cjtzaB6Wtfmb3prayiK8IdY4SmRRkh82ckNWAz9nMpp0jBYWd16UNghfrGg_vT8KCf3YGSHsXpp5wfPBtTgICIrruFdr2BOw0eS6xV7JL7FksvRtxTFQ6H96V9RT_1GYIIR2TLAMXLfFH8Z7_ybdFBj_vlPERTKuXr1CAECv1po0PpbFhBcHTJkuvk49QUCRG514adqCdD7BnJVfLA5-nUBSQ83U8_2ljfHVcBpQptWzMWFFD3Onsc7eecWLXIeJEFpGTvRo2Weih6_6DTZCoQn7qVpONqrjnEk4ZdvCfhChyxqN4oEGZGz_JFGc2v1zjwiVk_Ta1B85morAS5U1oM1ksDmAeZK-eJbcV6lIL09g-eHKgzGPgzceEnicMHovp7HeItWhdBArGoLAx_yOEbKiAOE7lY-jlR-uijaEu9dtoYytumfsU171K9iva6LJuySzR5IMEQJDHtqsquLb3_VMBhAB2BlddLcb6TmjL1ijbz3DJyJ9sc-kFYFWEOjvfs7vx5-wPwIXGPkoD5rGaDaMjeWCeOrs5zf1VauWjmTQr1rZFkyXRTzfzNrZvO7Tc3klL_n6QcwJVTT7Qbp2SIAiRMS0RdD4KGPi6vkkdh6aCd4BIgVtT7SRLSgtpTc7HwU0S-Ni1-d8Y2gYig_sE_K2OMvNdIpsKM1rW6VRR3KvBX_AHHr280qMDvGVDTQoQT-zwUST7eRC1uQdB1bh8XEZbTG1sh1bGr4Uf-xEHRNbUPTZ6NDDjV2kVXK9AacG_dpOYBZ-8FhN4th94Z63mUhYBabQk9N7UUwGCpN8_bpJd-sFPkR8HmnMRPDw4lNlwfsV5YhIWPrH8FrxKIjkzkyO1I2-g366ZECutUOWzV-nzNBU2v2m-9H7Zts9O709aZLJCjbLDASD-0DzlCk-kq2gIbxnsC8jaz4AGJccMt0KAzthJshYBM1Q7XaVvylbHi5rgyQcoO7kwS7QPXJrEyACzsKhyU1yVqeIPUO0BE5tEV7atAJgCGizCz3Sx42jqMqbccXCUjtgAdvLayA5uBrMNel0PRw0dhWShM-C5mwkDod7gdMgq3itFb4HYTNvo0EBtt_Bewav4vJnJXGOJN8XOGaVZdXSzQUvSr3Lp-4ZeEyGDwFlOOXyoJVxNxwIVPuCuB8rsRxS2rViXn9HdwgncR1kmoZz9_YIhd7zZ33xBeqc4YRos7oaA-ifys-cVCMGoL4ovkc9I25Xya03qXr_9yzMAI9EkkOuRuI5H7eq3PjVxZKNN28FgNKBO1M3WKZiqrgD3mwdn__tzA1JUqqjwDBNZTMcXydhMw1vMtBKyaojwj0KV68S4lZxYed5sSVcHmZmbfW3rokWTGXPJ4KBSM_FHhcDcdezkfbEFE5Bdm3JwtgUZ2aWw0HHJTP79XvkbldyfOqPoSUTxSpxwvPu-wYiy6ZWwpH-RlacTlDDGhgI62NvylZm4U8TCQ1fqJnS4XFJbKm_YQ05xvLRGlZBhrayIKE2gu8pBNslvPyDnDSvvQhNjJjI-y5gk_8ynzk5HJblKOuppgrYoFNGHgoDC2fVQ0N3dfRZWMGn5MDx-xS391INxFUEmjbSDXYndS_ezhb-Q3_7i6AZvAd-7jEN8xj5oAVQCZLN_GqDJKA4K63gGTTdpydgN9UBn9IVsJ7F4ACSnoDq060h3X9GT1X8dMgKB1A2ohQMGoweeddcpegYvQqz2Ta4bolCVASLa9jmtBAWS-iNfqCkZrsKm2eYls8HqZFYvLZarP7YZOChFREK9eYREBpnDSB8eOCJp6zJGyEckzClluPBWc8GWgdvXWM83cJ6LrHwEmuNfqnkne40MLF5wZee4t1l5_UaIr7qNuaU-7jJiZhBERX8THwbtP-bGp8gxGAyW3NH1fzlEPm9P0Q6dUWI5cU7hJm8NDZmfe4mtagVvvzWw5_7TAangV7WpQLcNQ1UC3bnTbb1mjsjIwGGba8XMimGEI3CdeSk81arb1OTOUlQGcxIxYEQhQ5EtRM_cmPL4va0R9ZxagHaZpLzRU6T1bAuuaHQ94aET9j6_0uSKoGEg_Casqu10Im5IX5iuGeNqywb3n9_ZBWkXtCVHprp8oNlRk7EhePfTB8UrNH0V-9f64OTH2ykAyz1JXWmPF4MsU_wSRVc0Q.lcufqaQwY2tqNk83Z63qPQ'

        # Set headers for login
        headers = {
            'authorization': f'{register_auth}',
        }

        # Set json for login
        json_data = {
            'query': '\n    mutation login($input: LoginInput!) {\n        login(login: $input) {\n            actionGrant\n            account {\n              activeProfile {\n                id\n              }\n              profiles {\n                id\n                attributes {\n                  isDefault\n                  parentalControls {\n                    isPinProtected\n                  }\n                }\n              }\n            }\n            activeSession {\n              isSubscriber\n            }\n            identity {\n              personalInfo {\n                dateOfBirth\n                gender\n              }\n              flows {\n                personalInfo {\n                  requiresCollection\n                  eligibleForCollection\n                }\n              }\n            }\n        }\n    }\n',
            'variables': {
                'input': {
                    'email': f'{credential.username}',
                    'password': f'{credential.password}',
                },
            },
            'operationName': 'login',
        }

        # Get the login auth token
        tmp = requests.post(url='https://disney.api.edge.bamgrid.com/v1/public/graphql', json=json_data, headers=headers).json()
        login_auth = tmp['extensions']['sdk']['token']['accessToken']
        #login_auth = 'eyJ6aXAiOiJERUYiLCJraWQiOiJ0Vy10M2ZQUTJEN2Q0YlBWTU1rSkd4dkJlZ0ZXQkdXek5KcFFtOGRJMWYwIiwiY3R5IjoiSldUIiwiZW5jIjoiQzIwUCIsImFsZyI6ImRpciJ9..mJpwBO4043hhTGSz.xcXGFtVQsB7UaK8ZkJvnnaXFdsD8VJ6gxT9MIvkIpzlPDK5KtOKivEa-XHAStKPTxFWKL3U1n5QBCqRBWqsh5_CR5b6Ilhaz-qETOhbT736_iX25qnvReDXLSuF0m28SKkP6xTpzdmqEazRDLeboPpCsU_nuqA94qJeMhnJJJ4j_BEjhU34QB_SIpv2tD4lgExpcVH-14PlPaybkx3MjprQijzGD0fcNcZJWT8Q9J1bh0CSd3s8C4mO1WYi8xtH0ZmRatkx9NBkND0r3mjWnLUs6Se0GNLbunrot6YB0vgHq2RzEe6jOXd0mxPP1IrRhiMMY6cwVrrTgo6CtusjYxtqKL7vzDag5NVM1JcI8Z8fEUqnEF8oddWrcgvZjbKBZJ53P19kRgOnxCpusvx0fr0Rgraf8QZE9SYE-T9yAgmPEQLQ4NrVwLelyGksiNaI-8tNEMjtsss89McBzInq9fPLRsIaCn1C5Utwd6CGxBBVUSPsI4Hib9BE59mRCVu5XNkO0UX84yMz5HvIUj-1Op4AMU8QZrk95Pz51QP0Q4h5zJ3JlW0qkZSZwAm2E-LF2vygfowd5ZLiI2oUf5j-cL6WJlZ2wAR11SzXtTvfIem4wMDkmK7omn1n_JLz6Wi21s3w8ijSjcRQ9UyI_zHTSRDQ88rZ0LWI9wqdkVtDXr8PhHM_8ZZ_YZqc2M6AG1KwIrhab6hN0pTaSRF_3gxv4mrS4kBV32kfabS2vEJJErcQPxOkCxpTRke3BXm_fN5EldgN2twJwUkzaVWnQPftongE-1E9vMAArFOYviLWUDxMDGOGH-DDBhut1pCdIUlU0iNzNNXE90cQEyffdDG2USvtAIPitzUMoa5MSMwbHzqNowOijK3bMo2-hVkDjU5JfRh4MN7Ff0iLqisRjBUcG-T2wNuBw0fHyLXmXnOtBXtmCTshdH30CgVUFYzZdkkqw-koWu_P4yQbRCnsxmMetYgKSAk3BgOm5BtinJ3shbJDKBkmbgHQ6G_91E2Vf_DnLxVQAdgEKB5dsNOMIP-gxl_E6K7Mg-hlKBpzUXZGjibKBvV5GMLRtwqB5DwO8bROQ0OdLq9yytBmaRDxhOXVNFjf7qjKFIesXU0Qfyv0vVFaOh6OHPckyAOxFrW_NtVLobMb__hzQJNL3wUE-ZILjRjn7g7572I8PpJxivYBFWeTZugKbU4O8y0E1c7YHmWBGjSpX_t53YjMIwceWmpE19l0NtejaFJVpqOu_-7CfsC_XmE92ArBo37aIkUbaD4s97GsfilFAYAIj0sulI-O9W2ODae6Q2sbaRRRhAh1HVSvYyPNvEDxtNnKzg1eIwDSkCtnvFa9LibX260UDg9DBT5DHAS8n-0dMiHe6X3CLQOrePlJ4vxMjGPNR_1_1V_DByQs9CmRvLkJPWSqwtIrNCkAu6UBZHNR3rVVr1Kvqg2gAhKk73k-NSXcHZ0RE6W41T8m35f36Yk8ZPkt4O7I41417__Zh9Z1FOep1uuLqNRdR_UrBG-TGC8D4awhUQzEykoiQvcNDIdmnh78CMx864q2a-2LY8YXCWEyyE1tEcZAlZV66--DY4URaYeiXh3v2Y9rm1ku9883w3iyCxra4LlD1vm38iwoMNUhjRUx1nr4t5yxMjpzis4JXTjiBtF10QPCS6tuVjIsKwwQr8Vh2RWoo5BftcJN0vKHZfaOwbAinH0n8HkDsPqQFSF4IQ6HsUhuvmgAFYPjiwCZt3mjdzrRsy5EX593EVUW3bOG16LL5o3iVZ9U3eHUsU_TNZGgO7GC0cNjXy8A44BArmpyaQJKyJCO0uNhp0wfC2PFhSzEQjPxEKiaOXTwnWMPYMX0rOH4hzMMA1NUfLdXLVfkR6a5TqLAu6xC6UvHKGnu7YJYxCcA6NBBj7OMGCncVBD7Vf7jdvPeuv3V5AmG8Sxw7YuQCUN1aJFULGwCa6r4ClWFFnWggy4w2xRJMWvGbQeCpbi27vch73WeoBTPe3WSbqx1Oe6gnhhsgx2kj2nJpkP0oMVWzl-rUF8qRZVB1ftuXg6ZxejMqlxPDw2oio_Uc1ge2CCnyGS1laAq1zDb7sxzA1u5A5gplK41pT7mnJ4c6GWrqGx9tQ1hihfUvDhqWSLp3-3AahgKQM524iyeLTT3I04H52-Ur_7OY1gk85PpQfw6kqewQwd-Qgs-2dI9aJp56N2Jt4R5oLE49qPBbX-FXbab6ccMBNAYYYBWHZFjUYWsnY8gmJIe4k01u44u7wUpP0XYjI0F1taCTHRNN7GF31YyutWB6qi51JzIQddY_-sczgiXVGOS4SyCee7Hz657d65_vX25H79bSYyYs00ZWLqwmM1IFbu0AHTGSlvaSr8SP25UH6GIRP6ULjK3vroAv3QtLmZq47Uwv6o7FvJcJjz4cqaJ22aSAXPtXgD_78G4gx_ndNMLJroXkqrzwvOb9aKxTMAtE6VLzBOsOPBOcN_3yMRvkcpuqh9uxFB-EM5ILabncYruiTHY_qnaEGh-CtnWykZP9G1m5pHQwtChSp5eCTNA6EIFOxZCRdUBC4lGMNlZ8kjWBL5VlyD_hAap2b6lrkXAAFk9MjglnZ3kbGIxqt4PMU9TnXcaqY7ozigFGMn3bPPesxX3ych1w6MnOkvp-B-MiHWqUoqXVGos6SWY6jqk8rs9FrM-8ymefof07Qi7uTOJKyijsjxXPHRlcGDx3XMJwfzzl0GeTvoFDHCGqGBTcMJuetAqBh3K9-DBAiFiBY2Qp9ZEleALd5x3kaCW2Jl_VYUyx1_YY_3xFNmmqF8gKqjSqU7s-mYf2Wf-MMSn8pxmqXmJ1dXqAIKFo_GffmFB8RWg5RA7glDwLBe1AiHhNsMIUrsaKxv0GY1KDtbzzfgxfIc5Am3gKC3aAeoSc70wafWMCtrMUGYelTnmX-zleQ4ihTB7UVt9aPaoIf2ZhGfkqBHsRu-K9ZlzH6DFToVo92siofcJl6bVLkpd6pcBTr7aOhq-82mKbS9cSPQ1qx5djWci_cg4gGNXjhFv0xx0Urjwb2CUZpJTFtHRkXenRlNtP4_ZOnuxoM-BpCbLQAaI7QzWoP-C4e0c2AxVVcwWQnOnsmu_kb6qpsNF0boRpy6EefA9A5m7o2EmYoy81mLHqh7D0UXeqV5l6k7wKTgrQJdHmQK2ipivd00Svis3lNYnbSH4LhAV-n43LGJBbk0St3YEKwW6mM94.9838aJufz7qOt5PdFLbcNQ'

        # Pick the first profile
        profile = requests.post(url='https://disney.api.edge.bamgrid.com/v1/public/graphql', json=json_data, headers=headers).json()['data']['login']['account']['profiles'][5]['id']

        # Set the headers to switch profiles
        headers = {
            'authorization': f'{login_auth}',
        }

        # Set the json data to switch profiles
        json_data = {
            'query': '\n  mutation switchProfile($input: SwitchProfileInput!) {\n    switchProfile(switchProfile: $input) {\n      account {\n        activeProfile {\n          name\n        }\n      }\n    }\n  }\n',
            'variables': {
                'input': {
                    'profileId': f'{profile}',
                },
            },
            'operationName': 'switchProfile',
        }

        # Get the profile auth refresh token
        profile_auth = requests.post(url='https://disney.api.edge.bamgrid.com/v1/public/graphql', json=json_data, headers=headers).json()['extensions']['sdk']['token']['refreshToken']

        # Set the headers to get an auth bearer token
        headers = {
            'authorization': 'ZGlzbmV5JmJyb3dzZXImMS4wLjA.Cu56AgSfBTDag5NiRA81oLHkDZfu5L3CKadnefEAY84',
        }

        # Set the json data to get an auth bearer token
        json_data = {
            'query': 'mutation refreshToken($input:RefreshTokenInput!){refreshToken(refreshToken:$input){activeSession{sessionId}}}',
            'variables': {
                'input': {
                    'refreshToken': f'{profile_auth}',
                },
            },
            'operationName': 'refreshToken',
        }

        # Get the bearer token
        bearer = requests.post(url=api_url, json=json_data, headers=headers).json()['extensions']['sdk']['token']['accessToken']

        # Set the bearer token in headers dictionary
        headers = {
            'authorization': f'Bearer {bearer}'
        }

        # Update the session with the auth bearer headers
        self.session.headers.update(headers)

    def get_titles(self) -> Titles_T:

        # Get the title metadata
        title_metadata = self.session.get(f'https://disney.api.edge.bamgrid.com/explore/v1.2/page/{self.title}').json()

        # Check if --movie was used
        if self.movie:
            movie_metadata = self.session.get(url=f'https://disney.api.edge.bamgrid.com/explore/v1.2/page/{self.title}').json()
            movie = Movie(
                id_=movie_metadata['data']['page']['id'],
                service=self.__class__,
                name=movie_metadata['data']['page']['visuals']['title'],
                year=movie_metadata['data']['page']['visuals']['metastringParts']['releaseYearRange']['startYear'],
                data={'resourceId': movie_metadata['data']['page']['actions'][0]['resourceId']}
            )
            return Movies([movie])

        else:
            # Set empty list for episodes
            all_episodes = []

            # Iterate through the seasons
            for season_num in title_metadata['data']['page']['containers'][0]['seasons']:

                # Grab the season metadata
                season_metadata = self.session.get(url=f'https://disney.api.edge.bamgrid.com/explore/v1.2/season/{season_num["id"]}?limit=150').json()

                # Iterate through each episode
                i = 0
                for episode_num in season_metadata['data']['season']['items']:
                    all_episodes.append(Episode(id_=episode_num['id'],
                                                service=self.__class__,
                                                title=episode_num['visuals']['title'],
                                                season=episode_num['visuals']['seasonNumber'],
                                                number=episode_num['visuals']['episodeNumber'],
                                                name=episode_num['visuals']['episodeTitle'],
                                                year=episode_num['visuals']['metastringParts']['releaseYearRange']['startYear'],
                                                data={'resourceId': self.session.get(f'https://disney.api.edge.bamgrid.com/explore/v1.2/deeplink?action=playback&refId={episode_num["id"]}&refIdType=deeplinkId').json()['data']['deeplink']['actions'][0]['resourceId']}
                                                ))
                    i += 1

            # Return the episodes
            return Series(all_episodes)

    def get_tracks(self, title: Title_T) -> Tracks:

        # Set the headers to grab the m3u
        self.session.headers['x-dss-feature-filtering'] = 'true'
        self.session.headers['x-application-version'] = '1.1.2'
        self.session.headers['x-bamsdk-client-id'] = 'disney-svod'
        self.session.headers['x-bamsdk-platform'] = 'javascript/windows/firefox'
        self.session.headers['x-bamsdk-version'] = '28.0'

        # Set the JSON to grab the m3u
        json_data = {
            'playback': {
                'attributes': {
                    'resolution': {
                        'max': [
                            '1280x720',
                        ],
                    },
                    'protocol': 'HTTPS',
                    'assetInsertionStrategy': 'SGAI',
                    'playbackInitiationContext': 'ONLINE',
                    'frameRates': [
                        60,
                    ],
                },
            },
            'playbackId': f'{title.data["resourceId"]}',
        }

        # Grab the metadata
        title_metadata = self.session.post(url='https://disney.playback.edge.bamgrid.com/v7/playback/ctr-limited', json=json_data).json()

        # Grab the m3u
        title_m3u = title_metadata['stream']['sources'][0]['complete']['url']

        # Convert the m3u to tracks
        tracks = HLS.from_url(url=title_m3u).to_tracks(language="en")

        # Format the bitrate
        for audio in tracks.audio:
            bitrate = re.search(r"(?<=r/composite_)\d+|\d+(?=_complete.m3u8)", as_list(audio.url)[0])
            audio.bitrate = int(bitrate.group()) * 10000

        # Return the tracks
        return tracks

    def get_chapters(self, title: Title_T) -> Chapters:
        return []

    def get_widevine_license(self, *, challenge: bytes, title: Title_T, track: AnyTrack) -> Optional[Union[bytes, str]]:
        return self.session.post(url='https://disney.playback.edge.bamgrid.com/widevine/v1/obtain-license', data=challenge).content