import base64
import datetime
import json
import re
import click
from langcodes import Language

from typing import Optional, Union, Generator
from devine.core.constants import AnyTrack
from devine.core.manifests import DASH
from devine.core.service import Service
from devine.core.titles import Episode, Movie, Movies, Series
from devine.core.tracks import Chapters, Tracks, Subtitle
from devine.core.search_result import SearchResult


class VIKI(Service):
    """
    Service code for Viki
    Written by ToonsHub, improved by @sp4rk.y

    Authorization: None (Free SD) | Cookies (Free and Paid Titles)
    Security: FHD@L3
    """

    TITLE_RE = r"^(?:https?://(?:www\.)?viki\.com/(?:tv|movies)/)(?P<id>[a-z0-9]+)(?:-.+)?$"
    GEOFENCE = ("ca",)

    @staticmethod
    @click.command(name="VIKI", short_help="https://www.viki.com", help=__doc__)
    @click.argument("title", type=str)
    @click.option("-m", "--movie", is_flag=True, default=False, help="Title is a Movie.")
    @click.pass_context
    def cli(ctx, **kwargs):
        return VIKI(ctx, **kwargs)

    def __init__(self, ctx, title: str, movie: bool):
        self.title = title

        if "/movies/" in self.title:
            self.is_movie = True
        else:
            self.is_movie = movie

        super().__init__(ctx)

        self.session.headers.update(
            {
                "user-agent": self.config["browser"]["user-agent"],
                "x-client-user-agent": self.config["browser"]["user-agent"],
                "x-viki-app-ver": self.config["browser"]["x-viki-app-ver"],
                "x-viki-as-id": self.config["browser"]["x-viki-as-id"],
            }
        )

    def search(self) -> Generator[SearchResult, None, None]:
        query = self.title
        response = self.session.get(
            self.config["endpoints"]["search_endpoint_url"],
            params={
                "term": query,
                "app": "100000a",
                "per_page": 10,
                "blocked": "true",
            },
        )
        response.raise_for_status()

        search_data = response.json()

        for result in search_data["response"]:
            media_type = "TV" if result["type"] == "series" else "Movie"  # Determine media type

            year = None
            distributors = result.get("distributors")
            if distributors:
                from_date = distributors[0].get("from")  # Assuming the first distributor has the year
                if from_date:
                    year_match = re.match(r"^\d{4}", from_date)  # Extract year from YYYY-MM-DD format
                    if year_match:
                        year = year_match.group()
                    label = media_type
                    if year:
                        label += f" ({year})"
                    if "viki_air_time" in result:
                        release_time = datetime.datetime.fromtimestamp(result["viki_air_time"], datetime.timezone.utc)
                        if release_time > datetime.datetime.now(
                            datetime.timezone.utc
                        ):  # Check if release time is in the future
                            time_diff = release_time - datetime.datetime.now(datetime.timezone.utc)
                            days, seconds = time_diff.days, time_diff.seconds
                            hours = days * 24 + seconds // 3600
                            minutes = (seconds % 3600) // 60
                            if hours > 0:
                                label = f"In {hours} hours"
                            elif minutes > 0:
                                label = f"In {minutes} minutes"
                            else:
                                label = "In less than a minute"
                    yield SearchResult(
                        id_=result["id"],
                        title=result["titles"]["en"],  # Using the English title
                        description=result.get("descriptions", {}).get("en", "")[:200] + "...",
                        label=label,
                        url=f"https://www.viki.com/tv/{result['id']}",
                    )

    def get_titles(self) -> Union[Movies, Series]:
        match = re.match(self.TITLE_RE, self.title)
        if match:
            title_id = match.group("id")
        else:
            title_id = self.title

        if not self.is_movie:
            self.is_movie = False
            episodes = []
            pagenumber = 1
            special_episode_number = 1
            while True:
                series_metadata = self.session.get(
                    f"https://api.viki.io/v4/containers/{title_id}/episodes.json?direction=asc&with_upcoming=false&sort=number&page={pagenumber}&per_page=10&app=100000a"
                ).json()

                self.series_metadata = series_metadata

                if not series_metadata["response"] and not series_metadata["more"]:
                    break
                show_year = self.get_show_year_from_search()

                for episode in series_metadata["response"]:
                    episode_id = episode["id"]
                    show_title = episode["container"]["titles"]["en"]
                    episode_season = 1
                    episode_number = episode["number"]

                    # Check for season number or year at the end of the show title
                    title_match = re.match(r"^(.*?)(?: (\d{4})| (\d+))?$", show_title)
                    if title_match:
                        base_title = title_match.group(1)
                        year = title_match.group(2)
                        season = title_match.group(3)

                        if season:
                            episode_season = int(season)
                        elif year:
                            base_title = show_title[:-5]  # Strip the year

                        show_title = base_title

                    episode_title_with_year = f"{show_title}.{show_year}"
                    if "Special" in episode.get("titles", {}).get("en", "") or "Extra" in episode.get("titles", {}).get(
                        "en", ""
                    ):
                        episode_season = 0
                        episode_number = special_episode_number
                        special_episode_number += 1

                    episode_name = None
                    episode_class = Episode(
                        id_=episode_id,
                        title=episode_title_with_year,
                        season=episode_season,
                        number=episode_number,
                        name=episode_name,
                        year=show_year,
                        service=self.__class__,
                    )
                    episodes.append(episode_class)
                pagenumber += 1

            return Series(episodes)

        else:
            movie_metadata = self.session.get(f"https://www.viki.com/movies/{title_id}").text
            video_id = re.search(r"https://api.viki.io/v4/videos/(.*?).json", movie_metadata).group(1)

            movie_metadata = self.session.get(self.config["endpoints"]["video_metadata"].format(id=video_id)).json()
            self.movie_metadata = movie_metadata
            movie_id = movie_metadata["id"]
            movie_name = movie_metadata["titles"]["en"]

            # Check for year at the end of the movie name and strip it
            title_match = re.match(r"^(.*?)(?: (\d{4}))?$", movie_name)
            if title_match:
                base_title = title_match.group(1)
                year = title_match.group(2)

                if year:
                    movie_name = base_title

            movie_year = self.get_show_year_from_search()
            movie_class = Movie(id_=movie_id, name=movie_name, year=movie_year, service=self.__class__)

            return Movies([movie_class])

    def get_show_year_from_search(self) -> Optional[str]:
        if hasattr(self, "movie_metadata") and self.movie_metadata:
            query = self.movie_metadata["container"]["titles"]["en"]
        else:
            query = self.series_metadata["response"][0]["container"]["titles"]["en"]

        response = self.session.get(
            self.config["endpoints"]["search_endpoint_url"],
            params={
                "term": query,
                "app": "100000a",
                "per_page": 50,
                "blocked": "true",
            },
        )
        response.raise_for_status()

        search_data = response.json()

        for result in search_data["response"]:
            if result["id"] == self.title or re.match(self.TITLE_RE, self.title).group("id") == result["id"]:
                distributors = result.get("distributors")
                if distributors:
                    from_date = distributors[0].get("from")
                    if from_date:
                        return from_date[:4]
        return None

    def get_tracks(self, title: Union[Movie, Episode]) -> Tracks:
        CHINESE_LANGUAGE_MAP = {
            "zh": "zh-Hans",  # Simplified Chinese
            "zt": "zh-Hant",  # Traditional Chinese
            "zh-TW": "zh-Hant",  # Traditional Chinese (Taiwan)
            "zh-HK": "zh-Hant",  # Traditional Chinese (Hong Kong)
        }
        mpd_info = self.session.get(self.config["endpoints"]["mpd_api"].format(id=title.id))
        mpd_data = mpd_info.json()
        mpd_url = mpd_data["queue"][1]["url"]
        mpd_lang = mpd_data["video"]["origin"]["language"]
        if mpd_lang in CHINESE_LANGUAGE_MAP:
            mpd_lang = CHINESE_LANGUAGE_MAP[mpd_lang]

        license_url = json.loads(base64.b64decode(mpd_data["drm"]).decode("utf-8", "ignore"))["dt3"]
        tracks = DASH.from_url(url=mpd_url).to_tracks(language=mpd_lang)

        for track in tracks:
            track.data["license_url"] = license_url

        for track in tracks.audio:
            track.language = Language.make(language=mpd_lang)

        tracks.subtitles.clear()

        def strip_percentage(name: str) -> str:
            return re.sub(r"\s*\(\d+%\)", "", name).strip()

        # Handle subtitles
        if "subtitles" in mpd_data:
            for sub in mpd_data["subtitles"]:
                if sub.get("percentage", 0) > 95:
                    language_code = sub["srclang"]
                    language_name = sub.get("label", language_code)
                    language_name = strip_percentage(language_name)

                    if language_code.startswith("zh"):
                        language_code = CHINESE_LANGUAGE_MAP.get(language_code, language_code)

                    is_original = language_code == mpd_lang

                    subtitle_track = Subtitle(
                        id_=f"{sub.get('id', '')}_{language_code}",
                        url=sub["src"],
                        codec=Subtitle.Codec.SubRip,
                        language=language_code,
                        is_original_lang=is_original,
                        forced=False,
                        sdh=False,
                        name=language_name,
                    )

                    if sub.get("default"):
                        subtitle_track.default = True

                    tracks.add(subtitle_track, warn_only=True)

        return tracks

    def get_chapters(self, *_, **__) -> Chapters:
        return Chapters()

    def get_widevine_service_certificate(self, challenge: bytes, track: AnyTrack, *_, **__) -> bytes | str:
        # TODO: Cache the returned service cert
        return self.get_widevine_license(challenge, track)

    def get_widevine_license(self, challenge: bytes, track: AnyTrack, *_, **__) -> bytes:
        return self.session.post(url=track.data["license_url"], data=challenge).content
