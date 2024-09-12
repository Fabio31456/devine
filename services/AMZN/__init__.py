import base64
import math
import uuid
import random
from http.cookiejar import CookieJar
from typing import Optional, Union, Generator
import click
from datetime import datetime, timedelta
from devine.core.service import Service
from devine.core.titles import Titles_T, Title_T, Series, Episode, Movies, Movie
from devine.core.constants import AnyTrack
from devine.core.credential import Credential
from devine.core.tracks import Chapters, Tracks, Subtitle, Chapter
from devine.core.search_result import SearchResult
from devine.core.manifests import DASH


class AMZN(Service):
    """
    Service code for Amazon (https://www.amazon.com)

    \b
    Author: TPD94
    Authorization: Login
    Robustness:
        Widevine:
            L3 Chrome: 1080p
            L3: 540p
    \b
    Tips:
    - Use Amazon ASIN ID
    - Plugin can be found at https://greasyfork.org/en/scripts/496577-amazon-video-asin-display
    """

    @staticmethod
    @click.command(name="AMZN", short_help="https://amazon.com", help=__doc__)
    @click.argument("title", type=str)
    @click.pass_context
    def cli(ctx, **kwargs):
        return AMZN(ctx, **kwargs)

    def __init__(self, ctx, title):

        self.title = title
        self.cookies = None

        # Overriding the constructor
        super().__init__(ctx)

    def authenticate(self, cookies: Optional[CookieJar] = None, credential: Optional[Credential] = None) -> None:
        self.session.cookies.update(cookies)
        return

    def get_titles(self) -> Titles_T:

        response = self.session.get(
            url=self.config['endpoints']['details'],
            params={
                "titleID": self.title,
                "isElcano": "1",
                "sections": ["Atf", "Btf"]
            },
            headers={
                "Accept": "application/json"
            }
        )

        data = response.json()["widgets"]

        product_details = data.get("productDetails", {}).get("detail")

        if data["pageContext"]["subPageType"] == "Movie":
            card = data["productDetails"]["detail"]
            return Movies([
                Movie(
                    id_=card["catalogId"],
                    service=self.__class__,
                    name=product_details["title"],
                    year=card.get("releaseYear", ""),
                    language="en"
                )
            ])
        else:
            episodes = []
            cards = [
                x['detail']
                for x in data["titleContent"][0]["cards"]
            ]
            for card in cards:
                episode_number = card.get("episodeNumber", 0)
                if episode_number != 0:
                    episodes.append(Episode(
                        id_=card["catalogId"],
                        service=self.__class__,
                        title=product_details["parentTitle"],
                        season=product_details["seasonNumber"],
                        number=episode_number,
                        name=card["title"],
                        year=card.get("releaseYear", ""),
                        language="en"
                    ))
            return Series(episodes)

    def get_tracks(self, title: Title_T) -> Tracks:
        tracks = Tracks()

        response = self.session.get(
            url=self.config['endpoints']['playback'],
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0',
            },
            params={
                'deviceID': 'eff7bd3a-730d-41d2-8ad8-bf4dfa55bee3',
                'deviceTypeID': 'AOAGZA014O5RE',
                'gascEnabled': 'false',
                'marketplaceID': 'ATVPDKIKX0DER',
                'uxLocale': 'en_US',
                'firmware': '1',
                'playerType': 'xp',
                'operatingSystemName': 'Windows',
                'operatingSystemVersion': '10.0',
                'deviceApplicationName': 'Firefox64',
                'asin': title.id,
                'consumptionType': 'Streaming',
                'desiredResources': 'PlaybackUrls,SubtitleUrls',
                'resourceUsage': 'CacheResources',
                'videoMaterialType': 'Feature',
                'displayWidth': '1920',
                'displayHeight': '1080',
                'supportsVariableAspectRatio': 'true',
                'deviceStreamingTechnologyOverride': 'DASH',
                'deviceDrmOverride': 'CENC',
                'deviceBitrateAdaptationsOverride': 'CVBR,CBR',
                'supportsEmbeddedTrickplayForVod': 'false',
                'audioTrackId': 'all',
                'languageFeature': 'MLFv2',
                'liveManifestType': 'patternTemplate,accumulating,live',
                'supportedDRMKeyScheme': 'DUAL_KEY',
                'supportsEmbeddedTrickplay': 'true',
                'daiSupportsEmbeddedTrickplay': 'true',
                'daiLiveManifestType': 'patternTemplate,accumulating,live',
                'ssaiSegmentInfoSupport': 'Base',
                'ssaiStitchType': 'MultiPeriod',
                'gdprEnabled': 'false',
                'subtitleFormat': 'TTMLv2',
                'playbackSettingsFormatVersion': '1.0.0',
                'titleDecorationScheme': 'primary-content',
                'xrayToken': 'XRAY_WEB_2023_V2',
                'xrayPlaybackMode': 'playback',
                'xrayDeviceClass': 'normal',
                'playerAttributes': '{"middlewareName":"Firefox64","middlewareVersion":"130.0","nativeApplicationName":"Firefox64","nativeApplicationVersion":"130.0","supportedAudioCodecs":"AAC","frameRate":"HFR","H264.codecLevel":"4.2","H265.codecLevel":"0.0","AV1.codecLevel":"0.0"}',
            }
        ).json()
        urls = []
        for set in response['playbackUrls']['urlSets']:
            url = response['playbackUrls']['urlSets'][set]['urls']['manifest']['url']
            urls.append(url)
        tracks.add(DASH.from_url(url=urls[random.randint(0, len(urls) - 1)], session=self.session).to_tracks(language='en'))
        return tracks

    def get_chapters(self, title: Title_T) -> Chapters:
        return []


    def get_widevine_service_certificate(self, *, challenge: bytes, title: Title_T, track: AnyTrack) -> Union[bytes, str]:

        response = self.session.post(
            url=self.config['endpoints']['playback'],
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0',
            },
            params={
                'deviceID': 'eff7bd3a-730d-41d2-8ad8-bf4dfa55bee3',
                'deviceTypeID': 'AOAGZA014O5RE',
                'gascEnabled': 'false',
                'marketplaceID': 'ATVPDKIKX0DER',
                'uxLocale': 'en_US',
                'firmware': '1',
                'playerType': 'xp',
                'operatingSystemName': 'Windows',
                'operatingSystemVersion': '10.0',
                'deviceApplicationName': 'Firefox64',
                'asin': title.id,
                'consumptionType': 'Streaming',
                'desiredResources': 'Widevine2License',
                'resourceUsage': 'CacheResources',
                'videoMaterialType': 'Feature',
                'displayWidth': '1920',
                'displayHeight': '1080',
                'supportsVariableAspectRatio': 'true',
                'deviceStreamingTechnologyOverride': 'DASH',
                'deviceDrmOverride': 'CENC',
                'deviceBitrateAdaptationsOverride': 'CVBR,CBR',
                'supportsEmbeddedTrickplayForVod': 'false',
                'audioTrackId': 'all',
                'languageFeature': 'MLFv2',
                'liveManifestType': 'patternTemplate,accumulating,live',
                'supportedDRMKeyScheme': 'DUAL_KEY',
                'supportsEmbeddedTrickplay': 'true',
                'daiSupportsEmbeddedTrickplay': 'true',
                'daiLiveManifestType': 'patternTemplate,accumulating,live',
                'ssaiSegmentInfoSupport': 'Base',
                'ssaiStitchType': 'MultiPeriod',
                'gdprEnabled': 'false',
                'subtitleFormat': 'TTMLv2',
                'playbackSettingsFormatVersion': '1.0.0',
                'titleDecorationScheme': 'primary-content',
                'xrayToken': 'XRAY_WEB_2023_V2',
                'xrayPlaybackMode': 'playback',
                'xrayDeviceClass': 'normal',
                'playerAttributes': '{"middlewareName":"Firefox64","middlewareVersion":"130.0","nativeApplicationName":"Firefox64","nativeApplicationVersion":"130.0","supportedAudioCodecs":"AAC","frameRate":"HFR","H264.codecLevel":"4.2","H265.codecLevel":"0.0","AV1.codecLevel":"0.0"}',
            },
            data={
                'widevine2Challenge': "CAQ=",
                'includeHdcpTestKeyInLicense': 'true',
            }
        ).json()['widevine2License']['license']

        return base64.b64decode(response)


    def get_widevine_license(self, *, challenge: bytes, title: Title_T, track: AnyTrack) -> Optional[Union[bytes, str]]:

        response = self.session.post(
            url=self.config['endpoints']['playback'],
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0',
            },
            params={
                'deviceID': 'eff7bd3a-730d-41d2-8ad8-bf4dfa55bee3',
                'deviceTypeID': 'AOAGZA014O5RE',
                'gascEnabled': 'false',
                'marketplaceID': 'ATVPDKIKX0DER',
                'uxLocale': 'en_US',
                'firmware': '1',
                'playerType': 'xp',
                'operatingSystemName': 'Windows',
                'operatingSystemVersion': '10.0',
                'deviceApplicationName': 'Firefox64',
                'asin': title.id,
                'consumptionType': 'Streaming',
                'desiredResources': 'Widevine2License',
                'resourceUsage': 'CacheResources',
                'videoMaterialType': 'Feature',
                'displayWidth': '1920',
                'displayHeight': '1080',
                'supportsVariableAspectRatio': 'true',
                'deviceStreamingTechnologyOverride': 'DASH',
                'deviceDrmOverride': 'CENC',
                'deviceBitrateAdaptationsOverride': 'CVBR,CBR',
                'supportsEmbeddedTrickplayForVod': 'false',
                'audioTrackId': 'all',
                'languageFeature': 'MLFv2',
                'liveManifestType': 'patternTemplate,accumulating,live',
                'supportedDRMKeyScheme': 'DUAL_KEY',
                'supportsEmbeddedTrickplay': 'true',
                'daiSupportsEmbeddedTrickplay': 'true',
                'daiLiveManifestType': 'patternTemplate,accumulating,live',
                'ssaiSegmentInfoSupport': 'Base',
                'ssaiStitchType': 'MultiPeriod',
                'gdprEnabled': 'false',
                'subtitleFormat': 'TTMLv2',
                'playbackSettingsFormatVersion': '1.0.0',
                'titleDecorationScheme': 'primary-content',
                'xrayToken': 'XRAY_WEB_2023_V2',
                'xrayPlaybackMode': 'playback',
                'xrayDeviceClass': 'normal',
                'playerAttributes': '{"middlewareName":"Firefox64","middlewareVersion":"130.0","nativeApplicationName":"Firefox64","nativeApplicationVersion":"130.0","supportedAudioCodecs":"AAC","frameRate":"HFR","H264.codecLevel":"4.2","H265.codecLevel":"0.0","AV1.codecLevel":"0.0"}',
            },
            data={
                'widevine2Challenge': f"{base64.b64encode(challenge).decode()}",
                'includeHdcpTestKeyInLicense': 'true',
            }
        ).json()['widevine2License']['license']

        return response