# 52°North Innovation-Prize: Spatial Data Search Assistant

You have multiple options to start the application:

1. Docker compose setup
1. Local [devcontainer](https://containers.dev/) setup
1. Start components separately
   - Start python module to run the backend
   - Start the demo client via `npm`

Refer to the corresponding sections below, how to start.
Once started, you will see

```
INFO:     Application startup complete.
```

Now, you can [create the embeddings via API](#create-embeddings-via-api).


## Start Docker Compose

Copy `sample.env` to `.env` and start via `docker compose up -d && docker compose logs -f`.

## Developing via DevConatiner

Helpful for developing within a docker compose setup.

- Install vscode on your system
- Open the vscode via `code ./innovation-prize/search-app/`
- Install the [Dev Container extension](https://code.visualstudio.com/docs/devcontainers/containers)
- (Build and) Open via command palette and type: `DevContainers: Reopen in Container`
- Once dropped into the container, you can start by pressing `F5`

## Start Components Separately

### Start Backend

Refer to [./server/README.md](./server/README.md) how to start.

### Start Demo Client

Refer to [./client/demo_client/README.md](./client/demo_client/README.md) how to start.

## Create Embeddings via API

Once the application has started, some demo data of buildings in Dresden is available.
To make the data available for search, enrich that data (OSM) with information from [the OSM wiki](https://wiki.openstreetmap.org/):

```
curl -v -H "x-api-key: demo-api-key" localhost:8000/index_geojson_osm_features
```

All pygeoapi instances have a different enpoint to trígger indexing.
Just run

```
curl -v -H "x-api-key: demo-api-key" localhost:8000/fetch_documents
```

> :bulb: Indexing will take a while

As soon as a search index is available you can either

- start the demo client
- check the OpenAPI docs (at http://localhost:8000/docs), 
- play with custom prompts via [Google Colab notebook](https://colab.research.google.com/drive/1GDRvYrQrRYi0xCl3102-xE1jaf_Brn8Z), ...
- create a new client acting with the API (e.g. Open Pioneer)
- ...
