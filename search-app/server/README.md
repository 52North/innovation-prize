# Geospatial Data Search App

SDSA (Spatial Data Search Assistant) is a server-based application designed to facilitate the development of an advanced search system for geospatial data.
Leveraging cutting-edge Large Language Models (LLMs), it enables a search capability that surpasses conventional methods found in metadata catalogs.

This README gives you a quick startup guide.
Refer to [SDSA documentaion](https://sdsadocs.readthedocs.io/) for more in-depth documentation.


## Installation

Ensure you have [poetry](https://python-poetry.org/) installed: 

```bash
sudo apt-get update
sudo apt-get install python3-poetry
```

> :bulb: Poetry Version
> 
> Make sure you have the right poetry version installed.
> For older distributions you may want to use `pipx`:
> 
> ```sh
> apt-get install pipx
> pipx install poetry
> pipx run poetry --version
> ```
>
> You also may want to ensure all pipx installed tooling is available from your `PATH`:
> 
> ```
> pipx ensurepath
> su -l
> ```

Clone this repository:

```bash
git clone https://github.com/52North/innovation-prize -b dev
```

Switch into the `./search-app/server` directory within the working copy you just cloned:

```bash
cd innovation-prize/search-app/server
poetry install --with=dev
```

## Configuration

> :warning: This app must be configured in order to work properly.

There are a few steps required:

1. **API keys**: 
   Can be provided via `.env` or [config file](./config/config.json)
2. **Data connectors**: 
   So far, it is possible to connect to a pygeoapi instance and then index collections of the instance.
   To add a pygeoapi instance, an entry is necessary in the  [config file](./config/config.json) like:
    ```
    "pygeoapi_instances": [
      "https://api.weather.gc.ca/",
    ]
    ```
4. **Index data collections**
   To enable contextual search, you need to first index the collections from connector instance.
   This is done using a local vector store called ([ChromaDB](https://docs.trychroma.com/)).
   Once the collections are indexed, the retrieval module performs a semantic search on the indexed metadata.
   

## Launch Application
```bash
# Go to the directory
cd search-app/server

# launch application
langchain serve --port=8000
```

## Indexing Collections

To start the indexing process, the app provides index endpoints:

- ```GET /fetch_documents``` for pygeoapi connectors
- ```GET /index_geojson_osm_features``` a demo connector for local geojson files

By calling these endpoints, the app synchronizes with the data endpoints specified in the config file.

> :bulb: **Note**
>
> To protect these endpoints you need to set the HTTP header `x-api-key`:
>
> ```
> curl -H "x-api-key: api-demo-key" http://localhost:8000/fetch_documents
> ```
>
> You can configure the API key via `.env` or [config file](./config/config.json).

A record manager is used to prevent duplicate entries in the index.
Also, it removes indexed documents that became unavailable.


## API Endpoints

Once the server is launched, a Swagger documentation is generated on `http://localhost:8000/docs`.

> :warning: Due to the Pydantic version used by Langserve, OpenAPI docs for `invoke`, `batch`, `stream`, `stream_log` endpoints will not be generated.
> However, API endpoints and playground should work as expected.
> If you need to see the docs, you can downgrade to Pydantic v1.
> For example, `pip install pydantic==1.10.13`.
> See [this issue](https://github.com/tiangolo/fastapi/issues/10360) for details.

The endpoints not included in the Swagger docs are:

- `/data/invoke` => Conversational module (search for data with chat)
  ```bash
  curl -X POST http://localhost:8000/data/invoke -H "Content-Type: application/json" -d '{"input": "Your query here"}'
  ```
- `/retrieve_pygeoapi/invoke` => Execute retrieval module without chat functionality
  ```bash
  curl -X POST http://localhost:8000/retrieve_pygeoapi/invoke -H "Content-Type: application/json" -d '{"input": "Your query here"}'
  ```


## Running in Docker

This project folder includes a Dockerfile that allows you to easily build and host your LangServe app.
Also, you may want to build and start via [docker compose setup](../compose.yml), which starts a demo client.

### Building the Image

To build the image, you simply:

```shell
docker build . -t my-langserve-app
```

If you tag your image with something other than `my-langserve-app`,
note it for use in the next step.


### Running the Image Locally

To run the image, you'll need to include any environment variables necessary for your application.

In the below example, we set the `OPENAI_API_KEY` environment variable via local environment and [map to local port](https://docs.docker.com/get-started/docker-concepts/running-containers/publishing-ports/) `8080`.

```shell
docker run -e OPENAI_API_KEY=$OPENAI_API_KEY -p 8080:8080 my-langserve-app
```
