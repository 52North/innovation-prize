from loguru import logger
from config.config import Config
import geojson
from typing import List, Dict
from langchain.schema import Document
import glob
import asyncio
import aiohttp
import requests
from bs4 import BeautifulSoup
from tqdm.asyncio import tqdm
import json
import re 

from config.config import CONFIG, package_dir

def is_url(string):
    # Regex pattern for matching URLs
    pattern = re.compile(r'^(https?|ftp):\/\/[^\s/$.?#].[^\s]*$')
    return re.match(pattern, string) is not None

class GeoJSON():
    """
    The GeoJSON class processes GeoJSON files containing OpenStreetMap (OSM) features, 
    adding textual descriptions for specific tags from the OSM Wiki. 

    Key functionalities include:
    - Loading GeoJSON files from a directory.
    - Filtering features based on a specified tag (e.g., 'building').
    - Asynchronously fetching descriptions for tags from the OSM Wiki.
    - Adding fetched descriptions to the features.
    - Grouping features by tag for summary documentation.
    - Converting features to structured documents.

    Attributes:
        features (List[dict]): A list of GeoJSON features filtered by the tag_name.
        tag_name (str): The tag to filter and describe features, defaults to 'building'.

    Methods:
        __init__(file_dir: str = None, tag_name: str = "building"): 
            Initializes the class, loads GeoJSON files, and filters features by tag.
        _filter_meaningful_features(features: List[dict], tag_name: str) -> List[dict]: 
            Filters features based on the presence of the specified tag.
        _get_osm_tag_description_async(tag: str, semaphore: asyncio.Semaphore) -> str: 
            Asynchronously fetches the description for a tag from the OSM Wiki.
        _get_descriptions_for_tags() -> Dict[str, str]: 
            Gathers descriptions for all unique tags in the features.
        add_descriptions_to_features() -> None: 
            Adds descriptions to the features.
        _group_features_by_tag() -> Dict[str, List[dict]]:
            Groups features by their tag value.
        _convert_to_geojson(data) -> str: 
            Converts a list of features into a GeoJSON string.
        _get_feature_description(feature: dict) -> str: 
            Creates a detailed description of a feature.
        _features_to_docs() -> List[Document]: 
            Converts features into a list of Document objects for further use.
    """
    def __init__(self, file_dir: str = None, tag_name: str = None):     
        self.file_dir = file_dir   
        if self.file_dir and is_url(self.file_dir):
            """We assume the online resource to be a collection published via a PyGeoAPI instance"""
            logger.info("Fetching GeoJSON features from online resource. This may take a few minutes.")
            params = {"f": "json", "limit": 10000}
            gj = self._fetch_features_from_online_resource(params)
            print(f"Retrieved {len(gj)} features")
            self.tag_name = tag_name
            if self.tag_name:
                self.features =  self._filter_meaningful_features(gj, self.tag_name)
            else:
                self.features = gj
        else:
            if not self.file_dir:
                self.file_dir = str(package_dir.joinpath(CONFIG.local_geojson_files[0]))
            logger.info(f"Looking for files in following dir: {self.file_dir}")
            gj_files = []
            for file in glob.glob(f"{self.file_dir}/*.geojson"):
                logger.info(f"Extracting features from file: {file}")
                with open(file) as f:
                    gj = geojson.load(f)
                    gj_files.extend(gj['features'])
                    # Todo: Maybe add filename to the properties of each feature

            self.features = self._filter_meaningful_features(gj_files, tag_name)

        logger.info(f"Recieved {len(self.features)} features")
        self.tag_name = tag_name

    def _fetch_features_from_online_resource(self, url, params):
        offset = 0
        all_features = []

        while True:
            params['offset'] = offset
            response = requests.get(self.file_dir, params=params)
            response_json = response.json()
            features = response_json.get('features', [])
            if not features:
                break
            all_features.extend(features)
            offset += params['limit']

        # copy id from pygeoapi in properties
        for f in all_features:
            f['properties']['id'] = f['id']

        return all_features
    
    def _filter_meaningful_features(self, features: List[dict], tag_name: str) -> List[dict]:
        filtered_features = list(filter(lambda feature: feature.get("properties", {}).get(tag_name) != "yes", features))
        return filtered_features

    async def _get_osm_tag_description_async(self, tag, semaphore) -> str:
        tag_url = tag.replace(':', '%3A').replace('=', '%3D')
        url = f"https://wiki.openstreetmap.org/wiki/Tag:{tag_url}"
        
        async with semaphore:  # Limit the number of concurrent requests
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        return tag.split("=")[-1]
                    html_content = await response.text()

        soup = BeautifulSoup(html_content, 'html.parser')
        content_div = soup.find("div", {"class": "mw-parser-output"})
        if content_div:
            paragraphs = content_div.find_all("p")
            if paragraphs:
                return paragraphs[0].get_text(strip=True)
        
        return tag.split("=")[-1]

    async def _get_descriptions_for_tags(self) -> Dict[str, str]:
        semaphore = asyncio.Semaphore(100)  # Limit to 100 concurrent requests

        tags = {f"{self.tag_name}={feature['properties'][self.tag_name]}" for feature in self.features}
        tasks = {tag: self._get_osm_tag_description_async(tag, semaphore) for tag in tags}

        descriptions = await tqdm.gather(*tasks.values(), desc="Fetching descriptions")
        return dict(zip(tasks.keys(), descriptions))

    async def add_descriptions_to_features(self) -> None:
        logger.info(f"Fetching descriptions for {len(self.features)} OSM features")
        tag_description_map = await self._get_descriptions_for_tags()
        
        for feature in self.features:
            tag = f"{self.tag_name}={feature['properties'][self.tag_name]}"
            feature['properties']['description'] = tag_description_map.get(tag, "Description not available")

    def _group_features_by_tag(self) -> Dict[str, List[dict]]:
        grouped_features = {}
        for feature in self.features:
            tag = f"{self.tag_name}={feature['properties'][self.tag_name]}"
            if tag not in grouped_features:
                grouped_features[tag] = []
            grouped_features[tag].append(feature)
        return grouped_features

    def _convert_to_geojson(self, data):
        geojson_data = {
            "type": "FeatureCollection",
            "features": data
        }
        
        # Generic cleanup of description fields
        for feature in geojson_data["features"]:
            if "properties" in feature and "description" in feature["properties"]:
                feature["properties"]["description"] = feature["properties"]["description"].rstrip('.')
    
        return json.dumps(geojson_data, indent=2)

    def _get_feature_description(self, feature):
        properties = feature['properties']
        address_components = ['addr:street', 'addr:housenumber', 'addr:city', 'addr:postcode', 'addr:country']
        address = ", ".join([properties.get(key, '') for key in address_components if properties.get(key, '')]).strip(", ")
        
        description_parts = []
        if address:
            description_parts.append(f"Address: {address}")
        
        for key, value in properties.items():
            if key not in address_components:
                description_parts.append(f"{key}: {value}")
        
        return "\n".join(description_parts)

    async def _features_to_docs(self) -> List[Document]:
        if self.tag_name:
            await self.add_descriptions_to_features()

        # Part 1: Create documents for features with names
        features_with_names = list(filter(lambda feature: feature if feature["properties"].get("name", "") else None, self.features))
        name_docs = []
        for feature in features_with_names:
            properties = feature['properties']
            name = properties.get("name", "Unknown")
            description = self._get_feature_description(feature)
            page_content = f"Name: {name}\n\n{description}"
            metadata = {
                "id": str(feature["id"]),
                "source": "Feature collection hosted from local GeoJSON",
                "type": properties.get(self.tag_name, "Unknown"),
                "feature": json.dumps(feature["geometry"] , indent=2),
                # "url": str(properties.get("id", "url"))
            }

            for property, value in feature["properties"].items():
                metadata[property] = value
            
            name_docs.append(Document(page_content=page_content, metadata=metadata))

        # Part 2: Create documents for grouped features by tag
        grouped_features = self._group_features_by_tag()
        tag_docs = []
        for tag, features in grouped_features.items():
            tag_description = features[0]['properties'].get('description', tag.replace('=', ': '))
            page_content = f"{tag}: {tag_description}\n\nThis collection includes {len(features)} features of type {tag}."
            if is_url(self.file_dir):
                source = self.file_dir.replace("/items", "")
            else:
                source = "Feature collection hosted from local GeoJSON"
            metadata = {
                "tag": tag,
                "count": len(features),
                "features": self._convert_to_geojson(features),
                "source": source  # Update this with the actual URL if needed
            }
            tag_docs.append(Document(page_content=page_content, metadata=metadata))

        return name_docs + tag_docs