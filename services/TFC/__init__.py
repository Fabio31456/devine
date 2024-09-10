import json
import re
import time
import sys
from datetime import datetime
from typing import Union, Generator, Optional
from urllib.parse import urljoin

import click
import requests

from devine.core.constants import AnyTrack
from devine.core.service import Service
from devine.core.titles import Episode, Movie, Movies, Series
from devine.core.tracks import Tracks, Chapters, Subtitle, Chapter
from devine.core.search_result import SearchResult
from devine.core.downloaders import curl_impersonate
from devine.core.utilities import get_ip_info
from devine.core.config import config
from devine.core.manifests.dash import DASH
import warnings

# Weird chunk error from search, we're using this to ignore the warning popup
warnings.filterwarnings("ignore", message="chunk_size is ignored")


class TFC(Service):
    """
    Service code for iWantTFC
    Written by @sp4rk.y

    Authorization: Cookies (Free and Paid Titles)
    Security: FHD@L3
    """

    @staticmethod
    @click.command(name="TFC", short_help="https://www.iwanttfc.com", help=__doc__)
    @click.argument("title", type=str)
    @click.option("-m", "--movie", is_flag=True, default=False, help="Title is a Movie.")
    @click.pass_context
    def cli(ctx, **kwargs):
        return TFC(ctx, **kwargs)

    def __init__(self, ctx, title: str, movie: bool):
        self.title = title
        self.is_movie = movie

        super().__init__(ctx)

        self.session.headers.update(
            {
                "user-agent": self.config["browser"]["headers"]["user-agent"],
            }
        )

    def search(self) -> Generator[SearchResult, None, None]:
        query = self.title
        headers = self.config["search"]["headers"]
        data = '{"requests":[{"query":"blabla","indexName":"www_iwanttfc_com_items","params":"hitsPerPage=200"},{"query":"blabla","indexName":"www_iwanttfc_com_tag_id_cast","params":"hitsPerPage=200"}]}'
        parsed_data = json.loads(data)
        parsed_data["requests"][0]["query"] = query
        parsed_data["requests"][1]["query"] = query
        response = requests.post(
            self.config["endpoints"]["api_search"],
            headers=headers,
            data=json.dumps(parsed_data),
        )
        response.raise_for_status()

        results = response.json()["results"]
        for result in results[0]["hits"]:
            title = result.get("title", {}).get("en", "")
            if not title:
                continue

                # Get detailed metadata
            detail_url = self.config["endpoints"]["api_playback"].format(js=self.get_js_value(), id=result["objectID"])
            detail_response = self.session.get(detail_url)
            detail_data = detail_response.json()

            # Extract description and media type
            description = detail_data.get("description", {}).get("en", "")[:200] + "..."
            media_type = "TV" if "children" in detail_data else "Movie"

            # Extract year and episode count for TV shows
            year = detail_data.get("release_year")
            episode_count = 0

            if media_type == "TV":
                episode_count = len(
                    [episode for episode in detail_data.get("children", []) if "-tlr" not in episode["id"]]
                )

            # Construct label with episode count for TV shows
            label = media_type
            if year:
                label += f" ({year})"
            if media_type == "TV":
                label += f" {episode_count} Episode{'' if episode_count == 1 else 's'}"

            # Create SearchResult with additional details
            yield SearchResult(
                id_=result["objectID"],
                title=title,
                description=description,
                label=label,
            )

    def get_js_value(self) -> Optional[str]:
        # Simulate browsing to the page and download the HTML file
        for _ in curl_impersonate(
            urls="https://www.iwanttfc.com/#!/browse",
            output_dir=config.directories.temp,
            filename="browse_page.html",
        ):
            pass

        # Read the downloaded HTML file
        html_path = config.directories.temp / "browse_page.html"
        with html_path.open("r", encoding="utf8") as f:
            html_content = f.read()

        # Find the script tag with the catalog URL and extract the 'js' value
        match = re.search(r'src="https://absprod-static.iwanttfc.com/c/6/catalog/(.*?)/script.js', html_content)
        if match:
            return match.group(1)

        return None

    def get_titles(self) -> Union[Movies, Series]:
        # Get title metadata
        try:
            title_metadata = self.session.get(
                self.config["endpoints"]["api_playback"].format(js=self.get_js_value(), id=self.title)
            ).json()
        except ValueError:
            self.log.warning("Show title does not exist.")
            sys.exit(1)

        # Check for GEOFENCE rules (this part remains the same)
        rules = title_metadata.get("rules", {}).get("rules", [])
        for rule in rules:
            if rule.get("start") <= time.time() * 1000 <= rule.get("end"):  # Check if rule is active
                required_countries = rule.get("countries", [])
                if required_countries:
                    current_region = get_ip_info(self.session)["country"].lower()
                    if not any(x.lower() == current_region for x in required_countries):
                        self.log.warning(
                            f"Show '{title_metadata['id']}' requires a proxy in {', '.join(required_countries)} "
                            f"but your current region is {current_region.upper()}. "
                        )
                        sys.exit(0)

        if "children" in title_metadata:
            # TV Show - Extract episodes with correct season info
            episodes = []
            for episode in title_metadata.get("children", []):
                episode_id = episode["id"]

                # Extract season and episode number from ID
                match = re.match(r".*-s(\d+)e(\d+)$", episode_id, re.IGNORECASE)
                if not match:
                    continue  # Skip if unable to parse season and episode

                season, number = map(int, match.groups())

                # Create Episode object with season and episode number
                episode_obj = Episode(
                    id_=episode_id,
                    title=title_metadata.get("title", {}).get("en"),
                    season=season,
                    number=number,
                    year=title_metadata.get("release_year"),
                    service=self.__class__,
                )
                episodes.append(episode_obj)

            return Series(episodes)

        else:
            # Movie - Extract movie details
            movie_name = title_metadata.get("title", {}).get("en")
            movie_year = title_metadata.get("release_year")

            # Create Movie object
            movie_class = Movie(
                id_=self.title,
                name=movie_name,
                year=movie_year,
                service=self.__class__,
            )

        return Movies([movie_class])

    def get_tracks(self, title: Union[Movie, Episode]) -> Tracks:
        if isinstance(title, Episode) and not title.data:
            # Fetch detailed episode data if needed
            episode_data = self.session.get(
                self.config["endpoints"]["api_playback"].format(js=self.get_js_value(), id=title.id)
            ).json()
            title.data = episode_data

        # Extract MPD URLs
        mpd_urls = episode_data.get("media", {}).get("mpds", [])

        # Extract subtitle URLs and languages
        subtitle_data = [
            (
                urljoin(self.config["endpoints"]["api_subtitle"], caption.get("id")) + ".vtt",
                caption.get("lang"),
            )
            for caption in episode_data.get("media", {}).get("captions", [])
        ]

        tracks = Tracks()

        # Create Video and Audio Tracks from MPDs, avoiding duplicates and storing episode_id
        for mpd_url in mpd_urls:
            mpd_tracks = DASH.from_url(url=mpd_url, session=self.session).to_tracks(language=title.language or "fil")
            for track in mpd_tracks:
                if not tracks.exists(by_id=track.id):
                    track.data["episode_id"] = episode_data.get("id")  # Store episode_id in track.data
                    tracks.add(track)

        for track in tracks.audio:
            mpd_lang = language = title.language or "fil"
            track.language.language = mpd_lang
            track.language._broader = [mpd_lang, "und"]
            track.language._dict = {"language": mpd_lang}
            track.language._str_tag = mpd_lang

        # Create Subtitle Tracks for all languages, avoiding duplicates
        for subtitle_url, language in subtitle_data:
            subtitle_track = Subtitle(
                id_=subtitle_url.split("/")[-1].split(".")[0],
                url=subtitle_url,
                codec=Subtitle.Codec.WebVTT,
                language=language,
                is_original_lang=language == title.language,
            )

            if not tracks.exists(by_id=subtitle_track.id):
                tracks.add(subtitle_track)

        chapters = self.get_chapters(title)
        tracks.chapters = Chapters(chapters)

        return tracks

    def get_chapters(self, title: Union[Movie, Episode]) -> list[Chapter]:
        if isinstance(title, Episode) and not title.data:
            episode_data = self.session.get(
                self.config["endpoints"]["api_playback"].format(js=self.get_js_value(), id=title.id)
            ).json()
            title.data = episode_data

        cuepoints = title.data.get("cuepoints", [])

        # Sort the cuepoints
        sorted_cuepoints = sorted(cuepoints, key=lambda x: datetime.strptime(x, "%H:%M:%S.%f"))

        chapters = [
            Chapter(name="Chapter 1", timestamp="00:00:00.000")
        ]

        for i, cuepoint in enumerate(sorted_cuepoints, start=2):
            try:
                timestamp = datetime.strptime(cuepoint, "%H:%M:%S.%f").time()
                chapters.append(Chapter(name=f"Chapter {i}", timestamp=timestamp.strftime("%H:%M:%S.%f")[:-3]))
            except ValueError:
                self.log.warning(f"Invalid cuepoint format: {cuepoint}")

        return chapters

    def get_widevine_service_certificate(self, challenge: bytes, track: AnyTrack, *_, **__) -> bytes | str:
        # TODO: Cache the returned service cert
        return self.get_widevine_license(challenge, track)

    def get_widevine_license(self, challenge: bytes, track: AnyTrack, *_, **__) -> bytes:
        episode_id = track.data.get("episode_id")
        license_url = self.config["endpoints"]["api_license"]
        license_url += f"?itemID={episode_id}"
        license_url += f"&UserAuthentication={self.session.cookies.get('UserAuthentication')}"
        license_url += "&build=52b61137ff3af37f55e0"
        return self.session.post(url=license_url, data=challenge).content
