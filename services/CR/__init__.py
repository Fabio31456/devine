import math
import uuid
from http.cookiejar import CookieJar
from typing import Optional, Union, Generator
import click
from datetime import datetime, timedelta
from devine.core.service import Service
from devine.core.titles import Titles_T, Title_T, Series, Episode
from devine.core.constants import AnyTrack
from devine.core.credential import Credential
from devine.core.tracks import Chapters, Tracks, Subtitle, Chapter
from devine.core.search_result import SearchResult
from devine.core.manifests import DASH


class CR(Service):
    """
    Service code for Crunchyroll (https://crunchyroll.com)

    \b
    Author: TPD94
    Authorization: Login
    Robustness:
        Widevine:
            L3: 1080p
    \b
    Tips:
    - Use complete title/episode URL or id as input:
        https://www.crunchyroll.com/series/GG5H5XQ7D/kaiju-no-8
        OR
        GG5H5XQ7D
    - Supports series
    """

    @staticmethod
    @click.command(name="CR", short_help="https://crunchyroll.com", help=__doc__)
    @click.argument("title", type=str)
    @click.pass_context
    def cli(ctx, **kwargs):
        return CR(ctx, **kwargs)

    def __init__(self, ctx, title):

        # Set the title, what the user inputs

        # Try parsing if it's a URL
        try:
            # Split the URL into parts by "/"
            parts = title.split("/")

            # Set the identifier for "series"
            identifier_index = parts.index("series") + 1

            # Extract the series ID
            self.title = parts[identifier_index]

        # If just a series ID
        except:
            self.title = title

        # Initialize variable for token
        self.token = None

        # Initialize variable for refresh token
        self.refresh_token = None

        # Initialize variable for token expiry
        self.token_expiry = None

        # Initialize variable for credentials
        self.credential = None

        # Initiliaze variable for UUID
        self.uuid = None

        # Overriding the constructor
        super().__init__(ctx)

    def authenticate(self, cookies: Optional[CookieJar] = None, credential: Optional[Credential] = None) -> None:

        # Generate a UUID for the session
        if self.uuid is None:
            self.uuid = str(uuid.uuid4())

        # Load credential for the whole session
        if self.credential is None:
            self.credential = credential

        # Check if there is no token.
        if self.token is None:

            # Assign a variable to the token and send a post request to acquire/refresh
            auth_response = self.session.post(

                # Token auth URL
                url=self.config['endpoints']['auth_url'],

                # Headers
                headers={
                    'Authorization': 'Basic d2piMV90YThta3Y3X2t4aHF6djc6MnlSWlg0Y0psX28yMzRqa2FNaXRTbXNLUVlGaUpQXzU=',
                    'ETP-Anonymous-ID': f'{uuid.uuid4()}'
                },

                # Body
                data={
                    'username': f'{credential.username}',
                    'password': f'{credential.password}',
                    'grant_type': 'password',
                    'scope': 'offline_access',
                    'device_id': self.uuid,
                    'device_name': 'AOSP on IA Emulator',
                    'device_type': 'Google AOSP on IA Emulator'
                }

            ).json()

            # Set the token
            self.token = auth_response['access_token']

            # Set the refresh token
            self.refresh_token = auth_response['refresh_token']

            # Set the token expiry time
            self.token_expiry = (datetime.now() + timedelta(minutes=4)).timestamp()

            # Update session headers to have Authorization Bearer token
            self.session.headers.update({'Authorization': f'Bearer {self.token}'})

            # Return the token if called
            return self.token

        # Check for token expiry
        if self.token_expiry:
            if self.token_expiry < datetime.now().timestamp():

                # Assign a variable to the token and send a post request to acquire/refresh
                auth_response = self.session.post(

                    # Token auth URL
                    url=self.config['endpoints']['auth_url'],

                    # Headers
                    headers={
                        'Authorization': 'Basic d2piMV90YThta3Y3X2t4aHF6djc6MnlSWlg0Y0psX28yMzRqa2FNaXRTbXNLUVlGaUpQXzU=',
                        'ETP-Anonymous-ID': self.uuid
                    },

                    # Body
                    data={
                        'refresh_token': self.refresh_token,
                        'grant_type': 'refresh_token',
                        'scope': 'offline_access',
                        'device_id': self.uuid,
                        'device_name': 'AOSP on IA Emulator',
                        'device_type': 'Google AOSP on IA Emulator'
                    }

                ).json()

                # Set the token
                self.token = auth_response['access_token']

                # Set the refresh token
                self.refresh_token = auth_response['refresh_token']

                # Set the token expiry time
                self.token_expiry = (datetime.now() + timedelta(minutes=4)).timestamp()

                # Update session headers to have Authorization Bearer token
                self.session.headers.update({'Authorization': f'Bearer {self.token}'})

                # Return the token if called
                return self.token

        # If neither, return token if called from function
        return self.token


    def get_titles(self) -> Titles_T:

        # Create a list for episodes
        episodes = []

        # Check/Call for authorization bearer token
        self.authenticate(credential=self.credential)

        # Get each season from series metadata
        for season in self.session.get(url=self.config['endpoints']['series_metadata'].format(title=self.title)).json()['data']:

            # Get each episode from season metadata
            for episode in self.session.get(url=self.config['endpoints']['episode_metadata'].format(season=season['id'])).json()['data']:

                # Append the available episodes
                episodes.append(Episode(
                    id_=episode['id'],
                    title=episode['season_title'],
                    season=episode['season_number'],
                    number=math.ceil(episode['sequence_number']),
                    name=episode['title'],
                    year=episode['episode_air_date'][:4],
                    language=episode['audio_locale'],
                    service=self.__class__
                ))

        # Return the series
        return Series(episodes)

    def get_tracks(self, title: Title_T) -> Tracks:

        # Initialize a tracks class object
        tracks = Tracks()

        # Check/Call for authorization bearer token
        self.authenticate(credential=self.credential)

        # Get the originally called title
        title_metadata = self.session.get(url=self.config['endpoints']['video_token'].format(id=title.id)).json()

        # Add original MPD
        original_mpd_tracks = DASH.from_url(url=title_metadata['url'], session=self.session).to_tracks(language=title_metadata['audioLocale'])

        # Add the GUID
        for track in original_mpd_tracks:
            track.data['guid'] = title.id

        # Add the tracks
        tracks.add(original_mpd_tracks)

        # Get all the subtitles
        for subtitle_lang in title_metadata['subtitles']:
            tracks.add(Subtitle(
                language=title_metadata['subtitles'][subtitle_lang]['language'],
                codec=Subtitle.Codec.from_mime(title_metadata['subtitles'][subtitle_lang]['format']),
                url=title_metadata['subtitles'][subtitle_lang]['url']
            ))

        # Delete the video token
        self.delete_video_token(title=title.id, token=title_metadata['token'])

        # Get other language MPDs
        for version in title_metadata['versions']:
            if version['guid'] != title.id:
                other_title_metadata = self.session.get(url=self.config['endpoints']['video_token'].format(id=version['guid'])).json()

                # Add other language MPD
                other_mpd_tracks = DASH.from_url(url=other_title_metadata['url'], session=self.session).to_tracks(language=other_title_metadata['audioLocale'])

                # Add the GUID
                for track in other_mpd_tracks:
                    track.data['guid'] = version['guid']

                # Add the tracks
                tracks.add(other_mpd_tracks)

                # Delete the video token
                self.delete_video_token(title=version['guid'], token=other_title_metadata['token'])

        # return the tracks
        return tracks

    def get_chapters(self, title: Title_T) -> Chapters:

        # Initalize a Chapters class object
        chapters = Chapters()

        # Check/Call for authorization bearer token
        self.authenticate(credential=self.credential)

        # Get the chapters metadata
        try:
            chapters_metadata = self.session.get(url=self.config['endpoints']['chapters_url'].format(id=title.id)).json()

            try:
                if chapters_metadata['intro']:
                    chapters.add(Chapter(timestamp=(chapters_metadata['intro']['start']) * 1000, name=chapters_metadata['intro']['type'].capitalize()))
            except:
                pass

            try:
                if chapters_metadata['credits']:
                    chapters.add(Chapter(timestamp=(chapters_metadata['credits']['start']) * 1000, name=chapters_metadata['credits']['type'].capitalize()))
            except:
                pass

            try:
                if chapters_metadata['preview']:
                    chapters.add(Chapter(timestamp=(chapters_metadata['preview']['start']) * 1000, name=chapters_metadata['preview']['type'].capitalize()))
            except:
                pass
        except:
            pass

        return chapters

    def get_widevine_license(self, *, challenge: bytes, title: Title_T, track: AnyTrack) -> Optional[Union[bytes, str]]:

        # Check/Call for authorization bearer token
        self.authenticate(credential=self.credential)

        # Get a video token
        video_token = self.get_video_token(title=track.data['guid'])

        # Update the headers
        self.session.headers.update({
            'content-type': 'application/octet-stream',
            'x-cr-content-id': f'{track.data["guid"]}',
            'x-cr-video-token': f'{video_token}',
        })

        # Get the license
        license_response = self.session.post(url=self.config['endpoints']['license_url'],
                                             data=challenge).content.decode()

        # Delete the video token
        self.delete_video_token(title=track.data['guid'], token=video_token)

        # Get the license
        return license_response

    def search(self) -> Generator[SearchResult, None, None]:

        # Check/Call for authorization bearer token
        self.authenticate(credential=self.credential)

        # Get the search results
        search_results = self.session.get(url=self.config['endpoints']['search_url'].format(search_keyword=self.title)).json()

        # Iterate through series responses, create generator for results.
        for result_type in search_results['data']:
            if result_type['type'] == 'series':
                for series_results in result_type['items']:
                    yield SearchResult(
                        id_=series_results['id'],
                        title=series_results['title'],
                        description=series_results['description']
                    )

    # Define function to retrieve video token for crunchyroll.
    def get_video_token(self, title: str) -> str:

        # Check/Call for authorization bearer token
        self.authenticate(credential=self.credential)

        # Get the token
        video_token = self.session.get(url=self.config['endpoints']['video_token'].format(id=title)).json()['token']

        # Return None.
        return video_token

    # Define function to delete video token for crunchyroll.
    def delete_video_token(self, title: str, token: str) -> None:

        # Check/Call for authorization bearer token
        self.authenticate(credential=self.credential)

        # Delete the token
        self.session.delete(
            url=self.config['endpoints']['video_token_delete'].format(title_id=title, video_token=token),
        )

        # Return None.
        return
