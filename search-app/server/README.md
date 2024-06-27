# Geospatial Data Search App

## Project description
...
### Component Overview

## Installation

Install the LangChain CLI if you haven't yet

```bash
pip install -U langchain-cli
```
## Configuration
:warning: This app must be configured in order to work properly.
There are a few steps required:
1. **Add API-keys** (e.g. OPENAI-API-KEY) to the [config file](./config/config.json)
2. **Add connectors**: So far, it is possible to connect to a pygeoapi instance and then index collections of the instance. To add a pygeoapi instance, An entry is necessary in the  [config file](./config/config.json) like: ```"pygeoapi_instances": 
["https://api.weather.gc.ca/", 
...]```
4. **Index collections of pygeoapi instance**: To enable contextual search, you need to first index the collections from the specified pygeoapi instance. This is done using a local vector store called ([ChromaDB](https://docs.trychroma.com/)). Once the collections are indexed, the retrieval module performs a semantic search on the indexed metadata.
To start the indexing process, the app provides an endpoint: ```GET /fetch_documents```. By calling this endpoint, the app synchronizes with the pygeoapi instances specified in the config file. A record manager is used to prevent duplicate entries in the index and to remove indexed documents that are no longer available from the pygeoapi server. 

## Launch Application
```bash
# Go to the directory
cd search-app/server

# launch application
langchain serve --port=8000
```

## Adding packages

```bash
# adding packages from 
# https://github.com/langchain-ai/langchain/tree/master/templates
langchain app add $PROJECT_NAME

# adding custom GitHub repo packages
langchain app add --repo $OWNER/$REPO
# or with whole git string (supports other git providers):
# langchain app add git+https://github.com/hwchase17/chain-of-verification

# with a custom api mount point (defaults to `/{package_name}`)
langchain app add $PROJECT_NAME --api_path=/my/custom/path/rag
```

Note: you remove packages by their api path

```bash
langchain app remove my/custom/path/rag
```

## Running in Docker

This project folder includes a Dockerfile that allows you to easily build and host your LangServe app.

### Building the Image

To build the image, you simply:

```shell
docker build . -t my-langserve-app
```

If you tag your image with something other than `my-langserve-app`,
note it for use in the next step.

### Running the Image Locally

To run the image, you'll need to include any environment variables
necessary for your application.

In the below example, we inject the `OPENAI_API_KEY` environment
variable with the value set in my local environment
(`$OPENAI_API_KEY`)

We also expose port 8080 with the `-p 8080:8080` option.

```shell
docker run -e OPENAI_API_KEY=$OPENAI_API_KEY -p 8080:8080 my-langserve-app
```
