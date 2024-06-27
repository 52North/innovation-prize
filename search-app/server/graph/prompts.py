from langchain.prompts import PromptTemplate
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_core.output_parsers import JsonOutputParser, StrOutputParser

# Define your desired data structure.
class SearchDict(BaseModel):
    spatial: str = Field(description="Get the spatial context. Can be a location or place or a region")
    thematic: str = Field(description="Get the thematic context. E.g. 'precipitation' or 'extreme weather'. It can also be the data type, such as 'administrative unit', or 'land use classification'")
    temporal: str = Field(description="Get the temporal context. must be a certain time period (e.g. 2010-2020) or a certain year, month or a time reference (e.g. last decade, this year) ")

### Analyze the spatial context in the query:
class SpatialContext(BaseModel):
    spatial_entities: str = Field(description="Get the spatial context. Can be a location or place or a region")
    spatial_scale: str = Field(description="Get the spatial scale (Local, City, Regional, National, Continental, Global")

### Analyze the spatial context in the query:
class OffTopic(BaseModel):
    off_topic: str = Field(description="yes or no. Decision of whether the user prompt is off-topic or not")
    off_topic_answer: str = Field(description="answer in case the topic is off-topic")


def generate_off_topic_answer():
        # follow_up generator
    parser = JsonOutputParser(pydantic_object=OffTopic)
    answer_prompt = PromptTemplate(
        template="""
        You assist users in finding environmental datasets. Based on the user input you recieve, you have to decide if the user wants to chat about data or not.
        If the user wants to chat about any other topic not related to environmental, climate or geospatial topics, please politely 
        point to the user that you can only assist in finding data or metadata. This can also be chitchat like 'hello, how are you?'
        Please output the decision (off_topic: yes/no) and, if yes, an answer.

        \n{format_instructions}\n{input}\n""",
        input_variables=["input"],
        partial_variables={"format_instructions": parser.get_format_instructions()},
    )
    return answer_prompt, parser

def generate_search_criteria_prompt():
    # Set up a parser + inject instructions into the prompt template.
    parser = JsonOutputParser(pydantic_object=SearchDict)
    prompt = PromptTemplate(
        template="""
        Extract the the spatio-temporal features of the query.
        If no information is provided, never make it up or halucinate a value to any of the keys in the search_dict.
        In case you don't have a value for any values, just write a empty string.

        ***important system note***: Please use double quotation marks ("") when generating the keys and values of the dict instead of single quotation marks ('').

        \n{format_instructions}\n{input}\n""",
        input_variables=["input"],
        partial_variables={"format_instructions": parser.get_format_instructions()},
    )
    return prompt, parser


def generate_follow_up_prompt():
        # follow_up generator
    follow_up_prompt = PromptTemplate(
        template="""
        You recieve a dict including search_criteria (search_dict). Please ask the user to provide more information for the keys that are missing in the dict.
        Please do not reference the search_dict as the user does not know about this (it is only used in the background). Formulate a short answer in natural language

        Here is the search_dict: {search_dict}
        Answer: """,
        input_variables=["search_dict"]
    )
    return follow_up_prompt


def generate_temporal_dim_prompt():
    # Find out if layer has temporal dimension:
    # use few-shot learning here
    temporal_prompt = PromptTemplate(
        template="""
        You recieve a query for environmental data and need to find out if the desired data has a temporal dimension.
        Answer with 'yes' or 'no'to indicate whether temporal dimension is included in the required data.

        Here are samples of data WITH temporal dimension:
        * Event-based data: e.g. precipitation, droughts, floodings
        * Time series data: e.g. river levels, climate projections
        * Seasonal data: e.g. heat days in summer months
        * Historical data: e.g. observational data from weather stations
        * Real-time data: e.g. sensor data
        * Remote sensing data: e.g. satellite imagery

        Here are samples of data WITHOUT temporal dimension
        * Topographic data: e.g Digital Evalation Model
        * Political Boundaries: e.g. administrative units
        * Landcover data: e.g. landuse information
        * Geological data: e.g. soil type maps
        * Socio-economic data: e.g. GDP and employment statistics
        * Transportation data: e.g. road networks and traffic patterns

        Here is the query: {query}

        Answer:""", 
        input_variables=["query"]
        )
    return temporal_prompt

def generate_spatial_prompt():
    # Set up a parser + inject instructions into the prompt template.
    spatial_parser = JsonOutputParser(pydantic_object=SpatialContext)

    spatial_prompt = PromptTemplate(
        template="""
        Extract spatial entities and determine the spatial scale ("Local", "City", "Regional", "National", "Continental", "Global") from the given query.

        Output:
        1. Spatial Entities
        2. Spatial Scale

        Examples:
        Example 1:
        - Query: "Datasets for temperature variations in Berlin"
        - Output:
        1. Spatial Entities: Berlin
        2. Spatial Scale: City

        Example 2:
        - Query: "Climate change datasets for Europe"
        - Output:
        1. Spatial Entities: Europe
        2. Spatial Scale: Continental

        Example 3:
        - Query: "Soil moisture datasets for California and Nevada"
        - Output:
        1. Spatial Entities: California, Nevada
        2. Spatial Scale: Regional

        Example 4:
        - Query: "Global air quality datasets"
        - Output:
        1. Spatial Entities: Global
        2. Spatial Scale: Global

        Example 5:
        - Query: "Datasets on water quality in the Mississippi River Basin"
        - Output:
        1. Spatial Entities: Mississippi River Basin
        2. Spatial Scale: Regional

        Guidelines:
        - Spatial entities: cities, regions, countries, continents, geographic features.
        - Determine the scale based on the entities' extent:
        - Local: Locations within a city.
        - City: Individual cities.
        - Regional: Multiple cities or parts of a country.
        - National: Entire countries.
        - Continental: Entire continents.
        - Global: Worldwide or multiple continents.

        \n{format_instructions}\n{query}\n""",
        input_variables=["query"],
        partial_variables={"format_instructions": spatial_parser.get_format_instructions()}
    )
    return spatial_prompt

def generate_final_answer_prompt():
    ### Generate final answer
    # Prompt
    final_answer_prompt = PromptTemplate(
        template="""
        You are an assistant for question-answering tasks. 
        Use the following pieces of retrieved context to answer the question. If you don't know the answer, just say that you don't know. 
        Use three sentences maximum and keep the answer concise
        Question: {query} 
        Context: {context} 
        Answer:""",
        input_variables=["query", "context"],
    )
    return final_answer_prompt